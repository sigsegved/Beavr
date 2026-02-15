"""Tests for broker domain models."""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from beavr.broker.models import (
    AccountInfo,
    BrokerError,
    BrokerPosition,
    MarketClock,
    OrderRequest,
    OrderResult,
)

# ---- Shared fixtures --------------------------------------------------------

_NOW = datetime(2026, 2, 15, 10, 0, 0)
_LATER = datetime(2026, 2, 15, 16, 0, 0)


class TestAccountInfo:
    """Tests for AccountInfo."""

    @pytest.fixture
    def account(self) -> AccountInfo:
        """Create a default AccountInfo."""
        return AccountInfo(
            equity=Decimal("50000.00"),
            cash=Decimal("25000.00"),
            buying_power=Decimal("100000.00"),
        )

    # ===== Happy Path =====

    def test_create_with_defaults(self, account: AccountInfo) -> None:
        """AccountInfo should be created with default currency USD."""
        assert account.equity == Decimal("50000.00")
        assert account.cash == Decimal("25000.00")
        assert account.buying_power == Decimal("100000.00")
        assert account.currency == "USD"

    def test_create_with_explicit_currency(self) -> None:
        """AccountInfo should accept an explicit currency."""
        info = AccountInfo(
            equity=Decimal("1000"),
            cash=Decimal("500"),
            buying_power=Decimal("2000"),
            currency="EUR",
        )
        assert info.currency == "EUR"

    def test_serialization_roundtrip(self, account: AccountInfo) -> None:
        """model_dump → model_validate should produce an equal instance."""
        data = account.model_dump()
        restored = AccountInfo.model_validate(data)
        assert restored == account

    # ===== Immutability =====

    def test_frozen_raises_on_assignment(self, account: AccountInfo) -> None:
        """Assigning to a field on a frozen model must raise."""
        with pytest.raises(ValidationError):
            account.equity = Decimal("999")  # type: ignore[misc]

    # ===== Error Cases =====

    def test_missing_required_field_raises(self) -> None:
        """Omitting a required field must raise ValidationError."""
        with pytest.raises(ValidationError):
            AccountInfo(equity=Decimal("100"), cash=Decimal("50"))  # type: ignore[call-arg]


class TestBrokerPosition:
    """Tests for BrokerPosition."""

    @pytest.fixture
    def position(self) -> BrokerPosition:
        """Create a default long position."""
        return BrokerPosition(
            symbol="AAPL",
            qty=Decimal("10"),
            market_value=Decimal("1500.00"),
            avg_cost=Decimal("140.00"),
            unrealized_pl=Decimal("100.00"),
            side="long",
        )

    # ===== Happy Path =====

    def test_create_long_position(self, position: BrokerPosition) -> None:
        """BrokerPosition should store all fields correctly."""
        assert position.symbol == "AAPL"
        assert position.qty == Decimal("10")
        assert position.market_value == Decimal("1500.00")
        assert position.avg_cost == Decimal("140.00")
        assert position.unrealized_pl == Decimal("100.00")
        assert position.side == "long"

    def test_create_short_position(self) -> None:
        """BrokerPosition should accept side='short'."""
        pos = BrokerPosition(
            symbol="TSLA",
            qty=Decimal("5"),
            market_value=Decimal("900.00"),
            avg_cost=Decimal("200.00"),
            unrealized_pl=Decimal("-100.00"),
            side="short",
        )
        assert pos.side == "short"

    def test_serialization_roundtrip(self, position: BrokerPosition) -> None:
        """model_dump → model_validate should produce an equal instance."""
        data = position.model_dump()
        restored = BrokerPosition.model_validate(data)
        assert restored == position

    # ===== Immutability =====

    def test_frozen_raises_on_assignment(self, position: BrokerPosition) -> None:
        """Assigning to a field on a frozen model must raise."""
        with pytest.raises(ValidationError):
            position.symbol = "GOOG"  # type: ignore[misc]

    # ===== Edge Cases =====

    def test_zero_quantity(self) -> None:
        """Position with zero quantity should still be valid."""
        pos = BrokerPosition(
            symbol="SPY",
            qty=Decimal("0"),
            market_value=Decimal("0"),
            avg_cost=Decimal("0"),
            unrealized_pl=Decimal("0"),
            side="long",
        )
        assert pos.qty == Decimal("0")

    # ===== Error Cases =====

    def test_invalid_side_raises(self) -> None:
        """An invalid side literal must raise ValidationError."""
        with pytest.raises(ValidationError):
            BrokerPosition(
                symbol="SPY",
                qty=Decimal("1"),
                market_value=Decimal("100"),
                avg_cost=Decimal("100"),
                unrealized_pl=Decimal("0"),
                side="neutral",  # type: ignore[arg-type]
            )


