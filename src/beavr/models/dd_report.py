"""Due Diligence report models for AI Investor v2."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class DDRecommendation(str, Enum):
    """DD Agent recommendation verdict."""
    
    APPROVE = "approve"  # Proceed with trade
    REJECT = "reject"  # Do not trade
    CONDITIONAL = "conditional"  # Proceed only if conditions met


class RecommendedTradeType(str, Enum):
    """Trade type classification by DD Agent."""
    
    DAY_TRADE = "day_trade"        # Power hour play
    SWING_SHORT = "swing_short"    # 1-2 weeks
    SWING_MEDIUM = "swing_medium"  # 1-3 months
    SWING_LONG = "swing_long"      # 3-12 months


class DayTradePlan(BaseModel):
    """Specific plan for day trade execution during power hour."""
    
    entry_window_start: str = Field(
        default="09:35",
        description="Earliest entry time (ET) - after opening range",
    )
    entry_window_end: str = Field(
        default="09:45",
        description="Latest entry time (ET) - optimal window",
    )
    exit_deadline: str = Field(
        default="10:30",
        description="Must exit by this time (ET) - end of power hour",
    )
    opening_range_confirmation: str = Field(
        description="What to look for in opening range to confirm entry",
    )
    scalp_target_pct: float = Field(
        default=1.5,
        description="Quick profit target percentage",
    )
    full_target_pct: float = Field(
        default=2.5,
        description="Full profit target percentage",
    )
    stop_pct: float = Field(
        default=1.0,
        description="Stop loss percentage",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional execution notes",
    )


class SwingTradePlan(BaseModel):
    """Specific plan for swing trade execution."""
    
    entry_strategy: str = Field(
        description="How to enter (limit at support, breakout confirm, etc.)",
    )
    scaling_plan: Optional[str] = Field(
        default=None,
        description="Plan for scaling into/out of position",
    )
    key_dates_to_monitor: list[str] = Field(
        default_factory=list,
        description="Important dates (earnings, ex-div, etc.)",
    )
    interim_targets: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Intermediate targets for partial profit taking",
    )
    trailing_stop_strategy: Optional[str] = Field(
        default=None,
        description="How to trail stop as position moves in favor",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes for swing management",
    )


class DueDiligenceReport(BaseModel):
    """
    Comprehensive DD report for a trading candidate.
    
    The DD Agent produces this report after deep analysis of a
    candidate stock. No trade executes without DD approval.
    
    Reports are generated OVERNIGHT (8 PM - 6 AM ET) to allow
    thorough research without time pressure. Reports are persisted
    in both JSON and Markdown formats for user consumption.
    """
    
    # Identification
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique report identifier",
    )
    thesis_id: Optional[str] = Field(
        default=None,
        description="Associated thesis ID (if exists)",
    )
    symbol: str = Field(description="Trading symbol analyzed")
    company_name: Optional[str] = Field(
        default=None,
        description="Full company name",
    )
    sector: Optional[str] = Field(
        default=None,
        description="Company sector",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When DD was performed",
    )
    
    # Trade Type Classification (NEW in v2)
    recommended_trade_type: RecommendedTradeType = Field(
        description="DD Agent's recommended trade type",
    )
    trade_type_rationale: str = Field(
        description="Why this trade type was selected",
    )
    
    # Verdict
    recommendation: DDRecommendation = Field(
        description="Final recommendation: approve, reject, or conditional",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the recommendation",
    )
    
    # Executive Summary (NEW - quick read)
    executive_summary: str = Field(
        description="2-3 sentence summary for quick reading",
    )
    
    # Analysis Sections
    fundamental_summary: str = Field(
        description="Detailed fundamental analysis",
    )
    technical_summary: str = Field(
        description="Detailed technical analysis",
    )
    catalyst_assessment: str = Field(
        description="Deep dive on the catalyst and historical patterns",
    )
    competitive_landscape: Optional[str] = Field(
        default=None,
        description="How company compares to peers",
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="Key risks identified during analysis",
    )
    
    # Scenario Analysis (NEW)
    bull_case: Optional[str] = Field(
        default=None,
        description="Best case scenario",
    )
    bear_case: Optional[str] = Field(
        default=None,
        description="Worst case scenario",
    )
    base_case: Optional[str] = Field(
        default=None,
        description="Most likely outcome",
    )
    
    # Company Data (captured at DD time)
    market_cap: Optional[Decimal] = Field(
        default=None,
        description="Market capitalization at DD time",
    )
    pe_ratio: Optional[float] = Field(
        default=None,
        description="Price to earnings ratio",
    )
    revenue_growth: Optional[float] = Field(
        default=None,
        description="Year-over-year revenue growth %",
    )
    institutional_ownership: Optional[float] = Field(
        default=None,
        description="Institutional ownership percentage",
    )
    
    # Adjusted Targets (DD may modify thesis targets)
    recommended_entry: Decimal = Field(
        description="Recommended entry price",
    )
    recommended_target: Decimal = Field(
        description="Recommended profit target",
    )
    recommended_stop: Decimal = Field(
        description="Recommended stop loss",
    )
    recommended_position_size_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Recommended position size as fraction of portfolio",
    )
    
    # Trade-Type Specific Plans (NEW)
    day_trade_plan: Optional[DayTradePlan] = Field(
        default=None,
        description="Specific plan for day trade execution",
    )
    swing_trade_plan: Optional[SwingTradePlan] = Field(
        default=None,
        description="Specific plan for swing trade execution",
    )
    
    # Rationale
    approval_rationale: Optional[str] = Field(
        default=None,
        description="Why the trade is approved (if approve)",
    )
    rejection_rationale: Optional[str] = Field(
        default=None,
        description="Why the trade is rejected (if reject)",
    )
    conditions: Optional[list[str]] = Field(
        default=None,
        description="Conditions that must be met (if conditional)",
    )
    
    # Processing metadata
    research_time_minutes: int = Field(
        default=0,
        description="How long the DD research took",
    )
    data_sources_used: list[str] = Field(
        default_factory=list,
        description="Data sources consulted during DD",
    )
    processing_time_ms: float = Field(
        default=0.0,
        description="LLM processing time",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="LLM model used for analysis",
    )
    
    @field_validator(
        "recommended_entry", "recommended_target", "recommended_stop", "market_cap",
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
    def is_approved(self) -> bool:
        """Check if recommendation is approve or conditional."""
        return self.recommendation in (DDRecommendation.APPROVE, DDRecommendation.CONDITIONAL)
    
    @property
    def is_day_trade(self) -> bool:
        """Check if this is classified as a day trade."""
        return self.recommended_trade_type == RecommendedTradeType.DAY_TRADE
    
    @property
    def risk_reward_ratio(self) -> float:
        """Calculate recommended risk/reward ratio."""
        reward = float(self.recommended_target - self.recommended_entry)
        risk = float(self.recommended_entry - self.recommended_stop)
        if risk <= 0:
            return 0.0
        return reward / risk
    
    @property  
    def target_pct(self) -> float:
        """Target profit as percentage from entry."""
        return float((self.recommended_target - self.recommended_entry) / self.recommended_entry) * 100
    
    @property
    def stop_pct(self) -> float:
        """Stop loss as percentage from entry."""
        return float((self.recommended_entry - self.recommended_stop) / self.recommended_entry) * 100
    
    def save(self, base_dir: str | Path = "logs/dd_reports") -> tuple[Path, Path]:
        """
        Save report as both JSON and Markdown files.
        
        Args:
            base_dir: Base directory for reports
            
        Returns:
            Tuple of (json_path, markdown_path)
        """
        base_dir = Path(base_dir)
        date_str = self.timestamp.strftime("%Y-%m-%d")
        time_str = self.timestamp.strftime("%H%M%S")
        
        # Create date-based directory
        report_dir = base_dir / date_str
        report_dir.mkdir(parents=True, exist_ok=True)
        
        # Create latest directory
        latest_dir = base_dir / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        
        filename_base = f"{self.symbol}_{date_str.replace('-', '')}_{time_str}"
        
        # Save JSON
        json_path = report_dir / f"{filename_base}.json"
        json_data = self.model_dump(mode="json")
        json_path.write_text(json.dumps(json_data, indent=2, default=str))
        
        # Save latest JSON
        latest_json = latest_dir / f"{self.symbol}.json"
        latest_json.write_text(json.dumps(json_data, indent=2, default=str))
        
        # Save Markdown
        md_path = report_dir / f"{filename_base}.md"
        md_content = self.to_markdown()
        md_path.write_text(md_content)
        
        # Save latest Markdown
        latest_md = latest_dir / f"{self.symbol}.md"
        latest_md.write_text(md_content)
        
        return json_path, md_path
    
    def to_markdown(self) -> str:
        """Generate human-readable markdown report."""
        emoji = "✅" if self.recommendation == DDRecommendation.APPROVE else (
            "⚠️" if self.recommendation == DDRecommendation.CONDITIONAL else "❌"
        )
        
        trade_type_display = {
            RecommendedTradeType.DAY_TRADE: "Day Trade (Power Hour)",
            RecommendedTradeType.SWING_SHORT: "Swing (Short-Term, 1-2 weeks)",
            RecommendedTradeType.SWING_MEDIUM: "Swing (Medium-Term, 1-3 months)",
            RecommendedTradeType.SWING_LONG: "Swing (Long-Term, 3-12 months)",
        }
        
        md = f"""# Due Diligence Report: {self.symbol}

