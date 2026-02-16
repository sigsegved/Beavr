"""Integration tests for Webull broker adapters.

These tests hit the real Webull API and require credentials.
They are skipped unless WEBULL_APP_KEY and WEBULL_APP_SECRET are set.

NOTE: Webull does NOT support paper trading. These tests hit the LIVE API.
Only run them with caution and with a funded account.

Run with:
    pytest tests/integration/broker/test_webull_live.py -v --timeout=30
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

_SKIP_REASON = "WEBULL_APP_KEY and WEBULL_APP_SECRET required"
_has_creds = bool(os.getenv("WEBULL_APP_KEY") and os.getenv("WEBULL_APP_SECRET"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _has_creds, reason=_SKIP_REASON),
]


@pytest.fixture(scope="module")
def webull_broker() -> object:
    """Create a live WebullBroker (live only — no paper trading support)."""
    from beavr.broker.webull.broker import WebullBroker

    return WebullBroker(
        app_key=os.environ["WEBULL_APP_KEY"],
        app_secret=os.environ["WEBULL_APP_SECRET"],
        account_id=os.getenv("WEBULL_ACCOUNT_ID"),
        region=os.getenv("WEBULL_REGION", "us"),
    )


@pytest.fixture(scope="module")
def webull_data() -> object:
    """Create a live WebullMarketData."""
    from webullsdkcore.client import ApiClient

    from beavr.broker.webull.data import WebullMarketData

    client = ApiClient(
        app_key=os.environ["WEBULL_APP_KEY"],
        app_secret=os.environ["WEBULL_APP_SECRET"],
        region_id=os.getenv("WEBULL_REGION", "us"),
    )
    return WebullMarketData(api_client=client)


class TestWebullBrokerLive:
    """Smoke tests for live Webull broker connection."""

    def test_get_account_returns_account_info(self, webull_broker: object) -> None:
        """get_account should return valid AccountInfo."""
        account = webull_broker.get_account()  # type: ignore[attr-defined]
        assert account.broker_name == "webull"
        assert isinstance(account.equity, Decimal)
        assert isinstance(account.buying_power, Decimal)

    def test_get_positions_returns_list(self, webull_broker: object) -> None:
        """get_positions should return a list (possibly empty)."""
        positions = webull_broker.get_positions()  # type: ignore[attr-defined]
        assert isinstance(positions, list)

    def test_get_clock(self, webull_broker: object) -> None:
        """get_clock should return MarketClock."""
        clock = webull_broker.get_clock()  # type: ignore[attr-defined]
        assert isinstance(clock.is_open, bool)


class TestWebullDataLive:
    """Smoke tests for live Webull market data."""

    def test_get_bars_returns_dataframe(self, webull_data: object) -> None:
        """get_bars should return a DataFrame with OHLCV columns."""
        import pandas as pd

        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=30)
        df = webull_data.get_bars("AAPL", start=start, end=end)  # type: ignore[attr-defined]
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "close" in df.columns

    def test_get_snapshot(self, webull_data: object) -> None:
        """get_snapshot should return a dict with price info."""
        snap = webull_data.get_snapshot("AAPL")  # type: ignore[attr-defined]
        assert isinstance(snap, dict)
        assert "latest_price" in snap