class TestOrderRequest:
    """Tests for OrderRequest."""

    # ===== Happy Path =====

    def test_market_buy_with_quantity(self) -> None:
        """Market buy with quantity should be valid."""
        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
        )
        assert order.quantity == Decimal("10")
        assert order.notional is None
        assert order.tif == "day"

    def test_market_buy_with_notional(self) -> None:
        """Market buy with notional should be valid."""
        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            notional=Decimal("5000.00"),
        )
        assert order.notional == Decimal("5000.00")
        assert order.quantity is None

    def test_limit_order_with_limit_price(self) -> None:
        """Limit order with limit_price should be valid."""
        order = OrderRequest(
            symbol="MSFT",
            side="sell",
            order_type="limit",
            quantity=Decimal("5"),
            limit_price=Decimal("350.00"),
        )
        assert order.limit_price == Decimal("350.00")

    def test_stop_order_with_stop_price(self) -> None:
        """Stop order with stop_price should be valid."""
        order = OrderRequest(
            symbol="TSLA",
            side="sell",
            order_type="stop",
            quantity=Decimal("2"),
            stop_price=Decimal("200.00"),
        )
        assert order.stop_price == Decimal("200.00")

    def test_stop_limit_order_with_both_prices(self) -> None:
        """Stop-limit order requires both limit_price and stop_price."""
        order = OrderRequest(
            symbol="AMZN",
            side="buy",
            order_type="stop_limit",
            quantity=Decimal("3"),
            limit_price=Decimal("180.00"),
            stop_price=Decimal("175.00"),
        )
        assert order.limit_price == Decimal("180.00")
        assert order.stop_price == Decimal("175.00")

    def test_client_order_id(self) -> None:
        """client_order_id should persist."""
        order = OrderRequest(
            symbol="SPY",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
            client_order_id="my-id-123",
        )
        assert order.client_order_id == "my-id-123"

    def test_serialization_roundtrip(self) -> None:
        """model_dump → model_validate should produce an equal instance."""
        order = OrderRequest(
            symbol="GOOG",
            side="buy",
            order_type="market",
            quantity=Decimal("7"),
            tif="gtc",
        )
        data = order.model_dump()
        restored = OrderRequest.model_validate(data)
        assert restored == order

    # ===== Immutability =====

    def test_frozen_raises_on_assignment(self) -> None:
        """Assigning to a field on a frozen model must raise."""
        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
        )
        with pytest.raises(ValidationError):
            order.symbol = "TSLA"  # type: ignore[misc]

    # ===== Validation Errors =====

    def test_neither_quantity_nor_notional_raises(self) -> None:
        """Omitting both quantity and notional must raise."""
        with pytest.raises(ValidationError, match="quantity.*notional"):
            OrderRequest(
                symbol="AAPL",
                side="buy",
                order_type="market",
            )

    def test_both_quantity_and_notional_raises(self) -> None:
        """Providing both quantity and notional must raise."""
        with pytest.raises(ValidationError, match="quantity.*notional"):
            OrderRequest(
                symbol="AAPL",
                side="buy",
                order_type="market",
                quantity=Decimal("10"),
                notional=Decimal("5000"),
            )

    def test_limit_order_without_limit_price_raises(self) -> None:
        """Limit order without limit_price must raise."""
        with pytest.raises(ValidationError, match="limit_price.*required"):
            OrderRequest(
                symbol="AAPL",
                side="buy",
                order_type="limit",
                quantity=Decimal("10"),
            )

    def test_stop_order_without_stop_price_raises(self) -> None:
        """Stop order without stop_price must raise."""
        with pytest.raises(ValidationError, match="stop_price.*required"):
            OrderRequest(
                symbol="AAPL",
                side="sell",
                order_type="stop",
                quantity=Decimal("5"),
            )

    def test_stop_limit_without_limit_price_raises(self) -> None:
        """Stop-limit order without limit_price must raise."""
        with pytest.raises(ValidationError, match="limit_price.*required"):
            OrderRequest(
                symbol="SPY",
                side="buy",
                order_type="stop_limit",
                quantity=Decimal("1"),
                stop_price=Decimal("400.00"),
            )

    def test_stop_limit_without_stop_price_raises(self) -> None:
        """Stop-limit order without stop_price must raise."""
        with pytest.raises(ValidationError, match="stop_price.*required"):
            OrderRequest(
                symbol="SPY",
                side="buy",
                order_type="stop_limit",
                quantity=Decimal("1"),
                limit_price=Decimal("410.00"),
            )

    def test_invalid_side_raises(self) -> None:
        """Invalid side literal must raise ValidationError."""
        with pytest.raises(ValidationError):
            OrderRequest(
                symbol="AAPL",
                side="hold",  # type: ignore[arg-type]
                order_type="market",
                quantity=Decimal("1"),
            )

    # ===== Edge Cases =====

    def test_empty_symbol_accepted(self) -> None:
        """Empty string symbol is structurally valid (broker rejects later)."""
        order = OrderRequest(
            symbol="",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
        )
        assert order.symbol == ""