**Generated:** {self.timestamp.strftime("%B %d, %Y %I:%M %p")} ET  
**Report ID:** {self.id}  
{"**Thesis ID:** " + self.thesis_id if self.thesis_id else ""}
**Recommendation:** {emoji} {self.recommendation.value.upper()}  
**Confidence:** {self.confidence:.0%}  
**Trade Type:** {trade_type_display.get(self.recommended_trade_type, self.recommended_trade_type.value)}

---

## Executive Summary

{self.executive_summary}

## Trade Plan

| Parameter | Value |
|-----------|-------|
| Entry | ${self.recommended_entry:,.2f} |
| Target | ${self.recommended_target:,.2f} ({self.target_pct:+.1f}%) |
| Stop | ${self.recommended_stop:,.2f} ({self.stop_pct:-.1f}%) |
| Risk/Reward | {self.risk_reward_ratio:.2f}:1 |
| Position Size | {self.recommended_position_size_pct:.0%} of portfolio |

"""
        
        # Add day trade plan if applicable
        if self.day_trade_plan:
            md += f"""### Day Trade Execution Plan

- **Entry Window:** {self.day_trade_plan.entry_window_start} - {self.day_trade_plan.entry_window_end} ET
- **Exit Deadline:** {self.day_trade_plan.exit_deadline} ET (mandatory)
- **Opening Range Confirmation:** {self.day_trade_plan.opening_range_confirmation}
- **Scalp Target:** {self.day_trade_plan.scalp_target_pct:.1f}%
- **Full Target:** {self.day_trade_plan.full_target_pct:.1f}%
- **Stop Loss:** {self.day_trade_plan.stop_pct:.1f}%

