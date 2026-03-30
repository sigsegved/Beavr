"""Tests for position cap enforcement."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from beavr.orchestrator import V2AutonomousOrchestrator, V2Config


class TestPositionCap:
    """Tests for max position cap enforcement."""

    @pytest.fixture
    def mock_broker(self) -> MagicMock:
        """Create a mock broker."""
        broker = MagicMock()
        broker.get_account.return_value = MagicMock(
            equity=Decimal("50000"),
            cash=Decimal("25000"),
        )
        return broker

    @pytest.fixture
    def orchestrator(self, mock_broker: MagicMock) -> V2AutonomousOrchestrator:
        """Create orchestrator with mocked broker."""
        config = V2Config(max_open_positions=8, min_position_value=500.0)
        orch = V2AutonomousOrchestrator(config=config)
        orch._broker = mock_broker
        orch._check_circuit_breaker = MagicMock(return_value=True)
        return orch

    def _create_position(self, symbol: str) -> MagicMock:
        """Create a mock broker position."""
        pos = MagicMock()
        pos.symbol = symbol
        pos.qty = Decimal("10")
        pos.market_value = Decimal("1000")
        return pos

    def test_blocks_new_entry_when_at_max(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock
    ) -> None:
        """No new entries when position count equals max."""
        # Setup: 8 positions (at max)
        positions = [self._create_position(f"SYM{i}") for i in range(8)]
        mock_broker.get_positions.return_value = positions

        # Mock approved theses
        orchestrator._get_approved_theses = MagicMock(return_value=[MagicMock()])
        orchestrator._execute_trade = MagicMock()

        # Execute swing trades
        orchestrator._execute_swing_trades()

        # Assert no trades executed (returned early due to cap)
        orchestrator._execute_trade.assert_not_called()

    def test_allows_entry_when_below_max(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock
    ) -> None:
        """New entries allowed when below cap."""
        from datetime import date, timedelta

        from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType

        # Set bull regime (max 8 positions)
        orchestrator._last_regime = "bull"

        # Setup: 5 positions (below max of 8 for bull regime)
        positions = [self._create_position(f"SYM{i}") for i in range(5)]
        mock_broker.get_positions.return_value = positions

        # Create a real thesis
        today = date.today()
        thesis = TradeThesis(
            symbol="NEWSTOCK",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Test",
            catalyst="Test catalyst",
            entry_price_target=Decimal("100"),
            stop_loss=Decimal("95"),
            profit_target=Decimal("110"),
            stop_pct=Decimal("5"),
            target_pct=Decimal("10"),
            expected_exit_date=today + timedelta(days=14),
            max_hold_date=today + timedelta(days=21),
            confidence=0.8,
            status=ThesisStatus.ACTIVE,
        )

        orchestrator._get_approved_theses = MagicMock(return_value=[thesis])
        orchestrator._has_related_position = MagicMock(return_value=False)
        orchestrator._is_related_to_any = MagicMock(return_value=None)
        orchestrator._execute_trade = MagicMock(return_value=True)

        # Execute
        orchestrator._execute_swing_trades()

        # Assert trade was attempted
        orchestrator._execute_trade.assert_called_once()

    def test_min_position_value_enforced(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock
    ) -> None:
        """Positions below min_position_value are rejected."""
        from datetime import date, timedelta

        from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType

        # Setup broker with very little cash
        mock_broker.get_account.return_value = MagicMock(
            equity=Decimal("1000"),
            cash=Decimal("400"),  # Will result in position < $500
        )
        mock_broker.get_positions.return_value = []

        today = date.today()
        thesis = TradeThesis(
            symbol="AAPL",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Test",
            catalyst="Test catalyst",
            entry_price_target=Decimal("180"),
            stop_loss=Decimal("170"),
            profit_target=Decimal("200"),
            stop_pct=Decimal("5.5"),
            target_pct=Decimal("11.1"),
            expected_exit_date=today + timedelta(days=14),
            max_hold_date=today + timedelta(days=21),
            confidence=0.8,
            status=ThesisStatus.ACTIVE,
        )

        orchestrator._check_risk_limits = MagicMock(return_value=True)
        orchestrator.dd_repo = None

        result = orchestrator._execute_trade(thesis, is_day_trade=False)

        # Should return False due to min position value
        assert result is False

    def test_config_defaults(self) -> None:
        """V2Config should have correct defaults for position limits."""
        config = V2Config()
        assert config.max_open_positions == 8
        assert config.min_position_value == 500.0