class TestOrderResult:
    """Tests for OrderResult."""

    @pytest.fixture
    def result(self) -> OrderResult:
        """Create a filled order result."""
        return OrderResult(
            order_id="broker-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            status="filled",
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.25"),
            submitted_at=_NOW,
            filled_at=_LATER,
        )

    # ===== Happy Path =====

    def test_create_filled_result(self, result: OrderResult) -> None:
        """OrderResult should store all fields correctly."""
        assert result.order_id == "broker-123"
        assert result.client_order_id == "client-456"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.order_type == "market"
        assert result.status == "filled"
        assert result.filled_qty == Decimal("10")
        assert result.filled_avg_price == Decimal("150.25")
        assert result.submitted_at == _NOW
        assert result.filled_at == _LATER

    def test_create_partial_fill(self) -> None:
        """OrderResult with partial fill and no filled_at should be valid."""
        res = OrderResult(
            order_id="o-789",
            symbol="TSLA",
            side="sell",
            order_type="limit",
            status="partially_filled",
            filled_qty=Decimal("3"),
            filled_avg_price=Decimal("210.00"),
            submitted_at=_NOW,
        )
        assert res.filled_at is None
        assert res.client_order_id is None

    def test_serialization_roundtrip(self, result: OrderResult) -> None:
        """model_dump → model_validate should produce an equal instance."""
        data = result.model_dump()
        restored = OrderResult.model_validate(data)
        assert restored == result

    # ===== Immutability =====

    def test_frozen_raises_on_assignment(self, result: OrderResult) -> None:
        """Assigning to a field on a frozen model must raise."""
        with pytest.raises(ValidationError):
            result.status = "cancelled"  # type: ignore[misc]


class TestMarketClock:
    """Tests for MarketClock."""

    @pytest.fixture
    def clock(self) -> MarketClock:
        """Create a MarketClock instance."""
        return MarketClock(
            is_open=True,
            next_open=_NOW,
            next_close=_LATER,
        )

    # ===== Happy Path =====

    def test_create_market_clock(self, clock: MarketClock) -> None:
        """MarketClock should store is_open, next_open, and next_close."""
        assert clock.is_open is True
        assert clock.next_open == _NOW
        assert clock.next_close == _LATER

    def test_market_closed(self) -> None:
        """MarketClock with is_open=False should be valid."""
        clock = MarketClock(is_open=False, next_open=_NOW, next_close=_LATER)
        assert clock.is_open is False

    def test_serialization_roundtrip(self, clock: MarketClock) -> None:
        """model_dump → model_validate should produce an equal instance."""
        data = clock.model_dump()
        restored = MarketClock.model_validate(data)
        assert restored == clock

    # ===== Immutability =====

    def test_frozen_raises_on_assignment(self, clock: MarketClock) -> None:
        """Assigning to a field on a frozen model must raise."""
        with pytest.raises(ValidationError):
            clock.is_open = False  # type: ignore[misc]


class TestBrokerError:
    """Tests for BrokerError."""

    # ===== Happy Path =====

    def test_create_error(self) -> None:
        """BrokerError should store error_code, message, and broker_name."""
        err = BrokerError(
            error_code="insufficient_funds",
            message="Not enough buying power",
            broker_name="alpaca",
        )
        assert err.error_code == "insufficient_funds"
        assert err.message == "Not enough buying power"
        assert err.broker_name == "alpaca"

    def test_is_exception(self) -> None:
        """BrokerError should be a subclass of Exception."""
        err = BrokerError("code", "msg", "broker")
        assert isinstance(err, Exception)

    def test_str_representation(self) -> None:
        """str(BrokerError) should include broker, code, and message."""
        err = BrokerError("timeout", "Request timed out", "webull")
        assert "[webull]" in str(err)
        assert "timeout" in str(err)
        assert "Request timed out" in str(err)

    def test_raise_and_catch(self) -> None:
        """BrokerError should be raisable and catchable."""
        with pytest.raises(BrokerError) as exc_info:
            raise BrokerError("rejected", "Order rejected", "alpaca")
        assert exc_info.value.error_code == "rejected"
        assert exc_info.value.broker_name == "alpaca"
