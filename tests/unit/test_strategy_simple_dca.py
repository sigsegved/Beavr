"""Tests for Simple DCA strategy."""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from beavr.models.config import SimpleDCAParams
from beavr.strategies.context import StrategyContext
from beavr.strategies.simple_dca import SimpleDCAStrategy


class TestSimpleDCAStrategy:
    """Tests for SimpleDCAStrategy."""

    @pytest.fixture
    def sample_bars(self) -> dict[str, pd.DataFrame]:
        """Create sample bar data."""
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
    ) -> StrategyContext:
        """Create a context for a specific date."""
        return StrategyContext(
            current_date=current_date,
            prices={"SPY": Decimal("450"), "QQQ": Decimal("350")},
            bars=sample_bars,
            cash=cash,
            positions={},
            period_budget=Decimal("500"),
            period_spent=Decimal("0"),
            day_of_month=current_date.day,
            day_of_week=current_date.weekday(),
            days_to_month_end=31 - current_date.day,
            is_first_trading_day_of_month=current_date.day == 1,
            is_last_trading_day_of_month=current_date.day >= 28,
        )

    def test_strategy_metadata(self) -> None:
        """Test strategy metadata is correct."""
        params = SimpleDCAParams()
        strategy = SimpleDCAStrategy(params)

        assert strategy.name == "Simple DCA"
        assert strategy.version == "1.0.0"
        assert "interval" in strategy.description.lower()

    def test_symbols_property(self) -> None:
        """Test symbols property returns configured symbols."""
        params = SimpleDCAParams(symbols=["SPY", "QQQ", "VOO"])
        strategy = SimpleDCAStrategy(params)

        assert strategy.symbols == ["SPY", "QQQ", "VOO"]

    def test_monthly_buy_on_correct_day(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test monthly strategy buys on configured day."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("500"),
            frequency="monthly",
            day_of_month=15,
        )
        strategy = SimpleDCAStrategy(params)

        # January 15th is a Monday in 2024
        ctx = self.create_context(sample_bars, date(2024, 1, 15))
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].symbol == "SPY"
        assert signals[0].amount == Decimal("500")
        assert signals[0].action == "buy"
        assert signals[0].reason == "scheduled"

    def test_monthly_no_buy_on_wrong_day(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test monthly strategy doesn't buy on non-scheduled days."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("500"),
            frequency="monthly",
            day_of_month=15,
        )
        strategy = SimpleDCAStrategy(params)

        # January 10th
        ctx = self.create_context(sample_bars, date(2024, 1, 10))
        signals = strategy.evaluate(ctx)

        assert len(signals) == 0

    def test_weekly_buy_on_correct_day(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test weekly strategy buys on configured weekday."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("100"),
            frequency="weekly",
            day_of_week=0,  # Monday
        )
        strategy = SimpleDCAStrategy(params)

        # January 8, 2024 is a Monday
        ctx = self.create_context(sample_bars, date(2024, 1, 8))
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].amount == Decimal("100")

    def test_weekly_no_buy_on_wrong_day(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test weekly strategy doesn't buy on non-scheduled days."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("100"),
            frequency="weekly",
            day_of_week=0,  # Monday
        )
        strategy = SimpleDCAStrategy(params)

        # January 9, 2024 is a Tuesday
        ctx = self.create_context(sample_bars, date(2024, 1, 9))
        signals = strategy.evaluate(ctx)

        assert len(signals) == 0

    def test_biweekly_alternates_weeks(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test biweekly buys every other week."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("200"),
            frequency="biweekly",
            day_of_week=0,  # Monday
        )
        strategy = SimpleDCAStrategy(params)

        # Check two consecutive Mondays
        # January 1, 2024 is Monday (week 1 - odd)
        ctx1 = self.create_context(sample_bars, date(2024, 1, 1))
        signals1 = strategy.evaluate(ctx1)

        # January 8, 2024 is Monday (week 2 - even)
        ctx2 = self.create_context(sample_bars, date(2024, 1, 8))
        signals2 = strategy.evaluate(ctx2)

        # One should trigger, one should not
        assert (len(signals1) == 1) != (len(signals2) == 1)

    def test_multiple_symbols_split_evenly(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test that amount is split evenly among symbols."""
        params = SimpleDCAParams(
            symbols=["SPY", "QQQ"],
            amount=Decimal("1000"),
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        ctx = self.create_context(sample_bars, date(2024, 1, 1))
        signals = strategy.evaluate(ctx)

        assert len(signals) == 2
        # $1000 / 2 symbols = $500 each
        assert signals[0].amount == Decimal("500")
        assert signals[1].amount == Decimal("500")
        assert {s.symbol for s in signals} == {"SPY", "QQQ"}

    def test_insufficient_cash_limits_signals(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test that signals respect available cash."""
        params = SimpleDCAParams(
            symbols=["SPY", "QQQ"],
            amount=Decimal("1000"),  # $500 per symbol
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        # Only $400 cash - not enough for even one symbol
        ctx = self.create_context(sample_bars, date(2024, 1, 1), cash=Decimal("400"))
        signals = strategy.evaluate(ctx)

        # Not enough cash for any purchase
        assert len(signals) == 0

    def test_partial_cash_allows_some_signals(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test that partial cash allows some purchases."""
        params = SimpleDCAParams(
            symbols=["SPY", "QQQ"],
            amount=Decimal("1000"),  # $500 per symbol
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        # $600 cash - enough for one symbol
        ctx = self.create_context(sample_bars, date(2024, 1, 1), cash=Decimal("600"))
        signals = strategy.evaluate(ctx)

        # Should generate 1 signal (for first symbol only)
        assert len(signals) == 1
        assert signals[0].amount == Decimal("500")

    def test_signal_has_correct_timestamp(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test that signals have correct timestamp."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("500"),
            frequency="monthly",
            day_of_month=15,
        )
        strategy = SimpleDCAStrategy(params)

        ctx = self.create_context(sample_bars, date(2024, 1, 15))
        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].timestamp.date() == date(2024, 1, 15)

    def test_default_params(self) -> None:
        """Test strategy works with default parameters."""
        params = SimpleDCAParams()  # Uses defaults
        strategy = SimpleDCAStrategy(params)

        assert strategy.symbols == ["SPY"]
        assert strategy.params.amount == Decimal("500")
        assert strategy.params.frequency == "monthly"
        assert strategy.params.day_of_month == 1

    def test_repr(self) -> None:
        """Test strategy repr."""
        params = SimpleDCAParams()
        strategy = SimpleDCAStrategy(params)

        assert "SimpleDCAStrategy" in repr(strategy)
        assert "Simple DCA" in repr(strategy)
