"""BeavrAPI — public API boundary for external consumers.

This is the ONLY interface the Telegram bot (or any external system)
may use to interact with Beavr. It exposes safe, well-defined operations
and never leaks internal state, repos, or orchestrator internals.

Security contract:
- All methods are read-only or trigger actions through proper channels
- No direct access to database, orchestrator state, or agent internals
- All inputs are validated before processing
- All outputs are plain data (dicts/strings), never internal objects
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Immutable snapshot of portfolio state."""

    cash: Decimal
    equity: Decimal
    positions: list[dict[str, Any]]


@dataclass(frozen=True)
class DDReportSummary:
    """Immutable summary of a DD report."""

    symbol: str
    recommendation: str
    confidence: float
    executive_summary: str
    entry: Optional[Decimal]
    target: Optional[Decimal]
    stop: Optional[Decimal]
    risk_factors: list[str]


@dataclass(frozen=True)
class TradeHistoryEntry:
    """Immutable trade history record."""

    symbol: str
    pnl: float
    pnl_pct: float
    exit_type: str


@runtime_checkable
class BeavrAPI(Protocol):
    """Public API protocol for external consumers (Telegram bot, etc.).

    Implementations provide safe access to Beavr system functionality
    without exposing internal state.
    """

    def get_portfolio_status(self) -> PortfolioSnapshot:
        """Get current portfolio snapshot (cash, equity, positions)."""
        ...

    def get_open_positions(self) -> list[dict[str, Any]]:
        """Get list of open AI-managed positions."""
        ...

    def get_trade_history(self, limit: int = 10) -> list[TradeHistoryEntry]:
        """Get recent closed trades."""
        ...

    def get_dd_report(self, symbol: str) -> Optional[DDReportSummary]:
        """Get the latest DD report for a symbol, if one exists."""
        ...

    def queue_symbol_for_analysis(self, symbol: str) -> str:
        """Queue a symbol for analysis in the next DD cycle.

        Returns:
            Status message describing what was queued.
        """
        ...

    def submit_research(self, text: str) -> str:
        """Submit freeform text as a market event for the system to process.

        Returns:
            Status message confirming submission.
        """
        ...

    def get_sector_etfs(self, sector: str) -> list[str]:
        """Get ETF tickers for a sector."""
        ...

    def submit_buy_order(
        self, symbol: str, notional: Decimal
    ) -> dict[str, Any]:
        """Submit a buy order through the broker.

        Returns:
            Order result dict with order_id and status.
        """
        ...

    def submit_sell_order(
        self, symbol: str, quantity: Optional[Decimal] = None
    ) -> dict[str, Any]:
        """Submit a sell order through the broker.

        Returns:
            Order result dict with order_id and status.
        """
        ...
