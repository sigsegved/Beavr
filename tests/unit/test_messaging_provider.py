"""Tests for messaging provider factory and protocol."""

import os
from unittest.mock import MagicMock

import pytest

from beavr.messaging.protocols import MessagingProvider
from beavr.messaging.providers.factory import MessagingProviderFactory
from beavr.models.config import MessagingConfig, TelegramConfig


class TestMessagingProviderProtocol:
    """Tests for MessagingProvider protocol compliance."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Protocol should support isinstance checks."""
        from beavr.messaging.providers.telegram import TelegramProvider
        from beavr.messaging.auth import AuthGuard

        provider = TelegramProvider(
            bot_token="fake:token",
            auth_guard=AuthGuard(),
        )
        assert isinstance(provider, MessagingProvider)


class TestMessagingProviderFactory:
    """Tests for MessagingProviderFactory."""

    def test_create_telegram_success(self) -> None:
        env_key = "BEAVR_TEST_BOT_TOKEN"
        os.environ[env_key] = "123456:ABC"
        try:
            config = MessagingConfig(
                enabled=True,
                provider="telegram",
                telegram=TelegramConfig(
                    bot_token_env=env_key,
                    verified_chat_ids=["12345"],
                ),
            )
            provider = MessagingProviderFactory.create(config)
            assert provider.provider_name == "telegram"
        finally:
            del os.environ[env_key]

    def test_create_telegram_no_config(self) -> None:
        config = MessagingConfig(enabled=True, provider="telegram", telegram=None)
        with pytest.raises(ValueError, match="Telegram config required"):
            MessagingProviderFactory.create(config)

    def test_create_telegram_no_token(self) -> None:
        env_key = "BEAVR_TEST_MISSING_TOKEN"
        os.environ.pop(env_key, None)
        config = MessagingConfig(
            enabled=True,
            provider="telegram",
            telegram=TelegramConfig(bot_token_env=env_key),
        )
        with pytest.raises(ValueError, match="bot token not found"):
            MessagingProviderFactory.create(config)

    def test_create_unsupported_provider(self) -> None:
        # Use a valid literal for construction but test the factory rejects unknown
        # Since provider is a Literal["telegram"], we need to bypass validation
        config = MagicMock(spec=MessagingConfig)
        config.provider = "discord"
        with pytest.raises(ValueError, match="Unsupported"):
            MessagingProviderFactory.create(config)


class TestMessagingConfig:
    """Tests for MessagingConfig model."""

    def test_defaults(self) -> None:
        config = MessagingConfig()
        assert config.enabled is False
        assert config.provider == "telegram"
        assert config.telegram is None
        assert config.notify_on_dd is True
        assert config.notify_on_trade is True
        assert config.accept_commands is True

    def test_telegram_config(self) -> None:
        tg = TelegramConfig(
            bot_token_env="MY_TOKEN",
            verified_chat_ids=["111", "222"],
        )
        config = MessagingConfig(
            enabled=True,
            telegram=tg,
        )
        assert config.telegram is not None
        assert config.telegram.verified_chat_ids == ["111", "222"]

    def test_telegram_get_bot_token(self) -> None:
        env_key = "BEAVR_TEST_TG_TOKEN"
        os.environ[env_key] = "test_token_value"
        try:
            tg = TelegramConfig(bot_token_env=env_key)
            assert tg.get_bot_token() == "test_token_value"
        finally:
            del os.environ[env_key]

    def test_telegram_get_bot_token_missing(self) -> None:
        env_key = "BEAVR_NONEXISTENT_TG_TOKEN"
        os.environ.pop(env_key, None)
        tg = TelegramConfig(bot_token_env=env_key)
        assert tg.get_bot_token() is None

    def test_chat_ids_coerces_int(self) -> None:
        tg = TelegramConfig(verified_chat_ids=8274199741)
        assert tg.verified_chat_ids == ["8274199741"]

    def test_chat_ids_coerces_comma_string(self) -> None:
        tg = TelegramConfig(verified_chat_ids="111,222,333")
        assert tg.verified_chat_ids == ["111", "222", "333"]

    def test_chat_ids_coerces_single_string(self) -> None:
        tg = TelegramConfig(verified_chat_ids="8274199741")
        assert tg.verified_chat_ids == ["8274199741"]
