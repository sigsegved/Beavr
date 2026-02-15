"""Tests for AlpacaBroker adapter."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from beavr.broker.alpaca.broker import AlpacaBroker
from beavr.broker.models import (
    AccountInfo,
    BrokerError,
    BrokerPosition,
    MarketClock,
    OrderRequest,
    OrderResult,
)

# ===== Mock Alpaca SDK objects =====


class MockAlpacaAccount:
    """Mimics an Alpaca Account object."""

    def __init__(
        self,
        equity: str = "100000.00",
        cash: str = "50000.00",
        buying_power: str = "100000.00",
    ) -> None:
        self.equity = equity
        self.cash = cash
        self.buying_power = buying_power


class MockAlpacaPosition:
    """Mimics an Alpaca Position object."""

    def __init__(
        self,
        symbol: str = "AAPL",
        qty: str = "10",
        market_value: str = "1755.00",
        avg_entry_price: str = "170.00",
        unrealized_pl: str = "55.00",
        side: str = "long",
    ) -> None:
        self.symbol = symbol
        self.qty = qty
        self.market_value = market_value
        self.avg_entry_price = avg_entry_price
        self.unrealized_pl = unrealized_pl
        self.side = side


class MockAlpacaOrder:
    """Mimics an Alpaca Order object."""

    def __init__(
        self,
        order_id: str = "test-order-123",
        client_order_id: str | None = None,
        symbol: str = "AAPL",
        side: str = "buy",
        order_type: str = "market",
        status: str = "filled",
        qty: str = "10",
        filled_qty: str = "10",
        filled_avg_price: str | None = "175.50",
        submitted_at: datetime | None = None,
        filled_at: datetime | None = None,
    ) -> None:
        self.id = order_id
        self.client_order_id = client_order_id
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.status = status
        self.qty = qty
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price
        self.submitted_at = submitted_at or datetime(2025, 1, 15, 10, 0, 0)
        self.filled_at = filled_at or datetime(2025, 1, 15, 10, 0, 1)


class MockAlpacaClock:
    """Mimics an Alpaca Clock object."""

    def __init__(self, is_open: bool = True) -> None:
        self.is_open = is_open
        self.next_open = datetime(2025, 1, 16, 9, 30, 0)
        self.next_close = datetime(2025, 1, 15, 16, 0, 0)


# ===== Fixtures =====


@pytest.fixture
def alpaca_broker() -> tuple[AlpacaBroker, MagicMock]:
    """Create an AlpacaBroker with a mocked TradingClient."""
    with patch("alpaca.trading.client.TradingClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        broker = AlpacaBroker(api_key="test-key", api_secret="test-secret", paper=True)
        yield broker, mock_client  # type: ignore[misc]


# ===== Tests =====


class TestAlpacaBrokerProperties:
    """Tests for broker properties."""

    def test_broker_name_returns_alpaca(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """broker_name should return 'alpaca'."""
        broker, _ = alpaca_broker
        assert broker.broker_name == "alpaca"

    def test_supports_fractional_returns_true(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """supports_fractional should return True for Alpaca."""
        broker, _ = alpaca_broker
        assert broker.supports_fractional is True


class TestAlpacaBrokerGetAccount:
    """Tests for get_account method."""

    def test_get_account_maps_all_fields_to_decimal(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_account should convert all monetary values to Decimal."""
        broker, mock_client = alpaca_broker
        mock_client.get_account.return_value = MockAlpacaAccount(
            equity="123456.78", cash="50000.50", buying_power="99000.25"
        )

        result = broker.get_account()

        assert isinstance(result, AccountInfo)
        assert result.equity == Decimal("123456.78")
        assert result.cash == Decimal("50000.50")
        assert result.buying_power == Decimal("99000.25")
        assert result.currency == "USD"

    def test_get_account_error_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_account should wrap SDK errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.get_account.side_effect = RuntimeError("API timeout")

        with pytest.raises(BrokerError, match="Failed to get account") as exc_info:
            broker.get_account()

        assert exc_info.value.error_code == "account_error"
        assert exc_info.value.broker_name == "alpaca"


