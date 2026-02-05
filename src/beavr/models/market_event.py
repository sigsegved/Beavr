"""Market event models for AI Investor v2 News Monitor."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    """Classification of market events."""
    
    # Earnings related
    EARNINGS_ANNOUNCED = "earnings_announced"  # Actual earnings released
    EARNINGS_UPCOMING = "earnings_upcoming"  # Earnings scheduled
    GUIDANCE_CHANGE = "guidance_change"  # Company guidance update
    
    # Analyst activity
    ANALYST_UPGRADE = "analyst_upgrade"
    ANALYST_DOWNGRADE = "analyst_downgrade"
    PRICE_TARGET_CHANGE = "price_target_change"
    
    # Insider activity
    INSIDER_BUY = "insider_buy"
    INSIDER_SELL = "insider_sell"
    
    # Regulatory filings
    SEC_FILING = "sec_filing"  # 8-K, 10-K, 10-Q, etc.
    
    # Macro events
    MACRO_RELEASE = "macro_release"  # Jobs, CPI, Fed, etc.
    
    # General news
    NEWS_CATALYST = "news_catalyst"  # Product launch, partnership, etc.
    
    # Custom/other
    OTHER = "other"


class EventImportance(str, Enum):
    """Importance classification for event filtering."""
    
    HIGH = "high"  # Likely to move stock 5%+
    MEDIUM = "medium"  # Could move stock 2-5%
    LOW = "low"  # Minor news, background info


class MarketEvent(BaseModel):
    """
    A market-moving event detected by the News Monitor.
    
    Events are sourced from news APIs, SEC filings, earnings calendars,
    and macro data releases. The News Monitor creates events, and the
    Thesis Generator processes them to form trading theses.
    """
    
    # Identification
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique event identifier",
    )
    
    # Event classification
    event_type: EventType = Field(description="Type of market event")
    
    # Core content
    symbol: Optional[str] = Field(
        default=None,
        description="Trading symbol (None for macro events)",
    )
    headline: str = Field(description="Event headline/title")
    summary: str = Field(description="Brief summary of the event")
    source: str = Field(description="Data source (alpaca, sec, yahoo, etc.)")
    url: Optional[str] = Field(
        default=None,
        description="Link to full article/filing",
    )
    
    # Timing
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When event occurred or was detected",
    )
    event_date: Optional[date] = Field(
        default=None,
        description="Relevant date for the event (e.g., earnings date)",
    )
    
    # Classification
    importance: EventImportance = Field(
        default=EventImportance.MEDIUM,
        description="Importance level for filtering",
    )
    
    # Structured data (varies by event type)
    # For earnings
    earnings_date: Optional[date] = Field(
        default=None,
        description="Earnings report date (for earnings events)",
    )
    estimate_eps: Optional[Decimal] = Field(
        default=None,
        description="Consensus EPS estimate",
    )
    actual_eps: Optional[Decimal] = Field(
        default=None,
        description="Actual reported EPS",
    )
    estimate_revenue: Optional[Decimal] = Field(
        default=None,
        description="Consensus revenue estimate",
    )
    actual_revenue: Optional[Decimal] = Field(
        default=None,
        description="Actual reported revenue",
    )
    
    # For analyst events
    analyst_firm: Optional[str] = Field(
        default=None,
        description="Analyst firm name",
    )
    old_rating: Optional[str] = Field(
        default=None,
        description="Previous rating",
    )
    new_rating: Optional[str] = Field(
        default=None,
        description="New rating",
    )
    old_price_target: Optional[Decimal] = Field(
        default=None,
        description="Previous price target",
    )
    new_price_target: Optional[Decimal] = Field(
        default=None,
        description="New price target",
    )
    
    # For insider events
    insider_name: Optional[str] = Field(
        default=None,
        description="Name of insider",
    )
    insider_title: Optional[str] = Field(
        default=None,
        description="Title/role of insider",
    )
    transaction_value: Optional[Decimal] = Field(
        default=None,
        description="Dollar value of transaction",
    )
    
    # Processing status
    processed: bool = Field(
        default=False,
        description="Whether event has been processed by Thesis Generator",
    )
    processed_at: Optional[datetime] = Field(
        default=None,
        description="When event was processed",
    )
    thesis_generated: bool = Field(
        default=False,
        description="Whether a thesis was created from this event",
    )
    thesis_id: Optional[str] = Field(
        default=None,
        description="ID of generated thesis (if any)",
    )
    
    # Raw data for debugging
    raw_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Original raw data from source",
    )
    
    @field_validator(
        "estimate_eps", "actual_eps", "estimate_revenue", "actual_revenue",
        "old_price_target", "new_price_target", "transaction_value",
        mode="before"
    )
    @classmethod
    def convert_to_decimal(cls, v: Decimal | float | str | None) -> Decimal | None:
        """Convert values to Decimal."""
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    
    @property
    def is_earnings_related(self) -> bool:
        """Check if event is earnings-related."""
        return self.event_type in (
            EventType.EARNINGS_ANNOUNCED,
            EventType.EARNINGS_UPCOMING,
            EventType.GUIDANCE_CHANGE,
        )
    
    @property
    def is_actionable(self) -> bool:
        """Check if event might lead to a trade."""
        return self.importance in (EventImportance.HIGH, EventImportance.MEDIUM)
    
    def __str__(self) -> str:
        """Human-readable event summary."""
        symbol_str = self.symbol or "MACRO"
        importance_emoji = {
            EventImportance.HIGH: "🔴",
            EventImportance.MEDIUM: "🟡",
            EventImportance.LOW: "⚪",
        }.get(self.importance, "⚪")
        return f"Event({self.id}): {importance_emoji} [{symbol_str}] {self.headline[:50]}..."


class EventSummary(BaseModel):
    """Lightweight event summary for lists."""
    
    id: str = Field(description="Event ID")
    event_type: EventType = Field(description="Event type")
    symbol: Optional[str] = Field(description="Trading symbol")
    headline: str = Field(description="Event headline")
    importance: EventImportance = Field(description="Importance level")
    timestamp: datetime = Field(description="Event timestamp")
    processed: bool = Field(description="Whether processed")
    
    model_config = {"frozen": True}
