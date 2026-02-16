"""Tests for BrokerFactory."""

import os
from unittest.mock import MagicMock, patch

import pytest

from beavr.broker.factory import BrokerFactory
from beavr.broker.models import BrokerError
from beavr.models.config import (
    AppConfig,
    BrokerProviderConfig,
    WebullConfig,
)


@pytest.fixture
def _alpaca_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set Alpaca credentials in the environment."""
    monkeypatch.setenv("ALPACA_API_KEY", "fake_key")
    monkeypatch.setenv("ALPACA_API_SECRET", "fake_secret")


@pytest.fixture
def _webull_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set Webull credentials in the environment."""
    monkeypatch.setenv("WEBULL_APP_KEY", "wb_key")
    monkeypatch.setenv("WEBULL_APP_SECRET", "wb_secret")
    monkeypatch.setenv("WEBULL_ACCOUNT_ID", "wb_acct")


class TestCreateBrokerDefault:
    """Tests for BrokerFactory.create_broker with default config."""

    @pytest.mark.usefixtures("_alpaca_env")
    def test_default_no_broker_config_uses_alpaca(self) -> None:
        """When broker config is None, should import and create AlpacaBroker."""
        config = AppConfig()
        mock_broker = MagicMock()
        with patch(
            "beavr.broker.factory.AlpacaBroker", create=True, return_value=mock_broker
        ) as mock_cls, patch.dict(
            "sys.modules",
            {"beavr.broker.alpaca.broker": MagicMock(AlpacaBroker=mock_cls)},
        ):
            result = BrokerFactory.create_broker(config)
        assert result is mock_broker

    @pytest.mark.usefixtures("_alpaca_env")
    def test_explicit_alpaca_provider(self) -> None:
        """When provider is 'alpaca', should create AlpacaBroker."""
        broker_cfg = BrokerProviderConfig(provider="alpaca")
        config = AppConfig(broker=broker_cfg)
        mock_broker = MagicMock()
        with patch(
            "beavr.broker.factory.AlpacaBroker", create=True, return_value=mock_broker
        ) as mock_cls, patch.dict(
            "sys.modules",
            {"beavr.broker.alpaca.broker": MagicMock(AlpacaBroker=mock_cls)},
        ):
            result = BrokerFactory.create_broker(config)
        assert result is mock_broker

    def test_alpaca_missing_credentials_raises(self) -> None:
        """When Alpaca credentials are not set, should raise BrokerError."""
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_API_SECRET", None)
        config = AppConfig()
        with pytest.raises(BrokerError, match="missing_credentials"):
            BrokerFactory.create_broker(config)


class TestCreateBrokerWebull:
    """Tests for BrokerFactory.create_broker with Webull provider."""

    def test_webull_paper_trading_raises(self) -> None:
        """When provider is 'webull' and paper=True, should raise BrokerError."""
        webull_cfg = WebullConfig()
        broker_cfg = BrokerProviderConfig(provider="webull", paper=True, webull=webull_cfg)
        config = AppConfig(broker=broker_cfg)
        with pytest.raises(BrokerError, match="paper_not_supported"):
            BrokerFactory.create_broker(config)

    def test_webull_no_webull_config_raises(self) -> None:
        """When provider is 'webull' but no webull config, should raise."""
        broker_cfg = BrokerProviderConfig(provider="webull", paper=False)
        config = AppConfig(broker=broker_cfg)
        with pytest.raises(BrokerError, match="missing_config"):
            BrokerFactory.create_broker(config)

    def test_webull_missing_credentials_raises(self) -> None:
        """When Webull credentials are not set, should raise BrokerError."""
        os.environ.pop("WEBULL_APP_KEY", None)
        os.environ.pop("WEBULL_APP_SECRET", None)
        webull_cfg = WebullConfig()
        broker_cfg = BrokerProviderConfig(provider="webull", paper=False, webull=webull_cfg)
        config = AppConfig(broker=broker_cfg)
        with pytest.raises(BrokerError, match="missing_credentials"):
            BrokerFactory.create_broker(config)

    @pytest.mark.usefixtures("_webull_env")
    def test_webull_with_credentials_creates_broker(self) -> None:
        """When Webull credentials are set and paper=False, should create WebullBroker."""
        webull_cfg = WebullConfig()
        broker_cfg = BrokerProviderConfig(provider="webull", paper=False, webull=webull_cfg)
        config = AppConfig(broker=broker_cfg)
        mock_broker = MagicMock()
        with patch(
            "beavr.broker.factory.WebullBroker", create=True, return_value=mock_broker
        ) as mock_cls, patch.dict(
            "sys.modules",
            {"beavr.broker.webull.broker": MagicMock(WebullBroker=mock_cls)},
        ):
            result = BrokerFactory.create_broker(config)
        assert result is mock_broker


