"""Stock quality screening for the research pipeline."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Large-cap, liquid stocks that always pass quality screening
QUALITY_UNIVERSE: set[str] = {
    # ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "XLF", "XLE", "XLK",
    "GLD", "SLV", "TLT", "EEM", "VWO",
    # Mega-cap
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AVGO",
    # Large-cap tech
    "AMD", "INTC", "CRM", "ORCL", "ADBE", "NFLX", "PYPL", "SQ", "UBER",
    "SNOW", "PLTR", "NET", "CRWD", "ZS", "DDOG", "MDB",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "BLK", "C", "WFC",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "AMGN", "GILD",
    # Consumer
    "WMT", "COST", "HD", "MCD", "SBUX", "NKE", "DIS", "TGT",
    # Energy
    "XOM", "CVX", "COP", "SLB",
    # Industrial
    "CAT", "BA", "HON", "UPS", "LMT", "RTX", "DE", "GE",
    # Crypto-adjacent
    "COIN", "MSTR",
}

# Minimum thresholds for the autonomous research pipeline
MIN_RESEARCH_PRICE: float = 15.0
MAX_RESEARCH_PRICE: float = 800.0
MIN_RESEARCH_VOLUME: int = 500_000


def passes_quality_gate(
    symbol: str,
    price: float = 0.0,
    avg_volume: int = 0,
) -> bool:
    """Hard quality gate for the autonomous research pipeline.

    Stocks that fail this check NEVER reach the LLM pipeline.
    This is distinct from the CLI quality check — it is stricter.

    Args:
        symbol: Stock ticker symbol.
        price: Current stock price (0 means unknown, will pass).
        avg_volume: Average daily volume (0 means unknown, will pass).

    Returns:
        True if the stock passes the quality gate.
    """
    # Quality universe always passes
    if symbol in QUALITY_UNIVERSE:
        return True

    # Reject long symbols (often warrants, units, etc.)
    if len(symbol) > 5:
        return False

    # Reject symbols with dots (class shares like BRK.B)
    if "." in symbol:
        return False

    # Price checks (only if price is known)
    if 0 < price < MIN_RESEARCH_PRICE:
        return False
    if price > MAX_RESEARCH_PRICE:
        return False

    # Volume check (only if volume is known)
    if 0 < avg_volume < MIN_RESEARCH_VOLUME:
        return False

    return True
