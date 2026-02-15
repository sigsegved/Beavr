"""Protocol conformance test suite.

Shared parametrized tests that ANY broker adapter must pass.
Initially parametrized with MockBroker; Alpaca and Webull adapters
are added in later phases.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from beavr.broker.models import (
    AccountInfo,
    BrokerError,
    BrokerPosition,
    MarketClock,
    OrderRequest,
    OrderResult,
)
from beavr.broker.protocols import BrokerProvider, MarketDataProvider

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(params=["mock"])
def broker(request: pytest.FixtureRequest, mock_broker) -> BrokerProvider:  # type: ignore[type-arg]
    """Parametrized BrokerProvider — extend params for new adapters."""
    if request.param == "mock":
        return mock_broker
    raise ValueError(f"Unknown broker param: {request.param}")


@pytest.fixture(params=["mock"])
def data_provider(request: pytest.FixtureRequest, mock_broker) -> MarketDataProvider:  # type: ignore[type-arg]
    """Parametrized MarketDataProvider — extend params for new adapters."""
    if request.param == "mock":
        return mock_broker
    raise ValueError(f"Unknown data_provider param: {request.param}")


# ── Helpers ────────────────────────────────────────────────────────────


def _make_buy_order(symbol: str = "SPY", qty: str = "10") -> OrderRequest:
    """Create a simple market buy order."""
    return OrderRequest(
        symbol=symbol,
        side="buy",
        order_type="market",
        quantity=Decimal(qty),
    )


def _make_sell_order(symbol: str = "SPY", qty: str = "5") -> OrderRequest:
    """Create a simple market sell order."""
    return OrderRequest(
        symbol=symbol,
        side="sell",
        order_type="market",
        quantity=Decimal(qty),
    )


# ══════════════════════════════════════════════════════════════════════
# BrokerProvider conformance
# ══════════════════════════════════════════════════════════════════════


class TestBrokerProviderConformance:
    """Every BrokerProvider implementation must pass these tests."""

    # ── Properties ─────────────────────────────────────────────────────

    def test_broker_name_returns_str(self, broker: BrokerProvider) -> None:
        """broker_name should return a non-empty string."""
        name = broker.broker_name
        assert isinstance(name, str)
        assert len(name) > 0

    def test_supports_fractional_returns_bool(self, broker: BrokerProvider) -> None:
        """supports_fractional should return a bool."""
        result = broker.supports_fractional
        assert isinstance(result, bool)

    # ── Account ────────────────────────────────────────────────────────

    def test_get_account_returns_account_info(self, broker: BrokerProvider) -> None:
        """get_account should return an AccountInfo instance."""
        account = broker.get_account()
        assert isinstance(account, AccountInfo)

    def test_get_account_fields_are_decimal(self, broker: BrokerProvider) -> None:
        """All monetary fields on AccountInfo must be Decimal, never float."""
        account = broker.get_account()
        assert isinstance(account.equity, Decimal)
        assert isinstance(account.cash, Decimal)
        assert isinstance(account.buying_power, Decimal)

    # ── Positions ──────────────────────────────────────────────────────

    def test_get_positions_returns_list(self, broker: BrokerProvider) -> None:
        """get_positions should return a list of BrokerPosition."""
        positions = broker.get_positions()
        assert isinstance(positions, list)
        for pos in positions:
            assert isinstance(pos, BrokerPosition)

    def test_get_positions_empty_initially(self, broker: BrokerProvider) -> None:
        """A fresh broker should have no open positions."""
        positions = broker.get_positions()
        assert positions == []

    def test_position_fields_are_decimal(self, broker: BrokerProvider) -> None:
        """qty, market_value, avg_cost, unrealized_pl must be Decimal."""
        broker.submit_order(_make_buy_order("AAPL", "5"))
        positions = broker.get_positions()
        assert len(positions) >= 1
        pos = [p for p in positions if p.symbol == "AAPL"][0]
        assert isinstance(pos.qty, Decimal)
        assert isinstance(pos.market_value, Decimal)
        assert isinstance(pos.avg_cost, Decimal)
        assert isinstance(pos.unrealized_pl, Decimal)

    # ── Submit order ───────────────────────────────────────────────────

    def test_submit_order_returns_order_result(self, broker: BrokerProvider) -> None:
        """submit_order should return an OrderResult."""
        result = broker.submit_order(_make_buy_order())
        assert isinstance(result, OrderResult)

    def test_submit_order_fills_with_decimal_qty(self, broker: BrokerProvider) -> None:
        """filled_qty on a filled order must be Decimal."""
        result = broker.submit_order(_make_buy_order("SPY", "3"))
        assert isinstance(result.filled_qty, Decimal)
        assert result.filled_qty == Decimal("3")

    def test_submit_order_filled_avg_price_is_decimal(
        self, broker: BrokerProvider
    ) -> None:
        """filled_avg_price on a filled order must be Decimal."""
        result = broker.submit_order(_make_buy_order())
        assert result.filled_avg_price is not None
        assert isinstance(result.filled_avg_price, Decimal)

    def test_submit_order_invalid_symbol_raises_broker_error(
        self, broker: BrokerProvider
    ) -> None:
        """Submitting an order for a non-existent symbol should raise BrokerError."""
        bad_order = OrderRequest(
            symbol="ZZZZZ",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
        )
        with pytest.raises(BrokerError) as exc_info:
            broker.submit_order(bad_order)
        assert exc_info.value.error_code == "invalid_symbol"

    def test_submit_order_buy_updates_positions(
        self, broker: BrokerProvider
    ) -> None:
        """Buying should create/update a position."""
        broker.submit_order(_make_buy_order("MSFT", "2"))
        positions = broker.get_positions()
        symbols = [p.symbol for p in positions]
        assert "MSFT" in symbols

    def test_submit_order_sell_updates_positions(
        self, broker: BrokerProvider
    ) -> None:
        """Selling all shares should remove the position."""
        broker.submit_order(_make_buy_order("AAPL", "10"))
        broker.submit_order(_make_sell_order("AAPL", "10"))
        positions = broker.get_positions()
        symbols = [p.symbol for p in positions]
        assert "AAPL" not in symbols

    def test_submit_order_partial_sell_keeps_position(
        self, broker: BrokerProvider
    ) -> None:
        """Selling fewer shares than held should keep a reduced position."""
        broker.submit_order(_make_buy_order("QQQ", "10"))
        broker.submit_order(_make_sell_order("QQQ", "3"))
        positions = broker.get_positions()
        pos = [p for p in positions if p.symbol == "QQQ"][0]
        assert pos.qty == Decimal("7")

    # ── Get / cancel / list orders ─────────────────────────────────────

    def test_submit_then_get_order_round_trip(
        self, broker: BrokerProvider
    ) -> None:
        """get_order should return the same order that was submitted."""
        submitted = broker.submit_order(_make_buy_order("SPY", "1"))
        fetched = broker.get_order(submitted.order_id)
        assert fetched.order_id == submitted.order_id
        assert fetched.symbol == submitted.symbol
        assert fetched.status == submitted.status

    def test_get_order_not_found_raises_broker_error(
        self, broker: BrokerProvider
    ) -> None:
        """Getting a non-existent order should raise BrokerError."""
        with pytest.raises(BrokerError) as exc_info:
            broker.get_order("nonexistent-id-12345")
        assert exc_info.value.error_code == "order_not_found"

    def test_cancel_pending_order_succeeds(self, broker: BrokerProvider) -> None:
        """Cancelling a pending order should return status='cancelled'."""
        # Use the helper to inject a pending order
        broker.add_pending_order("pending-001", "SPY")  # type: ignore[attr-defined]
        result = broker.cancel_order("pending-001")
        assert result.status == "cancelled"

    def test_cancel_filled_order_raises_broker_error(
        self, broker: BrokerProvider
    ) -> None:
        """Cancelling an already-filled order should raise BrokerError."""
        filled = broker.submit_order(_make_buy_order("SPY", "1"))
        with pytest.raises(BrokerError) as exc_info:
            broker.cancel_order(filled.order_id)
        assert exc_info.value.error_code == "order_already_filled"

    def test_list_orders_returns_list(self, broker: BrokerProvider) -> None:
        """list_orders should return a list of OrderResult."""
        broker.submit_order(_make_buy_order("SPY", "1"))
        orders = broker.list_orders()
        assert isinstance(orders, list)
        assert len(orders) >= 1
        assert all(isinstance(o, OrderResult) for o in orders)

    def test_list_orders_status_filter(self, broker: BrokerProvider) -> None:
        """list_orders with status filter should return only matching orders."""
        broker.submit_order(_make_buy_order("SPY", "1"))
        broker.add_pending_order("pending-filter", "AAPL")  # type: ignore[attr-defined]

        filled = broker.list_orders(status="filled")
        assert all(o.status == "filled" for o in filled)

        pending = broker.list_orders(status="pending")
        assert all(o.status == "pending" for o in pending)

    def test_multiple_orders_tracked(self, broker: BrokerProvider) -> None:
        """Multiple distinct orders should each be retrievable."""
        r1 = broker.submit_order(_make_buy_order("AAPL", "1"))
        r2 = broker.submit_order(_make_buy_order("MSFT", "2"))
        assert broker.get_order(r1.order_id).symbol == "AAPL"
        assert broker.get_order(r2.order_id).symbol == "MSFT"

    # ── Market clock ───────────────────────────────────────────────────

    def test_is_market_open_returns_bool(self, broker: BrokerProvider) -> None:
        """is_market_open should return a bool."""
        result = broker.is_market_open()
        assert isinstance(result, bool)

    def test_get_clock_returns_market_clock(self, broker: BrokerProvider) -> None:
        """get_clock should return a MarketClock instance."""
        clock = broker.get_clock()
        assert isinstance(clock, MarketClock)
        assert isinstance(clock.is_open, bool)

    # ── Protocol isinstance check ──────────────────────────────────────

    def test_broker_satisfies_protocol(self, broker: BrokerProvider) -> None:
        """The broker should satisfy the runtime-checkable BrokerProvider protocol."""
        assert isinstance(broker, BrokerProvider)


# ══════════════════════════════════════════════════════════════════════
# MarketDataProvider conformance
# ══════════════════════════════════════════════════════════════════════


class TestMarketDataProviderConformance:
    """Every MarketDataProvider implementation must pass these tests."""

    # ── Properties ─────────────────────────────────────────────────────

    def test_provider_name_returns_str(
        self, data_provider: MarketDataProvider
    ) -> None:
        """provider_name should return a non-empty string."""
        name = data_provider.provider_name
        assert isinstance(name, str)
        assert len(name) > 0

    # ── get_bars ───────────────────────────────────────────────────────

    def test_get_bars_returns_dataframe(
        self, data_provider: MarketDataProvider
    ) -> None:
        """get_bars should return a pandas DataFrame."""
        today = date.today()
        start = today - timedelta(days=5)
        df = data_provider.get_bars("SPY", start, today)
        assert isinstance(df, pd.DataFrame)

    def test_get_bars_has_ohlcv_columns(
        self, data_provider: MarketDataProvider
    ) -> None:
        """get_bars DataFrame should contain open, high, low, close, volume."""
        today = date.today()
        start = today - timedelta(days=5)
        df = data_provider.get_bars("SPY", start, today)
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns, f"Missing column: {col}"

    def test_get_bars_has_datetime_index(
        self, data_provider: MarketDataProvider
    ) -> None:
        """get_bars DataFrame should have a DatetimeIndex."""
        today = date.today()
        start = today - timedelta(days=3)
        df = data_provider.get_bars("SPY", start, today)
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_get_bars_close_is_decimal(
        self, data_provider: MarketDataProvider
    ) -> None:
        """OHLC values should be Decimal, not float."""
        today = date.today()
        start = today - timedelta(days=2)
        df = data_provider.get_bars("SPY", start, today)
        assert len(df) > 0
        close_val = df["close"].iloc[0]
        assert isinstance(close_val, Decimal), (
            f"close column contains {type(close_val).__name__}, expected Decimal"
        )

    def test_get_bars_open_high_low_are_decimal(
        self, data_provider: MarketDataProvider
    ) -> None:
        """open, high, low values should be Decimal."""
        today = date.today()
        start = today - timedelta(days=2)
        df = data_provider.get_bars("AAPL", start, today)
        assert len(df) > 0
        for col in ("open", "high", "low"):
            val = df[col].iloc[0]
            assert isinstance(val, Decimal), (
                f"{col} column contains {type(val).__name__}, expected Decimal"
            )

    def test_get_bars_invalid_symbol_raises_broker_error(
        self, data_provider: MarketDataProvider
    ) -> None:
        """get_bars with a bad symbol should raise BrokerError."""
        today = date.today()
        with pytest.raises(BrokerError):
            data_provider.get_bars("INVALID_XYZ", today - timedelta(days=5), today)

    # ── get_bars_multi ─────────────────────────────────────────────────

    def test_get_bars_multi_returns_dict(
        self, data_provider: MarketDataProvider
    ) -> None:
        """get_bars_multi should return a dict keyed by symbol."""
        today = date.today()
        start = today - timedelta(days=3)
        result = data_provider.get_bars_multi(["SPY", "AAPL"], start, today)
        assert isinstance(result, dict)
        assert "SPY" in result
        assert "AAPL" in result
        assert isinstance(result["SPY"], pd.DataFrame)
        assert isinstance(result["AAPL"], pd.DataFrame)

    # ── get_snapshot ───────────────────────────────────────────────────

    def test_get_snapshot_returns_dict_with_symbol(
        self, data_provider: MarketDataProvider
    ) -> None:
        """get_snapshot should return a dict containing the requested symbol."""
        snap = data_provider.get_snapshot("SPY")
        assert isinstance(snap, dict)
        assert snap["symbol"] == "SPY"

    def test_get_snapshot_invalid_symbol_raises_broker_error(
        self, data_provider: MarketDataProvider
    ) -> None:
        """get_snapshot with a bad symbol should raise BrokerError."""
        with pytest.raises(BrokerError):
            data_provider.get_snapshot("INVALID_XYZ")

    # ── Protocol isinstance check ──────────────────────────────────────

    def test_data_provider_satisfies_protocol(
        self, data_provider: MarketDataProvider
    ) -> None:
        """Provider should satisfy the runtime-checkable MarketDataProvider protocol."""
        assert isinstance(data_provider, MarketDataProvider)
