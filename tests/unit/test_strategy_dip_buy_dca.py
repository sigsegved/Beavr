"""Tests for Dip Buy DCA strategy."""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from beavr.models.config import DipBuyDCAParams
from beavr.strategies.context import StrategyContext
from beavr.strategies.dip_buy_dca import DipBuyDCAStrategy


class TestDipBuyDCAStrategy:
    """Tests for DipBuyDCAStrategy."""

    @pytest.fixture
    def default_params(self) -> DipBuyDCAParams:
        """Create default params for testing."""
        return DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("500"),
            dip_threshold=0.02,  # 2% dip
            dip_buy_pct=0.50,  # Buy 50% of remaining on dip
            lookback_days=5,
            fallback_days=3,
            min_buy_amount=Decimal("25"),
        )

    def create_bars_with_high(
        self, high_price: float, current_price: float, days: int = 10
    ) -> dict[str, pd.DataFrame]:
        """Create bar data with a specific recent high and current price."""
        dates = pd.date_range(end="2024-01-15", periods=days)
        prices = [high_price] * (days - 1) + [current_price]
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p * 1.01 for p in prices],
                "low": [p * 0.99 for p in prices],
                "close": prices,
                "volume": [1000000] * days,
            },
            index=dates,
        )
        return {"SPY": df}

    def create_context(
        self,
        bars: dict[str, pd.DataFrame],
        current_date: date,
        current_price: Decimal,
        period_spent: Decimal = Decimal("0"),
        days_to_month_end: int = 15,
        period_budget: Decimal = Decimal("500"),
    ) -> StrategyContext:
        """Create a strategy context for testing."""
        return StrategyContext(
            current_date=current_date,
            prices={"SPY": current_price},
            bars=bars,
            cash=Decimal("10000"),
            positions={},
            period_budget=period_budget,
            period_spent=period_spent,
            day_of_month=current_date.day,
            day_of_week=current_date.weekday(),
            days_to_month_end=days_to_month_end,
            is_first_trading_day_of_month=current_date.day == 1,
            is_last_trading_day_of_month=days_to_month_end == 0,
        )

    def test_strategy_metadata(self, default_params: DipBuyDCAParams) -> None:
        """Test strategy metadata is correct."""
        strategy = DipBuyDCAStrategy(default_params)

        assert strategy.name == "Dip Buy DCA"
        assert strategy.version == "1.0.0"
        assert "dip" in strategy.description.lower()

    def test_symbols_property(self) -> None:
        """Test symbols property returns configured symbols."""
        params = DipBuyDCAParams(symbols=["SPY", "QQQ", "VOO"])
        strategy = DipBuyDCAStrategy(params)

        assert strategy.symbols == ["SPY", "QQQ", "VOO"]

    def test_detects_dip_and_buys(self, default_params: DipBuyDCAParams) -> None:
        """Test that strategy detects a dip and generates buy signal."""
        strategy = DipBuyDCAStrategy(default_params)

        # Recent high: $100, current: $97 (3% drop, above 2% threshold)
        bars = self.create_bars_with_high(100.0, 97.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("97.00"),
            period_spent=Decimal("0"),
            days_to_month_end=16,  # Not in fallback period
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].symbol == "SPY"
        assert signals[0].action == "buy"
        assert signals[0].reason == "dip_buy"
        # 50% of $500 remaining = $250
        assert signals[0].amount == Decimal("250.00")

    def test_no_buy_when_not_dip(self, default_params: DipBuyDCAParams) -> None:
        """Test that strategy doesn't buy when price hasn't dipped enough."""
        strategy = DipBuyDCAStrategy(default_params)

        # Recent high: $100, current: $99 (1% drop, below 2% threshold)
        bars = self.create_bars_with_high(100.0, 99.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("99.00"),
            period_spent=Decimal("0"),
            days_to_month_end=16,  # Not in fallback period
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 0

    def test_fallback_triggers_at_month_end(
        self, default_params: DipBuyDCAParams
    ) -> None:
        """Test that fallback triggers in last N days of month."""
        strategy = DipBuyDCAStrategy(default_params)

        # No dip (price at recent high), but in fallback period
        bars = self.create_bars_with_high(100.0, 100.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 29),
            current_price=Decimal("100.00"),
            period_spent=Decimal("0"),
            days_to_month_end=2,  # 2 days left, fallback_days=3
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].reason == "fallback"

    def test_no_fallback_before_threshold(
        self, default_params: DipBuyDCAParams
    ) -> None:
        """Test that fallback doesn't trigger before threshold."""
        strategy = DipBuyDCAStrategy(default_params)

        # No dip, not in fallback period yet
        bars = self.create_bars_with_high(100.0, 100.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 25),
            current_price=Decimal("100.00"),
            period_spent=Decimal("0"),
            days_to_month_end=6,  # 6 days left, fallback_days=3
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 0

    def test_no_buy_when_budget_exhausted(
        self, default_params: DipBuyDCAParams
    ) -> None:
        """Test that no signals when budget is exhausted."""
        strategy = DipBuyDCAStrategy(default_params)

        # Dip detected, but all budget spent
        bars = self.create_bars_with_high(100.0, 97.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("97.00"),
            period_spent=Decimal("500"),  # Full budget spent
            days_to_month_end=16,
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 0

    def test_min_buy_amount_respected(self) -> None:
        """Test that minimum buy amount is respected."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("100"),  # Small budget
            dip_threshold=0.02,
            dip_buy_pct=0.10,  # 10% = $10
            min_buy_amount=Decimal("25"),  # But minimum is $25
        )
        strategy = DipBuyDCAStrategy(params)

        # Dip detected
        bars = self.create_bars_with_high(100.0, 97.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("97.00"),
            period_spent=Decimal("0"),
            days_to_month_end=16,
            period_budget=Decimal("100"),  # Match small budget
        )

        signals = strategy.evaluate(ctx)

        # 10% of $100 = $10, but min is $25, so no signal
        assert len(signals) == 0

    def test_partial_budget_remaining(self, default_params: DipBuyDCAParams) -> None:
        """Test buying with partial budget remaining."""
        strategy = DipBuyDCAStrategy(default_params)

        # Dip detected, partial budget remaining
        bars = self.create_bars_with_high(100.0, 97.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("97.00"),
            period_spent=Decimal("300"),  # $200 remaining
            days_to_month_end=16,
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        # 50% of $200 remaining = $100
        assert signals[0].amount == Decimal("100.00")

    def test_dip_detection_edge_case_exact_threshold(self) -> None:
        """Test dip detection at exact threshold."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            dip_threshold=0.02,  # Exactly 2%
        )
        strategy = DipBuyDCAStrategy(params)

        # Exactly 2% drop: $100 -> $98
        bars = self.create_bars_with_high(100.0, 98.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("98.00"),
            days_to_month_end=16,
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1

    def test_multiple_symbols(self) -> None:
        """Test strategy with multiple symbols."""
        params = DipBuyDCAParams(
            symbols=["SPY", "QQQ"],
            monthly_budget=Decimal("500"),
            dip_threshold=0.02,
            dip_buy_pct=0.50,
        )
        strategy = DipBuyDCAStrategy(params)

        # Create bars for both symbols
        dates = pd.date_range(end="2024-01-15", periods=10)
        spy_bars = pd.DataFrame(
            {
                "open": [100.0] * 9 + [97.0],
                "high": [102.0] * 9 + [98.0],
                "low": [99.0] * 9 + [96.0],
                "close": [100.0] * 9 + [97.0],  # 3% dip
                "volume": [1000000] * 10,
            },
            index=dates,
        )
        qqq_bars = pd.DataFrame(
            {
                "open": [350.0] * 10,
                "high": [355.0] * 10,
                "low": [345.0] * 10,
                "close": [350.0] * 10,  # No dip
                "volume": [500000] * 10,
            },
            index=dates,
        )

        ctx = StrategyContext(
            current_date=date(2024, 1, 15),
            prices={"SPY": Decimal("97.00"), "QQQ": Decimal("350.00")},
            bars={"SPY": spy_bars, "QQQ": qqq_bars},
            cash=Decimal("10000"),
            positions={},
            period_budget=Decimal("500"),
            period_spent=Decimal("0"),
            day_of_month=15,
            day_of_week=0,
            days_to_month_end=16,
            is_first_trading_day_of_month=False,
            is_last_trading_day_of_month=False,
        )

        signals = strategy.evaluate(ctx)

        # Only SPY should trigger (it has a dip)
        assert len(signals) == 1
        assert signals[0].symbol == "SPY"

    def test_fallback_spreads_over_remaining_days(self) -> None:
        """Test that fallback spreads budget over remaining days."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("300"),
            fallback_days=3,
            min_buy_amount=Decimal("25"),
        )
        strategy = DipBuyDCAStrategy(params)

        # 2 days remaining (including today): days_to_month_end=1 means tomorrow is last day
        # So we have today (30th) and tomorrow (31st) = 2 days
        # days_to_month_end + 1 = 2
        bars = self.create_bars_with_high(100.0, 100.0)
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 30),
            current_price=Decimal("100.00"),
            period_spent=Decimal("0"),
            days_to_month_end=1,  # 1 day remaining after today
            period_budget=Decimal("300"),  # Match strategy's monthly_budget
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        # $300 / (1+1=2 remaining days) / 1 symbol = $150 per day
        assert signals[0].amount == Decimal("150")

    def test_empty_bars_no_crash(self, default_params: DipBuyDCAParams) -> None:
        """Test that empty bars don't cause crash."""
        strategy = DipBuyDCAStrategy(default_params)

        empty_bars: dict[str, pd.DataFrame] = {"SPY": pd.DataFrame()}
        ctx = self.create_context(
            bars=empty_bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("100.00"),
            days_to_month_end=16,
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 0

    def test_missing_symbol_in_prices_skipped(
        self, default_params: DipBuyDCAParams
    ) -> None:
        """Test that missing symbols are skipped gracefully."""
        params = DipBuyDCAParams(symbols=["SPY", "MISSING"])
        strategy = DipBuyDCAStrategy(params)

        bars = self.create_bars_with_high(100.0, 97.0)
        ctx = StrategyContext(
            current_date=date(2024, 1, 15),
            prices={"SPY": Decimal("97.00")},  # MISSING not in prices
            bars=bars,
            cash=Decimal("10000"),
            positions={},
            period_budget=Decimal("500"),
            period_spent=Decimal("0"),
            day_of_month=15,
            day_of_week=0,
            days_to_month_end=16,
            is_first_trading_day_of_month=False,
            is_last_trading_day_of_month=False,
        )

        # Should not crash, should process SPY only
        signals = strategy.evaluate(ctx)
        assert len(signals) == 1
        assert signals[0].symbol == "SPY"

    def test_default_params(self) -> None:
        """Test strategy works with default parameters."""
        params = DipBuyDCAParams()  # Uses defaults
        strategy = DipBuyDCAStrategy(params)

        assert strategy.symbols == ["SPY"]
        assert strategy.params.monthly_budget == Decimal("500")
        assert strategy.params.dip_threshold == 0.02
