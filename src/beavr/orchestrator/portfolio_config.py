"""Portfolio-level configuration helpers.

Maps aggressiveness profiles to V2Config overrides and provides utilities
for building prompt directives and state-file paths.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from beavr.models.portfolio_record import Aggressiveness
from beavr.orchestrator.v2_engine import V2Config

# ---------------------------------------------------------------------------
# Aggressiveness → V2Config field overrides
# ---------------------------------------------------------------------------

AGGRESSIVENESS_OVERRIDES: dict[Aggressiveness, dict[str, Any]] = {
    Aggressiveness.CONSERVATIVE: {
        "max_daily_loss_pct": 2.0,
        "max_drawdown_pct": 7.0,
        "daily_trade_limit": 3,
        "max_position_pct": 0.08,
        "day_trade_target_pct": 3.0,
        "day_trade_stop_pct": 2.0,
        "swing_short_target_pct": 10.0,
        "swing_short_stop_pct": 5.0,
    },
    Aggressiveness.MODERATE: {
        "max_daily_loss_pct": 3.0,
        "max_drawdown_pct": 10.0,
        "daily_trade_limit": 5,
        "max_position_pct": 0.10,
        "day_trade_target_pct": 5.0,
        "day_trade_stop_pct": 3.0,
        "swing_short_target_pct": 15.0,
        "swing_short_stop_pct": 7.0,
    },
    Aggressiveness.AGGRESSIVE: {
        "max_daily_loss_pct": 5.0,
        "max_drawdown_pct": 15.0,
        "daily_trade_limit": 8,
        "max_position_pct": 0.15,
        "day_trade_target_pct": 8.0,
        "day_trade_stop_pct": 4.0,
        "swing_short_target_pct": 25.0,
        "swing_short_stop_pct": 10.0,
    },
}

# ---------------------------------------------------------------------------
# Confidence thresholds (not yet in V2Config — tracked separately)
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLDS: dict[Aggressiveness, dict[str, float]] = {
    Aggressiveness.CONSERVATIVE: {
        "min_thesis_confidence": 0.75,
        "dd_min_approval_confidence": 0.80,
    },
    Aggressiveness.MODERATE: {
        "min_thesis_confidence": 0.60,
        "dd_min_approval_confidence": 0.65,
    },
    Aggressiveness.AGGRESSIVE: {
        "min_thesis_confidence": 0.45,
        "dd_min_approval_confidence": 0.50,
    },
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def apply_aggressiveness(config: V2Config, aggressiveness: str) -> V2Config:
    """Return a *new* V2Config with aggressiveness overrides applied.

    Parameters
    ----------
    config:
        The base V2Config instance to start from.
    aggressiveness:
        One of ``"conservative"``, ``"moderate"``, or ``"aggressive"``.

    Returns
    -------
    V2Config
        A fresh dataclass instance with the relevant fields overridden.

    Raises
    ------
    ValueError
        If *aggressiveness* is not a valid ``Aggressiveness`` value.
    """
    level = Aggressiveness(aggressiveness.lower())
    overrides = AGGRESSIVENESS_OVERRIDES[level]
    return dataclasses.replace(config, **overrides)


def format_directives_for_prompt(directives: list[str]) -> str:
    """Format user trading directives for injection into LLM prompts.

    Parameters
    ----------
    directives:
        A list of plain-text directive strings (e.g. ``"Avoid biotech"``).

    Returns
    -------
    str
        A formatted block suitable for prompt injection, or an empty string
        if *directives* is empty.
    """
    if not directives:
        return ""

    lines = "\n".join(f"- {d}" for d in directives)
    return (
        "USER TRADING DIRECTIVES:\n"
        f"{lines}\n"
        "\n"
        "Factor these preferences into your analysis."
    )


def build_portfolio_state_path(
    portfolio_id: str,
    log_dir: str = "logs/ai_investor",
) -> str:
    """Build the JSON state-file path for a given portfolio.

    Parameters
    ----------
    portfolio_id:
        Unique identifier for the portfolio.
    log_dir:
        Base directory for AI investor logs.

    Returns
    -------
    str
        Path in the form ``{log_dir}/state_{portfolio_id}.json``.
    """
    return f"{log_dir}/state_{portfolio_id}.json"
