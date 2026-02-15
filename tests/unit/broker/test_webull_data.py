"""Tests for WebullMarketData adapter."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from beavr.broker.models import BrokerError

# ---------------------------------------------------------------------------
# Mock Webull SDK modules before importing the data module
# ---------------------------------------------------------------------------

_mock_webullsdkcore = MagicMock()
_mock_webullsdktrade = MagicMock()
_mock_webullsdkmdata = MagicMock()

sys.modules.setdefault("webullsdkcore", _mock_webullsdkcore)
sys.modules.setdefault("webullsdkcore.client", _mock_webullsdkcore.client)
sys.modules.setdefault("webullsdktrade", _mock_webullsdktrade)
sys.modules.setdefault("webullsdktrade.trade", _mock_webullsdktrade.trade)
sys.modules.setdefault(
    "webullsdktrade.trade.account_info",
    _mock_webullsdktrade.trade.account_info,
)
sys.modules.setdefault(
    "webullsdktrade.trade.order_operation",
    _mock_webullsdktrade.trade.order_operation,
)
sys.modules.setdefault(
    "webullsdktrade.trade.trade_calendar",
    _mock_webullsdktrade.trade.trade_calendar,
)
sys.modules.setdefault("webullsdkmdata", _mock_webullsdkmdata)
sys.modules.setdefault("webullsdkmdata.quotes", _mock_webullsdkmdata.quotes)
sys.modules.setdefault(
    "webullsdkmdata.quotes.instrument",
    _mock_webullsdkmdata.quotes.instrument,
)
sys.modules.setdefault(
    "webullsdkmdata.quotes.market_data",
    _mock_webullsdkmdata.quotes.market_data,
)

from beavr.broker.webull.data import (  # noqa: E402
    MAX_BARS_PER_REQUEST,
    TIMEFRAME_MAP,
    WebullMarketData,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INSTRUMENT_ID = "913256135"
CRYPTO_INSTRUMENT_ID = "1024800525"


def _bar_dict(
    ts: str = "2025-01-15T14:30:00Z",
    open_: str = "175.00",
    high: str = "176.50",
    low: str = "174.00",
    close: str = "175.50",
    volume: str = "1000000",
) -> Dict[str, Any]:
    """Build a raw Webull bar response dict."""
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _snapshot_response(
    price: str = "175.50",
    open_: str = "174.00",
    high: str = "176.50",
    low: str = "173.50",
    close: str = "175.50",
    volume: str = "1000000",
) -> Dict[str, Any]:
    """Build a raw Webull snapshot response dict."""
    return {
        "trade": {"price": price, "volume": volume},
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def webull_data() -> Generator[
    tuple[WebullMarketData, MagicMock, MagicMock], None, None
]:
    """Create WebullMarketData with mocked SDK and instrument cache.

    Yields (data_provider, mock_market_data, mock_cache).
    """
    mock_api_client = MagicMock()
    mock_cache = MagicMock()
    mock_cache.resolve.return_value = INSTRUMENT_ID

    provider = WebullMarketData(
        api_client=mock_api_client,
        instrument_cache=mock_cache,
    )

    mock_md = MagicMock()
    provider._market_data_api = mock_md

    yield provider, mock_md, mock_cache


# ---------------------------------------------------------------------------
# Tests — Properties
# ---------------------------------------------------------------------------


class TestWebullMarketDataProperties:
    """Tests for data provider properties."""

    # 1
    def test_provider_name_returns_webull(
        self, webull_data: tuple[WebullMarketData, Any, Any]
    ) -> None:
        """provider_name should return 'webull'."""
        provider, *_ = webull_data
        assert provider.provider_name == "webull"


# ---------------------------------------------------------------------------
# Tests — get_bars
# ---------------------------------------------------------------------------


class TestGetBars:
    """Tests for get_bars method."""

    # 2
    def test_get_bars_single_symbol(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should return a DataFrame for a single symbol."""
        provider, mock_md, mock_cache = webull_data
        mock_md.get_bars.return_value = {
            "bars": [
                _bar_dict("2025-01-15T14:30:00Z"),
                _bar_dict("2025-01-16T14:30:00Z"),
            ]
        }

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        mock_cache.resolve.assert_called_once_with(
            "AAPL", category="US_STOCK"
        )

    # 3
    @pytest.mark.parametrize(
        "protocol_tf,webull_ts",
        [
            ("1min", "M1"),
            ("5min", "M5"),
            ("15min", "M15"),
            ("30min", "M30"),
            ("1hour", "H1"),
            ("1day", "D1"),
            ("1week", "W1"),
        ],
    )
    def test_get_bars_maps_timeframes_correctly(
        self,
        webull_data: tuple[WebullMarketData, MagicMock, MagicMock],
        protocol_tf: str,
        webull_ts: str,
    ) -> None:
        """get_bars should map protocol timeframe to Webull timespan."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {"bars": [_bar_dict()]}

        provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31),
            timeframe=protocol_tf,
        )

        call_kwargs = mock_md.get_bars.call_args
        assert call_kwargs.kwargs.get("timespan") == webull_ts or (
            call_kwargs[1].get("timespan") == webull_ts
        )

    # 4
    def test_get_bars_auto_detect_crypto_category(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should use CRYPTO category for symbols with '/'."""
        provider, mock_md, mock_cache = webull_data
        mock_cache.resolve.return_value = CRYPTO_INSTRUMENT_ID
        mock_md.get_bars.return_value = {"bars": [_bar_dict()]}

        provider.get_bars(
            "BTC/USD", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        mock_cache.resolve.assert_called_once_with(
            "BTC/USD", category="CRYPTO"
        )

    # 5
    def test_get_bars_auto_detect_stock_category(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should use US_STOCK category for normal symbols."""
        provider, mock_md, mock_cache = webull_data
        mock_md.get_bars.return_value = {"bars": [_bar_dict()]}

        provider.get_bars(
            "SPY", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        mock_cache.resolve.assert_called_once_with(
            "SPY", category="US_STOCK"
        )

    # 6
    def test_get_bars_filters_by_start_datetime(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should exclude bars before the start date."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {
            "bars": [
                _bar_dict("2024-12-31T10:00:00Z"),  # before start
                _bar_dict("2025-01-15T10:00:00Z"),  # after start
            ]
        }

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert len(result) == 1

    # 7
    def test_get_bars_filters_by_end_datetime(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should exclude bars after the end date."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {
            "bars": [
                _bar_dict("2025-01-15T10:00:00Z"),  # within range
                _bar_dict("2025-06-01T10:00:00Z"),  # after end
            ]
        }

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 3, 31)
        )

        assert len(result) == 1

    # 8
    def test_get_bars_empty_response(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should return empty DataFrame when no bars available."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {"bars": []}

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    # 9
    def test_get_bars_error_wraps_in_broker_error(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should wrap SDK errors in BrokerError."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.side_effect = RuntimeError("API timeout")

        with pytest.raises(BrokerError, match="Failed to fetch bars"):
            provider.get_bars(
                "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
            )

    # 10
    def test_get_bars_returns_decimal_values(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should return Decimal values for OHLCV columns."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {
            "bars": [
                _bar_dict(
                    ts="2025-01-15T14:30:00Z",
                    open_="175.25",
                    high="176.50",
                    low="174.00",
                    close="175.50",
                    volume="1000000",
                )
            ]
        }

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        row = result.iloc[0]
        assert isinstance(row["open"], Decimal)
        assert isinstance(row["high"], Decimal)
        assert isinstance(row["low"], Decimal)
        assert isinstance(row["close"], Decimal)
        assert isinstance(row["volume"], Decimal)
        assert row["open"] == Decimal("175.25")
        assert row["high"] == Decimal("176.50")

    # 11
    def test_get_bars_respects_date_range(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should only include bars within the date range."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {
            "bars": [
                _bar_dict("2025-01-10T10:00:00Z"),
                _bar_dict("2025-01-15T10:00:00Z"),
                _bar_dict("2025-01-20T10:00:00Z"),
                _bar_dict("2025-02-01T10:00:00Z"),
            ]
        }

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 12), end=date(2025, 1, 25)
        )

        assert len(result) == 2

    # 12
    def test_get_bars_invalid_timeframe(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should raise BrokerError for unsupported timeframe."""
        provider, *_ = webull_data

        with pytest.raises(BrokerError, match="Unsupported timeframe"):
            provider.get_bars(
                "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31),
                timeframe="2hour",
            )

    # 13
    def test_get_bars_none_response(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should handle None response gracefully."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = None

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    # 14
    def test_get_bars_instrument_resolve_error(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should raise BrokerError if instrument resolution fails."""
        provider, _, mock_cache = webull_data
        mock_cache.resolve.side_effect = RuntimeError("network error")

        with pytest.raises(BrokerError, match="Failed to resolve symbol"):
            provider.get_bars(
                "INVALID", start=date(2025, 1, 1), end=date(2025, 12, 31)
            )


# ---------------------------------------------------------------------------
# Tests — get_bars_multi
# ---------------------------------------------------------------------------


class TestGetBarsMulti:
    """Tests for get_bars_multi method."""

    # 15
    def test_get_bars_multi_multiple_symbols(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars_multi should return DataFrames for each symbol."""
        provider, mock_md, mock_cache = webull_data
        mock_md.get_bars.return_value = {
            "bars": [_bar_dict("2025-01-15T14:30:00Z")]
        }

        result = provider.get_bars_multi(
            ["AAPL", "MSFT"],
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
        )

        assert "AAPL" in result
        assert "MSFT" in result
        assert isinstance(result["AAPL"], pd.DataFrame)
        assert isinstance(result["MSFT"], pd.DataFrame)

    # 16
    def test_get_bars_multi_single_symbol(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars_multi should work with a single symbol."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {
            "bars": [_bar_dict("2025-01-15T14:30:00Z")]
        }

        result = provider.get_bars_multi(
            ["SPY"], start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert len(result) == 1
        assert "SPY" in result

    # 17
    def test_get_bars_multi_empty_symbols_list(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars_multi should return empty dict for empty symbols list."""
        provider, *_ = webull_data

        result = provider.get_bars_multi(
            [], start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert result == {}


# ---------------------------------------------------------------------------
# Tests — get_snapshot
# ---------------------------------------------------------------------------


class TestGetSnapshot:
    """Tests for get_snapshot method."""

    # 18
    def test_get_snapshot_returns_decimal_values(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_snapshot should return Decimal values."""
        provider, mock_md, _ = webull_data
        mock_md.get_snapshot.return_value = _snapshot_response()

        result = provider.get_snapshot("AAPL")

        assert isinstance(result["price"], Decimal)
        assert isinstance(result["open"], Decimal)
        assert isinstance(result["high"], Decimal)
        assert isinstance(result["low"], Decimal)
        assert isinstance(result["close"], Decimal)
        assert isinstance(result["volume"], Decimal)
        assert result["price"] == Decimal("175.50")
        assert result["open"] == Decimal("174.00")
        assert result["high"] == Decimal("176.50")

    # 19
    def test_get_snapshot_crypto_symbol(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_snapshot should use CRYPTO category for crypto symbols."""
        provider, mock_md, mock_cache = webull_data
        mock_cache.resolve.return_value = CRYPTO_INSTRUMENT_ID
        mock_md.get_snapshot.return_value = _snapshot_response(
            price="45000.00"
        )

        result = provider.get_snapshot("BTC/USD")

        mock_cache.resolve.assert_called_once_with(
            "BTC/USD", category="CRYPTO"
        )
        assert result["price"] == Decimal("45000.00")

    # 20
    def test_get_snapshot_error_wraps_in_broker_error(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_snapshot should wrap SDK errors in BrokerError."""
        provider, mock_md, _ = webull_data
        mock_md.get_snapshot.side_effect = RuntimeError("connection refused")

        with pytest.raises(BrokerError, match="Failed to get snapshot"):
            provider.get_snapshot("AAPL")

    # 21
    def test_get_snapshot_empty_response(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_snapshot should handle empty/None response gracefully."""
        provider, mock_md, _ = webull_data
        mock_md.get_snapshot.return_value = None

        result = provider.get_snapshot("AAPL")

        assert result["price"] == Decimal("0")
        assert result["open"] == Decimal("0")
        assert result["volume"] == Decimal("0")

    # 22
    def test_get_snapshot_stock_category(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_snapshot should use US_STOCK category for stock symbols."""
        provider, mock_md, mock_cache = webull_data
        mock_md.get_snapshot.return_value = _snapshot_response()

        provider.get_snapshot("MSFT")

        mock_cache.resolve.assert_called_once_with(
            "MSFT", category="US_STOCK"
        )

    # 23
    def test_get_snapshot_instrument_resolve_error(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_snapshot should raise BrokerError if instrument fails."""
        provider, _, mock_cache = webull_data
        mock_cache.resolve.side_effect = RuntimeError("timeout")

        with pytest.raises(BrokerError, match="Failed to resolve symbol"):
            provider.get_snapshot("BROKEN")


# ---------------------------------------------------------------------------
# Tests — Initialisation
# ---------------------------------------------------------------------------


class TestWebullMarketDataInit:
    """Tests for initialisation behaviour."""

    # 24
    def test_creates_instrument_cache_if_not_provided(self) -> None:
        """Should create its own InstrumentCache when none is given."""
        mock_api_client = MagicMock()

        with patch(
            "beavr.broker.webull.data.InstrumentCache"
        ) as mock_cache_cls:
            mock_cache_cls.return_value = MagicMock()
            WebullMarketData(
                api_client=mock_api_client, db_path="/tmp/test.db"
            )

            mock_cache_cls.assert_called_once_with(
                mock_api_client, db_path="/tmp/test.db"
            )

    # 25
    def test_uses_provided_instrument_cache(self) -> None:
        """Should use the given InstrumentCache when provided."""
        mock_api_client = MagicMock()
        mock_cache = MagicMock()

        with patch(
            "beavr.broker.webull.data.InstrumentCache"
        ) as mock_cache_cls:
            provider = WebullMarketData(
                api_client=mock_api_client,
                instrument_cache=mock_cache,
            )

            mock_cache_cls.assert_not_called()
            assert provider._instrument_cache is mock_cache


# ---------------------------------------------------------------------------
# Tests — Pagination
# ---------------------------------------------------------------------------


class TestGetBarsPagination:
    """Tests for pagination when requesting more than MAX_BARS_PER_REQUEST."""

    # 26
    def test_get_bars_pagination_for_large_requests(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should paginate when more than 1200 bars are needed."""
        provider, mock_md, _ = webull_data

        # First call returns full page, second call returns partial
        second_page = [
            _bar_dict(f"2025-02-{str(i).zfill(2)}T10:00:00Z")
            for i in range(1, 20)  # 19 bars
        ]

        # Simulate pagination: first call returns MAX_BARS_PER_REQUEST bars,
        # second call returns fewer
        full_page = [_bar_dict(f"2025-01-15T{str(i).zfill(2)}:00:00Z") for i in range(24)]
        # We need exactly MAX_BARS_PER_REQUEST bars for the first page
        big_page = full_page * (MAX_BARS_PER_REQUEST // len(full_page) + 1)
        big_page = big_page[:MAX_BARS_PER_REQUEST]

        mock_md.get_bars.side_effect = [
            {"bars": big_page},
            {"bars": second_page},
        ]

        # The internal fetch will make 1 call with count=1200 (the max)
        # and since it returns 1200, it won't paginate further on the
        # default call path. Let's test the pagination logic directly.
        result = provider._fetch_bars_paginated(
            instrument_id=INSTRUMENT_ID,
            category="US_STOCK",
            webull_ts="D1",
            limit=MAX_BARS_PER_REQUEST + 500,
        )

        assert mock_md.get_bars.call_count == 2
        assert len(result) == MAX_BARS_PER_REQUEST + len(second_page)

    # 27
    def test_get_bars_stops_on_fewer_bars_than_requested(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """Pagination should stop if the API returns fewer bars than count."""
        provider, mock_md, _ = webull_data

        small_page = [_bar_dict(f"2025-01-{str(i).zfill(2)}T10:00:00Z") for i in range(1, 6)]
        mock_md.get_bars.return_value = {"bars": small_page}

        result = provider._fetch_bars_paginated(
            instrument_id=INSTRUMENT_ID,
            category="US_STOCK",
            webull_ts="D1",
            limit=MAX_BARS_PER_REQUEST,
        )

        assert mock_md.get_bars.call_count == 1
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Tests — Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and data validation."""

    # 28
    def test_get_bars_passes_correct_params_to_sdk(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should pass the correct instrument_id and category."""
        provider, mock_md, mock_cache = webull_data
        mock_cache.resolve.return_value = INSTRUMENT_ID
        mock_md.get_bars.return_value = {"bars": [_bar_dict()]}

        provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31),
            timeframe="1day",
        )

        mock_md.get_bars.assert_called_once_with(
            instrument_id=INSTRUMENT_ID,
            category="US_STOCK",
            timespan="D1",
            count=MAX_BARS_PER_REQUEST,
        )

    # 29
    def test_get_bars_dataframe_has_correct_columns(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """get_bars should return DataFrame with expected column names."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {"bars": [_bar_dict()]}

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert list(result.columns) == ["open", "high", "low", "close", "volume"]
        assert result.index.name == "timestamp"

    # 30
    def test_get_bars_empty_dataframe_has_correct_columns(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """Empty DataFrame should still have the correct column names."""
        provider, mock_md, _ = webull_data
        mock_md.get_bars.return_value = {"bars": []}

        result = provider.get_bars(
            "AAPL", start=date(2025, 1, 1), end=date(2025, 12, 31)
        )

        assert list(result.columns) == ["open", "high", "low", "close", "volume"]

    # 31
    def test_get_bars_broker_error_passthrough(
        self, webull_data: tuple[WebullMarketData, MagicMock, MagicMock]
    ) -> None:
        """BrokerError from instrument cache should propagate directly."""
        provider, _, mock_cache = webull_data
        mock_cache.resolve.side_effect = BrokerError(
            error_code="instrument_not_found",
            message="Symbol not found",
            broker_name="webull",
        )

        with pytest.raises(BrokerError, match="Symbol not found"):
            provider.get_bars(
                "INVALID", start=date(2025, 1, 1), end=date(2025, 12, 31)
            )

    # 32
    def test_timeframe_map_contains_all_expected_keys(self) -> None:
        """TIMEFRAME_MAP should contain all protocol timeframes."""
        expected_keys = {"1min", "5min", "15min", "30min", "1hour", "1day", "1week"}
        assert set(TIMEFRAME_MAP.keys()) == expected_keys
