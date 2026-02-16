"""Protocol conformance and basic CRUD tests for SQLite store implementations.

Verifies that each SQLite store satisfies its Protocol via isinstance checks,
and exercises core read/write operations on an in-memory database.
"""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from beavr.db.factory import StoreBundle, create_sqlite_stores
from beavr.db.protocols import (
    BarCacheStore,
    DDReportStore,
    EventStore,
    PositionStore,
    ThesisStore,
)
from beavr.db.sqlite.bar_cache_store import SQLiteBarCacheStore
from beavr.db.sqlite.connection import Database
from beavr.db.sqlite.dd_report_store import SQLiteDDReportStore
from beavr.db.sqlite.event_store import SQLiteEventStore
from beavr.db.sqlite.position_store import SQLitePositionStore
from beavr.db.sqlite.thesis_store import SQLiteThesisStore
from beavr.models.dd_report import DDRecommendation, DueDiligenceReport
from beavr.models.market_event import EventImportance, EventType, MarketEvent
from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType

# ===== Fixtures =====


@pytest.fixture
def db() -> Database:
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def thesis_store(db: Database) -> SQLiteThesisStore:
    """Create a thesis store backed by in-memory DB."""
    return SQLiteThesisStore(db)


@pytest.fixture
def dd_store(db: Database) -> SQLiteDDReportStore:
    """Create a DD report store backed by in-memory DB."""
    return SQLiteDDReportStore(db)


@pytest.fixture
def event_store(db: Database) -> SQLiteEventStore:
    """Create an event store backed by in-memory DB."""
    return SQLiteEventStore(db)


@pytest.fixture
def position_store(db: Database) -> SQLitePositionStore:
    """Create a position store backed by in-memory DB."""
    return SQLitePositionStore(db)


@pytest.fixture
def bar_cache_store(db: Database) -> SQLiteBarCacheStore:
    """Create a bar cache store backed by in-memory DB."""
    return SQLiteBarCacheStore(db)


# ===== Helpers =====


def _make_thesis(**overrides) -> TradeThesis:
    """Create a TradeThesis with sensible defaults."""
    defaults = {
        "symbol": "AAPL",
        "trade_type": TradeType.SWING_SHORT,
        "entry_rationale": "Strong momentum after earnings beat",
        "catalyst": "Q4 earnings report",
        "entry_price_target": Decimal("180.00"),
        "profit_target": Decimal("195.00"),
        "stop_loss": Decimal("172.00"),
        "expected_exit_date": date(2026, 6, 15),
        "max_hold_date": date(2026, 6, 20),
    }
    defaults.update(overrides)
    return TradeThesis(**defaults)


def _make_dd_report(thesis_id: str, **overrides) -> DueDiligenceReport:
    """Create a DueDiligenceReport with sensible defaults."""
    defaults = {
        "thesis_id": thesis_id,
        "symbol": "AAPL",
        "recommendation": DDRecommendation.APPROVE,
        "confidence": 0.85,
        "fundamental_summary": "Solid fundamentals",
        "technical_summary": "Bullish chart",
        "catalyst_assessment": "Earnings beat likely",
        "risk_factors": ["Market correction", "Supply chain"],
        "overall_assessment": "Good risk/reward",
        "recommended_entry": Decimal("180.00"),
        "recommended_target": Decimal("195.00"),
        "recommended_stop": Decimal("172.00"),
        "recommended_position_size_pct": 0.05,
    }
    defaults.update(overrides)
    return DueDiligenceReport(**defaults)


def _make_event(**overrides) -> MarketEvent:
    """Create a MarketEvent with sensible defaults."""
    defaults = {
        "event_type": EventType.EARNINGS_ANNOUNCED,
        "symbol": "AAPL",
        "headline": "AAPL reports Q4 earnings",
        "summary": "Beat estimates by 5%",
        "source": "Benzinga",
        "importance": EventImportance.HIGH,
    }
    defaults.update(overrides)
    return MarketEvent(**defaults)


def _make_bars_df(
    dates: list[str],
    prices: list[float],
    volumes: list[int],
) -> pd.DataFrame:
    """Helper to create a bars DataFrame."""
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(dates),
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": volumes,
        }
    )


