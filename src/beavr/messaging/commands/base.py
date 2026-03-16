"""Base command handler for the messaging system."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from beavr.models.messaging import CommandResult, InboundCommand

logger = logging.getLogger(__name__)


class BaseCommandHandler(ABC):
    """Base class for all command handlers.

    Subclasses implement ``handle()`` for their specific command logic.
    """

    @property
    @abstractmethod
    def command_names(self) -> list[str]:
        """Command names this handler responds to (e.g. ['status', 'positions'])."""
        ...

    @property
    @abstractmethod
    def tier(self) -> str:
        """Permission tier: 'read', 'analysis', or 'trading'."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Short help text for this command."""
        ...

    @abstractmethod
    async def handle(self, command: InboundCommand) -> CommandResult:
        """Process the command and return a result.

        Args:
            command: The parsed inbound command.

        Returns:
            CommandResult with success status and response message.
        """
        ...
