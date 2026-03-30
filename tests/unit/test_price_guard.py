"""Tests for price guard check before entry."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock

import pandas as pd
import pytest

from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType
from beavr.orchestrator import V2AutonomousOrchestrator, V2Config


class TestPriceGuard:
    """Tests for price guard logic in _execute_trade."""

    @pytest.fixture
    def mock_broker(self) -> MagicMock:
        """Create a mock broker."""
        broker = MagicMock()
        broker.get_account.return_value = MagicMock(
            equity=Decimal("50000"),
            cash=Decimal("25000"),
        )
        broker.get_positions.return_value = []
        return broker

    @pytest.fixture
    def mock_data_provider(self) -> MagicMock:
        """Create a mock data provider."""
        return MagicMock()

    @pytest.fixture
    def orchestrator(
        self, mock_broker: MagicMock, mock_data_provider: MagicMock
    ) -> V2AutonomousOrchestrator:
        """Create orchestrator with mocked dependencies."""
        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config)
        orch._broker = mock_broker
        orch._data_provider = mock_data_provider
        orch._check_risk_limits = MagicMock(return_value=True)
        orch._log_decision = MagicMock()
        orch.dd_repo = None
        orch.positions_repo = MagicMock()
        orch.thesis_repo = MagicMock()
        orch._notify_trade_executed = MagicMock()
        orch._save_state = MagicMock()
        return orch

    def _create_thesis(self, symbol: str, entry_price: Decimal) -> TradeThesis:
        """Create a test thesis."""
        today = date.today()
        return TradeThesis(
            symbol=symbol,
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Test thesis",
            catalyst="Test catalyst event",
            entry_price_target=entry_price,
            stop_loss=entry_price * Decimal("0.95"),
            profit_target=entry_price * Decimal("1.10"),
            stop_pct=Decimal("5"),
            target_pct=Decimal("10"),
            confidence=0.8,
            status=ThesisStatus.ACTIVE,
            expected_exit_date=today + timedelta(days=7),
            max_hold_date=today + timedelta(days=14),
        )

    def _create_bars_df(self, close_price: float) -> pd.DataFrame:
        """Create a mock bars DataFrame."""
        return pd.DataFrame({
            "open": [close_price * 0.99],
            "high": [close_price * 1.01],
            "low": [close_price * 0.98],
            "close": [close_price],
            "volume": [1000000],
        })

    def test_skips_when_price_above_threshold(
        self, orchestrator: V2AutonomousOrchestrator, mock_data_provider: MagicMock, mock_broker: MagicMock
    ) -> None:
        """Skips entry when live price > 3% above thesis target."""
        # Thesis target is $100
        thesis = self._create_thesis("AAPL", Decimal("100"))

        # Live price is $105 (5% above target)
        mock_data_provider.get_bars.return_value = self._create_bars_df(105.0)

        # Mock bracket order to track if it's called
        mock_broker.submit_bracket_order = MagicMock()

        result = orchestrator._execute_trade(thesis, is_day_trade=False)

        assert result is False
        mock_broker.submit_bracket_order.assert_not_called()
        mock_broker.submit_order.assert_not_called()

        # Verify skip was logged
        orchestrator._log_decision.assert_called()
        call_args = orchestrator._log_decision.call_args
        assert call_args.kwargs.get("decision_type") == "entry_skipped"

    def test_allows_when_price_within_threshold(
        self, orchestrator: V2AutonomousOrchestrator, mock_data_provider: MagicMock, mock_broker: MagicMock
    ) -> None:
        """Allows entry when live price within 3% of target."""
        from beavr.broker.models import OrderResult

        # Thesis target is $100
        thesis = self._create_thesis("AAPL", Decimal("100"))

        # Live price is $101 (1% above target - within threshold)
        mock_data_provider.get_bars.return_value = self._create_bars_df(101.0)

        # Mock successful bracket order
        mock_broker.submit_bracket_order.return_value = OrderResult(
            order_id="test-123",
            symbol="AAPL",
            side="buy",
            order_type="market",
            status="accepted",
            filled_qty=Decimal("0"),
        )

        result = orchestrator._execute_trade(thesis, is_day_trade=False)

        assert result is True
        mock_broker.submit_bracket_order.assert_called_once()

    def test_allows_when_price_below_target(
        self, orchestrator: V2AutonomousOrchestrator, mock_data_provider: MagicMock, mock_broker: MagicMock
    ) -> None:
        """Allows entry when live price is below target (even better)."""
        from beavr.broker.models import OrderResult

        # Thesis target is $100
        thesis = self._create_thesis("AAPL", Decimal("100"))

        # Live price is $95 (5% BELOW target - good deal)
        mock_data_provider.get_bars.return_value = self._create_bars_df(95.0)

        mock_broker.submit_bracket_order.return_value = OrderResult(
            order_id="test-123",
            symbol="AAPL",
            side="buy",
            order_type="market",
            status="accepted",
            filled_qty=Decimal("0"),
        )

        result = orchestrator._execute_trade(thesis, is_day_trade=False)

        assert result is True

    def test_uses_thesis_price_when_data_unavailable(
        self, orchestrator: V2AutonomousOrchestrator, mock_data_provider: MagicMock, mock_broker: MagicMock
    ) -> None:
        """Falls back to thesis price when live data unavailable."""
        from beavr.broker.models import OrderResult

        thesis = self._create_thesis("AAPL", Decimal("100"))

        # Data provider returns empty DataFrame
        mock_data_provider.get_bars.return_value = pd.DataFrame()

        mock_broker.submit_bracket_order.return_value = OrderResult(
            order_id="test-123",
            symbol="AAPL",
            side="buy",
            order_type="market",
            status="accepted",
            filled_qty=Decimal("0"),
        )

        result = orchestrator._execute_trade(thesis, is_day_trade=False)

        # Should still proceed with thesis price
        assert result is True

    def test_handles_data_provider_exception(
        self, orchestrator: V2AutonomousOrchestrator, mock_data_provider: MagicMock, mock_broker: MagicMock
    ) -> None:
        """Gracefully handles data provider errors."""
        from beavr.broker.models import OrderResult

        thesis = self._create_thesis("AAPL", Decimal("100"))

        # Data provider raises exception
        mock_data_provider.get_bars.side_effect = Exception("API error")

        mock_broker.submit_bracket_order.return_value = OrderResult(
            order_id="test-123",
            symbol="AAPL",
            side="buy",
            order_type="market",
            status="accepted",
            filled_qty=Decimal("0"),
        )

        result = orchestrator._execute_trade(thesis, is_day_trade=False)

        # Should still proceed with thesis price
        assert result is True
