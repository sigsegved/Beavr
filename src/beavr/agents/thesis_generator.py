"""Thesis Generator Agent for investment hypothesis formation.

The Thesis Generator converts market events and analysis into structured
trade theses. It operates in the continuous research pipeline (24/7).

A thesis is a falsifiable hypothesis with defined success and failure conditions.
Every thesis must have:
- A clear catalyst with known timing
- Specific entry/exit/stop levels
- Time horizon classification
- Invalidation conditions
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.market_event import EventImportance, EventType, MarketEvent
from beavr.models.thesis import (
    ThesisStatus,
    TradeDirection,
    TradeThesis,
    TradeType,
)

if TYPE_CHECKING:
    from beavr.db.thesis_repo import ThesisRepository
    from beavr.llm.client import LLMClient

logger = logging.getLogger(__name__)


class ThesisOutput(BaseModel):
    """Structured output from LLM thesis generation."""
    
    action: str = Field(
        description="CREATE_THESIS or NO_THESIS"
    )
    
    # Thesis fields (if CREATE_THESIS)
    symbol: Optional[str] = Field(default=None)
    trade_type: Optional[str] = Field(
        default=None,
        description="day_trade, swing_short, swing_medium, or swing_long"
    )
    direction: Optional[str] = Field(
        default=None,
        description="long or short"
    )
    entry_rationale: Optional[str] = Field(default=None)
    catalyst: Optional[str] = Field(default=None)
    catalyst_date: Optional[str] = Field(
        default=None,
        description="YYYY-MM-DD format or null"
    )
    entry_price_target: Optional[float] = Field(default=None)
    profit_target: Optional[float] = Field(default=None)
    stop_loss: Optional[float] = Field(default=None)
    expected_exit_days: Optional[int] = Field(
        default=None,
        description="Expected days to hold"
    )
    invalidation_conditions: Optional[list[str]] = Field(default=None)
    confidence: Optional[float] = Field(default=None)
    
    # Rejection fields (if NO_THESIS)
    rejection_reason: Optional[str] = Field(default=None)


class ThesisGeneratorAgent(BaseAgent):
    """
    Thesis Generator Agent for investment hypothesis formation.
    
    Operates in the continuous research pipeline (24/7).
    Converts market events and market analysis into structured trade theses.
    
    A good thesis requires:
    1. Clear catalyst with known date or timeframe
    2. Asymmetric risk/reward (target > 2x stop distance)
    3. Technical support for the direction
    4. Reasonable confidence the catalyst will drive the expected move
    """
    
    name: ClassVar[str] = "Thesis Generator"
    role: ClassVar[str] = "analyst"
    description: ClassVar[str] = "Investment hypothesis formation from events and analysis"
    version: ClassVar[str] = "2.0.0"
    
    # System prompt for thesis generation
    SYSTEM_PROMPT: ClassVar[str] = """You are a senior portfolio manager formulating investment hypotheses.
Your job is to convert market events and observations into structured trade theses.

ROLE:
- Formulate specific, testable investment hypotheses
- Define clear entry/exit criteria
- Classify opportunities by trade type
- Maintain high selectivity—most events should NOT become theses

CORE PHILOSOPHY:
"A thesis is a falsifiable hypothesis with defined success and failure conditions."

Every thesis MUST have:
1. CATALYST: A specific event/condition expected to drive the move
2. DIRECTION: Clear long or short bias
3. PRICE TARGETS: Specific entry, target, and stop levels
4. TIME HORIZON: When the thesis should play out
5. INVALIDATION: Conditions that would prove the thesis wrong

THESIS QUALITY CRITERIA:
A good thesis requires:
1. Clear catalyst with known date or timeframe
2. Asymmetric risk/reward (target distance > 2x stop distance)
3. Technical support for the direction
4. Reasonable confidence the catalyst will drive expected move

TRADE TYPE CLASSIFICATION:
- DAY_TRADE: Catalyst is TODAY, expect 1-3% move, exit by 10:30 AM
- SWING_SHORT: Catalyst in 1-2 weeks, expect 5-10% move
- SWING_MEDIUM: Catalyst in 1-3 months, expect 10-20% move
- SWING_LONG: Catalyst in 3-12 months, expect 20-50% move

SELECTIVITY:
- Most events (>70%) should result in "NO THESIS"
- Only create thesis when conviction is genuine
- Better to miss opportunities than force weak theses

