"""Tests for AlpacaMarketData adapter."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from beavr.broker.alpaca.data import TIMEFRAME_MAP, AlpacaMarketData
from beavr.broker.models import BrokerError

# ===== Mock helpers =====


class MockBar:
    """Mimics an Alpaca bar object."""

    def __init__(
        self,
        timestamp: datetime,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: int,
    ) -> None:
        self.timestamp = timestamp
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class MockBarsResponse:
    """Mimics an Alpaca bars response."""

    def __init__(self, data: dict) -> None:
        self.data = data


class MockTrade:
    """Mimics latest-trade data inside a snapshot."""

    def __init__(self) -> None:
        self.price = 150.25
        self.size = 100
        self.timestamp = datetime(2025, 1, 15, 10, 0, 0)


class MockQuote:
    """Mimics latest-quote data inside a snapshot."""

    def __init__(self) -> None:
        self.bid_price = 150.00
        self.ask_price = 150.50
        self.bid_size = 200
        self.ask_size = 300


class MockBar2:
    """Mimics a bar inside a snapshot (daily/minute bar)."""

    def __init__(self) -> None:
        self.open = 149.00
        self.high = 151.00
        self.low = 148.50
        self.close = 150.25
        self.volume = 5000000


class MockSnapshot:
    """Mimics an Alpaca snapshot response keyed by symbol."""

    def __init__(self, symbol: str) -> None:
        snap = MagicMock()
        snap.latest_trade = MockTrade()
        snap.latest_quote = MockQuote()
        snap.daily_bar = MockBar2()
        snap.minute_bar = MockBar2()
        # Snapshot is accessed via attribute named after the symbol
        setattr(self, symbol, snap)


def _make_response(
    symbol: str,
    dates: list[str],
    prices: list[float],
) -> MockBarsResponse:
    """Build a ``MockBarsResponse`` for *symbol*."""
    bars = [
        MockBar(
            timestamp=datetime.fromisoformat(d),
            open_=p,
            high=p + 1,
            low=p - 1,
            close=p,
            volume=1_000_000 + i * 100_000,
        )
        for i, (d, p) in enumerate(zip(dates, prices))
    ]
    return MockBarsResponse({symbol: bars})


# ===== Fixtures =====


@pytest.fixture
def _patch_clients():
    """Patch both Alpaca data clients so no real HTTP calls are made."""
    with (
        patch(
            "beavr.broker.alpaca.data.StockHistoricalDataClient"
        ) as stock_cls,
        patch(
            "beavr.broker.alpaca.data.CryptoHistoricalDataClient"
        ) as crypto_cls,
    ):
        yield stock_cls.return_value, crypto_cls.return_value


@pytest.fixture
def adapter(_patch_clients) -> AlpacaMarketData:
    """Return an ``AlpacaMarketData`` instance with mocked clients."""
    return AlpacaMarketData("key", "secret")


@pytest.fixture
def stock_client(_patch_clients) -> MagicMock:
    """Return the mocked ``StockHistoricalDataClient``."""
    return _patch_clients[0]


@pytest.fixture
def crypto_client(_patch_clients) -> MagicMock:
    """Return the mocked ``CryptoHistoricalDataClient``."""
    return _patch_clients[1]


# ===== Tests =====


class TestAlpacaMarketDataInit:
    """Tests for initialisation."""

    def test_init_creates_both_clients(self, _patch_clients) -> None:
        """Both stock and crypto clients should be instantiated."""
        stock_cls_instance, crypto_cls_instance = _patch_clients
        adapter = AlpacaMarketData("k", "s")
        # Accessing the private attrs confirms they were assigned
        assert adapter._stock_client is stock_cls_instance
        assert adapter._crypto_client is crypto_cls_instance

    def test_init_cache_default_none(self, _patch_clients) -> None:
        """Cache should default to None."""
        adapter = AlpacaMarketData("k", "s")
        assert adapter._cache is None


class TestProviderName:
    """Tests for provider_name property."""

    def test_provider_name_returns_alpaca(self, adapter: AlpacaMarketData) -> None:
        """provider_name should return 'alpaca'."""
        assert adapter.provider_name == "alpaca"


class TestGetBars:
    """Tests for get_bars method."""

    def test_returns_dataframe_with_correct_columns(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """Returned DataFrame should have OHLCV columns."""
        stock_client.get_stock_bars.return_value = _make_response(
            "SPY",
            ["2024-01-15T00:00:00", "2024-01-16T00:00:00"],
            [450.0, 452.0],
        )

        df = adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 16))

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_returns_datetimeindex(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """Index should be a DatetimeIndex named 'timestamp'."""
        stock_client.get_stock_bars.return_value = _make_response(
            "SPY",
            ["2024-01-15T00:00:00"],
            [450.0],
        )

        df = adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.name == "timestamp"

    def test_values_are_decimal(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """OHLCV values should be Decimal."""
        stock_client.get_stock_bars.return_value = _make_response(
            "SPY",
            ["2024-01-15T00:00:00"],
            [450.0],
        )

        df = adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

        for col in ("open", "high", "low", "close", "volume"):
            assert isinstance(df[col].iloc[0], Decimal), f"{col} is not Decimal"

    def test_crypto_detection(
        self,
        adapter: AlpacaMarketData,
        crypto_client: MagicMock,
        stock_client: MagicMock,
    ) -> None:
        """Symbols containing '/' should use the crypto client."""
        crypto_client.get_crypto_bars.return_value = _make_response(
            "BTC/USD",
            ["2024-01-15T00:00:00"],
            [42000.0],
        )

        adapter.get_bars("BTC/USD", date(2024, 1, 15), date(2024, 1, 15))

        crypto_client.get_crypto_bars.assert_called_once()
        stock_client.get_stock_bars.assert_not_called()

    def test_stock_uses_stock_client(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
        crypto_client: MagicMock,
    ) -> None:
        """Non-crypto symbols should use the stock client."""
        stock_client.get_stock_bars.return_value = _make_response(
            "AAPL",
            ["2024-01-15T00:00:00"],
            [185.0],
        )

        adapter.get_bars("AAPL", date(2024, 1, 15), date(2024, 1, 15))

        stock_client.get_stock_bars.assert_called_once()
        crypto_client.get_crypto_bars.assert_not_called()

    @pytest.mark.parametrize("tf", list(TIMEFRAME_MAP.keys()))
    def test_timeframe_mapping(
        self,
        tf: str,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """All 7 protocol timeframes should be accepted without error."""
        stock_client.get_stock_bars.return_value = _make_response(
            "SPY",
            ["2024-01-15T00:00:00"],
            [450.0],
        )

        df = adapter.get_bars(
            "SPY", date(2024, 1, 15), date(2024, 1, 15), timeframe=tf
        )

        assert len(df) == 1

    def test_invalid_timeframe_raises_broker_error(
        self,
        adapter: AlpacaMarketData,
    ) -> None:
        """An unsupported timeframe should raise BrokerError."""
        with pytest.raises(BrokerError, match="Unsupported timeframe"):
            adapter.get_bars(
                "SPY", date(2024, 1, 15), date(2024, 1, 15), timeframe="3day"
            )

    def test_api_error_wraps_in_broker_error(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """Alpaca API exceptions should be wrapped in BrokerError."""
        stock_client.get_stock_bars.side_effect = Exception("timeout")

        with pytest.raises(BrokerError, match="Failed to fetch bars"):
            adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

    def test_empty_response_returns_empty_dataframe(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """An empty API response should return an empty DataFrame."""
        stock_client.get_stock_bars.return_value = MockBarsResponse({"SPY": []})

        df = adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

        assert df.empty
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_missing_symbol_returns_empty_dataframe(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """A response with no data for the requested symbol returns empty."""
        stock_client.get_stock_bars.return_value = MockBarsResponse({})

        df = adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

        assert df.empty


class TestGetBarsMulti:
    """Tests for get_bars_multi method."""

    def test_returns_dict_keyed_by_symbol(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """Result should be a dict mapping each symbol to a DataFrame."""
        symbols = ["SPY", "QQQ"]

        def _side_effect(request):
            sym = request.symbol_or_symbols
            return _make_response(sym, ["2024-01-15T00:00:00"], [450.0])

        stock_client.get_stock_bars.side_effect = _side_effect

        result = adapter.get_bars_multi(
            symbols, date(2024, 1, 15), date(2024, 1, 15)
        )

        assert set(result.keys()) == {"SPY", "QQQ"}
        for sym in symbols:
            assert isinstance(result[sym], pd.DataFrame)

    def test_calls_get_bars_for_each_symbol(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """get_bars_multi should invoke get_bars once per symbol."""
        symbols = ["A", "B", "C"]

        stock_client.get_stock_bars.return_value = MockBarsResponse({})

        adapter.get_bars_multi(symbols, date(2024, 1, 15), date(2024, 1, 15))

        assert stock_client.get_stock_bars.call_count == len(symbols)


class TestGetSnapshot:
    """Tests for get_snapshot method."""

    def test_returns_dict(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """Snapshot should return a dict with trade/quote/bar data."""
        stock_client.get_stock_snapshot.return_value = MockSnapshot("SPY")

        result = adapter.get_snapshot("SPY")

        assert isinstance(result, dict)
        assert "latest_trade" in result
        assert isinstance(result["latest_trade"]["price"], Decimal)

    def test_snapshot_error_wraps_in_broker_error(
        self,
        adapter: AlpacaMarketData,
        stock_client: MagicMock,
    ) -> None:
        """Snapshot API errors should be wrapped in BrokerError."""
        stock_client.get_stock_snapshot.side_effect = Exception("down")

        with pytest.raises(BrokerError, match="Failed to get snapshot"):
            adapter.get_snapshot("SPY")

    def test_snapshot_crypto_uses_crypto_client(
        self,
        adapter: AlpacaMarketData,
        crypto_client: MagicMock,
        stock_client: MagicMock,
    ) -> None:
        """Crypto snapshots should use the crypto client."""
        crypto_client.get_crypto_snapshot.return_value = MockSnapshot("BTC/USD")

        adapter.get_snapshot("BTC/USD")

        crypto_client.get_crypto_snapshot.assert_called_once()
        stock_client.get_stock_snapshot.assert_not_called()


class TestCache:
    """Tests for cache integration."""

    def test_cache_hit_skips_api(
        self,
        _patch_clients,
        stock_client: MagicMock,
    ) -> None:
        """When cache returns data, no API call should be made."""
        mock_cache = MagicMock()
        mock_cache.get_bars.return_value = pd.DataFrame(
            {
                "open": [Decimal("450")],
                "high": [Decimal("451")],
                "low": [Decimal("449")],
                "close": [Decimal("450")],
                "volume": [Decimal("1000000")],
            },
            index=pd.DatetimeIndex(
                [datetime(2024, 1, 15)], name="timestamp"
            ),
        )

        adapter = AlpacaMarketData("k", "s", cache=mock_cache)
        df = adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

        stock_client.get_stock_bars.assert_not_called()
        assert len(df) == 1

    def test_cache_miss_hits_api(
        self,
        _patch_clients,
        stock_client: MagicMock,
    ) -> None:
        """When cache returns None, data should be fetched from the API."""
        mock_cache = MagicMock()
        mock_cache.get_bars.return_value = None

        stock_client.get_stock_bars.return_value = _make_response(
            "SPY",
            ["2024-01-15T00:00:00"],
            [450.0],
        )

        adapter = AlpacaMarketData("k", "s", cache=mock_cache)
        df = adapter.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

        stock_client.get_stock_bars.assert_called_once()
        mock_cache.save_bars.assert_called_once()
        assert len(df) == 1
