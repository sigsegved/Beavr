"""Tests for bracket order support."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from beavr.broker.models import BracketOrderRequest, OrderResult


class TestBracketOrderRequest:
    """Tests for BracketOrderRequest model."""

    def test_bracket_order_valid_with_notional(self) -> None:
        """Bracket order should accept notional amount."""
        order = BracketOrderRequest(
            symbol="AAPL",
            side="buy",
            notional=Decimal("1000"),
            take_profit_price=Decimal("200"),
            stop_loss_price=Decimal("170"),
        )
        assert order.symbol == "AAPL"
        assert order.notional == Decimal("1000")
        assert order.quantity is None
        assert order.take_profit_price == Decimal("200")
        assert order.stop_loss_price == Decimal("170")
        assert order.tif == "gtc"

    def test_bracket_order_valid_with_quantity(self) -> None:
        """Bracket order should accept share quantity."""
        order = BracketOrderRequest(
            symbol="AAPL",
            side="buy",
            quantity=Decimal("10"),
            take_profit_price=Decimal("200"),
            stop_loss_price=Decimal("170"),
        )
        assert order.quantity == Decimal("10")
        assert order.notional is None

    def test_bracket_order_requires_qty_or_notional(self) -> None:
        """Bracket order should reject when neither qty nor notional provided."""
        with pytest.raises(ValueError, match="quantity.*notional"):
            BracketOrderRequest(
                symbol="AAPL",
                side="buy",
                take_profit_price=Decimal("200"),
                stop_loss_price=Decimal("170"),
            )

    def test_bracket_order_rejects_both_qty_and_notional(self) -> None:
        """Bracket order should reject when both qty and notional provided."""
        with pytest.raises(ValueError, match="quantity.*notional"):
            BracketOrderRequest(
                symbol="AAPL",
                side="buy",
                quantity=Decimal("10"),
                notional=Decimal("1000"),
                take_profit_price=Decimal("200"),
                stop_loss_price=Decimal("170"),
            )

    def test_bracket_order_immutable(self) -> None:
        """Bracket order should be immutable (frozen)."""
        order = BracketOrderRequest(
            symbol="AAPL",
            side="buy",
            notional=Decimal("1000"),
            take_profit_price=Decimal("200"),
            stop_loss_price=Decimal("170"),
        )
        with pytest.raises(Exception):  # ValidationError for frozen model
            order.symbol = "MSFT"  # type: ignore[misc]


class TestExecuteTradeWithBracket:
    """Tests for bracket order usage in trade execution."""

    def test_execute_trade_uses_bracket_order(self) -> None:
        """_execute_trade should attempt bracket order first."""
        from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType
        from beavr.orchestrator import V2AutonomousOrchestrator, V2Config

        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config)

        # Mock broker with bracket order support
        mock_broker = MagicMock()
        mock_broker.get_account.return_value = MagicMock(
            equity=Decimal("10000"),
            cash=Decimal("5000"),
        )
        mock_broker.submit_bracket_order.return_value = OrderResult(
            order_id="bracket-123",
            symbol="AAPL",
            side="buy",
            order_type="market",
            status="accepted",
            filled_qty=Decimal("0"),
        )
        orch._broker = mock_broker
        orch.positions_repo = MagicMock()
        orch.thesis_repo = MagicMock()
        orch._log_decision = MagicMock()
        orch._notify_trade_executed = MagicMock()
        orch._save_state = MagicMock()
        orch._check_risk_limits = MagicMock(return_value=True)

        # Create thesis with all required fields
        today = date.today()
        thesis = TradeThesis(
            symbol="AAPL",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Test entry rationale",
            catalyst="Earnings announcement",
            entry_price_target=Decimal("180"),
            stop_loss=Decimal("170"),
            profit_target=Decimal("200"),
            expected_exit_date=today + timedelta(days=7),
            max_hold_date=today + timedelta(days=14),
            confidence=0.8,
            status=ThesisStatus.ACTIVE,
        )

        # Execute
        result = orch._execute_trade(thesis, is_day_trade=False)

        # Assert bracket order was used
        assert result is True
        mock_broker.submit_bracket_order.assert_called_once()
        mock_broker.submit_order.assert_not_called()

    def test_execute_trade_falls_back_to_simple_order(self) -> None:
        """_execute_trade falls back if broker lacks bracket support."""
        from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType
        from beavr.orchestrator import V2AutonomousOrchestrator, V2Config

        config = V2Config()
        orch = V2AutonomousOrchestrator(config=config)

        # Mock broker WITHOUT bracket order support
        mock_broker = MagicMock()
        mock_broker.get_account.return_value = MagicMock(
            equity=Decimal("10000"),
            cash=Decimal("5000"),
        )
        mock_broker.submit_bracket_order.side_effect = AttributeError("no bracket")
        mock_broker.submit_order.return_value = OrderResult(
            order_id="simple-123",
            symbol="AAPL",
            side="buy",
            order_type="market",
            status="accepted",
            filled_qty=Decimal("0"),
        )
        orch._broker = mock_broker
        orch.positions_repo = MagicMock()
        orch.thesis_repo = MagicMock()
        orch._log_decision = MagicMock()
        orch._notify_trade_executed = MagicMock()
        orch._save_state = MagicMock()
        orch._check_risk_limits = MagicMock(return_value=True)

        # Create thesis with all required fields
        today = date.today()
        thesis = TradeThesis(
            symbol="AAPL",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Test entry rationale",
            catalyst="Earnings announcement",
            entry_price_target=Decimal("180"),
            stop_loss=Decimal("170"),
            profit_target=Decimal("200"),
            expected_exit_date=today + timedelta(days=7),
            max_hold_date=today + timedelta(days=14),
            confidence=0.8,
            status=ThesisStatus.ACTIVE,
        )

        # Execute
        result = orch._execute_trade(thesis, is_day_trade=False)

        # Assert fallback to simple order
        assert result is True
        mock_broker.submit_bracket_order.assert_called_once()
        mock_broker.submit_order.assert_called_once()
