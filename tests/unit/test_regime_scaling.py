"""Tests for regime-based exposure scaling."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from beavr.orchestrator import V2AutonomousOrchestrator, V2Config


class TestRegimeScaling:
    """Tests for regime-based position limits and sizing."""

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
        config = V2Config()
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

    def _set_regime(self, orchestrator: V2AutonomousOrchestrator, regime: str) -> None:
        """Set the current regime via _last_regime attribute."""
        orchestrator._last_regime = regime

    def test_bear_regime_limits_positions(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock
    ) -> None:
        """Bear regime allows max 2 positions."""
        # Set bear regime
        self._set_regime(orchestrator, "bear")

        # Setup: 2 positions (at bear max)
        positions = [self._create_position(f"SYM{i}") for i in range(2)]
        mock_broker.get_positions.return_value = positions

        orchestrator._get_approved_theses = MagicMock(return_value=[MagicMock()])
        orchestrator._execute_trade = MagicMock()

        orchestrator._execute_swing_trades()

        # Should not execute any trades (at cap)
        orchestrator._execute_trade.assert_not_called()

    def test_bull_regime_allows_full_positions(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock
    ) -> None:
        """Bull regime allows max 8 positions."""
        from datetime import date, timedelta

        from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType

        # Set bull regime
        self._set_regime(orchestrator, "bull")

        # Setup: 5 positions (below bull max of 8)
        positions = [self._create_position(f"SYM{i}") for i in range(5)]
        mock_broker.get_positions.return_value = positions

        today = date.today()
        thesis = TradeThesis(
            symbol="NEWSTOCK",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Test entry rationale",
            catalyst="Test catalyst",
            entry_price_target=Decimal("100"),
            stop_loss=Decimal("95"),
            profit_target=Decimal("110"),
            stop_pct=Decimal("5"),
            target_pct=Decimal("10"),
            confidence=0.8,
            status=ThesisStatus.ACTIVE,
            expected_exit_date=today + timedelta(days=7),
            max_hold_date=today + timedelta(days=14),
        )

        orchestrator._get_approved_theses = MagicMock(return_value=[thesis])
        orchestrator._has_related_position = MagicMock(return_value=False)
        orchestrator._is_related_to_any = MagicMock(return_value=None)
        orchestrator._execute_trade = MagicMock(return_value=True)

        orchestrator._execute_swing_trades()

        # Should allow trade execution
        orchestrator._execute_trade.assert_called_once()

    def test_sideways_regime_limits_to_5(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock
    ) -> None:
        """Sideways regime allows max 5 positions."""
        self._set_regime(orchestrator, "sideways")

        # Setup: 5 positions (at sideways max)
        positions = [self._create_position(f"SYM{i}") for i in range(5)]
        mock_broker.get_positions.return_value = positions

        orchestrator._get_approved_theses = MagicMock(return_value=[MagicMock()])
        orchestrator._execute_trade = MagicMock()

        orchestrator._execute_swing_trades()

        # Should not execute (at cap)
        orchestrator._execute_trade.assert_not_called()

    def test_volatile_regime_limits_to_3(
        self, orchestrator: V2AutonomousOrchestrator, mock_broker: MagicMock
    ) -> None:
        """Volatile regime allows max 3 positions."""
        self._set_regime(orchestrator, "volatile")

        # Setup: 3 positions (at volatile max)
        positions = [self._create_position(f"SYM{i}") for i in range(3)]
        mock_broker.get_positions.return_value = positions

        orchestrator._get_approved_theses = MagicMock(return_value=[MagicMock()])
        orchestrator._execute_trade = MagicMock()

        orchestrator._execute_swing_trades()

        # Should not execute (at cap)
        orchestrator._execute_trade.assert_not_called()

    def test_get_regime_adjusted_limits_defaults(
        self, orchestrator: V2AutonomousOrchestrator
    ) -> None:
        """Should return correct limits for each regime."""
        test_cases = [
            ("bull", 8, 1.0),
            ("sideways", 5, 0.7),
            ("bear", 2, 0.4),
            ("volatile", 3, 0.3),
        ]

        for regime, expected_max, expected_mult in test_cases:
            self._set_regime(orchestrator, regime)
            max_pos, multiplier = orchestrator._get_regime_adjusted_limits()
            assert max_pos == expected_max, f"Failed for {regime}: expected max {expected_max}, got {max_pos}"
            assert multiplier == expected_mult, f"Failed for {regime}: expected mult {expected_mult}, got {multiplier}"

    def test_size_multiplier_reduces_in_volatility(
        self, orchestrator: V2AutonomousOrchestrator
    ) -> None:
        """Volatile regime reduces position size to 30%."""
        self._set_regime(orchestrator, "volatile")
        _, multiplier = orchestrator._get_regime_adjusted_limits()
        assert multiplier == 0.3

    def test_config_defaults(self) -> None:
        """V2Config should have correct regime defaults."""
        config = V2Config()
        assert config.regime_max_positions["bull"] == 8
        assert config.regime_max_positions["bear"] == 2
        assert config.regime_size_multiplier["volatile"] == 0.3
