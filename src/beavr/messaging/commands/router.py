"""Command router — maps inbound commands to handlers with rate limiting."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Optional

from beavr.messaging.commands.base import BaseCommandHandler
from beavr.models.messaging import CommandResult, InboundCommand

logger = logging.getLogger(__name__)

# Rate limits
MAX_TRADING_COMMANDS_PER_HOUR = 10
MAX_TOTAL_COMMANDS_PER_HOUR = 30


class CommandRouter:
    """Routes inbound commands to registered handlers with rate limiting.

    Attributes:
        handlers: Mapping of command name to handler instance.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, BaseCommandHandler] = {}
        # Rate tracking: sender_id -> list of timestamps
        self._command_timestamps: dict[str, list[float]] = defaultdict(list)
        self._trading_timestamps: dict[str, list[float]] = defaultdict(list)

    def register(self, handler: BaseCommandHandler) -> None:
        """Register a command handler for its command names.

        Args:
            handler: The handler instance to register.
        """
        for name in handler.command_names:
            self._handlers[name] = handler

    async def route(self, command: InboundCommand) -> CommandResult:
        """Route a command to the appropriate handler.

        Applies rate limiting before dispatching.

        Args:
            command: The parsed inbound command.

        Returns:
            CommandResult from the handler, or an error result.
        """
        cmd_name = command.command.lower()

        # Special case: help
        if cmd_name == "help":
            return self._help()

        handler = self._handlers.get(cmd_name)
        if not handler:
            return CommandResult(
                success=False,
                message=f"Unknown command: /{cmd_name}\nUse /help for available commands.",
            )

        # Rate limit check
        rate_result = self._check_rate_limit(command.sender_id, handler.tier)
        if rate_result:
            return rate_result

        try:
            return await handler.handle(command)
        except Exception:
            logger.exception("Error handling command /%s", cmd_name)
            return CommandResult(
                success=False,
                message=f"❌ Error processing /{cmd_name}. Please try again.",
            )

    def _check_rate_limit(self, sender_id: str, tier: str) -> Optional[CommandResult]:
        """Check rate limits and return an error result if exceeded.

        Args:
            sender_id: The sender to rate-limit.
            tier: The command tier ('read', 'analysis', 'trading').

        Returns:
            CommandResult if rate limited, None if within limits.
        """
        now = time.time()
        one_hour_ago = now - 3600

        # Clean old entries
        self._command_timestamps[sender_id] = [
            t for t in self._command_timestamps[sender_id] if t > one_hour_ago
        ]
        self._trading_timestamps[sender_id] = [
            t for t in self._trading_timestamps[sender_id] if t > one_hour_ago
        ]

        # Total command rate limit
        if len(self._command_timestamps[sender_id]) >= MAX_TOTAL_COMMANDS_PER_HOUR:
            return CommandResult(
                success=False,
                message="⏳ Rate limit exceeded. Max 30 commands per hour.",
            )

        # Trading-specific rate limit
        if tier == "trading":
            if len(self._trading_timestamps[sender_id]) >= MAX_TRADING_COMMANDS_PER_HOUR:
                return CommandResult(
                    success=False,
                    message="⏳ Trading rate limit exceeded. Max 10 trading commands per hour.",
                )
            self._trading_timestamps[sender_id].append(now)

        self._command_timestamps[sender_id].append(now)
        return None

    def _help(self) -> CommandResult:
        """Generate help text from all registered handlers.

        Returns:
            CommandResult with formatted help message.
        """
        lines = ["📖 Available Commands:\n"]

        # Group by tier
        by_tier: dict[str, list[BaseCommandHandler]] = defaultdict(list)
        seen: set[int] = set()
        for handler in self._handlers.values():
            hid = id(handler)
            if hid not in seen:
                seen.add(hid)
                by_tier[handler.tier].append(handler)

        tier_labels = {
            "read": "📋 Read-Only",
            "analysis": "🔍 Analysis",
            "trading": "💰 Trading",
        }

        for tier in ["read", "analysis", "trading"]:
            handlers = by_tier.get(tier, [])
            if handlers:
                lines.append(f"\n{tier_labels.get(tier, tier)}:")
                for h in handlers:
                    names = ", ".join(f"/{n}" for n in h.command_names)
                    lines.append(f"  {names} — {h.description}")

        return CommandResult(success=True, message="\n".join(lines))