If you cannot articulate a specific price target and exit date,
there is no thesis—pass on the opportunity."""

    def __init__(
        self,
        llm: LLMClient,
        min_confidence: float = 0.6,
        max_active_theses: int = 20,
        thesis_repo: Optional[ThesisRepository] = None,
    ) -> None:
        """
        Initialize the Thesis Generator.
        
        Args:
            llm: LLM client for reasoning
            min_confidence: Minimum confidence to create thesis
            max_active_theses: Maximum active theses at once
            thesis_repo: Repository for storing theses
        """
        super().__init__(llm)
        self.min_confidence = min_confidence
        self.max_active_theses = max_active_theses
        self.thesis_repo = thesis_repo
    
    def get_system_prompt(self) -> str:
        """Return the agent's system prompt."""
        return self.SYSTEM_PROMPT
    
    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """
        Analyze market context and generate potential theses.
        
        Called by the orchestrator during analysis phase.
        """
        start_time = datetime.now()
        
        # Check for events that could drive thesis generation
        events = ctx.events
        theses_created = []
        
        for event_data in events:
            event = MarketEvent(**event_data) if isinstance(event_data, dict) else event_data
            
            # Only process high/medium importance events
            if event.importance == EventImportance.LOW:
                continue
            
            thesis = self.generate_thesis_from_event(event, ctx)
            if thesis:
                theses_created.append(thesis)
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=[],  # Thesis Generator doesn't produce signals directly
            conviction=len(theses_created) / max(len(events), 1) if events else 0,
            rationale=f"Generated {len(theses_created)} theses from {len(events)} events",
            risk_score=0.0,
            risk_factors=[],
            model_version=self.version,
            processing_time_ms=processing_time,
            extra={
                "theses_created": len(theses_created),
                "theses": [t.model_dump() for t in theses_created],
            },
        )
    
    def generate_thesis_from_event(
        self,
        event: MarketEvent,
        ctx: AgentContext,
    ) -> Optional[TradeThesis]:
        """
        Generate a trade thesis from a market event.
        
        Args:
            event: The market event to analyze
            ctx: Current market context
            
        Returns:
            TradeThesis if hypothesis can be formed, None otherwise
        """
        if not event.symbol:
            logger.debug(f"Skipping event without symbol: {event.headline}")
            return None
        
        symbol = event.symbol
        current_price = ctx.prices.get(symbol)
        
        if current_price is None:
            logger.debug(f"No price data for {symbol}")
            return None
        
        # Get technical indicators if available
        indicators = ctx.indicators.get(symbol, {})
        
        # Build the prompt
        user_prompt = self._build_thesis_prompt(event, current_price, indicators, ctx)
        
        try:
            output: ThesisOutput = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=user_prompt,
                output_schema=ThesisOutput,
            )
            
            if output.action.upper() == "NO_THESIS":
                logger.debug(f"No thesis for {symbol}: {output.rejection_reason}")
                return None
            
            # Check minimum confidence
            if output.confidence and output.confidence < self.min_confidence:
                logger.debug(f"Thesis confidence too low for {symbol}: {output.confidence}")
                return None
            
            # Create the thesis
            thesis = self._create_thesis(output, event, current_price)
            
            # Save to repository if available
            if self.thesis_repo and thesis:
                self.thesis_repo.save(thesis)
                logger.info(f"Created thesis: {thesis}")
            
            return thesis
            
        except Exception as e:
            logger.warning(f"Failed to generate thesis for {symbol}: {e}")
            return None
    
    def _build_thesis_prompt(
        self,
        event: MarketEvent,
        current_price: Decimal,
        indicators: dict[str, float],
        ctx: AgentContext,
    ) -> str:
        """Build the LLM prompt for thesis generation."""
        
        indicator_text = ""
        if indicators:
            indicator_text = f"""
TECHNICAL INDICATORS:
- RSI(14): {indicators.get('rsi_14', 'N/A')}
- 20-day SMA: ${indicators.get('sma_20', 'N/A')}
- 50-day SMA: ${indicators.get('sma_50', 'N/A')}
- 200-day SMA: ${indicators.get('sma_200', 'N/A')}
- ATR(14): ${indicators.get('atr_14', 'N/A')}
"""
        
        return f"""MARKET EVENT:
Type: {event.event_type.value}
Symbol: {event.symbol}
Headline: {event.headline}
Summary: {event.summary}
Importance: {event.importance.value}
Event Date: {event.event_date or 'Not specified'}

CURRENT MARKET DATA:
Current Price: ${current_price}
Market Regime: {ctx.regime or 'Unknown'}
{indicator_text}

PORTFOLIO CONTEXT:
Current Position: {ctx.positions.get(event.symbol, 0)} shares
Risk Budget: {ctx.risk_budget:.0%}

Based on this event and data, determine if a tradeable thesis exists.

If you cannot articulate a specific price target and exit date,
respond with NO_THESIS.
{self._format_directives(ctx)}
Respond with your analysis in JSON format.
"""
    
    @staticmethod
    def _format_directives(ctx: AgentContext) -> str:
        """Format portfolio directives for prompt injection."""
        from beavr.orchestrator.portfolio_config import format_directives_for_prompt

        return format_directives_for_prompt(ctx.directives)

    def _create_thesis(
        self,
        output: ThesisOutput,
        event: MarketEvent,
        _current_price: Decimal,
    ) -> Optional[TradeThesis]:
        """Create a TradeThesis from LLM output."""
        
        if not all([
            output.symbol,
            output.trade_type,
            output.entry_price_target,
            output.profit_target,
            output.stop_loss,
        ]):
            return None
        
        # Parse trade type
        try:
            trade_type = TradeType(output.trade_type.lower())
        except ValueError:
            trade_type = TradeType.SWING_SHORT
        
        # Parse direction
        try:
            direction = TradeDirection(output.direction.lower() if output.direction else "long")
        except ValueError:
            direction = TradeDirection.LONG
        
        # Calculate expected exit date
        expected_days = output.expected_exit_days or trade_type.max_hold_days // 2
        expected_exit_date = date.today() + timedelta(days=expected_days)
        max_hold_date = date.today() + timedelta(days=trade_type.max_hold_days)
        
        # Parse catalyst date
        catalyst_date = None
        if output.catalyst_date:
            try:
                catalyst_date = datetime.strptime(output.catalyst_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        
        return TradeThesis(
            symbol=output.symbol,
            trade_type=trade_type,
            direction=direction,
            entry_rationale=output.entry_rationale or f"Based on {event.event_type.value}",
            catalyst=output.catalyst or event.headline,
            catalyst_date=catalyst_date or event.event_date,
            entry_price_target=Decimal(str(output.entry_price_target)),
            profit_target=Decimal(str(output.profit_target)),
            stop_loss=Decimal(str(output.stop_loss)),
            expected_exit_date=expected_exit_date,
            max_hold_date=max_hold_date,
            invalidation_conditions=output.invalidation_conditions or [],
            status=ThesisStatus.DRAFT,
            confidence=output.confidence or 0.5,
            source="news_monitor",
        )
    
    def generate_thesis(
        self,
        symbol: str,
        ctx: AgentContext,
        catalyst: Optional[str] = None,
        catalyst_date: Optional[date] = None,
    ) -> Optional[TradeThesis]:
        """
        Generate a thesis for a specific symbol (manual/scheduled).
        
        Args:
            symbol: Trading symbol
            ctx: Current market context
            catalyst: Optional catalyst description
            catalyst_date: Optional catalyst date
            
        Returns:
            TradeThesis if hypothesis can be formed, None otherwise
        """
        current_price = ctx.prices.get(symbol)
        if current_price is None:
            logger.warning(f"No price data for {symbol}")
            return None
        
        # Create a synthetic event for the prompt
        synthetic_event = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            symbol=symbol,
            headline=f"Manual thesis request for {symbol}",
            summary=catalyst or f"Analyzing {symbol} for potential trade opportunity",
            source="manual",
            timestamp=datetime.now(),
            importance=EventImportance.MEDIUM,
            event_date=catalyst_date,
        )
        
        return self.generate_thesis_from_event(synthetic_event, ctx)
    
    def review_existing_theses(
        self,
        ctx: AgentContext,
    ) -> list[TradeThesis]:
        """
        Review and update existing theses.
        
        Called during scheduled reviews (e.g., nightly).
        Checks if thesis conditions have changed.
        """
        if not self.thesis_repo:
            return []
        
        active_theses = self.thesis_repo.get_active_theses()
        updated = []
        
        for thesis in active_theses:
            current_price = ctx.prices.get(thesis.symbol)
            if current_price is None:
                continue
            
            # Check if thesis should be invalidated
            # (Price moved significantly against thesis before entry, etc.)
            if thesis.direction == TradeDirection.LONG:
                if current_price < thesis.stop_loss:
                    thesis.status = ThesisStatus.INVALIDATED
                    self.thesis_repo.save(thesis)
                    logger.info(f"Invalidated thesis {thesis.id}: price below stop before entry")
                    updated.append(thesis)
            else:
                if current_price > thesis.stop_loss:
                    thesis.status = ThesisStatus.INVALIDATED
                    self.thesis_repo.save(thesis)
                    logger.info(f"Invalidated thesis {thesis.id}: price above stop before entry")
                    updated.append(thesis)
        
        return updated
