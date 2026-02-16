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


class WebullConfig(BaseModel):
    """Webull API configuration.

    Attributes:
        app_key_env: Environment variable name for Webull app key
        app_secret_env: Environment variable name for Webull app secret
        account_id_env: Environment variable name for Webull account ID
        region: Webull region (us, hk, jp)
    """

    app_key_env: str = Field(default="WEBULL_APP_KEY", description="Env var for Webull app key")
    app_secret_env: str = Field(default="WEBULL_APP_SECRET", description="Env var for Webull app secret")
    account_id_env: str = Field(default="WEBULL_ACCOUNT_ID", description="Env var for Webull account ID")
    region: Literal["us", "hk", "jp"] = Field(default="us", description="Webull region")

    def get_app_key(self) -> Optional[str]:
        """Get Webull app key from environment."""
        return os.environ.get(self.app_key_env)

    def get_app_secret(self) -> Optional[str]:
        """Get Webull app secret from environment."""
        return os.environ.get(self.app_secret_env)

    def get_account_id(self) -> Optional[str]:
        """Get Webull account ID from environment."""
        return os.environ.get(self.account_id_env)


class BrokerProviderConfig(BaseModel):
    """Broker provider selection and configuration.

    Attributes:
        provider: Broker provider name (alpaca or webull)
        paper: Whether to use paper trading (Alpaca only; Webull is live-only)
        alpaca: Alpaca-specific configuration
        webull: Webull-specific configuration
    """

    provider: Literal["alpaca", "webull"] = Field(default="alpaca", description="Broker provider name")
    paper: bool = Field(default=True, description="Use paper trading (Alpaca only)")
    alpaca: Optional[AlpacaConfig] = Field(default=None, description="Alpaca-specific config")
    webull: Optional[WebullConfig] = Field(default=None, description="Webull-specific config")


class DataProviderConfig(BaseModel):
    """Market data provider configuration.

    Attributes:
        provider: Data provider name (defaults to broker provider)
    """

    provider: Optional[str] = Field(default=None, description="Data provider (defaults to broker provider)")


class NewsProviderConfig(BaseModel):
    """News provider configuration.

    Attributes:
        provider: News provider name (e.g. 'alpaca')
    """

    provider: Optional[str] = Field(default=None, description="News provider (e.g. 'alpaca')")


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
    broker: Optional[BrokerProviderConfig] = Field(default=None, description="Broker provider config")
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
    def alpaca_api_key(self) -> str:
        """Get Alpaca API key from environment."""
        key = self.alpaca.get_api_key()
        if not key:
            raise ValueError("ALPACA_API_KEY not set in environment")
        return key

    @property
    def alpaca_api_secret(self) -> str:
        """Get Alpaca API secret from environment."""
        secret = self.alpaca.get_api_secret()
        if not secret:
            raise ValueError("ALPACA_API_SECRET not set in environment")
        return secret

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
        default=Decimal("1000"),
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


class BuyAndHoldParams(BaseModel):
    """Parameters for Buy and Hold strategy.

    Buy once at the start, hold forever. Classic passive investing.
    """

    symbols: list[str] = Field(default=["SPY"], description="Symbols to buy")
    # No other params - just buy all cash on day 1

    model_config = ConfigDict(frozen=True)


class DipBuyDCAParams(BaseModel):
    """Parameters for Dip Buy DCA strategy.

    Hybrid DCA + Dip buying: Deploy base amount at month start,
    then buy dips with remaining budget throughout the month.
    Proportional buying: deeper dips trigger larger purchases.
    """

    symbols: list[str] = Field(default=["SPY"], description="Symbols to buy")
    monthly_budget: Decimal = Field(
        default=Decimal("1000"),
        description="Total budget per month",
        ge=Decimal("1"),
    )
    base_buy_pct: float = Field(
        default=0.50,
        description="Fraction of monthly budget to buy on first trading day (DCA portion)",
        ge=0.0,
        le=1.0,
    )
    # Proportional dip tiers: [threshold, buy_pct]
    # Buy more as the dip gets deeper
    dip_tier_1: float = Field(
        default=0.01,
        description="Tier 1: Small dip threshold (e.g., 1%)",
        ge=0.005,
        le=0.10,
    )
    dip_tier_1_pct: float = Field(
        default=0.20,
        description="Buy this fraction of remaining budget on Tier 1 dip",
        ge=0.05,
        le=1.0,
    )
    dip_tier_2: float = Field(
        default=0.02,
        description="Tier 2: Medium dip threshold (e.g., 2%)",
        ge=0.01,
        le=0.15,
    )
    dip_tier_2_pct: float = Field(
        default=0.40,
        description="Buy this fraction of remaining budget on Tier 2 dip",
        ge=0.1,
        le=1.0,
    )
    dip_tier_3: float = Field(
        default=0.03,
        description="Tier 3: Large dip threshold (e.g., 3%+)",
        ge=0.02,
        le=0.20,
    )
    dip_tier_3_pct: float = Field(
        default=0.75,
        description="Buy this fraction of remaining budget on Tier 3 dip",
        ge=0.2,
        le=1.0,
    )
    max_dip_buys: int = Field(
        default=8,
        description="Maximum number of dip buys per month",
        ge=1,
        le=20,
    )
    lookback_days: int = Field(
        default=1,
        description="Days to look back for recent high",
        ge=1,
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
        default=True,
        description="Use hourly data for better dip detection",
    )
    lookback_hours: int = Field(
        default=24,
        description="Hours to look back for recent high (when using hourly data)",
        ge=6,
        le=168,
    )

    model_config = ConfigDict(frozen=True)


