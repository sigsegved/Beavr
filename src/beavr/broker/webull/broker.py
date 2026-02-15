"""Webull broker adapter implementing BrokerProvider protocol."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from beavr.broker.models import (
    AccountInfo,
    BrokerError,
    BrokerPosition,
    MarketClock,
    OrderRequest,
    OrderResult,
)
from beavr.broker.webull.instrument_cache import InstrumentCache

logger = logging.getLogger(__name__)

# Max page size for Webull API pagination
MAX_PAGE_SIZE: int = 100
# Max pages to prevent infinite loops
MAX_PAGES: int = 50


class WebullBroker:
    """BrokerProvider implementation for Webull.

    Wraps Webull's SDK classes (``Account``, ``OrderOperation``,
    ``TradeCalendar``) behind the unified ``BrokerProvider`` protocol
    used by the rest of the Beavr platform.

    All monetary values are represented as ``Decimal`` — never ``float``.
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_id: Optional[str] = None,
        region: str = "us",
        paper: bool = True,
    ) -> None:
        from webullsdkcore.client import ApiClient

        self._api_client = ApiClient(app_key, app_secret, region_id=region)
        self._region = region
        self._paper = paper

        # Paper trading endpoint
        if paper:
            self._api_client.add_endpoint(
                region, "us-openapi-alb.uat.webullbroker.com"
            )

        # Account ID (auto-discover if not provided)
        self._account_id = account_id or self._discover_account_id()

        # Instrument cache for symbol → instrument_id resolution
        self._instrument_cache = InstrumentCache(self._api_client)

        # Lazy SDK module references
        self._account_api: Any = None
        self._order_api: Any = None
        self._calendar_api: Any = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _discover_account_id(self) -> str:
        """Auto-discover account ID from subscriptions."""
        try:
            from webullsdktrade.trade.account_info import Account

            account = Account(self._api_client)
            response = account.get_app_subscriptions()
            if response and isinstance(response, list) and len(response) > 0:
                acc_id = response[0].get("account_id")
                if acc_id:
                    return str(acc_id)
            raise BrokerError(
                error_code="no_account_found",
                message="No Webull account found in subscriptions",
                broker_name="webull",
            )
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="account_discovery_error",
                message=f"Failed to discover Webull account: {e}",
                broker_name="webull",
            ) from e

    @property
    def _account(self) -> Any:
        """Lazy accessor for ``Account`` SDK object."""
        if self._account_api is None:
            from webullsdktrade.trade.account_info import Account

            self._account_api = Account(self._api_client)
        return self._account_api

    @property
    def _orders(self) -> Any:
        """Lazy accessor for ``OrderOperation`` SDK object."""
        if self._order_api is None:
            from webullsdktrade.trade.order_operation import OrderOperation

            self._order_api = OrderOperation(self._api_client)
        return self._order_api

    @property
    def _calendar(self) -> Any:
        """Lazy accessor for ``TradeCalendar`` SDK object."""
        if self._calendar_api is None:
            from webullsdktrade.trade.trade_calendar import TradeCalendar

            self._calendar_api = TradeCalendar(self._api_client)
        return self._calendar_api

    # ------------------------------------------------------------------
    # BrokerProvider protocol — properties
    # ------------------------------------------------------------------

    @property
    def broker_name(self) -> str:
        """Human-readable broker identifier."""
        return "webull"

    @property
    def supports_fractional(self) -> bool:
        """Webull supports fractional shares via AMOUNT-based orders."""
        return True

    # ------------------------------------------------------------------
    # BrokerProvider protocol — account & positions
    # ------------------------------------------------------------------

    def get_account(self) -> AccountInfo:
        """Return current account balances as an ``AccountInfo``."""
        try:
            response = self._account.get_account_balance(
                self._account_id, total_asset_currency="USD"
            )
            if not response:
                raise BrokerError(
                    error_code="empty_response",
                    message="Empty account balance response",
                    broker_name="webull",
                )

            equity = Decimal(str(response.get("total_asset", "0")))
            cash = Decimal(str(response.get("total_cash", "0")))

            # Try to get buying power from account_currency_assets
            buying_power = cash
            assets = response.get("account_currency_assets", [])
            if assets and isinstance(assets, list):
                for a in assets:
                    if isinstance(a, dict):
                        bp = a.get("cash_power") or a.get("margin_power")
                        if bp:
                            buying_power = Decimal(str(bp))
                            break

            return AccountInfo(
                equity=equity,
                cash=cash,
                buying_power=buying_power,
                currency="USD",
            )
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="account_error",
                message=f"Failed to get Webull account: {e}",
                broker_name="webull",
            ) from e

    def get_positions(self) -> list[BrokerPosition]:
        """Get all positions with auto-pagination."""
        try:
            all_positions: list[BrokerPosition] = []
            last_instrument_id: Optional[str] = None

            for _ in range(MAX_PAGES):
                response = self._account.get_account_position(
                    self._account_id,
                    page_size=MAX_PAGE_SIZE,
                    last_instrument_id=last_instrument_id,
                )
                if not response:
                    break

                holdings = response.get("holdings", [])
                for h in holdings:
                    all_positions.append(self._map_holding(h))
                    last_instrument_id = h.get("instrument_id")

                if not response.get("has_next", False):
                    break

            return all_positions
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="positions_error",
                message=f"Failed to get Webull positions: {e}",
                broker_name="webull",
            ) from e

    def _map_holding(self, h: Dict[str, Any]) -> BrokerPosition:
        """Map a Webull holding dict to ``BrokerPosition``."""
        symbol = str(h.get("instrument", h.get("symbol", "UNKNOWN")))
        qty = Decimal(str(h.get("quantity", "0")))
        market_value = Decimal(str(h.get("market_value", "0")))
        total_cost = Decimal(str(h.get("total_cost", "0")))
        avg_cost = total_cost / qty if qty > 0 else Decimal("0")
        unrealized_pl = Decimal(str(h.get("unrealized_profit_loss", "0")))

        return BrokerPosition(
            symbol=symbol,
            qty=qty,
            market_value=market_value,
            avg_cost=avg_cost,
            unrealized_pl=unrealized_pl,
            side="long",
        )

    # ------------------------------------------------------------------
    # BrokerProvider protocol — orders
    # ------------------------------------------------------------------

    def submit_order(self, order: OrderRequest) -> OrderResult:
        """Submit a new order to Webull."""
        try:
            # Resolve symbol to instrument_id
            instrument_id = self._instrument_cache.resolve(order.symbol)

            # Generate client_order_id if not provided
            client_order_id = order.client_order_id or str(uuid.uuid4())

            # Map order type
            order_type_map: Dict[str, str] = {
                "market": "MARKET",
                "limit": "LIMIT",
                "stop": "STOP_LOSS",
                "stop_limit": "STOP_LOSS_LIMIT",
            }
            webull_order_type = order_type_map.get(order.order_type)
            if not webull_order_type:
                raise BrokerError(
                    error_code="unsupported_order_type",
                    message=f"Order type '{order.order_type}' not supported",
                    broker_name="webull",
                )

            # Map side
            side = "BUY" if order.side == "buy" else "SELL"

            # Map TIF
            tif_map: Dict[str, str] = {
                "day": "DAY",
                "gtc": "GTC",
                "ioc": "IOC",
                "fok": "IOC",
            }
            tif = tif_map.get(order.tif, "DAY")

            # Determine qty
            qty_str = (
                str(order.quantity)
                if order.quantity is not None
                else str(order.notional)
            )

            # Build kwargs for place_order
            kwargs: Dict[str, Any] = {
                "account_id": self._account_id,
                "qty": qty_str,
                "instrument_id": instrument_id,
                "side": side,
                "client_order_id": client_order_id,
                "order_type": webull_order_type,
                "extended_hours_trading": False,
                "tif": tif,
            }

            if order.limit_price is not None:
                kwargs["limit_price"] = str(order.limit_price)
            if order.stop_price is not None:
                kwargs["stop_price"] = str(order.stop_price)

            self._orders.place_order(**kwargs)

            return OrderResult(
                order_id=client_order_id,
                client_order_id=client_order_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                status="submitted",
                filled_qty=Decimal("0"),
                filled_avg_price=None,
                submitted_at=datetime.utcnow(),
                filled_at=None,
            )
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="order_error",
                message=f"Failed to submit order: {e}",
                broker_name="webull",
            ) from e

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order by its client_order_id."""
        try:
            self._orders.cancel_order(self._account_id, order_id)
            # Fetch updated status
            return self.get_order(order_id)
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="cancel_error",
                message=f"Failed to cancel order {order_id}: {e}",
                broker_name="webull",
            ) from e

    def get_order(self, order_id: str) -> OrderResult:
        """Get order details by client_order_id."""
        try:
            response = self._orders.query_order_detail(
                self._account_id, order_id
            )
            if not response:
                raise BrokerError(
                    error_code="order_not_found",
                    message=f"Order '{order_id}' not found",
                    broker_name="webull",
                )
            return self._map_order(response)
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="order_error",
                message=f"Failed to get order {order_id}: {e}",
                broker_name="webull",
            ) from e

    def list_orders(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[OrderResult]:
        """List orders with auto-pagination."""
        try:
            all_orders: list[OrderResult] = []

            last_id: Optional[str] = None
            for _ in range(MAX_PAGES):
                response = self._orders.list_today_orders(
                    self._account_id,
                    page_size=min(limit, MAX_PAGE_SIZE),
                    last_client_order_id=last_id,
                )
                if not response:
                    break

                orders = response.get("orders", [])
                for o in orders:
                    mapped = self._map_order(o)
                    if status is None or mapped.status == status:
                        all_orders.append(mapped)
                    last_id = o.get("client_order_id")

                if not response.get("has_next", False) or len(all_orders) >= limit:
                    break

            return all_orders[:limit]
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="list_orders_error",
                message=f"Failed to list orders: {e}",
                broker_name="webull",
            ) from e

    def _map_order(self, o: Dict[str, Any]) -> OrderResult:
        """Map a Webull order dict to ``OrderResult``."""
        client_order_id = str(o.get("client_order_id", ""))
        symbol = str(o.get("symbol", o.get("instrument", "")))

        side_raw = str(o.get("side", "BUY")).lower()
        side = side_raw if side_raw in ("buy", "sell") else "buy"

        order_type_raw = str(o.get("order_type", "MARKET")).lower()
        type_map: Dict[str, str] = {
            "market": "market",
            "limit": "limit",
            "stop_loss": "stop",
            "stop_loss_limit": "stop_limit",
        }
        order_type = type_map.get(order_type_raw, order_type_raw)

        status_raw = str(o.get("status", "")).lower()
        status_map: Dict[str, str] = {
            "submitted": "submitted",
            "cancelled": "cancelled",
            "failed": "failed",
            "filled": "filled",
            "partial_filled": "partially_filled",
        }
        mapped_status = status_map.get(status_raw, status_raw)

        filled_qty = Decimal(
            str(o.get("filled_quantity", o.get("filled_qty", "0")))
        )
        filled_price_raw = o.get("avg_filled_price", o.get("filled_avg_price"))
        filled_avg_price = (
            Decimal(str(filled_price_raw)) if filled_price_raw else None
        )

        submitted_at: Optional[datetime] = None
        place_time = o.get("place_time") or o.get("submitted_at")
        if place_time:
            try:
                submitted_at = datetime.fromisoformat(
                    str(place_time).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        filled_at: Optional[datetime] = None
        fill_time = o.get("filled_time") or o.get("filled_at")
        if fill_time:
            try:
                filled_at = datetime.fromisoformat(
                    str(fill_time).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return OrderResult(
            order_id=client_order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            status=mapped_status,
            filled_qty=filled_qty,
            filled_avg_price=filled_avg_price,
            submitted_at=submitted_at,
            filled_at=filled_at,
        )

    # ------------------------------------------------------------------
    # BrokerProvider protocol — market clock
    # ------------------------------------------------------------------

    def is_market_open(self) -> bool:
        """Return whether the market is currently open."""
        try:
            clock = self.get_clock()
            return clock.is_open
        except Exception:
            return False

    def get_clock(self) -> MarketClock:
        """Return current market clock information."""
        try:
            today = date.today()
            start = today.isoformat()
            end = (today + timedelta(days=7)).isoformat()

            response = self._calendar.get_trade_calendar(
                market="US", start=start, end=end
            )

            now = datetime.utcnow()
            is_open = False
            next_open = now + timedelta(hours=12)  # fallback
            next_close = now + timedelta(hours=6)  # fallback

            if response and isinstance(response, list):
                for day in response:
                    day_date = day.get("date", "")
                    day_status = day.get("status", "")

                    if day_date == today.isoformat() and day_status == "TRADING":
                        # Market hours: 9:30 AM – 4:00 PM ET (14:30 – 21:00 UTC)
                        market_open = datetime.fromisoformat(
                            f"{day_date}T14:30:00"
                        )
                        market_close = datetime.fromisoformat(
                            f"{day_date}T21:00:00"
                        )

                        if market_open <= now <= market_close:
                            is_open = True
                            next_close = market_close
                        elif now < market_open:
                            next_open = market_open

                        break
                    elif (
                        day_date > today.isoformat() and day_status == "TRADING"
                    ):
                        next_open = datetime.fromisoformat(
                            f"{day_date}T14:30:00"
                        )
                        next_close = datetime.fromisoformat(
                            f"{day_date}T21:00:00"
                        )
                        break

            return MarketClock(
                is_open=is_open, next_open=next_open, next_close=next_close
            )
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(
                error_code="clock_error",
                message=f"Failed to get market clock: {e}",
                broker_name="webull",
            ) from e
