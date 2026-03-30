"""Tests for time-based position exit enforcement."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType
from beavr.orchestrator import V2AutonomousOrchestrator, V2Config


class TestTimeBasedExits:
    """Tests for time-based exit logic in _monitor_positions."""

    @pytest.fixture
    def mock_broker(self) -> MagicMock:
        """Create a mock broker."""
        broker = MagicMock()
        return broker

    @pytest.fixture
    def mock_thesis_repo(self) -> MagicMock:
        """Create a mock thesis repository."""
        return MagicMock()

    @pytest.fixture
    def mock_positions_repo(self) -> MagicMock:
        """Create a mock positions repository."""
        return MagicMock()

    @pytest.fixture
    def orchestrator(
        self, mock_broker: MagicMock, mock_thesis_repo: MagicMock, mock_positions_repo: MagicMock
    ) -> V2AutonomousOrchestrator:
        """Create an orchestrator with mocked dependencies."""
        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config)
        orch._broker = mock_broker
        orch.thesis_repo = mock_thesis_repo
        orch.positions_repo = mock_positions_repo
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
        )

    def test_closes_position_past_max_hold_date(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Position past max_hold_date is force-closed."""
        # Setup position
        position = self._create_position("AAPL", pnl_pct=2.0)
        mock_broker.get_positions.return_value = [position]
        
        # Setup thesis with max_hold_date in the past
        yesterday = date.today() - timedelta(days=1)
        thesis = self._create_thesis("AAPL", max_hold_date=yesterday)
        mock_thesis_repo.get_by_symbol.return_value = [thesis]
        
        # Setup positions repo
        db_pos = MagicMock()
        db_pos.target_pct = 10.0
        db_pos.stop_loss_pct = 5.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Mock _close_position
        orchestrator._close_position = MagicMock()
        
        # Run monitor
        orchestrator._monitor_positions()
        
        # Assert close was called with time_exit reason
        orchestrator._close_position.assert_called_once_with("AAPL", "time_exit", pytest.approx(2.0, rel=0.1))

    def test_holds_position_before_max_hold_date(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Position before max_hold_date is NOT closed."""
        # Setup position
        position = self._create_position("AAPL", pnl_pct=2.0)
        mock_broker.get_positions.return_value = [position]
        
        # Setup thesis with max_hold_date in the future
        next_week = date.today() + timedelta(days=7)
        thesis = self._create_thesis("AAPL", max_hold_date=next_week)
        mock_thesis_repo.get_by_symbol.return_value = [thesis]
        
        # Setup positions repo
        db_pos = MagicMock()
        db_pos.target_pct = 10.0
        db_pos.stop_loss_pct = 5.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Mock _close_position
        orchestrator._close_position = MagicMock()
        
        # Run monitor
        orchestrator._monitor_positions()
        
        # Assert close was NOT called
        orchestrator._close_position.assert_not_called()

    def test_logs_warning_past_expected_exit_date(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_thesis_repo: MagicMock, mock_positions_repo: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Position past expected_exit_date logs warning but does not close."""
        import logging
        caplog.set_level(logging.WARNING)
        
        # Setup position
        position = self._create_position("AAPL", pnl_pct=2.0)
        mock_broker.get_positions.return_value = [position]
        
        # Setup thesis with expected_exit_date in past, max_hold_date in future
        yesterday = date.today() - timedelta(days=1)
        next_week = date.today() + timedelta(days=7)
        thesis = self._create_thesis("AAPL", max_hold_date=next_week, expected_exit_date=yesterday)
        mock_thesis_repo.get_by_symbol.return_value = [thesis]
        
        # Setup positions repo
        db_pos = MagicMock()
        db_pos.target_pct = 10.0
        db_pos.stop_loss_pct = 5.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Mock _close_position
        orchestrator._close_position = MagicMock()
        
        # Run monitor
        orchestrator._monitor_positions()
        
        # Assert warning was logged but position NOT closed
        assert "past expected_exit_date" in caplog.text or "review needed" in caplog.text
        orchestrator._close_position.assert_not_called()