"""
            if self.day_trade_plan.notes:
                md += f"> **Notes:** {self.day_trade_plan.notes}\n\n"
        
        # Add swing trade plan if applicable
        if self.swing_trade_plan:
            md += f"""### Swing Trade Execution Plan

- **Entry Strategy:** {self.swing_trade_plan.entry_strategy}
"""
            if self.swing_trade_plan.scaling_plan:
                md += f"- **Scaling Plan:** {self.swing_trade_plan.scaling_plan}\n"
            if self.swing_trade_plan.key_dates_to_monitor:
                md += f"- **Key Dates:** {', '.join(self.swing_trade_plan.key_dates_to_monitor)}\n"
            if self.swing_trade_plan.trailing_stop_strategy:
                md += f"- **Trailing Stop:** {self.swing_trade_plan.trailing_stop_strategy}\n"
            md += "\n"
        
        md += f"""## Trade Type Rationale

{self.trade_type_rationale}

## Fundamental Analysis

{self.fundamental_summary}

"""
        
        if self.company_name or self.sector or self.market_cap:
            md += "### Company Data\n\n"
            if self.company_name:
                md += f"- **Company:** {self.company_name}\n"
            if self.sector:
                md += f"- **Sector:** {self.sector}\n"
            if self.market_cap:
                md += f"- **Market Cap:** ${self.market_cap:,.0f}\n"
            if self.pe_ratio:
                md += f"- **P/E Ratio:** {self.pe_ratio:.1f}\n"
            if self.revenue_growth:
                md += f"- **Revenue Growth:** {self.revenue_growth:+.1f}%\n"
            if self.institutional_ownership:
                md += f"- **Institutional Ownership:** {self.institutional_ownership:.1f}%\n"
            md += "\n"
        
        md += f"""## Technical Analysis

