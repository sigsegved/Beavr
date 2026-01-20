"""Configuration models for Beavr."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AlpacaConfig(BaseModel):
    """Alpaca API configuration.

    Attributes:
        api_key_env: Environment variable name for API key
        api_secret_env: Environment variable name for API secret
        paper: Whether to use paper trading
    """

    api_key_env: str = Field(default="ALPACA_API_KEY", description="Env var for API key")
    api_secret_env: str = Field(default="ALPACA_API_SECRET", description="Env var for API secret")
    paper: bool = Field(default=True, description="Use paper trading")

    def get_api_key(self) -> Optional[str]:
        """Get API key from environment."""
        return os.environ.get(self.api_key_env)

    def get_api_secret(self) -> Optional[str]:
        """Get API secret from environment."""
        return os.environ.get(self.api_secret_env)


class StrategyConfig(BaseModel):
    """Configuration for a single strategy instance.

    Attributes:
        template: Strategy class name (e.g., "simple_dca", "dip_buy_dca")
        name: Optional display name for this instance
        params: Strategy-specific parameters
        enabled: Whether the strategy is enabled
    """

    template: str = Field(..., description="Strategy class name")
    name: Optional[str] = Field(default=None, description="Display name")
    params: dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    enabled: bool = Field(default=True, description="Whether strategy is enabled")

    model_config = ConfigDict(extra="allow")


class AppConfig(BaseSettings):
    """Main application configuration.

    Loads configuration from environment variables with BEAVR_ prefix.

    Attributes:
        alpaca: Alpaca API configuration
        data_dir: Directory for data storage
        db_path: Path to SQLite database (defaults to data_dir/beavr.db)
    """

    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".beavr",
        description="Data directory"
    )
    db_path: Optional[Path] = Field(default=None, description="Database path")

    model_config = SettingsConfigDict(
        env_prefix="BEAVR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @property
    def database_path(self) -> Path:
        """Get the database path, defaulting to data_dir/beavr.db."""
        return self.db_path or (self.data_dir / "beavr.db")

    def ensure_data_dir(self) -> Path:
        """Ensure data directory exists and return its path."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


# Strategy-specific parameter models

class SimpleDCAParams(BaseModel):
    """Parameters for Simple DCA strategy.

    Buy a fixed dollar amount at regular intervals.
    """

    symbols: list[str] = Field(default=["SPY"], description="Symbols to buy")
    amount: Decimal = Field(
        default=Decimal("500"),
        description="Dollar amount per buy",
        ge=Decimal("1"),
    )
    frequency: Literal["weekly", "biweekly", "monthly"] = Field(
        default="monthly",
        description="Buy frequency"
    )
    day_of_month: int = Field(
        default=1,
        description="Day of month to buy (for monthly)",
        ge=1,
        le=28,
    )
    day_of_week: int = Field(
        default=0,
        description="Day of week to buy (0=Monday, for weekly)",
        ge=0,
        le=6,
    )

    model_config = ConfigDict(frozen=True)


class DipBuyDCAParams(BaseModel):
    """Parameters for Dip Buy DCA strategy.

    Buy on dips throughout the period, with fallback at period end.
    """

    symbols: list[str] = Field(default=["SPY"], description="Symbols to buy")
    monthly_budget: Decimal = Field(
        default=Decimal("500"),
        description="Total budget per month",
        ge=Decimal("1"),
    )
    dip_threshold: float = Field(
        default=0.02,
        description="Buy when price drops this % from recent high",
        ge=0.01,
        le=0.10,
    )
    dip_buy_pct: float = Field(
        default=0.50,
        description="Fraction of remaining budget to deploy on dip",
        ge=0.1,
        le=1.0,
    )
    lookback_days: int = Field(
        default=5,
        description="Days to look back for recent high",
        ge=2,
        le=20,
    )
    fallback_days: int = Field(
        default=3,
        description="Days before month-end to trigger fallback buy",
        ge=1,
        le=5,
    )
    min_buy_amount: Decimal = Field(
        default=Decimal("25"),
        description="Minimum order size in dollars",
        ge=Decimal("1"),
    )
    use_hourly_data: bool = Field(
        default=False,
        description="Use hourly data for better dip detection",
    )
    lookback_hours: int = Field(
        default=24,
        description="Hours to look back for recent high (when using hourly data)",
        ge=6,
        le=168,
    )

    model_config = ConfigDict(frozen=True)


class BacktestConfig(BaseModel):
    """Configuration for a backtest run.

    Attributes:
        initial_cash: Starting cash balance
        start_date: Backtest start date (YYYY-MM-DD format)
        end_date: Backtest end date (YYYY-MM-DD format)
        strategy: Strategy configuration
    """

    initial_cash: Decimal = Field(
        default=Decimal("10000"),
        description="Starting cash balance",
        ge=Decimal("100"),
    )
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    strategy: StrategyConfig = Field(..., description="Strategy configuration")

    model_config = ConfigDict(frozen=True)