class TestCreateDataProvider:
    """Tests for BrokerFactory.create_data_provider."""

    @pytest.mark.usefixtures("_alpaca_env")
    def test_default_creates_alpaca_data_provider(self) -> None:
        """Default config should create AlpacaMarketData."""
        config = AppConfig()
        mock_data = MagicMock()
        with patch(
            "beavr.broker.factory.AlpacaMarketData", create=True, return_value=mock_data
        ) as mock_cls, patch.dict(
            "sys.modules",
            {"beavr.broker.alpaca.data": MagicMock(AlpacaMarketData=mock_cls)},
        ):
            result = BrokerFactory.create_data_provider(config)
        assert result is mock_data

    def test_missing_alpaca_credentials_raises(self) -> None:
        """When Alpaca credentials missing, should raise BrokerError."""
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_API_SECRET", None)
        config = AppConfig()
        with pytest.raises(BrokerError, match="missing_credentials"):
            BrokerFactory.create_data_provider(config)


class TestCreateScreener:
    """Tests for BrokerFactory.create_screener."""

    def test_no_credentials_returns_none(self) -> None:
        """Without Alpaca credentials, screener should return None."""
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_API_SECRET", None)
        config = AppConfig()
        result = BrokerFactory.create_screener(config)
        assert result is None


class TestCreateNewsProvider:
    """Tests for BrokerFactory.create_news_provider."""

    def test_no_credentials_returns_none(self) -> None:
        """Without Alpaca credentials, news provider should return None."""
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_API_SECRET", None)
        config = AppConfig()
        result = BrokerFactory.create_news_provider(config)
        assert result is None

    @pytest.mark.usefixtures("_alpaca_env")
    def test_with_credentials_creates_provider(self) -> None:
        """With Alpaca credentials, should create AlpacaNews."""
        config = AppConfig()
        mock_news = MagicMock()
        with patch(
            "beavr.broker.factory.AlpacaNews", create=True, return_value=mock_news
        ) as mock_cls, patch.dict(
            "sys.modules",
            {"beavr.broker.alpaca.news": MagicMock(AlpacaNews=mock_cls)},
        ):
            result = BrokerFactory.create_news_provider(config)
        assert result is mock_news


class TestCreateBrokerUnsupported:
    """Tests for unsupported broker provider."""

    def test_unsupported_broker_provider_raises(self) -> None:
        """An unknown provider string should raise BrokerError."""
        broker_cfg = BrokerProviderConfig.model_construct(provider="foobar")
        config = AppConfig.model_construct(broker=broker_cfg, alpaca=AppConfig().alpaca)
        with pytest.raises(BrokerError, match="unsupported_provider"):
            BrokerFactory.create_broker(config)


class TestCreateDataProviderWebull:
    """Tests for BrokerFactory.create_data_provider with Webull."""

    @pytest.mark.usefixtures("_webull_env")
    def test_webull_data_provider_with_credentials(self) -> None:
        """Webull data provider should be created when credentials exist."""
        webull_cfg = WebullConfig()
        broker_cfg = BrokerProviderConfig(provider="webull", webull=webull_cfg)
        config = AppConfig(broker=broker_cfg)
        mock_data = MagicMock()
        mock_api_client_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "webullsdkcore": MagicMock(),
                "webullsdkcore.client": MagicMock(ApiClient=mock_api_client_cls),
                "beavr.broker.webull": MagicMock(),
                "beavr.broker.webull.data": MagicMock(WebullMarketData=MagicMock(return_value=mock_data)),
            },
        ):
            result = BrokerFactory.create_data_provider(config)
        assert result is mock_data

    def test_webull_data_provider_missing_config_raises(self) -> None:
        """Webull data provider without webull config should raise."""
        broker_cfg = BrokerProviderConfig(provider="webull")
        config = AppConfig(broker=broker_cfg)
        with pytest.raises(BrokerError, match="missing_config"):
            BrokerFactory.create_data_provider(config)

    def test_webull_data_provider_missing_credentials_raises(self) -> None:
        """Webull data provider without credentials should raise."""
        os.environ.pop("WEBULL_APP_KEY", None)
        os.environ.pop("WEBULL_APP_SECRET", None)
        webull_cfg = WebullConfig()
        broker_cfg = BrokerProviderConfig(provider="webull", webull=webull_cfg)
        config = AppConfig(broker=broker_cfg)
        with pytest.raises(BrokerError, match="missing_credentials"):
            BrokerFactory.create_data_provider(config)


class TestCreateDataProviderUnsupported:
    """Tests for unsupported data provider."""

    def test_unsupported_data_provider_raises(self) -> None:
        """An unknown data provider string should raise BrokerError."""
        broker_cfg = BrokerProviderConfig.model_construct(provider="foobar")
        config = AppConfig.model_construct(broker=broker_cfg, alpaca=AppConfig().alpaca)
        with pytest.raises(BrokerError, match="unsupported_provider"):
            BrokerFactory.create_data_provider(config)


class TestCreateScreenerWithCredentials:
    """Tests for BrokerFactory.create_screener with valid creds."""

    @pytest.mark.usefixtures("_alpaca_env")
    def test_screener_with_credentials_creates_instance(self) -> None:
        """With Alpaca credentials, should create AlpacaScreener."""
        config = AppConfig()
        mock_screener = MagicMock()
        with patch(
            "beavr.broker.factory.AlpacaScreener", create=True, return_value=mock_screener
        ) as mock_cls, patch.dict(
            "sys.modules",
            {"beavr.broker.alpaca.screener": MagicMock(AlpacaScreener=mock_cls)},
        ):
            result = BrokerFactory.create_screener(config)
        assert result is mock_screener