{self.technical_summary}

## Catalyst Assessment

{self.catalyst_assessment}

"""
        
        if self.competitive_landscape:
            md += f"""## Competitive Landscape

{self.competitive_landscape}

"""
        
        md += "## Risk Factors\n\n"
        for i, risk in enumerate(self.risk_factors, 1):
            md += f"{i}. {risk}\n"
        md += "\n"
        
        if self.bull_case or self.bear_case or self.base_case:
            md += "## Scenario Analysis\n\n"
            if self.bull_case:
                md += f"**Bull Case:** {self.bull_case}\n\n"
            if self.base_case:
                md += f"**Base Case:** {self.base_case}\n\n"
            if self.bear_case:
                md += f"**Bear Case:** {self.bear_case}\n\n"
        
        if self.approval_rationale:
            md += f"""## Approval Rationale

{self.approval_rationale}

"""
        
        if self.rejection_rationale:
            md += f"""## Rejection Rationale

{self.rejection_rationale}

"""
        
        if self.conditions:
            md += "## Conditions for Approval\n\n"
            for condition in self.conditions:
                md += f"- {condition}\n"
            md += "\n"
        
        md += f"""---

*Research Time: {self.research_time_minutes} minutes*  
*LLM Model: {self.llm_model or 'Not specified'}*  
*Sources: {', '.join(self.data_sources_used) if self.data_sources_used else 'Not specified'}*
"""
        
        return md
    
    def __str__(self) -> str:
        """Human-readable DD summary."""
        emoji = "✅" if self.recommendation == DDRecommendation.APPROVE else (
            "⚠️" if self.recommendation == DDRecommendation.CONDITIONAL else "❌"
        )
        return (
            f"DD({self.id}): {emoji} {self.recommendation.value.upper()} {self.symbol} "
            f"[{self.recommended_trade_type.value}] confidence: {self.confidence:.0%}"
        )


class DDSummary(BaseModel):
    """Lightweight DD summary for lists and displays."""
    
    id: str = Field(description="Report ID")
    symbol: str = Field(description="Trading symbol")
    recommendation: DDRecommendation = Field(description="Verdict")
    recommended_trade_type: RecommendedTradeType = Field(description="Trade classification")
    confidence: float = Field(description="Confidence level")
    timestamp: datetime = Field(description="When DD was performed")
    thesis_id: Optional[str] = Field(description="Associated thesis ID")
    risk_reward_ratio: float = Field(description="Risk/reward ratio")
    
    model_config = {"frozen": True}
