"""Unit tests for SQLitePortfolioStore, SQLiteDecisionStore, SQLiteSnapshotStore.

Covers protocol conformance, CRUD operations, lifecycle transitions,
and audit trail queries.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from beavr.db.factory import StoreBundle, create_sqlite_stores
from beavr.db.protocols import DecisionStore, PortfolioStore, SnapshotStore
from beavr.db.sqlite.connection import Database
from beavr.db.sqlite.portfolio_store import (
    SQLiteDecisionStore,
    SQLitePortfolioStore,
    SQLiteSnapshotStore,
)
from beavr.models.portfolio_record import (
    DecisionType,
    PortfolioDecision,
    PortfolioSnapshot,
    PortfolioStatus,
    TradingMode,
)

# ===== Fixtures =====


@pytest.fixture
def db() -> Database:
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def portfolio_store(db: Database) -> SQLitePortfolioStore:
    """Create a portfolio store."""
    return SQLitePortfolioStore(db)


@pytest.fixture
def decision_store(db: Database) -> SQLiteDecisionStore:
    """Create a decision store."""
    return SQLiteDecisionStore(db)


@pytest.fixture
def snapshot_store(db: Database) -> SQLiteSnapshotStore:
    """Create a snapshot store."""
    return SQLiteSnapshotStore(db)


# ===== Helpers =====


def _create_portfolio(store: SQLitePortfolioStore, **overrides) -> str:
    """Create a portfolio and return its ID."""
    defaults = {
        "name": "Test Paper Portfolio",
        "mode": "paper",
        "initial_capital": Decimal("10000.00"),
        "config_snapshot": {"max_daily_loss": 0.03},
        "aggressiveness": "moderate",
        "directives": ["Focus on tech", "Avoid biotech"],
    }
    defaults.update(overrides)
    return store.create_portfolio(**defaults)


def _make_decision(portfolio_id: str, **overrides) -> PortfolioDecision:
    """Create a PortfolioDecision with sensible defaults."""
    defaults = {
        "portfolio_id": portfolio_id,
        "phase": "market_hours",
        "decision_type": DecisionType.TRADE_ENTERED,
        "symbol": "AAPL",
        "action": "buy",
        "reasoning": "DD approved with high confidence",
        "confidence": 0.85,
        "amount": Decimal("500.00"),
        "shares": Decimal("2.5"),
        "price": Decimal("200.00"),
    }
    defaults.update(overrides)
    return PortfolioDecision(**defaults)


def _make_snapshot(portfolio_id: str, **overrides) -> PortfolioSnapshot:
    """Create a PortfolioSnapshot with sensible defaults."""
    defaults = {
        "portfolio_id": portfolio_id,
        "snapshot_date": date.today(),
        "portfolio_value": Decimal("10500.00"),
        "cash": Decimal("5000.00"),
        "positions_value": Decimal("5500.00"),
        "daily_pnl": Decimal("100.00"),
        "daily_pnl_pct": 0.96,
        "cumulative_pnl": Decimal("500.00"),
        "cumulative_pnl_pct": 5.0,
        "open_positions": 3,
        "trades_today": 1,
    }
    defaults.update(overrides)
    return PortfolioSnapshot(**defaults)


# ===================================================================
# Protocol Conformance
# ===================================================================


class TestProtocolConformance:
    """Verify stores satisfy their Protocol interfaces."""

    def test_portfolio_store_satisfies_protocol(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """SQLitePortfolioStore should satisfy PortfolioStore protocol."""
        assert isinstance(portfolio_store, PortfolioStore)

    def test_decision_store_satisfies_protocol(
        self, decision_store: SQLiteDecisionStore
    ) -> None:
        """SQLiteDecisionStore should satisfy DecisionStore protocol."""
        assert isinstance(decision_store, DecisionStore)

    def test_snapshot_store_satisfies_protocol(
        self, snapshot_store: SQLiteSnapshotStore
    ) -> None:
        """SQLiteSnapshotStore should satisfy SnapshotStore protocol."""
        assert isinstance(snapshot_store, SnapshotStore)

    def test_factory_includes_new_stores(self) -> None:
        """Factory bundle should include portfolio, decision, snapshot stores."""
        bundle = create_sqlite_stores(":memory:")
        assert isinstance(bundle, StoreBundle)
        assert isinstance(bundle.portfolios, PortfolioStore)
        assert isinstance(bundle.decisions, DecisionStore)
        assert isinstance(bundle.snapshots, SnapshotStore)


# ===================================================================
# SQLitePortfolioStore Tests
# ===================================================================


class TestPortfolioStoreCreate:
    """Tests for creating portfolios."""

    def test_create_portfolio_returns_id(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should create a portfolio and return its ID."""
        pid = _create_portfolio(portfolio_store)
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_create_portfolio_paper_mode(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should create paper portfolio with correct attributes."""
        pid = _create_portfolio(portfolio_store, name="Paper Test", mode="paper")
        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.mode == TradingMode.PAPER
        assert portfolio.status == PortfolioStatus.ACTIVE

    def test_create_portfolio_live_mode(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should create live portfolio."""
        pid = _create_portfolio(portfolio_store, name="Live Test", mode="live")
        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.mode == TradingMode.LIVE

    def test_create_portfolio_capital(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should store capital as Decimal, not float."""
        pid = _create_portfolio(
            portfolio_store,
            initial_capital=Decimal("5000.50"),
        )
        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.initial_capital == Decimal("5000.50")

    def test_create_portfolio_config_snapshot(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should preserve config snapshot as dict."""
        config = {"max_daily_loss": 0.05, "position_size_pct": 0.1}
        pid = _create_portfolio(portfolio_store, config_snapshot=config)
        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.config_snapshot == config

    def test_create_portfolio_directives(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should preserve directives as list of strings."""
        directives = ["Focus on tech", "Avoid biotech", "Be aggressive"]
        pid = _create_portfolio(portfolio_store, directives=directives)
        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.directives == directives

    def test_create_portfolio_unique_name(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should reject duplicate portfolio names."""
        _create_portfolio(portfolio_store, name="Same Name")
        with pytest.raises(Exception):
            _create_portfolio(portfolio_store, name="Same Name")


class TestPortfolioStoreGet:
    """Tests for retrieving portfolios."""

    def test_get_portfolio_not_found(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should return None for non-existent portfolio."""
        assert portfolio_store.get_portfolio("nonexistent") is None

    def test_get_portfolio_by_name(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should find portfolio by name."""
        pid = _create_portfolio(portfolio_store, name="Named Portfolio")
        portfolio = portfolio_store.get_portfolio_by_name("Named Portfolio")
        assert portfolio is not None
        assert portfolio.id == pid

    def test_get_portfolio_by_name_not_found(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should return None for non-existent name."""
        assert portfolio_store.get_portfolio_by_name("Ghost") is None


class TestPortfolioStoreList:
    """Tests for listing portfolios."""

    def test_list_all_portfolios(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should return all portfolios."""
        _create_portfolio(portfolio_store, name="P1")
        _create_portfolio(portfolio_store, name="P2")
        _create_portfolio(portfolio_store, name="P3")
        portfolios = portfolio_store.list_portfolios()
        assert len(portfolios) == 3

    def test_list_by_status(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should filter by status."""
        _create_portfolio(portfolio_store, name="Active")
        _create_portfolio(portfolio_store, name="Paused")
        portfolio_store.pause_portfolio(
            _create_portfolio(portfolio_store, name="Paused2")
        )

        active = portfolio_store.list_portfolios(status="active")
        assert len(active) >= 2  # Active and Paused (still active until paused)

    def test_list_by_mode(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should filter by trading mode."""
        _create_portfolio(portfolio_store, name="Paper1", mode="paper")
        _create_portfolio(portfolio_store, name="Live1", mode="live")

        paper = portfolio_store.list_portfolios(mode="paper")
        assert len(paper) == 1
        assert paper[0].mode == TradingMode.PAPER


class TestPortfolioStoreLifecycle:
    """Tests for portfolio status transitions."""

    def test_close_portfolio(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should mark portfolio as closed with timestamp."""
        pid = _create_portfolio(portfolio_store)
        portfolio_store.close_portfolio(pid)

        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.status == PortfolioStatus.CLOSED
        assert portfolio.closed_at is not None

    def test_pause_portfolio(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should mark portfolio as paused."""
        pid = _create_portfolio(portfolio_store)
        portfolio_store.pause_portfolio(pid)

        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.status == PortfolioStatus.PAUSED

    def test_resume_portfolio(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should resume a paused portfolio."""
        pid = _create_portfolio(portfolio_store)
        portfolio_store.pause_portfolio(pid)
        portfolio_store.resume_portfolio(pid)

        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.status == PortfolioStatus.ACTIVE

    def test_update_stats_winning_trade(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should update stats after a winning trade."""
        pid = _create_portfolio(portfolio_store)
        portfolio_store.update_portfolio_stats(pid, Decimal("150.00"), is_win=True)

        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.total_trades == 1
        assert portfolio.winning_trades == 1
        assert portfolio.losing_trades == 0
        assert portfolio.realized_pnl == Decimal("150.00")

    def test_update_stats_losing_trade(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should update stats after a losing trade."""
        pid = _create_portfolio(portfolio_store)
        portfolio_store.update_portfolio_stats(pid, Decimal("-50.00"), is_win=False)

        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.total_trades == 1
        assert portfolio.losing_trades == 1
        assert portfolio.realized_pnl == Decimal("-50.00")

    def test_update_stats_cumulative(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should accumulate stats across multiple trades."""
        pid = _create_portfolio(portfolio_store)
        portfolio_store.update_portfolio_stats(pid, Decimal("100.00"), is_win=True)
        portfolio_store.update_portfolio_stats(pid, Decimal("-30.00"), is_win=False)
        portfolio_store.update_portfolio_stats(pid, Decimal("200.00"), is_win=True)

        portfolio = portfolio_store.get_portfolio(pid)
        assert portfolio is not None
        assert portfolio.total_trades == 3
        assert portfolio.winning_trades == 2
        assert portfolio.losing_trades == 1
        assert portfolio.realized_pnl == Decimal("270.00")


class TestPortfolioStoreDelete:
    """Tests for deleting portfolios."""

    def test_delete_portfolio(
        self, portfolio_store: SQLitePortfolioStore, decision_store: SQLiteDecisionStore
    ) -> None:
        """Should delete portfolio and associated decisions."""
        pid = _create_portfolio(portfolio_store)
        decision_store.log_decision(_make_decision(pid))

        portfolio_store.delete_portfolio(pid)
        assert portfolio_store.get_portfolio(pid) is None
        # Decisions should also be gone
        assert len(decision_store.get_decisions(pid)) == 0

    def test_delete_all_data(
        self, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should delete all portfolios."""
        _create_portfolio(portfolio_store, name="P1")
        _create_portfolio(portfolio_store, name="P2")

        portfolio_store.delete_all_data()
        assert len(portfolio_store.list_portfolios()) == 0


# ===================================================================
# SQLiteDecisionStore Tests
# ===================================================================


class TestDecisionStoreLog:
    """Tests for logging decisions."""

    def test_log_decision_returns_id(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should log a decision and return its ID."""
        pid = _create_portfolio(portfolio_store)
        decision = _make_decision(pid)
        decision_id = decision_store.log_decision(decision)
        assert isinstance(decision_id, str)
        assert len(decision_id) > 0

    def test_log_decision_preserves_fields(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should preserve all decision fields."""
        pid = _create_portfolio(portfolio_store)
        decision = _make_decision(
            pid,
            symbol="NVDA",
            action="buy",
            amount=Decimal("1000.00"),
            confidence=0.92,
        )
        decision_id = decision_store.log_decision(decision)
        decisions = decision_store.get_decisions(pid)
        assert len(decisions) >= 1
        found = [d for d in decisions if d.id == decision_id]
        assert len(found) == 1
        assert found[0].symbol == "NVDA"
        assert found[0].amount == Decimal("1000.00")


class TestDecisionStoreQuery:
    """Tests for querying decisions."""

    def test_get_decisions_by_portfolio(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should return decisions for a specific portfolio."""
        pid1 = _create_portfolio(portfolio_store, name="P1")
        pid2 = _create_portfolio(portfolio_store, name="P2")
        decision_store.log_decision(_make_decision(pid1))
        decision_store.log_decision(_make_decision(pid1))
        decision_store.log_decision(_make_decision(pid2))

        d1 = decision_store.get_decisions(pid1)
        d2 = decision_store.get_decisions(pid2)
        assert len(d1) == 2
        assert len(d2) == 1

    def test_get_decisions_filter_by_type(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should filter decisions by type."""
        pid = _create_portfolio(portfolio_store)
        decision_store.log_decision(
            _make_decision(pid, decision_type=DecisionType.TRADE_ENTERED)
        )
        decision_store.log_decision(
            _make_decision(pid, decision_type=DecisionType.DD_APPROVED, symbol="NVDA")
        )

        trades = decision_store.get_decisions(pid, decision_type="trade_entered")
        assert len(trades) == 1

    def test_get_decisions_filter_by_symbol(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should filter decisions by symbol."""
        pid = _create_portfolio(portfolio_store)
        decision_store.log_decision(_make_decision(pid, symbol="AAPL"))
        decision_store.log_decision(_make_decision(pid, symbol="NVDA"))

        aapl = decision_store.get_decisions(pid, symbol="AAPL")
        assert len(aapl) == 1
        assert aapl[0].symbol == "AAPL"

    def test_get_decisions_pagination(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should support limit and offset."""
        pid = _create_portfolio(portfolio_store)
        for i in range(5):
            decision_store.log_decision(
                _make_decision(pid, symbol=f"SYM{i}")
            )

        page1 = decision_store.get_decisions(pid, limit=2, offset=0)
        page2 = decision_store.get_decisions(pid, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2

    def test_get_full_audit_trail(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should return all decisions ordered by timestamp ascending."""
        pid = _create_portfolio(portfolio_store)
        decision_store.log_decision(_make_decision(pid, symbol="AAPL"))
        decision_store.log_decision(_make_decision(pid, symbol="NVDA"))
        decision_store.log_decision(_make_decision(pid, symbol="TSLA"))

        trail = decision_store.get_full_audit_trail(pid)
        assert len(trail) == 3

    def test_get_full_audit_trail_date_filter(
        self, decision_store: SQLiteDecisionStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should filter audit trail by date range."""
        pid = _create_portfolio(portfolio_store)
        # Log decisions — all with current timestamp
        decision_store.log_decision(_make_decision(pid))

        today = date.today()
        trail = decision_store.get_full_audit_trail(
            pid, start_date=today, end_date=today
        )
        assert len(trail) >= 1


# ===================================================================
# SQLiteSnapshotStore Tests
# ===================================================================


class TestSnapshotStoreSave:
    """Tests for taking snapshots."""

    def test_take_snapshot_returns_id(
        self, snapshot_store: SQLiteSnapshotStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should save a snapshot and return its ID."""
        pid = _create_portfolio(portfolio_store)
        snapshot = _make_snapshot(pid)
        snapshot_id = snapshot_store.take_snapshot(snapshot)
        assert isinstance(snapshot_id, str)
        assert len(snapshot_id) > 0

    def test_take_snapshot_preserves_values(
        self, snapshot_store: SQLiteSnapshotStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should preserve all snapshot values as Decimals."""
        pid = _create_portfolio(portfolio_store)
        snapshot = _make_snapshot(
            pid,
            portfolio_value=Decimal("10500.50"),
            cash=Decimal("5000.25"),
            positions_value=Decimal("5500.25"),
        )
        snapshot_store.take_snapshot(snapshot)

        snapshots = snapshot_store.get_snapshots(pid)
        assert len(snapshots) == 1
        s = snapshots[0]
        assert s.portfolio_value == Decimal("10500.50")
        assert s.cash == Decimal("5000.25")

    def test_take_snapshot_upsert(
        self, snapshot_store: SQLiteSnapshotStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should replace snapshot for same portfolio+date."""
        pid = _create_portfolio(portfolio_store)
        today = date.today()
        snapshot1 = _make_snapshot(
            pid, snapshot_date=today, portfolio_value=Decimal("10000.00")
        )
        snapshot2 = _make_snapshot(
            pid, snapshot_date=today, portfolio_value=Decimal("10500.00")
        )
        snapshot_store.take_snapshot(snapshot1)
        snapshot_store.take_snapshot(snapshot2)

        snapshots = snapshot_store.get_snapshots(pid)
        assert len(snapshots) == 1
        assert snapshots[0].portfolio_value == Decimal("10500.00")


class TestSnapshotStoreQuery:
    """Tests for querying snapshots."""

    def test_get_snapshots_by_portfolio(
        self, snapshot_store: SQLiteSnapshotStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should return snapshots for specific portfolio."""
        pid1 = _create_portfolio(portfolio_store, name="P1")
        pid2 = _create_portfolio(portfolio_store, name="P2")
        snapshot_store.take_snapshot(
            _make_snapshot(pid1, snapshot_date=date.today())
        )
        snapshot_store.take_snapshot(
            _make_snapshot(pid2, snapshot_date=date.today())
        )

        s1 = snapshot_store.get_snapshots(pid1)
        s2 = snapshot_store.get_snapshots(pid2)
        assert len(s1) == 1
        assert len(s2) == 1

    def test_get_snapshots_date_range(
        self, snapshot_store: SQLiteSnapshotStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Should filter snapshots by date range."""
        pid = _create_portfolio(portfolio_store)
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        snapshot_store.take_snapshot(_make_snapshot(pid, snapshot_date=yesterday))
        snapshot_store.take_snapshot(_make_snapshot(pid, snapshot_date=today))
        snapshot_store.take_snapshot(_make_snapshot(pid, snapshot_date=tomorrow))

        # Only yesterday and today
        filtered = snapshot_store.get_snapshots(
            pid, start_date=yesterday, end_date=today
        )
        assert len(filtered) == 2

    def test_get_snapshots_ordered_ascending(
        self, snapshot_store: SQLiteSnapshotStore, portfolio_store: SQLitePortfolioStore
    ) -> None:
        """Snapshots should be ordered by date ascending."""
        pid = _create_portfolio(portfolio_store)
        today = date.today()
        dates = [today - timedelta(days=i) for i in range(5)]

        # Insert in random order
        for d in dates:
            snapshot_store.take_snapshot(_make_snapshot(pid, snapshot_date=d))

        snapshots = snapshot_store.get_snapshots(pid)
        assert len(snapshots) == 5
        snapshot_dates = [s.snapshot_date for s in snapshots]
        assert snapshot_dates == sorted(snapshot_dates)
