"""Swing Trader agent for multi-day opportunities."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent

logger = logging.getLogger(__name__)


class SwingTradeSignal(BaseModel):
    """Structured swing trade recommendation."""

    symbol: str = Field(description="Trading symbol")
    action: str = Field(description="buy, sell, or hold")
    conviction: float = Field(
        ge=0.0, le=1.0, description="Confidence in this trade"
    )
    entry_rationale: str = Field(
        description="Why this is a good entry/exit point"
    )
    stop_loss_pct: float = Field(
        ge=0.01,
        le=0.20,
        description="Stop loss as percentage below entry (e.g., 0.05 = 5%)",
    )
    take_profit_pct: float = Field(
        ge=0.02,
        le=0.50,
        description="Take profit as percentage above entry (e.g., 0.10 = 10%)",
    )
    position_size_pct: float = Field(
        ge=0.01,
        le=0.15,
        description="Recommended position size as % of portfolio (max 15%)",
    )


class SwingAnalysis(BaseModel):
    """Structured output from swing analysis."""

    signals: list[SwingTradeSignal] = Field(
        description="List of trade recommendations (0-3 signals)"
    )
    market_view: str = Field(
        description="Brief assessment of trading conditions"
    )
    overall_conviction: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in recommendations"
    )


class SwingTraderAgent(BaseAgent):
    """
    Swing Trader agent for multi-day position opportunities.

    Looks for:
    - Mean reversion from oversold/overbought
    - Support/resistance bounces
    - Trend continuation after pullbacks

    Typical holding period: 3-10 trading days
    """

    name: ClassVar[str] = "Swing Trader"
    role: ClassVar[str] = "trader"
    description: ClassVar[str] = "Multi-day swing trading opportunities"
    version: ClassVar[str] = "0.1.0"

    def get_system_prompt(self) -> str:
        return """You are a swing trader agent looking for multi-day opportunities.
Your typical holding period is 3-10 trading days.

TRADING STYLE:
- Mean reversion from oversold (RSI < 30) or overbought (RSI > 70) conditions
- Bounces from support levels (near lower Bollinger Band, key SMAs)
- Trend continuation after healthy pullbacks (price pulling back to 20 SMA in uptrend)

BUY SIGNALS TO LOOK FOR:
- RSI < 35 with price near lower Bollinger Band (oversold bounce)
- Price pulling back to 20-day SMA in an uptrend (trend continuation)
- Price > SMA50 but temporarily < SMA20 (buy the dip)
- Volume spike on recovery after selloff

SELL SIGNALS TO LOOK FOR:
- RSI > 70 with price near upper Bollinger Band (overbought)
- Price breaking below SMA50 after being above (trend break)
- Large profit (>15%) - consider taking partial profits
- Stop loss hit

POSITION SIZING:
- High conviction setups: 8-12% of portfolio
- Medium conviction: 4-8% of portfolio
- Low conviction or volatile market: 2-4% of portfolio
- Never recommend more than 15% per position

RISK MANAGEMENT:
- Stop loss: 3-7% below entry for longs (wider for volatile stocks)
- Take profit: Target 2:1 or better reward:risk ratio
- Consider current drawdown - size down in drawdown

