"""Tests for NotificationService."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from beavr.messaging.service import NotificationService
from beavr.models.messaging import NotificationType, OutboundMessage


@pytest.fixture
def mock_provider() -> MagicMock:
    """Create a mock messaging provider."""
    provider = MagicMock()
    provider.provider_name = "test"
    provider.send_message = AsyncMock(return_value=True)
    return provider


@pytest.fixture
def mock_log_repo() -> MagicMock:
    """Create a mock log repository."""
    repo = MagicMock()
    repo.log_outbound = MagicMock(return_value=1)
    return repo


@pytest.fixture
def service(mock_provider: MagicMock, mock_log_repo: MagicMock) -> NotificationService:
    """Create a NotificationService with mocks."""
    return NotificationService(provider=mock_provider, log_repo=mock_log_repo)


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.mark.asyncio
    async def test_notify_dd_report(
        self, service: NotificationService, mock_provider: MagicMock
    ) -> None:
        result = await service.notify_dd_report(
            symbol="AAPL",
            recommendation="approve",
            confidence=0.87,
            entry=Decimal("185.00"),
            target=Decimal("195.00"),
            stop=Decimal("180.00"),
        )
        assert result is True
        mock_provider.send_message.assert_called_once()
        msg = mock_provider.send_message.call_args[0][0]
        assert isinstance(msg, OutboundMessage)
        assert msg.notification_type == NotificationType.DD_REPORT
        assert msg.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_notify_trade_executed(
        self, service: NotificationService, mock_provider: MagicMock
    ) -> None:
        result = await service.notify_trade_executed(
            action="buy",
            symbol="AAPL",
            quantity=Decimal("27"),
            price=Decimal("185.23"),
        )
        assert result is True
        msg = mock_provider.send_message.call_args[0][0]
        assert msg.notification_type == NotificationType.TRADE_EXECUTED

    @pytest.mark.asyncio
    async def test_notify_position_closed_target(
        self, service: NotificationService, mock_provider: MagicMock
    ) -> None:
        result = await service.notify_position_closed(
            symbol="AAPL",
            exit_reason="target_hit",
            entry_price=Decimal("185.00"),
            exit_price=Decimal("195.00"),
            quantity=Decimal("27"),
            pnl=Decimal("270"),
            pnl_pct=5.4,
        )
        assert result is True
        msg = mock_provider.send_message.call_args[0][0]
        assert msg.notification_type == NotificationType.TARGET_HIT

    @pytest.mark.asyncio
    async def test_notify_position_closed_stop(
        self, service: NotificationService, mock_provider: MagicMock
    ) -> None:
        result = await service.notify_position_closed(
            symbol="TSLA",
            exit_reason="stop_hit",
            entry_price=Decimal("250"),
            exit_price=Decimal("240"),
            quantity=Decimal("10"),
            pnl=Decimal("-100"),
            pnl_pct=-4.0,
        )
        assert result is True
        msg = mock_provider.send_message.call_args[0][0]
        assert msg.notification_type == NotificationType.STOP_LOSS_HIT

    @pytest.mark.asyncio
    async def test_notify_market_event(
        self, service: NotificationService, mock_provider: MagicMock
    ) -> None:
        result = await service.notify_market_event(
            headline="Fed raises rates",
            symbol="SPY",
            importance="high",
        )
        assert result is True
        msg = mock_provider.send_message.call_args[0][0]
        assert msg.notification_type == NotificationType.MARKET_EVENT

    @pytest.mark.asyncio
    async def test_notify_error(
        self, service: NotificationService, mock_provider: MagicMock
    ) -> None:
        result = await service.notify_error(
            error="Connection timeout",
            component="broker",
        )
        assert result is True
        msg = mock_provider.send_message.call_args[0][0]
        assert msg.notification_type == NotificationType.SYSTEM_ERROR

    @pytest.mark.asyncio
    async def test_logs_outbound_on_success(
        self,
        service: NotificationService,
        mock_log_repo: MagicMock,
    ) -> None:
        await service.notify_error(error="test error")
        mock_log_repo.log_outbound.assert_called_once()
        call_kwargs = mock_log_repo.log_outbound.call_args[1]
        assert call_kwargs["platform"] == "test"
        assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_logs_outbound_on_failure(
        self,
        mock_provider: MagicMock,
        mock_log_repo: MagicMock,
    ) -> None:
        mock_provider.send_message = AsyncMock(side_effect=Exception("Network error"))
        svc = NotificationService(provider=mock_provider, log_repo=mock_log_repo)
        result = await svc.notify_error(error="test")
        assert result is False
        mock_log_repo.log_outbound.assert_called_once()
        call_kwargs = mock_log_repo.log_outbound.call_args[1]
        assert call_kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_send_raw(
        self, service: NotificationService, mock_provider: MagicMock
    ) -> None:
        msg = OutboundMessage(
            notification_type=NotificationType.COMMAND_RESPONSE,
            priority="low",
            title="Test",
            body="Hello",
        )
        result = await service.send_raw(msg)
        assert result is True
        mock_provider.send_message.assert_called_once_with(msg)
