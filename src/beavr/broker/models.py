"""Broker-agnostic domain models.

Defines the canonical data structures shared across all broker integrations.
These models are immutable (frozen) and use Decimal for all monetary values
to ensure financial correctness.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class AccountInfo(BaseModel):
    """Broker account summary.

    Represents the current state of a trading account including
    equity, available cash, and buying power.

    Attributes:
        equity: Total account equity (assets − liabilities).
        cash: Settled cash available for withdrawal.
        buying_power: Cash available for placing new orders.
        currency: ISO-4217 currency code.
    """

    model_config = {"frozen": True}

    equity: Decimal = Field(description="Total account equity")
    cash: Decimal = Field(description="Settled cash balance")
    buying_power: Decimal = Field(description="Buying power available for new orders")
    currency: str = Field(default="USD", description="ISO-4217 currency code")


class BrokerPosition(BaseModel):
    """A single open position reported by the broker.

    Attributes:
        symbol: Ticker symbol of the held asset.
        qty: Number of shares/units held.
        market_value: Current market value of the position.
        avg_cost: Average cost basis per share.
        unrealized_pl: Unrealized profit/loss on the position.
        side: Whether the position is long or short.
    """

    model_config = {"frozen": True}

    symbol: str = Field(description="Ticker symbol")
    qty: Decimal = Field(description="Number of shares held")
    market_value: Decimal = Field(description="Current market value")
    avg_cost: Decimal = Field(description="Average cost per share")
    unrealized_pl: Decimal = Field(description="Unrealized profit/loss")
    side: Literal["long", "short"] = Field(description="Position side")


class OrderRequest(BaseModel):
    """Intent to place an order with a broker.

    Exactly one of ``quantity`` or ``notional`` must be provided.
    ``limit_price`` is required for ``limit`` and ``stop_limit`` order types.
    ``stop_price`` is required for ``stop`` and ``stop_limit`` order types.

    Attributes:
        symbol: Ticker symbol to trade.
        side: Buy or sell.
        order_type: Type of order to place.
        tif: Time-in-force instruction.
        quantity: Number of shares (mutually exclusive with notional).
        notional: Dollar amount (mutually exclusive with quantity).
        limit_price: Limit price for limit/stop-limit orders.
        stop_price: Stop/trigger price for stop/stop-limit orders.
        client_order_id: Optional client-generated idempotency key.
    """

    model_config = {"frozen": True}

    symbol: str = Field(description="Ticker symbol to trade")
    side: Literal["buy", "sell"] = Field(description="Order side")
    order_type: Literal["market", "limit", "stop", "stop_limit"] = Field(
        description="Order type"
    )
    tif: Literal["day", "gtc", "ioc", "fok"] = Field(
        default="day", description="Time-in-force"
    )
    quantity: Optional[Decimal] = Field(
        default=None, description="Number of shares to trade"
    )
    notional: Optional[Decimal] = Field(
        default=None, description="Dollar amount to trade"
    )
    limit_price: Optional[Decimal] = Field(
        default=None, description="Limit price for limit/stop-limit orders"
    )
    stop_price: Optional[Decimal] = Field(
        default=None, description="Stop price for stop/stop-limit orders"
    )
    client_order_id: Optional[str] = Field(
        default=None, description="Client-generated idempotency key"
    )

    @model_validator(mode="after")
    def _validate_quantity_xor_notional(self) -> OrderRequest:
        """Ensure exactly one of quantity or notional is provided."""
        has_qty = self.quantity is not None
        has_notional = self.notional is not None
        if has_qty == has_notional:
            raise ValueError(
                "Exactly one of 'quantity' or 'notional' must be provided, not both or neither"
            )
        return self

    @model_validator(mode="after")
    def _validate_limit_price(self) -> OrderRequest:
        """Ensure limit_price is set for limit and stop_limit orders."""
        if self.order_type in ("limit", "stop_limit") and self.limit_price is None:
            raise ValueError(
                f"limit_price is required for '{self.order_type}' orders"
            )
        return self

    @model_validator(mode="after")
    def _validate_stop_price(self) -> OrderRequest:
        """Ensure stop_price is set for stop and stop_limit orders."""
        if self.order_type in ("stop", "stop_limit") and self.stop_price is None:
            raise ValueError(
                f"stop_price is required for '{self.order_type}' orders"
            )
        return self


class OrderResult(BaseModel):
    """Broker-reported outcome of a submitted order.

    Attributes:
        order_id: Broker-assigned order identifier.
        client_order_id: Client-generated idempotency key, if provided.
        symbol: Ticker symbol traded.
        side: Buy or sell.
        order_type: Type of the order.
        status: Current order status as reported by the broker.
        filled_qty: Number of shares filled so far.
        filled_avg_price: Volume-weighted average fill price, if any fills occurred.
        submitted_at: Timestamp when the order was accepted by the broker.
        filled_at: Timestamp when the order was completely filled.
    """

    model_config = {"frozen": True}

    order_id: str = Field(description="Broker-assigned order identifier")
    client_order_id: Optional[str] = Field(
        default=None, description="Client-generated idempotency key"
    )
    symbol: str = Field(description="Ticker symbol traded")
    side: Literal["buy", "sell"] = Field(description="Order side")
    order_type: str = Field(description="Order type")
    status: str = Field(description="Current order status")
    filled_qty: Decimal = Field(description="Shares filled so far")
    filled_avg_price: Optional[Decimal] = Field(
        default=None, description="Average fill price"
    )
    submitted_at: Optional[datetime] = Field(
        default=None, description="Submission timestamp"
    )
    filled_at: Optional[datetime] = Field(
        default=None, description="Fill completion timestamp"
    )


class MarketClock(BaseModel):
    """Market session timing information.

    Attributes:
        is_open: Whether the market is currently open for trading.
        next_open: Datetime of the next market open.
        next_close: Datetime of the next market close.
    """

    model_config = {"frozen": True}

    is_open: bool = Field(description="Whether the market is currently open")
    next_open: datetime = Field(description="Next market open time")
    next_close: datetime = Field(description="Next market close time")


class BrokerError(Exception):
    """Exception raised by broker operations.

    Attributes:
        error_code: Machine-readable error code (e.g. ``"insufficient_funds"``).
        message: Human-readable error description.
        broker_name: Name of the broker that raised the error.
    """

    def __init__(self, error_code: str, message: str, broker_name: str) -> None:
        self.error_code: str = error_code
        self.message: str = message
        self.broker_name: str = broker_name
        super().__init__(f"[{broker_name}] {error_code}: {message}")
