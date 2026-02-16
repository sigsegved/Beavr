"""Portfolio lifecycle models — records, decisions, and snapshots.

These models represent the core portfolio management concepts:
- PortfolioRecord: a named trading session with config and running stats
- PortfolioDecision: an auditable decision within a portfolio
- PortfolioSnapshot: a daily point-in-time portfolio value capture
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TradingMode(str, Enum):
    """Paper vs live trading — NEVER mix."""

    PAPER = "paper"
    LIVE = "live"


class Aggressiveness(str, Enum):
    """Risk profile that modulates V2Config parameters."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class PortfolioStatus(str, Enum):
    """Lifecycle status of a portfolio."""

    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class DecisionType(str, Enum):
    """Every material decision type logged to the audit trail."""

    THESIS_CREATED = "thesis_created"
    THESIS_REJECTED = "thesis_rejected"
    DD_APPROVED = "dd_approved"
    DD_REJECTED = "dd_rejected"
    DD_CONDITIONAL = "dd_conditional"
    TRADE_ENTERED = "trade_entered"
    TRADE_SKIPPED = "trade_skipped"
    POSITION_HOLD = "position_hold"
    POSITION_PARTIAL_EXIT = "position_partial_exit"
    POSITION_EXIT_TARGET = "position_exit_target"
    POSITION_EXIT_STOP = "position_exit_stop"
    POSITION_EXIT_TIME = "position_exit_time"
    POSITION_EXIT_INVALIDATED = "position_exit_invalidated"
    POSITION_EXIT_MANUAL = "position_exit_manual"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"
    CIRCUIT_BREAKER_RESET = "circuit_breaker_reset"
    PHASE_TRANSITION = "phase_transition"
    RESEARCH_CYCLE = "research_cycle"
    PORTFOLIO_PAUSED = "portfolio_paused"
    PORTFOLIO_RESUMED = "portfolio_resumed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PortfolioRecord(BaseModel):
    """Persisted portfolio with configuration, personality, and running stats.

    A portfolio is the fundamental unit of operation — every ``bvr ai auto``
    session is bound to exactly one portfolio.  Paper and live portfolios
    are strictly isolated.
    """

    id: str = Field(default_factory=lambda: str(uuid4())[:8], description="Unique portfolio ID")
    name: str = Field(description="User-friendly portfolio name")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    closed_at: Optional[datetime] = Field(default=None, description="When portfolio was closed")
    status: PortfolioStatus = Field(default=PortfolioStatus.ACTIVE, description="Lifecycle status")
    mode: TradingMode = Field(description="Paper or live — NEVER mix")

    # Capital
    initial_capital: Decimal = Field(description="Starting capital allocation")
    allocated_capital: Decimal = Field(description="Capital available for trading (after capital_pct)")
    current_cash: Decimal = Field(description="Remaining uninvested cash")

    # Configuration snapshot (frozen at creation time)
    config_snapshot: dict = Field(default_factory=dict, description="V2Config dump at creation time")

    # AI Personality
    aggressiveness: Aggressiveness = Field(
        default=Aggressiveness.MODERATE,
        description="Risk profile: conservative, moderate, or aggressive",
    )
    directives: list[str] = Field(
        default_factory=list,
        description="User-provided AI personality directives",
    )

    # Running totals (updated per trade)
    total_invested: Decimal = Field(default=Decimal("0"), description="Cumulative amount invested")
    total_returned: Decimal = Field(default=Decimal("0"), description="Cumulative amount returned")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Cumulative realized P&L")
    total_trades: int = Field(default=0, description="Total trades executed")
    winning_trades: int = Field(default=0, description="Profitable trades count")
    losing_trades: int = Field(default=0, description="Unprofitable trades count")

    # Risk
    peak_value: Decimal = Field(default=Decimal("0"), description="Peak portfolio value")
    max_drawdown_pct: float = Field(default=0.0, description="Maximum drawdown percentage")

    # Metadata
    notes: Optional[str] = Field(default=None, description="Free-form notes")

    model_config = {"frozen": False}

    @property
    def win_rate(self) -> float:
        """Win rate as a percentage (0.0–100.0)."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100.0

    @property
    def is_active(self) -> bool:
        """Whether the portfolio is currently active."""
        return self.status == PortfolioStatus.ACTIVE


class PortfolioDecision(BaseModel):
    """Single auditable decision within a portfolio.

    Every material AI decision — thesis creation, DD approval, trade
    entry, position exit, circuit-breaker trigger, etc. — is persisted
    as a decision for full reproducibility and audit.
    """

    id: str = Field(default_factory=lambda: str(uuid4())[:8], description="Unique decision ID")
    portfolio_id: str = Field(description="Owning portfolio ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the decision was made")
    phase: str = Field(description="Orchestrator phase (e.g. market_hours, overnight_dd)")
    decision_type: DecisionType = Field(description="Category of decision")
    symbol: Optional[str] = Field(default=None, description="Relevant trading symbol")

    # Linked entities (not all decisions have all links)
    thesis_id: Optional[str] = Field(default=None, description="Linked thesis ID")
    dd_report_id: Optional[str] = Field(default=None, description="Linked DD report ID")
    position_id: Optional[str] = Field(default=None, description="Linked position ID")
    event_id: Optional[str] = Field(default=None, description="Linked market event ID")

    # Decision content
    action: str = Field(description="What was decided (buy, sell, skip, hold, etc.)")
    reasoning: Optional[str] = Field(default=None, description="AI or rule-based reasoning")
    confidence: Optional[float] = Field(default=None, description="Confidence level 0.0–1.0")

    # Financial impact
    amount: Optional[Decimal] = Field(default=None, description="Dollar amount involved")
    shares: Optional[Decimal] = Field(default=None, description="Shares involved")
    price: Optional[Decimal] = Field(default=None, description="Price at decision time")

    # Outcome (filled in later)
    outcome: Optional[str] = Field(default=None, description="success | failure | pending")
    outcome_details: Optional[dict] = Field(default=None, description="Structured outcome data")

    model_config = {"frozen": True}


class PortfolioSnapshot(BaseModel):
    """Daily portfolio value snapshot for equity-curve construction.

    Captures point-in-time state: equity value, cash, positions value,
    daily/cumulative P&L.  Used for drawdown analysis and charting.
    """

    id: str = Field(default_factory=lambda: str(uuid4())[:8], description="Unique snapshot ID")
    portfolio_id: str = Field(description="Owning portfolio ID")
    snapshot_date: date = Field(description="Date this snapshot represents")
    timestamp: datetime = Field(default_factory=datetime.now, description="Exact capture timestamp")

    # Values
    portfolio_value: Decimal = Field(description="Total value (cash + positions)")
    cash: Decimal = Field(description="Cash balance")
    positions_value: Decimal = Field(description="Market value of open positions")

    # Daily P&L
    daily_pnl: Decimal = Field(default=Decimal("0"), description="P&L for this day")
    daily_pnl_pct: float = Field(default=0.0, description="Daily P&L as percentage")

    # Cumulative
    cumulative_pnl: Decimal = Field(default=Decimal("0"), description="Total P&L since inception")
    cumulative_pnl_pct: float = Field(default=0.0, description="Cumulative P&L percentage")

    # Positions
    open_positions: int = Field(default=0, description="Number of open positions")
    trades_today: int = Field(default=0, description="Trades executed today")

    model_config = {"frozen": True}
