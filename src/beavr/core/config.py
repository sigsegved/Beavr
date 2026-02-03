"""Configuration loading utilities."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# tomllib is available in Python 3.11+, use tomli for earlier versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from beavr.models.config import AppConfig, StrategyConfig


def load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file and return its contents as a dictionary.

    Args:
        path: Path to the TOML file

    Returns:
        Dictionary with TOML contents

    Raises:
        FileNotFoundError: If file doesn't exist
        tomllib.TOMLDecodeError: If file is invalid TOML
    """
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_strategy_config(path: Path) -> StrategyConfig:
    """Load a strategy configuration from a TOML file.

    Args:
        path: Path to the strategy TOML file

    Returns:
        StrategyConfig object

    Example TOML format:
        template = "simple_dca"
        name = "My DCA Strategy"

        [params]
        symbols = ["SPY", "QQQ"]
        amount = 500
    """
    data = load_toml(path)
    return StrategyConfig(**data)


def load_app_config() -> AppConfig:
    """Load application configuration from environment variables.

    Returns:
        AppConfig object with settings from environment
    """
    return AppConfig()


# Singleton settings instance
_settings: AppConfig | None = None


def get_settings() -> AppConfig:
    """Get or create the settings singleton.
    
    This ensures we only load settings once and reuse them.
    """
    global _settings
    if _settings is None:
        from dotenv import load_dotenv
        load_dotenv()  # Ensure .env is loaded
        _settings = AppConfig()
    return _settings


def get_default_strategies_dir() -> Path:
    """Get the default strategies directory.

    Returns:
        Path to ~/.beavr/strategies/
    """
    config = AppConfig()
    strategies_dir = config.data_dir / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    return strategies_dir
