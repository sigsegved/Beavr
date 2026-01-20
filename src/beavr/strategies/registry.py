"""Strategy registry for discovering and loading strategies."""

from __future__ import annotations

from typing import Any, Callable, Type, Union

from pydantic import BaseModel

from beavr.strategies.base import BaseStrategy

# Global registry
_REGISTRY: dict[str, Type[BaseStrategy]] = {}


def register_strategy(name: str) -> Callable[[Type[BaseStrategy]], Type[BaseStrategy]]:
    """Decorator to register a strategy class.

    Use this decorator to register a strategy so it can be loaded by name.

    Usage:
        @register_strategy("simple_dca")
        class SimpleDCAStrategy(BaseStrategy):
            ...

    Args:
        name: Unique name for the strategy

    Returns:
        Decorator function

    Raises:
        ValueError: If a strategy with this name is already registered
    """

    def decorator(cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
        if name in _REGISTRY:
            raise ValueError(f"Strategy '{name}' already registered by {_REGISTRY[name]}")
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_strategy(name: str) -> Type[BaseStrategy]:
    """Get strategy class by name.

    Args:
        name: Name of the strategy to retrieve

    Returns:
        The strategy class

    Raises:
        ValueError: If the strategy is not found
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown strategy: '{name}'. Available: {available}")
    return _REGISTRY[name]


def list_strategies() -> list[str]:
    """List all registered strategy names.

    Returns:
        Sorted list of registered strategy names
    """
    return sorted(_REGISTRY.keys())


def get_strategy_info(name: str) -> dict[str, Any]:
    """Get information about a registered strategy.

    Args:
        name: Name of the strategy

    Returns:
        Dictionary with strategy metadata

    Raises:
        ValueError: If the strategy is not found
    """
    cls = get_strategy(name)
    return {
        "name": name,
        "display_name": cls.name,
        "description": cls.description,
        "version": cls.version,
        "param_model": cls.param_model,
    }


def create_strategy(name: str, params: Union[dict[str, Any], BaseModel]) -> BaseStrategy:
    """Create strategy instance with params.

    Validates params against strategy's param model.

    Args:
        name: Name of the strategy to create
        params: Dictionary of params or validated param model

    Returns:
        Instantiated strategy

    Raises:
        ValueError: If the strategy is not found
        ValidationError: If params are invalid
    """
    strategy_cls = get_strategy(name)

    # If params is already a validated model, use it directly
    if isinstance(params, BaseModel):
        validated_params = params
    else:
        # Validate params using the strategy's param model
        validated_params = strategy_cls.param_model(**params)

    return strategy_cls(validated_params)


def clear_registry() -> None:
    """Clear all registered strategies.

    Primarily used for testing.
    """
    _REGISTRY.clear()


def _ensure_strategies_loaded() -> None:
    """Ensure built-in strategies are loaded.

    This imports the strategy modules to trigger their @register_strategy
    decorators. Called automatically when listing or creating strategies.
    """
    # Import built-in strategies to trigger registration
    try:
        from beavr.strategies import simple_dca  # noqa: F401
    except ImportError:
        pass

    try:
        from beavr.strategies import dip_buy_dca  # noqa: F401
    except ImportError:
        pass
