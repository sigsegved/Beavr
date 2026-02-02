"""Simulated portfolio for backtesting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from beavr.models.portfolio import PortfolioState, Position
from beavr.models.trade import Trade


class SimulatedPortfolio:
    """Track portfolio state during backtest simulation.

    This class maintains the state of a simulated portfolio during backtesting,
    including cash balance, positions, and trade history.

    Attributes:
        cash: Current cash balance
        positions: Current positions by symbol (symbol -> shares)
        trades: List of all executed trades
        initial_cash: Starting cash balance
    """

    def __init__(self, initial_cash: Decimal) -> None:
        """Initialize portfolio with starting cash.

        Args:
            initial_cash: Starting cash balance
        """
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.positions: dict[str, Decimal] = {}  # symbol -> shares
        self._avg_costs: dict[str, Decimal] = {}  # symbol -> avg cost per share
        self.trades: list[Trade] = []

    def buy(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        timestamp: datetime,
        reason: str,
        strategy_id: Optional[str] = None,
    ) -> Optional[Trade]:
        """Execute a buy order.

        Args:
            symbol: Trading symbol
            amount: Dollar amount to buy
            price: Price per share
            timestamp: Trade timestamp
            reason: Reason for trade
            strategy_id: Optional strategy identifier

        Returns:
            Trade record if executed, None if insufficient cash
        """
        if amount > self.cash:
            return None

        if amount <= Decimal("0"):
            return None

        if price <= Decimal("0"):
            return None

        shares = amount / price

        # Update position and average cost
        existing_shares = self.positions.get(symbol, Decimal("0"))
        existing_cost = self._avg_costs.get(symbol, Decimal("0"))

        # Calculate new average cost
        if existing_shares > 0:
            total_cost = (existing_shares * existing_cost) + amount
            new_shares = existing_shares + shares
            new_avg_cost = total_cost / new_shares
        else:
            new_shares = shares
            new_avg_cost = price

        self.positions[symbol] = new_shares
        self._avg_costs[symbol] = new_avg_cost
        self.cash -= amount

        trade = Trade(
            id=str(uuid4()),
            symbol=symbol,
            side="buy",
            quantity=shares,
            price=price,
            amount=amount,
            timestamp=timestamp,
            reason=reason,
            strategy_id=strategy_id,
        )
        self.trades.append(trade)
        return trade

    def sell(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        timestamp: datetime,
        reason: str,
        strategy_id: Optional[str] = None,
    ) -> Optional[Trade]:
        """Execute a sell order.

        Args:
            symbol: Trading symbol
            quantity: Number of shares to sell
            price: Price per share
            timestamp: Trade timestamp
            reason: Reason for trade
            strategy_id: Optional strategy identifier

        Returns:
            Trade record if executed, None if insufficient shares
        """
        existing_shares = self.positions.get(symbol, Decimal("0"))
        if quantity > existing_shares:
            return None

        if quantity <= Decimal("0"):
            return None

        if price <= Decimal("0"):
            return None

        amount = quantity * price
        new_shares = existing_shares - quantity

        if new_shares == Decimal("0"):
            # Close position
            del self.positions[symbol]
            if symbol in self._avg_costs:
                del self._avg_costs[symbol]
        else:
            self.positions[symbol] = new_shares
            # Average cost doesn't change on sell

        self.cash += amount

        trade = Trade(
            id=str(uuid4()),
            symbol=symbol,
            side="sell",
            quantity=quantity,
            price=price,
            amount=amount,
            timestamp=timestamp,
            reason=reason,
            strategy_id=strategy_id,
        )
        self.trades.append(trade)
        return trade

    def get_position(self, symbol: str) -> Decimal:
        """Get shares held for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Number of shares held (0 if no position)
        """
        return self.positions.get(symbol, Decimal("0"))

    def get_avg_cost(self, symbol: str) -> Decimal:
        """Get average cost per share for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Average cost per share (0 if no position)
        """
        return self._avg_costs.get(symbol, Decimal("0"))

    def get_value(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate total portfolio value.

        Args:
            prices: Current prices by symbol

        Returns:
            Total portfolio value (cash + position values)
        """
        position_value = sum(
            shares * prices.get(symbol, Decimal("0"))
            for symbol, shares in self.positions.items()
        )
        return self.cash + position_value

    def get_position_value(self, symbol: str, price: Decimal) -> Decimal:
        """Get market value of a specific position.

        Args:
            symbol: Trading symbol
            price: Current price

        Returns:
            Market value of position
        """
        shares = self.positions.get(symbol, Decimal("0"))
        return shares * price

    def get_cost_basis(self, symbol: str) -> Decimal:
        """Get cost basis for a position.

        Args:
            symbol: Trading symbol

        Returns:
            Total cost basis (shares * avg cost)
        """
        shares = self.positions.get(symbol, Decimal("0"))
        avg_cost = self._avg_costs.get(symbol, Decimal("0"))
        return shares * avg_cost

    def get_total_cost_basis(self) -> Decimal:
        """Get total cost basis across all positions.

        Returns:
            Sum of cost basis for all positions
        """
        return sum(
            self.get_cost_basis(symbol)
            for symbol in self.positions
        )

    def get_unrealized_pnl(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate unrealized profit/loss.

        Args:
            prices: Current prices by symbol

        Returns:
            Unrealized P&L across all positions
        """
        current_value = sum(
            shares * prices.get(symbol, Decimal("0"))
            for symbol, shares in self.positions.items()
        )
        return current_value - self.get_total_cost_basis()

    def get_state(
        self,
        timestamp: datetime,
        prices: dict[str, Decimal],  # noqa: ARG002
    ) -> PortfolioState:
        """Get current state as PortfolioState model.

        Args:
            timestamp: Current timestamp
            prices: Current prices by symbol (reserved for future use)

        Returns:
            PortfolioState snapshot
        """
        positions = {
            symbol: Position(
                symbol=symbol,
                quantity=shares,
                avg_cost=self._avg_costs.get(symbol, Decimal("0")),
            )
            for symbol, shares in self.positions.items()
        }
        return PortfolioState(
            timestamp=timestamp,
            cash=self.cash,
            positions=positions,
        )

    def get_total_invested(self) -> Decimal:
        """Get total amount invested (sum of all buy amounts).

        Returns:
            Total dollar amount of all buy trades
        """
        return sum(
            (trade.amount for trade in self.trades if trade.side == "buy"),
            Decimal("0"),
        )

    def get_total_withdrawn(self) -> Decimal:
        """Get total amount withdrawn (sum of all sell amounts).

        Returns:
            Total dollar amount of all sell trades
        """
        return sum(
            (trade.amount for trade in self.trades if trade.side == "sell"),
            Decimal("0"),
        )

    def __repr__(self) -> str:
        return (
            f"SimulatedPortfolio(cash={self.cash}, "
            f"positions={len(self.positions)}, "
            f"trades={len(self.trades)})"
        )
