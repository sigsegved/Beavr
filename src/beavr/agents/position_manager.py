"""Position Manager Agent for monitoring and exit decisions.

The Position Manager runs continuously during market hours, monitoring
all open positions against their theses and executing exit decisions.

Key responsibilities:
- Price-based exits (stop loss, profit target)
- Time-based exits (max hold date, day trade deadline)
- Thesis validation (catalyst occurred, conditions changed)
- Power hour management for day trades
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.thesis import TradeType

if TYPE_CHECKING:
    from beavr.llm.client import LLMClient

logger = logging.getLogger(__name__)


class ExitType(str, Enum):
    """Reason for exiting a position."""
    
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    TIME_EXIT = "time_exit"
    THESIS_INVALIDATED = "thesis_invalidated"
    POWER_HOUR_DEADLINE = "power_hour_deadline"
    PARTIAL_PROFIT = "partial_profit"
    MANUAL = "manual"


class ExitAction(str, Enum):
    """Actions the Position Manager can take."""
    
    HOLD = "hold"
    EXIT_FULL = "exit_full"
    EXIT_PARTIAL = "exit_partial"
    ADJUST_STOP = "adjust_stop"
    FLAG_REVIEW = "flag_review"


class ThesisValidationStatus(str, Enum):
    """Status of thesis validation during review."""
    
    INTACT = "intact"
    WEAKENING = "weakening"
    INVALIDATED = "invalidated"


class CatalystStatus(str, Enum):
    """Status of the expected catalyst."""
    
    PENDING = "pending"
    OCCURRED = "occurred"
    MISSED = "missed"


class PositionReview(BaseModel):
    """Result of reviewing a position against its thesis."""
    
    position_id: str = Field(description="Position identifier")
    symbol: str = Field(description="Trading symbol")
    review_timestamp: datetime = Field(default_factory=datetime.now)
    
    # Current state
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float
    days_held: int
    
    # Trade type
    trade_type: str = Field(description="day_trade, swing_short, etc.")
    is_day_trade: bool = Field(default=False)
    
    # Thesis check
    thesis_status: ThesisValidationStatus
    catalyst_status: CatalystStatus
    
    # Targets
    stop_price: Decimal
    target_price: Decimal
    
    # Decision
    action: ExitAction
    action_rationale: str
    
    # If exit recommended
    exit_type: Optional[ExitType] = None
    exit_shares_pct: float = Field(
        default=1.0,
        description="Percentage of shares to exit (1.0 = full exit)"
    )
    
    # Alerts
    alerts: list[str] = Field(default_factory=list)


class PositionManagerAgent(BaseAgent):
    """
    Position Manager Agent for monitoring and exit decisions.
    
    Runs continuously during market hours:
    - Every 5 minutes for swing positions
    - Every 2 minutes during power hour (9:30-10:30 AM) for day trades
    
    Exit triggers:
    1. Price-based: Stop loss or profit target hit
    2. Time-based: Max hold date or day trade deadline
    3. Thesis-based: Catalyst missed or invalidation condition triggered
    """
    
    name: ClassVar[str] = "Position Manager"
    role: ClassVar[str] = "risk"
    description: ClassVar[str] = "Position monitoring and exit execution"
    version: ClassVar[str] = "2.0.0"
    
    # Time constants (Eastern Time)
    MARKET_OPEN = time(9, 30)
    POWER_HOUR_END = time(10, 30)
    MARKET_CLOSE = time(16, 0)
    
    # System prompt for thesis validation
    SYSTEM_PROMPT: ClassVar[str] = """You are a Position Manager for an automated trading system.
Your job is to monitor positions and make exit decisions.

PRIMARY RESPONSIBILITIES:

1. PRICE-BASED EXITS
   - Stop loss hit → IMMEDIATE EXIT
   - Profit target hit → EXECUTE EXIT
   - Consider trailing stops for winners

2. TIME-BASED EXITS
   - Day trades: MUST exit by 10:30 AM ET
   - Past max_hold_date → FORCE EXIT
   - Approaching expected_exit_date → FLAG FOR REVIEW

3. THESIS VALIDATION
   - Has the catalyst occurred?
   - Did it play out as expected?
   - Have invalidation conditions triggered?

4. POWER HOUR MANAGEMENT (9:30-10:30 AM)
   For day trades:
   - Monitor every 2 minutes
   - Tight stop management
   - Mandatory exit at 10:30 AM regardless of P/L

DECISION FRAMEWORK:

CHECK 1: Price Levels
- If price <= stop_loss → EXIT_FULL, type=stop_hit
- If price >= profit_target → EXIT_FULL, type=target_hit

CHECK 2: Time Constraints
- If trade_type == day_trade AND time >= 10:30 AM → EXIT_FULL
- If date > max_hold_date → EXIT_FULL

CHECK 3: Thesis Status
- If catalyst occurred AND contradicts thesis → FLAG_FOR_REVIEW
- If invalidation condition triggered → EXIT_FULL

