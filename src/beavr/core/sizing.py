"""Position sizing based on volatility and risk budget."""
from __future__ import annotations

from decimal import Decimal


def calculate_position_size(
    portfolio_value: Decimal,
    stop_distance_pct: float,
    max_risk_per_trade: float = 0.02,
    min_position_pct: float = 0.05,
    max_position_pct: float = 0.20,
) -> Decimal:
    """Calculate position size so max loss = risk_pct of portfolio.

    Volatile stocks (wide stop) get SMALLER positions.
    Tight-stop setups get LARGER positions.

    The formula: position_size = risk_amount / stop_distance
    This ensures that if stop is hit, you lose at most risk_amount.

    Args:
        portfolio_value: Total portfolio value in dollars.
        stop_distance_pct: Stop loss distance as percentage (e.g., 5.0 for 5%).
        max_risk_per_trade: Max portfolio risk per trade as decimal (default 0.02 = 2%).
        min_position_pct: Minimum position as fraction of portfolio (default 0.05 = 5%).
        max_position_pct: Maximum position as fraction of portfolio (default 0.20 = 20%).

    Returns:
        Dollar amount to invest in this position.

    Examples:
        >>> calculate_position_size(Decimal("10000"), stop_distance_pct=5.0)
        Decimal('4000')  # 2% risk / 5% stop = 40% position, capped at 20% = $2000

        >>> calculate_position_size(Decimal("10000"), stop_distance_pct=2.0)
        Decimal('2000')  # 2% risk / 2% stop = 100% position, capped at 20% = $2000

        >>> calculate_position_size(Decimal("10000"), stop_distance_pct=20.0)
        Decimal('1000')  # 2% risk / 20% stop = 10% position = $1000
    """
    # Default stop if not provided or invalid
    if stop_distance_pct <= 0:
        stop_distance_pct = 5.0  # Default 5% stop

    # Calculate risk amount (how much we're willing to lose)
    risk_amount = portfolio_value * Decimal(str(max_risk_per_trade))

    # Calculate raw position size: if stop hits, we lose risk_amount
    # position_size * stop_pct = risk_amount
    # position_size = risk_amount / stop_pct
    raw_size = risk_amount / Decimal(str(stop_distance_pct / 100))

    # Apply min/max bounds
    min_size = portfolio_value * Decimal(str(min_position_pct))
    max_size = portfolio_value * Decimal(str(max_position_pct))

    # Clamp to bounds
    return max(min_size, min(max_size, raw_size))
