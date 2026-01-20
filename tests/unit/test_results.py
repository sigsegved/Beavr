"""Unit tests for BacktestResultsRepository."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from beavr.db import BacktestMetrics, BacktestResultsRepository, Database
from beavr.models.trade import Trade


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def repo(db):
    """Create a BacktestResultsRepository instance for testing."""
    return BacktestResultsRepository(db)


def make_metrics(
    final_value: Decimal = Decimal("11000"),
    total_return: float = 0.10,
    total_trades: int = 12,
    total_invested: Decimal = Decimal("10000"),
) -> BacktestMetrics:
    """Helper to create BacktestMetrics."""
    return BacktestMetrics(
        final_value=final_value,
        total_return=total_return,
        cagr=0.08,
        max_drawdown=-0.05,
        sharpe_ratio=1.2,
        total_trades=total_trades,
        total_invested=total_invested,
        holdings={"SPY": Decimal("10.5"), "VOO": Decimal("5.25")},
    )


def make_trade(
    symbol: str = "SPY",
    side: str = "buy",
    amount: Decimal = Decimal("4505"),
    price: Decimal = Decimal("450.50"),
) -> Trade:
    """Helper to create a Trade."""
    if side == "buy":
        return Trade.create_buy(
            symbol=symbol,
            amount=amount,
            price=price,
            timestamp=datetime(2024, 1, 15, 10, 30),
            reason="Monthly DCA",
        )
    else:
        return Trade.create_sell(
            symbol=symbol,
            quantity=amount / price,
            price=price,
            timestamp=datetime(2024, 1, 15, 10, 30),
            reason="Rebalance",
        )


class TestBacktestMetrics:
    """Tests for BacktestMetrics model."""

    def test_metrics_creation(self):
        """Test creating metrics."""
        metrics = make_metrics()
        assert metrics.final_value == Decimal("11000")
        assert metrics.total_return == 0.10
        assert metrics.total_trades == 12

    def test_metrics_is_frozen(self):
        """Test that metrics are immutable."""
        metrics = make_metrics()
        with pytest.raises(Exception):
            metrics.final_value = Decimal("12000")

    def test_metrics_with_no_optional(self):
        """Test metrics without optional fields."""
        metrics = BacktestMetrics(
            final_value=Decimal("11000"),
            total_return=0.10,
            total_trades=12,
            total_invested=Decimal("10000"),
        )
        assert metrics.cagr is None
        assert metrics.max_drawdown is None
        assert metrics.sharpe_ratio is None
        assert metrics.holdings == {}


class TestCreateRun:
    """Tests for creating backtest runs."""

    def test_create_run_returns_uuid(self, repo):
        """Test that create_run returns a UUID."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={"amount": 100, "day": 15},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        assert run_id is not None
        assert len(run_id) == 36  # UUID format
        assert "-" in run_id

    def test_create_run_persists(self, repo):
        """Test that created run can be retrieved."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={"amount": 100},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        run = repo.get_run(run_id)
        
        assert run is not None
        assert run["strategy_name"] == "simple_dca"
        assert run["config"] == {"amount": 100}
        assert run["start_date"] == date(2023, 1, 1)
        assert run["end_date"] == date(2023, 12, 31)
        assert run["initial_cash"] == Decimal("10000")


class TestSaveResults:
    """Tests for saving backtest results."""

    def test_save_results_basic(self, repo):
        """Test saving results."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        metrics = make_metrics()
        
        repo.save_results(run_id, metrics)
        
        results = repo.get_results(run_id)
        assert results is not None
        assert results.final_value == Decimal("11000")
        assert results.total_return == 0.10

    def test_save_results_preserves_holdings(self, repo):
        """Test that holdings are preserved correctly."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        metrics = make_metrics()
        
        repo.save_results(run_id, metrics)
        
        results = repo.get_results(run_id)
        assert results.holdings == {"SPY": Decimal("10.5"), "VOO": Decimal("5.25")}

    def test_save_results_upsert(self, repo):
        """Test that saving results twice updates."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        # Save first
        repo.save_results(run_id, make_metrics(final_value=Decimal("11000")))
        
        # Save again with different value
        repo.save_results(run_id, make_metrics(final_value=Decimal("12000")))
        
        results = repo.get_results(run_id)
        assert results.final_value == Decimal("12000")


