"""Tests for Dip Buy DCA strategy (Hybrid DCA + Dip Buy)."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from beavr.models.config import DipBuyDCAParams
from beavr.strategies.context import StrategyContext
from beavr.strategies.dip_buy_dca import DipBuyDCAStrategy


class TestDipBuyDCAStrategy:
    """Tests for DipBuyDCAStrategy (Hybrid approach)."""

    @pytest.fixture
    def default_params(self) -> DipBuyDCAParams:
        """Create default params for testing."""
        return DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,  # 50% DCA on first day
            dip_tier_1=0.01,  # 1% dip
            dip_tier_1_pct=0.20,
            dip_tier_2=0.02,
            dip_tier_2_pct=0.40,
            dip_tier_3=0.03,
            dip_tier_3_pct=0.75,
            max_dip_buys=8,
            lookback_days=1,
            fallback_days=3,
            min_buy_amount=Decimal("25"),
        )

    def create_bars(self, days: int = 10, price: float = 100.0) -> dict[str, pd.DataFrame]:
        """Create bar data with constant price."""
        dates = pd.date_range(end="2024-01-15", periods=days)
        df = pd.DataFrame(
            {
                "open": [price] * days,
                "high": [price * 1.01] * days,
                "low": [price * 0.99] * days,
                "close": [price] * days,
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
        period_budget: Decimal = Decimal("1000"),
        is_first_trading_day: bool = False,
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
            is_first_trading_day_of_month=is_first_trading_day,
            is_last_trading_day_of_month=days_to_month_end == 0,
        )

    def test_strategy_metadata(self, default_params: DipBuyDCAParams) -> None:
        """Test strategy metadata is correct."""
        strategy = DipBuyDCAStrategy(default_params)

        assert strategy.name == "Dip Buy DCA"
        assert strategy.version == "3.0.0"
        assert "dip" in strategy.description.lower()

    def test_symbols_property(self) -> None:
        """Test symbols property returns configured symbols."""
        params = DipBuyDCAParams(symbols=["SPY", "QQQ", "VOO"])
        strategy = DipBuyDCAStrategy(params)

        assert strategy.symbols == ["SPY", "QQQ", "VOO"]

    def test_base_dca_on_first_trading_day(self, default_params: DipBuyDCAParams) -> None:
        """Test that strategy buys base amount on first trading day of month."""
        strategy = DipBuyDCAStrategy(default_params)

        bars = self.create_bars()
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),  # First trading day (Jan 1 is holiday)
            current_price=Decimal("100.00"),
            period_spent=Decimal("0"),
            days_to_month_end=29,
            is_first_trading_day=True,  # First trading day!
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].symbol == "SPY"
        assert signals[0].action == "buy"
        assert signals[0].reason == "base_dca"
        # 50% of $1000 = $500
        assert signals[0].amount == Decimal("500.00")

    def test_dip_buy_after_base_dca(self, default_params: DipBuyDCAParams) -> None:
        """Test that strategy buys on dip from last buy price."""
        strategy = DipBuyDCAStrategy(default_params)

        # First, simulate the first trading day buy
        bars = self.create_bars()
        ctx1 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            is_first_trading_day=True,
        )
        signals1 = strategy.evaluate(ctx1)
        assert len(signals1) == 1
        assert signals1[0].reason == "base_dca"

        # Now, price drops 1.5% from $100 to $98.50
        ctx2 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 3),
            current_price=Decimal("98.50"),
            period_spent=Decimal("500"),  # Base DCA was spent
            days_to_month_end=28,
            is_first_trading_day=False,
        )
        signals2 = strategy.evaluate(ctx2)

        assert len(signals2) == 1
        assert signals2[0].reason == "dip_buy_t1"
        # 20% of remaining $500 = $100
        assert signals2[0].amount == Decimal("100.00")

    def test_no_dip_buy_when_price_stable(self, default_params: DipBuyDCAParams) -> None:
        """Test no dip buy when price hasn't dropped enough."""
        strategy = DipBuyDCAStrategy(default_params)

        # First day buy
        bars = self.create_bars()
        ctx1 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            is_first_trading_day=True,
        )
        strategy.evaluate(ctx1)

        # Next day, price only drops 0.5% (below 1% threshold)
        ctx2 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 3),
            current_price=Decimal("99.50"),
            period_spent=Decimal("500"),
            days_to_month_end=28,
            is_first_trading_day=False,
        )
        signals = strategy.evaluate(ctx2)

        # No dip buy, not in fallback period either
        assert len(signals) == 0

    def test_max_dip_buys_limit(self) -> None:
        """Test that max_dip_buys is respected."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
            dip_tier_1=0.01,
            dip_tier_1_pct=0.20,
            max_dip_buys=4,  # Limit to 4 dip buys for this test
        )
        strategy = DipBuyDCAStrategy(params)

        bars = self.create_bars()

        # First day buy
        ctx1 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            is_first_trading_day=True,
        )
        strategy.evaluate(ctx1)

        # Simulate 4 dip buys (max)
        prices = [Decimal("98.50"), Decimal("97.00"), Decimal("95.50"), Decimal("94.00")]
        spent = Decimal("500")

        for i, price in enumerate(prices):
            ctx = self.create_context(
                bars=bars,
                current_date=date(2024, 1, 3 + i),
                current_price=price,
                period_spent=spent,
                days_to_month_end=27 - i,
                is_first_trading_day=False,
            )
            signals = strategy.evaluate(ctx)
            if signals and "dip_buy" in signals[0].reason:
                spent += signals[0].amount

        # Now try a 5th dip - should NOT trigger dip buy
        ctx5 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 7),
            current_price=Decimal("92.00"),  # Another dip
            period_spent=spent,
            days_to_month_end=24,
            is_first_trading_day=False,
        )
        signals5 = strategy.evaluate(ctx5)

        # No dip buy (max reached), and not in fallback period
        assert len(signals5) == 0

    def test_fallback_triggers_at_month_end(self, default_params: DipBuyDCAParams) -> None:
        """Test that fallback triggers in last days of month."""
        strategy = DipBuyDCAStrategy(default_params)

        # Reset by setting a new month
        bars = self.create_bars()
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 29),  # In fallback period (3 days)
            current_price=Decimal("100.00"),
            period_spent=Decimal("500"),  # $500 remaining
            days_to_month_end=2,  # Last 3 days
            period_budget=Decimal("1000"),
            is_first_trading_day=False,
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        assert signals[0].reason == "fallback"

    def test_no_fallback_before_threshold(self, default_params: DipBuyDCAParams) -> None:
        """Test no fallback when not yet in fallback period."""
        strategy = DipBuyDCAStrategy(default_params)

        bars = self.create_bars()
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 15),
            current_price=Decimal("100.00"),
            period_spent=Decimal("0"),
            days_to_month_end=16,  # Outside fallback period
            is_first_trading_day=False,
        )

        signals = strategy.evaluate(ctx)

        # No first day, no dip (no previous buy), no fallback
        assert len(signals) == 0

    def test_no_buy_when_budget_exhausted(self, default_params: DipBuyDCAParams) -> None:
        """Test that no signals when budget is exhausted."""
        strategy = DipBuyDCAStrategy(default_params)

        bars = self.create_bars()
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            period_spent=Decimal("1000"),  # All spent
            period_budget=Decimal("1000"),
            is_first_trading_day=True,
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 0

    def test_min_buy_amount_respected(self) -> None:
        """Test that minimum buy amount is enforced."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("100"),
            base_buy_pct=0.50,
            dip_buy_pct=0.25,
            min_buy_amount=Decimal("50"),  # High minimum
        )
        strategy = DipBuyDCAStrategy(params)

        # First day: $50 base buy (50% of $100)
        bars = self.create_bars()
        ctx1 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            period_budget=Decimal("100"),
            is_first_trading_day=True,
        )
        signals1 = strategy.evaluate(ctx1)
        assert len(signals1) == 1
        assert signals1[0].amount == Decimal("50.00")

        # Dip: 25% of $50 remaining = $12.50, below $50 min
        ctx2 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 3),
            current_price=Decimal("98.00"),
            period_spent=Decimal("50"),
            period_budget=Decimal("100"),
            days_to_month_end=28,
            is_first_trading_day=False,
        )
        signals2 = strategy.evaluate(ctx2)

        # No buy because $12.50 < $50 min
        assert len(signals2) == 0

    def test_fallback_spreads_over_remaining_days(self) -> None:
        """Test that fallback spreads budget over remaining days."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
            fallback_days=3,
            min_buy_amount=Decimal("25"),
        )
        strategy = DipBuyDCAStrategy(params)

        # 2 days remaining, $500 left after base DCA
        bars = self.create_bars()
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 30),
            current_price=Decimal("100.00"),
            period_spent=Decimal("500"),
            days_to_month_end=1,  # 1 day remaining after today = 2 days total
            period_budget=Decimal("1000"),
            is_first_trading_day=False,
        )

        signals = strategy.evaluate(ctx)

        assert len(signals) == 1
        # $500 / 2 remaining days / 1 symbol = $250 per day
        assert signals[0].amount == Decimal("250")
        assert signals[0].reason == "fallback"

    def test_empty_bars_no_crash(self, default_params: DipBuyDCAParams) -> None:
        """Test that empty bars don't cause crash."""
        strategy = DipBuyDCAStrategy(default_params)

        empty_bars: dict[str, pd.DataFrame] = {"SPY": pd.DataFrame()}
        ctx = self.create_context(
            bars=empty_bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            days_to_month_end=29,
            is_first_trading_day=True,
        )

        # Should still generate base DCA signal (doesn't need bars)
        signals = strategy.evaluate(ctx)
        assert len(signals) == 1
        assert signals[0].reason == "base_dca"

    def test_missing_symbol_in_prices_skipped(
        self, default_params: DipBuyDCAParams
    ) -> None:
        """Test that missing symbols are skipped gracefully."""
        params = DipBuyDCAParams(symbols=["SPY", "MISSING"])
        strategy = DipBuyDCAStrategy(params)

        bars = self.create_bars()
        ctx = StrategyContext(
            current_date=date(2024, 1, 2),
            prices={"SPY": Decimal("100.00")},  # MISSING not in prices
            bars=bars,
            cash=Decimal("10000"),
            positions={},
            period_budget=Decimal("1000"),
            period_spent=Decimal("0"),
            day_of_month=2,
            day_of_week=1,
            days_to_month_end=29,
            is_first_trading_day_of_month=True,
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
        assert strategy.params.monthly_budget == Decimal("1000")
        assert strategy.params.base_buy_pct == 0.50
        assert strategy.params.dip_tier_1 == 0.01
        assert strategy.params.dip_tier_1_pct == 0.20
        assert strategy.params.dip_tier_2 == 0.02
        assert strategy.params.dip_tier_2_pct == 0.40
        assert strategy.params.dip_tier_3 == 0.03
        assert strategy.params.dip_tier_3_pct == 0.75
        assert strategy.params.max_dip_buys == 8

    def test_month_reset(self) -> None:
        """Test that dip count resets on new month."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.50,
            dip_tier_1=0.01,
            dip_tier_1_pct=0.20,
            max_dip_buys=2,  # Low max for testing
        )
        strategy = DipBuyDCAStrategy(params)

        bars = self.create_bars()

        # January first day
        ctx_jan1 = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            is_first_trading_day=True,
        )
        strategy.evaluate(ctx_jan1)

        # Use up all dip buys in January
        strategy._dip_buy_count = 2  # Simulate 2 dip buys

        # February first day - should reset and buy base DCA
        ctx_feb1 = self.create_context(
            bars=bars,
            current_date=date(2024, 2, 1),
            current_price=Decimal("95.00"),
            period_spent=Decimal("0"),
            is_first_trading_day=True,
        )
        signals = strategy.evaluate(ctx_feb1)

        assert len(signals) == 1
        assert signals[0].reason == "base_dca"
        assert strategy._dip_buy_count == 0  # Reset

    def test_no_base_buy_when_base_pct_zero(self) -> None:
        """Test that base buy is skipped when base_buy_pct is 0."""
        params = DipBuyDCAParams(
            symbols=["SPY"],
            monthly_budget=Decimal("1000"),
            base_buy_pct=0.0,  # No base DCA
            dip_tier_1=0.01,
            dip_tier_1_pct=0.20,
        )
        strategy = DipBuyDCAStrategy(params)

        bars = self.create_bars()
        ctx = self.create_context(
            bars=bars,
            current_date=date(2024, 1, 2),
            current_price=Decimal("100.00"),
            is_first_trading_day=True,
        )

        signals = strategy.evaluate(ctx)

        # No base buy since base_buy_pct is 0
        assert len(signals) == 0
