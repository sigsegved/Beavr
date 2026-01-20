"""OHLCV bar data model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Bar(BaseModel):
    """
    OHLCV bar data representing a single candlestick.

    Attributes:
        symbol: Trading symbol (e.g., "SPY", "AAPL")
        timestamp: Bar timestamp (start of the period)
        open: Opening price
        high: Highest price during the period
        low: Lowest price during the period
        close: Closing price
        volume: Trading volume
        timeframe: Timeframe string (e.g., "1Day", "1Hour")
    """

    symbol: str = Field(..., description="Trading symbol")
    timestamp: datetime = Field(..., description="Bar timestamp")
    open: Decimal = Field(..., description="Opening price", ge=0)
    high: Decimal = Field(..., description="Highest price", ge=0)
    low: Decimal = Field(..., description="Lowest price", ge=0)
    close: Decimal = Field(..., description="Closing price", ge=0)
    volume: int = Field(..., description="Trading volume", ge=0)
    timeframe: Optional[str] = Field(default="1Day", description="Bar timeframe")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return (
            f"Bar({self.symbol} {self.timestamp.date()} "
            f"O:{self.open} H:{self.high} L:{self.low} C:{self.close} V:{self.volume})"
        )
