"""Earnings Play Agent — generates trade theses from earnings events.

Evaluates upcoming earnings announcements and generates theses for
pre-earnings drift or post-earnings momentum plays.  Theses always
go through the standard DD pipeline before any trade is executed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.market_event import EventType, MarketEvent
from beavr.models.thesis import ThesisStatus, TradeDirection, TradeThesis, TradeType

logger = logging.getLogger(__name__)


# ===================================================================
# Earnings play classification
# ===================================================================


class EarningsPlayType(str, Enum):
    """Strategy classification for earnings plays."""

    PRE_EARNINGS_DRIFT = "pre_earnings_drift"   # Buy T-5 to T-3, sell T-1
    POST_EARNINGS_MOMENTUM = "post_earnings_momentum"  # Trade the gap T+0 to T+3
    SKIP = "skip"  # No edge or too risky


# ===================================================================
# LLM structured output schemas
# ===================================================================


class EarningsAnalysisOutput(BaseModel):
    """Structured LLM output for a single earnings opportunity."""

    symbol: str = Field(description="Trading symbol")
    play_type: str = Field(description="pre_earnings_drift | post_earnings_momentum | skip")
    direction: str = Field(default="long", description="long or short")
    conviction: float = Field(ge=0.0, le=1.0, description="Overall conviction 0–1")
    entry_rationale: str = Field(description="Why enter this trade (2–3 sentences)")
    catalyst: str = Field(description="The earnings announcement catalyst")
    target_pct: float = Field(description="Profit target as percentage")
    stop_pct: float = Field(description="Stop loss as percentage")
    risk_factors: list[str] = Field(default_factory=list, description="Key risks")


class EarningsAnalysisBatch(BaseModel):
    """Batch output from the LLM for multiple earnings opportunities."""

    analyses: list[EarningsAnalysisOutput] = Field(default_factory=list)
    market_outlook: str = Field(default="", description="Current market context for earnings")
    overall_conviction: float = Field(default=0.5, ge=0.0, le=1.0)


# ===================================================================
# Earnings Play Agent
# ===================================================================


class EarningsPlayAgent(BaseAgent):
    """Generates earnings-play theses from upcoming earnings events.

    Earnings plays are high-conviction, short-duration trades around
    earnings announcements.  Strategies include:

    - Pre-earnings drift (buy 3–5 days before, sell before announcement)
    - Post-earnings momentum (trade the gap after results)
    """

    name: ClassVar[str] = "EarningsPlay"
    role: ClassVar[str] = "trader"
    description: ClassVar[str] = "Earnings play specialist — pre-drift and post-momentum strategies"
    version: ClassVar[str] = "0.1.0"

    # Configurable thresholds
    min_conviction: float = 0.55
    max_plays_per_batch: int = 3
    entry_days_before: int = 5
    min_historical_beat_rate: float = 0.6

    def __init__(
        self,
        llm: object,
        thesis_repo: Optional[object] = None,
        min_conviction: float = 0.55,
        max_plays_per_batch: int = 3,
    ) -> None:
        super().__init__(llm=llm)
        self.thesis_repo = thesis_repo
        self.min_conviction = min_conviction
        self.max_plays_per_batch = max_plays_per_batch

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        """Define the earnings specialist persona."""
        return """You are an elite earnings play specialist with deep expertise in:

YOUR EXPERTISE:
- Analyzing historical earnings surprise patterns (beat/miss streaks)
- Pre-earnings price drift detection (institutional accumulation)
- Post-earnings gap analysis (momentum vs. mean-reversion)
- Understanding analyst consensus vs. whisper numbers
- Sector-relative earnings momentum

YOUR APPROACH:
- Only recommend plays where there's a clear statistical edge
- Pre-earnings drift: stocks that consistently beat and drift up before the report
- Post-earnings momentum: trade the gap when results clearly exceed/miss expectations
- Always consider the broader market regime and sector context
- Capital preservation is paramount — skip uncertain plays

