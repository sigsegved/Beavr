"""Authentication guard for the messaging system.

Validates that inbound messages come from verified users by checking
their chat ID against a pre-configured allowlist. Chat IDs are
unforgeable — Telegram guarantees them per-user.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Valid ticker: 1-5 uppercase alphanumeric characters
_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}$")

# Maximum inbound message length
MAX_MESSAGE_LENGTH = 500


class AuthGuard:
    """Validates sender identity via chat ID allowlist.

    Chat IDs are set in config (``BEAVR_MESSAGING__TELEGRAM__VERIFIED_CHAT_IDS``).
    Use the ``/chatid`` bot command to discover your ID, then add it to config.

    Attributes:
        verified_chat_ids: Set of chat IDs allowed to interact with the bot.
    """

    def __init__(
        self,
        verified_chat_ids: Optional[list[str]] = None,
    ) -> None:
        self.verified_chat_ids: set[str] = set(verified_chat_ids or [])

    def is_verified(self, sender_id: str) -> bool:
        """Check whether a sender is in the verified allowlist.

        Args:
            sender_id: Platform-specific user/chat identifier.

        Returns:
            True if the sender is verified.
        """
        return sender_id in self.verified_chat_ids

    def add_verified(self, sender_id: str) -> None:
        """Add a chat ID to the verified allowlist.

        Args:
            sender_id: Platform-specific user/chat identifier.
        """
        self.verified_chat_ids.add(sender_id)

    def remove_verified(self, sender_id: str) -> None:
        """Remove a chat ID from the verified allowlist.

        Args:
            sender_id: Platform-specific user/chat identifier.
        """
        self.verified_chat_ids.discard(sender_id)


def sanitize_input(text: str) -> str:
    """Sanitize and length-limit inbound message text.

    Args:
        text: Raw inbound message text.

    Returns:
        Cleaned, length-limited text.
    """
    cleaned = text.strip()
    if len(cleaned) > MAX_MESSAGE_LENGTH:
        cleaned = cleaned[:MAX_MESSAGE_LENGTH]
    return cleaned


def validate_symbol(symbol: str) -> bool:
    """Validate that a string looks like a stock ticker symbol.

    Args:
        symbol: Candidate ticker string.

    Returns:
        True if the symbol matches the expected pattern (1-5 uppercase letters).
    """
    return bool(_SYMBOL_PATTERN.match(symbol.upper()))