class TestSaveTrades:
    """Tests for saving trades."""

    def test_save_trade_single(self, repo):
        """Test saving a single trade."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        trade = make_trade()
        
        repo.save_trade(run_id, trade)
        
        trades = repo.get_trades(run_id)
        assert len(trades) == 1
        assert trades[0].symbol == "SPY"
        assert trades[0].side == "buy"

    def test_save_trades_batch(self, repo):
        """Test saving multiple trades at once."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        trades = [
            make_trade(symbol="SPY"),
            make_trade(symbol="VOO"),
            make_trade(symbol="QQQ"),
        ]
        
        repo.save_trades(run_id, trades)
        
        saved_trades = repo.get_trades(run_id)
        assert len(saved_trades) == 3
        symbols = {t.symbol for t in saved_trades}
        assert symbols == {"SPY", "VOO", "QQQ"}

    def test_save_trades_empty_list(self, repo):
        """Test saving empty trade list does nothing."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        repo.save_trades(run_id, [])
        
        trades = repo.get_trades(run_id)
        assert len(trades) == 0


class TestGetRun:
    """Tests for retrieving run metadata."""

    def test_get_run_not_found(self, repo):
        """Test getting non-existent run."""
        result = repo.get_run("non-existent-id")
        assert result is None

    def test_get_run_has_created_at(self, repo):
        """Test that run has created_at timestamp."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        run = repo.get_run(run_id)
        
        assert "created_at" in run
        assert isinstance(run["created_at"], datetime)


class TestGetResults:
    """Tests for retrieving results."""

    def test_get_results_not_found(self, repo):
        """Test getting results for non-existent run."""
        result = repo.get_results("non-existent-id")
        assert result is None

    def test_get_results_preserves_decimal(self, repo):
        """Test that Decimal values are preserved."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000.50"),
        )
        metrics = BacktestMetrics(
            final_value=Decimal("11234.56"),
            total_return=0.123456,
            total_trades=5,
            total_invested=Decimal("10000.50"),
        )
        
        repo.save_results(run_id, metrics)
        
        results = repo.get_results(run_id)
        assert isinstance(results.final_value, Decimal)
        assert isinstance(results.total_invested, Decimal)


class TestGetTrades:
    """Tests for retrieving trades."""

    def test_get_trades_empty(self, repo):
        """Test getting trades when none exist."""
        trades = repo.get_trades("non-existent-id")
        assert trades == []

    def test_get_trades_ordered_by_time(self, repo):
        """Test that trades are ordered by timestamp."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )

        # Save trades with different timestamps
        trade1 = Trade.create_buy("SPY", Decimal("4500"), Decimal("450"),
                                  datetime(2024, 1, 15), "DCA")
        trade2 = Trade.create_buy("SPY", Decimal("4550"), Decimal("455"),
                                  datetime(2024, 1, 10), "DCA")  # Earlier

        repo.save_trade(run_id, trade1)
        repo.save_trade(run_id, trade2)

        trades = repo.get_trades(run_id)

        # Should be ordered by timestamp
        assert trades[0].timestamp < trades[1].timestamp


class TestListRuns:
    """Tests for listing runs."""

    def test_list_runs_empty(self, repo):
        """Test listing runs when none exist."""
        runs = repo.list_runs()
        assert runs == []

    def test_list_runs_basic(self, repo):
        """Test listing runs."""
        repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        repo.create_run(
            strategy_name="dip_buy_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        runs = repo.list_runs()
        
        assert len(runs) == 2

    def test_list_runs_filter_by_strategy(self, repo):
        """Test filtering runs by strategy name."""
        repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        repo.create_run(
            strategy_name="dip_buy_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        runs = repo.list_runs(strategy_name="simple_dca")
        
        assert len(runs) == 1
        assert runs[0]["strategy_name"] == "simple_dca"

    def test_list_runs_with_results(self, repo):
        """Test that list includes results when available."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        repo.save_results(run_id, make_metrics())
        
        runs = repo.list_runs()
        
        assert len(runs) == 1
        assert "final_value" in runs[0]
        assert "total_return" in runs[0]
        assert "total_trades" in runs[0]

    def test_list_runs_limit(self, repo):
        """Test that limit works."""
        for i in range(5):
            repo.create_run(
                strategy_name=f"strategy_{i}",
                config={},
                start_date=date(2023, 1, 1),
                end_date=date(2023, 12, 31),
                initial_cash=Decimal("10000"),
            )
        
        runs = repo.list_runs(limit=3)
        
        assert len(runs) == 3


class TestDeleteRun:
    """Tests for deleting runs."""

    def test_delete_run_basic(self, repo):
        """Test deleting a run."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        
        deleted = repo.delete_run(run_id)
        
        assert deleted is True
        assert repo.get_run(run_id) is None

    def test_delete_run_not_found(self, repo):
        """Test deleting non-existent run."""
        deleted = repo.delete_run("non-existent-id")
        assert deleted is False

    def test_delete_run_cascade(self, repo):
        """Test that deleting run also deletes results and trades."""
        run_id = repo.create_run(
            strategy_name="simple_dca",
            config={},
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_cash=Decimal("10000"),
        )
        repo.save_results(run_id, make_metrics())
        repo.save_trade(run_id, make_trade())
        
        repo.delete_run(run_id)
        
        assert repo.get_results(run_id) is None
        assert repo.get_trades(run_id) == []
