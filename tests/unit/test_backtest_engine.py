"""Tests for backtest engine."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from beavr.backtest.engine import BacktestEngine, BacktestResult
from beavr.models.config import SimpleDCAParams
from beavr.models.signal import Signal
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.simple_dca import SimpleDCAStrategy


class MockDataFetcher:
    """Mock data fetcher for testing."""

    def __init__(self, bars: dict[str, pd.DataFrame]) -> None:
        self.bars = bars

    def get_multi_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> dict[str, pd.DataFrame]:
        """Return pre-configured bar data."""
        return {s: self.bars.get(s, pd.DataFrame()) for s in symbols}


def create_test_bars(
    symbol: str,
    start_date: str,
    num_days: int,
    base_price: float = 100.0,
    daily_change: float = 0.001,
) -> pd.DataFrame:
    """Create test bar data.

    Args:
        symbol: Symbol name
        start_date: Start date string (YYYY-MM-DD)
        num_days: Number of trading days
        base_price: Starting price
        daily_change: Daily price change percentage

    Returns:
        DataFrame with OHLCV data
    """
    dates = pd.date_range(start=start_date, periods=num_days, freq="B")
    prices = [base_price * (1 + daily_change) ** i for i in range(num_days)]

    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000000] * num_days,
        },
        index=dates,
    )


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    @pytest.fixture
    def sample_bars(self) -> dict[str, pd.DataFrame]:
        """Create sample bar data for testing."""
        return {
            "SPY": create_test_bars("SPY", "2024-01-01", 252, base_price=450.0),
        }

    @pytest.fixture
    def data_fetcher(self, sample_bars: dict[str, pd.DataFrame]) -> MockDataFetcher:
        """Create mock data fetcher."""
        return MockDataFetcher(sample_bars)

    @pytest.fixture
    def engine(self, data_fetcher: MockDataFetcher) -> BacktestEngine:
        """Create backtest engine."""
        return BacktestEngine(data_fetcher=data_fetcher)

    def test_engine_initialization(self, data_fetcher: MockDataFetcher) -> None:
        """Test engine initialization."""
        engine = BacktestEngine(data_fetcher=data_fetcher)
        assert engine.data == data_fetcher
        assert engine.results_repo is None

    def test_simple_backtest(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test running a simple backtest."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("500"),
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_cash=Decimal("10000"),
        )

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Simple DCA"
        assert result.start_date == date(2024, 1, 1)
        assert result.end_date == date(2024, 12, 31)
        assert result.metrics.initial_cash == Decimal("10000")
        assert len(result.daily_values) > 0

    def test_backtest_with_trades(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test backtest generates trades."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("500"),
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_cash=Decimal("10000"),
        )

        # Should have roughly 12 trades (one per month)
        assert len(result.trades) > 0
        assert all(t.side == "buy" for t in result.trades)
        assert all(t.symbol == "SPY" for t in result.trades)

    def test_backtest_metrics_calculated(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test metrics are calculated correctly."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("500"),
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_cash=Decimal("10000"),
        )

        assert result.metrics.total_trades > 0
        assert result.metrics.total_invested > Decimal("0")
        assert "SPY" in result.metrics.holdings

    def test_backtest_daily_values_tracked(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test daily values are tracked."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("100"),
            frequency="weekly",
            day_of_week=0,  # Monday
        )
        strategy = SimpleDCAStrategy(params)

        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            initial_cash=Decimal("10000"),
        )

        # Should have daily values for each trading day
        assert len(result.daily_values) > 50  # ~60 trading days in 3 months
        # All values should be dates and decimals
        assert all(isinstance(d, date) for d, v in result.daily_values)
        assert all(isinstance(v, Decimal) for d, v in result.daily_values)

    def test_backtest_respects_cash(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test backtest respects available cash."""
        params = SimpleDCAParams(
            symbols=["SPY"],
            amount=Decimal("500"),
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        # Small initial cash - can only afford a few buys
        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_cash=Decimal("1000"),
        )

        # Total invested should not exceed initial cash
        assert result.metrics.total_invested <= Decimal("1000")

    def test_empty_date_range_raises(
        self,
        data_fetcher: MockDataFetcher,
    ) -> None:
        """Test that empty date range raises error."""
        # Create engine with empty data
        empty_fetcher = MockDataFetcher({"SPY": pd.DataFrame()})
        engine = BacktestEngine(data_fetcher=empty_fetcher)

        params = SimpleDCAParams(symbols=["SPY"])
        strategy = SimpleDCAStrategy(params)

        with pytest.raises(ValueError, match="No trading days"):
            engine.run(
                strategy=strategy,
                start_date=date(2020, 1, 1),
                end_date=date(2020, 1, 31),
                initial_cash=Decimal("10000"),
            )

    def test_multiple_symbols(
        self,
        data_fetcher: MockDataFetcher,
    ) -> None:
        """Test backtest with multiple symbols."""
        # Add QQQ data to fetcher
        data_fetcher.bars["QQQ"] = create_test_bars(
            "QQQ", "2024-01-01", 252, base_price=350.0
        )
        engine = BacktestEngine(data_fetcher=data_fetcher)

        params = SimpleDCAParams(
            symbols=["SPY", "QQQ"],
            amount=Decimal("1000"),  # $500 per symbol
            frequency="monthly",
            day_of_month=1,
        )
        strategy = SimpleDCAStrategy(params)

        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_cash=Decimal("15000"),
        )

        # Should have trades for both symbols
        symbols_traded = set(t.symbol for t in result.trades)
        assert "SPY" in symbols_traded
        assert "QQQ" in symbols_traded

    def test_run_id_unique(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test that each run gets a unique ID."""
        params = SimpleDCAParams(symbols=["SPY"], amount=Decimal("500"))
        strategy = SimpleDCAStrategy(params)

        result1 = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_cash=Decimal("10000"),
        )
        result2 = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_cash=Decimal("10000"),
        )

        assert result1.run_id != result2.run_id


class TestBacktestEngineHelpers:
    """Tests for helper methods."""

    @pytest.fixture
    def sample_bars(self) -> dict[str, pd.DataFrame]:
        """Create sample bar data."""
        return {"SPY": create_test_bars("SPY", "2024-01-01", 30)}

    @pytest.fixture
    def engine(self, sample_bars: dict[str, pd.DataFrame]) -> BacktestEngine:
        """Create backtest engine."""
        return BacktestEngine(data_fetcher=MockDataFetcher(sample_bars))

    def test_get_trading_days(
        self,
        engine: BacktestEngine,
        sample_bars: dict[str, pd.DataFrame],
    ) -> None:
        """Test extracting trading days from bars."""
        trading_days = engine._get_trading_days(
            bars=sample_bars,
            start=date(2024, 1, 1),
            end=date(2024, 2, 28),
        )

        assert len(trading_days) > 0
        assert all(isinstance(d, date) for d in trading_days)
        assert trading_days == sorted(trading_days)

    def test_is_first_trading_day_of_month(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test first trading day detection."""
        trading_days = [
            date(2024, 1, 29),
            date(2024, 1, 30),
            date(2024, 1, 31),
            date(2024, 2, 1),
            date(2024, 2, 2),
        ]

        assert engine._is_first_trading_day_of_month(trading_days, 0)
        assert not engine._is_first_trading_day_of_month(trading_days, 1)
        assert not engine._is_first_trading_day_of_month(trading_days, 2)
        assert engine._is_first_trading_day_of_month(trading_days, 3)

    def test_is_last_trading_day_of_month(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test last trading day detection."""
        trading_days = [
            date(2024, 1, 29),
            date(2024, 1, 30),
            date(2024, 1, 31),
            date(2024, 2, 1),
            date(2024, 2, 2),
        ]

        assert not engine._is_last_trading_day_of_month(trading_days, 0)
        assert not engine._is_last_trading_day_of_month(trading_days, 1)
        assert engine._is_last_trading_day_of_month(trading_days, 2)
        assert not engine._is_last_trading_day_of_month(trading_days, 3)
        assert engine._is_last_trading_day_of_month(trading_days, 4)

    def test_days_to_month_end(
        self,
        engine: BacktestEngine,
    ) -> None:
        """Test days to month end calculation."""
        trading_days = [
            date(2024, 1, 29),
            date(2024, 1, 30),
            date(2024, 1, 31),
            date(2024, 2, 1),
            date(2024, 2, 2),
        ]

        assert engine._days_to_month_end(trading_days, 0) == 2  # 30th, 31st
        assert engine._days_to_month_end(trading_days, 1) == 1  # 31st
        assert engine._days_to_month_end(trading_days, 2) == 0  # Last day
        assert engine._days_to_month_end(trading_days, 3) == 1  # Feb 2nd
