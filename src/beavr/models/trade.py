"""Trade records model."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Trade(BaseModel):
    """
    Record of an executed (or simulated) trade.

    Attributes:
        id: Unique trade identifier (UUID)
        symbol: Trading symbol
        side: Trade side - "buy" or "sell"
        quantity: Number of shares traded
        price: Price per share
        amount: Total dollar amount (quantity * price)
        timestamp: When the trade was executed
        reason: Reason for the trade (e.g., "dip_buy", "scheduled", "fallback")
        strategy_id: Optional strategy identifier
    """

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique trade ID")
    symbol: str = Field(..., description="Trading symbol")
    side: Literal["buy", "sell"] = Field(..., description="Trade side")
    quantity: Decimal = Field(..., description="Number of shares", ge=0)
    price: Decimal = Field(..., description="Price per share", ge=0)
    amount: Decimal = Field(..., description="Total dollar amount", ge=0)
    timestamp: datetime = Field(..., description="Trade timestamp")
    reason: str = Field(..., description="Trade reason")
    strategy_id: Optional[str] = Field(default=None, description="Strategy identifier")

    def __str__(self) -> str:
        return (
            f"Trade({self.side.upper()} {self.quantity} {self.symbol} "
            f"@ ${self.price} = ${self.amount} [{self.reason}])"
        )

    @classmethod
    def create_buy(
        cls,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        timestamp: datetime,
        reason: str,
        strategy_id: Optional[str] = None,
    ) -> "Trade":
        """
        Factory method to create a buy trade from a dollar amount.

        Calculates quantity based on amount and price.
        """
        quantity = amount / price
        return cls(
            symbol=symbol,
            side="buy",
            quantity=quantity,
            price=price,
            amount=amount,
            timestamp=timestamp,
            reason=reason,
            strategy_id=strategy_id,
        )

    @classmethod
    def create_sell(
        cls,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        timestamp: datetime,
        reason: str,
        strategy_id: Optional[str] = None,
    ) -> "Trade":
        """
        Factory method to create a sell trade from a share quantity.

        Calculates amount based on quantity and price.
        """
        amount = quantity * price
        return cls(
            symbol=symbol,
            side="sell",
            quantity=quantity,
            price=price,
            amount=amount,
            timestamp=timestamp,
            reason=reason,
            strategy_id=strategy_id,
        )
