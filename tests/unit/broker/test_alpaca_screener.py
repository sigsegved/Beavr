"""Tests for AlpacaScreener adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from beavr.broker.models import BrokerError

# ===== Mock helpers =====


class MockMover:
    """Mimics an Alpaca market-mover entry."""

    def __init__(self, symbol: str, price: float, percent_change: float) -> None:
        self.symbol = symbol
        self.price = price
        self.percent_change = percent_change


class MockMoversResponse:
    """Mimics the response from ScreenerClient.get_market_movers."""

    def __init__(
        self,
        gainers: list[MockMover],
        losers: list[MockMover],
    ) -> None:
        self.gainers = gainers
        self.losers = losers


class MockActiveStock:
    """Mimics an active-stock entry."""

    def __init__(
        self,
        symbol: str,
        volume: int | None = None,
        trade_count: int | None = None,
    ) -> None:
        self.symbol = symbol
        self.volume = volume
        self.trade_count = trade_count


class MockActivesResponse:
    """Mimics the response from ScreenerClient.get_most_actives."""

    def __init__(self, most_actives: list[MockActiveStock]) -> None:
        self.most_actives = most_actives


# ===== Fixtures =====


@pytest.fixture
def mock_screener_client() -> MagicMock:
    """Create a mock ScreenerClient."""
    return MagicMock()


@pytest.fixture
def _patch_alpaca_modules() -> Any:
    """Patch all alpaca submodules so imports succeed without alpaca-py."""
    mods = {
        "alpaca": MagicMock(),
        "alpaca.data": MagicMock(),
        "alpaca.data.requests": MagicMock(),
        "alpaca.data.timeframe": MagicMock(),
    }
    with patch.dict("sys.modules", mods):
        yield


@pytest.fixture
def screener(
    _patch_alpaca_modules: Any, mock_screener_client: MagicMock
) -> Any:
    """Create an AlpacaScreener with a mocked client."""
    from beavr.broker.alpaca.screener import AlpacaScreener

    instance = AlpacaScreener.__new__(AlpacaScreener)
    instance._client = mock_screener_client
    instance._MarketMoversRequest = MagicMock()
    instance._MostActivesRequest = MagicMock()
    instance._MostActivesBy = MagicMock()
    return instance


# ===== Tests =====


class TestAlpacaScreener:
    """Tests for AlpacaScreener."""

    # ===== Init =====

    def test_init_stores_client(self, screener: Any) -> None:
        """AlpacaScreener should store a screener client."""
        assert screener._client is not None

    # ===== get_market_movers — happy path =====

    def test_get_market_movers_returns_gainers_and_losers(
        self,
        screener: Any,
        mock_screener_client: MagicMock,
    ) -> None:
        """get_market_movers should return both gainers and losers."""
        mock_screener_client.get_market_movers.return_value = MockMoversResponse(
            gainers=[
                MockMover("AAPL", 195.50, 3.2),
                MockMover("MSFT", 420.00, 2.1),
            ],
            losers=[
                MockMover("TSLA", 180.75, -4.5),
            ],
        )

        result = screener.get_market_movers(top=5)

        assert len(result) == 3
        gainers = [r for r in result if r["type"] == "gainer"]
        losers = [r for r in result if r["type"] == "loser"]
        assert len(gainers) == 2
        assert len(losers) == 1

    def test_get_market_movers_prices_are_decimal(
        self,
        screener: Any,
        mock_screener_client: MagicMock,
    ) -> None:
        """get_market_movers should return prices as Decimal, not float."""
        mock_screener_client.get_market_movers.return_value = MockMoversResponse(
            gainers=[MockMover("AAPL", 195.50, 3.2)],
            losers=[],
        )

        result = screener.get_market_movers(top=5)

        assert isinstance(result[0]["price"], Decimal)
        assert result[0]["price"] == Decimal("195.5")

    def test_get_market_movers_dict_keys(
        self,
        screener: Any,
        mock_screener_client: MagicMock,
    ) -> None:
        """get_market_movers should return dicts with expected keys."""
        mock_screener_client.get_market_movers.return_value = MockMoversResponse(
            gainers=[MockMover("SPY", 500.0, 1.5)],
            losers=[],
        )

        result = screener.get_market_movers(top=1)

        assert result[0]["symbol"] == "SPY"
        assert "price" in result[0]
        assert "percent_change" in result[0]
        assert result[0]["type"] == "gainer"

    # ===== get_market_movers — error =====

    def test_get_market_movers_error_wraps_in_broker_error(
        self,
        screener: Any,
        mock_screener_client: MagicMock,
    ) -> None:
        """get_market_movers should wrap exceptions in BrokerError."""
        mock_screener_client.get_market_movers.side_effect = RuntimeError("API down")

        with pytest.raises(BrokerError, match="Failed to get market movers"):
            screener.get_market_movers()

    # ===== get_most_actives — happy path =====

    def test_get_most_actives_returns_list_of_dicts(
        self,
        screener: Any,
        mock_screener_client: MagicMock,
    ) -> None:
        """get_most_actives should return list of dicts with symbol, volume, trade_count."""
        mock_screener_client.get_most_actives.return_value = MockActivesResponse(
            most_actives=[
                MockActiveStock("NVDA", volume=80_000_000, trade_count=500_000),
                MockActiveStock("AMD", volume=60_000_000, trade_count=400_000),
            ],
        )

        result = screener.get_most_actives(top=5)

        assert len(result) == 2
        assert result[0]["symbol"] == "NVDA"
        assert result[0]["volume"] == 80_000_000
        assert result[0]["trade_count"] == 500_000

    def test_get_most_actives_handles_none_volume(
        self,
        screener: Any,
        mock_screener_client: MagicMock,
    ) -> None:
        """get_most_actives should handle None volume/trade_count gracefully."""
        mock_screener_client.get_most_actives.return_value = MockActivesResponse(
            most_actives=[MockActiveStock("XYZ", volume=None, trade_count=None)],
        )

        result = screener.get_most_actives(top=5)

        assert result[0]["volume"] is None
        assert result[0]["trade_count"] is None

    # ===== get_most_actives — error =====

    def test_get_most_actives_error_wraps_in_broker_error(
        self,
        screener: Any,
        mock_screener_client: MagicMock,
    ) -> None:
        """get_most_actives should wrap exceptions in BrokerError."""
        mock_screener_client.get_most_actives.side_effect = RuntimeError("timeout")

        with pytest.raises(BrokerError, match="Failed to get most actives"):
            screener.get_most_actives()

    # ===== __init__ coverage =====

    def test_init_actually_calls_constructor(
        self, _patch_alpaca_modules: Any
    ) -> None:
        """Instantiating AlpacaScreener should import classes and store them."""
        from beavr.broker.alpaca.screener import AlpacaScreener

        instance = AlpacaScreener("key", "secret")
        assert instance._client is not None
        assert instance._MarketMoversRequest is not None
        assert instance._MostActivesRequest is not None
        assert instance._MostActivesBy is not None

    def test_init_import_error_when_alpaca_missing(
        self, _patch_alpaca_modules: Any
    ) -> None:
        """AlpacaScreener should raise ImportError when alpaca-py is missing."""
        import builtins

        from beavr.broker.alpaca.screener import AlpacaScreener

        original_import = builtins.__import__

        def selective_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "alpaca.data":
                raise ImportError("No module named 'alpaca.data'")
            return original_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=selective_import),
            pytest.raises(ImportError, match="alpaca-py required for screener"),
        ):
            AlpacaScreener("key", "secret")
