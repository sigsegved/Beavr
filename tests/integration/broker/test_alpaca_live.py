"""Integration tests for Alpaca broker adapters.

These tests hit the real Alpaca paper trading API and require credentials.
They are skipped unless ALPACA_API_KEY and ALPACA_API_SECRET are set.

Run with:
    pytest tests/integration/broker/test_alpaca_live.py -v --timeout=30
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

_SKIP_REASON = "ALPACA_API_KEY and ALPACA_API_SECRET required"
_has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _has_creds, reason=_SKIP_REASON),
]


@pytest.fixture(scope="module")
def alpaca_broker() -> object:
    """Create a live AlpacaBroker (paper mode)."""
    from beavr.broker.alpaca.broker import AlpacaBroker

    return AlpacaBroker(
        api_key=os.environ["ALPACA_API_KEY"],
        api_secret=os.environ["ALPACA_API_SECRET"],
        paper=True,
    )


@pytest.fixture(scope="module")
def alpaca_data() -> object:
    """Create a live AlpacaMarketData."""
    from beavr.broker.alpaca.data import AlpacaMarketData

    return AlpacaMarketData(
        api_key=os.environ["ALPACA_API_KEY"],
        api_secret=os.environ["ALPACA_API_SECRET"],
    )


class TestAlpacaBrokerLive:
    """Smoke tests for live Alpaca broker connection."""

    def test_get_account_returns_account_info(self, alpaca_broker: object) -> None:
        """get_account should return valid AccountInfo."""
        account = alpaca_broker.get_account()  # type: ignore[attr-defined]
        assert account.broker_name == "alpaca"
        assert isinstance(account.equity, Decimal)
        assert isinstance(account.buying_power, Decimal)

    def test_get_positions_returns_list(self, alpaca_broker: object) -> None:
        """get_positions should return a list (possibly empty)."""
        positions = alpaca_broker.get_positions()  # type: ignore[attr-defined]
        assert isinstance(positions, list)

    def test_get_clock(self, alpaca_broker: object) -> None:
        """get_clock should return MarketClock."""
        clock = alpaca_broker.get_clock()  # type: ignore[attr-defined]
        assert isinstance(clock.is_open, bool)


class TestAlpacaDataLive:
    """Smoke tests for live Alpaca market data."""

    def test_get_bars_returns_dataframe(self, alpaca_data: object) -> None:
        """get_bars should return a DataFrame with OHLCV columns."""
        import pandas as pd

        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=30)
        df = alpaca_data.get_bars("SPY", start=start, end=end)  # type: ignore[attr-defined]
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "close" in df.columns

    def test_get_snapshot(self, alpaca_data: object) -> None:
        """get_snapshot should return a dict with price info."""
        snap = alpaca_data.get_snapshot("AAPL")  # type: ignore[attr-defined]
        assert isinstance(snap, dict)
        assert "latest_price" in snap
