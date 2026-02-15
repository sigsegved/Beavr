"""Alpaca broker adapter implementing BrokerProvider protocol."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from beavr.broker.models import (
    AccountInfo,
    BrokerError,
    BrokerPosition,
    MarketClock,
    OrderRequest,
    OrderResult,
)

logger = logging.getLogger(__name__)


class AlpacaBroker:
    """BrokerProvider implementation for Alpaca.

    Wraps alpaca-py TradingClient to provide broker-agnostic trading operations.
    All Alpaca-specific types are converted to broker-agnostic models.
    All monetary values are converted to Decimal for financial precision.
    """

    def __init__(self, api_key: str, api_secret: str, paper: bool = True) -> None:
        from alpaca.trading.client import TradingClient

        self._client = TradingClient(api_key, api_secret, paper=paper)
        self._paper = paper

    @property
    def broker_name(self) -> str:
        """Human-readable broker identifier."""
        return "alpaca"

    @property
    def supports_fractional(self) -> bool:
        """Whether the broker supports fractional-share orders."""
        return True

    def get_account(self) -> AccountInfo:
        """Return current account information."""
        try:
            account = self._client.get_account()
            return AccountInfo(
                equity=Decimal(str(account.equity)),
                cash=Decimal(str(account.cash)),
                buying_power=Decimal(str(account.buying_power)),
                currency="USD",
            )
        except Exception as e:
            raise BrokerError(
                error_code="account_error",
                message=f"Failed to get account: {e}",
                broker_name=self.broker_name,
            ) from e

    def get_positions(self) -> list[BrokerPosition]:
        """Return all open positions held in the account."""
        try:
            positions = self._client.get_all_positions()
            return [self._map_position(p) for p in positions]
        except Exception as e:
            raise BrokerError(
                error_code="positions_error",
                message=f"Failed to get positions: {e}",
                broker_name=self.broker_name,
            ) from e

    def submit_order(self, order: OrderRequest) -> OrderResult:
        """Submit order to Alpaca.

        Builds the appropriate Alpaca SDK request object based on the
        order type and delegates to the TradingClient.
        """
        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import (
                LimitOrderRequest,
                MarketOrderRequest,
                StopLimitOrderRequest,
                StopOrderRequest,
            )

            side = OrderSide.BUY if order.side == "buy" else OrderSide.SELL
            tif_map = {
                "day": TimeInForce.DAY,
                "gtc": TimeInForce.GTC,
                "ioc": TimeInForce.IOC,
                "fok": TimeInForce.FOK,
            }
            tif = tif_map.get(order.tif, TimeInForce.DAY)

            # Build the appropriate order type
            if order.order_type == "market":
                if order.notional is not None:
                    req = MarketOrderRequest(
                        symbol=order.symbol,
                        notional=float(order.notional),
                        side=side,
                        time_in_force=tif,
                        client_order_id=order.client_order_id,
                    )
                else:
                    req = MarketOrderRequest(
                        symbol=order.symbol,
                        qty=float(order.quantity),
                        side=side,
                        time_in_force=tif,
                        client_order_id=order.client_order_id,
                    )
            elif order.order_type == "limit":
                req = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity) if order.quantity else None,
                    notional=float(order.notional) if order.notional else None,
                    side=side,
                    time_in_force=tif,
                    limit_price=float(order.limit_price),
                    client_order_id=order.client_order_id,
                )
            elif order.order_type == "stop":
                req = StopOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=side,
                    time_in_force=tif,
                    stop_price=float(order.stop_price),
                    client_order_id=order.client_order_id,
                )
            elif order.order_type == "stop_limit":
                req = StopLimitOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=side,
                    time_in_force=tif,
                    limit_price=float(order.limit_price),
                    stop_price=float(order.stop_price),
                    client_order_id=order.client_order_id,
                )
            else:
                raise BrokerError(
                    error_code="unsupported_order_type",
                    message=f"Order type '{order.order_type}' not supported",
                    broker_name=self.broker_name,
                )

            result = self._client.submit_order(req)
            return self._map_order(result)

        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="order_error",
                message=f"Failed to submit order: {e}",
                broker_name=self.broker_name,
            ) from e

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an existing order by its broker-assigned ID."""
        try:
            self._client.cancel_order_by_id(order_id)
            # Fetch the updated order after cancellation
            return self.get_order(order_id)
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="cancel_error",
                message=f"Failed to cancel order {order_id}: {e}",
                broker_name=self.broker_name,
            ) from e

    def get_order(self, order_id: str) -> OrderResult:
        """Retrieve the current state of an order."""
        try:
            order = self._client.get_order_by_id(order_id)
            return self._map_order(order)
        except Exception as e:
            raise BrokerError(
                error_code="order_not_found",
                message=f"Failed to get order {order_id}: {e}",
                broker_name=self.broker_name,
            ) from e

    def list_orders(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[OrderResult]:
        """List orders, optionally filtered by status."""
        try:
            from alpaca.trading.requests import GetOrdersRequest

            if status:
                params = GetOrdersRequest(status=status, limit=limit)
            else:
                params = GetOrdersRequest(limit=limit)

            orders = self._client.get_orders(params)
            return [self._map_order(o) for o in orders]
        except Exception as e:
            raise BrokerError(
                error_code="list_orders_error",
                message=f"Failed to list orders: {e}",
                broker_name=self.broker_name,
            ) from e

    def is_market_open(self) -> bool:
        """Return True if the market is currently open for trading."""
        try:
            clock = self._client.get_clock()
            return bool(clock.is_open)
        except Exception as e:
            raise BrokerError(
                error_code="clock_error",
                message=f"Failed to check market status: {e}",
                broker_name=self.broker_name,
            ) from e

    def get_clock(self) -> MarketClock:
        """Return the current market clock with open/close times."""
        try:
            clock = self._client.get_clock()
            return MarketClock(
                is_open=bool(clock.is_open),
                next_open=(
                    clock.next_open
                    if isinstance(clock.next_open, datetime)
                    else datetime.fromisoformat(str(clock.next_open))
                ),
                next_close=(
                    clock.next_close
                    if isinstance(clock.next_close, datetime)
                    else datetime.fromisoformat(str(clock.next_close))
                ),
            )
        except Exception as e:
            raise BrokerError(
                error_code="clock_error",
                message=f"Failed to get market clock: {e}",
                broker_name=self.broker_name,
            ) from e

    # ===== Private helpers =====

    def _map_position(self, p: object) -> BrokerPosition:
        """Map an Alpaca Position to a broker-agnostic BrokerPosition.

        Handles the Alpaca ``PositionSide`` enum by normalising to
        ``"long"`` or ``"short"`` string literals.
        """
        side_str = str(getattr(p, "side", "long")).lower()
        if side_str not in ("long", "short"):
            side_str = "long"  # safe default
        return BrokerPosition(
            symbol=p.symbol,  # type: ignore[union-attr]
            qty=Decimal(str(p.qty)),  # type: ignore[union-attr]
            market_value=Decimal(str(p.market_value)),  # type: ignore[union-attr]
            avg_cost=Decimal(str(p.avg_entry_price)),  # type: ignore[union-attr]
            unrealized_pl=Decimal(str(p.unrealized_pl)),  # type: ignore[union-attr]
            side=side_str,  # type: ignore[arg-type]
        )

    def _map_order(self, order: object) -> OrderResult:
        """Map an Alpaca Order to a broker-agnostic OrderResult."""
        side_str = str(getattr(order, "side", "buy")).lower()
        if side_str not in ("buy", "sell"):
            side_str = "buy"

        filled_qty = (
            Decimal(str(order.filled_qty))  # type: ignore[union-attr]
            if order.filled_qty  # type: ignore[union-attr]
            else Decimal("0")
        )
        filled_avg_price = (
            Decimal(str(order.filled_avg_price))  # type: ignore[union-attr]
            if order.filled_avg_price  # type: ignore[union-attr]
            else None
        )

        submitted_at = None
        if order.submitted_at:  # type: ignore[union-attr]
            submitted_at = (
                order.submitted_at  # type: ignore[union-attr]
                if isinstance(order.submitted_at, datetime)  # type: ignore[union-attr]
                else datetime.fromisoformat(str(order.submitted_at))  # type: ignore[union-attr]
            )

        filled_at = None
        if order.filled_at:  # type: ignore[union-attr]
            filled_at = (
                order.filled_at  # type: ignore[union-attr]
                if isinstance(order.filled_at, datetime)  # type: ignore[union-attr]
                else datetime.fromisoformat(str(order.filled_at))  # type: ignore[union-attr]
            )

        return OrderResult(
            order_id=str(order.id),  # type: ignore[union-attr]
            client_order_id=(
                str(order.client_order_id)  # type: ignore[union-attr]
                if order.client_order_id  # type: ignore[union-attr]
                else None
            ),
            symbol=order.symbol,  # type: ignore[union-attr]
            side=side_str,  # type: ignore[arg-type]
            order_type=str(getattr(order, "order_type", "market")).lower(),
            status=str(order.status).lower(),  # type: ignore[union-attr]
            filled_qty=filled_qty,
            filled_avg_price=filled_avg_price,
            submitted_at=submitted_at,
            filled_at=filled_at,
        )