class TestAlpacaBrokerGetPositions:
    """Tests for get_positions method."""

    def test_get_positions_maps_all_fields_correctly(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_positions should convert Alpaca positions to BrokerPosition."""
        broker, mock_client = alpaca_broker
        mock_client.get_all_positions.return_value = [
            MockAlpacaPosition(
                symbol="AAPL",
                qty="10",
                market_value="1755.00",
                avg_entry_price="170.00",
                unrealized_pl="55.00",
                side="long",
            ),
            MockAlpacaPosition(
                symbol="TSLA",
                qty="5",
                market_value="1250.00",
                avg_entry_price="240.00",
                unrealized_pl="10.00",
                side="long",
            ),
        ]

        result = broker.get_positions()

        assert len(result) == 2
        aapl = result[0]
        assert isinstance(aapl, BrokerPosition)
        assert aapl.symbol == "AAPL"
        assert aapl.qty == Decimal("10")
        assert aapl.market_value == Decimal("1755.00")
        assert aapl.avg_cost == Decimal("170.00")
        assert aapl.unrealized_pl == Decimal("55.00")
        assert aapl.side == "long"

    def test_get_positions_handles_empty_positions(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_positions should return empty list when no positions."""
        broker, mock_client = alpaca_broker
        mock_client.get_all_positions.return_value = []

        result = broker.get_positions()

        assert result == []

    def test_get_positions_handles_short_side(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_positions should correctly map short positions."""
        broker, mock_client = alpaca_broker
        mock_client.get_all_positions.return_value = [
            MockAlpacaPosition(side="short"),
        ]

        result = broker.get_positions()

        assert result[0].side == "short"

    def test_get_positions_defaults_unknown_side_to_long(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_positions should default to 'long' for unknown side values."""
        broker, mock_client = alpaca_broker
        mock_client.get_all_positions.return_value = [
            MockAlpacaPosition(side="UNKNOWN_ENUM"),
        ]

        result = broker.get_positions()

        assert result[0].side == "long"

    def test_get_positions_error_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_positions should wrap SDK errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.get_all_positions.side_effect = RuntimeError("Connection refused")

        with pytest.raises(BrokerError, match="Failed to get positions") as exc_info:
            broker.get_positions()

        assert exc_info.value.error_code == "positions_error"
        assert exc_info.value.broker_name == "alpaca"


class TestAlpacaBrokerSubmitOrder:
    """Tests for submit_order method."""

    def test_submit_market_order_with_qty(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should create a MarketOrderRequest with qty."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder()

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
        )
        result = broker.submit_order(order)

        assert isinstance(result, OrderResult)
        assert result.order_id == "test-order-123"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        mock_client.submit_order.assert_called_once()

    def test_submit_market_order_with_notional(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should create a MarketOrderRequest with notional."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder(
            filled_avg_price="175.50",
        )

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            notional=Decimal("1000.00"),
        )
        result = broker.submit_order(order)

        assert isinstance(result, OrderResult)
        # Verify the SDK was called with notional, not qty
        call_args = mock_client.submit_order.call_args
        sdk_request = call_args[0][0]
        assert hasattr(sdk_request, "notional")

    def test_submit_limit_order(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should create a LimitOrderRequest."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder(
            order_type="limit", status="new", filled_qty="0", filled_avg_price=None
        )

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="limit",
            quantity=Decimal("10"),
            limit_price=Decimal("170.00"),
        )
        result = broker.submit_order(order)

        assert isinstance(result, OrderResult)
        assert result.order_type == "limit"
        mock_client.submit_order.assert_called_once()

    def test_submit_stop_order(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should create a StopOrderRequest."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder(
            order_type="stop", side="sell", status="new", filled_qty="0", filled_avg_price=None
        )

        order = OrderRequest(
            symbol="AAPL",
            side="sell",
            order_type="stop",
            quantity=Decimal("10"),
            stop_price=Decimal("160.00"),
        )
        result = broker.submit_order(order)

        assert isinstance(result, OrderResult)
        assert result.side == "sell"
        mock_client.submit_order.assert_called_once()

    def test_submit_stop_limit_order(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should create a StopLimitOrderRequest."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder(
            order_type="stop_limit",
            status="new",
            filled_qty="0",
            filled_avg_price=None,
        )

        order = OrderRequest(
            symbol="AAPL",
            side="sell",
            order_type="stop_limit",
            quantity=Decimal("10"),
            limit_price=Decimal("158.00"),
            stop_price=Decimal("160.00"),
        )
        result = broker.submit_order(order)

        assert isinstance(result, OrderResult)
        mock_client.submit_order.assert_called_once()

    def test_submit_order_with_client_order_id(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should pass through client_order_id."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder(
            client_order_id="my-custom-id-123",
        )

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("5"),
            client_order_id="my-custom-id-123",
        )
        result = broker.submit_order(order)

        assert result.client_order_id == "my-custom-id-123"

    def test_submit_order_with_gtc_tif(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should map time-in-force correctly."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder()

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
            tif="gtc",
        )
        broker.submit_order(order)

        call_args = mock_client.submit_order.call_args
        sdk_request = call_args[0][0]
        # Verify TIF was set (the actual enum value depends on SDK)
        assert sdk_request.time_in_force is not None

    def test_submit_order_error_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should wrap SDK errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.side_effect = RuntimeError("Insufficient funds")

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
        )

        with pytest.raises(BrokerError, match="Failed to submit order") as exc_info:
            broker.submit_order(order)

        assert exc_info.value.error_code == "order_error"
        assert exc_info.value.broker_name == "alpaca"

    def test_submit_order_maps_filled_result_correctly(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """submit_order should correctly map filled order fields."""
        broker, mock_client = alpaca_broker
        submitted = datetime(2025, 1, 15, 10, 0, 0)
        filled = datetime(2025, 1, 15, 10, 0, 1)
        mock_client.submit_order.return_value = MockAlpacaOrder(
            order_id="order-456",
            symbol="MSFT",
            side="sell",
            order_type="market",
            status="filled",
            filled_qty="25",
            filled_avg_price="410.25",
            submitted_at=submitted,
            filled_at=filled,
        )

        order = OrderRequest(
            symbol="MSFT",
            side="sell",
            order_type="market",
            quantity=Decimal("25"),
        )
        result = broker.submit_order(order)

        assert result.order_id == "order-456"
        assert result.symbol == "MSFT"
        assert result.side == "sell"
        assert result.order_type == "market"
        assert result.status == "filled"
        assert result.filled_qty == Decimal("25")
        assert result.filled_avg_price == Decimal("410.25")
        assert result.submitted_at == submitted
        assert result.filled_at == filled


class TestAlpacaBrokerCancelOrder:
    """Tests for cancel_order method."""

    def test_cancel_order_success(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """cancel_order should cancel and return the updated order."""
        broker, mock_client = alpaca_broker
        mock_client.cancel_order_by_id.return_value = None
        mock_client.get_order_by_id.return_value = MockAlpacaOrder(
            status="canceled", filled_qty="0", filled_avg_price=None
        )

        result = broker.cancel_order("test-order-123")

        assert isinstance(result, OrderResult)
        assert result.status == "canceled"
        mock_client.cancel_order_by_id.assert_called_once_with("test-order-123")

    def test_cancel_order_error_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """cancel_order should wrap SDK errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.cancel_order_by_id.side_effect = RuntimeError("Order not found")

        with pytest.raises(BrokerError, match="Failed to cancel order") as exc_info:
            broker.cancel_order("nonexistent-id")

        assert exc_info.value.error_code == "cancel_error"
        assert exc_info.value.broker_name == "alpaca"


class TestAlpacaBrokerGetOrder:
    """Tests for get_order method."""

    def test_get_order_success(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_order should return the mapped OrderResult."""
        broker, mock_client = alpaca_broker
        mock_client.get_order_by_id.return_value = MockAlpacaOrder(
            order_id="order-789",
            symbol="GOOG",
            side="buy",
            status="filled",
            filled_qty="3",
            filled_avg_price="140.00",
        )

        result = broker.get_order("order-789")

        assert isinstance(result, OrderResult)
        assert result.order_id == "order-789"
        assert result.symbol == "GOOG"
        assert result.filled_qty == Decimal("3")
        assert result.filled_avg_price == Decimal("140.00")

    def test_get_order_not_found_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_order should wrap not-found errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.get_order_by_id.side_effect = RuntimeError("404 Not Found")

        with pytest.raises(BrokerError, match="Failed to get order") as exc_info:
            broker.get_order("nonexistent")

        assert exc_info.value.error_code == "order_not_found"
        assert exc_info.value.broker_name == "alpaca"


class TestAlpacaBrokerListOrders:
    """Tests for list_orders method."""

    def test_list_orders_success(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """list_orders should return a list of mapped OrderResults."""
        broker, mock_client = alpaca_broker
        mock_client.get_orders.return_value = [
            MockAlpacaOrder(order_id="o1", symbol="AAPL"),
            MockAlpacaOrder(order_id="o2", symbol="TSLA"),
        ]

        result = broker.list_orders()

        assert len(result) == 2
        assert result[0].order_id == "o1"
        assert result[1].order_id == "o2"
        mock_client.get_orders.assert_called_once()

    def test_list_orders_with_status_filter(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """list_orders should pass status filter to SDK."""
        broker, mock_client = alpaca_broker
        mock_client.get_orders.return_value = [
            MockAlpacaOrder(status="open", filled_qty="0", filled_avg_price=None),
        ]

        result = broker.list_orders(status="open")

        assert len(result) == 1
        call_args = mock_client.get_orders.call_args
        sdk_params = call_args[0][0]
        assert sdk_params.status == "open"

    def test_list_orders_empty(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """list_orders should return empty list when no orders."""
        broker, mock_client = alpaca_broker
        mock_client.get_orders.return_value = []

        result = broker.list_orders()

        assert result == []

    def test_list_orders_error_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """list_orders should wrap SDK errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.get_orders.side_effect = RuntimeError("Server error")

        with pytest.raises(BrokerError, match="Failed to list orders") as exc_info:
            broker.list_orders()

        assert exc_info.value.error_code == "list_orders_error"


class TestAlpacaBrokerMarketClock:
    """Tests for is_market_open and get_clock methods."""

    def test_is_market_open_returns_true_when_open(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """is_market_open should return True when market is open."""
        broker, mock_client = alpaca_broker
        mock_client.get_clock.return_value = MockAlpacaClock(is_open=True)

        assert broker.is_market_open() is True

    def test_is_market_open_returns_false_when_closed(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """is_market_open should return False when market is closed."""
        broker, mock_client = alpaca_broker
        mock_client.get_clock.return_value = MockAlpacaClock(is_open=False)

        assert broker.is_market_open() is False

    def test_get_clock_maps_correctly(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_clock should map Alpaca clock to MarketClock."""
        broker, mock_client = alpaca_broker
        mock_client.get_clock.return_value = MockAlpacaClock(is_open=True)

        result = broker.get_clock()

        assert isinstance(result, MarketClock)
        assert result.is_open is True
        assert result.next_open == datetime(2025, 1, 16, 9, 30, 0)
        assert result.next_close == datetime(2025, 1, 15, 16, 0, 0)

    def test_get_clock_error_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """get_clock should wrap SDK errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.get_clock.side_effect = RuntimeError("Clock unavailable")

        with pytest.raises(BrokerError, match="Failed to get market clock") as exc_info:
            broker.get_clock()

        assert exc_info.value.error_code == "clock_error"
        assert exc_info.value.broker_name == "alpaca"

    def test_is_market_open_error_wraps_in_broker_error(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """is_market_open should wrap SDK errors in BrokerError."""
        broker, mock_client = alpaca_broker
        mock_client.get_clock.side_effect = RuntimeError("Network error")

        with pytest.raises(BrokerError, match="Failed to check market status"):
            broker.is_market_open()


class TestAlpacaBrokerOrderMapping:
    """Tests for _map_order edge cases."""

    def test_map_order_handles_none_filled_avg_price(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """_map_order should set filled_avg_price to None when not filled."""
        broker, mock_client = alpaca_broker
        mock_client.submit_order.return_value = MockAlpacaOrder(
            status="new", filled_qty="0", filled_avg_price=None
        )

        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
        )
        result = broker.submit_order(order)

        assert result.filled_qty == Decimal("0")
        assert result.filled_avg_price is None

    def test_map_order_handles_sell_side(
        self, alpaca_broker: tuple[AlpacaBroker, MagicMock]
    ) -> None:
        """_map_order should correctly map 'sell' side."""
        broker, mock_client = alpaca_broker
        mock_client.get_order_by_id.return_value = MockAlpacaOrder(side="sell")

        result = broker.get_order("order-123")

        assert result.side == "sell"
