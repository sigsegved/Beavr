"""Tests for Reddit Sentiment DCA strategy."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from beavr.models.config import RedditSentimentDCAParams
from beavr.reddit.models import MemeStockTrend
from beavr.strategies.context import StrategyContext
from beavr.strategies.reddit_sentiment_dca import RedditSentimentDCAStrategy


class TestRedditSentimentDCAStrategy:
    """Tests for RedditSentimentDCAStrategy."""

    @pytest.fixture
    def sample_bars(self) -> dict[str, pd.DataFrame]:
        dates = pd.date_range("2024-01-01", periods=30)
        df = pd.DataFrame(
            {
                "open": [450.0] * 30,
                "high": [455.0] * 30,
                "low": [445.0] * 30,
                "close": [450.0] * 30,
                "volume": [1000000] * 30,
            },
            index=dates,
        )
        return {"SPY": df, "QQQ": df.copy()}

    def create_context(
        self,
        sample_bars: dict[str, pd.DataFrame],
        current_date: date,
        cash: Decimal = Decimal("10000"),
        is_first: bool = False,
        days_to_end: int = 20,
        period_spent: Decimal = Decimal("0"),
    ) -> StrategyContext:
        return StrategyContext(
            current_date=current_date,
            prices={"SPY": Decimal("450"), "QQQ": Decimal("350")},
            bars=sample_bars,
            cash=cash,
            positions={},
            period_budget=Decimal("1000"),
            period_spent=period_spent,
            day_of_month=current_date.day,
            day_of_week=current_date.weekday(),
            days_to_month_end=days_to_end,
            is_first_trading_day_of_month=is_first,
            is_last_trading_day_of_month=days_to_end == 0,
        )

    def test_strategy_metadata(self) -> None:
        params = RedditSentimentDCAParams()
        strategy = RedditSentimentDCAStrategy(params)
        assert strategy.name == "Reddit Sentiment DCA"
        assert strategy.version == "1.0.0"
        assert "reddit" in strategy.description.lower()

    def test_symbols_property(self) -> None:
        params = RedditSentimentDCAParams(symbols=["SPY", "QQQ"])
        strategy = RedditSentimentDCAStrategy(params)
        assert strategy.symbols == ["SPY", "QQQ"]

    def test_base_dca_without_reddit_data(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Without Reddit data, should do standard DCA."""
        params = RedditSentimentDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
        )
        strategy = RedditSentimentDCAStrategy(params)

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].symbol == "SPY"
        assert signals[0].amount == Decimal("500")
        assert "no Reddit signal" in signals[0].reason

    def test_bullish_sentiment_boosts_allocation(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
            bullish_boost=0.25,
            sentiment_threshold=0.3,
            min_mentions=5,
        )
        strategy = RedditSentimentDCAStrategy(params)

        # Load bullish Reddit data
        strategy.set_reddit_trends([
            MemeStockTrend(
                ticker="SPY",
                mention_count=20,
                avg_sentiment=0.6,
                total_post_score=1000,
            ),
        ])

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        # Base = 500, boosted by 25% = 625
        assert signals[0].amount == Decimal("625.00")
        assert "bullish" in signals[0].reason.lower()

    def test_bearish_sentiment_reduces_allocation(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
            bearish_reduction=0.50,
            sentiment_threshold=0.3,
            min_mentions=5,
        )
        strategy = RedditSentimentDCAStrategy(params)

        # Load bearish Reddit data
        strategy.set_reddit_trends([
            MemeStockTrend(
                ticker="SPY",
                mention_count=20,
                avg_sentiment=-0.5,
                total_post_score=500,
            ),
        ])

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        # Base = 500, reduced by 50% = 250
        assert signals[0].amount == Decimal("250.00")
        assert "bearish" in signals[0].reason.lower()

    def test_neutral_sentiment_no_adjustment(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
            sentiment_threshold=0.3,
            min_mentions=5,
        )
        strategy = RedditSentimentDCAStrategy(params)

        strategy.set_reddit_trends([
            MemeStockTrend(
                ticker="SPY",
                mention_count=20,
                avg_sentiment=0.1,  # Below threshold
            ),
        ])

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].amount == Decimal("500")
        assert "neutral" in signals[0].reason.lower()

    def test_low_mentions_ignored(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
            min_mentions=10,  # High threshold
        )
        strategy = RedditSentimentDCAStrategy(params)

        strategy.set_reddit_trends([
            MemeStockTrend(
                ticker="SPY",
                mention_count=3,  # Below threshold
                avg_sentiment=0.8,
            ),
        ])

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].amount == Decimal("500")  # No boost
        assert "no Reddit signal" in signals[0].reason

    def test_no_buy_on_non_first_day(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(symbols=["SPY"])
        strategy = RedditSentimentDCAStrategy(params)

        ctx = self.create_context(
            sample_bars, date(2024, 1, 15), is_first=False, days_to_end=16
        )
        signals = strategy.evaluate(ctx)
        assert len(signals) == 0

    def test_fallback_near_month_end(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            fallback_days=3,
            min_buy_amount=Decimal("25"),
        )
        strategy = RedditSentimentDCAStrategy(params)

        ctx = self.create_context(
            sample_bars,
            date(2024, 1, 29),
            is_first=False,
            days_to_end=2,
            period_spent=Decimal("500"),
        )
        signals = strategy.evaluate(ctx)
        assert len(signals) >= 1
        assert signals[0].reason == "month-end fallback DCA"

    def test_multi_symbol_splits_budget(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(
            symbols=["SPY", "QQQ"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
        )
        strategy = RedditSentimentDCAStrategy(params)

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)

        assert len(signals) == 2
        # 1000 * 0.50 / 2 = 250 each
        assert signals[0].amount == Decimal("250")
        assert signals[1].amount == Decimal("250")

    def test_confidence_without_reddit(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(symbols=["SPY"])
        strategy = RedditSentimentDCAStrategy(params)

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)
        assert signals[0].confidence == 0.5

    def test_confidence_with_strong_reddit(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        params = RedditSentimentDCAParams(
            symbols=["SPY"],
            sentiment_threshold=0.3,
            min_mentions=5,
        )
        strategy = RedditSentimentDCAStrategy(params)

        strategy.set_reddit_trends([
            MemeStockTrend(ticker="SPY", mention_count=50, avg_sentiment=0.8),
        ])

        ctx = self.create_context(sample_bars, date(2024, 1, 2), is_first=True)
        signals = strategy.evaluate(ctx)
        assert signals[0].confidence > 0.5