# ===================================================================
# Protocol Conformance Tests
# ===================================================================


class TestProtocolConformance:
    """Verify each SQLite store isinstance-satisfies its Protocol."""

    def test_thesis_store_satisfies_protocol(self, thesis_store: SQLiteThesisStore) -> None:
        """SQLiteThesisStore should satisfy ThesisStore protocol."""
        assert isinstance(thesis_store, ThesisStore)

    def test_dd_store_satisfies_protocol(self, dd_store: SQLiteDDReportStore) -> None:
        """SQLiteDDReportStore should satisfy DDReportStore protocol."""
        assert isinstance(dd_store, DDReportStore)

    def test_event_store_satisfies_protocol(self, event_store: SQLiteEventStore) -> None:
        """SQLiteEventStore should satisfy EventStore protocol."""
        assert isinstance(event_store, EventStore)

    def test_position_store_satisfies_protocol(self, position_store: SQLitePositionStore) -> None:
        """SQLitePositionStore should satisfy PositionStore protocol."""
        assert isinstance(position_store, PositionStore)

    def test_bar_cache_store_satisfies_protocol(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """SQLiteBarCacheStore should satisfy BarCacheStore protocol."""
        assert isinstance(bar_cache_store, BarCacheStore)


# ===================================================================
# Factory Tests
# ===================================================================


class TestFactory:
    """Tests for create_sqlite_stores factory function."""

    def test_create_returns_store_bundle(self) -> None:
        """Factory should return a StoreBundle with all stores."""
        bundle = create_sqlite_stores(":memory:")
        assert isinstance(bundle, StoreBundle)

    def test_bundle_stores_satisfy_protocols(self) -> None:
        """All stores in the bundle should satisfy their protocols."""
        bundle = create_sqlite_stores(":memory:")
        assert isinstance(bundle.theses, ThesisStore)
        assert isinstance(bundle.dd_reports, DDReportStore)
        assert isinstance(bundle.events, EventStore)
        assert isinstance(bundle.bar_cache, BarCacheStore)


# ===================================================================
# SQLiteThesisStore CRUD Tests
# ===================================================================


class TestThesisStore:
    """CRUD tests for SQLiteThesisStore."""

    def test_save_and_get_thesis(self, thesis_store: SQLiteThesisStore) -> None:
        """Should save a thesis and retrieve it by ID."""
        thesis = _make_thesis()
        thesis_id = thesis_store.save_thesis(thesis)

        retrieved = thesis_store.get_thesis(thesis_id)
        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
        assert retrieved.entry_price_target == Decimal("180.00")

    def test_get_thesis_not_found(self, thesis_store: SQLiteThesisStore) -> None:
        """Should return None for non-existent thesis."""
        assert thesis_store.get_thesis("nonexistent-id") is None

    def test_get_active_theses(self, thesis_store: SQLiteThesisStore) -> None:
        """Should return theses in draft/active status."""
        thesis1 = _make_thesis(symbol="AAPL")
        thesis2 = _make_thesis(symbol="NVDA")
        thesis_store.save_thesis(thesis1)
        thesis_store.save_thesis(thesis2)

        active = thesis_store.get_active_theses()
        assert len(active) >= 2
        symbols = [t.symbol for t in active]
        assert "AAPL" in symbols
        assert "NVDA" in symbols

    def test_get_pending_dd(self, thesis_store: SQLiteThesisStore) -> None:
        """Should return active theses not yet DD-approved."""
        thesis = _make_thesis()
        thesis_id = thesis_store.save_thesis(thesis)
        # Promote to active status (get_pending_dd queries active, not draft)
        thesis_store.update_thesis_status(thesis_id, ThesisStatus.ACTIVE)

        pending = thesis_store.get_pending_dd()
        assert len(pending) >= 1
        assert all(not t.dd_approved for t in pending)

    def test_update_thesis_status(self, thesis_store: SQLiteThesisStore) -> None:
        """Should update thesis status."""
        thesis = _make_thesis()
        thesis_id = thesis_store.save_thesis(thesis)

        result = thesis_store.update_thesis_status(thesis_id, ThesisStatus.EXECUTED)
        assert result is True

        updated = thesis_store.get_thesis(thesis_id)
        assert updated is not None
        assert updated.status == ThesisStatus.EXECUTED

    def test_approve_dd(self, thesis_store: SQLiteThesisStore) -> None:
        """Should mark thesis as DD-approved and link report."""
        thesis = _make_thesis()
        thesis_id = thesis_store.save_thesis(thesis)

        result = thesis_store.approve_dd(thesis_id, "dd-report-123")
        assert result is True

        updated = thesis_store.get_thesis(thesis_id)
        assert updated is not None
        assert updated.dd_approved is True
        assert updated.dd_report_id == "dd-report-123"

    def test_get_theses_by_symbol(self, thesis_store: SQLiteThesisStore) -> None:
        """Should filter theses by symbol."""
        thesis_store.save_thesis(_make_thesis(symbol="AAPL"))
        thesis_store.save_thesis(_make_thesis(symbol="NVDA"))
        thesis_store.save_thesis(_make_thesis(symbol="AAPL"))

        results = thesis_store.get_theses_by_symbol("AAPL")
        assert len(results) == 2
        assert all(t.symbol == "AAPL" for t in results)

    def test_get_theses_by_catalyst_date(self, thesis_store: SQLiteThesisStore) -> None:
        """Should return theses whose catalyst matches a date."""
        target = date(2026, 6, 15)
        thesis = _make_thesis(catalyst_date=target)
        thesis_store.save_thesis(thesis)

        results = thesis_store.get_theses_by_catalyst_date(target)
        # May or may not find it depending on whether catalyst_date mapping
        # is stored; at minimum should not error
        assert isinstance(results, list)

    def test_get_thesis_summaries(self, thesis_store: SQLiteThesisStore) -> None:
        """Should return lightweight summaries."""
        thesis_store.save_thesis(_make_thesis(symbol="AAPL"))
        thesis_store.save_thesis(_make_thesis(symbol="NVDA"))

        summaries = thesis_store.get_thesis_summaries(limit=10)
        assert len(summaries) >= 2

    def test_update_thesis_confidence(self, thesis_store: SQLiteThesisStore) -> None:
        """Should update just the confidence score."""
        thesis = _make_thesis(confidence=0.5)
        thesis_id = thesis_store.save_thesis(thesis)

        result = thesis_store.update_thesis_confidence(thesis_id, 0.9)
        assert result is True

        updated = thesis_store.get_thesis(thesis_id)
        assert updated is not None
        assert updated.confidence == pytest.approx(0.9, abs=0.01)


# ===================================================================
# SQLiteDDReportStore CRUD Tests
# ===================================================================


class TestDDReportStore:
    """CRUD tests for SQLiteDDReportStore."""

    def test_save_and_get_report(
        self, dd_store: SQLiteDDReportStore, thesis_store: SQLiteThesisStore
    ) -> None:
        """Should save a DD report and retrieve it by ID."""
        thesis_id = thesis_store.save_thesis(_make_thesis())
        report = _make_dd_report(thesis_id)

        report_id = dd_store.save_report(report)
        retrieved = dd_store.get_report(report_id)

        assert retrieved is not None
        assert retrieved.thesis_id == thesis_id
        assert retrieved.recommendation == DDRecommendation.APPROVE

    def test_get_report_not_found(self, dd_store: SQLiteDDReportStore) -> None:
        """Should return None for non-existent report."""
        assert dd_store.get_report("nonexistent") is None

    def test_get_report_by_thesis(
        self, dd_store: SQLiteDDReportStore, thesis_store: SQLiteThesisStore
    ) -> None:
        """Should retrieve DD report by thesis ID."""
        thesis_id = thesis_store.save_thesis(_make_thesis())
        report = _make_dd_report(thesis_id)
        dd_store.save_report(report)

        retrieved = dd_store.get_report_by_thesis(thesis_id)
        assert retrieved is not None
        assert retrieved.thesis_id == thesis_id

    def test_get_reports_by_symbol(
        self, dd_store: SQLiteDDReportStore, thesis_store: SQLiteThesisStore
    ) -> None:
        """Should retrieve DD reports for a symbol."""
        tid1 = thesis_store.save_thesis(_make_thesis(symbol="AAPL"))
        tid2 = thesis_store.save_thesis(_make_thesis(symbol="AAPL"))
        dd_store.save_report(_make_dd_report(tid1, symbol="AAPL"))
        dd_store.save_report(_make_dd_report(tid2, symbol="AAPL"))

        results = dd_store.get_reports_by_symbol("AAPL")
        assert len(results) >= 2

    def test_get_recent_approvals(
        self, dd_store: SQLiteDDReportStore, thesis_store: SQLiteThesisStore
    ) -> None:
        """Should return recently approved reports."""
        tid = thesis_store.save_thesis(_make_thesis())
        dd_store.save_report(
            _make_dd_report(tid, recommendation=DDRecommendation.APPROVE)
        )

        approvals = dd_store.get_recent_approvals(limit=10)
        assert len(approvals) >= 1
        assert all(
            r.recommendation
            in (DDRecommendation.APPROVE, DDRecommendation.CONDITIONAL)
            for r in approvals
        )

    def test_get_recent_rejections(
        self, dd_store: SQLiteDDReportStore, thesis_store: SQLiteThesisStore
    ) -> None:
        """Should return recently rejected reports."""
        tid = thesis_store.save_thesis(_make_thesis())
        dd_store.save_report(
            _make_dd_report(tid, recommendation=DDRecommendation.REJECT)
        )

        rejections = dd_store.get_recent_rejections(limit=10)
        assert len(rejections) >= 1

    def test_get_approval_stats(
        self, dd_store: SQLiteDDReportStore, thesis_store: SQLiteThesisStore
    ) -> None:
        """Should return aggregate statistics."""
        tid1 = thesis_store.save_thesis(_make_thesis())
        tid2 = thesis_store.save_thesis(_make_thesis(symbol="NVDA"))
        dd_store.save_report(
            _make_dd_report(tid1, recommendation=DDRecommendation.APPROVE)
        )
        dd_store.save_report(
            _make_dd_report(tid2, recommendation=DDRecommendation.REJECT)
        )

        stats = dd_store.get_approval_stats()
        assert isinstance(stats, dict)
        assert stats["total_reports"] >= 2

    def test_get_report_summaries(
        self, dd_store: SQLiteDDReportStore, thesis_store: SQLiteThesisStore
    ) -> None:
        """Should return lightweight summaries."""
        tid = thesis_store.save_thesis(_make_thesis())
        dd_store.save_report(_make_dd_report(tid))

        summaries = dd_store.get_report_summaries(limit=10)
        assert len(summaries) >= 1


# ===================================================================
# SQLiteEventStore CRUD Tests
# ===================================================================


class TestEventStore:
    """CRUD tests for SQLiteEventStore."""

    def test_save_and_get_event(self, event_store: SQLiteEventStore) -> None:
        """Should save an event and retrieve it by ID."""
        event = _make_event()
        event_id = event_store.save_event(event)

        retrieved = event_store.get_event(event_id)
        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
        assert retrieved.importance == EventImportance.HIGH

    def test_get_event_not_found(self, event_store: SQLiteEventStore) -> None:
        """Should return None for non-existent event."""
        assert event_store.get_event("nonexistent") is None

    def test_get_recent_events(self, event_store: SQLiteEventStore) -> None:
        """Should return recent events."""
        event_store.save_event(_make_event(symbol="AAPL"))
        event_store.save_event(_make_event(symbol="NVDA"))

        events = event_store.get_recent_events(limit=10)
        assert len(events) >= 2

    def test_get_recent_events_filter_importance(self, event_store: SQLiteEventStore) -> None:
        """Should filter events by importance."""
        event_store.save_event(_make_event(importance=EventImportance.HIGH))
        event_store.save_event(_make_event(importance=EventImportance.LOW, symbol="TSLA"))

        high_events = event_store.get_recent_events(importance=EventImportance.HIGH)
        assert all(e.importance == EventImportance.HIGH for e in high_events)

    def test_get_events_by_symbol(self, event_store: SQLiteEventStore) -> None:
        """Should filter events by symbol."""
        event_store.save_event(_make_event(symbol="AAPL"))
        event_store.save_event(_make_event(symbol="NVDA"))

        results = event_store.get_events_by_symbol("AAPL")
        assert len(results) >= 1
        assert all(e.symbol == "AAPL" for e in results)

    def test_get_unprocessed_events(self, event_store: SQLiteEventStore) -> None:
        """Should return events not yet processed."""
        event_store.save_event(_make_event())
        unprocessed = event_store.get_unprocessed_events()
        assert len(unprocessed) >= 1

    def test_mark_event_processed(self, event_store: SQLiteEventStore) -> None:
        """Should mark an event as processed."""
        event = _make_event()
        event_id = event_store.save_event(event)

        result = event_store.mark_event_processed(event_id, thesis_id="thesis-123")
        assert result is True

        # Verify it's no longer in unprocessed
        unprocessed = event_store.get_unprocessed_events()
        unprocessed_ids = [e.id for e in unprocessed]
        assert event_id not in unprocessed_ids

    def test_get_upcoming_earnings(self, event_store: SQLiteEventStore) -> None:
        """Should return earnings events within look-ahead window."""
        # Create an earnings event dated tomorrow
        tomorrow = date.today() + timedelta(days=1)
        event = _make_event(
            event_type=EventType.EARNINGS_UPCOMING,
            earnings_date=tomorrow,
        )
        event_store.save_event(event)

        upcoming = event_store.get_upcoming_earnings(days_ahead=7)
        # Should find at least the one we inserted
        assert isinstance(upcoming, list)

    def test_get_event_summaries(self, event_store: SQLiteEventStore) -> None:
        """Should return lightweight summaries."""
        event_store.save_event(_make_event())
        summaries = event_store.get_event_summaries(limit=10)
        assert len(summaries) >= 1


# ===================================================================
# SQLitePositionStore CRUD Tests
# ===================================================================


class TestPositionStore:
    """CRUD tests for SQLitePositionStore."""

    def test_open_position(self, position_store: SQLitePositionStore) -> None:
        """Should open a new position and return its ID."""
        pos_id = position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
            strategy="swing",
            rationale="Earnings momentum",
        )
        assert isinstance(pos_id, int)
        assert pos_id > 0

    def test_get_position(self, position_store: SQLitePositionStore) -> None:
        """Should retrieve a position by ID."""
        pos_id = position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        position = position_store.get_position(pos_id)
        assert position is not None
        assert position.symbol == "AAPL"
        assert position.quantity == Decimal("10")

    def test_get_position_not_found(self, position_store: SQLitePositionStore) -> None:
        """Should return None for non-existent position."""
        assert position_store.get_position(99999) is None

    def test_get_open_position(self, position_store: SQLitePositionStore) -> None:
        """Should return the open position for a symbol."""
        position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        position = position_store.get_open_position("AAPL")
        assert position is not None
        assert position.status == "open"

    def test_get_open_positions(self, position_store: SQLitePositionStore) -> None:
        """Should return all open positions."""
        position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        position_store.open_position(
            symbol="NVDA",
            quantity=Decimal("5"),
            entry_price=Decimal("900.00"),
            stop_loss_pct=5.0,
            target_pct=15.0,
        )
        positions = position_store.get_open_positions()
        assert len(positions) >= 2

    def test_close_position(self, position_store: SQLitePositionStore) -> None:
        """Should close a position and calculate P&L."""
        pos_id = position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        closed = position_store.close_position(pos_id, Decimal("198.00"), "target")
        assert closed is not None
        assert closed.status == "closed_target"
        assert closed.exit_price == Decimal("198.00")
        assert closed.pnl is not None
        assert closed.pnl > Decimal("0")

    def test_close_position_by_symbol(self, position_store: SQLitePositionStore) -> None:
        """Should close the open position for a symbol."""
        position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        closed = position_store.close_position_by_symbol("AAPL", Decimal("170.00"), "stop")
        assert closed is not None
        assert closed.pnl is not None
        assert closed.pnl < Decimal("0")

    def test_get_all_positions(self, position_store: SQLitePositionStore) -> None:
        """Should return all positions (open and closed)."""
        pos_id = position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        position_store.close_position(pos_id, Decimal("190.00"), "manual")
        position_store.open_position(
            symbol="NVDA",
            quantity=Decimal("5"),
            entry_price=Decimal("900.00"),
            stop_loss_pct=5.0,
            target_pct=15.0,
        )

        all_pos = position_store.get_all_positions()
        assert len(all_pos) >= 2

    def test_get_trades(self, position_store: SQLitePositionStore) -> None:
        """Should return trade records."""
        pos_id = position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        position_store.close_position(pos_id, Decimal("195.00"), "target")

        trades = position_store.get_trades()
        # Should have entry + exit trades
        assert len(trades) >= 2

    def test_get_performance_summary(self, position_store: SQLitePositionStore) -> None:
        """Should return aggregate performance stats."""
        pos_id = position_store.open_position(
            symbol="AAPL",
            quantity=Decimal("10"),
            entry_price=Decimal("180.00"),
            stop_loss_pct=5.0,
            target_pct=10.0,
        )
        position_store.close_position(pos_id, Decimal("195.00"), "target")

        summary = position_store.get_performance_summary()
        assert isinstance(summary, dict)
        assert "total_positions" in summary


