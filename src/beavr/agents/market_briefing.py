"""Market Briefing Agent — generates on-demand market outlook."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent

logger = logging.getLogger(__name__)

SECTOR_ETFS = ["XLE", "XLK", "XLF", "XLV", "XLI", "XLU", "XLP", "XLY", "XLC", "XLRE"]
INDEX_SYMBOLS = ["SPY", "QQQ"]


class IndexSnapshot(BaseModel):
    """Snapshot of a major index."""

    symbol: str
    price: float
    change_pct: float
    rsi: float
    above_sma20: bool
    above_sma50: bool
    signal: str = Field(description="bullish, bearish, or neutral")


class SectorPerformance(BaseModel):
    """Performance summary for a sector."""

    name: str
    etf: str
    change_pct: float


class MarketBrief(BaseModel):
    """Structured market briefing."""

    generated_at: datetime = Field(default_factory=datetime.now)
    regime: str = Field(description="bull, bear, sideways, or volatile")
    regime_confidence: float = Field(ge=0.0, le=1.0)
    risk_posture: str = Field(description="aggressive, moderate, cautious, or defensive")
    indices: list[IndexSnapshot] = Field(default_factory=list, description="Key index data")
    leading_sectors: list[str] = Field(default_factory=list, description="Top performing sectors")
    lagging_sectors: list[str] = Field(default_factory=list, description="Worst performing sectors")
    rotation_theme: str = Field(default="", description="1-sentence sector rotation summary")
    portfolio_summary: str = Field(default="", description="2-3 sentence portfolio context")
    portfolio_warnings: list[str] = Field(default_factory=list, description="Specific portfolio risks")
    key_takeaways: list[str] = Field(default_factory=list, description="3-5 actionable bullet points")
    watch_list: list[str] = Field(default_factory=list, description="Symbols to monitor")
    raw_summary: str = Field(default="", description="Full narrative summary (3-5 paragraphs)")


class MarketBriefingAgent(BaseAgent):
    """Generates on-demand market briefing with outlook."""

    name: ClassVar[str] = "Market Briefing"
    role: ClassVar[str] = "analyst"
    description: ClassVar[str] = "On-demand market outlook and portfolio briefing"
    version: ClassVar[str] = "1.0.0"

    def get_system_prompt(self) -> str:
        return """You are a senior market strategist providing a comprehensive briefing.

Your briefing should cover:
1. MARKET REGIME: Classify as bull/bear/sideways/volatile with confidence
2. INDEX ANALYSIS: SPY/QQQ trend, momentum, key levels
3. SECTOR ROTATION: Which sectors are leading/lagging and why
4. PORTFOLIO CONTEXT: How current holdings relate to market conditions
5. ACTIONABLE OUTLOOK: 3-5 specific, actionable recommendations

Be direct and decisive. This is a trading desk briefing, not academic analysis.
Focus on what matters for trading decisions TODAY and THIS WEEK."""

    def generate_brief(self, ctx: AgentContext, portfolio_info: str = "") -> MarketBrief:
        """Generate a market brief from current context."""
        user_prompt = self._build_brief_prompt(ctx, portfolio_info)

        brief: MarketBrief = self.llm.reason(
            system_prompt=self.get_system_prompt(),
            user_prompt=user_prompt,
            output_schema=MarketBrief,
        )
        return brief

    def _build_brief_prompt(self, ctx: AgentContext, portfolio_info: str) -> str:
        index_text = []
        sector_text = []

        for symbol, inds in ctx.indicators.items():
            if symbol in ("SPY", "QQQ"):
                index_text.append(
                    f"{symbol}: ${inds.get('current_price', 0):.2f}, "
                    f"RSI={inds.get('rsi_14', 0):.1f}, "
                    f"vs SMA20={inds.get('price_vs_sma20', 0):+.1f}%, "
                    f"vs SMA50={inds.get('price_vs_sma50', 0):+.1f}%, "
                    f"5d={inds.get('change_5d', 0):+.1f}%"
                )
            elif symbol.startswith("XL") or symbol == "XLRE":
                sector_text.append(
                    f"{symbol}: 5d={inds.get('change_5d', 0):+.1f}%, "
                    f"RSI={inds.get('rsi_14', 0):.1f}"
                )

        return f"""Generate a market briefing for {ctx.current_date}.

INDEX DATA:
{chr(10).join(index_text) if index_text else "No index data available"}

SECTOR ETFs:
{chr(10).join(sector_text) if sector_text else "No sector data available"}

PORTFOLIO:
{portfolio_info or "No portfolio data available"}

Cash: ${ctx.cash:,.2f}
Portfolio Value: ${ctx.portfolio_value:,.2f}
Drawdown: {ctx.current_drawdown:.1%}
"""

    def analyze(self, ctx: AgentContext) -> AgentProposal:  # noqa: ARG002
        """Required by BaseAgent but briefing uses generate_brief() instead."""
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=[],
            conviction=0.0,
            rationale="Use generate_brief() for market briefing",
            risk_score=0.0,
            risk_factors=[],
            model_version=self.version,
        )
