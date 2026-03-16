"""Messaging provider protocol definitions.

Defines structural typing protocols (PEP 544) for messaging integrations.
Any class implementing the required methods satisfies the protocol
without explicit inheritance.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol, runtime_checkable

from beavr.models.messaging import CommandResult, InboundCommand, OutboundMessage


@runtime_checkable
class MessagingProvider(Protocol):
    """Protocol for messaging integrations (Telegram, Discord, Slack, etc.).

    A messaging provider handles sending notifications to users and
    receiving inbound commands. Implementations must expose all listed
    methods and properties with matching signatures.
    """

    @property
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g. ``'telegram'``, ``'discord'``)."""
        ...

    async def send_message(self, message: OutboundMessage) -> bool:
        """Send a notification message to the user.

        Args:
            message: The outbound message to deliver.

        Returns:
            True if delivery succeeded, False otherwise.
        """
        ...

    async def start_listening(self) -> None:
        """Start listening for inbound commands (long-polling or webhook)."""
        ...

    async def stop_listening(self) -> None:
        """Stop the listener gracefully."""
        ...

    def set_command_callback(
        self,
        callback: Callable[[InboundCommand], Awaitable[CommandResult]],
    ) -> None:
        """Register the callback invoked when a verified command is received.

        Args:
            callback: Async function that processes an InboundCommand
                      and returns a CommandResult.
        """
        ...