CHECK 4: Partial Profits
- If unrealized_gain > 10% AND below target → Consider EXIT_PARTIAL (50%)

ALWAYS prioritize capital preservation over profit maximization."""

    def __init__(
        self,
        llm: LLMClient,
        check_interval_minutes: int = 5,
        power_hour_interval_minutes: int = 2,
        partial_profit_threshold_pct: float = 10.0,
        partial_profit_pct: float = 0.50,
    ) -> None:
        """
        Initialize the Position Manager.
        
        Args:
            llm: LLM client for reasoning
            check_interval_minutes: Interval for checking swing positions
            power_hour_interval_minutes: Interval during power hour
            partial_profit_threshold_pct: Threshold for partial profit taking
            partial_profit_pct: Percentage to sell at partial profit
        """
        super().__init__(llm)
        self.check_interval_minutes = check_interval_minutes
        self.power_hour_interval_minutes = power_hour_interval_minutes
        self.partial_profit_threshold_pct = partial_profit_threshold_pct
        self.partial_profit_pct = partial_profit_pct
    
    def get_system_prompt(self) -> str:
        """Return the agent's system prompt."""
        return self.SYSTEM_PROMPT
    
    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """
        Analyze all open positions and determine actions.
        
        Called by the orchestrator during the monitoring phase.
        """
        start_time = datetime.now()
        
        # Get positions from context
        positions = ctx.positions
        if not positions:
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],
                conviction=0.0,
                rationale="No open positions to monitor",
                risk_score=0.0,
                risk_factors=[],
                model_version=self.version,
            )
        
        # Review each position
        reviews = []
        exit_signals = []
        
        for symbol, shares in positions.items():
            if float(shares) <= 0:
                continue
            
            review = self.review_position(symbol, shares, ctx)
            reviews.append(review)
            
            # Generate exit signal if action required
            if review.action in (ExitAction.EXIT_FULL, ExitAction.EXIT_PARTIAL):
                exit_signals.append({
                    "symbol": symbol,
                    "action": "sell",
                    "shares_pct": review.exit_shares_pct,
                    "reason": review.action_rationale,
                    "exit_type": review.exit_type.value if review.exit_type else None,
                    "urgency": "immediate" if review.exit_type in (
                        ExitType.STOP_HIT, ExitType.POWER_HOUR_DEADLINE
                    ) else "normal",
                })
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Calculate overall risk
        positions_at_risk = sum(1 for r in reviews if r.thesis_status != ThesisValidationStatus.INTACT)
        
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=exit_signals,
            conviction=1.0 - (positions_at_risk / max(len(reviews), 1)),
            rationale=f"Reviewed {len(reviews)} positions, {len(exit_signals)} exits triggered",
            risk_score=positions_at_risk / max(len(reviews), 1),
            risk_factors=[r.alerts[0] for r in reviews if r.alerts],
            model_version=self.version,
            processing_time_ms=processing_time,
            extra={
                "reviews": [r.model_dump() for r in reviews],
                "exit_count": len(exit_signals),
            },
        )
    
    def review_position(
        self,
        symbol: str,
        shares: Decimal,
        ctx: AgentContext,
        thesis_data: Optional[dict] = None,
        _dd_report_data: Optional[dict] = None,
    ) -> PositionReview:
        """
        Review a single position against its thesis.
        
        Args:
            symbol: Trading symbol
            shares: Current position size
            ctx: Market context
            thesis_data: Optional thesis information
            _dd_report_data: Optional DD report data
            
        Returns:
            PositionReview with action recommendation
        """
        current_price = ctx.prices.get(symbol, Decimal("0"))
        
        # Get position data (mock for now - would come from position store)
        entry_price = thesis_data.get("entry_price", current_price) if thesis_data else current_price
        stop_price = thesis_data.get("stop_loss", entry_price * Decimal("0.95")) if thesis_data else entry_price * Decimal("0.95")
        target_price = thesis_data.get("profit_target", entry_price * Decimal("1.10")) if thesis_data else entry_price * Decimal("1.10")
        trade_type = thesis_data.get("trade_type", "swing_short") if thesis_data else "swing_short"
        entry_date = thesis_data.get("entry_date", date.today()) if thesis_data else date.today()
        max_hold_date = thesis_data.get("max_hold_date", date.today() + timedelta(days=14)) if thesis_data else date.today() + timedelta(days=14)
        
        # Calculate P/L
        unrealized_pnl = (current_price - entry_price) * shares
        unrealized_pnl_pct = float((current_price - entry_price) / entry_price * 100)
        days_held = (date.today() - entry_date).days if isinstance(entry_date, date) else 0
        
        is_day_trade = trade_type == "day_trade" or trade_type == TradeType.DAY_TRADE.value
        
        # Initialize review
        alerts = []
        action = ExitAction.HOLD
        action_rationale = "Position within parameters"
        exit_type = None
        exit_shares_pct = 1.0
        
        # Check 1: Price-based exits
        if current_price <= stop_price:
            action = ExitAction.EXIT_FULL
            exit_type = ExitType.STOP_HIT
            action_rationale = f"Stop loss triggered at ${current_price:.2f} (stop: ${stop_price:.2f})"
            alerts.append("⚠️ STOP LOSS HIT")
        
        elif current_price >= target_price:
            action = ExitAction.EXIT_FULL
            exit_type = ExitType.TARGET_HIT
            action_rationale = f"Profit target reached at ${current_price:.2f} (target: ${target_price:.2f})"
            alerts.append("🎯 TARGET HIT")
        
        # Check 2: Time-based exits
        elif is_day_trade and self._is_power_hour_deadline():
            action = ExitAction.EXIT_FULL
            exit_type = ExitType.POWER_HOUR_DEADLINE
            action_rationale = "Day trade power hour deadline (10:30 AM) - mandatory exit"
            alerts.append("⏰ POWER HOUR DEADLINE")
        
        elif date.today() > max_hold_date:
            action = ExitAction.EXIT_FULL
            exit_type = ExitType.TIME_EXIT
            action_rationale = f"Max hold date exceeded ({max_hold_date})"
            alerts.append("📅 MAX HOLD DATE EXCEEDED")
        
        # Check 3: Partial profit taking
        elif unrealized_pnl_pct >= self.partial_profit_threshold_pct and not is_day_trade:
            # Check if we should take partial profits
            action = ExitAction.EXIT_PARTIAL
            exit_type = ExitType.PARTIAL_PROFIT
            exit_shares_pct = self.partial_profit_pct
            action_rationale = f"Taking {self.partial_profit_pct:.0%} profit at {unrealized_pnl_pct:.1f}% gain"
            alerts.append(f"💰 PARTIAL PROFIT ({unrealized_pnl_pct:.1f}%)")
        
        # Check 4: Thesis validation (would involve LLM for complex cases)
        thesis_status = ThesisValidationStatus.INTACT
        catalyst_status = CatalystStatus.PENDING
        
        # Simple thesis checks
        if thesis_data:
            catalyst_date = thesis_data.get("catalyst_date")
            if catalyst_date and date.today() > catalyst_date:
                catalyst_status = CatalystStatus.OCCURRED
                # If catalyst passed and price didn't move as expected, flag
                if unrealized_pnl_pct < 0:
                    thesis_status = ThesisValidationStatus.WEAKENING
                    alerts.append("⚠️ Catalyst passed, thesis weakening")
        
        return PositionReview(
            position_id=f"pos_{symbol}",
            symbol=symbol,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            days_held=days_held,
            trade_type=trade_type,
            is_day_trade=is_day_trade,
            thesis_status=thesis_status,
            catalyst_status=catalyst_status,
            stop_price=stop_price,
            target_price=target_price,
            action=action,
            action_rationale=action_rationale,
            exit_type=exit_type,
            exit_shares_pct=exit_shares_pct,
            alerts=alerts,
        )
    
    def _is_power_hour_deadline(self) -> bool:
        """Check if we're at or past the power hour deadline (10:30 AM ET)."""
        now = datetime.now()
        current_time = now.time()
        return current_time >= self.POWER_HOUR_END
    
    def _is_power_hour(self) -> bool:
        """Check if we're in the power hour (9:30 AM - 10:30 AM ET)."""
        now = datetime.now()
        current_time = now.time()
        return self.MARKET_OPEN <= current_time < self.POWER_HOUR_END
    
    def get_check_interval(self) -> int:
        """Get the appropriate check interval based on current time."""
        if self._is_power_hour():
            return self.power_hour_interval_minutes
        return self.check_interval_minutes
    
    def generate_daily_summary(
        self,
        reviews: list[PositionReview],
    ) -> str:
        """Generate a daily summary of position reviews."""
        
        total_pnl = sum(float(r.unrealized_pnl) for r in reviews)
        exits_triggered = [r for r in reviews if r.action in (ExitAction.EXIT_FULL, ExitAction.EXIT_PARTIAL)]
        
        summary = f"""# Daily Position Summary - {date.today()}

## Overview
- **Positions Reviewed:** {len(reviews)}
- **Exits Triggered:** {len(exits_triggered)}
- **Total Unrealized P/L:** ${total_pnl:,.2f}

## Position Details

| Symbol | Entry | Current | P/L % | Status | Action |
|--------|-------|---------|-------|--------|--------|
"""
        
        for r in reviews:
            status_emoji = {
                ThesisValidationStatus.INTACT: "✅",
                ThesisValidationStatus.WEAKENING: "⚠️",
                ThesisValidationStatus.INVALIDATED: "❌",
            }[r.thesis_status]
            
            summary += f"| {r.symbol} | ${r.entry_price:.2f} | ${r.current_price:.2f} | {r.unrealized_pnl_pct:+.1f}% | {status_emoji} | {r.action.value} |\n"
        
        if exits_triggered:
            summary += "\n## Exits Triggered\n\n"
            for r in exits_triggered:
                summary += f"- **{r.symbol}**: {r.action_rationale}\n"
        
        return summary


