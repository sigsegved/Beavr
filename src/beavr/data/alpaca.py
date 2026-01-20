"""Alpaca market data fetcher."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Optional

import pandas as pd
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

if TYPE_CHECKING:
    from beavr.db.cache import BarCache

logger = logging.getLogger(__name__)


class AlpacaDataFetcherError(Exception):
    """Base exception for Alpaca data fetcher errors."""

    pass


class AlpacaAPIError(AlpacaDataFetcherError):
    """Error from Alpaca API."""

    pass


class AlpacaDataFetcher:
    """
    Fetches historical bar data from Alpaca API.

    Supports caching to avoid redundant API calls. When a cache is provided,
    data is first checked in cache before fetching from Alpaca.

    Attributes:
        cache: Optional BarCache for caching fetched data
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        cache: Optional[BarCache] = None,
    ):
        """
        Initialize the Alpaca data fetcher.

        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            cache: Optional BarCache instance for caching
        """
        self.client = StockHistoricalDataClient(api_key, api_secret)
        self.cache = cache

    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> pd.DataFrame:
        """
        Fetch bars for a symbol, using cache if available.

        Args:
            symbol: Stock symbol (e.g., "SPY")
            start: Start date (inclusive)
            end: End date (inclusive)
            timeframe: Bar timeframe ("1Day" or "1Hour")

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Prices are Decimal for precision.

        Raises:
            AlpacaAPIError: If Alpaca API call fails
        """
        # Check cache first
        if self.cache:
            cached = self.cache.get_bars(symbol, start, end, timeframe)
            if cached is not None:
                logger.debug(f"Cache hit for {symbol} [{start} to {end}]")
                return cached

        logger.debug(f"Cache miss for {symbol}, fetching from Alpaca")

        # Fetch from Alpaca
        bars_df = self._fetch_from_alpaca(symbol, start, end, timeframe)

        # Cache for next time
        if self.cache and not bars_df.empty:
            self.cache.save_bars(symbol, bars_df, timeframe)
            logger.debug(f"Cached {len(bars_df)} bars for {symbol}")

        return bars_df

    def get_multi_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch bars for multiple symbols.

        Args:
            symbols: List of stock symbols
            start: Start date (inclusive)
            end: End date (inclusive)
            timeframe: Bar timeframe ("1Day" or "1Hour")

        Returns:
            Dict mapping symbol to DataFrame of bars
        """
        return {
            symbol: self.get_bars(symbol, start, end, timeframe) for symbol in symbols
        }

    def _fetch_from_alpaca(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str,
    ) -> pd.DataFrame:
        """
        Direct Alpaca API call to fetch bars.

        Args:
            symbol: Stock symbol
            start: Start date
            end: End date
            timeframe: Bar timeframe

        Returns:
            DataFrame with bar data

        Raises:
            AlpacaAPIError: If API call fails
        """
        # Map timeframe string to Alpaca TimeFrame
        tf = self._get_timeframe(timeframe)

        # Build request
        # Use start of day for start, end of day for end
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end, time(23, 59, 59))

        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            start=start_dt,
            end=end_dt,
            timeframe=tf,
        )

        try:
            bars_response = self.client.get_stock_bars(request)
        except Exception as e:
            raise AlpacaAPIError(f"Failed to fetch bars for {symbol}: {e}") from e

        # Convert to DataFrame
        return self._bars_to_dataframe(bars_response, symbol)

    def _get_timeframe(self, timeframe: str) -> TimeFrame:
        """Convert timeframe string to Alpaca TimeFrame."""
        mapping: Dict[str, TimeFrame] = {
            "1Day": TimeFrame.Day,
            "1Hour": TimeFrame.Hour,
            "1Min": TimeFrame.Minute,
        }
        if timeframe not in mapping:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return mapping[timeframe]

    def _bars_to_dataframe(self, bars_response: object, symbol: str) -> pd.DataFrame:
        """
        Convert Alpaca bars response to DataFrame.

        Args:
            bars_response: Response from Alpaca API
            symbol: The symbol we requested

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        # Get bars for this symbol
        # Use getattr to handle the response object
        response_data = getattr(bars_response, "data", {})
        if symbol not in response_data:
            logger.warning(f"No bars returned for {symbol}")
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

        bars_list = response_data[symbol]

        if not bars_list:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

        # Build DataFrame
        data: Dict[str, list] = {
            "timestamp": [],
            "open": [],
            "high": [],
            "low": [],
            "close": [],
            "volume": [],
        }

        for bar in bars_list:
            data["timestamp"].append(bar.timestamp)
            data["open"].append(Decimal(str(bar.open)))
            data["high"].append(Decimal(str(bar.high)))
            data["low"].append(Decimal(str(bar.low)))
            data["close"].append(Decimal(str(bar.close)))
            data["volume"].append(int(bar.volume))

        df = pd.DataFrame(data)

        # Ensure timestamp is datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        return df
