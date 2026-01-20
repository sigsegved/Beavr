"""Portfolio state models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class Position(BaseModel):
    """
    A position in a single asset.

    Attributes:
        symbol: Trading symbol
        quantity: Number of shares held
        avg_cost: Average cost per share
    """

    symbol: str = Field(..., description="Trading symbol")
    quantity: Decimal = Field(..., description="Number of shares", ge=0)
    avg_cost: Decimal = Field(..., description="Average cost per share", ge=0)

    @property
    def cost_basis(self) -> Decimal:
        """Total cost basis for this position."""
        return self.quantity * self.avg_cost

    def market_value(self, price: Decimal) -> Decimal:
        """Calculate market value at given price."""
        return self.quantity * price

    def unrealized_pnl(self, price: Decimal) -> Decimal:
        """Calculate unrealized profit/loss at given price."""
        return self.market_value(price) - self.cost_basis

    def unrealized_pnl_pct(self, price: Decimal) -> float:
        """Calculate unrealized P&L as a percentage."""
        if self.cost_basis == 0:
            return 0.0
        return float(self.unrealized_pnl(price) / self.cost_basis)

    def __str__(self) -> str:
        return f"Position({self.symbol}: {self.quantity} shares @ ${self.avg_cost} avg)"


class PortfolioState(BaseModel):
    """
    Snapshot of portfolio state at a point in time.

    Attributes:
        timestamp: When this state was recorded
        cash: Available cash balance
        positions: Dictionary of symbol -> Position
    """

    timestamp: datetime = Field(..., description="State timestamp")
    cash: Decimal = Field(..., description="Available cash", ge=0)
    positions: dict[str, Position] = Field(
        default_factory=dict,
        description="Positions by symbol"
    )

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol, or None if not held."""
        return self.positions.get(symbol)

    def position_value(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate total market value of all positions."""
        return sum(
            (pos.market_value(prices.get(symbol, Decimal(0)))
             for symbol, pos in self.positions.items()),
            Decimal(0),
        )

    def total_value(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate total portfolio value (cash + positions)."""
        return self.cash + self.position_value(prices)

    def total_cost_basis(self) -> Decimal:
        """Calculate total cost basis of all positions."""
        return sum(
            (pos.cost_basis for pos in self.positions.values()),
            Decimal(0),
        )

    def total_unrealized_pnl(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate total unrealized P&L across all positions."""
        return sum(
            (pos.unrealized_pnl(prices.get(symbol, Decimal(0)))
             for symbol, pos in self.positions.items()),
            Decimal(0),
        )


    def __str__(self) -> str:
        pos_count = len(self.positions)
        return f"Portfolio(cash=${self.cash}, {pos_count} positions)"