OUTPUT RULES:
- Only recommend trades with clear technical setup
- Maximum 3 signals per analysis
- If no compelling opportunity, return empty signals list
- Be conservative in volatile/bear regimes
- Include specific reasoning for each trade"""

    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """Analyze for swing trading opportunities."""
        start_time = datetime.now()

        # Build specialized prompt
        user_prompt = self._build_swing_prompt(ctx)

        logger.info(
            f"Swing Trader analyzing opportunities "
            f"(regime: {ctx.regime}, risk budget: {ctx.risk_budget:.1%})..."
        )

        try:
            # Get structured analysis from LLM
            analysis: SwingAnalysis = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=user_prompt,
                output_schema=SwingAnalysis,
            )

            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            # Convert signals to proposal format
            signals = []
            for sig in analysis.signals:
                if sig.action == "hold":
                    continue

                # Calculate actual amounts based on portfolio
                position_value = ctx.portfolio_value * Decimal(
                    str(sig.position_size_pct)
                )

                # Adjust for risk budget
                adjusted_value = position_value * Decimal(str(ctx.risk_budget))

                if sig.action == "buy":
                    # Cap at available cash
                    amount = min(adjusted_value, ctx.cash * Decimal("0.95"))
                    if amount < Decimal("50"):  # Min trade size
                        logger.debug(f"Skipping {sig.symbol} buy - amount too small")
                        continue

                    signals.append(
                        {
                            "symbol": sig.symbol,
                            "action": "buy",
                            "amount": float(amount),
                            "conviction": sig.conviction,
                            "reason": sig.entry_rationale,
                            "stop_loss_pct": sig.stop_loss_pct,
                            "take_profit_pct": sig.take_profit_pct,
                        }
                    )

                elif sig.action == "sell":
                    # Get current position
                    shares = ctx.positions.get(sig.symbol, Decimal(0))
                    if shares <= 0:
                        logger.debug(f"Skipping {sig.symbol} sell - no position")
                        continue

                    signals.append(
                        {
                            "symbol": sig.symbol,
                            "action": "sell",
                            "quantity": float(shares),
                            "conviction": sig.conviction,
                            "reason": sig.entry_rationale,
                        }
                    )

            logger.info(
                f"Swing Trader found {len(signals)} opportunities "
                f"(conviction: {analysis.overall_conviction:.2f})"
            )

            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=signals,
                conviction=analysis.overall_conviction,
                rationale=analysis.market_view,
                risk_score=0.5,  # Default medium risk
                risk_factors=[],
                model_version=self.version,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            logger.error(f"Swing Trader failed: {e}")
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],
                conviction=0.0,
                rationale=f"Analysis failed: {e}",
                risk_score=0.8,
                risk_factors=["LLM analysis failed"],
                model_version=self.version,
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )

    def _build_swing_prompt(self, ctx: AgentContext) -> str:
        """Build specialized prompt for swing trading analysis."""
        # Format current positions
        positions_text = []
        for symbol, shares in ctx.positions.items():
            price = ctx.prices.get(symbol, Decimal(0))
            value = shares * price
            pct_of_portfolio = (
                (value / ctx.portfolio_value * 100) if ctx.portfolio_value else 0
            )
            positions_text.append(
                f"  {symbol}: {shares:.4f} shares = ${value:,.2f} ({pct_of_portfolio:.1f}% of portfolio)"
            )

        # Format indicators for analysis
        indicators_text = []
        for symbol, inds in ctx.indicators.items():
            price = inds.get("current_price", 0)
            rsi = inds.get("rsi_14", 50)
            bb_pct = inds.get("bb_pct", 0.5)
            price_vs_sma20 = inds.get("price_vs_sma20", 0)
            price_vs_sma50 = inds.get("price_vs_sma50", 0)
            atr_pct = inds.get("atr_pct", 0)
            change_5d = inds.get("change_5d", 0)
            macd_hist = inds.get("macd_histogram", 0)

            # Determine if we have a position
            has_position = symbol in ctx.positions
            position_note = " [HOLDING]" if has_position else ""

            indicators_text.append(f"""
{symbol}{position_note}:
  Price: ${price:.2f}
  RSI(14): {rsi:.1f} {"[OVERSOLD]" if rsi < 35 else "[OVERBOUGHT]" if rsi > 70 else ""}
  BB%: {bb_pct:.2f} (0=lower band, 1=upper band)
  Price vs SMA20: {price_vs_sma20:+.1f}%
  Price vs SMA50: {price_vs_sma50:+.1f}%
  ATR%: {atr_pct:.2f}% (volatility)
  5-day change: {change_5d:+.1f}%
  MACD Histogram: {macd_hist:.3f}""")

        positions_str = (
            "\n".join(positions_text) if positions_text else "  (no positions)"
        )

        return f"""
DATE: {ctx.current_date}
MARKET REGIME: {ctx.regime or 'unknown'} (confidence: {ctx.regime_confidence:.2f})

PORTFOLIO STATE:
- Cash: ${ctx.cash:,.2f}
- Portfolio Value: ${ctx.portfolio_value:,.2f}
- Current Drawdown: {ctx.current_drawdown:.1%}
- Risk Budget: {ctx.risk_budget:.1%}

CURRENT POSITIONS:
{positions_str}

TECHNICAL ANALYSIS:
{"".join(indicators_text)}

Based on this data, identify swing trading opportunities:
1. Look for oversold bounces (RSI < 35, BB% < 0.2)
2. Look for trend pullbacks (price near SMA20 in uptrend)
3. Consider selling overbought positions (RSI > 70, BB% > 0.8)
4. Factor in the market regime and adjust conviction accordingly

Return up to 3 signals with clear rationale. If no good setups exist, return an empty signals list.
"""
