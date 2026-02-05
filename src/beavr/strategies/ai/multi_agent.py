"""Multi-agent AI strategy for Beavr.

This strategy integrates the AI agent orchestrator into Beavr's
existing strategy framework for backtesting and live trading.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Optional, Type

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext
from beavr.agents.indicators import (
    bars_to_dict_list,
    build_agent_context_indicators,
)
from beavr.agents.market_analyst import MarketAnalystAgent
from beavr.agents.swing_trader import SwingTraderAgent
from beavr.llm.client import LLMClient, LLMConfig
from beavr.models.signal import Signal
from beavr.orchestrator.engine import OrchestratorEngine
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.registry import register_strategy

logger = logging.getLogger(__name__)


class MultiAgentParams(BaseModel):
    """Parameters for multi-agent AI strategy."""

    symbols: list[str] = Field(
        ..., description="Symbols to trade"
    )

    # Risk parameters
    max_drawdown: float = Field(
        default=0.20,
        ge=0.05,
        le=0.50,
        description="Maximum allowed drawdown before reducing exposure",
    )
    max_position_pct: float = Field(
        default=0.10,
        ge=0.01,
        le=0.25,
        description="Maximum position size as % of portfolio",
    )
    min_cash_pct: float = Field(
        default=0.05,
        ge=0.0,
        le=0.50,
        description="Minimum cash to maintain as buffer",
    )

    # LLM configuration (uses GitHub Copilot SDK - no API key needed!)
    llm_model: str = Field(
        default="gpt-4.1",
        description="Model to use (gpt-5, gpt-4.1, claude-sonnet-4.5)",
    )
    llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="LLM sampling temperature",
    )


@register_strategy("ai_multi_agent")
class MultiAgentStrategy(BaseStrategy):
    """
    AI-powered multi-agent trading strategy.

    Integrates the agent orchestrator into Beavr's existing
    strategy framework for seamless backtesting and live trading.

    Agents:
    - Market Analyst: Determines market regime (bull/bear/sideways/volatile)
    - Swing Trader: Identifies multi-day trading opportunities

    The strategy respects drawdown limits and position sizing constraints.
    """

    name: ClassVar[str] = "AI Multi-Agent"
    description: ClassVar[str] = "LLM-powered multi-agent trading system"
    version: ClassVar[str] = "0.1.0"
    param_model: ClassVar[Type[BaseModel]] = MultiAgentParams

    def __init__(self, params: MultiAgentParams) -> None:
        """Initialize strategy with params."""
        self.params = params
        self._llm: LLMClient | None = None
        self._orchestrator: OrchestratorEngine | None = None
        self._peak_value: Decimal = Decimal(0)
        self._initialized = False

    @property
    def symbols(self) -> list[str]:
        """Return symbols to trade."""
        return list(self.params.symbols)

    def _ensure_initialized(self) -> None:
        """Lazy initialization of LLM client and orchestrator."""
        if self._initialized:
            return

        # Create LLM client (uses GitHub Copilot SDK - no API key needed!)
        config = LLMConfig(
            model=self.params.llm_model,
            temperature=self.params.llm_temperature,
        )
        self._llm = LLMClient(config=config)

        # Create agents
        market_analyst = MarketAnalystAgent(self._llm)
        swing_trader = SwingTraderAgent(self._llm)

        # Create orchestrator
        self._orchestrator = OrchestratorEngine(
            market_analyst=market_analyst,
            trading_agents=[swing_trader],
            max_position_pct=self.params.max_position_pct,
            min_cash_pct=self.params.min_cash_pct,
        )

        self._initialized = True
        logger.info("AI Multi-Agent strategy initialized")

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """
        Evaluate strategy and return trading signals.

        This method is called once per trading day during backtest
        or at scheduled intervals during live trading.

        Args:
            ctx: Strategy context with market data and portfolio state

        Returns:
            List of trading signals
        """
        self._ensure_initialized()

        logger.info(f"AI strategy evaluating for {ctx.current_date}")

        # Track portfolio peak for drawdown calculation
        portfolio_value = ctx.get_portfolio_value()
        if portfolio_value > self._peak_value:
            self._peak_value = portfolio_value

        # Calculate current drawdown
        current_drawdown = float(
            (self._peak_value - portfolio_value) / self._peak_value
        ) if self._peak_value > 0 else 0.0

        # Check kill switch (hard stop at max drawdown)
        if current_drawdown >= self.params.max_drawdown:
            logger.warning(
                f"KILL SWITCH: Drawdown {current_drawdown:.1%} >= {self.params.max_drawdown:.1%}. "
                "Generating flatten signals."
            )
            return self._generate_flatten_signals(ctx)

        # Build agent context from strategy context
        agent_ctx = self._build_agent_context(ctx, current_drawdown)

        # Run the orchestrator
        try:
            signals = self._orchestrator.run_daily_cycle(agent_ctx)

            # Apply final position limits
            signals = self._apply_position_limits(signals, ctx)

            return signals

        except Exception as e:
            logger.error(f"Orchestrator failed: {e}")
            # Return empty on failure - don't trade if unsure
            return []

    def _build_agent_context(
        self, ctx: StrategyContext, current_drawdown: float
    ) -> AgentContext:
        """
        Convert StrategyContext to AgentContext.

        Args:
            ctx: Beavr strategy context
            current_drawdown: Current drawdown from peak

        Returns:
            AgentContext for agents
        """
        # Build indicators from bars
        indicators = build_agent_context_indicators(ctx.bars)

        # Convert bars to dict lists for agent consumption
        bars_dict = {
            symbol: bars_to_dict_list(bars, n=20)
            for symbol, bars in ctx.bars.items()
        }

        return AgentContext(
            current_date=ctx.current_date,
            timestamp=datetime.now(),
            prices=dict(ctx.prices),
            bars=bars_dict,
            indicators=indicators,
            cash=ctx.cash,
            positions=dict(ctx.positions),
            portfolio_value=ctx.get_portfolio_value(),
            current_drawdown=current_drawdown,
            peak_value=self._peak_value,
            risk_budget=1.0,  # Will be set by orchestrator
            regime=None,  # Will be set by market analyst
            regime_confidence=0.0,
        )

    def _apply_position_limits(
        self, signals: list[Signal], ctx: StrategyContext
    ) -> list[Signal]:
        """
        Apply final position size limits to signals.

        Args:
            signals: Signals from orchestrator
            ctx: Strategy context

        Returns:
            Adjusted signals
        """
        portfolio_value = ctx.get_portfolio_value()
        max_position = portfolio_value * Decimal(str(self.params.max_position_pct))

        limited_signals = []
        for signal in signals:
            if signal.action == "buy" and signal.amount:
                # Check current position value
                current_value = ctx.get_position_value(signal.symbol)
                space = max_position - current_value

                if space <= Decimal("0"):
                    logger.debug(
                        f"Skipping {signal.symbol}: already at max position"
                    )
                    continue

                if signal.amount > space:
                    signal = Signal(
                        symbol=signal.symbol,
                        action=signal.action,
                        amount=space,
                        reason=signal.reason + " (capped to max position)",
                        timestamp=signal.timestamp,
                        confidence=signal.confidence,
                    )

            limited_signals.append(signal)

        return limited_signals

    def _generate_flatten_signals(self, ctx: StrategyContext) -> list[Signal]:
        """
        Generate signals to flatten all positions (kill switch).

        Args:
            ctx: Strategy context

        Returns:
            List of sell signals for all positions
        """
        signals = []
        for symbol, shares in ctx.positions.items():
            if shares > Decimal("0"):
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        quantity=shares,
                        reason=f"KILL SWITCH: Drawdown limit reached ({self.params.max_drawdown:.0%})",
                        timestamp=datetime.now(),
                        confidence=1.0,
                    )
                )
        return signals

    def on_period_start(self, ctx: StrategyContext) -> None:
        """Called at start of each period."""
        logger.info(f"AI strategy: New period starting {ctx.current_date}")

    def get_orchestrator_summary(self) -> Optional[dict]:
        """Get summary of last orchestrator cycle."""
        if self._orchestrator:
            return self._orchestrator.get_cycle_summary()
        return None
