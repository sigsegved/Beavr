"""Trading command handlers: /buy, /sell, /confirm, /cancel.

All trading goes through BeavrAPI — no direct broker or repo access.
Trading commands require explicit confirmation within a timeout window.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from beavr.messaging.auth import validate_symbol
from beavr.messaging.commands.base import BaseCommandHandler
from beavr.models.messaging import CommandResult, InboundCommand, PendingConfirmation

if TYPE_CHECKING:
    from beavr.messaging.api import BeavrAPI

logger = logging.getLogger(__name__)

# Confirmation timeout in seconds
CONFIRM_TIMEOUT_SECONDS = 60


class TradingCommandHandler(BaseCommandHandler):
    """Handles /buy, /sell, /confirm, /cancel trading commands.

    Trading commands go through a two-step flow:
    1. User sends /buy AAPL $500 → bot shows preview and asks for /confirm
    2. User sends /confirm → bot executes via BeavrAPI
    """

    command_names: list[str] = ["buy", "sell", "confirm", "cancel"]
    tier: str = "trading"
    description: str = "Buy/sell stocks (requires confirmation)"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api
        # chat_id -> PendingConfirmation
        self._pending: dict[str, PendingConfirmation] = {}

    async def handle(self, command: InboundCommand) -> CommandResult:
        cmd = command.command.lower()

        if cmd == "buy":
            return self._handle_buy(command)
        elif cmd == "sell":
            return self._handle_sell(command)
        elif cmd == "confirm":
            return await self._handle_confirm(command)
        elif cmd == "cancel":
            return self._handle_cancel(command)
        else:
            return CommandResult(success=False, message=f"Unknown trading command: /{cmd}")

    def _handle_buy(self, command: InboundCommand) -> CommandResult:
        """Stage a buy order for confirmation."""
        if len(command.args) < 2:
            return CommandResult(
                success=False,
                message="Usage: /buy <SYMBOL> <$AMOUNT>\nExample: /buy AAPL $500",
            )

        symbol = command.args[0].upper()
        if not validate_symbol(symbol):
            return CommandResult(
                success=False,
                message=f"❌ Invalid symbol: {symbol}",
            )

        amount_str = command.args[1].lstrip("$").replace(",", "")
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise InvalidOperation("Amount must be positive")
        except (InvalidOperation, ValueError):
            return CommandResult(
                success=False,
                message=f"❌ Invalid amount: {command.args[1]}. Use a positive number.",
            )

        from datetime import datetime, timedelta

        pending = PendingConfirmation(
            chat_id=command.sender_id,
            command="buy",
            symbol=symbol,
            amount=amount,
            expires_at=datetime.utcnow() + timedelta(seconds=CONFIRM_TIMEOUT_SECONDS),
        )
        self._pending[command.sender_id] = pending

        return CommandResult(
            success=True,
            message=(
                f"⚠️ CONFIRM TRADE\n"
                f"Action: BUY {symbol}\n"
                f"Amount: ${amount:,.2f}\n\n"
                f"Reply /confirm within 60s to execute.\n"
                f"Reply /cancel to abort."
            ),
        )

    def _handle_sell(self, command: InboundCommand) -> CommandResult:
        """Stage a sell order for confirmation."""
        if not command.args:
            return CommandResult(
                success=False,
                message="Usage: /sell <SYMBOL> [QUANTITY]\nExample: /sell AAPL 10",
            )

        symbol = command.args[0].upper()
        if not validate_symbol(symbol):
            return CommandResult(
                success=False,
                message=f"❌ Invalid symbol: {symbol}",
            )

        quantity: Optional[Decimal] = None
        if len(command.args) > 1:
            try:
                quantity = Decimal(command.args[1])
                if quantity <= 0:
                    raise InvalidOperation("Quantity must be positive")
            except (InvalidOperation, ValueError):
                return CommandResult(
                    success=False,
                    message=f"❌ Invalid quantity: {command.args[1]}",
                )

        from datetime import datetime, timedelta

        pending = PendingConfirmation(
            chat_id=command.sender_id,
            command="sell",
            symbol=symbol,
            quantity=quantity,
            expires_at=datetime.utcnow() + timedelta(seconds=CONFIRM_TIMEOUT_SECONDS),
        )
        self._pending[command.sender_id] = pending

        qty_text = f"{quantity} shares" if quantity else "all shares"
        return CommandResult(
            success=True,
            message=(
                f"⚠️ CONFIRM TRADE\n"
                f"Action: SELL {symbol} ({qty_text})\n\n"
                f"Reply /confirm within 60s to execute.\n"
                f"Reply /cancel to abort."
            ),
        )

    async def _handle_confirm(self, command: InboundCommand) -> CommandResult:
        """Execute a pending trade via BeavrAPI after confirmation."""
        pending = self._pending.pop(command.sender_id, None)
        if not pending:
            return CommandResult(
                success=False,
                message="No pending trade to confirm.",
            )

        from datetime import datetime

        if datetime.utcnow() > pending.expires_at:
            return CommandResult(
                success=False,
                message="⏰ Confirmation expired. Please re-enter the trade command.",
            )

        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        try:
            if pending.command == "buy" and pending.amount is not None:
                result = self._api.submit_buy_order(pending.symbol, pending.amount)
            elif pending.command == "sell":
                result = self._api.submit_sell_order(pending.symbol, pending.quantity)
            else:
                return CommandResult(success=False, message="❌ Invalid pending command.")

            return CommandResult(
                success=True,
                message=(
                    f"✅ Order submitted!\n"
                    f"Order ID: {result['order_id']}\n"
                    f"Status: {result['status']}"
                ),
                data=result,
            )
        except Exception as e:
            logger.exception("Error executing %s for %s", pending.command, pending.symbol)
            return CommandResult(
                success=False,
                message=f"❌ Order failed: {e}",
            )

    def _handle_cancel(self, command: InboundCommand) -> CommandResult:
        """Cancel a pending trade confirmation."""
        pending = self._pending.pop(command.sender_id, None)
        if pending:
            return CommandResult(
                success=True,
                message=f"🚫 Cancelled pending {pending.command.upper()} {pending.symbol}.",
            )
        return CommandResult(
            success=True,
            message="No pending trade to cancel.",
        )
