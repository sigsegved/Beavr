"""Webull market-data adapter implementing MarketDataProvider protocol."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

from beavr.broker.models import BrokerError
from beavr.broker.webull.instrument_cache import InstrumentCache

logger = logging.getLogger(__name__)

# Maximum number of bars the Webull API returns per request.
MAX_BARS_PER_REQUEST: int = 1200

TIMEFRAME_MAP: Dict[str, str] = {
    "1min": "M1",
    "5min": "M5",
    "15min": "M15",
    "30min": "M30",
    "1hour": "H1",
    "1day": "D1",
    "1week": "W1",
}
"""Mapping from protocol timeframe strings to Webull timespan codes."""


class WebullMarketData:
    """MarketDataProvider implementation backed by the Webull SDK.

    Wraps :class:`webullsdkmdata.quotes.market_data.MarketData` and
    :class:`webullsdkmdata.quotes.instrument.Instrument` to provide
    historical OHLCV bars and real-time snapshots through the
    broker-agnostic ``MarketDataProvider`` protocol.

    Crypto symbols are auto-detected by the presence of ``/`` in the
    ticker (e.g. ``"BTC/USD"``).

    All monetary values in returned DataFrames are ``Decimal`` for
    financial precision.
    """

    def __init__(
        self,
        api_client: Any,
        instrument_cache: Optional[InstrumentCache] = None,
        db_path: str = ":memory:",
    ) -> None:
        """Initialise the Webull market-data adapter.

        Args:
            api_client: Authenticated Webull ``ApiClient`` instance.
            instrument_cache: Optional pre-built instrument cache. If
                ``None``, a new one is created with the given *db_path*.
            db_path: SQLite path used when creating a default cache.
        """
        self._api_client = api_client
        self._instrument_cache = instrument_cache or InstrumentCache(
            api_client, db_path=db_path
        )

        # Lazy SDK module reference
        self._market_data_api: Any = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_market_data_api(self) -> Any:
        """Lazily initialise the MarketData SDK object."""
        if self._market_data_api is None:
            from webullsdkmdata.quotes.market_data import MarketData

            self._market_data_api = MarketData(self._api_client)
        return self._market_data_api

    @staticmethod
    def _detect_category(symbol: str) -> str:
        """Auto-detect Webull category from symbol pattern."""
        if "/" in symbol:
            return "CRYPTO"
        return "US_STOCK"

    @staticmethod
    def _resolve_timeframe(timeframe: str) -> str:
        """Convert a protocol timeframe string to a Webull timespan code.

        Raises:
            BrokerError: If the timeframe is not supported.
        """
        webull_ts = TIMEFRAME_MAP.get(timeframe)
        if webull_ts is None:
            raise BrokerError(
                error_code="invalid_timeframe",
                message=(
                    f"Unsupported timeframe '{timeframe}'. "
                    f"Valid values: {list(TIMEFRAME_MAP)}"
                ),
                broker_name="webull",
            )
        return webull_ts

    @staticmethod
    def _parse_bar(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a raw Webull bar dict to a canonical bar dict.

        Returns a dict with keys ``timestamp``, ``open``, ``high``,
        ``low``, ``close``, ``volume`` where monetary values are
        ``Decimal`` and *timestamp* is a timezone-aware ``datetime``.
        """
        ts_str = raw.get("time", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.now(tz=timezone.utc)

        return {
            "timestamp": ts,
            "open": Decimal(str(raw.get("open", "0"))),
            "high": Decimal(str(raw.get("high", "0"))),
            "low": Decimal(str(raw.get("low", "0"))),
            "close": Decimal(str(raw.get("close", "0"))),
            "volume": Decimal(str(raw.get("volume", "0"))),
        }

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        """Human-readable data-provider identifier."""
        return "webull"

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
            BrokerError: If the Webull API call fails.
        """
        webull_ts = self._resolve_timeframe(timeframe)
        category = self._detect_category(symbol)

        try:
            instrument_id = self._instrument_cache.resolve(
                symbol, category=category
            )
        except BrokerError:
            raise
        except Exception as exc:
            raise BrokerError(
                error_code="instrument_resolve_error",
                message=f"Failed to resolve symbol '{symbol}': {exc}",
                broker_name="webull",
            ) from exc

        start_dt = datetime.combine(start, time.min).replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.combine(end, time(23, 59, 59)).replace(
            tzinfo=timezone.utc
        )

        all_bars = self._fetch_bars_paginated(
            instrument_id=instrument_id,
            category=category,
            webull_ts=webull_ts,
            limit=MAX_BARS_PER_REQUEST,
        )

        # Filter to the requested time range
        filtered: List[Dict[str, Any]] = [
            b for b in all_bars if start_dt <= b["timestamp"] <= end_dt
        ]

        return self._bars_to_dataframe(filtered)

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
            Dictionary with ``price``, ``open``, ``high``, ``low``,
            ``close``, and ``volume`` — all as ``Decimal``.

        Raises:
            BrokerError: If the Webull API call fails.
        """
        category = self._detect_category(symbol)

        try:
            instrument_id = self._instrument_cache.resolve(
                symbol, category=category
            )
        except BrokerError:
            raise
        except Exception as exc:
            raise BrokerError(
                error_code="instrument_resolve_error",
                message=f"Failed to resolve symbol '{symbol}': {exc}",
                broker_name="webull",
            ) from exc

        try:
            md = self._get_market_data_api()
            response = md.get_snapshot(
                instrument_id=instrument_id,
                category=category,
            )
        except BrokerError:
            raise
        except Exception as exc:
            raise BrokerError(
                error_code="snapshot_error",
                message=f"Failed to get snapshot for {symbol}: {exc}",
                broker_name="webull",
            ) from exc

        if not response:
            return {
                "price": Decimal("0"),
                "open": Decimal("0"),
                "high": Decimal("0"),
                "low": Decimal("0"),
                "close": Decimal("0"),
                "volume": Decimal("0"),
            }

        trade = response.get("trade", {})
        return {
            "price": Decimal(str(trade.get("price", "0"))),
            "open": Decimal(str(response.get("open", "0"))),
            "high": Decimal(str(response.get("high", "0"))),
            "low": Decimal(str(response.get("low", "0"))),
            "close": Decimal(str(response.get("close", "0"))),
            "volume": Decimal(str(trade.get("volume", "0"))),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_bars_paginated(
        self,
        instrument_id: str,
        category: str,
        webull_ts: str,
        limit: int = MAX_BARS_PER_REQUEST,
    ) -> List[Dict[str, Any]]:
        """Fetch bars from the SDK, paginating if needed.

        The Webull API caps each request at ``MAX_BARS_PER_REQUEST``
        bars. If *limit* exceeds that cap, multiple requests are issued
        and the results concatenated.

        Returns:
            List of parsed bar dicts (see ``_parse_bar``).
        """
        md = self._get_market_data_api()
        all_bars: List[Dict[str, Any]] = []
        remaining = limit

        while remaining > 0:
            count = min(remaining, MAX_BARS_PER_REQUEST)

            try:
                response = md.get_bars(
                    instrument_id=instrument_id,
                    category=category,
                    timespan=webull_ts,
                    count=count,
                )
            except BrokerError:
                raise
            except Exception as exc:
                raise BrokerError(
                    error_code="market_data_error",
                    message=f"Failed to fetch bars: {exc}",
                    broker_name="webull",
                ) from exc

            raw_bars = (response or {}).get("bars", [])
            if not raw_bars:
                break

            parsed = [self._parse_bar(b) for b in raw_bars]
            all_bars.extend(parsed)

            # If we got fewer than requested, no more data available
            if len(raw_bars) < count:
                break

            remaining -= len(raw_bars)

        return all_bars

    @staticmethod
    def _bars_to_dataframe(bars: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert a list of bar dicts to a pandas DataFrame.

        Returns an empty DataFrame with the correct columns if *bars*
        is empty.
        """
        columns = ["open", "high", "low", "close", "volume"]
        if not bars:
            return pd.DataFrame(columns=columns)

        df = pd.DataFrame(bars)
        df = df.set_index("timestamp")
        df.index.name = "timestamp"
        return df[columns]
