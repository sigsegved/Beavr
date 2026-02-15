"""Broker protocol definitions for the Beavr trading platform.

Defines structural typing protocols (PEP 544) for broker, market data,
screener, and news providers. Any class implementing the required methods
and properties satisfies the protocol without explicit inheritance.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional, Protocol, runtime_checkable

import pandas as pd

from beavr.broker.models import (
    AccountInfo,
    BrokerPosition,
    MarketClock,
    OrderRequest,
    OrderResult,
)

Timeframe = Literal["1min", "5min", "15min", "30min", "1hour", "1day", "1week"]
"""Supported bar timeframe intervals for market data queries."""


@runtime_checkable
class BrokerProvider(Protocol):
    """Protocol for broker integrations (Alpaca, Webull, etc.).

    A broker provider handles account management, position tracking,
    order execution, and market-hours queries. Implementations must
    expose all listed methods and properties with matching signatures.

    All monetary values use ``Decimal`` — never ``float``.
    """

    @property
    def broker_name(self) -> str:
        """Human-readable broker identifier (e.g. ``'alpaca'``, ``'webull'``)."""
        ...

    @property
    def supports_fractional(self) -> bool:
        """Whether the broker supports fractional-share orders."""
        ...

    def get_account(self) -> AccountInfo:
        """Return current account information (balances, equity, etc.)."""
        ...

    def get_positions(self) -> list[BrokerPosition]:
        """Return all open positions held in the account."""
        ...

    def submit_order(self, order: OrderRequest) -> OrderResult:
        """Submit a new order to the broker.

        Args:
            order: The order specification to submit.

        Returns:
            The resulting order acknowledgement from the broker.
        """
        ...

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an existing order by its broker-assigned ID.

        Args:
            order_id: Broker-assigned order identifier.

        Returns:
            Updated order result reflecting cancellation status.
        """
        ...

    def get_order(self, order_id: str) -> OrderResult:
        """Retrieve the current state of an order.

        Args:
            order_id: Broker-assigned order identifier.

        Returns:
            Current order status and fill details.
        """
        ...

    def list_orders(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[OrderResult]:
        """List orders, optionally filtered by status.

        Args:
            status: Filter by order status (e.g. ``'open'``, ``'closed'``).
                    ``None`` returns orders of any status.
            limit: Maximum number of orders to return.

        Returns:
            List of order results matching the criteria.
        """
        ...

    def is_market_open(self) -> bool:
        """Return ``True`` if the market is currently open for trading."""
        ...

    def get_clock(self) -> MarketClock:
        """Return the current market clock with open/close times."""
        ...


@runtime_checkable
class MarketDataProvider(Protocol):
    """Protocol for market-data feeds.

    Provides historical OHLCV bars and real-time snapshots.
    Implementations may source data from Alpaca, Webull, or other vendors.
    """

    @property
    def provider_name(self) -> str:
        """Human-readable data-provider identifier (e.g. ``'alpaca'``)."""
        ...

    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1day",
    ) -> pd.DataFrame:
        """Fetch historical OHLCV bars for a single symbol.

        Args:
            symbol: Ticker symbol (e.g. ``'SPY'``).
            start: Start date (inclusive).
            end: End date (inclusive).
            timeframe: Bar interval — one of
                ``"1min"``, ``"5min"``, ``"15min"``, ``"30min"``,
                ``"1hour"``, ``"1day"``, ``"1week"``.

        Returns:
            DataFrame with OHLCV columns indexed by timestamp.
        """
        ...

    def get_bars_multi(
        self,
        symbols: list[str],
        start: date,
        end: date,
        timeframe: str = "1day",
    ) -> dict[str, pd.DataFrame]:
        """Fetch historical OHLCV bars for multiple symbols.

        Args:
            symbols: List of ticker symbols.
            start: Start date (inclusive).
            end: End date (inclusive).
            timeframe: Bar interval (see ``get_bars``).

        Returns:
            Mapping of symbol to its OHLCV DataFrame.
        """
        ...

    def get_snapshot(self, symbol: str) -> dict:
        """Return a real-time snapshot for a symbol.

        The returned dict typically includes latest trade, quote, and
        minute/daily bar data. Structure is provider-dependent.

        Args:
            symbol: Ticker symbol.

        Returns:
            Dictionary containing the latest market snapshot.
        """
        ...


@runtime_checkable
class ScreenerProvider(Protocol):
    """Protocol for market screener / scanner services.

    Provides ranked lists of stocks based on momentum, volume,
    or other screening criteria.
    """

    def get_market_movers(self, top: int = 10) -> list[dict]:
        """Return the top gaining and losing symbols.

        Args:
            top: Number of movers to return.

        Returns:
            List of dicts with symbol, price, and change information.
        """
        ...

    def get_most_actives(self, top: int = 20) -> list[dict]:
        """Return the most actively traded symbols by volume.

        Args:
            top: Number of active symbols to return.

        Returns:
            List of dicts with symbol, price, and volume information.
        """
        ...


@runtime_checkable
class NewsProvider(Protocol):
    """Protocol for financial news feeds.

    Provides recent news articles filtered by symbol(s).
    """

    def get_news(self, symbols: list[str], limit: int = 10) -> list[dict]:
        """Fetch recent news articles for the given symbols.

        Args:
            symbols: Ticker symbols to filter news for.
            limit: Maximum number of articles to return.

        Returns:
            List of dicts containing headline, summary, source, and
            published timestamp for each article.
        """
        ...