OUTPUT FORMAT:
Return JSON matching the EarningsAnalysisBatch schema with up to 3 play recommendations.
For each play, provide a conviction score, clear rationale, and specific risk factors.
If no plays have sufficient edge, return an empty analyses list."""

    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """Analyze earnings events in context and produce theses.

        Filters ``ctx.events`` for ``EARNINGS_UPCOMING`` events and
        evaluates each for tradability.  Returns an ``AgentProposal``
        with created theses in ``extra["theses"]``.
        """
        start = datetime.now()

        # Extract earnings events from context
        earnings_events = self._extract_earnings_events(ctx)
        if not earnings_events:
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],
                conviction=0.0,
                rationale="No upcoming earnings events to analyze",
                risk_score=0.0,
            )

        # Build prompt and call LLM
        prompt = self._build_earnings_prompt(earnings_events, ctx)
        try:
            result: EarningsAnalysisBatch = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=prompt,
                output_schema=EarningsAnalysisBatch,
            )
        except Exception as exc:
            logger.error(f"LLM earnings analysis failed: {exc}")
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],
                conviction=0.0,
                rationale=f"LLM analysis failed: {exc}",
                risk_score=0.0,
            )

        # Convert approved analyses to theses
        theses: list[TradeThesis] = []
        signals: list[dict] = []

        for analysis in result.analyses[: self.max_plays_per_batch]:
            if analysis.play_type == "skip":
                continue
            if analysis.conviction < self.min_conviction:
                logger.info(
                    f"Skipping {analysis.symbol} earnings play — "
                    f"conviction {analysis.conviction:.0%} < {self.min_conviction:.0%}"
                )
                continue

            thesis = self._create_thesis_from_analysis(analysis, ctx)
            if thesis:
                theses.append(thesis)
                if self.thesis_repo:
                    try:
                        self.thesis_repo.save_thesis(thesis)
                    except Exception as exc:
                        logger.warning(f"Failed to save earnings thesis: {exc}")

                signals.append({
                    "symbol": analysis.symbol,
                    "action": "buy" if analysis.direction == "long" else "sell",
                    "conviction": analysis.conviction,
                    "rationale": analysis.entry_rationale,
                    "play_type": analysis.play_type,
                })

        elapsed_ms = (datetime.now() - start).total_seconds() * 1000
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=signals,
            conviction=result.overall_conviction,
            rationale=result.market_outlook or "Earnings calendar analysis complete",
            risk_score=0.4,
            risk_factors=[f for a in result.analyses for f in a.risk_factors],
            processing_time_ms=elapsed_ms,
            extra={
                "theses": [t.model_dump() for t in theses],
                "theses_created": len(theses),
                "events_analyzed": len(earnings_events),
            },
        )

    # ------------------------------------------------------------------
    # Earnings-specific analysis
    # ------------------------------------------------------------------

    def analyze_earnings_opportunity(
        self,
        event: MarketEvent,
        ctx: AgentContext,
    ) -> Optional[TradeThesis]:
        """Evaluate a single earnings event for tradability.

        This is the per-event entry point (similar to
        ``ThesisGenerator.generate_thesis_from_event``).
        Returns a thesis if the opportunity passes filters, else *None*.
        """
        if event.event_type != EventType.EARNINGS_UPCOMING:
            return None
        if not event.symbol:
            return None

        # Build a single-event prompt
        prompt = self._build_single_event_prompt(event, ctx)
        try:
            result: EarningsAnalysisOutput = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=prompt,
                output_schema=EarningsAnalysisOutput,
            )
        except Exception as exc:
            logger.error(f"LLM single-event analysis failed for {event.symbol}: {exc}")
            return None

        if result.play_type == "skip" or result.conviction < self.min_conviction:
            return None

        return self._create_thesis_from_analysis(result, ctx)

    def classify_earnings_play(
        self,
        _event: MarketEvent,
        days_until_earnings: int,
    ) -> EarningsPlayType:
        """Determine the best earnings play strategy.

        Quick heuristic classification — used before the LLM call.
        """
        if days_until_earnings < 0:
            # Earnings already happened → post-momentum only
            if days_until_earnings >= -3:
                return EarningsPlayType.POST_EARNINGS_MOMENTUM
            return EarningsPlayType.SKIP

        if days_until_earnings <= self.entry_days_before:
            return EarningsPlayType.PRE_EARNINGS_DRIFT

        # Too far out
        return EarningsPlayType.SKIP

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_earnings_prompt(
        self,
        events: list[MarketEvent],
        ctx: AgentContext,
    ) -> str:
        """Build the multi-event earnings analysis prompt."""
        events_section = ""
        for e in events:
            days = (e.earnings_date - date.today()).days if e.earnings_date else "?"
            price_str = f"${ctx.prices.get(e.symbol, 'N/A')}" if e.symbol else "N/A"
            eps_str = f"${e.estimate_eps}" if e.estimate_eps else "N/A"
            events_section += (
                f"\n- {e.symbol}: Earnings on {e.earnings_date} "
                f"(in {days} days), EPS estimate: {eps_str}, "
                f"Current price: {price_str}"
            )

        return f"""Analyze these upcoming earnings for trading opportunities:

UPCOMING EARNINGS:{events_section}

