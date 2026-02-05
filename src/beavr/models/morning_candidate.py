"""Morning scanner candidate models for AI Investor v2."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ScanType(str, Enum):
    """Type of scan that identified this candidate."""
    
    GAP_UP = "gap_up"  # Significant pre-market gap up
    GAP_DOWN = "gap_down"  # Significant pre-market gap down
    VOLUME_SURGE = "volume_surge"  # Unusual pre-market volume
    BREAKOUT = "breakout"  # Breaking technical resistance
    SECTOR_LEADER = "sector_leader"  # Best performer in hot sector
    THESIS_SETUP = "thesis_setup"  # Aligns with active thesis
    MOMENTUM = "momentum"  # Strong intraday momentum


class MorningCandidate(BaseModel):
    """
    A trading candidate from the Morning Scanner.
    
    The Morning Scanner runs during pre-market (4 AM - 9:30 AM ET)
    to identify momentum opportunities for the trading day. Candidates
    are ranked by conviction score and passed to the DD Agent for
    deeper analysis before execution.
    """
    
    # Identification
    symbol: str = Field(description="Trading symbol")
    scan_type: ScanType = Field(description="How this candidate was identified")
    scan_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the scan identified this candidate",
    )
    
    # Pre-market data
    pre_market_price: Decimal = Field(description="Current pre-market price")
    previous_close: Decimal = Field(description="Previous day's close")
    pre_market_change_pct: float = Field(
        description="Pre-market change percentage",
    )
    pre_market_volume: int = Field(description="Pre-market volume")
    avg_daily_volume: int = Field(description="Average daily volume")
    
    # Volume analysis
    volume_ratio: float = Field(
        description="Pre-market volume as multiple of average",
    )
    
    # Technical levels (if available)
    key_resistance: Optional[Decimal] = Field(
        default=None,
        description="Nearest resistance level",
    )
    key_support: Optional[Decimal] = Field(
        default=None,
        description="Nearest support level",
    )
    rsi_14: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="14-period RSI",
    )
    sma_20: Optional[Decimal] = Field(
        default=None,
        description="20-day simple moving average",
    )
    sma_50: Optional[Decimal] = Field(
        default=None,
        description="50-day simple moving average",
    )
    
    # Catalyst information
    catalyst_summary: str = Field(
        description="Brief description of why stock is moving",
    )
    has_news: bool = Field(
        default=False,
        description="Whether there's recent news driving the move",
    )
    news_headline: Optional[str] = Field(
        default=None,
        description="Most relevant news headline",
    )
    
    # Thesis alignment
    has_active_thesis: bool = Field(
        default=False,
        description="Whether an active thesis exists for this symbol",
    )
    thesis_id: Optional[str] = Field(
        default=None,
        description="ID of matching thesis (if any)",
    )
    
    # Preliminary trade assessment
    preliminary_direction: str = Field(
        default="long",
        description="Expected trade direction: long or short",
    )
    preliminary_target_pct: float = Field(
        description="Preliminary profit target percentage",
    )
    preliminary_stop_pct: float = Field(
        description="Preliminary stop loss percentage",
    )
    
    # Scoring
    conviction_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Scanner's conviction in this opportunity",
    )
    priority_rank: int = Field(
        ge=1,
        description="Rank among today's candidates (1 = highest priority)",
    )
    
    # Quality flags
    is_quality_stock: bool = Field(
        default=True,
        description="Passes quality filters (liquidity, price, market cap)",
    )
    quality_notes: Optional[str] = Field(
        default=None,
        description="Notes about quality concerns (if any)",
    )
    
    # Risk flags
    is_halted: bool = Field(
        default=False,
        description="Whether stock is currently halted",
    )
    extreme_move: bool = Field(
        default=False,
        description="Whether move is extreme (potential pump/dump)",
    )
    low_float: bool = Field(
        default=False,
        description="Whether stock has low float (high volatility risk)",
    )
    
    @field_validator(
        "pre_market_price", "previous_close", "key_resistance", "key_support",
        "sma_20", "sma_50",
        mode="before"
    )
    @classmethod
    def convert_to_decimal(cls, v: Decimal | float | str | None) -> Decimal | None:
        """Convert price values to Decimal."""
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    
    @property
    def gap_pct(self) -> float:
        """Calculate gap percentage from previous close."""
        if self.previous_close == 0:
            return 0.0
        return float(
            (self.pre_market_price - self.previous_close) / self.previous_close * 100
        )
    
    @property
    def distance_to_resistance_pct(self) -> Optional[float]:
        """Calculate percentage distance to resistance."""
        if self.key_resistance is None:
            return None
        return float(
            (self.key_resistance - self.pre_market_price) / self.pre_market_price * 100
        )
    
    @property
    def distance_to_support_pct(self) -> Optional[float]:
        """Calculate percentage distance to support."""
        if self.key_support is None:
            return None
        return float(
            (self.pre_market_price - self.key_support) / self.pre_market_price * 100
        )
    
    @property
    def risk_reward_ratio(self) -> float:
        """Calculate preliminary risk/reward ratio."""
        if self.preliminary_stop_pct == 0:
            return 0.0
        return self.preliminary_target_pct / self.preliminary_stop_pct
    
    def __str__(self) -> str:
        """Human-readable candidate summary."""
        direction_emoji = "🟢" if self.preliminary_direction == "long" else "🔴"
        return (
            f"Candidate({self.priority_rank}): {direction_emoji} {self.symbol} "
            f"{self.pre_market_change_pct:+.1f}% [{self.scan_type.value}] "
            f"(conv: {self.conviction_score:.0%})"
        )


class MorningScanResult(BaseModel):
    """Complete result from morning scan."""
    
    scan_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When scan was performed",
    )
    market_open_time: datetime = Field(description="Expected market open time")
    
    # Candidates
    candidates: list[MorningCandidate] = Field(
        default_factory=list,
        description="Ranked list of candidates",
    )
    
    # Market context
    market_sentiment: str = Field(
        default="neutral",
        description="Overall market sentiment: bullish, bearish, neutral",
    )
    futures_change_pct: Optional[float] = Field(
        default=None,
        description="S&P futures change percentage",
    )
    vix_level: Optional[float] = Field(
        default=None,
        description="VIX level",
    )
    
    # Summary statistics
    total_scanned: int = Field(
        default=0,
        description="Total stocks scanned",
    )
    gaps_up_count: int = Field(
        default=0,
        description="Number of stocks gapping up",
    )
    gaps_down_count: int = Field(
        default=0,
        description="Number of stocks gapping down",
    )
    
    @property
    def top_candidates(self) -> list[MorningCandidate]:
        """Get top 5 candidates by priority."""
        return sorted(self.candidates, key=lambda c: c.priority_rank)[:5]
    
    def __str__(self) -> str:
        """Summary of scan results."""
        return (
            f"MorningScan: {len(self.candidates)} candidates "
            f"({self.gaps_up_count} gaps up, {self.gaps_down_count} gaps down)"
        )
