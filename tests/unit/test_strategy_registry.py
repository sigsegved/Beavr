"""Tests for strategy registry."""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from pydantic import BaseModel, Field

from beavr.models.signal import Signal
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.registry import (
    clear_registry,
    create_strategy,
    get_strategy,
    get_strategy_info,
    list_strategies,
    register_strategy,
)


class TestParams(BaseModel):
    """Test parameter model."""

    symbols: list[str] = Field(default_factory=lambda: ["SPY"])
    amount: Decimal = Field(default=Decimal("100"))


class TestRegistry:
    """Tests for strategy registry."""

    @pytest.fixture(autouse=True)
    def clear_before_each(self) -> None:
        """Clear registry before each test."""
        clear_registry()

    def test_register_strategy(self) -> None:
        """Test registering a strategy."""

        @register_strategy("test_strat")
        class TestStrategy(BaseStrategy):
            name = "Test"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        assert "test_strat" in list_strategies()
        assert get_strategy("test_strat") is TestStrategy

    def test_register_duplicate_fails(self) -> None:
        """Test that registering duplicate name raises error."""

        @register_strategy("dupe")
        class FirstStrategy(BaseStrategy):
            name = "First"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return []

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        with pytest.raises(ValueError, match="already registered"):

            @register_strategy("dupe")
            class SecondStrategy(BaseStrategy):
                name = "Second"
                param_model = TestParams

                def __init__(self, params: TestParams):
                    self.params = params

                @property
                def symbols(self) -> list[str]:
                    return []

                def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                    return []

    def test_get_unknown_strategy_raises(self) -> None:
        """Test that getting unknown strategy raises error."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("nonexistent")

    def test_get_unknown_strategy_lists_available(self) -> None:
        """Test that error message includes available strategies."""

        @register_strategy("available_one")
        class AvailableStrategy(BaseStrategy):
            name = "Available"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return []

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        with pytest.raises(ValueError) as exc_info:
            get_strategy("nonexistent")

        assert "available_one" in str(exc_info.value)

    def test_list_strategies_empty(self) -> None:
        """Test listing strategies when none registered."""
        assert list_strategies() == []

    def test_list_strategies_sorted(self) -> None:
        """Test that listed strategies are sorted."""

        @register_strategy("zebra")
        class ZebraStrategy(BaseStrategy):
            name = "Zebra"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return []

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        @register_strategy("alpha")
        class AlphaStrategy(BaseStrategy):
            name = "Alpha"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return []

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        assert list_strategies() == ["alpha", "zebra"]

    def test_get_strategy_info(self) -> None:
        """Test getting strategy info."""

        @register_strategy("info_test")
        class InfoStrategy(BaseStrategy):
            name = "Info Strategy"
            description = "A strategy for testing info"
            version = "2.0.0"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        info = get_strategy_info("info_test")
        assert info["name"] == "info_test"
        assert info["display_name"] == "Info Strategy"
        assert info["description"] == "A strategy for testing info"
        assert info["version"] == "2.0.0"
        assert info["param_model"] is TestParams

    def test_create_strategy_with_dict(self) -> None:
        """Test creating strategy with dict params."""

        @register_strategy("create_test")
        class CreateTestStrategy(BaseStrategy):
            name = "Create Test"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        strategy = create_strategy(
            "create_test",
            {"symbols": ["QQQ", "SPY"], "amount": Decimal("250")}
        )

        assert isinstance(strategy, CreateTestStrategy)
        assert strategy.symbols == ["QQQ", "SPY"]
        assert strategy.params.amount == Decimal("250")

    def test_create_strategy_with_model(self) -> None:
        """Test creating strategy with validated model."""

        @register_strategy("model_test")
        class ModelTestStrategy(BaseStrategy):
            name = "Model Test"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return self.params.symbols

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        params = TestParams(symbols=["AAPL"], amount=Decimal("500"))
        strategy = create_strategy("model_test", params)

        assert isinstance(strategy, ModelTestStrategy)
        assert strategy.symbols == ["AAPL"]

    def test_create_strategy_validates_params(self) -> None:
        """Test that create_strategy validates params."""
        from pydantic import ValidationError

        class StrictParams(BaseModel):
            amount: Decimal = Field(ge=Decimal("100"))

        @register_strategy("strict_test")
        class StrictStrategy(BaseStrategy):
            name = "Strict"
            param_model = StrictParams

            def __init__(self, params: StrictParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return []

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        with pytest.raises(ValidationError):
            create_strategy("strict_test", {"amount": Decimal("50")})

    def test_clear_registry(self) -> None:
        """Test clearing the registry."""

        @register_strategy("to_clear")
        class ToClearStrategy(BaseStrategy):
            name = "To Clear"
            param_model = TestParams

            def __init__(self, params: TestParams):
                self.params = params

            @property
            def symbols(self) -> list[str]:
                return []

            def evaluate(self, ctx: StrategyContext) -> list[Signal]:
                return []

        assert "to_clear" in list_strategies()
        clear_registry()
        assert list_strategies() == []
