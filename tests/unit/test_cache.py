"""Unit tests for BarCache repository."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

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


def make_bars_df(
    dates: list[str],
    prices: list[float],
    volumes: list[int],
) -> pd.DataFrame:
    """Helper to create a bars DataFrame."""
    return pd.DataFrame({
        "timestamp": pd.to_datetime(dates),
        "open": prices,
        "high": [p + 1 for p in prices],
        "low": [p - 1 for p in prices],
        "close": prices,
        "volume": volumes,
    })


class TestBarCacheSave:
    """Tests for saving bars to cache."""

    def test_save_bars_basic(self, cache, db):
        """Test saving bars to cache."""
        bars = make_bars_df(
            dates=["2024-01-15", "2024-01-16", "2024-01-17"],
            prices=[450.0, 452.0, 455.0],
            volumes=[1000000, 1100000, 1200000],
        )

        cache.save_bars("SPY", bars)

        # Verify data was saved
        assert db.get_row_count("bars") == 3

    def test_save_bars_empty_dataframe(self, cache, db):
        """Test saving empty DataFrame does nothing."""
        bars = pd.DataFrame()
        cache.save_bars("SPY", bars)

        assert db.get_row_count("bars") == 0

    def test_save_bars_missing_columns(self, cache):
        """Test saving bars with missing columns raises error."""
        bars = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-15"]),
            "close": [450.0],
        })

        with pytest.raises(ValueError, match="Missing required columns"):
            cache.save_bars("SPY", bars)

    def test_save_bars_upsert(self, cache, db):
        """Test that duplicate inserts update existing data."""
        bars1 = make_bars_df(
            dates=["2024-01-15"],
            prices=[450.0],
            volumes=[1000000],
        )
        cache.save_bars("SPY", bars1)

        # Save again with different price
        bars2 = make_bars_df(
            dates=["2024-01-15"],
            prices=[460.0],
            volumes=[1100000],
        )
        cache.save_bars("SPY", bars2)

        # Should still be 1 row but with updated data
        assert db.get_row_count("bars") == 1

        with db.connect() as conn:
            cursor = conn.execute("SELECT close, volume FROM bars WHERE symbol = 'SPY'")
            row = cursor.fetchone()
            assert row["close"] == 460.0
            assert row["volume"] == 1100000

    def test_save_bars_different_timeframes(self, cache, db):
        """Test saving bars with different timeframes."""
        bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[450.0],
            volumes=[1000000],
        )

        cache.save_bars("SPY", bars, timeframe="1Day")
        cache.save_bars("SPY", bars, timeframe="1Hour")

        # Should have 2 rows (different timeframes)
        assert db.get_row_count("bars") == 2


class TestBarCacheGet:
    """Tests for retrieving bars from cache."""

    def test_get_bars_basic(self, cache):
        """Test retrieving cached bars."""
        bars = make_bars_df(
            dates=["2024-01-15", "2024-01-16", "2024-01-17"],
            prices=[450.0, 452.0, 455.0],
            volumes=[1000000, 1100000, 1200000],
        )
        cache.save_bars("SPY", bars)

        result = cache.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 17))

        assert result is not None
        assert len(result) == 3
        assert list(result.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_get_bars_returns_decimal(self, cache):
        """Test that prices are returned as Decimal."""
        bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[450.50],
            volumes=[1000000],
        )
        cache.save_bars("SPY", bars)

        result = cache.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 15))

        assert result is not None
        assert isinstance(result["close"].iloc[0], Decimal)
        assert result["close"].iloc[0] == Decimal("450.5")

    def test_get_bars_no_data(self, cache):
        """Test getting bars when no data exists."""
        result = cache.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 17))
        assert result is None

    def test_get_bars_partial_range(self, cache):
        """Test that get_bars returns None when only partial data exists."""
        bars = make_bars_df(
            dates=["2024-01-16"],  # Only middle date
            prices=[452.0],
            volumes=[1100000],
        )
        cache.save_bars("SPY", bars)

        # Request range that includes more than we have
        # has_data will return False since we don't have full coverage
        result = cache.get_bars("SPY", date(2024, 1, 15), date(2024, 1, 17))

        # Should return None because we don't have full range coverage
        assert result is None

        # But if we request just what we have, it should work
        result = cache.get_bars("SPY", date(2024, 1, 16), date(2024, 1, 16))
        assert result is not None
        assert len(result) == 1

    def test_get_bars_date_filtering(self, cache):
        """Test that date filtering works correctly."""
        bars = make_bars_df(
            dates=["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18"],
            prices=[450.0, 452.0, 455.0, 458.0],
            volumes=[1000000, 1100000, 1200000, 1300000],
        )
        cache.save_bars("SPY", bars)

        # Request subset of dates
        result = cache.get_bars("SPY", date(2024, 1, 16), date(2024, 1, 17))

        assert result is not None
        assert len(result) == 2

    def test_get_bars_different_symbol(self, cache):
        """Test that different symbols are separate."""
        spy_bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[450.0],
            volumes=[1000000],
        )
        cache.save_bars("SPY", spy_bars)

        # Request different symbol
        result = cache.get_bars("AAPL", date(2024, 1, 15), date(2024, 1, 15))
        assert result is None


class TestBarCacheHasData:
    """Tests for checking data existence."""

    def test_has_data_true(self, cache):
        """Test has_data returns True when data exists."""
        bars = make_bars_df(
            dates=["2024-01-15", "2024-01-16"],
            prices=[450.0, 452.0],
            volumes=[1000000, 1100000],
        )
        cache.save_bars("SPY", bars)

        assert cache.has_data("SPY", date(2024, 1, 15), date(2024, 1, 16)) is True

    def test_has_data_false(self, cache):
        """Test has_data returns False when no data."""
        assert cache.has_data("SPY", date(2024, 1, 15), date(2024, 1, 16)) is False

    def test_has_data_partial(self, cache):
        """Test has_data returns False when only partial data exists."""
        bars = make_bars_df(
            dates=["2024-01-16"],  # Only middle date
            prices=[452.0],
            volumes=[1100000],
        )
        cache.save_bars("SPY", bars)

        # Does NOT have full coverage - should return False
        assert cache.has_data("SPY", date(2024, 1, 15), date(2024, 1, 17)) is False
        # But does have coverage for just the date we have
        assert cache.has_data("SPY", date(2024, 1, 16), date(2024, 1, 16)) is True

    def test_has_data_outside_range(self, cache):
        """Test has_data returns False when data outside range."""
        bars = make_bars_df(
            dates=["2024-01-20"],  # Outside requested range
            prices=[460.0],
            volumes=[1000000],
        )
        cache.save_bars("SPY", bars)

        assert cache.has_data("SPY", date(2024, 1, 15), date(2024, 1, 17)) is False


class TestBarCacheGetDateRange:
    """Tests for getting cached date range."""

    def test_get_date_range_basic(self, cache):
        """Test getting date range for cached data."""
        bars = make_bars_df(
            dates=["2024-01-15", "2024-01-16", "2024-01-17"],
            prices=[450.0, 452.0, 455.0],
            volumes=[1000000, 1100000, 1200000],
        )
        cache.save_bars("SPY", bars)

        result = cache.get_date_range("SPY")

        assert result is not None
        assert result == (date(2024, 1, 15), date(2024, 1, 17))

    def test_get_date_range_no_data(self, cache):
        """Test getting date range when no data exists."""
        result = cache.get_date_range("SPY")
        assert result is None

    def test_get_date_range_single_day(self, cache):
        """Test getting date range for single day."""
        bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[450.0],
            volumes=[1000000],
        )
        cache.save_bars("SPY", bars)

        result = cache.get_date_range("SPY")

        assert result == (date(2024, 1, 15), date(2024, 1, 15))


class TestBarCacheDelete:
    """Tests for deleting cached bars."""

    def test_delete_bars(self, cache, db):
        """Test deleting bars for a symbol."""
        bars = make_bars_df(
            dates=["2024-01-15", "2024-01-16"],
            prices=[450.0, 452.0],
            volumes=[1000000, 1100000],
        )
        cache.save_bars("SPY", bars)

        deleted = cache.delete_bars("SPY")

        assert deleted == 2
        assert db.get_row_count("bars") == 0

    def test_delete_bars_preserves_other_symbols(self, cache, db):
        """Test that deleting bars preserves other symbols."""
        spy_bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[450.0],
            volumes=[1000000],
        )
        aapl_bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[180.0],
            volumes=[500000],
        )
        cache.save_bars("SPY", spy_bars)
        cache.save_bars("AAPL", aapl_bars)

        cache.delete_bars("SPY")

        assert db.get_row_count("bars") == 1  # AAPL still there

    def test_delete_bars_no_data(self, cache):
        """Test deleting bars when none exist."""
        deleted = cache.delete_bars("SPY")
        assert deleted == 0


class TestBarCacheGetSymbols:
    """Tests for getting list of cached symbols."""

    def test_get_symbols(self, cache):
        """Test getting list of symbols with cached data."""
        spy_bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[450.0],
            volumes=[1000000],
        )
        aapl_bars = make_bars_df(
            dates=["2024-01-15"],
            prices=[180.0],
            volumes=[500000],
        )
        cache.save_bars("SPY", spy_bars)
        cache.save_bars("AAPL", aapl_bars)

        symbols = cache.get_symbols()

        assert symbols == ["AAPL", "SPY"]  # Alphabetically sorted

    def test_get_symbols_empty(self, cache):
        """Test getting symbols when cache is empty."""
        symbols = cache.get_symbols()
        assert symbols == []
