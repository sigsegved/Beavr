"""Tests for messaging data models."""

from datetime import datetime
from decimal import Decimal

import pytest

from beavr.models.messaging import (
    CommandResult,
    InboundCommand,
    MessagePriority,
    NotificationType,
    OutboundMessage,
    PendingConfirmation,
)


class TestMessagePriority:
    """Tests for MessagePriority enum."""

    def test_values(self) -> None:
        assert MessagePriority.LOW == "low"
        assert MessagePriority.MEDIUM == "medium"
        assert MessagePriority.HIGH == "high"
        assert MessagePriority.CRITICAL == "critical"


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_values(self) -> None:
        assert NotificationType.DD_REPORT == "dd_report"
        assert NotificationType.TRADE_EXECUTED == "trade_executed"
        assert NotificationType.STOP_LOSS_HIT == "stop_loss_hit"


class TestOutboundMessage:
    """Tests for OutboundMessage model."""

    def test_create_minimal(self) -> None:
        msg = OutboundMessage(
            notification_type=NotificationType.DD_REPORT,
            priority=MessagePriority.MEDIUM,
            title="Test",
            body="Test body",
        )
        assert msg.notification_type == NotificationType.DD_REPORT
        assert msg.priority == MessagePriority.MEDIUM
        assert msg.title == "Test"
        assert msg.body == "Test body"
        assert msg.symbol is None
        assert msg.metadata == {}
        assert isinstance(msg.timestamp, datetime)

    def test_create_full(self) -> None:
        msg = OutboundMessage(
            notification_type=NotificationType.TRADE_EXECUTED,
            priority=MessagePriority.HIGH,
            title="Trade",
            body="BUY AAPL",
            symbol="AAPL",
            metadata={"order_id": "123"},
        )
        assert msg.symbol == "AAPL"
        assert msg.metadata == {"order_id": "123"}


class TestInboundCommand:
    """Tests for InboundCommand model."""

    def test_create(self) -> None:
        cmd = InboundCommand(
            raw_text="/buy AAPL $500",
            command="buy",
            args=["AAPL", "$500"],
            sender_id="12345",
            platform="telegram",
        )
        assert cmd.command == "buy"
        assert cmd.args == ["AAPL", "$500"]
        assert cmd.sender_id == "12345"
        assert cmd.platform == "telegram"
        assert cmd.is_verified is False

    def test_verified_flag(self) -> None:
        cmd = InboundCommand(
            raw_text="/status",
            command="status",
            sender_id="12345",
            platform="telegram",
            is_verified=True,
        )
        assert cmd.is_verified is True


class TestCommandResult:
    """Tests for CommandResult model."""

    def test_success(self) -> None:
        result = CommandResult(success=True, message="Done!")
        assert result.success is True
        assert result.message == "Done!"
        assert result.data is None

    def test_failure_with_data(self) -> None:
        result = CommandResult(
            success=False,
            message="Error",
            data={"error_code": "rate_limit"},
        )
        assert result.success is False
        assert result.data == {"error_code": "rate_limit"}


class TestPendingConfirmation:
    """Tests for PendingConfirmation model."""

    def test_buy_confirmation(self) -> None:
        pc = PendingConfirmation(
            chat_id="12345",
            command="buy",
            symbol="AAPL",
            amount=Decimal("500"),
            expires_at=datetime(2026, 3, 12, 12, 0, 0),
        )
        assert pc.command == "buy"
        assert pc.symbol == "AAPL"
        assert pc.amount == Decimal("500")
        assert pc.quantity is None

    def test_sell_confirmation(self) -> None:
        pc = PendingConfirmation(
            chat_id="12345",
            command="sell",
            symbol="TSLA",
            quantity=Decimal("10"),
            expires_at=datetime(2026, 3, 12, 12, 0, 0),
        )
        assert pc.command == "sell"
        assert pc.quantity == Decimal("10")
        assert pc.amount is None
