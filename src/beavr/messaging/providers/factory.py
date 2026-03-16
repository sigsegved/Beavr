"""Messaging provider factory.

Creates provider instances from application configuration,
following the same pattern as BrokerFactory.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from beavr.messaging.auth import AuthGuard
from beavr.messaging.protocols import MessagingProvider

if TYPE_CHECKING:
    from beavr.models.config import MessagingConfig

logger = logging.getLogger(__name__)


class MessagingProviderFactory:
    """Factory that creates messaging provider instances from configuration."""

    @staticmethod
    def create(config: MessagingConfig) -> MessagingProvider:
        """Create a MessagingProvider from messaging config.

        Args:
            config: MessagingConfig with provider selection and credentials.

        Returns:
            A configured MessagingProvider instance.

        Raises:
            ValueError: If the provider is unsupported or misconfigured.
        """
        if config.provider == "telegram":
            return MessagingProviderFactory._create_telegram(config)
        else:
            raise ValueError(f"Unsupported messaging provider: '{config.provider}'")

    @staticmethod
    def _create_telegram(config: MessagingConfig) -> MessagingProvider:
        """Create a TelegramProvider instance.

        Args:
            config: MessagingConfig with telegram sub-config.

        Returns:
            Configured TelegramProvider.

        Raises:
            ValueError: If Telegram bot token is missing.
        """
        from beavr.messaging.providers.telegram import TelegramProvider

        tg_config = config.telegram
        if not tg_config:
            raise ValueError(
                "Telegram config required when provider is 'telegram'. "
                "Set messaging.telegram in your config."
            )

        bot_token = tg_config.get_bot_token()
        if not bot_token:
            raise ValueError(
                f"Telegram bot token not found. "
                f"Set the {tg_config.bot_token_env} environment variable."
            )

        auth_guard = AuthGuard(
            verified_chat_ids=list(tg_config.verified_chat_ids),
        )

        return TelegramProvider(
            bot_token=bot_token,
            auth_guard=auth_guard,
            chat_ids=list(tg_config.verified_chat_ids),
        )
