"""Tests for trailing stop logic."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from beavr.orchestrator import V2AutonomousOrchestrator, V2Config


class TestTrailingStops:
    """Tests for trailing stop logic in _monitor_positions."""

    @pytest.fixture
    def mock_broker(self) -> MagicMock:
        """Create a mock broker."""
        return MagicMock()

    @pytest.fixture
    def mock_positions_repo(self) -> MagicMock:
        """Create a mock positions repository."""
        return MagicMock()

    @pytest.fixture
    def orchestrator(
        self, mock_broker: MagicMock, mock_positions_repo: MagicMock
    ) -> V2AutonomousOrchestrator:
        """Create orchestrator with mocked dependencies."""
        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config)
        orch._broker = mock_broker
        orch.positions_repo = mock_positions_repo
        orch.thesis_repo = MagicMock()
        orch._close_position = MagicMock()
        return orch

    def _create_position(self, symbol: str, entry_price: float, current_price: float) -> MagicMock:
        """Create a mock broker position with specific prices."""
        pos = MagicMock()
        pos.symbol = symbol
        pos.qty = Decimal("10")
        pos.avg_cost = Decimal(str(entry_price))
        pos.market_value = Decimal(str(current_price)) * pos.qty
        cost_basis = pos.avg_cost * pos.qty
        pos.unrealized_pl = pos.market_value - cost_basis
        return pos

    def test_trailing_stop_activates_after_3pct_gain(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Trailing stop only activates when position is up > 3%."""
        # Position up 2% - should NOT activate trailing stop
        position = self._create_position("AAPL", entry_price=100.0, current_price=102.0)
        mock_broker.get_positions.return_value = [position]
        
        db_pos = MagicMock()
        db_pos.target_pct = 10.0
        db_pos.stop_loss_pct = 5.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        orchestrator._monitor_positions()
        
        # Should not have trailing stop entry yet
        assert "AAPL" not in orchestrator.state.trailing_stops

    def test_trailing_stop_tracks_high_after_3pct(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Highest price is tracked after position exceeds 3% gain."""
        # Position up 5% - should activate and track
        position = self._create_position("AAPL", entry_price=100.0, current_price=105.0)
        mock_broker.get_positions.return_value = [position]
        
        db_pos = MagicMock()
        db_pos.target_pct = 15.0  # Higher target so we don't exit on target
        db_pos.stop_loss_pct = 5.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Ensure thesis lookup doesn't interfere
        orchestrator.thesis_repo.get_by_symbol.return_value = []
        
        orchestrator._monitor_positions()
        
        # Should track the high
        assert "AAPL" in orchestrator.state.trailing_stops
        assert orchestrator.state.trailing_stops["AAPL"] == 105.0

    def test_trailing_stop_ratchets_up(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Highest price tracked is updated when price goes higher."""
        # Set initial high
        orchestrator.state.trailing_stops["AAPL"] = 105.0
        
        # Position now at $108 (higher)
        position = self._create_position("AAPL", entry_price=100.0, current_price=108.0)
        mock_broker.get_positions.return_value = [position]
        
        db_pos = MagicMock()
        db_pos.target_pct = 15.0
        db_pos.stop_loss_pct = 5.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Ensure thesis lookup doesn't interfere
        orchestrator.thesis_repo.get_by_symbol.return_value = []
        
        orchestrator._monitor_positions()
        
        # Should ratchet up to new high
        assert orchestrator.state.trailing_stops["AAPL"] == 108.0

    def test_trailing_stop_does_not_ratchet_down(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Highest price is never lowered (only ratchets up)."""
        # Set high at $110
        orchestrator.state.trailing_stops["AAPL"] = 110.0
        
        # Position now at $107 (lower than high but still in profit)
        position = self._create_position("AAPL", entry_price=100.0, current_price=107.0)
        mock_broker.get_positions.return_value = [position]
        
        db_pos = MagicMock()
        db_pos.target_pct = 15.0
        db_pos.stop_loss_pct = 5.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Ensure thesis lookup doesn't interfere
        orchestrator.thesis_repo.get_by_symbol.return_value = []
        
        orchestrator._monitor_positions()
        
        # High should stay at $110, not drop to $107
        assert orchestrator.state.trailing_stops["AAPL"] == 110.0

    def test_trailing_stop_exits_on_4pct_drop(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Position exits when price drops 4% from highest seen."""
        # Set high at $110
        orchestrator.state.trailing_stops["AAPL"] = 110.0
        
        # Position dropped to $105 (more than 4% below $110)
        # Trail stop = 110 * 0.96 = $105.60, current $105 < $105.60
        position = self._create_position("AAPL", entry_price=100.0, current_price=105.0)
        mock_broker.get_positions.return_value = [position]
        
        db_pos = MagicMock()
        db_pos.target_pct = 20.0  # High enough to not exit on target
        db_pos.stop_loss_pct = 10.0  # Not hitting regular stop
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Ensure thesis lookup doesn't interfere
        orchestrator.thesis_repo.get_by_symbol.return_value = []
        
        orchestrator._monitor_positions()
        
        # Should have called close with trailing_stop reason
        orchestrator._close_position.assert_called_once()
        call_args = orchestrator._close_position.call_args
        assert call_args[0][0] == "AAPL"
        assert call_args[0][1] == "trailing_stop"

    def test_trailing_stop_cleans_up_on_exit(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock, mock_positions_repo: MagicMock
    ) -> None:
        """Trailing stop state is removed when position closes."""
        # Setup: position at trailing stop trigger
        orchestrator.state.trailing_stops["AAPL"] = 110.0
        
        position = self._create_position("AAPL", entry_price=100.0, current_price=105.0)
        mock_broker.get_positions.return_value = [position]
        
        db_pos = MagicMock()
        db_pos.target_pct = 20.0
        db_pos.stop_loss_pct = 10.0
        mock_positions_repo.get_open_position.return_value = db_pos
        
        # Ensure thesis lookup doesn't interfere
        orchestrator.thesis_repo.get_by_symbol.return_value = []
        
        orchestrator._monitor_positions()
        
        # After trailing stop exit, the entry should be cleaned up
        assert "AAPL" not in orchestrator.state.trailing_stops
