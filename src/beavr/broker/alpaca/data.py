"""Alpaca market-data adapter implementing MarketDataProvider protocol."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import pandas as pd
from alpaca.data import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import (
    CryptoBarsRequest,
    CryptoSnapshotRequest,
    StockBarsRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from beavr.broker.models import BrokerError

if TYPE_CHECKING:
    from beavr.db.cache import BarCache

logger = logging.getLogger(__name__)

TIMEFRAME_MAP: dict[str, TimeFrame] = {
    "1min": TimeFrame.Minute,
    "5min": TimeFrame(5, TimeFrameUnit.Minute),
    "15min": TimeFrame(15, TimeFrameUnit.Minute),
    "30min": TimeFrame(30, TimeFrameUnit.Minute),
    "1hour": TimeFrame.Hour,
    "1day": TimeFrame.Day,
    "1week": TimeFrame.Week,
}
"""Mapping from protocol timeframe strings to Alpaca ``TimeFrame`` objects."""


class AlpacaMarketData:
    """MarketDataProvider implementation backed by Alpaca.

    Wraps :class:`StockHistoricalDataClient` and
    :class:`CryptoHistoricalDataClient` to provide historical OHLCV bars and
    real-time snapshots through the broker-agnostic ``MarketDataProvider``
    protocol.

    Crypto symbols are auto-detected by the presence of ``/`` in the ticker
    (e.g. ``"BTC/USD"``).

    All monetary values in returned DataFrames are ``Decimal`` for financial
    precision.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        cache: Optional[BarCache] = None,
    ) -> None:
        """Initialise Alpaca data clients.

        Args:
            api_key: Alpaca API key.
            api_secret: Alpaca API secret.
            cache: Optional bar-cache for avoiding redundant API calls.
        """
        self._stock_client = StockHistoricalDataClient(api_key, api_secret)
        self._crypto_client = CryptoHistoricalDataClient(api_key, api_secret)
        self._cache = cache

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        """Human-readable data-provider identifier."""
        return "alpaca"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1day",
    ) -> pd.DataFrame:
        """Fetch historical OHLCV bars for *symbol*.

        Args:
            symbol: Ticker symbol (e.g. ``"SPY"`` or ``"BTC/USD"``).
            start: Start date (inclusive).
            end: End date (inclusive).
            timeframe: Bar interval — one of the keys in ``TIMEFRAME_MAP``.

        Returns:
            DataFrame with a ``DatetimeIndex`` and Decimal-valued OHLCV
            columns (``open``, ``high``, ``low``, ``close``, ``volume``).

        Raises:
            BrokerError: If the Alpaca API call fails.
        """
        # Cache lookup
        if self._cache is not None:
            cached = self._cache.get_bars(symbol, start, end, timeframe)
            if cached is not None:
                logger.debug("Cache hit for %s [%s to %s]", symbol, start, end)
                return cached

        logger.debug("Fetching %s bars from Alpaca [%s to %s]", symbol, start, end)

        tf = self._resolve_timeframe(timeframe)
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end, time(23, 59, 59))

        try:
            if self._is_crypto(symbol):
                request = CryptoBarsRequest(
                    symbol_or_symbols=symbol,
                    start=start_dt,
                    end=end_dt,
                    timeframe=tf,
                )
                response = self._crypto_client.get_crypto_bars(request)
            else:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    start=start_dt,
                    end=end_dt,
                    timeframe=tf,
                    feed="iex",
                )
                response = self._stock_client.get_stock_bars(request)
        except Exception as exc:
            raise BrokerError(
                error_code="market_data_error",
                message=f"Failed to fetch bars for {symbol}: {exc}",
                broker_name=self.provider_name,
            ) from exc

        df = self._bars_to_dataframe(response, symbol)

        # Persist to cache
        if self._cache is not None and not df.empty:
            self._cache.save_bars(symbol, df, timeframe)
            logger.debug("Cached %d bars for %s", len(df), symbol)

        return df

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
        return {
            symbol: self.get_bars(symbol, start, end, timeframe)
            for symbol in symbols
        }

    def get_snapshot(self, symbol: str) -> dict:
        """Return a real-time market snapshot for *symbol*.

        Args:
            symbol: Ticker symbol.

        Returns:
            Dictionary with latest trade, quote, and bar data. Key structure
            is provider-dependent.

        Raises:
            BrokerError: If the Alpaca API call fails.
        """
        try:
            if self._is_crypto(symbol):
                request = CryptoSnapshotRequest(symbol_or_symbols=symbol)
                snap = self._crypto_client.get_crypto_snapshot(request)
            else:
                request = StockSnapshotRequest(symbol_or_symbols=symbol)
                snap = self._stock_client.get_stock_snapshot(request)
        except Exception as exc:
            raise BrokerError(
                error_code="snapshot_error",
                message=f"Failed to get snapshot for {symbol}: {exc}",
                broker_name=self.provider_name,
            ) from exc

        return self._snapshot_to_dict(snap, symbol)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        """Return ``True`` when *symbol* looks like a crypto pair."""
        return "/" in symbol

    @staticmethod
    def _resolve_timeframe(timeframe: str) -> TimeFrame:
        """Map a protocol timeframe string to an Alpaca ``TimeFrame``."""
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise BrokerError(
                error_code="invalid_timeframe",
                message=(
                    f"Unsupported timeframe '{timeframe}'. "
                    f"Valid values: {', '.join(sorted(TIMEFRAME_MAP))}"
                ),
                broker_name="alpaca",
            )
        return tf

    @staticmethod
    def _bars_to_dataframe(response: object, symbol: str) -> pd.DataFrame:
        """Convert an Alpaca bars response into a ``DatetimeIndex`` DataFrame.

        Columns: ``open``, ``high``, ``low``, ``close``, ``volume`` — all
        monetary columns are ``Decimal``.
        """
        empty = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
        )
        empty.index.name = "timestamp"

        response_data = getattr(response, "data", {})
        bars_list = response_data.get(symbol)
        if not bars_list:
            return empty

        rows: list[dict] = []
        for bar in bars_list:
            rows.append(
                {
                    "timestamp": bar.timestamp,
                    "open": Decimal(str(bar.open)),
                    "high": Decimal(str(bar.high)),
                    "low": Decimal(str(bar.low)),
                    "close": Decimal(str(bar.close)),
                    "volume": Decimal(str(bar.volume)),
                }
            )

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
        return df

    @staticmethod
    def _snapshot_to_dict(snapshot: object, symbol: str) -> dict:
        """Normalise an Alpaca snapshot into a plain ``dict``."""
        snap_data = getattr(snapshot, symbol, None)
        if snap_data is None:
            # Some Alpaca SDK versions index by symbol directly
            snap_data = snapshot  # type: ignore[assignment]

        result: dict = {}

        latest_trade = getattr(snap_data, "latest_trade", None)
        if latest_trade is not None:
            result["latest_trade"] = {
                "price": Decimal(str(latest_trade.price)),
                "size": Decimal(str(latest_trade.size)),
                "timestamp": str(getattr(latest_trade, "timestamp", "")),
            }

        latest_quote = getattr(snap_data, "latest_quote", None)
        if latest_quote is not None:
            result["latest_quote"] = {
                "bid_price": Decimal(str(latest_quote.bid_price)),
                "ask_price": Decimal(str(latest_quote.ask_price)),
                "bid_size": Decimal(str(latest_quote.bid_size)),
                "ask_size": Decimal(str(latest_quote.ask_size)),
            }

        daily_bar = getattr(snap_data, "daily_bar", None)
        if daily_bar is not None:
            result["daily_bar"] = {
                "open": Decimal(str(daily_bar.open)),
                "high": Decimal(str(daily_bar.high)),
                "low": Decimal(str(daily_bar.low)),
                "close": Decimal(str(daily_bar.close)),
                "volume": Decimal(str(daily_bar.volume)),
            }

        minute_bar = getattr(snap_data, "minute_bar", None)
        if minute_bar is not None:
            result["minute_bar"] = {
                "open": Decimal(str(minute_bar.open)),
                "high": Decimal(str(minute_bar.high)),
                "low": Decimal(str(minute_bar.low)),
                "close": Decimal(str(minute_bar.close)),
                "volume": Decimal(str(minute_bar.volume)),
            }

        return result
