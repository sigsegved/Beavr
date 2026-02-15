"""Tests for Webull InstrumentCache."""

from __future__ import annotations

import sys
import time
import types
from typing import Dict, Generator, List
from unittest.mock import MagicMock, patch

import pytest

from beavr.broker.models import BrokerError
from beavr.broker.webull.instrument_cache import InstrumentCache


def _make_api_response(
    symbols: Dict[str, str],
    exchange: str = "NAS",
) -> List[Dict[str, str]]:
    """Build a fake Webull instrument API response."""
    return [
        {
            "symbol": sym,
            "instrument_id": inst_id,
            "exchange_code": exchange,
            "currency": "USD",
        }
        for sym, inst_id in symbols.items()
    ]


@pytest.fixture(autouse=True)
def _fake_webull_sdk() -> Generator[MagicMock, None, None]:
    """Inject fake webullsdkmdata modules into sys.modules so lazy imports resolve."""
    mock_instrument_cls = MagicMock()

    mod_root = types.ModuleType("webullsdkmdata")
    mod_quotes = types.ModuleType("webullsdkmdata.quotes")
    mod_instrument = types.ModuleType("webullsdkmdata.quotes.instrument")
    mod_instrument.Instrument = mock_instrument_cls  # type: ignore[attr-defined]

    with patch.dict(
        sys.modules,
        {
            "webullsdkmdata": mod_root,
            "webullsdkmdata.quotes": mod_quotes,
            "webullsdkmdata.quotes.instrument": mod_instrument,
        },
    ):
        yield mock_instrument_cls


