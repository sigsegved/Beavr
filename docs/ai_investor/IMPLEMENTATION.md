# Beavr AI Investor: Implementation Roadmap

## Quick Start Guide

This document provides the technical implementation details for the AI Investor architecture. Follow this alongside the [Architecture Document](./AI_INVESTOR_ARCHITECTURE.md).

---

## Phase 1: Foundation (Weeks 1-3)

### 1.1 Copilot SDK Integration

For MVP, we use the official [GitHub Copilot Python SDK](https://github.com/github/copilot-sdk/tree/main/python).

```bash
# Prerequisites
# 1. GitHub Copilot CLI installed and authenticated
#    See: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli

# 2. Install the Copilot SDK (from the copilot-sdk repo)
pip install copilot-sdk

# Or install from source
git clone https://github.com/github/copilot-sdk.git
cd copilot-sdk/python
pip install -e ".[dev]"
```

**Beavr Copilot Wrapper:**

```python
# src/beavr/llm/copilot.py
"""GitHub Copilot SDK integration for Beavr AI Investor."""

import asyncio
import json
from typing import TypeVar

from copilot import CopilotClient as BaseCopilotClient, define_tool
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class CopilotConfig(BaseModel):
    """Configuration for Copilot SDK."""
    model: str = Field(default="gpt-4.1", description="Model to use")
    streaming: bool = Field(default=False, description="Enable streaming responses")
    timeout: float = Field(default=60.0)


class CopilotClient:
    """
    Beavr wrapper around GitHub Copilot Python SDK.
    
    Provides structured LLM calls with Pydantic schema validation
    for AI Investor agents.
    """
    
    def __init__(self, config: CopilotConfig | None = None):
        self.config = config or CopilotConfig()
        self._client: BaseCopilotClient | None = None
        self._started = False
    
    async def start(self) -> None:
        """Initialize the Copilot client."""
        if not self._started:
            self._client = BaseCopilotClient()
            await self._client.start()
            self._started = True
    
    async def stop(self) -> None:
        """Clean up resources."""
        if self._client and self._started:
            await self._client.stop()
            self._started = False
    
    async def reason(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T]
    ) -> T:
        """
        Execute LLM reasoning with structured output.
        
        Uses a tool to ensure valid JSON output matching the Pydantic schema.
        
        Args:
            system_prompt: Agent persona/instructions
            user_prompt: Current context and request
            output_schema: Pydantic model for response validation
            
        Returns:
            Validated instance of output_schema
        """
        await self.start()
        
        # Define a tool that the model will call to return structured output
        result_holder = {"data": None}
        
        @define_tool(description="Return your analysis in structured format")
        async def return_analysis(params: output_schema) -> str:
            result_holder["data"] = params
            return "Analysis recorded"
        
        # Create session with the structured output tool
        session = await self._client.create_session({
            "model": self.config.model,
            "streaming": self.config.streaming,
            "tools": [return_analysis],
            "system_message": {"content": system_prompt},
        })
        
        # Wait for completion
        done = asyncio.Event()
        
        def on_event(event):
            if event.type.value == "session.idle":
                done.set()
        
        session.on(on_event)
        
        # Send prompt that instructs model to use the tool
        await session.send({
            "prompt": f"{user_prompt}\n\nUse the return_analysis tool to provide your response."
        })
        await done.wait()
        
        await session.destroy()
        
        if result_holder["data"] is None:
            raise RuntimeError("Model did not return structured output")
        
        return result_holder["data"]
    
    async def complete(self, prompt: str) -> str:
        """Simple text completion without structured output."""
        await self.start()
        
        session = await self._client.create_session({
            "model": self.config.model,
            "streaming": False,
        })
        
        done = asyncio.Event()
        response_content = {"text": ""}
        
        def on_event(event):
            if event.type.value == "assistant.message":
                response_content["text"] = event.data.content
            elif event.type.value == "session.idle":
                done.set()
        
        session.on(on_event)
        await session.send({"prompt": prompt})
        await done.wait()
        
        await session.destroy()
        return response_content["text"]
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, *args):
        await self.stop()
```

**Usage in Agents:**

```python
from beavr.llm.copilot import CopilotClient, CopilotConfig

# Use as async context manager
async with CopilotClient(CopilotConfig(model="gpt-4.1")) as copilot:
    # Get structured analysis from the model
    analysis = await copilot.reason(
        system_prompt="You are a market analyst...",
        user_prompt="Analyze these indicators...",
        output_schema=MarketAnalysis
    )
    print(f"Regime: {analysis.regime}, Confidence: {analysis.confidence}")
```

### 1.2 Base Agent Interface

```python
# src/beavr/agents/base.py
"""Base agent interface for AI Investor."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.models.signal import Signal


class AgentContext(BaseModel):
    """
    Context provided to agents for decision making.
    
    This is the "view of the world" that each agent receives.
    """
    # Time
    current_date: date
    timestamp: datetime
    
    # Market data
    prices: dict[str, Decimal]           # symbol -> current price
    bars: dict[str, list[dict]]          # symbol -> recent OHLCV bars
    indicators: dict[str, dict[str, float]]  # symbol -> {rsi, sma_20, etc.}
    
    # Portfolio state
    cash: Decimal
    positions: dict[str, Decimal]        # symbol -> shares
    portfolio_value: Decimal
    
    # Risk state
    current_drawdown: float              # current drawdown from peak
    risk_budget: float                   # available risk budget (0-1)
    
    # Regime (from Market Analyst)
    regime: Optional[str] = None         # bull, bear, sideways, volatile
    regime_confidence: float = 0.0
    
    # Events/News (future)
    events: list[dict[str, Any]] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


class AgentProposal(BaseModel):
    """
    Output from an agent's analysis.
    
    Each agent produces proposals that are aggregated by the orchestrator.
    """
    agent_name: str
    timestamp: datetime
    
    # Proposed signals
    signals: list[Signal] = Field(default_factory=list)
    
    # Confidence and reasoning
    conviction: float = Field(ge=0.0, le=1.0)
    rationale: str
    
    # Risk assessment
    risk_score: float = Field(ge=0.0, le=1.0, default=0.5)
    risk_factors: list[str] = Field(default_factory=list)
    
    # Metadata
    model_version: str = "unknown"
    processing_time_ms: float = 0.0


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.
    
    Each agent represents a specialized "persona" with a specific
    role and expertise in the trading system.
    """
    
    # Class-level metadata (override in subclass)
    name: ClassVar[str] = "Base Agent"
    role: ClassVar[str] = "base"  # analyst, trader, risk
    description: ClassVar[str] = ""
    version: ClassVar[str] = "0.1.0"
    
    def __init__(self, copilot: "CopilotClient"):
        """
        Initialize agent with Copilot client.
        
        Args:
            copilot: GitHub Copilot SDK client for LLM reasoning
        """
        self.copilot = copilot
    
    @abstractmethod
    async def analyze(self, ctx: AgentContext) -> AgentProposal:
        """
        Analyze context and propose actions.
        
        This is the main entry point called by the orchestrator.
        
        Args:
            ctx: Current market/portfolio context
            
        Returns:
            AgentProposal with signals and reasoning
        """
        pass
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the agent's persona/system prompt.
        
        This defines the agent's role and expertise for the LLM.
        """
        pass
    
    def build_user_prompt(self, ctx: AgentContext) -> str:
        """
        Build the user prompt from context.
        
        Override for custom prompt formatting.
        """
        return f"""
Current Date: {ctx.current_date}
Regime: {ctx.regime or 'unknown'} (confidence: {ctx.regime_confidence:.2f})
Cash: ${ctx.cash:,.2f}
Portfolio Value: ${ctx.portfolio_value:,.2f}
Current Drawdown: {ctx.current_drawdown:.1%}
Risk Budget: {ctx.risk_budget:.1%}

Positions:
{self._format_positions(ctx)}

Recent Prices:
{self._format_prices(ctx)}

Indicators:
{self._format_indicators(ctx)}

Based on this information, provide your analysis and recommendations.
"""
    
    def _format_positions(self, ctx: AgentContext) -> str:
        if not ctx.positions:
            return "  (no positions)"
        lines = []
        for symbol, shares in ctx.positions.items():
            price = ctx.prices.get(symbol, Decimal(0))
            value = shares * price
            lines.append(f"  {symbol}: {shares} shares @ ${price} = ${value:,.2f}")
        return "\n".join(lines)
    
    def _format_prices(self, ctx: AgentContext) -> str:
        lines = []
        for symbol, price in ctx.prices.items():
            lines.append(f"  {symbol}: ${price}")
        return "\n".join(lines)
    
    def _format_indicators(self, ctx: AgentContext) -> str:
        lines = []
        for symbol, inds in ctx.indicators.items():
            ind_str = ", ".join(f"{k}={v:.2f}" for k, v in inds.items())
            lines.append(f"  {symbol}: {ind_str}")
        return "\n".join(lines)
```

### 1.3 Market Analyst Agent

```python
# src/beavr/agents/market_analyst.py
"""Market Analyst agent for regime detection."""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent


class MarketAnalysis(BaseModel):
    """Structured output from market analysis."""
    regime: str = Field(description="Market regime: bull, bear, sideways, volatile")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in regime")
    key_observations: list[str] = Field(description="Notable patterns observed")
    risk_factors: list[str] = Field(description="Current risk concerns")
    summary: str = Field(description="2-3 sentence market assessment")
    recommended_risk_posture: float = Field(
        ge=0.0, le=1.0,
        description="Recommended risk budget (0=defensive, 1=aggressive)"
    )


class MarketAnalystAgent(BaseAgent):
    """
    Market Analyst agent for regime detection and market assessment.
    
    This agent runs first in the daily cycle to set the context
    for trading agents.
    """
    
    name: ClassVar[str] = "Market Analyst"
    role: ClassVar[str] = "analyst"
    description: ClassVar[str] = "Analyzes market conditions and detects regime"
    version: ClassVar[str] = "0.1.0"
    
    def get_system_prompt(self) -> str:
        return """You are a professional market analyst for an automated trading system.
Your role is to analyze market data and determine the current market regime.

REGIME DEFINITIONS:
- bull: Sustained uptrend with higher highs and higher lows. RSI generally >50, price above key SMAs.
- bear: Sustained downtrend with lower highs and lower lows. RSI generally <50, price below key SMAs.
- sideways: Range-bound price action. No clear trend direction. Mixed signals.
- volatile: High volatility regime. Large price swings, uncertainty. Risk-off recommended.

ANALYSIS FRAMEWORK:
1. Trend: Is price above/below 20-day and 50-day SMAs?
2. Momentum: What does RSI indicate? Overbought (>70), oversold (<30)?
3. Volume: Are volume patterns confirming price moves?
4. Breadth: How are multiple symbols behaving relative to each other?

OUTPUT REQUIREMENTS:
- Be concise and actionable
- Focus on what matters for trading decisions
- Quantify confidence based on signal alignment
- Flag specific risk factors that could impact positions
"""
    
    async def analyze(self, ctx: AgentContext) -> AgentProposal:
        """Analyze market and determine regime."""
        start_time = datetime.now()
        
        # Build specialized prompt for market analysis
        user_prompt = self._build_market_prompt(ctx)
        
        # Get structured analysis from Copilot
        analysis: MarketAnalysis = await self.copilot.reason(
            system_prompt=self.get_system_prompt(),
            user_prompt=user_prompt,
            output_schema=MarketAnalysis
        )
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Market analyst doesn't produce trading signals, just analysis
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=[],  # No direct signals
            conviction=analysis.confidence,
            rationale=analysis.summary,
            risk_score=1.0 - analysis.recommended_risk_posture,
            risk_factors=analysis.risk_factors,
            model_version=self.version,
            processing_time_ms=processing_time,
        )
    
    def _build_market_prompt(self, ctx: AgentContext) -> str:
        """Build specialized prompt for market analysis."""
        # Format recent bars as a summary
        bars_summary = []
        for symbol, bars in ctx.bars.items():
            if bars:
                recent = bars[-5:] if len(bars) >= 5 else bars
                changes = []
                for i in range(1, len(recent)):
                    prev_close = recent[i-1].get('close', 0)
                    curr_close = recent[i].get('close', 0)
                    if prev_close:
                        pct = (curr_close - prev_close) / prev_close * 100
                        changes.append(f"{pct:+.1f}%")
                bars_summary.append(f"{symbol}: last 5 days: {', '.join(changes)}")
        
        return f"""
Analyze the current market conditions based on the following data:

DATE: {ctx.current_date}

PRICES AND INDICATORS:
{self._format_indicators(ctx)}

RECENT PRICE ACTION:
{chr(10).join(bars_summary)}

CURRENT PORTFOLIO STATE:
- Cash: ${ctx.cash:,.2f}
- Portfolio Value: ${ctx.portfolio_value:,.2f}
- Current Drawdown: {ctx.current_drawdown:.1%}

Please provide your market regime assessment.
"""
```

### 1.4 Technical Indicator Calculator

```python
# src/beavr/agents/indicators.py
"""Technical indicator calculations for agent context."""

from decimal import Decimal
from typing import Any

import pandas as pd


def calculate_indicators(bars: pd.DataFrame) -> dict[str, float]:
    """
    Calculate technical indicators from OHLCV bars.
    
    Args:
        bars: DataFrame with columns [open, high, low, close, volume]
        
    Returns:
        Dictionary of indicator values
    """
    if bars.empty or len(bars) < 20:
        return {}
    
    close = bars['close'].astype(float)
    high = bars['high'].astype(float)
    low = bars['low'].astype(float)
    volume = bars['volume'].astype(float)
    
    indicators = {}
    
    # Simple Moving Averages
    indicators['sma_10'] = close.rolling(10).mean().iloc[-1]
    indicators['sma_20'] = close.rolling(20).mean().iloc[-1]
    if len(close) >= 50:
        indicators['sma_50'] = close.rolling(50).mean().iloc[-1]
    
    # RSI (14-period)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 0.001)
    indicators['rsi_14'] = (100 - (100 / (1 + rs))).iloc[-1]
    
    # MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    indicators['macd'] = macd_line.iloc[-1]
    indicators['macd_signal'] = signal_line.iloc[-1]
    indicators['macd_histogram'] = (macd_line - signal_line).iloc[-1]
    
    # Bollinger Bands
    sma_20 = close.rolling(20).mean()
    std_20 = close.rolling(20).std()
    indicators['bb_upper'] = (sma_20 + 2 * std_20).iloc[-1]
    indicators['bb_lower'] = (sma_20 - 2 * std_20).iloc[-1]
    indicators['bb_pct'] = ((close.iloc[-1] - indicators['bb_lower']) / 
                           (indicators['bb_upper'] - indicators['bb_lower']))
    
    # Average True Range (volatility)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    indicators['atr_14'] = tr.rolling(14).mean().iloc[-1]
    
    # Volume analysis
    indicators['volume_sma_20'] = volume.rolling(20).mean().iloc[-1]
    indicators['volume_ratio'] = volume.iloc[-1] / indicators['volume_sma_20']
    
    # Price vs SMAs
    indicators['price_vs_sma20'] = (close.iloc[-1] / indicators['sma_20'] - 1) * 100
    if 'sma_50' in indicators:
        indicators['price_vs_sma50'] = (close.iloc[-1] / indicators['sma_50'] - 1) * 100
    
    return {k: round(v, 4) for k, v in indicators.items()}


def build_agent_context_indicators(
    bars_by_symbol: dict[str, pd.DataFrame]
) -> dict[str, dict[str, float]]:
    """
    Build indicators dictionary for AgentContext.
    
    Args:
        bars_by_symbol: Symbol -> DataFrame mapping
        
    Returns:
        Symbol -> indicators mapping
    """
    return {
        symbol: calculate_indicators(bars)
        for symbol, bars in bars_by_symbol.items()
        if not bars.empty
    }
```

---

## Phase 2: Multi-Agent Core (Weeks 4-6)

### 2.1 Swing Trader Agent

```python
# src/beavr/agents/swing_trader.py
"""Swing Trader agent for multi-day opportunities."""

from datetime import datetime
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.signal import Signal


class SwingTradeSignal(BaseModel):
    """Structured swing trade recommendation."""
    symbol: str
    action: str = Field(description="buy, sell, or hold")
    conviction: float = Field(ge=0.0, le=1.0)
    entry_price: float = Field(description="Suggested entry price")
    stop_loss: float = Field(description="Stop loss price")
    take_profit: float = Field(description="Take profit price")
    position_size_pct: float = Field(ge=0.0, le=0.2, description="% of portfolio")
    rationale: str


class SwingAnalysis(BaseModel):
    """Structured output from swing analysis."""
    signals: list[SwingTradeSignal]
    market_view: str
    overall_conviction: float = Field(ge=0.0, le=1.0)


class SwingTraderAgent(BaseAgent):
    """
    Swing Trader agent for multi-day position opportunities.
    
    Looks for:
    - Mean reversion from oversold/overbought
    - Support/resistance bounces
    - Trend continuation after pullbacks
    """
    
    name: ClassVar[str] = "Swing Trader"
    role: ClassVar[str] = "trader"
    description: ClassVar[str] = "Multi-day swing trading opportunities"
    version: ClassVar[str] = "0.1.0"
    
    def get_system_prompt(self) -> str:
        return """You are a swing trader agent looking for multi-day opportunities.
Your typical holding period is 3-10 trading days.

TRADING STYLE:
- Mean reversion from oversold (RSI < 30) or overbought (RSI > 70) conditions
- Bounces from support levels (near lower Bollinger Band, key SMAs)
- Trend continuation after healthy pullbacks (price pulling back to 20 SMA in uptrend)

POSITION SIZING:
- Never recommend more than 10% of portfolio per position
- Scale conviction: high conviction = up to 10%, low = 2-3%
- Consider current drawdown when sizing

RISK MANAGEMENT:
- Always set stop loss (typically 3-5% below entry for longs)
- Set take profit targets (typically 2:1 or 3:1 reward:risk)
- Consider overall market regime

OUTPUT RULES:
- Only recommend trades with clear technical setup
- Hold if no compelling opportunity
- Be conservative in volatile/bear regimes
- Maximum 3 signals per analysis
"""
    
    async def analyze(self, ctx: AgentContext) -> AgentProposal:
        """Analyze for swing trading opportunities."""
        start_time = datetime.now()
        
        user_prompt = self.build_user_prompt(ctx)
        
        analysis: SwingAnalysis = await self.copilot.reason(
            system_prompt=self.get_system_prompt(),
            user_prompt=user_prompt,
            output_schema=SwingAnalysis
        )
        
        # Convert to Beavr Signal objects
        signals = []
        for sig in analysis.signals:
            if sig.action in ("buy", "sell"):
                signal = Signal(
                    symbol=sig.symbol,
                    action=sig.action,
                    amount=self._calculate_amount(ctx, sig) if sig.action == "buy" else None,
                    quantity=self._calculate_quantity(ctx, sig) if sig.action == "sell" else None,
                    reason=sig.rationale,
                    timestamp=datetime.combine(ctx.current_date, datetime.min.time()),
                    confidence=sig.conviction
                )
                signals.append(signal)
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=signals,
            conviction=analysis.overall_conviction,
            rationale=analysis.market_view,
            risk_score=0.5,  # Medium risk profile
            model_version=self.version,
            processing_time_ms=processing_time,
        )
    
    def _calculate_amount(self, ctx: AgentContext, sig: SwingTradeSignal) -> Decimal:
        """Calculate buy amount based on position size percentage."""
        target_value = ctx.portfolio_value * Decimal(str(sig.position_size_pct))
        return min(target_value, ctx.cash)
    
    def _calculate_quantity(self, ctx: AgentContext, sig: SwingTradeSignal) -> Decimal:
        """Calculate sell quantity."""
        return ctx.positions.get(sig.symbol, Decimal(0))
```

### 2.2 Orchestrator Engine

```python
# src/beavr/orchestrator/engine.py
"""Orchestrator for multi-agent coordination."""

import asyncio
from datetime import datetime
from typing import Optional

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.agents.market_analyst import MarketAnalystAgent
from beavr.llm.copilot import BeavrCopilot
from beavr.models.signal import Signal
from beavr.orchestrator.blackboard import Blackboard


class OrchestratorEngine:
    """
    Coordinates multi-agent decision making.
    
    The orchestrator manages the daily decision cycle:
    1. Market analysis (sets regime)
    2. Trading agent proposals (parallel)
    3. Risk gating
    4. Signal aggregation
    """
    
    def __init__(
        self,
        copilot: CopilotClient,
        market_analyst: MarketAnalystAgent,
        trading_agents: list[BaseAgent],
        risk_agent: Optional[BaseAgent] = None,
    ):
        self.copilot = copilot
        self.market_analyst = market_analyst
        self.trading_agents = trading_agents
        self.risk_agent = risk_agent
        self.blackboard = Blackboard()
    
    async def run_daily_cycle(self, ctx: AgentContext) -> list[Signal]:
        """
        Execute the daily decision cycle.
        
        Args:
            ctx: Initial agent context
            
        Returns:
            List of approved signals for execution
        """
        cycle_start = datetime.now()
        
        # Phase 1: Market Analysis
        market_proposal = await self.market_analyst.analyze(ctx)
        self.blackboard.set("market_analysis", market_proposal)
        
        # Update context with regime info
        ctx.regime = self._extract_regime(market_proposal)
        ctx.regime_confidence = market_proposal.conviction
        ctx.risk_budget = self._calculate_risk_budget(market_proposal, ctx)
        
        # Phase 2: Trading Agent Proposals (parallel)
        proposals = await asyncio.gather(*[
            agent.analyze(ctx) for agent in self.trading_agents
        ])
        self.blackboard.set("trading_proposals", proposals)
        
        # Phase 3: Aggregate Signals
        all_signals = []
        for proposal in proposals:
            all_signals.extend(proposal.signals)
        
        # Phase 4: Risk Gating (if risk agent configured)
        if self.risk_agent:
            risk_proposal = await self.risk_agent.analyze(ctx)
            approved_signals = self._apply_risk_gate(all_signals, risk_proposal)
        else:
            approved_signals = all_signals
        
        # Phase 5: Deduplication and conflict resolution
        final_signals = self._resolve_conflicts(approved_signals)
        
        # Log cycle summary
        cycle_time = (datetime.now() - cycle_start).total_seconds()
        self.blackboard.set("cycle_summary", {
            "timestamp": datetime.now().isoformat(),
            "regime": ctx.regime,
            "proposals_count": len(proposals),
            "signals_generated": len(all_signals),
            "signals_approved": len(final_signals),
            "cycle_time_seconds": cycle_time
        })
        
        return final_signals
    
    def _extract_regime(self, proposal: AgentProposal) -> str:
        """Extract regime from market analyst proposal."""
        # The rationale contains the regime - parse it
        # In practice, we'd have structured output
        rationale = proposal.rationale.lower()
        for regime in ["bull", "bear", "volatile", "sideways"]:
            if regime in rationale:
                return regime
        return "sideways"  # Default
    
    def _calculate_risk_budget(
        self, 
        market_proposal: AgentProposal, 
        ctx: AgentContext
    ) -> float:
        """
        Calculate risk budget based on market analysis and current state.
        """
        base_budget = 1.0 - market_proposal.risk_score
        
        # Reduce budget based on current drawdown
        if ctx.current_drawdown > 0.15:
            base_budget *= 0.5
        elif ctx.current_drawdown > 0.10:
            base_budget *= 0.7
        
        return max(0.1, min(1.0, base_budget))
    
    def _apply_risk_gate(
        self,
        signals: list[Signal],
        risk_proposal: AgentProposal
    ) -> list[Signal]:
        """Apply risk agent's assessment to filter/modify signals."""
        # Simple implementation: reject low-confidence signals in high-risk
        if risk_proposal.risk_score > 0.7:
            return [s for s in signals if s.confidence > 0.7]
        return signals
    
    def _resolve_conflicts(self, signals: list[Signal]) -> list[Signal]:
        """
        Resolve conflicts between signals.
        
        Rules:
        - If multiple signals for same symbol, take highest confidence
        - Don't buy and sell same symbol
        """
        by_symbol: dict[str, list[Signal]] = {}
        for signal in signals:
            by_symbol.setdefault(signal.symbol, []).append(signal)
        
        resolved = []
        for symbol, symbol_signals in by_symbol.items():
            # Check for conflicting actions
            actions = {s.action for s in symbol_signals}
            if "buy" in actions and "sell" in actions:
                # Conflict - take highest confidence
                best = max(symbol_signals, key=lambda s: s.confidence)
                resolved.append(best)
            else:
                # No conflict - take highest confidence
                best = max(symbol_signals, key=lambda s: s.confidence)
                resolved.append(best)
        
        return resolved
```

### 2.3 Blackboard (Shared State)

```python
# src/beavr/orchestrator/blackboard.py
"""Blackboard pattern for shared agent state."""

from datetime import datetime
from threading import Lock
from typing import Any, Optional


class Blackboard:
    """
    Shared state container for multi-agent coordination.
    
    The blackboard pattern allows agents to read/write shared state
    without direct coupling. All writes are timestamped and logged.
    """
    
    def __init__(self):
        self._state: dict[str, Any] = {}
        self._history: list[dict] = []
        self._lock = Lock()
    
    def set(self, key: str, value: Any) -> None:
        """Set a value on the blackboard."""
        with self._lock:
            self._state[key] = value
            self._history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "set",
                "key": key,
                "value_type": type(value).__name__
            })
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the blackboard."""
        with self._lock:
            return self._state.get(key, default)
    
    def get_all(self) -> dict[str, Any]:
        """Get all current state."""
        with self._lock:
            return dict(self._state)
    
    def get_history(self) -> list[dict]:
        """Get history of all writes."""
        with self._lock:
            return list(self._history)
    
    def clear(self) -> None:
        """Clear all state (start of new day)."""
        with self._lock:
            self._state.clear()
            self._history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "clear"
            })
```

---

## Phase 3: Strategy Integration (Weeks 7-8)

### 3.1 Multi-Agent Strategy

```python
# src/beavr/strategies/ai/multi_agent.py
"""Multi-agent AI strategy for Beavr."""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Type

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext
from beavr.agents.indicators import build_agent_context_indicators
from beavr.agents.market_analyst import MarketAnalystAgent
from beavr.agents.swing_trader import SwingTraderAgent
from beavr.llm.copilot import BeavrCopilot, CopilotConfig
from beavr.models.signal import Signal
from beavr.orchestrator.engine import OrchestratorEngine
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.registry import register_strategy


class MultiAgentParams(BaseModel):
    """Parameters for multi-agent strategy."""
    symbols: list[str] = Field(..., description="Symbols to trade")
    
    # Risk parameters
    max_drawdown: float = Field(default=0.20, ge=0.05, le=0.50)
    max_position_pct: float = Field(default=0.10, ge=0.01, le=0.25)
    min_cash_pct: float = Field(default=0.05, ge=0.0, le=0.50)
    
    # Agent configuration
    agents_enabled: list[str] = Field(
        default=["market_analyst", "swing_trader"],
        description="Which agents to enable"
    )
    
    # LLM configuration (GitHub Copilot SDK)
    llm_model: str = Field(default="gpt-4.1", description="Copilot SDK model")
    llm_streaming: bool = Field(default=False, description="Enable streaming responses")


@register_strategy("ai_multi_agent")
class MultiAgentStrategy(BaseStrategy):
    """
    AI-powered multi-agent trading strategy.
    
    Integrates the agent orchestrator into Beavr's existing
    strategy framework for seamless backtesting and live trading.
    
    Uses GitHub Copilot SDK for all LLM reasoning.
    """
    
    name: ClassVar[str] = "AI Multi-Agent"
    description: ClassVar[str] = "LLM-powered multi-agent trading system"
    version: ClassVar[str] = "0.1.0"
    param_model: ClassVar[Type[BaseModel]] = MultiAgentParams
    
    def __init__(self, params: MultiAgentParams):
        self.params = params
        self._orchestrator: OrchestratorEngine | None = None
        self._copilot: CopilotClient | None = None
        self._peak_value: Decimal = Decimal(0)
    
    @property
    def symbols(self) -> list[str]:
        return list(self.params.symbols)
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of Copilot client and orchestrator."""
        if self._copilot is None:
            from beavr.llm.copilot import CopilotClient, CopilotConfig
            
            # Create Copilot client with SDK config
            self._copilot = CopilotClient(CopilotConfig(
                model=self.params.llm_model,
                streaming=self.params.llm_streaming,
            ))
            
            # Initialize agents with Copilot client
            market_analyst = MarketAnalystAgent(self._copilot)
            swing_trader = SwingTraderAgent(self._copilot)
            
            trading_agents = []
            if "swing_trader" in self.params.agents_enabled:
                trading_agents.append(swing_trader)
            
            self._orchestrator = OrchestratorEngine(
                copilot=self._copilot,
                market_analyst=market_analyst,
                trading_agents=trading_agents
            )
    
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """
        Evaluate the multi-agent strategy.
        
        Bridges Beavr's StrategyContext to the agent system.
        """
        self._ensure_initialized()
        
        # Track peak for drawdown calculation
        portfolio_value = ctx.get_portfolio_value()
        if portfolio_value > self._peak_value:
            self._peak_value = portfolio_value
        
        current_drawdown = float(
            (self._peak_value - portfolio_value) / self._peak_value
        ) if self._peak_value > 0 else 0.0
        
        # Check drawdown kill switch
        if current_drawdown >= self.params.max_drawdown:
            # Return flatten signals
            return self._generate_flatten_signals(ctx)
        
        # Build AgentContext from StrategyContext
        agent_ctx = self._build_agent_context(ctx, current_drawdown)
        
        # Run orchestrator (async in sync context)
        signals = asyncio.run(
            self._orchestrator.run_daily_cycle(agent_ctx)
        )
        
        # Apply position limits
        signals = self._apply_position_limits(signals, ctx)
        
        return signals
    
    def _build_agent_context(
        self, 
        ctx: StrategyContext,
        current_drawdown: float
    ) -> AgentContext:
        """Convert StrategyContext to AgentContext."""
        # Convert bars to list of dicts for agent context
        bars_dict = {}
        for symbol, df in ctx.bars.items():
            if not df.empty:
                bars_dict[symbol] = df.tail(50).to_dict('records')
        
        # Calculate indicators
        indicators = build_agent_context_indicators(ctx.bars)
        
        return AgentContext(
            current_date=ctx.current_date,
            timestamp=datetime.now(),
            prices={s: ctx.prices.get(s, Decimal(0)) for s in self.symbols},
            bars=bars_dict,
            indicators=indicators,
            cash=ctx.cash,
            positions=ctx.positions,
            portfolio_value=ctx.get_portfolio_value(),
            current_drawdown=current_drawdown,
            risk_budget=1.0 - current_drawdown,  # Simple risk budget
        )
    
    def _apply_position_limits(
        self, 
        signals: list[Signal], 
        ctx: StrategyContext
    ) -> list[Signal]:
        """Apply position size limits to signals."""
        portfolio_value = ctx.get_portfolio_value()
        max_position_value = portfolio_value * Decimal(str(self.params.max_position_pct))
        
        limited_signals = []
        for signal in signals:
            if signal.action == "buy" and signal.amount:
                # Check if this would exceed position limit
                current_value = ctx.get_position_value(signal.symbol)
                max_buy = max_position_value - current_value
                if max_buy > 0:
                    signal.amount = min(signal.amount, max_buy)
                    limited_signals.append(signal)
            else:
                limited_signals.append(signal)
        
        return limited_signals
    
    def _generate_flatten_signals(self, ctx: StrategyContext) -> list[Signal]:
        """Generate signals to flatten all positions (kill switch)."""
        signals = []
        for symbol, shares in ctx.positions.items():
            if shares > 0:
                signals.append(Signal(
                    symbol=symbol,
                    action="sell",
                    quantity=shares,
                    reason="KILL_SWITCH: Max drawdown exceeded",
                    timestamp=datetime.combine(ctx.current_date, datetime.min.time()),
                    confidence=1.0
                ))
        return signals
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_agents.py
"""Unit tests for agent system."""

import pytest
from decimal import Decimal
from datetime import date

from beavr.agents.base import AgentContext
from beavr.agents.indicators import calculate_indicators


class TestIndicators:
    def test_calculate_indicators_with_sufficient_data(self, sample_bars):
        """Test indicator calculation with enough data."""
        indicators = calculate_indicators(sample_bars)
        
        assert 'sma_20' in indicators
        assert 'rsi_14' in indicators
        assert 'macd' in indicators
        assert 0 <= indicators['rsi_14'] <= 100

    def test_calculate_indicators_insufficient_data(self, short_bars):
        """Test indicator calculation with insufficient data."""
        indicators = calculate_indicators(short_bars)
        assert indicators == {}


class TestAgentContext:
    def test_context_creation(self):
        """Test AgentContext can be created."""
        ctx = AgentContext(
            current_date=date(2025, 1, 15),
            timestamp=datetime.now(),
            prices={"SPY": Decimal("500.00")},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            risk_budget=1.0
        )
        
        assert ctx.current_date == date(2025, 1, 15)
        assert ctx.cash == Decimal("10000")
```

---

## Configuration Templates

### Environment Variables

```bash
# .env.example

# Alpaca (for market data and trading)
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret

# Note: GitHub Copilot SDK uses your existing Copilot subscription
# No additional API keys needed
```

### Strategy Configuration

```toml
# examples/strategies/ai_multi_agent.toml
[strategy]
name = "ai_multi_agent"

[params]
symbols = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL"]

[params.risk]
max_drawdown = 0.20
max_position_pct = 0.10
min_cash_pct = 0.05

[params.agents]
agents_enabled = ["market_analyst", "swing_trader"]

# LLM settings (GitHub Copilot SDK)
[params.llm]
model = "gpt-4.1"
streaming = false
```

---

## Next Steps

1. **Immediate**: Install GitHub Copilot CLI and verify authentication
2. **This Week**: Implement Copilot SDK wrapper with mock for testing
3. **Week 2**: Build Market Analyst agent with unit tests
4. **Week 3**: Integrate with existing BacktestEngine for validation

---

*Implementation Roadmap v0.1.0*
*Last Updated: February 2026*
