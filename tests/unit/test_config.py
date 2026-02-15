"""Unit tests for configuration models and loading."""

import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from beavr.core.config import load_strategy_config, load_toml
from beavr.models.config import (
    AlpacaConfig,
    AppConfig,
    BacktestConfig,
    BrokerProviderConfig,
    DataProviderConfig,
    DipBuyDCAParams,
    NewsProviderConfig,
    SimpleDCAParams,
    StrategyConfig,
    WebullConfig,
)


class TestAlpacaConfig:
    """Tests for AlpacaConfig."""

    def test_default_config(self) -> None:
        """Test default Alpaca configuration."""
        config = AlpacaConfig()
        assert config.api_key_env == "ALPACA_API_KEY"
        assert config.api_secret_env == "ALPACA_API_SECRET"
        assert config.paper is True

    def test_get_api_key_from_env(self) -> None:
        """Test getting API key from environment."""
        config = AlpacaConfig()
        # Set env var temporarily
        os.environ["ALPACA_API_KEY"] = "test_key_123"
        try:
            assert config.get_api_key() == "test_key_123"
        finally:
            del os.environ["ALPACA_API_KEY"]

    def test_get_api_key_missing(self) -> None:
        """Test getting API key when not set."""
        config = AlpacaConfig()
        # Ensure env var is not set
        os.environ.pop("ALPACA_API_KEY", None)
        assert config.get_api_key() is None


class TestAppConfig:
    """Tests for AppConfig."""

    def test_default_config(self) -> None:
        """Test default application configuration."""
        config = AppConfig()
        assert config.data_dir == Path.home() / ".beavr"
        assert config.database_path == Path.home() / ".beavr" / "beavr.db"

    def test_custom_db_path(self) -> None:
        """Test custom database path."""
        config = AppConfig(db_path=Path("/custom/path/db.sqlite"))
        assert config.database_path == Path("/custom/path/db.sqlite")

    def test_env_prefix(self) -> None:
        """Test that BEAVR_ env prefix works."""
        os.environ["BEAVR_DATA_DIR"] = "/tmp/beavr_test"
        try:
            config = AppConfig()
            assert config.data_dir == Path("/tmp/beavr_test")
        finally:
            del os.environ["BEAVR_DATA_DIR"]


class TestStrategyConfig:
    """Tests for StrategyConfig."""

    def test_minimal_config(self) -> None:
        """Test minimal strategy configuration."""
        config = StrategyConfig(template="simple_dca")
        assert config.template == "simple_dca"
        assert config.params == {}
        assert config.enabled is True

    def test_full_config(self) -> None:
        """Test full strategy configuration."""
        config = StrategyConfig(
            template="dip_buy_dca",
            name="My DCA Strategy",
            params={"symbols": ["SPY", "QQQ"], "monthly_budget": 1000},
            enabled=True,
        )
        assert config.template == "dip_buy_dca"
        assert config.name == "My DCA Strategy"
        assert config.params["symbols"] == ["SPY", "QQQ"]


class TestSimpleDCAParams:
    """Tests for SimpleDCAParams."""

    def test_default_params(self) -> None:
        """Test default Simple DCA parameters."""
        params = SimpleDCAParams()
        assert params.symbols == ["SPY"]
        assert params.amount == Decimal("1000")
        assert params.frequency == "monthly"
        assert params.day_of_month == 1

    def test_custom_params(self) -> None:
        """Test custom Simple DCA parameters."""
        params = SimpleDCAParams(
            symbols=["QQQ", "VTI"],
            amount=Decimal("1000"),
            frequency="weekly",
            day_of_week=4,  # Friday
        )
        assert params.symbols == ["QQQ", "VTI"]
        assert params.amount == Decimal("1000")
        assert params.frequency == "weekly"
        assert params.day_of_week == 4

    def test_is_frozen(self) -> None:
        """Test that SimpleDCAParams is immutable."""
        params = SimpleDCAParams()
        with pytest.raises(ValidationError):
            params.amount = Decimal("1000")  # type: ignore

    def test_validation_day_of_month(self) -> None:
        """Test day_of_month validation."""
        with pytest.raises(ValueError):
            SimpleDCAParams(day_of_month=0)  # Too low
        with pytest.raises(ValueError):
            SimpleDCAParams(day_of_month=29)  # Too high


