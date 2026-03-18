"""Telegram messaging provider.

Implements the MessagingProvider protocol using the python-telegram-bot
library. Handles outbound notifications and inbound command processing
via long-polling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from beavr.messaging.auth import AuthGuard, sanitize_input
from beavr.models.messaging import (
    CommandResult,
    InboundCommand,
    OutboundMessage,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TelegramProvider:
    """Telegram Bot API messaging provider.

    Uses long-polling to receive messages and the Bot API to send them.
    Only processes commands from verified chat IDs.

    Attributes:
        provider_name: Always ``'telegram'``.
    """

    provider_name: str = "telegram"

    def __init__(
        self,
        bot_token: str,
        auth_guard: AuthGuard,
        chat_ids: Optional[list[str]] = None,
    ) -> None:
        """Initialize the Telegram provider.

        Args:
            bot_token: Telegram Bot API token from @BotFather.
            auth_guard: AuthGuard instance for verifying senders.
            chat_ids: Default chat IDs to send notifications to.
        """
        self._bot_token = bot_token
        self._auth_guard = auth_guard
        self._chat_ids = chat_ids or []
        self._command_callback: Optional[
            Callable[[InboundCommand], Awaitable[CommandResult]]
        ] = None
        self._application: Optional[object] = None
        self._running = False

    async def send_message(self, message: OutboundMessage) -> bool:
        """Send a notification to all verified chat IDs.

        Args:
            message: The outbound message to deliver.

        Returns:
            True if at least one delivery succeeded.
        """
        try:
            from telegram import Bot
        except ImportError:
            logger.error(
                "python-telegram-bot not installed. "
                "Install with: pip install 'beavr[messaging]'"
            )
            return False

        bot = Bot(token=self._bot_token)
        text = f"{message.title}\n\n{message.body}"
        # Telegram message limit is 4096 chars
        if len(text) > 4096:
            text = text[:4093] + "..."

        success = False
        for chat_id in self._chat_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                )
                success = True
            except Exception:
                logger.exception("Failed to send Telegram message to %s", chat_id)

        return success

    async def start_listening(self) -> None:
        """Start long-polling for inbound messages.

        This is a blocking call that runs until ``stop_listening()`` is called.
        Should be run in a background task.
        """
        try:
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.error(
                "python-telegram-bot not installed. "
                "Install with: pip install 'beavr[messaging]'"
            )
            return

        app = Application.builder().token(self._bot_token).build()

        # /chatid — always available, lets user discover their ID for config
        app.add_handler(CommandHandler("chatid", self._handle_chatid))
        app.add_handler(CommandHandler("start", self._handle_chatid))

        # Register all known command handlers
        known_commands = [
            "help", "status", "positions", "history",
            "analyze", "dd", "sector", "research",
            "buy", "sell", "confirm", "cancel",
        ]
        for cmd in known_commands:
            app.add_handler(
                CommandHandler(cmd, self._handle_command)
            )

        # Catch-all for unrecognized messages
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_unknown)
        )

        self._application = app
        self._running = True

        logger.info("Telegram bot starting long-polling...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()  # type: ignore[union-attr]

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

        await app.updater.stop()  # type: ignore[union-attr]
        await app.stop()
        await app.shutdown()

    async def stop_listening(self) -> None:
        """Stop the long-polling listener."""
        self._running = False

    def set_command_callback(
        self,
        callback: Callable[[InboundCommand], Awaitable[CommandResult]],
    ) -> None:
        """Register the callback for processing verified commands.

        Args:
            callback: Async function that processes an InboundCommand.
        """
        self._command_callback = callback

    # --- Internal handlers ---

    async def _handle_chatid(self, update: object, context: object) -> None:  # noqa: ARG002
        """Handle /chatid and /start — show the user's chat ID for config."""
        message = getattr(update, "message", None)
        chat = getattr(update, "effective_chat", None)
        if not message or not chat:
            return

        chat_id = str(chat.id)
        is_verified = self._auth_guard.is_verified(chat_id)
        status = "✅ Verified" if is_verified else "⛔ Not verified"

        await message.reply_text(
            f"Your Chat ID: `{chat_id}`\n"
            f"Status: {status}\n\n"
            f"To authorize this bot, add your Chat ID to:\n"
            f"`BEAVR_MESSAGING__TELEGRAM__VERIFIED_CHAT_IDS={chat_id}`\n"
            f"in your .env file, then restart Beavr.",
            parse_mode="Markdown",
        )

    async def _handle_command(self, update: object, context: object) -> None:  # noqa: ARG002
        """Route a verified command to the registered callback."""
        message = getattr(update, "message", None)
        chat = getattr(update, "effective_chat", None)
        if not message or not chat:
            return

        chat_id = str(chat.id)
        raw_text = sanitize_input(message.text or "")

        if not self._auth_guard.is_verified(chat_id):
            logger.warning("Unverified command attempt from chat %s: %s", chat_id, raw_text)
            await message.reply_text(
                f"⛔ Not authorized.\n\n"
                f"Your Chat ID: `{chat_id}`\n"
                f"Add it to your .env:\n"
                f"`BEAVR_MESSAGING__TELEGRAM__VERIFIED_CHAT_IDS={chat_id}`\n"
                f"Then restart Beavr.",
                parse_mode="Markdown",
            )
            return

        if not self._command_callback:
            await message.reply_text("⚙️ Command processing not configured.")
            return

        # Parse command and args
        parts = raw_text.split()
        command = parts[0].lstrip("/").lower() if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        inbound = InboundCommand(
            raw_text=raw_text,
            command=command,
            args=args,
            sender_id=chat_id,
            platform="telegram",
            timestamp=datetime.utcnow(),
            is_verified=True,
        )

        logger.info("Telegram command: /%s %s (from %s)", command, " ".join(args), chat_id)

        try:
            result = await self._command_callback(inbound)
            await message.reply_text(result.message)
        except Exception:
            logger.exception("Error processing command: %s", raw_text)
            await message.reply_text("❌ Internal error processing command.")

    async def _handle_unknown(self, update: object, context: object) -> None:  # noqa: ARG002
        """Handle unrecognized text messages."""
        message = getattr(update, "message", None)
        if message:
            await message.reply_text(
                "Unknown command. Use /help for available commands."
            )
