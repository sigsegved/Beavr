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
    DipBuyDCAParams,
    SimpleDCAParams,
    StrategyConfig,
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