class TestDipBuyDCAParams:
    """Tests for DipBuyDCAParams."""

    def test_default_params(self) -> None:
        """Test default Dip Buy DCA parameters."""
        params = DipBuyDCAParams()
        assert params.symbols == ["SPY"]
        assert params.monthly_budget == Decimal("1000")
        assert params.base_buy_pct == 0.50
        assert params.dip_tier_1 == 0.01
        assert params.dip_tier_1_pct == 0.20
        assert params.dip_tier_2 == 0.02
        assert params.dip_tier_2_pct == 0.40
        assert params.dip_tier_3 == 0.03
        assert params.dip_tier_3_pct == 0.75
        assert params.max_dip_buys == 8
        assert params.lookback_days == 1
        assert params.fallback_days == 3

    def test_validation_dip_tiers(self) -> None:
        """Test dip tier validation."""
        # Tier 1 too low (below 0.005)
        with pytest.raises(ValueError):
            DipBuyDCAParams(dip_tier_1=0.001)
        # Tier 3 too high (above 0.20)
        with pytest.raises(ValueError):
            DipBuyDCAParams(dip_tier_3=0.25)
        # Valid tiers
        params = DipBuyDCAParams(dip_tier_1=0.01, dip_tier_2=0.03, dip_tier_3=0.05)
        assert params.dip_tier_1 == 0.01
        assert params.dip_tier_2 == 0.03
        assert params.dip_tier_3 == 0.05


class TestBacktestConfig:
    """Tests for BacktestConfig."""

    def test_backtest_config(self) -> None:
        """Test backtest configuration."""
        config = BacktestConfig(
            initial_cash=Decimal("10000"),
            start_date="2020-01-01",
            end_date="2024-12-31",
            strategy=StrategyConfig(template="simple_dca"),
        )
        assert config.initial_cash == Decimal("10000")
        assert config.start_date == "2020-01-01"
        assert config.end_date == "2024-12-31"


class TestTOMLLoading:
    """Tests for TOML file loading."""

    def test_load_simple_toml(self) -> None:
        """Test loading a simple TOML file."""
        toml_content = """
template = "simple_dca"
name = "Test Strategy"

[params]
symbols = ["SPY", "QQQ"]
amount = 500
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as f:
            f.write(toml_content)
            f.flush()
            path = Path(f.name)

        try:
            data = load_toml(path)
            assert data["template"] == "simple_dca"
            assert data["name"] == "Test Strategy"
            assert data["params"]["symbols"] == ["SPY", "QQQ"]
        finally:
            path.unlink()

    def test_load_strategy_config_from_toml(self) -> None:
        """Test loading StrategyConfig from TOML."""
        toml_content = """
template = "dip_buy_dca"
name = "My Dip Strategy"

[params]
symbols = ["SPY"]
monthly_budget = 1000
dip_threshold = 0.03
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as f:
            f.write(toml_content)
            f.flush()
            path = Path(f.name)

        try:
            config = load_strategy_config(path)
            assert config.template == "dip_buy_dca"
            assert config.name == "My Dip Strategy"
            assert config.params["monthly_budget"] == 1000
        finally:
            path.unlink()

    def test_load_example_simple_dca(self) -> None:
        """Test loading the example simple_dca.toml."""
        example_path = Path(__file__).parent.parent.parent / "examples" / "strategies" / "simple_dca.toml"
        if example_path.exists():
            config = load_strategy_config(example_path)
            assert config.template == "simple_dca"
            assert "amount" in config.params

    def test_load_example_dip_buy_dca(self) -> None:
        """Test loading the example dip_buy_dca.toml."""
        example_path = Path(__file__).parent.parent.parent / "examples" / "strategies" / "dip_buy_dca.toml"
        if example_path.exists():
            config = load_strategy_config(example_path)
            assert config.template == "dip_buy_dca"
            assert "monthly_budget" in config.params


