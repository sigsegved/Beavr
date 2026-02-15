"""Shared fixtures and MockBroker test double for broker tests."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

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


class MockBroker:
    """In-memory broker implementing BrokerProvider + MarketDataProvider protocols.

    Used for testing protocol conformance without hitting real APIs.
    Simulates order fills, tracks positions, returns canned bar data.
    """

    def __init__(self) -> None:
        self._cash: Decimal = Decimal("100000")
        self._equity: Decimal = Decimal("100000")
        self._positions: Dict[str, BrokerPosition] = {}
        self._orders: Dict[str, OrderResult] = {}
        self._market_open: bool = True
        self._valid_symbols: set[str] = {
            "AAPL",
            "SPY",
            "QQQ",
            "MSFT",
            "GOOGL",
            "BTC/USD",
            "TSLA",
        }
        self._prices: Dict[str, Decimal] = {
            "AAPL": Decimal("175.50"),
            "SPY": Decimal("450.00"),
            "QQQ": Decimal("380.00"),
            "MSFT": Decimal("400.00"),
            "GOOGL": Decimal("140.00"),
            "BTC/USD": Decimal("45000.00"),
            "TSLA": Decimal("200.00"),
        }

    # ── BrokerProvider properties ──────────────────────────────────────

    @property
    def broker_name(self) -> str:
        return "mock"

    @property
    def supports_fractional(self) -> bool:
        return True

    # ── MarketDataProvider property ────────────────────────────────────

    @property
    def provider_name(self) -> str:
        return "mock"

    # ── Account & positions ────────────────────────────────────────────

    def get_account(self) -> AccountInfo:
        return AccountInfo(
            equity=self._equity,
            cash=self._cash,
            buying_power=self._cash,
        )

    def get_positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    # ── Order lifecycle ────────────────────────────────────────────────

    def submit_order(self, order: OrderRequest) -> OrderResult:
        if order.symbol not in self._valid_symbols:
            raise BrokerError(
                error_code="invalid_symbol",
                message=f"Symbol '{order.symbol}' not found",
                broker_name=self.broker_name,
            )

        price = self._prices[order.symbol]
        qty: Decimal
        if order.quantity is not None:
            qty = order.quantity
        elif order.notional is not None:
            qty = order.notional / price
        else:
            qty = Decimal("0")

        order_id = str(uuid.uuid4())
        now = datetime.utcnow()

        result = OrderResult(
            order_id=order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            status="filled",
            filled_qty=qty,
            filled_avg_price=price,
            submitted_at=now,
            filled_at=now,
        )
        self._orders[order_id] = result

        # Update positions
        if order.side == "buy":
            existing = self._positions.get(order.symbol)
            if existing:
                new_qty = existing.qty + qty
                new_cost = (
                    (existing.avg_cost * existing.qty) + (price * qty)
                ) / new_qty
                self._positions[order.symbol] = BrokerPosition(
                    symbol=order.symbol,
                    qty=new_qty,
                    market_value=new_qty * price,
                    avg_cost=new_cost,
                    unrealized_pl=Decimal("0"),
                    side="long",
                )
            else:
                self._positions[order.symbol] = BrokerPosition(
                    symbol=order.symbol,
                    qty=qty,
                    market_value=qty * price,
                    avg_cost=price,
                    unrealized_pl=Decimal("0"),
                    side="long",
                )
            self._cash -= qty * price
        else:
            if order.symbol in self._positions:
                existing = self._positions[order.symbol]
                new_qty = existing.qty - qty
                if new_qty <= 0:
                    del self._positions[order.symbol]
                else:
                    self._positions[order.symbol] = BrokerPosition(
                        symbol=order.symbol,
                        qty=new_qty,
                        market_value=new_qty * price,
                        avg_cost=existing.avg_cost,
                        unrealized_pl=Decimal("0"),
                        side="long",
                    )
                self._cash += qty * price

        return result

    def cancel_order(self, order_id: str) -> OrderResult:
        if order_id not in self._orders:
            raise BrokerError(
                error_code="order_not_found",
                message=f"Order '{order_id}' not found",
                broker_name=self.broker_name,
            )
        existing = self._orders[order_id]
        if existing.status == "filled":
            raise BrokerError(
                error_code="order_already_filled",
                message=f"Cannot cancel filled order '{order_id}'",
                broker_name=self.broker_name,
            )
        cancelled = OrderResult(
            order_id=existing.order_id,
            client_order_id=existing.client_order_id,
            symbol=existing.symbol,
            side=existing.side,
            order_type=existing.order_type,
            status="cancelled",
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            submitted_at=existing.submitted_at,
            filled_at=None,
        )
        self._orders[order_id] = cancelled
        return cancelled

    def get_order(self, order_id: str) -> OrderResult:
        if order_id not in self._orders:
            raise BrokerError(
                error_code="order_not_found",
                message=f"Order '{order_id}' not found",
                broker_name=self.broker_name,
            )
        return self._orders[order_id]

    def list_orders(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[OrderResult]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return orders[:limit]

    def is_market_open(self) -> bool:
        return self._market_open

    def get_clock(self) -> MarketClock:
        now = datetime.utcnow()
        return MarketClock(
            is_open=self._market_open,
            next_open=now + timedelta(hours=12),
            next_close=now + timedelta(hours=6),
        )

    # ── MarketDataProvider methods ─────────────────────────────────────

    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1day",
    ) -> pd.DataFrame:
        if symbol not in self._valid_symbols:
            raise BrokerError(
                error_code="invalid_symbol",
                message=f"Symbol '{symbol}' not found",
                broker_name=self.broker_name,
            )

        base_price = self._prices.get(symbol, Decimal("100"))
        current = start
        rows: list[dict] = []
        while current <= end:
            rows.append(
                {
                    "timestamp": datetime.combine(current, datetime.min.time()),
                    "open": base_price * Decimal("0.99"),
                    "high": base_price * Decimal("1.02"),
                    "low": base_price * Decimal("0.98"),
                    "close": base_price,
                    "volume": 1000000,
                }
            )
            current += timedelta(days=1)

        df = pd.DataFrame(rows)
        if not df.empty:
            df.set_index("timestamp", inplace=True)
            df.index = pd.DatetimeIndex(df.index)
        return df

    def get_bars_multi(
        self,
        symbols: list[str],
        start: date,
        end: date,
        timeframe: str = "1day",
    ) -> dict[str, pd.DataFrame]:
        return {sym: self.get_bars(sym, start, end, timeframe) for sym in symbols}

    def get_snapshot(self, symbol: str) -> dict:
        if symbol not in self._valid_symbols:
            raise BrokerError(
                error_code="invalid_symbol",
                message=f"Symbol '{symbol}' not found",
                broker_name=self.broker_name,
            )
        price = self._prices.get(symbol, Decimal("100"))
        return {
            "symbol": symbol,
            "latest_trade": {"price": price, "size": 100},
            "latest_quote": {
                "bid": price - Decimal("0.01"),
                "ask": price + Decimal("0.01"),
            },
        }

    # ── Test helper methods ────────────────────────────────────────────

    def set_market_open(self, is_open: bool) -> None:
        """Toggle whether the market is considered open."""
        self._market_open = is_open

    def add_pending_order(self, order_id: str, symbol: str) -> None:
        """Add a pending (unfilled) order for testing cancel/get flows."""
        self._orders[order_id] = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side="buy",
            order_type="market",
            status="pending",
            filled_qty=Decimal("0"),
            submitted_at=datetime.utcnow(),
            filled_at=None,
        )


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_broker() -> MockBroker:
    """Create a fresh MockBroker instance."""
    return MockBroker()
