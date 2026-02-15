"""Webull instrument cache for symbol → instrument_id resolution.

Webull requires numeric instrument_id for all trading and data operations.
This cache resolves ticker symbols to instrument IDs with two-tier caching:
in-memory dictionary for fast lookups and SQLite for persistence across restarts.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from beavr.broker.models import BrokerError

logger = logging.getLogger(__name__)

# Default TTL: 24 hours
DEFAULT_TTL_SECONDS: int = 86400

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS instrument_cache (
    symbol TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    category TEXT NOT NULL,
    exchange TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (symbol, category)
)
"""


class InstrumentCache:
    """Two-tier cache for Webull symbol → instrument_id resolution.

    Tier 1: In-memory dict for fast lookups within a session.
    Tier 2: SQLite for persistence across restarts.
    Falls back to Webull API when both miss.
    """

    def __init__(
        self,
        api_client: Any,
        db_path: str = ":memory:",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._api_client = api_client
        self._ttl = ttl_seconds
        # {category: {symbol: instrument_id}}
        self._memory_cache: Dict[str, Dict[str, str]] = {}
        self._memory_timestamps: Dict[str, Dict[str, float]] = {}

        # Initialize SQLite
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

    def _detect_category(self, symbol: str) -> str:
        """Auto-detect Webull category from symbol pattern."""
        if "/" in symbol:
            return "CRYPTO"
        return "US_STOCK"

    def resolve(
        self,
        symbol: str,
        category: Optional[str] = None,
        force_refresh: bool = False,
    ) -> str:
        """Resolve a single symbol to its instrument_id.

        Checks memory → SQLite → API in order.

        Args:
            symbol: Ticker symbol (e.g. ``"AAPL"`` or ``"BTC/USD"``).
            category: Webull category override. Auto-detected if ``None``.
            force_refresh: When ``True``, bypass all caches and hit the API.

        Returns:
            The Webull instrument_id string.

        Raises:
            BrokerError: If the symbol cannot be resolved.
        """
        cat = category or self._detect_category(symbol)

        if not force_refresh:
            # Check memory
            mem_result = self._get_from_memory(symbol, cat)
            if mem_result is not None:
                return mem_result

            # Check SQLite
            db_result = self._get_from_db(symbol, cat)
            if db_result is not None:
                # Populate memory cache
                self._set_in_memory(symbol, cat, db_result)
                return db_result

        # Call API
        result = self._fetch_from_api([symbol], cat)
        if symbol not in result:
            raise BrokerError(
                error_code="instrument_not_found",
                message=f"Could not resolve symbol '{symbol}' (category={cat})",
                broker_name="webull",
            )

        return result[symbol]

    def resolve_batch(
        self,
        symbols: List[str],
        category: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, str]:
        """Resolve multiple symbols. Only fetches uncached symbols from API.

        Args:
            symbols: List of ticker symbols.
            category: Webull category override. Auto-detected from the first
                symbol if ``None``.
            force_refresh: When ``True``, bypass all caches and hit the API.

        Returns:
            Mapping of symbol → instrument_id for all resolved symbols.
        """
        if not symbols:
            return {}

        cat = category or self._detect_category(symbols[0])
        result: Dict[str, str] = {}
        uncached: List[str] = []

        if not force_refresh:
            for sym in symbols:
                # Check memory first
                mem = self._get_from_memory(sym, cat)
                if mem is not None:
                    result[sym] = mem
                    continue

                # Check SQLite
                db = self._get_from_db(sym, cat)
                if db is not None:
                    self._set_in_memory(sym, cat, db)
                    result[sym] = db
                    continue

                uncached.append(sym)
        else:
            uncached = list(symbols)

        # Fetch uncached from API
        if uncached:
            api_result = self._fetch_from_api(uncached, cat)
            result.update(api_result)

        return result

    # ------------------------------------------------------------------
    # Memory cache helpers
    # ------------------------------------------------------------------

    def _get_from_memory(self, symbol: str, category: str) -> Optional[str]:
        """Check memory cache, respecting TTL."""
        cat_cache = self._memory_cache.get(category, {})
        if symbol in cat_cache:
            timestamp = self._memory_timestamps.get(category, {}).get(symbol, 0)
            if (time.time() - timestamp) < self._ttl:
                return cat_cache[symbol]
            # Expired — remove from memory
            del cat_cache[symbol]
            if symbol in self._memory_timestamps.get(category, {}):
                del self._memory_timestamps[category][symbol]
        return None

    def _set_in_memory(
        self, symbol: str, category: str, instrument_id: str
    ) -> None:
        """Set a value in the memory cache."""
        if category not in self._memory_cache:
            self._memory_cache[category] = {}
            self._memory_timestamps[category] = {}
        self._memory_cache[category][symbol] = instrument_id
        self._memory_timestamps[category][symbol] = time.time()

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------

    def _get_from_db(self, symbol: str, category: str) -> Optional[str]:
        """Check SQLite cache, respecting TTL."""
        cursor = self._conn.execute(
            "SELECT instrument_id, updated_at FROM instrument_cache "
            "WHERE symbol = ? AND category = ?",
            (symbol, category),
        )
        row = cursor.fetchone()
        if row is not None:
            instrument_id, updated_at = row
            if (time.time() - updated_at) < self._ttl:
                return instrument_id
        return None

    def _save_to_db(
        self,
        symbol: str,
        category: str,
        instrument_id: str,
        exchange: Optional[str] = None,
    ) -> None:
        """Save to SQLite cache."""
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO instrument_cache "
            "(symbol, instrument_id, category, exchange, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (symbol, instrument_id, category, exchange, now),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # API interaction
    # ------------------------------------------------------------------

    def _fetch_from_api(
        self, symbols: List[str], category: str
    ) -> Dict[str, str]:
        """Fetch instrument IDs from Webull API and cache results."""
        try:
            from webullsdkmdata.quotes.instrument import Instrument
        except ImportError:
            raise BrokerError(
                error_code="sdk_not_installed",
                message="webull-python-sdk-mdata required for instrument resolution",
                broker_name="webull",
            ) from None

        try:
            instrument_api = Instrument(self._api_client)
            symbols_str = ",".join(symbols)
            response = instrument_api.get_instrument(symbols_str, category)

            result: Dict[str, str] = {}
            if response and isinstance(response, list):
                for item in response:
                    sym: str = item.get("symbol", "")
                    inst_id: str = str(item.get("instrument_id", ""))
                    exchange: Optional[str] = item.get("exchange_code")
                    if sym and inst_id:
                        result[sym] = inst_id
                        # Cache in both tiers
                        self._set_in_memory(sym, category, inst_id)
                        self._save_to_db(sym, category, inst_id, exchange)

            return result
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="instrument_resolution_error",
                message=f"Failed to resolve instruments {symbols}: {e}",
                broker_name="webull",
            ) from e

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()
