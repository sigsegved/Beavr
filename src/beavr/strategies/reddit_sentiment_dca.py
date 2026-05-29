"""Reddit Sentiment DCA strategy implementation."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Optional, Type

from pydantic import BaseModel

from beavr.models.config import RedditSentimentDCAParams
from beavr.models.signal import Signal
from beavr.reddit.models import MemeStockTrend
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.registry import register_strategy

logger = logging.getLogger(__name__)


@register_strategy("reddit_sentiment_dca")
class RedditSentimentDCAStrategy(BaseStrategy):
    """DCA strategy that adjusts allocations based on Reddit sentiment.

    Base behavior: standard monthly DCA on the first trading day.
    Adjustment: When a symbol is trending on Reddit with strong sentiment,
    the allocation is boosted (bullish) or reduced (bearish).

    This strategy requires Reddit scan data to be loaded via
    `set_reddit_trends()` before evaluation. Without Reddit data,
    it falls back to standard DCA behavior.

    Logic:
        On first trading day of month:
            For each symbol:
                base_amount = monthly_budget * base_buy_pct / num_symbols
                if symbol has bullish Reddit sentiment:
                    amount = base_amount * (1 + bullish_boost)
                elif symbol has bearish Reddit sentiment:
                    amount = base_amount * (1 - bearish_reduction)
                else:
                    amount = base_amount
                Buy $amount of symbol

        On month-end fallback:
            Deploy any remaining budget equally across symbols
    """

    name: ClassVar[str] = "Reddit Sentiment DCA"
    description: ClassVar[str] = "DCA with Reddit meme stock sentiment adjustments"
    version: ClassVar[str] = "1.0.0"
    param_model: ClassVar[Type[BaseModel]] = RedditSentimentDCAParams

    def __init__(self, params: RedditSentimentDCAParams) -> None:
        self.params = params
        self._reddit_trends: dict[str, MemeStockTrend] = {}
        self._period_dip_buys: int = 0

    @property
    def symbols(self) -> list[str]:
        return list(self.params.symbols)

    def set_reddit_trends(self, trends: list[MemeStockTrend]) -> None:
        """Load Reddit trend data for strategy evaluation.

        Args:
            trends: List of meme stock trends from a Reddit scan
        """
        self._reddit_trends = {t.ticker: t for t in trends}

    def _get_sentiment_for_symbol(self, symbol: str) -> Optional[MemeStockTrend]:
        """Get Reddit trend data for a symbol if it meets thresholds.

        Args:
            symbol: Stock symbol to look up

        Returns:
            Trend data if the symbol has enough mentions, None otherwise
        """
        trend = self._reddit_trends.get(symbol)
        if trend is None:
            return None
        if trend.mention_count < self.params.min_mentions:
            return None
        return trend

    def _compute_buy_amount(self, symbol: str, base_amount: Decimal) -> tuple[Decimal, str]:
        """Compute the buy amount for a symbol, adjusted by Reddit sentiment.

        Args:
            symbol: Stock symbol
            base_amount: Base DCA amount before adjustment

        Returns:
            Tuple of (adjusted_amount, reason_string)
        """
        trend = self._get_sentiment_for_symbol(symbol)

        if trend is None:
            return base_amount, "scheduled DCA (no Reddit signal)"

        sentiment = trend.avg_sentiment

        if abs(sentiment) < self.params.sentiment_threshold:
            return base_amount, f"scheduled DCA (Reddit neutral, sentiment={sentiment:.2f})"

        if sentiment > 0:
            boost = Decimal(str(1 + self.params.bullish_boost))
            adjusted = base_amount * boost
            return adjusted, (
                f"DCA boosted by Reddit bullish sentiment "
                f"(sentiment={sentiment:.2f}, mentions={trend.mention_count})"
            )
        else:
            reduction = Decimal(str(1 - self.params.bearish_reduction))
            adjusted = base_amount * reduction
            return adjusted, (
                f"DCA reduced by Reddit bearish sentiment "
                f"(sentiment={sentiment:.2f}, mentions={trend.mention_count})"
            )

    def on_period_start(self, ctx: StrategyContext) -> None:  # noqa: ARG002
        self._period_dip_buys = 0

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        signals: list[Signal] = []

        # Base buy on first trading day of month
        if ctx.is_first_trading_day_of_month:
            signals.extend(self._base_buy_signals(ctx))

        # Fallback: deploy remaining budget near month-end
        if ctx.days_to_month_end <= self.params.fallback_days and ctx.remaining_budget > self.params.min_buy_amount:
            signals.extend(self._fallback_buy_signals(ctx))

        return signals

    def _base_buy_signals(self, ctx: StrategyContext) -> list[Signal]:
        """Generate base DCA buy signals, adjusted by Reddit sentiment."""
        num_symbols = len(self.params.symbols)
        base_per_symbol = (self.params.monthly_budget * Decimal(str(self.params.base_buy_pct))) / num_symbols

        signals: list[Signal] = []
        remaining_cash = ctx.cash

        for symbol in self.params.symbols:
            amount, reason = self._compute_buy_amount(symbol, base_per_symbol)

            if amount < self.params.min_buy_amount:
                continue
            if remaining_cash < amount:
                amount = remaining_cash
            if amount < self.params.min_buy_amount:
                continue

            signals.append(Signal(
                symbol=symbol,
                action="buy",
                amount=amount,
                reason=reason,
                timestamp=datetime.combine(ctx.current_date, datetime.min.time()),
                confidence=self._compute_confidence(symbol),
            ))
            remaining_cash -= amount

        return signals

    def _fallback_buy_signals(self, ctx: StrategyContext) -> list[Signal]:
        """Deploy remaining budget near month-end."""
        remaining = ctx.remaining_budget
        if remaining < self.params.min_buy_amount:
            return []

        num_symbols = len(self.params.symbols)
        per_symbol = remaining / num_symbols

        signals: list[Signal] = []
        remaining_cash = ctx.cash

        for symbol in self.params.symbols:
            amount = min(per_symbol, remaining_cash)
            if amount < self.params.min_buy_amount:
                continue

            signals.append(Signal(
                symbol=symbol,
                action="buy",
                amount=amount,
                reason="month-end fallback DCA",
                timestamp=datetime.combine(ctx.current_date, datetime.min.time()),
            ))
            remaining_cash -= amount

        return signals

    def _compute_confidence(self, symbol: str) -> float:
        """Compute signal confidence based on Reddit data quality."""
        trend = self._get_sentiment_for_symbol(symbol)
        if trend is None:
            return 0.5  # Default confidence without Reddit data

        # More mentions = higher confidence, capped at 1.0
        mention_factor = min(trend.mention_count / 50.0, 1.0)
        # Stronger sentiment = higher confidence
        sentiment_factor = min(abs(trend.avg_sentiment) * 2, 1.0)

        return min(0.5 + (mention_factor + sentiment_factor) / 4, 1.0)
