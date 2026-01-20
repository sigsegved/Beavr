"""Unit tests for AlpacaDataFetcher."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from beavr.data.alpaca import AlpacaAPIError, AlpacaDataFetcher
from beavr.db import BarCache, Database


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def cache(db):
    """Create a BarCache instance for testing."""
    return BarCache(db)


@pytest.fixture
def mock_client():
    """Create a mock Alpaca client."""
    with patch("beavr.data.alpaca.StockHistoricalDataClient") as mock:
        yield mock.return_value


class MockBar:
    """Mock Alpaca bar object."""

    def __init__(
        self,
        timestamp: datetime,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: int,
    ):
        self.timestamp = timestamp
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class MockBarsResponse:
    """Mock Alpaca bars response."""

    def __init__(self, data: dict):
        self.data = data


def make_mock_bars(symbol: str, dates: list[str], prices: list[float]) -> MockBarsResponse:
    """Create a mock bars response."""
    bars = [
        MockBar(
            timestamp=datetime.fromisoformat(date_str),
            open_=price,
            high=price + 1,
            low=price - 1,
            close=price,
            volume=1000000 + i * 100000,
        )
        for i, (date_str, price) in enumerate(zip(dates, prices))
    ]
    return MockBarsResponse({symbol: bars})


class TestAlpacaDataFetcherInit:
    """Tests for AlpacaDataFetcher initialization."""

    def test_init_creates_client(self, mock_client):
        """Test that init creates Alpaca client."""
        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        assert fetcher.client == mock_client

    def test_init_with_cache(self, mock_client, cache):
        """Test init with cache."""
        fetcher = AlpacaDataFetcher("test_key", "test_secret", cache=cache)
        assert fetcher.cache == cache

    def test_init_without_cache(self, mock_client):
        """Test init without cache."""
        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        assert fetcher.cache is None


class TestGetBars:
    """Tests for get_bars method."""

    def test_get_bars_from_api(self, mock_client):
        """Test fetching bars from API."""
        mock_response = make_mock_bars(
            "SPY",
            ["2024-01-15T00:00:00", "2024-01-16T00:00:00"],
            [450.0, 452.0],
        )
        mock_client.get_stock_bars.return_value = mock_response

        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        result = fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 16))

        assert len(result) == 2
        assert list(result.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert isinstance(result["close"].iloc[0], Decimal)

    def test_get_bars_uses_cache(self, mock_client, cache):
        """Test that cached data is returned without API call."""
        # Pre-populate cache
        bars_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-15", "2024-01-16"]),
            "open": [450.0, 452.0],
            "high": [451.0, 453.0],
            "low": [449.0, 451.0],
            "close": [450.0, 452.0],
            "volume": [1000000, 1100000],
        })
        cache.save_bars("SPY", bars_df)

        fetcher = AlpacaDataFetcher("test_key", "test_secret", cache=cache)
        result = fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 16))

        # Should not call API
        mock_client.get_stock_bars.assert_not_called()
        assert len(result) == 2

    def test_get_bars_caches_result(self, mock_client, cache):
        """Test that fetched data is cached."""
        mock_response = make_mock_bars(
            "SPY",
            ["2024-01-15T00:00:00", "2024-01-16T00:00:00"],
            [450.0, 452.0],
        )
        mock_client.get_stock_bars.return_value = mock_response

        fetcher = AlpacaDataFetcher("test_key", "test_secret", cache=cache)
        fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 16))

        # Cache should now have data
        assert cache.has_data("SPY", date(2024, 1, 15), date(2024, 1, 16))

    def test_get_bars_empty_response(self, mock_client):
        """Test handling empty response from API."""
        mock_response = MockBarsResponse({"SPY": []})
        mock_client.get_stock_bars.return_value = mock_response

        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        result = fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 16))

        assert len(result) == 0
        assert list(result.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_get_bars_missing_symbol(self, mock_client):
        """Test handling missing symbol in response."""
        mock_response = MockBarsResponse({})
        mock_client.get_stock_bars.return_value = mock_response

        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        result = fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 16))

        assert len(result) == 0

    def test_get_bars_api_error(self, mock_client):
        """Test handling API errors."""
        mock_client.get_stock_bars.side_effect = Exception("API Error")

        fetcher = AlpacaDataFetcher("test_key", "test_secret")

        with pytest.raises(AlpacaAPIError, match="Failed to fetch bars"):
            fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 16))


class TestGetMultiBars:
    """Tests for get_multi_bars method."""

    def test_get_multi_bars(self, mock_client):
        """Test fetching bars for multiple symbols."""
        # Set up mock to return different data for each call
        call_count = [0]
        symbols = ["SPY", "VOO"]

        def mock_get_bars(request):
            symbol = symbols[call_count[0]]
            call_count[0] += 1
            return make_mock_bars(
                symbol,
                ["2024-01-15T00:00:00"],
                [450.0 if symbol == "SPY" else 400.0],
            )

        mock_client.get_stock_bars.side_effect = mock_get_bars

        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        result = fetcher.get_multi_bars(
            ["SPY", "VOO"],
            date(2024, 1, 15),
            date(2024, 1, 15),
        )

        assert "SPY" in result
        assert "VOO" in result
        assert len(result["SPY"]) == 1
        assert len(result["VOO"]) == 1


class TestTimeframeConversion:
    """Tests for timeframe conversion."""

    def test_timeframe_1day(self, mock_client):
        """Test 1Day timeframe."""
        mock_response = make_mock_bars("SPY", ["2024-01-15T00:00:00"], [450.0])
        mock_client.get_stock_bars.return_value = mock_response

        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15), timeframe="1Day")

        # Verify timeframe was set correctly in request
        call_args = mock_client.get_stock_bars.call_args
        request = call_args[0][0]
        # Compare by amount and unit, not by object identity
        assert request.timeframe.amount == 1
        assert request.timeframe.unit.value == "Day"

    def test_timeframe_1hour(self, mock_client):
        """Test 1Hour timeframe."""
        mock_response = make_mock_bars("SPY", ["2024-01-15T00:00:00"], [450.0])
        mock_client.get_stock_bars.return_value = mock_response

        fetcher = AlpacaDataFetcher("test_key", "test_secret")
        fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15), timeframe="1Hour")

        call_args = mock_client.get_stock_bars.call_args
        request = call_args[0][0]
        assert request.timeframe.amount == 1
        assert request.timeframe.unit.value == "Hour"

    def test_invalid_timeframe(self, mock_client):
        """Test invalid timeframe raises error."""
        fetcher = AlpacaDataFetcher("test_key", "test_secret")

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            fetcher.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15), timeframe="5Min")
