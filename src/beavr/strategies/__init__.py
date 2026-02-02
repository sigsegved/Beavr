"""Strategies package for Beavr.

This module provides:
- BaseStrategy: Abstract base class for all strategies
- StrategyContext: Context provided to strategies during evaluation
- Strategy registry for discovering and loading strategies
- Built-in strategies: SimpleDCA, DipBuyDCA, BuyAndHold
"""

from beavr.strategies.base import BaseStrategy
from beavr.strategies.buy_and_hold import BuyAndHoldStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.dip_buy_dca import DipBuyDCAStrategy
from beavr.strategies.registry import (
    clear_registry,
    create_strategy,
    get_strategy,
    get_strategy_info,
    list_strategies,
    register_strategy,
)
from beavr.strategies.simple_dca import SimpleDCAStrategy

__all__ = [
    "BaseStrategy",
    "StrategyContext",
    "SimpleDCAStrategy",
    "BuyAndHoldStrategy",
    "DipBuyDCAStrategy",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "get_strategy_info",
    "create_strategy",
    "clear_registry",
]

