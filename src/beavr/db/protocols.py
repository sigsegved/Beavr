"""Repository protocol definitions for the Beavr trading platform.

Defines structural typing protocols (PEP 544) for all data persistence
interfaces.  Business logic (orchestrator, agents, CLI) depends on these
Protocols — never on a concrete implementation — so the storage backend
can be swapped (SQLite → DynamoDB, etc.) without touching any consumers.

Pattern mirrors ``beavr.broker.protocols``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

import pandas as pd

if TYPE_CHECKING:
    from beavr.db.ai_positions import AIPosition, AITrade
    from beavr.models.dd_report import DDSummary, DueDiligenceReport
    from beavr.models.market_event import (
        EventImportance,
        EventSummary,
        EventType,
        MarketEvent,
    )
    from beavr.models.portfolio_record import (
        PortfolioDecision,
        PortfolioRecord,
        PortfolioSnapshot,
    )
    from beavr.models.thesis import ThesisStatus, ThesisSummary, TradeThesis


# ---------------------------------------------------------------------------
# Existing V1/V2 repository interfaces
# ---------------------------------------------------------------------------


@runtime_checkable
class ThesisStore(Protocol):
    """Interface for trade thesis persistence.

    Manages the full lifecycle of trade theses — from draft creation
    through DD approval, execution, and closure/invalidation.

    Implementations: ``ThesisRepository`` (SQLite).
    """

    def save_thesis(self, thesis: TradeThesis) -> str:
        """Persist a new trade thesis.

        Args:
            thesis: The thesis model to store.

        Returns:
            The thesis ID.
        """
        ...

    def get_thesis(self, thesis_id: str) -> Optional[TradeThesis]:
        """Retrieve a thesis by its unique ID.

        Args:
            thesis_id: Unique thesis identifier.

        Returns:
            The thesis, or ``None`` if not found.
        """
        ...

    def get_active_theses(self) -> list[TradeThesis]:
        """Return all theses in *draft* or *active* status.

        Results are ordered by confidence (descending), then creation date.

        Returns:
            List of active theses.
        """
        ...

    def get_pending_dd(self) -> list[TradeThesis]:
        """Return active theses that have not yet been DD-approved.

        Returns:
            List of theses awaiting due-diligence review.
        """
        ...

    def get_theses_by_symbol(
        self, symbol: str, status: Optional[ThesisStatus] = None
    ) -> list[TradeThesis]:
        """Return theses for a given symbol, optionally filtered by status.

        Args:
            symbol: Trading symbol (e.g. ``'AAPL'``).
            status: If provided, only return theses with this status.

        Returns:
            List of matching theses, most recent first.
        """
        ...

    def get_theses_by_catalyst_date(self, target_date: date) -> list[TradeThesis]:
        """Return theses whose catalyst falls on *target_date*.

        Args:
            target_date: The catalyst date to match.

        Returns:
            List of matching theses ordered by confidence.
        """
        ...

    def update_thesis_status(
        self,
        thesis_id: str,
        status: ThesisStatus,
        position_id: Optional[int] = None,
    ) -> bool:
        """Update the status of a thesis.

        Args:
            thesis_id: Thesis to update.
            status: New status value.
            position_id: Optional linked position ID (set when executed).

        Returns:
            ``True`` if the row was updated.
        """
        ...

    def approve_dd(self, thesis_id: str, dd_report_id: str) -> bool:
        """Mark a thesis as DD-approved and link its DD report.

        Args:
            thesis_id: Thesis to approve.
            dd_report_id: The approving DD report ID.

        Returns:
            ``True`` if the row was updated.
        """
        ...

    def update_thesis(self, thesis: TradeThesis) -> bool:
        """Overwrite all mutable fields of an existing thesis.

        Args:
            thesis: The thesis with updated values (matched by ``thesis.id``).

        Returns:
            ``True`` if the row was updated.
        """
        ...

    def update_thesis_confidence(self, thesis_id: str, confidence: float) -> bool:
        """Update just the confidence score of a thesis.

        Args:
            thesis_id: Thesis to update.
            confidence: New confidence value (0.0–1.0).

        Returns:
            ``True`` if the row was updated.
        """
        ...

    def get_thesis_summaries(self, limit: int = 50) -> list[ThesisSummary]:
        """Return lightweight thesis summaries for display.

        Args:
            limit: Maximum number of summaries to return.

        Returns:
            List of ``ThesisSummary`` objects, most recent first.
        """
        ...


@runtime_checkable
class DDReportStore(Protocol):
    """Interface for due-diligence report persistence.

    Stores DD analysis results for the audit trail, learning, and
    approval-rate statistics.

    Implementations: ``DDReportsRepository`` (SQLite).
    """

    def save_report(self, report: DueDiligenceReport) -> str:
        """Persist a new DD report.

        Args:
            report: The report model to store.

        Returns:
            The report ID.
        """
        ...

    def get_report(self, report_id: str) -> Optional[DueDiligenceReport]:
        """Retrieve a DD report by its unique ID.

        Args:
            report_id: Unique report identifier.

        Returns:
            The report, or ``None`` if not found.
        """
        ...

    def get_report_by_thesis(self, thesis_id: str) -> Optional[DueDiligenceReport]:
        """Retrieve the most recent DD report for a thesis.

        Args:
            thesis_id: The thesis whose report is requested.

        Returns:
            The latest report for the thesis, or ``None``.
        """
        ...

    def get_reports_by_symbol(
        self, symbol: str, limit: int = 10
    ) -> list[DueDiligenceReport]:
        """Retrieve DD reports for a symbol.

        Args:
            symbol: Trading symbol.
            limit: Maximum reports to return.

        Returns:
            List of reports, most recent first.
        """
        ...

    def get_recent_approvals(self, limit: int = 20) -> list[DueDiligenceReport]:
        """Return recently approved (or conditionally approved) DD reports.

        Args:
            limit: Maximum reports to return.

        Returns:
            List of approved/conditional reports, most recent first.
        """
        ...

    def get_recent_rejections(self, limit: int = 20) -> list[DueDiligenceReport]:
        """Return recently rejected DD reports.

        Args:
            limit: Maximum reports to return.

        Returns:
            List of rejected reports, most recent first.
        """
        ...

    def get_approval_stats(self) -> dict:
        """Return aggregate approval/rejection statistics.

        Returns:
            Dictionary with keys such as ``total_reports``,
            ``approved``, ``rejected``, ``conditional``,
            ``approval_rate``, ``avg_confidence``, etc.
        """
        ...

    def get_report_summaries(self, limit: int = 50) -> list[DDSummary]:
        """Return lightweight DD-report summaries for display.

        Args:
            limit: Maximum summaries to return.

        Returns:
            List of ``DDSummary`` objects, most recent first.
        """
        ...


@runtime_checkable
class EventStore(Protocol):
    """Interface for market event persistence.

    Manages events discovered by the news monitor, tracking their
    processing status and thesis generation links.

    Implementations: ``EventsRepository`` (SQLite).
    """

    def save_event(self, event: MarketEvent) -> str:
        """Persist a new market event.

        Uses upsert semantics — duplicate event IDs are silently ignored.

        Args:
            event: The event model to store.

        Returns:
            The event ID.
        """
        ...

    def get_event(self, event_id: str) -> Optional[MarketEvent]:
        """Retrieve an event by its unique ID.

        Args:
            event_id: Unique event identifier.

        Returns:
            The event, or ``None`` if not found.
        """
        ...

    def get_recent_events(
        self,
        limit: int = 50,
        importance: Optional[EventImportance] = None,
        event_type: Optional[EventType] = None,
    ) -> list[MarketEvent]:
        """Return recent events with optional filters.

        Args:
            limit: Maximum events to return.
            importance: Filter by importance level.
            event_type: Filter by event type.

        Returns:
            List of events, most recent first.
        """
        ...

    def get_events_by_symbol(self, symbol: str, limit: int = 20) -> list[MarketEvent]:
        """Return events for a specific symbol.

        Args:
            symbol: Trading symbol.
            limit: Maximum events to return.

        Returns:
            List of events, most recent first.
        """
        ...

    def get_unprocessed_events(
        self, min_importance: Optional[EventImportance] = None
    ) -> list[MarketEvent]:
        """Return events that have not yet been processed.

        Args:
            min_importance: Minimum importance threshold.  Events below
                this level are excluded.  ``None`` defaults to medium.

        Returns:
            List of unprocessed events, ordered by importance then time.
        """
        ...

    def mark_event_processed(
        self, event_id: str, thesis_id: Optional[str] = None
    ) -> bool:
        """Mark an event as processed and optionally link a generated thesis.

        Args:
            event_id: The event to mark.
            thesis_id: If a thesis was generated from this event, its ID.

        Returns:
            ``True`` if the row was updated.
        """
        ...

    def get_upcoming_earnings(self, days_ahead: int = 7) -> list[MarketEvent]:
        """Return upcoming earnings events within a look-ahead window.

        Args:
            days_ahead: Number of calendar days to look ahead.

        Returns:
            List of earnings events, ordered by date ascending.
        """
        ...

    def get_event_summaries(self, limit: int = 50) -> list[EventSummary]:
        """Return lightweight event summaries for display.

        Args:
            limit: Maximum summaries to return.

        Returns:
            List of ``EventSummary`` objects, most recent first.
        """
        ...


@runtime_checkable
class PositionStore(Protocol):
    """Interface for AI position and trade persistence (V1).

    Tracks positions with stop/target levels and records every
    entry/exit trade for performance analysis.

    Implementations: ``AIPositionsRepository`` (SQLite).
    """

    def open_position(
        self,
        symbol: str,
        quantity: Decimal,
        entry_price: Decimal,
        stop_loss_pct: float,
        target_pct: float,
        strategy: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> int:
        """Open a new AI-managed position.

        Args:
            symbol: Stock symbol.
            quantity: Number of shares to buy.
            entry_price: Entry price per share.
            stop_loss_pct: Stop-loss percentage (e.g. ``5.0`` for 5 %).
            target_pct: Profit-target percentage.
            strategy: Trading strategy name.
            rationale: AI reasoning for the trade.

        Returns:
            The new position ID.
        """
        ...

    def close_position(
        self,
        position_id: int,
        exit_price: Decimal,
        reason: str,
    ) -> Optional[AIPosition]:
        """Close a position by its ID.

        Args:
            position_id: Position to close.
            exit_price: Exit price per share.
            reason: Human-readable exit reason (``'target'``, ``'stop'``, etc.).

        Returns:
            The updated (closed) position, or ``None`` if not found / already closed.
        """
        ...

    def close_position_by_symbol(
        self,
        symbol: str,
        exit_price: Decimal,
        reason: str,
    ) -> Optional[AIPosition]:
        """Close the open position for a symbol.

        Args:
            symbol: Stock symbol.
            exit_price: Exit price per share.
            reason: Exit reason.

        Returns:
            The closed position, or ``None`` if no open position exists.
        """
        ...

    def get_position(self, position_id: int) -> Optional[AIPosition]:
        """Retrieve a position by ID.

        Args:
            position_id: Position identifier.

        Returns:
            The position, or ``None`` if not found.
        """
        ...

    def get_open_position(self, symbol: str) -> Optional[AIPosition]:
        """Retrieve the currently open position for a symbol.

        Args:
            symbol: Stock symbol.

        Returns:
            The open position, or ``None``.
        """
        ...

    def get_open_positions(self) -> list[AIPosition]:
        """Return all currently open positions.

        Returns:
            List of open positions, most recent first.
        """
        ...

    def get_all_positions(self, limit: int = 100) -> list[AIPosition]:
        """Return all positions (open and closed).

        Args:
            limit: Maximum positions to return.

        Returns:
            List of positions, most recent first.
        """
        ...

    def get_trades(
        self, position_id: Optional[int] = None, limit: int = 100
    ) -> list[AITrade]:
        """Return trade executions, optionally filtered by position.

        Args:
            position_id: If provided, only return trades for this position.
            limit: Maximum trades to return (ignored when *position_id* is set).

        Returns:
            List of trades, most recent first.
        """
        ...

    def get_performance_summary(self) -> dict:
        """Return aggregate performance statistics for all AI trading.

        Returns:
            Dictionary with keys such as ``total_positions``,
            ``open_positions``, ``winning_trades``, ``total_pnl``,
            ``avg_pnl_pct``, ``win_rate``, etc.
        """
        ...


@runtime_checkable
class BarCacheStore(Protocol):
    """Interface for OHLCV bar-data caching.

    Provides local caching of historical bar data to avoid redundant
    API calls to market-data providers.

    Implementations: ``BarCache`` (SQLite).
    """

    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> Optional[pd.DataFrame]:
        """Retrieve cached bars for a symbol and date range.

        Returns ``None`` when the cache does not fully cover the
        requested range.

        Args:
            symbol: Stock symbol (e.g. ``'SPY'``).
            start: Start date (inclusive).
            end: End date (inclusive).
            timeframe: Bar timeframe (default ``'1Day'``).

        Returns:
            DataFrame with OHLCV columns, or ``None`` if not fully cached.
        """
        ...

    def save_bars(
        self,
        symbol: str,
        bars: pd.DataFrame,
        timeframe: str = "1Day",
    ) -> None:
        """Save (upsert) bars into the cache.

        Args:
            symbol: Stock symbol.
            bars: DataFrame with columns ``timestamp``, ``open``,
                ``high``, ``low``, ``close``, ``volume``.
            timeframe: Bar timeframe (default ``'1Day'``).
        """
        ...

    def has_data(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> bool:
        """Check whether the cache fully covers a date range.

        Args:
            symbol: Stock symbol.
            start: Start date (inclusive).
            end: End date (inclusive).
            timeframe: Bar timeframe (default ``'1Day'``).

        Returns:
            ``True`` if cached data covers the entire range.
        """
        ...

    def get_date_range(
        self,
        symbol: str,
        timeframe: str = "1Day",
    ) -> Optional[tuple[date, date]]:
        """Return the cached date range for a symbol.

        Args:
            symbol: Stock symbol.
            timeframe: Bar timeframe (default ``'1Day'``).

        Returns:
            ``(min_date, max_date)`` tuple, or ``None`` if no data cached.
        """
        ...

    def delete_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
    ) -> int:
        """Delete all cached bars for a symbol.

        Args:
            symbol: Stock symbol.
            timeframe: Bar timeframe (default ``'1Day'``).

        Returns:
            Number of rows deleted.
        """
        ...

    def get_symbols(self) -> list[str]:
        """Return all symbols that have cached data.

        Returns:
            Sorted list of unique symbol names.
        """
        ...


# ---------------------------------------------------------------------------
# New V3 repository interfaces (portfolio lifecycle & audit trail)
# ---------------------------------------------------------------------------


@runtime_checkable
class PortfolioStore(Protocol):
    """Interface for portfolio lifecycle persistence.

    Manages the creation, status transitions, stat tracking, and
    deletion of portfolio records.  Each portfolio encapsulates its
    own configuration, capital allocation, and performance history.

    Implementations: ``SQLitePortfolioStore`` (planned).
    """

    def create_portfolio(
        self,
        name: str,
        mode: str,
        initial_capital: Decimal,
        config_snapshot: dict,
        aggressiveness: str,
        directives: list[str],
    ) -> str:
        """Create a new portfolio record.

        Args:
            name: Human-readable portfolio name.
            mode: Trading mode (``'paper'`` or ``'live'``).
            initial_capital: Starting capital allocation.
            config_snapshot: Frozen copy of the trading configuration.
            aggressiveness: Risk profile (``'conservative'``,
                ``'moderate'``, ``'aggressive'``).
            directives: User-provided AI personality directives.

        Returns:
            The new portfolio ID.
        """
        ...

    def get_portfolio(self, portfolio_id: str) -> Optional[PortfolioRecord]:
        """Retrieve a portfolio by ID.

        Args:
            portfolio_id: Unique portfolio identifier.

        Returns:
            The portfolio record, or ``None`` if not found.
        """
        ...

    def get_portfolio_by_name(self, name: str) -> Optional[PortfolioRecord]:
        """Retrieve a portfolio by its unique name.

        Args:
            name: Portfolio name.

        Returns:
            The portfolio record, or ``None`` if not found.
        """
        ...

    def list_portfolios(
        self,
        status: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> list[PortfolioRecord]:
        """List portfolios with optional status/mode filters.

        Args:
            status: Filter by portfolio status (e.g. ``'active'``,
                ``'paused'``, ``'closed'``).  ``None`` returns all.
            mode: Filter by trading mode (``'paper'``, ``'live'``).
                ``None`` returns all.

        Returns:
            List of matching portfolio records.
        """
        ...

    def close_portfolio(self, portfolio_id: str) -> None:
        """Mark a portfolio as closed.

        Args:
            portfolio_id: Portfolio to close.
        """
        ...

    def pause_portfolio(self, portfolio_id: str) -> None:
        """Pause autonomous trading for a portfolio.

        Args:
            portfolio_id: Portfolio to pause.
        """
        ...

    def resume_portfolio(self, portfolio_id: str) -> None:
        """Resume a previously paused portfolio.

        Args:
            portfolio_id: Portfolio to resume.
        """
        ...

    def update_portfolio_stats(
        self,
        portfolio_id: str,
        trade_pnl: Decimal,
        is_win: bool,
    ) -> None:
        """Update aggregate performance stats after a trade closes.

        Args:
            portfolio_id: Portfolio that owns the trade.
            trade_pnl: Realized P&L of the closed trade.
            is_win: Whether the trade was profitable.
        """
        ...

    def delete_portfolio(self, portfolio_id: str) -> None:
        """Permanently delete a portfolio and its associated data.

        Args:
            portfolio_id: Portfolio to delete.
        """
        ...

    def delete_all_data(self) -> None:
        """Delete **all** portfolio data (use with caution).

        Intended for test teardown and hard resets only.
        """
        ...


@runtime_checkable
class DecisionStore(Protocol):
    """Interface for the portfolio audit trail.

    Every material decision the AI makes — thesis creation, DD
    approval, trade entry/exit, circuit-breaker triggers, etc. —
    is logged as a ``PortfolioDecision`` for full reproducibility.

    Implementations: ``SQLiteDecisionStore`` (planned).
    """

    def log_decision(self, decision: PortfolioDecision) -> str:
        """Persist an auditable decision record.

        Args:
            decision: The decision to log.

        Returns:
            The decision ID.
        """
        ...

    def get_decisions(
        self,
        portfolio_id: str,
        decision_type: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        decision_types: Optional[list[str]] = None,
    ) -> list[PortfolioDecision]:
        """Query decisions with optional filters and pagination.

        Args:
            portfolio_id: Portfolio to query.
            decision_type: Filter by single ``DecisionType`` value.
            symbol: Filter by trading symbol.
            limit: Maximum decisions to return.
            offset: Number of decisions to skip (for pagination).
            decision_types: Filter by multiple ``DecisionType`` values
                (SQL ``IN``).  Mutually exclusive with *decision_type*.

        Returns:
            List of matching decisions, most recent first.
        """
        ...

    def get_full_audit_trail(
        self,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PortfolioDecision]:
        """Return the complete decision history for a portfolio.

        Args:
            portfolio_id: Portfolio to query.
            start_date: If provided, only include decisions on or after
                this date.
            end_date: If provided, only include decisions on or before
                this date.

        Returns:
            Full ordered list of decisions within the date window.
        """
        ...


@runtime_checkable
class SnapshotStore(Protocol):
    """Interface for daily portfolio value snapshots.

    Captures point-in-time portfolio state (equity, cash, positions
    value, P&L) for equity-curve construction and drawdown analysis.

    Implementations: ``SQLiteSnapshotStore`` (planned).
    """

    def take_snapshot(self, snapshot: PortfolioSnapshot) -> str:
        """Persist a portfolio snapshot.

        Args:
            snapshot: The snapshot to store.

        Returns:
            The snapshot ID.
        """
        ...

    def get_snapshots(
        self,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PortfolioSnapshot]:
        """Retrieve snapshots for a portfolio within a date window.

        Args:
            portfolio_id: Portfolio to query.
            start_date: If provided, only include snapshots on or after
                this date.
            end_date: If provided, only include snapshots on or before
                this date.

        Returns:
            List of snapshots ordered by date ascending.
        """
        ...
