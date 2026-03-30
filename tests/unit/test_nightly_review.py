"""Tests for nightly position review."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType
from beavr.orchestrator import V2AutonomousOrchestrator, V2Config


class TestNightlyPositionReview:
    """Tests for _nightly_position_review method."""

    @pytest.fixture
    def mock_broker(self) -> MagicMock:
        """Create a mock broker."""
        return MagicMock()

    @pytest.fixture
    def mock_thesis_repo(self) -> MagicMock:
        """Create a mock thesis repository."""
        return MagicMock()

    @pytest.fixture
    def orchestrator(
        self, mock_broker: MagicMock, mock_thesis_repo: MagicMock
    ) -> V2AutonomousOrchestrator:
        """Create orchestrator with mocked dependencies."""
        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config)
        orch._broker = mock_broker
        orch.thesis_repo = mock_thesis_repo
        orch._log_decision = MagicMock()
        orch._save_state = MagicMock()
        return orch

    def _create_position(self, symbol: str, pnl_pct: float = 0.0) -> MagicMock:
        """Create a mock broker position."""
        pos = MagicMock()
        pos.symbol = symbol
        pos.qty = Decimal("10")
        pos.avg_cost = Decimal("100")
        pos.market_value = Decimal("1000") * Decimal(str(1 + pnl_pct / 100))
        pos.unrealized_pl = pos.market_value - Decimal("1000")
        return pos

    def _create_thesis(
        self,
        symbol: str,
        max_hold_date: date | None = None,
        expected_exit_date: date | None = None,
        catalyst_date: date | None = None,
        status: ThesisStatus = ThesisStatus.EXECUTED,
    ) -> TradeThesis:
        """Create a thesis with specified dates."""
        # Use sensible defaults for required date fields
        _max_hold = max_hold_date or (date.today() + timedelta(days=14))
        _expected_exit = expected_exit_date or (date.today() + timedelta(days=7))
        return TradeThesis(
            symbol=symbol,
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Test thesis",
            catalyst="Test catalyst for price movement",
            entry_price_target=Decimal("100"),
            stop_loss=Decimal("95"),
            profit_target=Decimal("110"),
            confidence=0.7,
            status=status,
            max_hold_date=_max_hold,
            expected_exit_date=_expected_exit,
            catalyst_date=catalyst_date,
        )

    def test_flags_position_past_max_hold(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock
    ) -> None:
        """Position past max_hold_date is flagged for exit."""
        position = self._create_position("AAPL")
        mock_broker.get_positions.return_value = [position]

        yesterday = date.today() - timedelta(days=1)
        thesis = self._create_thesis("AAPL", max_hold_date=yesterday)
        mock_thesis_repo.get_by_symbol.return_value = [thesis]

        orchestrator._nightly_position_review()

        # Should log decision for exit
        orchestrator._log_decision.assert_called()
        call_kwargs = orchestrator._log_decision.call_args.kwargs
        assert call_kwargs["decision_type"] == "nightly_review_exit"
        assert call_kwargs["symbol"] == "AAPL"
        assert "max_hold_date" in call_kwargs["reasoning"]

    def test_flags_position_past_expected_exit(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock
    ) -> None:
        """Position 5+ days past expected_exit_date is flagged."""
        position = self._create_position("MSFT")
        mock_broker.get_positions.return_value = [position]

        # 7 days past expected exit
        week_ago = date.today() - timedelta(days=7)
        thesis = self._create_thesis("MSFT", expected_exit_date=week_ago)
        mock_thesis_repo.get_by_symbol.return_value = [thesis]

        orchestrator._nightly_position_review()

        orchestrator._log_decision.assert_called()
        call_kwargs = orchestrator._log_decision.call_args.kwargs
        assert "expected_exit_date" in call_kwargs["reasoning"]

    def test_keeps_position_with_valid_thesis(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock
    ) -> None:
        """Position with valid, non-expired thesis is kept."""
        position = self._create_position("GOOGL")
        mock_broker.get_positions.return_value = [position]

        next_week = date.today() + timedelta(days=7)
        thesis = self._create_thesis("GOOGL", max_hold_date=next_week)
        mock_thesis_repo.get_by_symbol.return_value = [thesis]

        orchestrator._nightly_position_review()

        # Should NOT flag for exit
        orchestrator._log_decision.assert_not_called()

    def test_flags_failed_catalyst_with_loss(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock
    ) -> None:
        """Position with passed catalyst and negative P/L is flagged."""
        position = self._create_position("NVDA", pnl_pct=-5.0)  # Down 5%
        mock_broker.get_positions.return_value = [position]

        # Catalyst was 5 days ago
        five_days_ago = date.today() - timedelta(days=5)
        thesis = self._create_thesis("NVDA", catalyst_date=five_days_ago)
        mock_thesis_repo.get_by_symbol.return_value = [thesis]

        orchestrator._nightly_position_review()

        orchestrator._log_decision.assert_called()
        call_kwargs = orchestrator._log_decision.call_args.kwargs
        assert "catalyst" in call_kwargs["reasoning"].lower()

    def test_handles_missing_thesis(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Orphaned position (no thesis) logs warning but doesn't crash."""
        import logging
        caplog.set_level(logging.WARNING)

        position = self._create_position("ORPHAN")
        mock_broker.get_positions.return_value = [position]

        mock_thesis_repo.get_by_symbol.return_value = []  # No thesis

        # Should not raise
        orchestrator._nightly_position_review()

        # Should log warning about orphaned position
        assert "orphaned" in caplog.text.lower() or "no active thesis" in caplog.text.lower()