class TestWebullConfig:
    """Tests for WebullConfig."""

    def test_default_config(self) -> None:
        """Test default Webull configuration."""
        config = WebullConfig()
        assert config.app_key_env == "WEBULL_APP_KEY"
        assert config.app_secret_env == "WEBULL_APP_SECRET"
        assert config.account_id_env == "WEBULL_ACCOUNT_ID"
        assert config.region == "us"

    def test_custom_env_vars(self) -> None:
        """Test custom env var names."""
        config = WebullConfig(
            app_key_env="MY_WB_KEY",
            app_secret_env="MY_WB_SECRET",
            account_id_env="MY_WB_ACCT",
        )
        assert config.app_key_env == "MY_WB_KEY"
        assert config.app_secret_env == "MY_WB_SECRET"
        assert config.account_id_env == "MY_WB_ACCT"

    def test_get_app_key_from_env(self) -> None:
        """Test getting app key from environment."""
        config = WebullConfig()
        os.environ["WEBULL_APP_KEY"] = "test_wb_key"
        try:
            assert config.get_app_key() == "test_wb_key"
        finally:
            del os.environ["WEBULL_APP_KEY"]

    def test_get_app_key_missing(self) -> None:
        """Test getting app key when not set."""
        config = WebullConfig()
        os.environ.pop("WEBULL_APP_KEY", None)
        assert config.get_app_key() is None

    def test_get_app_secret_from_env(self) -> None:
        """Test getting app secret from environment."""
        config = WebullConfig()
        os.environ["WEBULL_APP_SECRET"] = "test_wb_secret"
        try:
            assert config.get_app_secret() == "test_wb_secret"
        finally:
            del os.environ["WEBULL_APP_SECRET"]

    def test_get_account_id_from_env(self) -> None:
        """Test getting account ID from environment."""
        config = WebullConfig()
        os.environ["WEBULL_ACCOUNT_ID"] = "acct_123"
        try:
            assert config.get_account_id() == "acct_123"
        finally:
            del os.environ["WEBULL_ACCOUNT_ID"]

    def test_region_validation(self) -> None:
        """Test that region must be us, hk, or jp."""
        with pytest.raises(ValidationError):
            WebullConfig(region="eu")  # type: ignore


class TestBrokerProviderConfig:
    """Tests for BrokerProviderConfig."""

    def test_default_provider_is_alpaca(self) -> None:
        """Test default provider is alpaca."""
        config = BrokerProviderConfig()
        assert config.provider == "alpaca"

    def test_default_paper_is_true(self) -> None:
        """Test default paper trading is enabled."""
        config = BrokerProviderConfig()
        assert config.paper is True

    def test_with_alpaca_config(self) -> None:
        """Test creation with alpaca sub-config."""
        alpaca = AlpacaConfig(paper=False)
        config = BrokerProviderConfig(provider="alpaca", alpaca=alpaca, paper=False)
        assert config.provider == "alpaca"
        assert config.alpaca is not None
        assert config.alpaca.paper is False
        assert config.paper is False

    def test_with_webull_config(self) -> None:
        """Test creation with webull sub-config."""
        webull = WebullConfig(region="hk")
        config = BrokerProviderConfig(provider="webull", webull=webull)
        assert config.provider == "webull"
        assert config.webull is not None
        assert config.webull.region == "hk"

    def test_no_sub_configs_by_default(self) -> None:
        """Test that alpaca and webull sub-configs are None by default."""
        config = BrokerProviderConfig()
        assert config.alpaca is None
        assert config.webull is None


class TestDataProviderConfig:
    """Tests for DataProviderConfig."""

    def test_default_provider_is_none(self) -> None:
        """Test default data provider is None."""
        config = DataProviderConfig()
        assert config.provider is None

    def test_custom_provider(self) -> None:
        """Test setting a custom data provider."""
        config = DataProviderConfig(provider="alpaca")
        assert config.provider == "alpaca"


class TestNewsProviderConfig:
    """Tests for NewsProviderConfig."""

    def test_default_provider_is_none(self) -> None:
        """Test default news provider is None."""
        config = NewsProviderConfig()
        assert config.provider is None

    def test_custom_provider(self) -> None:
        """Test setting a custom news provider."""
        config = NewsProviderConfig(provider="alpaca")
        assert config.provider == "alpaca"


class TestAppConfigBrokerBackcompat:
    """Tests for AppConfig backward compatibility with broker field."""

    def test_appconfig_without_broker_works(self) -> None:
        """Test AppConfig works without broker field (backward compat)."""
        config = AppConfig()
        assert config.broker is None
        # Existing alpaca field still works
        assert config.alpaca is not None
        assert config.alpaca.api_key_env == "ALPACA_API_KEY"

    def test_appconfig_with_broker_field(self) -> None:
        """Test AppConfig works with broker field set."""
        broker = BrokerProviderConfig(provider="webull", paper=False)
        config = AppConfig(broker=broker)
        assert config.broker is not None
        assert config.broker.provider == "webull"
        assert config.broker.paper is False
        # Existing alpaca field still present
        assert config.alpaca is not None
