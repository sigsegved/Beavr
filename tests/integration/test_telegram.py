"""Integration tests for the Telegram messaging system.

These tests hit the real Telegram Bot API to verify:
1. Bot token is valid and bot is reachable
2. Messages can be sent to a verified chat ID
3. The NotificationService sends formatted messages end-to-end
4. Auth guard correctly identifies verified/unverified users

Requires environment variables:
    BEAVR_TELEGRAM_BOT_TOKEN - Valid Telegram bot token
    BEAVR_MESSAGING__TELEGRAM__VERIFIED_CHAT_IDS - At least one chat ID

Run with:
    pytest tests/integration/test_telegram.py -v
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

# Load .env before anything else
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@pytest.fixture
def bot_token() -> str:
    """Get Telegram bot token from environment."""
    token = os.environ.get("BEAVR_TELEGRAM_BOT_TOKEN")
    if not token:
        pytest.skip("BEAVR_TELEGRAM_BOT_TOKEN required for Telegram integration tests")
    return token


@pytest.fixture
def chat_id() -> str:
    """Get a verified chat ID from environment."""
    chat_ids = os.environ.get("BEAVR_MESSAGING__TELEGRAM__VERIFIED_CHAT_IDS", "")
    if not chat_ids:
        pytest.skip(
            "BEAVR_MESSAGING__TELEGRAM__VERIFIED_CHAT_IDS required for Telegram integration tests"
        )
    # Take the first one
    first_id = chat_ids.split(",")[0].strip()
    if not first_id:
        pytest.skip("No valid chat ID found")
    return first_id


class TestTelegramBotConnection:
    """Test that the bot token is valid and the bot is reachable."""

    @pytest.mark.asyncio
    async def test_bot_token_is_valid(self, bot_token: str) -> None:
        """Bot token should authenticate successfully with Telegram API."""
        from telegram import Bot

        bot = Bot(token=bot_token)
        me = await bot.get_me()
        assert me.id is not None
        assert me.is_bot is True
        assert me.username is not None
        print(f"\n  Bot: @{me.username} (ID: {me.id})")

    @pytest.mark.asyncio
    async def test_bot_can_get_updates(self, bot_token: str) -> None:
        """Bot should be able to poll for updates (even if empty)."""
        from telegram import Bot

        bot = Bot(token=bot_token)
        # This just verifies the API call works, not that there are messages
        updates = await bot.get_updates(limit=1, timeout=1)
        assert isinstance(updates, (list, tuple))


class TestTelegramSendMessage:
    """Test sending messages to a real chat."""

    @pytest.mark.asyncio
    async def test_send_plain_text(self, bot_token: str, chat_id: str) -> None:
        """Bot should send a plain text message to the verified chat ID."""
        from telegram import Bot

        bot = Bot(token=bot_token)
        msg = await bot.send_message(
            chat_id=chat_id,
            text="🧪 Beavr Integration Test: Plain text message",
        )
        assert msg.message_id is not None
        assert msg.chat.id == int(chat_id)

    @pytest.mark.asyncio
    async def test_send_markdown_message(self, bot_token: str, chat_id: str) -> None:
        """Bot should send a Markdown-formatted message."""
        from telegram import Bot

        bot = Bot(token=bot_token)
        msg = await bot.send_message(
            chat_id=chat_id,
            text="*🧪 Integration Test*\n\nThis is a _formatted_ test message from Beavr.",
            parse_mode="Markdown",
        )
        assert msg.message_id is not None


class TestTelegramProvider:
    """Test the TelegramProvider class end-to-end."""

    @pytest.mark.asyncio
    async def test_provider_send_message(self, bot_token: str, chat_id: str) -> None:
        """TelegramProvider.send_message should deliver to the chat."""
        from beavr.messaging.auth import AuthGuard
        from beavr.messaging.providers.telegram import TelegramProvider
        from beavr.models.messaging import (
            MessagePriority,
            NotificationType,
            OutboundMessage,
        )

        provider = TelegramProvider(
            bot_token=bot_token,
            auth_guard=AuthGuard(verified_chat_ids=[chat_id]),
            chat_ids=[chat_id],
        )

        msg = OutboundMessage(
            notification_type=NotificationType.COMMAND_RESPONSE,
            priority=MessagePriority.LOW,
            title="🧪 Provider Test",
            body="Message sent via TelegramProvider.send_message()",
        )

        result = await provider.send_message(msg)
        assert result is True

    @pytest.mark.asyncio
    async def test_provider_send_to_invalid_chat_fails_gracefully(
        self, bot_token: str
    ) -> None:
        """Sending to an invalid chat ID should return False, not crash."""
        from beavr.messaging.auth import AuthGuard
        from beavr.messaging.providers.telegram import TelegramProvider
        from beavr.models.messaging import (
            MessagePriority,
            NotificationType,
            OutboundMessage,
        )

        provider = TelegramProvider(
            bot_token=bot_token,
            auth_guard=AuthGuard(),
            chat_ids=["0"],  # invalid chat ID
        )

        msg = OutboundMessage(
            notification_type=NotificationType.SYSTEM_ERROR,
            priority=MessagePriority.LOW,
            title="Test",
            body="Should fail gracefully",
        )

        result = await provider.send_message(msg)
        assert result is False


class TestNotificationServiceEndToEnd:
    """Test NotificationService sending real formatted messages."""

    @pytest.mark.asyncio
    async def test_dd_report_notification(self, bot_token: str, chat_id: str) -> None:
        """Full DD report notification should arrive formatted in Telegram."""
        from beavr.messaging.auth import AuthGuard
        from beavr.messaging.providers.telegram import TelegramProvider
        from beavr.messaging.service import NotificationService

        provider = TelegramProvider(
            bot_token=bot_token,
            auth_guard=AuthGuard(verified_chat_ids=[chat_id]),
            chat_ids=[chat_id],
        )
        service = NotificationService(provider=provider)

        result = await service.notify_dd_report(
            symbol="AAPL",
            recommendation="approve",
            confidence=0.87,
            trade_type="swing_short",
            entry=Decimal("185.00"),
            target=Decimal("195.00"),
            stop=Decimal("180.00"),
            position_size_pct=0.05,
            executive_summary="Strong Q1 earnings catalyst with institutional accumulation.",
            risk_factors=["Trade war escalation", "AI spending slowdown"],
            bull_case="iPhone 17 cycle drives 15% upside",
            bear_case="China tariff escalation caps gains",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_trade_executed_notification(
        self, bot_token: str, chat_id: str
    ) -> None:
        """Trade execution notification should arrive formatted in Telegram."""
        from beavr.messaging.auth import AuthGuard
        from beavr.messaging.providers.telegram import TelegramProvider
        from beavr.messaging.service import NotificationService

        provider = TelegramProvider(
            bot_token=bot_token,
            auth_guard=AuthGuard(verified_chat_ids=[chat_id]),
            chat_ids=[chat_id],
        )
        service = NotificationService(provider=provider)

        result = await service.notify_trade_executed(
            action="buy",
            symbol="AAPL",
            quantity=Decimal("27"),
            price=Decimal("185.23"),
            total_cost=Decimal("5001.21"),
            stop_loss=Decimal("180.00"),
            target=Decimal("195.00"),
            order_id="test_order_123",
            thesis_summary="Q1 earnings momentum + iPhone 17 cycle",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_position_closed_notification(
        self, bot_token: str, chat_id: str
    ) -> None:
        """Position closure notification should arrive formatted in Telegram."""
        from beavr.messaging.auth import AuthGuard
        from beavr.messaging.providers.telegram import TelegramProvider
        from beavr.messaging.service import NotificationService

        provider = TelegramProvider(
            bot_token=bot_token,
            auth_guard=AuthGuard(verified_chat_ids=[chat_id]),
            chat_ids=[chat_id],
        )
        service = NotificationService(provider=provider)

        result = await service.notify_position_closed(
            symbol="AAPL",
            exit_reason="target_hit",
            entry_price=Decimal("185.00"),
            exit_price=Decimal("195.00"),
            quantity=Decimal("27"),
            pnl=Decimal("270.00"),
            pnl_pct=5.4,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_error_notification(self, bot_token: str, chat_id: str) -> None:
        """System error notification should arrive in Telegram."""
        from beavr.messaging.auth import AuthGuard
        from beavr.messaging.providers.telegram import TelegramProvider
        from beavr.messaging.service import NotificationService

        provider = TelegramProvider(
            bot_token=bot_token,
            auth_guard=AuthGuard(verified_chat_ids=[chat_id]),
            chat_ids=[chat_id],
        )
        service = NotificationService(provider=provider)

        result = await service.notify_error(
            error="SDK protocol version mismatch (test — ignore this)",
            component="ThesisGenerator",
        )
        assert result is True


class TestAuthGuardWithRealIds:
    """Test AuthGuard with real chat IDs."""

    def test_verified_chat_id_passes(self, chat_id: str) -> None:
        """Configured chat ID should be recognized as verified."""
        from beavr.messaging.auth import AuthGuard

        guard = AuthGuard(verified_chat_ids=[chat_id])
        assert guard.is_verified(chat_id) is True

    def test_random_chat_id_rejected(self, chat_id: str) -> None:
        """A random chat ID should be rejected."""
        from beavr.messaging.auth import AuthGuard

        guard = AuthGuard(verified_chat_ids=[chat_id])
        assert guard.is_verified("999999999") is False

    def test_multiple_chat_ids(self, chat_id: str) -> None:
        """Multiple chat IDs should all be verified."""
        from beavr.messaging.auth import AuthGuard

        guard = AuthGuard(verified_chat_ids=[chat_id, "111111111"])
        assert guard.is_verified(chat_id) is True
        assert guard.is_verified("111111111") is True
        assert guard.is_verified("222222222") is False
