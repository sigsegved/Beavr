"""Tests for WebullBroker adapter."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest

from beavr.broker.models import (
    AccountInfo,
    BrokerError,
    MarketClock,
    OrderRequest,
    OrderResult,
)

# ---------------------------------------------------------------------------
# Mock Webull SDK modules before importing the broker module
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

from beavr.broker.webull.broker import WebullBroker  # noqa: E402, I001


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _balance_response(
    total_asset: str = "100000",
    total_cash: str = "50000",
    cash_power: str = "60000",
) -> Dict[str, Any]:
    """Build a fake Webull account balance response."""
    return {
        "total_asset": total_asset,
        "total_market_value": "50000",
        "total_cash": total_cash,
        "account_currency_assets": [
            {
                "net_asset": total_asset,
                "cash_balance": total_cash,
                "margin_power": "80000",
                "cash_power": cash_power,
            }
        ],
    }


def _holding(
    symbol: str = "AAPL",
    instrument_id: str = "913256135",
    quantity: str = "10",
    total_cost: str = "1700.00",
    market_value: str = "1755.00",
    unrealized_pl: str = "55.00",
) -> Dict[str, Any]:
    return {
        "instrument_id": instrument_id,
        "instrument": symbol,
        "quantity": quantity,
        "total_cost": total_cost,
        "market_value": market_value,
        "unrealized_profit_loss": unrealized_pl,
    }


def _order_dict(
    client_order_id: str = "uuid-1",
    symbol: str = "AAPL",
    side: str = "BUY",
    order_type: str = "MARKET",
    status: str = "FILLED",
    filled_quantity: str = "10",
    avg_filled_price: str = "175.50",
    place_time: str = "2025-01-15T10:00:00Z",
    filled_time: str = "2025-01-15T10:00:01Z",
) -> Dict[str, Any]:
    return {
        "client_order_id": client_order_id,
        "instrument_id": "913256135",
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "status": status,
        "filled_quantity": filled_quantity,
        "avg_filled_price": avg_filled_price,
        "place_time": place_time,
        "filled_time": filled_time,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def webull_broker() -> Generator[
    tuple[WebullBroker, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock],
    None,
    None,
]:
    """Create a WebullBroker with all SDK calls mocked.

    Yields (broker, mock_api_client, mock_account, mock_order_op, mock_calendar, mock_cache).
    """
    with (
        patch(
            "beavr.broker.webull.broker.InstrumentCache"
        ) as mock_cache_cls,
    ):
        mock_api_cls = MagicMock()
        mock_api_client = MagicMock()
        mock_api_cls.return_value = mock_api_client

        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache

        # Patch ApiClient import inside __init__
        with patch.dict(
            sys.modules["webullsdkcore.client"].__dict__,
            {"ApiClient": mock_api_cls},
        ):
            # Provide the mock so the lazy import resolves for ApiClient
            _mock_webullsdkcore.client.ApiClient = mock_api_cls

            broker = WebullBroker(
                app_key="test_key",
                app_secret="test_secret",
                account_id="12345",
                paper=True,
            )

        # Set up lazy-initialised SDK mocks
        mock_account = MagicMock()
        mock_order_op = MagicMock()
        mock_calendar = MagicMock()

        broker._account_api = mock_account
        broker._order_api = mock_order_op
        broker._calendar_api = mock_calendar

        yield broker, mock_api_client, mock_account, mock_order_op, mock_calendar, mock_cache


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWebullBrokerProperties:
    """Tests for broker properties."""

    # 1
    def test_broker_name_returns_webull(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """broker_name should return 'webull'."""
        broker, *_ = webull_broker
        assert broker.broker_name == "webull"

    # 2
    def test_supports_fractional_returns_true(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """supports_fractional should return True."""
        broker, *_ = webull_broker
        assert broker.supports_fractional is True


class TestWebullBrokerInit:
    """Tests for broker initialization."""

    # 3
    def test_init_paper_sets_endpoint(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Paper mode should configure the UAT endpoint."""
        broker, mock_api_client, *_ = webull_broker
        assert broker._paper is True
        mock_api_client.add_endpoint.assert_called_once_with(
            "us", "us-openapi-alb.uat.webullbroker.com"
        )

    # 4
    def test_init_live_does_not_set_paper_endpoint(self) -> None:
        """Live mode should NOT add the paper endpoint."""
        with patch(
            "beavr.broker.webull.broker.InstrumentCache"
        ):
            _mock_webullsdkcore.client.ApiClient = MagicMock()
            mock_client = _mock_webullsdkcore.client.ApiClient.return_value
            broker = WebullBroker(
                app_key="k",
                app_secret="s",
                account_id="999",
                paper=False,
            )
            mock_client.add_endpoint.assert_not_called()
            assert broker._paper is False

    # 5
    def test_account_id_auto_discovery_success(self) -> None:
        """Should auto-discover account_id from get_app_subscriptions."""
        mock_account_inst = MagicMock()
        mock_account_inst.get_app_subscriptions.return_value = [
            {"account_id": "auto-id-123"}
        ]

        with (
            patch("beavr.broker.webull.broker.InstrumentCache"),
            patch.dict(
                sys.modules["webullsdktrade.trade.account_info"].__dict__,
                {"Account": MagicMock(return_value=mock_account_inst)},
            ),
        ):
            _mock_webullsdkcore.client.ApiClient = MagicMock()
            _mock_webullsdktrade.trade.account_info.Account = MagicMock(
                return_value=mock_account_inst
            )

            broker = WebullBroker(
                app_key="k",
                app_secret="s",
                account_id=None,
                paper=True,
            )
            assert broker._account_id == "auto-id-123"

    # 6
    def test_account_id_auto_discovery_failure_raises_broker_error(self) -> None:
        """Should raise BrokerError when no account is found."""
        mock_account_inst = MagicMock()
        mock_account_inst.get_app_subscriptions.return_value = []

        with (
            patch("beavr.broker.webull.broker.InstrumentCache"),
            patch.dict(
                sys.modules["webullsdktrade.trade.account_info"].__dict__,
                {"Account": MagicMock(return_value=mock_account_inst)},
            ),
        ):
            _mock_webullsdkcore.client.ApiClient = MagicMock()
            _mock_webullsdktrade.trade.account_info.Account = MagicMock(
                return_value=mock_account_inst
            )

            with pytest.raises(BrokerError, match="no_account_found"):
                WebullBroker(
                    app_key="k",
                    app_secret="s",
                    account_id=None,
                    paper=True,
                )