class RSIDCAParams(BaseModel):
    """Parameters for RSI-based DCA strategy.

    Hybrid DCA + RSI buying: Deploy base amount at month start,
    then buy based on RSI (Relative Strength Index) levels.
    Lower RSI = more oversold = buy more aggressively.
    """

    symbols: list[str] = Field(default=["SPY"], description="Symbols to buy")
    monthly_budget: Decimal = Field(
        default=Decimal("1000"),
        description="Total budget per month",
        ge=Decimal("1"),
    )
    base_buy_pct: float = Field(
        default=0.50,
        description="Fraction of monthly budget to buy on first trading day (DCA portion)",
        ge=0.0,
        le=1.0,
    )
    rsi_period: int = Field(
        default=14,
        description="Number of periods for RSI calculation",
        ge=5,
        le=30,
    )
    # RSI tiers: [threshold, buy_pct] - lower RSI = more oversold = buy more
    rsi_tier_1: int = Field(
        default=40,
        description="Tier 1: Moderately oversold RSI threshold",
        ge=30,
        le=50,
    )
    rsi_tier_1_pct: float = Field(
        default=0.20,
        description="Buy this fraction of remaining budget when RSI < Tier 1",
        ge=0.05,
        le=1.0,
    )
    rsi_tier_2: int = Field(
        default=30,
        description="Tier 2: Oversold RSI threshold",
        ge=20,
        le=40,
    )
    rsi_tier_2_pct: float = Field(
        default=0.40,
        description="Buy this fraction of remaining budget when RSI < Tier 2",
        ge=0.1,
        le=1.0,
    )
    rsi_tier_3: int = Field(
        default=25,
        description="Tier 3: Extremely oversold RSI threshold",
        ge=10,
        le=35,
    )
    rsi_tier_3_pct: float = Field(
        default=0.75,
        description="Buy this fraction of remaining budget when RSI < Tier 3",
        ge=0.2,
        le=1.0,
    )
    max_rsi_buys: int = Field(
        default=8,
        description="Maximum number of RSI-triggered buys per month",
        ge=1,
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

    model_config = ConfigDict(frozen=True)


class MACrossoverDCAParams(BaseModel):
    """Parameters for MA Crossover DCA strategy.

    Regular DCA + extra buys when short MA crosses below long MA (death cross).
    When death cross occurs, deploy extra funds from surplus to buy the dip.
    """

    symbols: list[str] = Field(default=["SPY"], description="Symbols to buy")
    monthly_budget: Decimal = Field(
        default=Decimal("1000"),
        description="Regular monthly DCA amount",
        ge=Decimal("1"),
    )
    surplus_budget: Decimal = Field(
        default=Decimal("12000"),
        description="Total surplus fund available for death cross buys",
        ge=Decimal("0"),
    )
    surplus_buy_amount: Decimal = Field(
        default=Decimal("1000"),
        description="Amount to deploy from surplus on each death cross",
        ge=Decimal("1"),
    )
    short_ma_period: int = Field(
        default=7,
        description="Short moving average period (e.g., 7-day)",
        ge=3,
        le=20,
    )
    long_ma_period: int = Field(
        default=30,
        description="Long moving average period (e.g., 30-day)",
        ge=10,
        le=200,
    )
    min_buy_amount: Decimal = Field(
        default=Decimal("25"),
        description="Minimum order size in dollars",
        ge=Decimal("1"),
    )
    cooldown_days: int = Field(
        default=5,
        description="Days to wait after a death cross buy before another",
        ge=1,
        le=30,
    )

    model_config = ConfigDict(frozen=True)


class VolatilitySwingParams(BaseModel):
    """Parameters for Volatility Swing strategy.

    Buy dips, sell bounces. Designed for volatile assets (BTC, TSLA, NVDA).
    Capital is recycled - no monthly budget reset.

    Logic:
        - Buy when price drops by dip_threshold from recent high
        - Sell when price rises by profit_target from purchase price
        - Optional stop loss to limit downside
    """

    symbols: list[str] = Field(default=["TSLA"], description="Volatile symbols to trade")
    position_size: Decimal = Field(
        default=Decimal("1000"),
        description="Dollar amount per position",
        ge=Decimal("100"),
    )
    max_positions: int = Field(
        default=5,
        description="Maximum concurrent positions per symbol",
        ge=1,
        le=20,
    )
    dip_threshold: float = Field(
        default=0.01,
        description="Buy when price drops this % from recent high (e.g., 1%)",
        ge=0.005,
        le=0.20,
    )
    profit_target: float = Field(
        default=0.02,
        description="Sell when price rises this % from purchase (e.g., 2%)",
        ge=0.005,
        le=0.50,
    )
    stop_loss: float = Field(
        default=1.0,
        description="Sell if price drops this % from purchase (1.0 = disabled)",
        ge=0.01,
        le=1.0,
    )
    require_reversal_after_stop: bool = Field(
        default=False,
        description="After stop loss, wait for reversal before buying again",
    )
    reversal_threshold: float = Field(
        default=0.02,
        description="Price must rise this % from recent low to signal reversal",
        ge=0.005,
        le=0.10,
    )
    lookback_days: int = Field(
        default=5,
        description="Days to look back for recent high (for daily bars)",
        ge=1,
        le=30,
    )
    min_hold_days: int = Field(
        default=0,
        description="Minimum days to hold before selling",
        ge=0,
        le=30,
    )
    use_hourly_data: bool = Field(
        default=True,
        description="Use hourly data for better intraday swing detection",
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
