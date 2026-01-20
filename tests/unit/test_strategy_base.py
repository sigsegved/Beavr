"""Tests for BaseStrategy and StrategyContext."""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from beavr.models.signal import Signal
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext


class TestStrategyContext:
    """Tests for StrategyContext dataclass."""

    @pytest.fixture
    def sample_bars(self) -> dict[str, pd.DataFrame]:
        """Create sample bar data."""
        dates = pd.date_range("2024-01-01", periods=5)
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 101.5, 103.0],
                "high": [102.0, 103.0, 104.0, 103.5, 105.0],
                "low": [99.0, 100.0, 101.0, 100.5, 102.0],
                "close": [101.0, 102.0, 103.0, 102.5, 104.0],
                "volume": [1000000] * 5,
            },
            index=dates,
        )
        return {"SPY": df}

    @pytest.fixture
    def sample_context(self, sample_bars: dict[str, pd.DataFrame]) -> StrategyContext:
        """Create a sample strategy context."""
        return StrategyContext(
            current_date=date(2024, 1, 5),
            prices={"SPY": Decimal("104.00"), "QQQ": Decimal("350.00")},
            bars=sample_bars,
            cash=Decimal("10000"),
            positions={"SPY": Decimal("10.5")},
            period_budget=Decimal("500"),
            period_spent=Decimal("200"),
            day_of_month=5,
            day_of_week=4,  # Friday
            days_to_month_end=18,
            is_first_trading_day_of_month=False,
            is_last_trading_day_of_month=False,
        )

    def test_context_creation(self, sample_context: StrategyContext) -> None:
        """Test that context is created with all fields."""
        assert sample_context.current_date == date(2024, 1, 5)
        assert sample_context.cash == Decimal("10000")
        assert sample_context.day_of_month == 5
        assert sample_context.day_of_week == 4

    def test_remaining_budget(self, sample_context: StrategyContext) -> None:
        """Test remaining budget calculation."""
        assert sample_context.remaining_budget == Decimal("300")

    def test_get_position_value(self, sample_context: StrategyContext) -> None:
        """Test position value calculation."""
        # SPY: 10.5 shares * $104 = $1092
        assert sample_context.get_position_value("SPY") == Decimal("1092.00")

    def test_get_position_value_no_position(self, sample_context: StrategyContext) -> None:
        """Test position value for non-held symbol."""
        assert sample_context.get_position_value("AAPL") == Decimal("0")

    def test_get_total_position_value(self, sample_context: StrategyContext) -> None:
        """Test total position value (only calculates for positions we hold)."""
        # We hold 10.5 shares of SPY at $104 = $1092
        # We have prices for QQQ but no position
        assert sample_context.get_total_position_value() == Decimal("1092.00")

    def test_get_portfolio_value(self, sample_context: StrategyContext) -> None:
        """Test portfolio value (cash + positions)."""
        # Cash: $10,000 + Position value: $1,092 = $11,092
        assert sample_context.get_portfolio_value() == Decimal("11092.00")


class TestBaseStrategy:
    """Tests for BaseStrategy abstract class."""

    def test_cannot_instantiate_directly(self) -> None:
        """Test that BaseStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseStrategy()

    def test_concrete_strategy_implementation(self) -> None:
        """Test that a concrete strategy can be implemented."""
        from pydantic import BaseModel

        class TestParams(BaseModel):
            symbols: list[str]

        class TestStrategy(BaseStrategy):
            name = "Test Strategy"
            description = "A test strategy"
            version = "0.1.0"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return [
                    Signal(
                        symbol=self.params.symbols[0],
                        action="buy",
                        amount=Decimal("100"),
                        reason="test",
                        timestamp=datetime.combine(ctx.current_date, datetime.min.time()),
                    )
                ]

        params = TestParams(symbols=["SPY"])
        strategy = TestStrategy(params)

        assert strategy.name == "Test Strategy"
        assert strategy.version == "0.1.0"
        assert strategy.symbols == ["SPY"]

    def test_strategy_evaluate_returns_signals(
        self, sample_bars: dict[str, pd.DataFrame]
    ) -> None:
        """Test that evaluate returns signals."""
        from pydantic import BaseModel

        class TestParams(BaseModel):
            symbols: list[str]
            amount: Decimal

        class TestStrategy(BaseStrategy):
            name = "Buy Strategy"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return [
                    Signal(
                        symbol=s,
                        action="buy",
                        amount=self.params.amount,
                        reason="test_buy",
                        timestamp=datetime.combine(ctx.current_date, datetime.min.time()),
                    )
                    for s in self.params.symbols
                ]

        params = TestParams(symbols=["SPY", "QQQ"], amount=Decimal("250"))
        strategy = TestStrategy(params)

        ctx = StrategyContext(
            current_date=date(2024, 1, 5),
            prices={"SPY": Decimal("450"), "QQQ": Decimal("350")},
            bars=sample_bars,
            cash=Decimal("10000"),
            positions={},
            period_budget=Decimal("500"),
            period_spent=Decimal("0"),
            day_of_month=5,
            day_of_week=4,
            days_to_month_end=18,
            is_first_trading_day_of_month=False,
            is_last_trading_day_of_month=False,
        )

        signals = strategy.evaluate(ctx)
        assert len(signals) == 2
        assert signals[0].symbol == "SPY"
        assert signals[0].amount == Decimal("250")
        assert signals[1].symbol == "QQQ"

    def test_strategy_repr(self) -> None:
        """Test strategy __repr__."""
        from pydantic import BaseModel

        class TestParams(BaseModel):
            symbols: list[str]

        class TestStrategy(BaseStrategy):
            name = "My Test"
            version = "2.0.0"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        params = TestParams(symbols=["SPY"])
        strategy = TestStrategy(params)
        assert repr(strategy) == "<TestStrategy 'My Test' v2.0.0>"

    def test_lifecycle_hooks_optional(self) -> None:
        """Test that on_period_start and on_period_end are optional."""
        from pydantic import BaseModel

        class TestParams(BaseModel):
            symbols: list[str]

        class TestStrategy(BaseStrategy):
            name = "Minimal"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        params = TestParams(symbols=["SPY"])
        strategy = TestStrategy(params)

        # These should not raise
        strategy.on_period_start(None)  # type: ignore
        strategy.on_period_end(None)  # type: ignore


@pytest.fixture
def sample_bars() -> dict[str, pd.DataFrame]:
    """Create sample bar data for tests."""
    dates = pd.date_range("2024-01-01", periods=5)
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 101.5, 103.0],
            "high": [102.0, 103.0, 104.0, 103.5, 105.0],
            "low": [99.0, 100.0, 101.0, 100.5, 102.0],
            "close": [101.0, 102.0, 103.0, 102.5, 104.0],
            "volume": [1000000] * 5,
        },
        index=dates,
    )
    return {"SPY": df}
