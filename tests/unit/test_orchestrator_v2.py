"""Tests for v2 orchestrator research scheduling."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from beavr.orchestrator import OrchestratorPhase, V2AutonomousOrchestrator, V2Config

ET = ZoneInfo("America/New_York")


@pytest.fixture
def orchestrator() -> V2AutonomousOrchestrator:
    """Create a v2 orchestrator with a short research interval."""
    config = V2Config(market_research_interval=900)
    return V2AutonomousOrchestrator(config=config)


class TestV2OrchestratorResearch:
    """Tests for research mode and scheduling logic."""

    def test_is_research_mode_true_when_idle(self, orchestrator: V2AutonomousOrchestrator) -> None:
        """Research mode should be active when no theses or positions exist."""
        assert orchestrator._is_research_mode(
            approved_theses=0,
            pending_dd=0,
            open_positions=0,
        )

    def test_is_research_mode_false_when_positions(self, orchestrator: V2AutonomousOrchestrator) -> None:
        """Research mode should be disabled when positions exist."""
        assert not orchestrator._is_research_mode(
            approved_theses=0,
            pending_dd=0,
            open_positions=1,
        )

    def test_should_run_research_first_time(self, orchestrator: V2AutonomousOrchestrator) -> None:
        """Research should run immediately if no prior run is recorded."""
        now = datetime(2026, 2, 5, 11, 0, tzinfo=ET)
        assert orchestrator._should_run_research(now, OrchestratorPhase.MARKET_HOURS)

    def test_should_not_run_research_before_interval(self, orchestrator: V2AutonomousOrchestrator) -> None:
        """Research should not run again until the interval elapses."""
        now = datetime(2026, 2, 5, 11, 0, tzinfo=ET)
        orchestrator.state.last_research_run = now - timedelta(seconds=600)
        assert not orchestrator._should_run_research(now, OrchestratorPhase.MARKET_HOURS)

    def test_should_run_research_after_interval(self, orchestrator: V2AutonomousOrchestrator) -> None:
        """Research should run when the interval has elapsed."""
        now = datetime(2026, 2, 5, 11, 0, tzinfo=ET)
        orchestrator.state.last_research_run = now - timedelta(seconds=900)
        assert orchestrator._should_run_research(now, OrchestratorPhase.POWER_HOUR)

    def test_should_not_run_research_outside_market_hours(self, orchestrator: V2AutonomousOrchestrator) -> None:
        """Research should not run outside market or power hour phases."""
        now = datetime(2026, 2, 5, 8, 0, tzinfo=ET)
        assert not orchestrator._should_run_research(now, OrchestratorPhase.PRE_MARKET)

    def test_should_run_research_immediately_in_research_mode(
        self, orchestrator: V2AutonomousOrchestrator
    ) -> None:
        """Research should run immediately when in research_mode, skipping interval."""
        now = datetime(2026, 2, 5, 11, 0, tzinfo=ET)
        # Set last research to just 1 minute ago (way under 15 min interval)
        orchestrator.state.last_research_run = now - timedelta(seconds=60)
        # Without research_mode, should NOT run
        assert not orchestrator._should_run_research(now, OrchestratorPhase.MARKET_HOURS, research_mode=False)
        # With research_mode=True, should run immediately
        assert orchestrator._should_run_research(now, OrchestratorPhase.MARKET_HOURS, research_mode=True)
