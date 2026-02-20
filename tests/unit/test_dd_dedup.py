"""Tests for DD deduplication on restart.

Verifies that the orchestrator does not re-run DD for symbols that
already have reports from today, even when dd_runs_today is empty in
the loaded state (e.g. after a restart with a stale state file).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import pytest

from beavr.db import Database
from beavr.db.dd_reports_repo import DDReportsRepository
from beavr.models.dd_report import DDRecommendation, DueDiligenceReport
from beavr.orchestrator import V2AutonomousOrchestrator, V2Config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dd_report(
    symbol: str,
    timestamp: Optional[datetime] = None,
    recommendation: DDRecommendation = DDRecommendation.APPROVE,
) -> DueDiligenceReport:
    """Create a minimal DD report for testing."""
    return DueDiligenceReport(
        symbol=symbol,
        timestamp=timestamp or datetime.now(),
        recommendation=recommendation,
        confidence=0.75,
        fundamental_summary="ok",
        technical_summary="ok",
        catalyst_assessment="ok",
        risk_factors=["risk"],
        recommended_entry=Decimal("10"),
        recommended_target=Decimal("12"),
        recommended_stop=Decimal("9"),
        recommended_position_size_pct=0.05,
        approval_rationale="looks good",
        data_sources_used=["source"],
    )


# ---------------------------------------------------------------------------
# DDReportsRepository.get_runs_since
# ---------------------------------------------------------------------------

class TestDDReportsGetRunsSince:
    """Tests for the new get_runs_since repository method."""

    @pytest.fixture
    def db(self) -> Database:
        """In-memory database with schema."""
        db = Database(":memory:")
        yield db
        db.close()

    @pytest.fixture
    def repo(self, db: Database) -> DDReportsRepository:
        return DDReportsRepository(db)

    def test_empty_when_no_reports(self, repo: DDReportsRepository) -> None:
        """Returns empty dict when no reports exist."""
        result = repo.get_runs_since(datetime.now() - timedelta(hours=1))
        assert result == {}

    def test_returns_counts_and_timestamps(self, repo: DDReportsRepository) -> None:
        """Returns correct counts and last_run per symbol."""
        now = datetime.now()
        repo.create(_make_dd_report("AAPL", now - timedelta(minutes=60)))
        repo.create(_make_dd_report("AAPL", now - timedelta(minutes=30)))
        repo.create(_make_dd_report("GOOG", now - timedelta(minutes=20)))

        result = repo.get_runs_since(now - timedelta(hours=2))
        assert "AAPL" in result
        assert result["AAPL"]["count"] == 2
        assert "GOOG" in result
        assert result["GOOG"]["count"] == 1

    def test_excludes_reports_before_cutoff(self, repo: DDReportsRepository) -> None:
        """Reports before the cutoff datetime are excluded."""
        now = datetime.now()
        repo.create(_make_dd_report("OLD", now - timedelta(hours=25)))
        repo.create(_make_dd_report("NEW", now - timedelta(minutes=10)))

        result = repo.get_runs_since(now - timedelta(hours=1))
        assert "OLD" not in result
        assert "NEW" in result
        assert result["NEW"]["count"] == 1

    def test_last_run_is_most_recent(self, repo: DDReportsRepository) -> None:
        """last_run should be the latest timestamp for each symbol."""
        now = datetime.now()
        early = now - timedelta(minutes=90)
        late = now - timedelta(minutes=10)
        repo.create(_make_dd_report("MSFT", early))
        repo.create(_make_dd_report("MSFT", late))

        result = repo.get_runs_since(now - timedelta(hours=2))
        # The last_run value comes from MAX(timestamp) in SQLite
        assert result["MSFT"]["last_run"] >= late.isoformat()


# ---------------------------------------------------------------------------
# V2AutonomousOrchestrator._rebuild_dd_runs_from_db
# ---------------------------------------------------------------------------

class TestRebuildDDRunsFromDB:
    """Tests for the _rebuild_dd_runs_from_db method."""

    @pytest.fixture
    def db(self) -> Database:
        db = Database(":memory:")
        yield db
        db.close()

    @pytest.fixture
    def repo(self, db: Database) -> DDReportsRepository:
        return DDReportsRepository(db)

    @pytest.fixture
    def orchestrator(self, repo: DDReportsRepository) -> V2AutonomousOrchestrator:
        """Create orchestrator with a real DD repo."""
        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config, dd_repo=repo)
        orch.state.current_date = date.today()
        return orch

    def test_no_repo_is_noop(self) -> None:
        """When dd_repo is None the method should not crash."""
        orch = V2AutonomousOrchestrator(config=V2Config(), dd_repo=None)
        orch.state.dd_runs_today = {}
        orch._rebuild_dd_runs_from_db()
        assert orch.state.dd_runs_today == {}

    def test_empty_db_leaves_state_unchanged(
        self, orchestrator: V2AutonomousOrchestrator
    ) -> None:
        """Empty DB should not modify dd_runs_today."""
        orchestrator.state.dd_runs_today = {"AAPL": {"count": 1, "last_run": "x"}}
        orchestrator._rebuild_dd_runs_from_db()
        assert "AAPL" in orchestrator.state.dd_runs_today

    def test_merges_missing_symbols(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """Symbols in the DB but missing from state should be added."""
        repo.create(_make_dd_report("HIMS", datetime.now() - timedelta(minutes=30)))
        orchestrator.state.dd_runs_today = {}
        orchestrator._rebuild_dd_runs_from_db()

        assert "HIMS" in orchestrator.state.dd_runs_today
        assert orchestrator.state.dd_runs_today["HIMS"]["count"] == 1
        assert "HIMS" in orchestrator.state.dd_completed_tonight

    def test_upgrades_stale_count(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """If DB has a higher count than state, state should be upgraded."""
        now = datetime.now()
        repo.create(_make_dd_report("TSLA", now - timedelta(minutes=60)))
        repo.create(_make_dd_report("TSLA", now - timedelta(minutes=30)))

        orchestrator.state.dd_runs_today = {
            "TSLA": {"count": 1, "last_run": (now - timedelta(minutes=60)).isoformat()}
        }
        orchestrator._rebuild_dd_runs_from_db()

        assert orchestrator.state.dd_runs_today["TSLA"]["count"] == 2

    def test_does_not_downgrade_count(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """If state already has a higher count, it should not be downgraded."""
        now = datetime.now()
        repo.create(_make_dd_report("META", now - timedelta(minutes=30)))

        orchestrator.state.dd_runs_today = {
            "META": {"count": 3, "last_run": now.isoformat()}
        }
        orchestrator._rebuild_dd_runs_from_db()

        assert orchestrator.state.dd_runs_today["META"]["count"] == 3

    def test_populates_dd_completed_tonight(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """Symbols from the DB should be added to dd_completed_tonight."""
        repo.create(_make_dd_report("NVDA"))
        orchestrator.state.dd_completed_tonight = []
        orchestrator._rebuild_dd_runs_from_db()

        assert "NVDA" in orchestrator.state.dd_completed_tonight

    def test_no_duplicate_in_dd_completed_tonight(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """No duplicate entries in dd_completed_tonight."""
        repo.create(_make_dd_report("AMD"))
        orchestrator.state.dd_completed_tonight = ["AMD"]
        orchestrator._rebuild_dd_runs_from_db()

        assert orchestrator.state.dd_completed_tonight.count("AMD") == 1


# ---------------------------------------------------------------------------
# Integration: _should_run_dd after rebuild
# ---------------------------------------------------------------------------

class TestShouldRunDDAfterRebuild:
    """Verify _should_run_dd respects rebuilt state."""

    @pytest.fixture
    def db(self) -> Database:
        db = Database(":memory:")
        yield db
        db.close()

    @pytest.fixture
    def repo(self, db: Database) -> DDReportsRepository:
        return DDReportsRepository(db)

    @pytest.fixture
    def orchestrator(self, repo: DDReportsRepository) -> V2AutonomousOrchestrator:
        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config, dd_repo=repo)
        orch.state.current_date = date.today()
        return orch

    def test_skips_recently_dded_symbol(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """A symbol DD'd 30 min ago should be skipped (within cooldown)."""
        repo.create(_make_dd_report("HIMS", datetime.now() - timedelta(minutes=30)))
        orchestrator.state.dd_runs_today = {}

        # Rebuild from DB
        orchestrator._rebuild_dd_runs_from_db()

        should_run, reason = orchestrator._should_run_dd("HIMS")
        assert should_run is False
        assert "cooldown" in reason or "no major event" in reason

    def test_allows_first_dd_for_new_symbol(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """A symbol not in the DB today should be allowed as first DD."""
        orchestrator.state.dd_runs_today = {}
        orchestrator._rebuild_dd_runs_from_db()

        should_run, reason = orchestrator._should_run_dd("NEWSTOCK")
        assert should_run is True
        assert "first DD" in reason

    def test_allows_dd_after_cooldown(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """A symbol DD'd 3 hours ago should still be blocked without major event."""
        repo.create(
            _make_dd_report("GOOG", datetime.now() - timedelta(hours=3))
        )
        orchestrator.state.dd_runs_today = {}
        orchestrator._rebuild_dd_runs_from_db()

        should_run, reason = orchestrator._should_run_dd("GOOG")
        assert should_run is False
        assert "no major event" in reason

    def test_allows_dd_with_major_event_after_cooldown(
        self,
        orchestrator: V2AutonomousOrchestrator,
        repo: DDReportsRepository,
    ) -> None:
        """A symbol DD'd 3 hours ago should be allowed with a major event."""
        repo.create(
            _make_dd_report("GOOG", datetime.now() - timedelta(hours=3))
        )
        orchestrator.state.dd_runs_today = {}
        orchestrator._rebuild_dd_runs_from_db()

        should_run, reason = orchestrator._should_run_dd("GOOG", has_major_event=True)
        assert should_run is True
        assert "major event" in reason