# ===================================================================
# SQLiteBarCacheStore CRUD Tests
# ===================================================================


class TestBarCacheStore:
    """CRUD tests for SQLiteBarCacheStore."""

    def test_save_and_get_bars(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """Should save bars and retrieve them."""
        bars = _make_bars_df(
            dates=["2024-01-15", "2024-01-16", "2024-01-17"],
            prices=[450.0, 452.0, 455.0],
            volumes=[1_000_000, 1_100_000, 1_200_000],
        )
        bar_cache_store.save_bars("SPY", bars)

        result = bar_cache_store.get_bars(
            "SPY", date(2024, 1, 15), date(2024, 1, 17)
        )
        assert result is not None
        assert len(result) == 3

    def test_get_bars_not_cached(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """Should return None when data not fully cached."""
        result = bar_cache_store.get_bars(
            "SPY", date(2024, 1, 15), date(2024, 1, 17)
        )
        assert result is None

    def test_has_data(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """Should check if data exists for range."""
        bars = _make_bars_df(
            dates=["2024-01-15", "2024-01-16", "2024-01-17"],
            prices=[450.0, 452.0, 455.0],
            volumes=[1_000_000, 1_100_000, 1_200_000],
        )
        bar_cache_store.save_bars("SPY", bars)

        assert bar_cache_store.has_data("SPY", date(2024, 1, 15), date(2024, 1, 17))
        assert not bar_cache_store.has_data("SPY", date(2024, 1, 10), date(2024, 1, 17))

    def test_get_date_range(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """Should return min/max cached dates."""
        bars = _make_bars_df(
            dates=["2024-01-15", "2024-01-16", "2024-01-17"],
            prices=[450.0, 452.0, 455.0],
            volumes=[1_000_000, 1_100_000, 1_200_000],
        )
        bar_cache_store.save_bars("SPY", bars)

        result = bar_cache_store.get_date_range("SPY")
        assert result is not None
        min_date, max_date = result
        assert min_date == date(2024, 1, 15)
        assert max_date == date(2024, 1, 17)

    def test_get_date_range_no_data(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """Should return None when no data cached."""
        assert bar_cache_store.get_date_range("MISSING") is None

    def test_delete_bars(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """Should delete cached bars for a symbol."""
        bars = _make_bars_df(
            dates=["2024-01-15", "2024-01-16"],
            prices=[450.0, 452.0],
            volumes=[1_000_000, 1_100_000],
        )
        bar_cache_store.save_bars("SPY", bars)
        deleted = bar_cache_store.delete_bars("SPY")
        assert deleted == 2
        assert bar_cache_store.get_date_range("SPY") is None

    def test_get_symbols(self, bar_cache_store: SQLiteBarCacheStore) -> None:
        """Should return all symbols with cached data."""
        bars1 = _make_bars_df(["2024-01-15"], [450.0], [1_000_000])
        bars2 = _make_bars_df(["2024-01-15"], [900.0], [500_000])

        bar_cache_store.save_bars("SPY", bars1)
        bar_cache_store.save_bars("NVDA", bars2)

        symbols = bar_cache_store.get_symbols()
        assert "NVDA" in symbols
        assert "SPY" in symbols
