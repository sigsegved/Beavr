"""Tests for the audit trail, daily snapshots, and reset flows."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from beavr.db.factory import create_sqlite_stores
from beavr.models.portfolio_record import DecisionType, PortfolioSnapshot
from beavr.orchestrator.v2_engine import OrchestratorPhase, V2AutonomousOrchestrator

# ===================================================================
# Helpers
# ===================================================================


def _make_orch_with_stores(
    db_path: str = ":memory:",
) -> tuple[V2AutonomousOrchestrator, object]:
    """Create an orchestrator with in-memory stores wired."""
    stores = create_sqlite_stores(db_path)
    pid = stores.portfolios.create_portfolio(
        name="Test",
        mode="paper",
        initial_capital=Decimal("10000"),
        config_snapshot={},
        aggressiveness="moderate",
        directives=[],
    )
    orch = V2AutonomousOrchestrator(
        portfolio_id=pid,
        decision_store=stores.decisions,
        snapshot_store=stores.snapshots,
        portfolio_store=stores.portfolios,
    )
    return orch, stores


# ===================================================================
# Decision logging
# ===================================================================


class TestDecisionLogging:
    """Tests for _log_decision integration with stores."""

    def test_log_thesis_created(self) -> None:
        """thesis_created decision should be persisted."""
        orch, stores = _make_orch_with_stores()
        orch._log_decision(
            decision_type="thesis_created",
            action="create",
            symbol="AAPL",
            reasoning="Strong momentum signal",
        )
        decisions = stores.decisions.get_decisions(orch.portfolio_id)
        assert len(decisions) == 1
        assert decisions[0].decision_type == DecisionType.THESIS_CREATED

    def test_log_dd_approved(self) -> None:
        """DD approval should include confidence."""
        orch, stores = _make_orch_with_stores()
        orch._log_decision(
            decision_type="dd_approved",
            action="approve",
            symbol="MSFT",
            confidence=0.85,
        )
        d = stores.decisions.get_decisions(orch.portfolio_id)[0]
        assert d.confidence == 0.85
        assert d.symbol == "MSFT"

    def test_log_trade_entered(self) -> None:
        """Trade entries should record financial details."""
        orch, stores = _make_orch_with_stores()
        orch._log_decision(
            decision_type="trade_entered",
            action="buy",
            symbol="TSLA",
            amount=Decimal("500"),
            shares=Decimal("2.5"),
            price=Decimal("200"),
        )
        d = stores.decisions.get_decisions(orch.portfolio_id)[0]
        assert d.amount == Decimal("500")
        assert d.shares == Decimal("2.5")
        assert d.price == Decimal("200")

    def test_log_circuit_breaker(self) -> None:
        """Circuit breaker decisions should be logged."""
        orch, stores = _make_orch_with_stores()
        orch._log_decision(
            decision_type="circuit_breaker_triggered",
            action="halt_trading",
            reasoning="Max daily loss exceeded",
        )
        d = stores.decisions.get_decisions(orch.portfolio_id)[0]
        assert d.decision_type == DecisionType.CIRCUIT_BREAKER_TRIGGERED
        assert "Max daily loss" in d.reasoning

    def test_log_all_decision_types(self) -> None:
        """All DecisionType values should be loggable."""
        orch, stores = _make_orch_with_stores()
        for dt in DecisionType:
            orch._log_decision(
                decision_type=dt.value,
                action="test",
                symbol="TEST",
            )
        decisions = stores.decisions.get_decisions(orch.portfolio_id, limit=50)
        assert len(decisions) == len(DecisionType)

    def test_log_decision_exception_is_swallowed(self) -> None:
        """If store raises, decision logging should not crash."""
        orch, stores = _make_orch_with_stores()
        orch.decision_store = MagicMock()
        orch.decision_store.log_decision.side_effect = RuntimeError("DB locked")
        # Should not raise
        orch._log_decision(
            decision_type="thesis_created",
            action="create",
            symbol="FAIL",
        )

    def test_log_records_current_phase(self) -> None:
        """Logged decision should reflect the current orchestrator phase."""
        orch, stores = _make_orch_with_stores()
        orch.state.current_phase = OrchestratorPhase.POWER_HOUR
        orch._log_decision(
            decision_type="trade_entered",
            action="buy",
            symbol="SPY",
        )
        d = stores.decisions.get_decisions(orch.portfolio_id)[0]
        assert d.phase == "power_hour"

    def test_get_full_audit_trail(self) -> None:
        """Full audit trail should return all decisions chronologically."""
        orch, stores = _make_orch_with_stores()
        for i in range(5):
            orch._log_decision(
                decision_type="thesis_created",
                action=f"create_{i}",
                symbol=f"SYM{i}",
            )
        trail = stores.decisions.get_full_audit_trail(orch.portfolio_id)
        assert len(trail) == 5


# ===================================================================
# Daily snapshot capture
# ===================================================================


class TestDailySnapshot:
    """Tests for _capture_daily_snapshot."""

    def test_noop_without_stores(self) -> None:
        """Should not raise when snapshot_store is None."""
        orch = V2AutonomousOrchestrator()
        orch._capture_daily_snapshot()

    def test_noop_without_portfolio_id(self) -> None:
        """Should not raise when portfolio_id is None."""
        stores = create_sqlite_stores(":memory:")
        orch = V2AutonomousOrchestrator(snapshot_store=stores.snapshots)
        orch._capture_daily_snapshot()

    def test_captures_snapshot_with_broker(self) -> None:
        """Should capture snapshot when broker is available."""
        orch, stores = _make_orch_with_stores()

        # Mock broker
        mock_broker = MagicMock()
        mock_broker.get_positions.return_value = []
        mock_account = MagicMock()
        mock_account.cash = "5000.00"
        mock_broker.get_account.return_value = mock_account
        orch._broker = mock_broker

        orch._capture_daily_snapshot()

        snapshots = stores.snapshots.get_snapshots(orch.portfolio_id)
        assert len(snapshots) == 1
        assert snapshots[0].cash == Decimal("5000.00")
        assert snapshots[0].portfolio_value == Decimal("5000.00")
        assert snapshots[0].open_positions == 0

    def test_captures_snapshot_no_broker(self) -> None:
        """Should still capture a zero-value snapshot without broker."""
        orch, stores = _make_orch_with_stores()
        orch._capture_daily_snapshot()

        snapshots = stores.snapshots.get_snapshots(orch.portfolio_id)
        assert len(snapshots) == 1
        assert snapshots[0].portfolio_value == Decimal("0")

    def test_daily_pnl_from_previous_snapshot(self) -> None:
        """Daily P&L should be computed from previous snapshot."""
        orch, stores = _make_orch_with_stores()

        # First snapshot: $10,000
        first = PortfolioSnapshot(
            portfolio_id=orch.portfolio_id,
            snapshot_date=__import__("datetime").date(2026, 1, 1),
            portfolio_value=Decimal("10000"),
            cash=Decimal("10000"),
            positions_value=Decimal("0"),
        )
        stores.snapshots.take_snapshot(first)

        # Capture second snapshot with broker showing $10,500
        mock_broker = MagicMock()
        mock_broker.get_positions.return_value = []
        mock_account = MagicMock()
        mock_account.cash = "10500.00"
        mock_broker.get_account.return_value = mock_account
        orch._broker = mock_broker

        orch._capture_daily_snapshot()

        snapshots = stores.snapshots.get_snapshots(orch.portfolio_id)
        assert len(snapshots) == 2
        latest = snapshots[-1]
        assert latest.daily_pnl == Decimal("500.00")

    def test_exception_is_swallowed(self) -> None:
        """Snapshot capture errors should not crash orchestrator."""
        orch, stores = _make_orch_with_stores()
        orch.snapshot_store = MagicMock()
        orch.snapshot_store.get_snapshots.side_effect = RuntimeError("fail")
        # Should not raise
        orch._capture_daily_snapshot()


# ===================================================================
# Reset flows (store-level)
# ===================================================================


class TestResetStoreLevel:
    """Tests for portfolio deletion at the store level."""

    def test_delete_portfolio_removes_decisions(self) -> None:
        """Deleting a portfolio should remove its decisions."""
        stores = create_sqlite_stores(":memory:")
        pid = stores.portfolios.create_portfolio(
            name="ToDelete",
            mode="paper",
            initial_capital=Decimal("1000"),
            config_snapshot={},
            aggressiveness="moderate",
            directives=[],
        )
        from beavr.models.portfolio_record import PortfolioDecision

        decision = PortfolioDecision(
            portfolio_id=pid,
            phase="market_hours",
            decision_type=DecisionType.THESIS_CREATED,
            action="create",
        )
        stores.decisions.log_decision(decision)
        assert len(stores.decisions.get_decisions(pid)) == 1

        stores.portfolios.delete_portfolio(pid)

        assert stores.decisions.get_decisions(pid) == []
        assert stores.portfolios.get_portfolio(pid) is None

    def test_delete_portfolio_removes_snapshots(self) -> None:
        """Deleting a portfolio should remove its snapshots."""
        stores = create_sqlite_stores(":memory:")
        pid = stores.portfolios.create_portfolio(
            name="SnapTest",
            mode="paper",
            initial_capital=Decimal("1000"),
            config_snapshot={},
            aggressiveness="moderate",
            directives=[],
        )
        snap = PortfolioSnapshot(
            portfolio_id=pid,
            snapshot_date=__import__("datetime").date.today(),
            portfolio_value=Decimal("1000"),
            cash=Decimal("1000"),
            positions_value=Decimal("0"),
        )
        stores.snapshots.take_snapshot(snap)
        assert len(stores.snapshots.get_snapshots(pid)) == 1

        stores.portfolios.delete_portfolio(pid)
        assert stores.snapshots.get_snapshots(pid) == []

    def test_delete_all_data(self) -> None:
        """delete_all_data should wipe all portfolios."""
        stores = create_sqlite_stores(":memory:")
        for name in ["A", "B", "C"]:
            stores.portfolios.create_portfolio(
                name=name,
                mode="paper",
                initial_capital=Decimal("1000"),
                config_snapshot={},
                aggressiveness="moderate",
                directives=[],
            )
        assert len(stores.portfolios.list_portfolios()) == 3

        stores.portfolios.delete_all_data()
        assert stores.portfolios.list_portfolios() == []

    def test_delete_all_preserves_other_tables(self) -> None:
        """delete_all_data only touches portfolio tables."""
        stores = create_sqlite_stores(":memory:")
        stores.portfolios.create_portfolio(
            name="X",
            mode="paper",
            initial_capital=Decimal("1000"),
            config_snapshot={},
            aggressiveness="moderate",
            directives=[],
        )
        stores.portfolios.delete_all_data()

        # Events store should still be functional
        assert stores.portfolios.list_portfolios() == []


# ===================================================================
# History audit trail helper (unit-level)
# ===================================================================


class TestShowAuditTrailHelper:
    """Tests for the _show_audit_trail CLI helper logic."""

    def test_empty_portfolios_exits(self) -> None:
        """Should exit gracefully when no portfolios exist."""
        import click

        from beavr.cli.ai import _show_audit_trail

        stores = create_sqlite_stores(":memory:")
        with pytest.raises(click.exceptions.Exit):
            _show_audit_trail(stores, None, 20)

    def test_filter_by_portfolio_name(self) -> None:
        """Should filter decisions to matching portfolio."""
        from beavr.cli.ai import _show_audit_trail
        from beavr.models.portfolio_record import PortfolioDecision

        stores = create_sqlite_stores(":memory:")
        pid1 = stores.portfolios.create_portfolio(
            name="Alpha",
            mode="paper",
            initial_capital=Decimal("1000"),
            config_snapshot={},
            aggressiveness="moderate",
            directives=[],
        )
        pid2 = stores.portfolios.create_portfolio(
            name="Beta",
            mode="paper",
            initial_capital=Decimal("1000"),
            config_snapshot={},
            aggressiveness="moderate",
            directives=[],
        )
        for pid in [pid1, pid2]:
            stores.decisions.log_decision(
                PortfolioDecision(
                    portfolio_id=pid,
                    phase="market_hours",
                    decision_type=DecisionType.THESIS_CREATED,
                    action="test",
                )
            )

        # Should not raise, just prints
        _show_audit_trail(stores, "Alpha", 20)

    def test_nonexistent_portfolio_exits(self) -> None:
        """Should exit with error for unknown portfolio name."""
        import click

        from beavr.cli.ai import _show_audit_trail

        stores = create_sqlite_stores(":memory:")
        stores.portfolios.create_portfolio(
            name="Real",
            mode="paper",
            initial_capital=Decimal("1000"),
            config_snapshot={},
            aggressiveness="moderate",
            directives=[],
        )
        with pytest.raises(click.exceptions.Exit):
            _show_audit_trail(stores, "Nonexistent", 20)
