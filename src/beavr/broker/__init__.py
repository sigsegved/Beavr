"""Broker abstraction layer.

Provides protocol-based abstractions for trading operations and market data,
enabling broker-agnostic strategies, agents, and execution.
"""

from __future__ import annotations

from beavr.broker.factory import BrokerFactory
from beavr.broker.models import (
    AccountInfo,
    BrokerError,
    BrokerPosition,
    MarketClock,
    OrderRequest,
    OrderResult,
)
from beavr.broker.protocols import (
    BrokerProvider,
    MarketDataProvider,
    NewsProvider,
    ScreenerProvider,
    Timeframe,
)

__all__ = [
    "AccountInfo",
    "BrokerError",
    "BrokerFactory",
    "BrokerPosition",
    "BrokerProvider",
    "MarketClock",
    "MarketDataProvider",
    "NewsProvider",
    "OrderRequest",
    "OrderResult",
    "ScreenerProvider",
    "Timeframe",
]
