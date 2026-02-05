"""Trade thesis models for AI Investor v2."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TradeType(str, Enum):
    """
    Expected holding period category for a trade.
    
    The DD Agent classifies each opportunity into one of these categories
    based on catalyst timing and expected move duration.
    """
    
    # Day trade: Power hour strategy, exit by 10:30 AM
    DAY_TRADE = "day_trade"
    
    # Swing trades with different time horizons
    SWING_SHORT = "swing_short"    # 1-2 weeks, 5-10% target
    SWING_MEDIUM = "swing_medium"  # 1-3 months, 10-20% target
    SWING_LONG = "swing_long"      # 3-12 months, 20-50% target
    
    @property
    def default_target_pct(self) -> float:
        """Default profit target percentage for this trade type."""
        return {
            TradeType.DAY_TRADE: 2.0,
            TradeType.SWING_SHORT: 8.0,
            TradeType.SWING_MEDIUM: 15.0,
            TradeType.SWING_LONG: 30.0,
        }[self]
    
    @property
    def default_stop_pct(self) -> float:
        """Default stop loss percentage for this trade type."""
        return {
            TradeType.DAY_TRADE: 1.0,
            TradeType.SWING_SHORT: 4.0,
            TradeType.SWING_MEDIUM: 7.0,
            TradeType.SWING_LONG: 12.0,
        }[self]
    
    @property
    def max_hold_days(self) -> int:
        """Maximum days to hold for this trade type."""
        return {
            TradeType.DAY_TRADE: 1,
            TradeType.SWING_SHORT: 14,
            TradeType.SWING_MEDIUM: 90,
            TradeType.SWING_LONG: 365,
        }[self]
    
    @property
    def min_conviction(self) -> float:
        """Minimum DD conviction required for this trade type."""
        return {
            TradeType.DAY_TRADE: 0.70,
            TradeType.SWING_SHORT: 0.65,
            TradeType.SWING_MEDIUM: 0.70,
            TradeType.SWING_LONG: 0.80,
        }[self]


class TradeDirection(str, Enum):
    """Trade direction."""
    
    LONG = "long"
    SHORT = "short"


class ThesisStatus(str, Enum):
    """Current status of a trade thesis."""
    
    DRAFT = "draft"  # Under development
    ACTIVE = "active"  # Ready for execution
    EXECUTED = "executed"  # Position opened
    CLOSED = "closed"  # Position closed
    INVALIDATED = "invalidated"  # Thesis invalidated before execution


class TradeThesis(BaseModel):
    """
    Structured investment hypothesis for a position.
    
    Every position in the v2 system must have an attached thesis that
    documents why we entered, what we expect, and when we plan to exit.
    This replaces the v1 approach of "buy because RSI is low."
    """
    
    # Identification
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique thesis identifier",
    )
    symbol: str = Field(description="Trading symbol")
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When thesis was created",
    )
    
    # Classification
    trade_type: TradeType = Field(
        description="Expected holding period category",
    )
    
    # Core Hypothesis
    direction: TradeDirection = Field(
        default=TradeDirection.LONG,
        description="Trade direction (long or short)",
    )
    entry_rationale: str = Field(
        description="Why we are entering this trade (2-3 sentences)",
    )
    catalyst: str = Field(
        description="Specific event/condition expected to drive the move",
    )
    catalyst_date: Optional[date] = Field(
        default=None,
        description="When the catalyst is expected (earnings date, etc.)",
    )
    
    # Price Targets (all in Decimal for financial precision)
    entry_price_target: Decimal = Field(
        description="Ideal entry price",
    )
    profit_target: Decimal = Field(
        description="Price target for taking profits",
    )
    stop_loss: Decimal = Field(
        description="Price level to cut losses",
    )
    
    # Time Management
    expected_exit_date: date = Field(
        description="When we expect to exit, regardless of price",
    )
    max_hold_date: date = Field(
        description="Latest date to hold—must exit by this date",
    )
    
    # Invalidation
    invalidation_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions that would invalidate the thesis",
    )
    
    # Status Tracking
    status: ThesisStatus = Field(
        default=ThesisStatus.DRAFT,
        description="Current thesis status",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.5,
        description="Confidence in the thesis (0.0 to 1.0)",
    )
    dd_approved: bool = Field(
        default=False,
        description="Whether DD Agent approved this thesis",
    )
    dd_report_id: Optional[str] = Field(
        default=None,
        description="ID of associated DD report",
    )
    
    # Optional metadata
    source: Optional[str] = Field(
        default=None,
        description="How this thesis was generated (news, scan, manual)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes or context",
    )
    
    @field_validator("entry_price_target", "profit_target", "stop_loss", mode="before")
    @classmethod
    def convert_to_decimal(cls, v: Decimal | float | str) -> Decimal:
        """Convert price values to Decimal."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    
    @property
    def risk_reward_ratio(self) -> float:
        """Calculate risk/reward ratio based on targets."""
        if self.direction == TradeDirection.LONG:
            reward = float(self.profit_target - self.entry_price_target)
            risk = float(self.entry_price_target - self.stop_loss)
        else:
            reward = float(self.entry_price_target - self.profit_target)
            risk = float(self.stop_loss - self.entry_price_target)
        
        if risk <= 0:
            return 0.0
        return reward / risk
    
    @property
    def target_pct(self) -> float:
        """Target profit as percentage."""
        if self.direction == TradeDirection.LONG:
            return float((self.profit_target - self.entry_price_target) / self.entry_price_target) * 100
        return float((self.entry_price_target - self.profit_target) / self.entry_price_target) * 100
    
    @property
    def stop_pct(self) -> float:
        """Stop loss as percentage."""
        if self.direction == TradeDirection.LONG:
            return float((self.entry_price_target - self.stop_loss) / self.entry_price_target) * 100
        return float((self.stop_loss - self.entry_price_target) / self.entry_price_target) * 100

    def __str__(self) -> str:
        """Human-readable thesis summary."""
        return (
            f"Thesis({self.id}): {self.direction.value.upper()} {self.symbol} "
            f"@ ${self.entry_price_target} → ${self.profit_target} "
            f"(stop ${self.stop_loss}) by {self.expected_exit_date}"
        )


class ThesisSummary(BaseModel):
    """Lightweight thesis summary for lists and displays."""
    
    id: str = Field(description="Thesis ID")
    symbol: str = Field(description="Trading symbol")
    direction: TradeDirection = Field(description="Trade direction")
    trade_type: TradeType = Field(description="Trade type")
    status: ThesisStatus = Field(description="Current status")
    catalyst: str = Field(description="Expected catalyst")
    catalyst_date: Optional[date] = Field(description="Catalyst date")
    confidence: float = Field(description="Confidence level")
    dd_approved: bool = Field(description="DD approved")
    created_at: datetime = Field(description="Creation time")
    
    model_config = {"frozen": True}
