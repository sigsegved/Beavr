"""Broker and provider factory.

Creates broker, market-data, screener, and news provider instances
from application configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from beavr.broker.models import BrokerError
from beavr.broker.protocols import (
    BrokerProvider,
    MarketDataProvider,
    NewsProvider,
    ScreenerProvider,
)

if TYPE_CHECKING:
    from beavr.models.config import AppConfig

logger = logging.getLogger(__name__)


class BrokerFactory:
    """Factory that creates provider instances from configuration."""

    @staticmethod
    def create_broker(config: AppConfig) -> BrokerProvider:
        """Create a BrokerProvider from app config.

        If config.broker is set, uses that. Otherwise defaults to Alpaca
        using config.alpaca for backward compatibility.
        """
        broker_config = config.broker

        if broker_config is None or broker_config.provider == "alpaca":
            alpaca_cfg = (
                broker_config.alpaca
                if broker_config and broker_config.alpaca
                else config.alpaca
            )
            api_key = alpaca_cfg.get_api_key()
            api_secret = alpaca_cfg.get_api_secret()
            if not api_key or not api_secret:
                raise BrokerError(
                    error_code="missing_credentials",
                    message="Alpaca API key and secret must be set",
                    broker_name="alpaca",
                )
            # Import here to avoid circular deps and optional deps
            from beavr.broker.alpaca.broker import AlpacaBroker

            paper = broker_config.paper if broker_config else alpaca_cfg.paper
            return AlpacaBroker(api_key=api_key, api_secret=api_secret, paper=paper)

        elif broker_config.provider == "webull":
            webull_cfg = broker_config.webull
            if not webull_cfg:
                raise BrokerError(
                    error_code="missing_config",
                    message="Webull config required when provider is 'webull'",
                    broker_name="webull",
                )
            app_key = webull_cfg.get_app_key()
            app_secret = webull_cfg.get_app_secret()
            if not app_key or not app_secret:
                raise BrokerError(
                    error_code="missing_credentials",
                    message="Webull app key and secret must be set",
                    broker_name="webull",
                )
            from beavr.broker.webull.broker import WebullBroker

            account_id = webull_cfg.get_account_id()
            return WebullBroker(
                app_key=app_key,
                app_secret=app_secret,
                account_id=account_id,
                region=webull_cfg.region,
                paper=broker_config.paper,
            )
        else:
            raise BrokerError(
                error_code="unsupported_provider",
                message=f"Unsupported broker provider: '{broker_config.provider}'",
                broker_name="unknown",
            )

    @staticmethod
    def create_data_provider(config: AppConfig) -> MarketDataProvider:
        """Create a MarketDataProvider from app config."""
        # For now, data provider follows the broker
        broker_config = config.broker
        provider = "alpaca"
        if broker_config:
            provider = broker_config.provider

        if provider == "alpaca":
            alpaca_cfg = (
                broker_config.alpaca
                if broker_config and broker_config.alpaca
                else config.alpaca
            )
            api_key = alpaca_cfg.get_api_key()
            api_secret = alpaca_cfg.get_api_secret()
            if not api_key or not api_secret:
                raise BrokerError(
                    error_code="missing_credentials",
                    message="Alpaca API key and secret needed for data",
                    broker_name="alpaca",
                )
            from beavr.broker.alpaca.data import AlpacaMarketData

            return AlpacaMarketData(api_key=api_key, api_secret=api_secret)
        elif provider == "webull":
            webull_cfg = broker_config.webull if broker_config else None
            if not webull_cfg:
                raise BrokerError(
                    error_code="missing_config",
                    message="Webull config required for data provider",
                    broker_name="webull",
                )
            app_key = webull_cfg.get_app_key()
            app_secret = webull_cfg.get_app_secret()
            if not app_key or not app_secret:
                raise BrokerError(
                    error_code="missing_credentials",
                    message="Webull credentials needed for data",
                    broker_name="webull",
                )
            from beavr.broker.webull.data import WebullMarketData

            return WebullMarketData(
                app_key=app_key,
                app_secret=app_secret,
                region=webull_cfg.region,
            )
        else:
            raise BrokerError(
                error_code="unsupported_provider",
                message=f"Unsupported data provider: '{provider}'",
                broker_name="unknown",
            )

    @staticmethod
    def create_screener(config: AppConfig) -> Optional[ScreenerProvider]:
        """Create a ScreenerProvider. Only Alpaca supports this currently."""
        alpaca_cfg = config.alpaca
        api_key = alpaca_cfg.get_api_key()
        api_secret = alpaca_cfg.get_api_secret()
        if not api_key or not api_secret:
            logger.warning("No Alpaca credentials — screener unavailable")
            return None
        from beavr.broker.alpaca.screener import AlpacaScreener

        return AlpacaScreener(api_key=api_key, api_secret=api_secret)

    @staticmethod
    def create_news_provider(config: AppConfig) -> Optional[NewsProvider]:
        """Create a NewsProvider. Only Alpaca supports this currently."""
        alpaca_cfg = config.alpaca
        api_key = alpaca_cfg.get_api_key()
        api_secret = alpaca_cfg.get_api_secret()
        if not api_key or not api_secret:
            logger.warning("No Alpaca credentials — news provider unavailable")
            return None
        from beavr.broker.alpaca.news import AlpacaNews

        return AlpacaNews(api_key=api_key, api_secret=api_secret)
