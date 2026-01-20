"""Base strategy interface."""

from abc import ABC, abstractmethod
from typing import ClassVar, Type

from pydantic import BaseModel

from beavr.models.signal import Signal
from beavr.strategies.context import StrategyContext


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies.

    To create a custom strategy:
    1. Subclass BaseStrategy
    2. Define a Pydantic model for your params
    3. Override name, description, version class attributes
    4. Implement symbols property
    5. Implement evaluate() method

    Example:
        class MyStrategyParams(BaseModel):
            symbols: list[str]
            amount: Decimal

        class MyStrategy(BaseStrategy):
            name = "My Strategy"
            description = "Does something cool"
            version = "1.0.0"
            param_model = MyStrategyParams

            def __init__(self, params: MyStrategyParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                # Your strategy logic here
                return []
    """

    # Metadata - override in subclass
    name: ClassVar[str] = "Base Strategy"
    description: ClassVar[str] = ""
    version: ClassVar[str] = "1.0.0"

    # Parameter model class - override in subclass
    param_model: ClassVar[Type[BaseModel]] = BaseModel

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """Evaluate strategy and return signals.

        Called once per trading day during backtest.
        Return empty list for no action.

        Args:
            ctx: Strategy context with market data and portfolio state

        Returns:
            List of trading signals, empty list if no action
        """
        pass

    @property
    @abstractmethod
    def symbols(self) -> list[str]:
        """Symbols this strategy trades.

        Returns:
            List of trading symbols (e.g., ["SPY", "QQQ"])
        """
        pass

    def on_period_start(self, ctx: StrategyContext) -> None:
        """Called at start of each budget period (month/week).

        Override this method to perform any setup at the start
        of a new budget period.

        Args:
            ctx: Strategy context for the first day of the period
        """
        pass

    def on_period_end(self, ctx: StrategyContext) -> None:
        """Called at end of each budget period.

        Override this method to perform any cleanup or final
        actions at the end of a budget period.

        Args:
            ctx: Strategy context for the last day of the period
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}' v{self.version}>"