PORTFOLIO CONTEXT:
- Cash: ${ctx.cash:,.2f}
- Portfolio value: ${ctx.portfolio_value:,.2f}
- Open positions: {len(ctx.positions)}
- Current drawdown: {ctx.current_drawdown:.1f}%
- Risk budget: {ctx.risk_budget:.1%}

RULES:
- Maximum {self.max_plays_per_batch} plays per batch
- Minimum conviction threshold: {self.min_conviction:.0%}
- Pre-earnings drift: entry 3–5 days before, exit day before earnings
- Post-earnings momentum: entry after results, exit within 1–3 days
- Skip if no clear statistical edge

Respond with your analysis in JSON matching the EarningsAnalysisBatch schema."""

    def _build_single_event_prompt(
        self,
        event: MarketEvent,
        ctx: AgentContext,
    ) -> str:
        """Build prompt for a single earnings event."""
        symbol = event.symbol or "UNKNOWN"
        days = (event.earnings_date - date.today()).days if event.earnings_date else "?"
        price = ctx.prices.get(symbol, Decimal("0"))
        eps_str = f"${event.estimate_eps}" if event.estimate_eps else "N/A"

        indicators_str = ""
        if symbol in ctx.indicators:
            for k, v in ctx.indicators[symbol].items():
                indicators_str += f"\n  - {k}: {v:.2f}"

        return f"""Evaluate this earnings opportunity:

SYMBOL: {symbol}
EARNINGS DATE: {event.earnings_date} (in {days} days)
EPS ESTIMATE: {eps_str}
CURRENT PRICE: ${price}
{f"TECHNICAL INDICATORS:{indicators_str}" if indicators_str else ""}

PORTFOLIO:
- Cash: ${ctx.cash:,.2f}
- Current drawdown: {ctx.current_drawdown:.1f}%

Should we trade this earnings event? If yes, what strategy?

Respond with JSON matching the EarningsAnalysisOutput schema."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_earnings_events(ctx: AgentContext) -> list[MarketEvent]:
        """Pull EARNINGS_UPCOMING events from context."""
        events: list[MarketEvent] = []
        for raw in ctx.events:
            if isinstance(raw, dict):
                etype = raw.get("event_type", "")
                if etype == EventType.EARNINGS_UPCOMING.value or etype == "earnings_upcoming":
                    try:
                        events.append(MarketEvent(**raw))
                    except Exception:
                        pass
            elif isinstance(raw, MarketEvent):
                if raw.event_type == EventType.EARNINGS_UPCOMING:
                    events.append(raw)
        return events

    def _create_thesis_from_analysis(
        self,
        analysis: EarningsAnalysisOutput,
        ctx: AgentContext,
    ) -> Optional[TradeThesis]:
        """Convert an LLM analysis output to a ``TradeThesis``."""
        symbol = analysis.symbol
        price = ctx.prices.get(symbol)
        if not price or price <= 0:
            logger.warning(f"No price for {symbol} — cannot create thesis")
            return None

        # Map play type to trade type
        if analysis.play_type == "pre_earnings_drift":
            trade_type = TradeType.SWING_SHORT
        elif analysis.play_type == "post_earnings_momentum":
            trade_type = TradeType.DAY_TRADE
        else:
            return None

        direction = TradeDirection.LONG if analysis.direction == "long" else TradeDirection.SHORT

        target_pct = Decimal(str(max(analysis.target_pct, 1.0)))
        stop_pct = Decimal(str(max(analysis.stop_pct, 0.5)))

        if direction == TradeDirection.LONG:
            profit_target = price * (1 + target_pct / 100)
            stop_loss = price * (1 - stop_pct / 100)
        else:
            profit_target = price * (1 - target_pct / 100)
            stop_loss = price * (1 + stop_pct / 100)

        # Exit dates
        today = date.today()
        if analysis.play_type == "pre_earnings_drift":
            expected_exit = today + timedelta(days=self.entry_days_before)
            max_hold = today + timedelta(days=self.entry_days_before + 2)
        else:
            expected_exit = today + timedelta(days=3)
            max_hold = today + timedelta(days=5)

        return TradeThesis(
            symbol=symbol,
            trade_type=trade_type,
            direction=direction,
            entry_rationale=analysis.entry_rationale,
            catalyst=analysis.catalyst,
            catalyst_date=None,
            entry_price_target=price,
            profit_target=profit_target,
            stop_loss=stop_loss,
            expected_exit_date=expected_exit,
            max_hold_date=max_hold,
            invalidation_conditions=analysis.risk_factors[:3],
            status=ThesisStatus.DRAFT,
            confidence=analysis.conviction,
            source="earnings_agent",
        )