class TestInstrumentCache:
    """Tests for InstrumentCache."""

    # ===== Fixtures =====

    @pytest.fixture
    def mock_api_client(self) -> MagicMock:
        """Create a mock Webull API client."""
        return MagicMock()

    @pytest.fixture
    def mock_instrument(self, _fake_webull_sdk: MagicMock) -> MagicMock:
        """Return the mock Instrument *instance* (what __init__ returns)."""
        instance = MagicMock()
        _fake_webull_sdk.return_value = instance
        return instance

    @pytest.fixture
    def cache(self, mock_api_client: MagicMock) -> Generator[InstrumentCache, None, None]:
        """Create an InstrumentCache with in-memory SQLite."""
        c = InstrumentCache(api_client=mock_api_client, db_path=":memory:")
        yield c
        c.close()

    # ===== 1. Cache miss → API call → result returned =====

    def test_resolve_cache_miss_calls_api_and_returns_id(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """Cache miss should call the Webull API and return the instrument_id."""
        mock_instrument.get_instrument.return_value = _make_api_response(
            {"AAPL": "913256135"}
        )
        result = cache.resolve("AAPL")

        assert result == "913256135"
        mock_instrument.get_instrument.assert_called_once_with("AAPL", "US_STOCK")

    # ===== 2. Cache miss → API call → memory cache populated =====

    def test_resolve_populates_memory_cache(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """After API fetch, the result should be in the memory cache."""
        mock_instrument.get_instrument.return_value = _make_api_response(
            {"AAPL": "913256135"}
        )
        cache.resolve("AAPL")

        # Memory cache should be populated
        assert cache._memory_cache["US_STOCK"]["AAPL"] == "913256135"

    # ===== 3. Cache miss → API call → SQLite cache populated =====

    def test_resolve_populates_sqlite_cache(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """After API fetch, the result should be persisted in SQLite."""
        mock_instrument.get_instrument.return_value = _make_api_response(
            {"AAPL": "913256135"}
        )
        cache.resolve("AAPL")

        cursor = cache._conn.execute(
            "SELECT instrument_id FROM instrument_cache WHERE symbol = ? AND category = ?",
            ("AAPL", "US_STOCK"),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "913256135"

    # ===== 4. Memory cache hit → no API call =====

    def test_resolve_memory_hit_no_api_call(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """Memory cache hit should return immediately without an API call."""
        # Pre-populate memory cache
        cache._set_in_memory("AAPL", "US_STOCK", "913256135")

        result = cache.resolve("AAPL")

        assert result == "913256135"
        mock_instrument.get_instrument.assert_not_called()

    # ===== 5. SQLite cache hit (memory cleared) → restored, no API call =====

    def test_resolve_sqlite_hit_restores_to_memory(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """SQLite hit should restore value to memory cache without API call."""
        # Write directly to SQLite (simulating a previous session)
        cache._save_to_db("AAPL", "US_STOCK", "913256135", "NAS")

        result = cache.resolve("AAPL")

        assert result == "913256135"
        mock_instrument.get_instrument.assert_not_called()
        # Memory cache should now contain the value
        assert cache._memory_cache["US_STOCK"]["AAPL"] == "913256135"

    # ===== 6. Batch: mix of cached + uncached → only uncached hit API =====

    def test_resolve_batch_mixed_cached_and_uncached(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """Batch resolve should only API-fetch symbols not already cached."""
        # Pre-cache AAPL
        cache._set_in_memory("AAPL", "US_STOCK", "913256135")

        mock_instrument.get_instrument.return_value = _make_api_response(
            {"TSLA": "888888888"}
        )
        result = cache.resolve_batch(["AAPL", "TSLA"])

        assert result == {"AAPL": "913256135", "TSLA": "888888888"}
        # Only TSLA should be in the API call
        mock_instrument.get_instrument.assert_called_once_with("TSLA", "US_STOCK")

    # ===== 7. Batch: all cached → no API call =====

    def test_resolve_batch_all_cached_no_api(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """Batch resolve with all symbols cached should not call the API."""
        cache._set_in_memory("AAPL", "US_STOCK", "913256135")
        cache._set_in_memory("TSLA", "US_STOCK", "888888888")

        result = cache.resolve_batch(["AAPL", "TSLA"])

        assert result == {"AAPL": "913256135", "TSLA": "888888888"}
        mock_instrument.get_instrument.assert_not_called()

    # ===== 8. TTL expiry → re-fetches from API =====

    def test_resolve_ttl_expiry_refetches(
        self, mock_api_client: MagicMock, mock_instrument: MagicMock
    ) -> None:
        """Expired cache entries should be re-fetched from the API."""
        cache = InstrumentCache(
            api_client=mock_api_client, db_path=":memory:", ttl_seconds=1
        )
        try:
            # Pre-populate memory & db with old timestamp
            cache._set_in_memory("AAPL", "US_STOCK", "old_id")
            cache._save_to_db("AAPL", "US_STOCK", "old_id")

            # Backdate timestamps so entries are expired
            cache._memory_timestamps["US_STOCK"]["AAPL"] = time.time() - 10
            cache._conn.execute(
                "UPDATE instrument_cache SET updated_at = ? WHERE symbol = ?",
                (time.time() - 10, "AAPL"),
            )
            cache._conn.commit()

            mock_instrument.get_instrument.return_value = _make_api_response(
                {"AAPL": "new_id"}
            )
            result = cache.resolve("AAPL")

            assert result == "new_id"
            mock_instrument.get_instrument.assert_called_once()
        finally:
            cache.close()

    # ===== 9. Unknown symbol → raises BrokerError =====

    def test_resolve_unknown_symbol_raises_broker_error(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """Resolving an unknown symbol should raise BrokerError."""
        mock_instrument.get_instrument.return_value = []

        with pytest.raises(BrokerError, match="instrument_not_found"):
            cache.resolve("INVALID_SYMBOL")

    # ===== 10. Category auto-detection: "/" → CRYPTO =====

    def test_detect_category_crypto(self, cache: InstrumentCache) -> None:
        """Symbols containing '/' should auto-detect as CRYPTO."""
        assert cache._detect_category("BTC/USD") == "CRYPTO"
        assert cache._detect_category("ETH/USD") == "CRYPTO"

    # ===== 11. Category auto-detection: plain symbol → US_STOCK =====

    def test_detect_category_us_stock(self, cache: InstrumentCache) -> None:
        """Plain ticker symbols should auto-detect as US_STOCK."""
        assert cache._detect_category("AAPL") == "US_STOCK"
        assert cache._detect_category("TSLA") == "US_STOCK"
        assert cache._detect_category("SPY") == "US_STOCK"

    # ===== 12. Explicit category overrides auto-detection =====

    def test_explicit_category_overrides_detection(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """Explicitly provided category should override auto-detection."""
        mock_instrument.get_instrument.return_value = _make_api_response(
            {"AAPL": "913256135"}
        )
        cache.resolve("AAPL", category="HK_STOCK")

        mock_instrument.get_instrument.assert_called_once_with("AAPL", "HK_STOCK")

    # ===== 13. force_refresh bypasses cache =====

    def test_force_refresh_bypasses_cache(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """force_refresh=True should skip caches and call the API."""
        # Pre-populate caches
        cache._set_in_memory("AAPL", "US_STOCK", "old_id")
        cache._save_to_db("AAPL", "US_STOCK", "old_id")

        mock_instrument.get_instrument.return_value = _make_api_response(
            {"AAPL": "new_id"}
        )
        result = cache.resolve("AAPL", force_refresh=True)

        assert result == "new_id"
        mock_instrument.get_instrument.assert_called_once()

    # ===== 14. Empty batch returns empty dict =====

    def test_resolve_batch_empty_returns_empty(
        self, cache: InstrumentCache
    ) -> None:
        """Batch resolve with no symbols should return an empty dict."""
        result = cache.resolve_batch([])
        assert result == {}

    # ===== 15. API error wrapped in BrokerError =====

    def test_api_error_wrapped_in_broker_error(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """Unexpected API exceptions should be wrapped in BrokerError."""
        mock_instrument.get_instrument.side_effect = RuntimeError("connection lost")

        with pytest.raises(BrokerError, match="instrument_resolution_error"):
            cache.resolve("AAPL")

    # ===== 16. close() closes SQLite connection =====

    def test_close_closes_sqlite_connection(
        self, mock_api_client: MagicMock
    ) -> None:
        """close() should close the underlying SQLite connection."""
        cache = InstrumentCache(api_client=mock_api_client, db_path=":memory:")
        cache.close()

        with pytest.raises(Exception):
            cache._conn.execute("SELECT 1")

    # ===== 17. Batch force_refresh calls API for all symbols =====

    def test_resolve_batch_force_refresh_fetches_all(
        self, cache: InstrumentCache, mock_instrument: MagicMock
    ) -> None:
        """force_refresh on batch should re-fetch every symbol from API."""
        cache._set_in_memory("AAPL", "US_STOCK", "old_id")
        cache._set_in_memory("TSLA", "US_STOCK", "old_id_2")

        mock_instrument.get_instrument.return_value = _make_api_response(
            {"AAPL": "new_1", "TSLA": "new_2"}
        )
        result = cache.resolve_batch(
            ["AAPL", "TSLA"], force_refresh=True
        )

        assert result == {"AAPL": "new_1", "TSLA": "new_2"}
        mock_instrument.get_instrument.assert_called_once_with(
            "AAPL,TSLA", "US_STOCK"
        )