class TestGetAccount:
    """Tests for get_account."""

    # 7
    def test_get_account_maps_balance_to_account_info(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """get_account should map response to AccountInfo with Decimal values."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_balance.return_value = _balance_response()

        info = broker.get_account()

        assert isinstance(info, AccountInfo)
        assert info.equity == Decimal("100000")
        assert info.cash == Decimal("50000")
        assert isinstance(info.equity, Decimal)
        assert isinstance(info.cash, Decimal)

    # 8
    def test_get_account_buying_power_from_currency_assets(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Buying power should be extracted from account_currency_assets."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_balance.return_value = _balance_response(
            cash_power="75000"
        )

        info = broker.get_account()

        assert info.buying_power == Decimal("75000")
        assert isinstance(info.buying_power, Decimal)

    # 9
    def test_get_account_empty_response_raises_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Empty API response should raise BrokerError."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_balance.return_value = None

        with pytest.raises(BrokerError, match="empty_response"):
            broker.get_account()

    # 10
    def test_get_account_sdk_error_wraps_in_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """SDK exceptions should be wrapped in BrokerError."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_balance.side_effect = RuntimeError("timeout")

        with pytest.raises(BrokerError, match="account_error"):
            broker.get_account()

    # 11
    def test_get_account_fallback_buying_power_equals_cash(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Buying power should fall back to cash when assets list is empty."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_balance.return_value = {
            "total_asset": "100000",
            "total_cash": "50000",
            "account_currency_assets": [],
        }

        info = broker.get_account()
        assert info.buying_power == Decimal("50000")


class TestGetPositions:
    """Tests for get_positions."""

    # 12
    def test_get_positions_single_page(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Single page of positions should be returned."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_position.return_value = {
            "has_next": False,
            "holdings": [_holding("AAPL"), _holding("MSFT", instrument_id="99")],
        }

        positions = broker.get_positions()

        assert len(positions) == 2
        assert positions[0].symbol == "AAPL"
        assert positions[1].symbol == "MSFT"
        assert isinstance(positions[0].qty, Decimal)
        assert isinstance(positions[0].avg_cost, Decimal)

    # 13
    def test_get_positions_multi_page_pagination(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Multi-page responses should be auto-paginated."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_position.side_effect = [
            {
                "has_next": True,
                "holdings": [_holding("AAPL", instrument_id="1")],
            },
            {
                "has_next": False,
                "holdings": [_holding("MSFT", instrument_id="2")],
            },
        ]

        positions = broker.get_positions()

        assert len(positions) == 2
        assert mock_account.get_account_position.call_count == 2

    # 14
    def test_get_positions_empty(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Empty holdings should return empty list."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_position.return_value = {
            "has_next": False,
            "holdings": [],
        }

        positions = broker.get_positions()

        assert positions == []

    # 15
    def test_get_positions_error_wraps_in_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """SDK exceptions should be wrapped in BrokerError."""
        broker, _, mock_account, *_ = webull_broker
        mock_account.get_account_position.side_effect = RuntimeError("fail")

        with pytest.raises(BrokerError, match="positions_error"):
            broker.get_positions()

    # 16
    def test_map_holding_avg_cost_calculation(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """avg_cost should be total_cost / quantity."""
        broker, *_ = webull_broker
        pos = broker._map_holding(
            _holding(quantity="10", total_cost="1700.00")
        )
        assert pos.avg_cost == Decimal("170")

    # 17
    def test_map_holding_zero_quantity_avg_cost_zero(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """avg_cost should be 0 when quantity is 0."""
        broker, *_ = webull_broker
        pos = broker._map_holding(
            _holding(quantity="0", total_cost="0")
        )
        assert pos.avg_cost == Decimal("0")


class TestSubmitOrder:
    """Tests for submit_order."""

    def _market_buy(self, **overrides: Any) -> OrderRequest:
        defaults: Dict[str, Any] = {
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "market",
            "tif": "day",
            "quantity": Decimal("10"),
        }
        defaults.update(overrides)
        return OrderRequest(**defaults)

    # 18
    def test_submit_order_market_buy(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Market buy order should be submitted successfully."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "913256135"
        mock_order_op.place_order.return_value = {"client_order_id": "uuid-1"}

        order = self._market_buy()
        result = broker.submit_order(order)

        assert isinstance(result, OrderResult)
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.status == "submitted"
        assert result.filled_qty == Decimal("0")

    # 19
    def test_submit_order_resolves_symbol_via_instrument_cache(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Symbol should be resolved to instrument_id via the cache."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "12345"
        mock_order_op.place_order.return_value = {"client_order_id": "x"}

        broker.submit_order(self._market_buy())

        mock_cache.resolve.assert_called_once_with("AAPL")
        call_kwargs = mock_order_op.place_order.call_args[1]
        assert call_kwargs["instrument_id"] == "12345"

    # 20
    def test_submit_order_generates_client_order_id(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """A UUID client_order_id should be generated when not provided."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "1"
        mock_order_op.place_order.return_value = {}

        result = broker.submit_order(self._market_buy(client_order_id=None))

        assert result.client_order_id is not None
        assert len(result.client_order_id) > 0

    # 21
    def test_submit_order_uses_explicit_client_order_id(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Explicit client_order_id should be used when provided."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "1"
        mock_order_op.place_order.return_value = {}

        result = broker.submit_order(
            self._market_buy(client_order_id="my-custom-id")
        )

        assert result.client_order_id == "my-custom-id"
        call_kwargs = mock_order_op.place_order.call_args[1]
        assert call_kwargs["client_order_id"] == "my-custom-id"

    # 22
    def test_submit_order_limit_passes_limit_price(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Limit orders should pass limit_price to Webull."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "1"
        mock_order_op.place_order.return_value = {}

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="limit",
            tif="day",
            quantity=Decimal("5"),
            limit_price=Decimal("150.00"),
        )
        broker.submit_order(order)

        call_kwargs = mock_order_op.place_order.call_args[1]
        assert call_kwargs["limit_price"] == "150.00"
        assert call_kwargs["order_type"] == "LIMIT"

    # 23
    def test_submit_order_stop_passes_stop_price(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Stop orders should pass stop_price to Webull."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "1"
        mock_order_op.place_order.return_value = {}

        order = OrderRequest(
            symbol="AAPL",
            side="sell",
            order_type="stop",
            tif="day",
            quantity=Decimal("5"),
            stop_price=Decimal("140.00"),
        )
        broker.submit_order(order)

        call_kwargs = mock_order_op.place_order.call_args[1]
        assert call_kwargs["stop_price"] == "140.00"
        assert call_kwargs["order_type"] == "STOP_LOSS"

    # 24
    def test_submit_order_instrument_not_found_raises_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """BrokerError from instrument cache should propagate."""
        broker, _, _, _, _, mock_cache = webull_broker
        mock_cache.resolve.side_effect = BrokerError(
            error_code="instrument_not_found",
            message="Not found",
            broker_name="webull",
        )

        with pytest.raises(BrokerError, match="instrument_not_found"):
            broker.submit_order(self._market_buy())

    # 25
    def test_submit_order_sdk_error_wraps_in_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """SDK exceptions should be wrapped in BrokerError."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "1"
        mock_order_op.place_order.side_effect = RuntimeError("network")

        with pytest.raises(BrokerError, match="order_error"):
            broker.submit_order(self._market_buy())

    # 26
    def test_submit_order_sell_side_mapping(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Sell orders should map side to 'SELL'."""
        broker, _, _, mock_order_op, _, mock_cache = webull_broker
        mock_cache.resolve.return_value = "1"
        mock_order_op.place_order.return_value = {}

        broker.submit_order(self._market_buy(side="sell"))

        call_kwargs = mock_order_op.place_order.call_args[1]
        assert call_kwargs["side"] == "SELL"


class TestCancelOrder:
    """Tests for cancel_order."""

    # 27
    def test_cancel_order_success(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """cancel_order should call SDK and return updated order."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.cancel_order.return_value = {}
        mock_order_op.query_order_detail.return_value = _order_dict(
            status="CANCELLED"
        )

        result = broker.cancel_order("uuid-1")

        assert result.status == "cancelled"
        mock_order_op.cancel_order.assert_called_once_with("12345", "uuid-1")

    # 28
    def test_cancel_order_error_wraps_in_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """SDK exceptions should be wrapped in BrokerError."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.cancel_order.side_effect = RuntimeError("fail")

        with pytest.raises(BrokerError, match="cancel_error"):
            broker.cancel_order("uuid-1")


class TestGetOrder:
    """Tests for get_order."""

    # 29
    def test_get_order_maps_all_fields(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """get_order should correctly map all fields from the API response."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.query_order_detail.return_value = _order_dict()

        result = broker.get_order("uuid-1")

        assert isinstance(result, OrderResult)
        assert result.order_id == "uuid-1"
        assert result.client_order_id == "uuid-1"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.order_type == "market"
        assert result.status == "filled"
        assert result.filled_qty == Decimal("10")
        assert result.filled_avg_price == Decimal("175.50")
        assert result.submitted_at is not None
        assert result.filled_at is not None

    # 30
    def test_get_order_not_found_raises_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Empty response should raise BrokerError with order_not_found."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.query_order_detail.return_value = None

        with pytest.raises(BrokerError, match="order_not_found"):
            broker.get_order("missing-id")

    # 31
    def test_get_order_error_wraps_in_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """SDK exceptions should be wrapped in BrokerError."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.query_order_detail.side_effect = RuntimeError("boom")

        with pytest.raises(BrokerError, match="order_error"):
            broker.get_order("uuid-1")


class TestListOrders:
    """Tests for list_orders."""

    # 32
    def test_list_orders_returns_paginated_results(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """list_orders should return all orders from paginated responses."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.list_today_orders.side_effect = [
            {
                "has_next": True,
                "orders": [_order_dict(client_order_id="o1")],
            },
            {
                "has_next": False,
                "orders": [_order_dict(client_order_id="o2")],
            },
        ]

        orders = broker.list_orders()

        assert len(orders) == 2
        assert orders[0].order_id == "o1"
        assert orders[1].order_id == "o2"

    # 33
    def test_list_orders_status_filter(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """list_orders should filter by status."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.list_today_orders.return_value = {
            "has_next": False,
            "orders": [
                _order_dict(client_order_id="o1", status="FILLED"),
                _order_dict(client_order_id="o2", status="CANCELLED"),
            ],
        }

        orders = broker.list_orders(status="filled")

        assert len(orders) == 1
        assert orders[0].status == "filled"

    # 34
    def test_list_orders_error_wraps_in_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """SDK exceptions should be wrapped in BrokerError."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.list_today_orders.side_effect = RuntimeError("fail")

        with pytest.raises(BrokerError, match="list_orders_error"):
            broker.list_orders()

    # 35
    def test_list_orders_respects_limit(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """list_orders should truncate results to requested limit."""
        broker, _, _, mock_order_op, _, _ = webull_broker
        mock_order_op.list_today_orders.return_value = {
            "has_next": False,
            "orders": [
                _order_dict(client_order_id=f"o{i}") for i in range(5)
            ],
        }

        orders = broker.list_orders(limit=2)

        assert len(orders) == 2


class TestMapOrder:
    """Tests for _map_order helper."""

    # 36
    def test_map_order_status_mapping(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Status values should be correctly normalised."""
        broker, *_ = webull_broker

        for webull_status, expected in [
            ("SUBMITTED", "submitted"),
            ("CANCELLED", "cancelled"),
            ("FAILED", "failed"),
            ("FILLED", "filled"),
            ("PARTIAL_FILLED", "partially_filled"),
        ]:
            result = broker._map_order(_order_dict(status=webull_status))
            assert result.status == expected

    # 37
    def test_map_order_type_mapping(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Order types should be correctly normalised."""
        broker, *_ = webull_broker

        for webull_type, expected in [
            ("MARKET", "market"),
            ("LIMIT", "limit"),
            ("STOP_LOSS", "stop"),
            ("STOP_LOSS_LIMIT", "stop_limit"),
        ]:
            result = broker._map_order(_order_dict(order_type=webull_type))
            assert result.order_type == expected

    # 38
    def test_map_order_no_fill_price(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Missing fill price should map to None."""
        broker, *_ = webull_broker
        raw = _order_dict()
        del raw["avg_filled_price"]

        result = broker._map_order(raw)
        assert result.filled_avg_price is None

    # 39
    def test_map_order_decimal_types(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Monetary fields should be Decimal, never float."""
        broker, *_ = webull_broker
        result = broker._map_order(_order_dict())

        assert isinstance(result.filled_qty, Decimal)
        assert isinstance(result.filled_avg_price, Decimal)


class TestMarketClock:
    """Tests for is_market_open and get_clock."""

    # 40
    def test_is_market_open_returns_bool(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """is_market_open should return a boolean."""
        broker, _, _, _, mock_calendar, _ = webull_broker
        today = date.today().isoformat()
        mock_calendar.get_trade_calendar.return_value = [
            {"date": today, "status": "TRADING"},
        ]

        result = broker.is_market_open()
        assert isinstance(result, bool)

    # 41
    def test_get_clock_returns_market_clock(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """get_clock should return a MarketClock instance."""
        broker, _, _, _, mock_calendar, _ = webull_broker
        today = date.today().isoformat()
        mock_calendar.get_trade_calendar.return_value = [
            {"date": today, "status": "TRADING"},
        ]

        clock = broker.get_clock()

        assert isinstance(clock, MarketClock)
        assert isinstance(clock.is_open, bool)
        assert isinstance(clock.next_open, datetime)
        assert isinstance(clock.next_close, datetime)

    # 42
    def test_get_clock_non_trading_day(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Non-trading day should set is_open=False and find next trading day."""
        broker, _, _, _, mock_calendar, _ = webull_broker
        today = date.today()
        tomorrow = today + timedelta(days=1)
        mock_calendar.get_trade_calendar.return_value = [
            {"date": today.isoformat(), "status": "CLOSED"},
            {"date": tomorrow.isoformat(), "status": "TRADING"},
        ]

        clock = broker.get_clock()

        assert clock.is_open is False

    # 43
    def test_get_clock_error_wraps_in_broker_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """SDK exceptions should be wrapped in BrokerError."""
        broker, _, _, _, mock_calendar, _ = webull_broker
        mock_calendar.get_trade_calendar.side_effect = RuntimeError("fail")

        with pytest.raises(BrokerError, match="clock_error"):
            broker.get_clock()

    # 44
    def test_is_market_open_returns_false_on_error(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """is_market_open should return False when clock fails."""
        broker, _, _, _, mock_calendar, _ = webull_broker
        mock_calendar.get_trade_calendar.side_effect = RuntimeError("fail")

        assert broker.is_market_open() is False

    # 45
    def test_get_clock_empty_calendar_response(
        self, webull_broker: tuple[WebullBroker, Any, Any, Any, Any, Any]
    ) -> None:
        """Empty calendar response should return fallback clock values."""
        broker, _, _, _, mock_calendar, _ = webull_broker
        mock_calendar.get_trade_calendar.return_value = []

        clock = broker.get_clock()

        assert isinstance(clock, MarketClock)
        assert clock.is_open is False
