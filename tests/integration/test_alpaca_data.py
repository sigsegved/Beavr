"""Integration tests for Alpaca data fetching."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from beavr.data.alpaca import AlpacaDataFetcher


@pytest.mark.slow
class TestAlpacaDataFetcher:
    """Integration tests for AlpacaDataFetcher with real API."""

    def test_fetch_single_symbol(
        self, alpaca_credentials: tuple[str, str]
    ) -> None:
        """Test fetching data for a single symbol."""
        api_key, api_secret = alpaca_credentials
        
        fetcher = AlpacaDataFetcher(
            api_key=api_key,
            api_secret=api_secret,
        )
        
        # Fetch last 5 trading days of data
        end_date = date.today()
        start_date = end_date - timedelta(days=10)  # Allow for weekends
        
        df = fetcher.get_bars("SPY", start_date, end_date)
        
        # Should have some data
        assert not df.empty
        assert "close" in df.columns
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "volume" in df.columns
        
        # Prices should be positive Decimals
        assert all(isinstance(p, Decimal) for p in df["close"])
        assert all(p > Decimal("0") for p in df["close"])

    def test_fetch_multiple_symbols(
        self, alpaca_credentials: tuple[str, str]
    ) -> None:
        """Test fetching data for multiple symbols."""
        api_key, api_secret = alpaca_credentials
        
        fetcher = AlpacaDataFetcher(
            api_key=api_key,
            api_secret=api_secret,
        )
        
        end_date = date.today()
        start_date = end_date - timedelta(days=10)
        
        bars = fetcher.get_multi_bars(
            symbols=["SPY", "QQQ"],
            start=start_date,
            end=end_date,
        )
        
        # Should have data for both symbols
        assert "SPY" in bars
        assert "QQQ" in bars
        assert not bars["SPY"].empty
        assert not bars["QQQ"].empty

    def test_fetch_historical_data(
        self, alpaca_credentials: tuple[str, str]
    ) -> None:
        """Test fetching historical data from a past period."""
        api_key, api_secret = alpaca_credentials
        
        fetcher = AlpacaDataFetcher(
            api_key=api_key,
            api_secret=api_secret,
        )
        
        # Fetch data from 2023
        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 31)
        
        df = fetcher.get_bars("SPY", start_date, end_date)
        
        # Should have about 20-21 trading days of data
        assert len(df) >= 15  # Allow some margin
        assert len(df) <= 25
