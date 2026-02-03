"""Market Analyst agent for regime detection."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent

logger = logging.getLogger(__name__)


class MarketAnalysis(BaseModel):
    """Structured output from market analysis."""

    regime: str = Field(
        description="Market regime: bull, bear, sideways, or volatile"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in regime assessment"
    )
    key_observations: list[str] = Field(
        description="Notable patterns and observations (2-4 items)"
    )
    risk_factors: list[str] = Field(
        description="Current risk concerns (1-3 items)"
    )
    summary: str = Field(
        description="2-3 sentence market assessment"
    )
    recommended_risk_posture: float = Field(
        ge=0.0,
        le=1.0,
        description="Recommended risk budget (0=defensive, 1=aggressive)",
    )


class MarketAnalystAgent(BaseAgent):
    """
    Market Analyst agent for regime detection and market assessment.

    This agent runs first in the daily cycle to set the context
    for trading agents. It analyzes technical indicators and price
    action to determine the current market regime.

    Regimes:
    - bull: Sustained uptrend, price above SMAs, RSI > 50
    - bear: Sustained downtrend, price below SMAs, RSI < 50
    - sideways: Range-bound, no clear trend
    - volatile: High volatility, large swings, uncertainty
    """

    name: ClassVar[str] = "Market Analyst"
    role: ClassVar[str] = "analyst"
    description: ClassVar[str] = "Analyzes market conditions and detects regime"
    version: ClassVar[str] = "0.1.0"

    def get_system_prompt(self) -> str:
        return """You are a professional market analyst for an automated trading system.
Your role is to analyze market data and determine the current market regime.

REGIME DEFINITIONS:
- bull: Sustained uptrend with higher highs and higher lows. RSI generally >50, price above key SMAs.
- bear: Sustained downtrend with lower highs and lower lows. RSI generally <50, price below key SMAs.
- sideways: Range-bound price action. No clear trend direction. Mixed signals.
- volatile: High volatility regime. Large price swings, uncertainty. Risk-off recommended.

ANALYSIS FRAMEWORK:
1. Trend: Is price above/below 20-day and 50-day SMAs?
2. Momentum: What does RSI indicate? Overbought (>70), oversold (<30)?
3. Volatility: Is ATR elevated? Are Bollinger Bands wide?
4. Recent Movement: What's the 5-day and 20-day price change?

OUTPUT REQUIREMENTS:
- Be concise and actionable
- Focus on what matters for trading decisions
- Quantify confidence based on signal alignment (0.0-1.0)
- Flag specific risk factors that could impact positions
- Provide 2-4 key observations and 1-3 risk factors

RISK POSTURE GUIDELINES:
- Bull regime with strong confirmation: 0.8-1.0
- Bull regime with some caution: 0.6-0.8
- Sideways regime: 0.4-0.6
- Bear regime: 0.2-0.4
- Volatile/uncertain: 0.1-0.3"""

    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """Analyze market and determine regime."""
        start_time = datetime.now()

        # Build specialized prompt for market analysis
        user_prompt = self._build_market_prompt(ctx)

        logger.info(f"Market Analyst analyzing {len(ctx.indicators)} symbols...")

        try:
            # Get structured analysis from LLM
            analysis: MarketAnalysis = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=user_prompt,
                output_schema=MarketAnalysis,
            )

            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            logger.info(
                f"Market regime: {analysis.regime} "
                f"(confidence: {analysis.confidence:.2f}, "
                f"risk posture: {analysis.recommended_risk_posture:.2f})"
            )

            # Market analyst doesn't produce trading signals, just analysis
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],  # No trading signals from analyst
                conviction=analysis.confidence,
                rationale=analysis.summary,
                risk_score=1.0 - analysis.recommended_risk_posture,
                risk_factors=analysis.risk_factors,
                model_version=self.version,
                processing_time_ms=processing_time,
                extra={
                    "regime": analysis.regime,
                    "confidence": analysis.confidence,
                    "key_observations": analysis.key_observations,
                    "recommended_risk_posture": analysis.recommended_risk_posture,
                },
            )

        except Exception as e:
            logger.error(f"Market Analyst failed: {e}")
            # Return conservative fallback
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],
                conviction=0.3,
                rationale=f"Analysis failed: {e}. Defaulting to sideways/cautious.",
                risk_score=0.7,
                risk_factors=["LLM analysis failed - using fallback"],
                model_version=self.version,
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                extra={
                    "regime": "sideways",
                    "confidence": 0.3,
                    "key_observations": ["Analysis error - using defaults"],
                    "recommended_risk_posture": 0.3,
                },
            )

    def _build_market_prompt(self, ctx: AgentContext) -> str:
        """Build specialized prompt for market analysis."""
        # Format indicators summary
        indicators_text = []
        for symbol, inds in ctx.indicators.items():
            price = inds.get("current_price", 0)
            rsi = inds.get("rsi_14", 50)
            sma20 = inds.get("sma_20", price)
            sma50 = inds.get("sma_50", price)
            atr_pct = inds.get("atr_pct", 0)
            change_5d = inds.get("change_5d", 0)
            change_20d = inds.get("change_20d", 0)
            price_vs_sma20 = inds.get("price_vs_sma20", 0)
            bb_pct = inds.get("bb_pct", 0.5)

            indicators_text.append(f"""
{symbol}:
  Price: ${price:.2f}
  RSI(14): {rsi:.1f}
  SMA20: ${sma20:.2f} (price {price_vs_sma20:+.1f}% vs SMA)
  SMA50: ${sma50:.2f}
  ATR%: {atr_pct:.2f}%
  BB%: {bb_pct:.2f} (0=lower band, 1=upper band)
  5-day change: {change_5d:+.1f}%
  20-day change: {change_20d:+.1f}%""")

        return f"""
Analyze the current market conditions based on the following data:

DATE: {ctx.current_date}

PORTFOLIO STATE:
- Cash: ${ctx.cash:,.2f}
- Portfolio Value: ${ctx.portfolio_value:,.2f}
- Current Drawdown: {ctx.current_drawdown:.1%}

TECHNICAL INDICATORS:
{"".join(indicators_text)}

Please provide your market regime assessment. Consider:
1. Are most symbols trending in the same direction?
2. What does RSI tell us about momentum?
3. Is volatility (ATR%) elevated or normal?
4. Are prices above or below key moving averages?
"""
