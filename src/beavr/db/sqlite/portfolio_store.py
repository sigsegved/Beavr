"""SQLite-backed stores for portfolio lifecycle, decisions, and snapshots."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from beavr.models.portfolio_record import (
    Aggressiveness,
    DecisionType,
    PortfolioDecision,
    PortfolioRecord,
    PortfolioSnapshot,
    PortfolioStatus,
    TradingMode,
)

if TYPE_CHECKING:
    from sqlite3 import Row

    from beavr.db.sqlite.connection import Database


# ---------------------------------------------------------------------------
# SQLitePortfolioStore
# ---------------------------------------------------------------------------


class SQLitePortfolioStore:
    """SQLite implementation of ``PortfolioStore`` protocol.

    Manages creation, status transitions, stat tracking, and deletion
    of portfolio records.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _row_to_portfolio(row: Row) -> PortfolioRecord:
        """Convert a database row to a ``PortfolioRecord``."""
        return PortfolioRecord(
            id=row["id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            status=PortfolioStatus(row["status"]),
            mode=TradingMode(row["mode"]),
            initial_capital=Decimal(row["initial_capital"]),
            allocated_capital=Decimal(row["allocated_capital"]),
            current_cash=Decimal(row["current_cash"]),
            config_snapshot=json.loads(row["config_snapshot"]) if row["config_snapshot"] else {},
            aggressiveness=Aggressiveness(row["aggressiveness"]),
            directives=json.loads(row["directives"]) if row["directives"] else [],
            total_invested=Decimal(row["total_invested"]),
            total_returned=Decimal(row["total_returned"]),
            realized_pnl=Decimal(row["realized_pnl"]),
            total_trades=int(row["total_trades"]),
            winning_trades=int(row["winning_trades"]),
            losing_trades=int(row["losing_trades"]),
            peak_value=Decimal(row["peak_value"]),
            max_drawdown_pct=float(row["max_drawdown_pct"]),
            notes=row["notes"],
        )

    # -- protocol methods ----------------------------------------------------

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

        Returns:
            The new portfolio ID.
        """
        portfolio_id: str = str(uuid4())[:8]
        now: str = datetime.now().isoformat()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolios (
                    id, name, created_at, closed_at, status, mode,
                    initial_capital, allocated_capital, current_cash,
                    config_snapshot, aggressiveness, directives,
                    total_invested, total_returned, realized_pnl,
                    total_trades, winning_trades, losing_trades,
                    peak_value, max_drawdown_pct, notes
                ) VALUES (
                    ?, ?, ?, NULL, 'active', ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    '0', '0', '0',
                    0, 0, 0,
                    '0', 0.0, NULL
                )
                """,
                (
                    portfolio_id,
                    name,
                    now,
                    mode,
                    str(initial_capital),
                    str(initial_capital),
                    str(initial_capital),
                    json.dumps(config_snapshot),
                    aggressiveness,
                    json.dumps(directives),
                ),
            )
        return portfolio_id

    def get_portfolio(self, portfolio_id: str) -> Optional[PortfolioRecord]:
        """Retrieve a portfolio by ID."""
        with self.db.connect() as conn:
            cursor = conn.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,))
            row = cursor.fetchone()
        return self._row_to_portfolio(row) if row else None

    def get_portfolio_by_name(self, name: str) -> Optional[PortfolioRecord]:
        """Retrieve a portfolio by its unique name."""
        with self.db.connect() as conn:
            cursor = conn.execute("SELECT * FROM portfolios WHERE name = ?", (name,))
            row = cursor.fetchone()
        return self._row_to_portfolio(row) if row else None

    def list_portfolios(
        self,
        status: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> list[PortfolioRecord]:
        """List portfolios with optional status/mode filters."""
        query = "SELECT * FROM portfolios"
        conditions: list[str] = []
        params: list[str] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if mode is not None:
            conditions.append("mode = ?")
            params.append(mode)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        with self.db.connect() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [self._row_to_portfolio(r) for r in rows]

    def close_portfolio(self, portfolio_id: str) -> None:
        """Mark a portfolio as closed."""
        now: str = datetime.now().isoformat()
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE portfolios SET status = 'closed', closed_at = ? WHERE id = ?",
                (now, portfolio_id),
            )

    def pause_portfolio(self, portfolio_id: str) -> None:
        """Pause autonomous trading for a portfolio."""
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE portfolios SET status = 'paused' WHERE id = ?",
                (portfolio_id,),
            )

    def resume_portfolio(self, portfolio_id: str) -> None:
        """Resume a previously paused portfolio."""
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE portfolios SET status = 'active' WHERE id = ?",
                (portfolio_id,),
            )

    def update_portfolio_stats(
        self,
        portfolio_id: str,
        trade_pnl: Decimal,
        is_win: bool,
    ) -> None:
        """Update aggregate performance stats after a trade closes."""
        with self.db.connect() as conn:
            # Fetch current values
            cursor = conn.execute(
                "SELECT total_trades, winning_trades, losing_trades, realized_pnl FROM portfolios WHERE id = ?",
                (portfolio_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return
            new_total_trades: int = int(row["total_trades"]) + 1
            new_winning: int = int(row["winning_trades"]) + (1 if is_win else 0)
            new_losing: int = int(row["losing_trades"]) + (0 if is_win else 1)
            new_pnl: Decimal = Decimal(row["realized_pnl"]) + trade_pnl
            conn.execute(
                """
                UPDATE portfolios
                SET total_trades = ?, winning_trades = ?, losing_trades = ?, realized_pnl = ?
                WHERE id = ?
                """,
                (new_total_trades, new_winning, new_losing, str(new_pnl), portfolio_id),
            )

    def delete_portfolio(self, portfolio_id: str) -> None:
        """Permanently delete a portfolio and its associated data."""
        with self.db.connect() as conn:
            conn.execute("DELETE FROM portfolio_snapshots WHERE portfolio_id = ?", (portfolio_id,))
            conn.execute("DELETE FROM portfolio_decisions WHERE portfolio_id = ?", (portfolio_id,))
            conn.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))

    def delete_all_data(self) -> None:
        """Delete **all** portfolio data (use with caution)."""
        with self.db.connect() as conn:
            conn.execute("DELETE FROM portfolio_snapshots")
            conn.execute("DELETE FROM portfolio_decisions")
            conn.execute("DELETE FROM portfolios")


# ---------------------------------------------------------------------------
# SQLiteDecisionStore
# ---------------------------------------------------------------------------


class SQLiteDecisionStore:
    """SQLite implementation of ``DecisionStore`` protocol.

    Every material AI decision is persisted for full audit trail and
    reproducibility.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _row_to_decision(row: Row) -> PortfolioDecision:
        """Convert a database row to a ``PortfolioDecision``."""
        return PortfolioDecision(
            id=row["id"],
            portfolio_id=row["portfolio_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            phase=row["phase"],
            decision_type=DecisionType(row["decision_type"]),
            symbol=row["symbol"],
            thesis_id=row["thesis_id"],
            dd_report_id=row["dd_report_id"],
            position_id=row["position_id"],
            event_id=row["event_id"],
            action=row["action"],
            reasoning=row["reasoning"],
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            amount=Decimal(row["amount"]) if row["amount"] is not None else None,
            shares=Decimal(row["shares"]) if row["shares"] is not None else None,
            price=Decimal(row["price"]) if row["price"] is not None else None,
            outcome=row["outcome"],
            outcome_details=json.loads(row["outcome_details"]) if row["outcome_details"] else None,
        )

    # -- protocol methods ----------------------------------------------------

    def log_decision(self, decision: PortfolioDecision) -> str:
        """Persist an auditable decision record.

        Returns:
            The decision ID.
        """
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_decisions (
                    id, portfolio_id, timestamp, phase, decision_type, symbol,
                    thesis_id, dd_report_id, position_id, event_id,
                    action, reasoning, confidence,
                    amount, shares, price,
                    outcome, outcome_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.id,
                    decision.portfolio_id,
                    decision.timestamp.isoformat(),
                    decision.phase,
                    decision.decision_type.value,
                    decision.symbol,
                    decision.thesis_id,
                    decision.dd_report_id,
                    decision.position_id,
                    decision.event_id,
                    decision.action,
                    decision.reasoning,
                    decision.confidence,
                    str(decision.amount) if decision.amount is not None else None,
                    str(decision.shares) if decision.shares is not None else None,
                    str(decision.price) if decision.price is not None else None,
                    decision.outcome,
                    json.dumps(decision.outcome_details) if decision.outcome_details is not None else None,
                ),
            )
        return decision.id

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

        Returns:
            List of matching decisions, most recent first.
        """
        query = "SELECT * FROM portfolio_decisions WHERE portfolio_id = ?"
        params: list[object] = [portfolio_id]
        if decision_types is not None:
            placeholders = ", ".join("?" for _ in decision_types)
            query += f" AND decision_type IN ({placeholders})"
            params.extend(decision_types)
        elif decision_type is not None:
            query += " AND decision_type = ?"
            params.append(decision_type)
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self.db.connect() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [self._row_to_decision(r) for r in rows]

    def get_full_audit_trail(
        self,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PortfolioDecision]:
        """Return the complete decision history for a portfolio.

        Returns:
            Full ordered list of decisions within the date window.
        """
        query = "SELECT * FROM portfolio_decisions WHERE portfolio_id = ?"
        params: list[object] = [portfolio_id]
        if start_date is not None:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        if end_date is not None:
            # Include the full end day
            query += " AND timestamp < ?"
            params.append(end_date.isoformat() + "T23:59:59.999999")
        query += " ORDER BY timestamp ASC"
        with self.db.connect() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [self._row_to_decision(r) for r in rows]


# ---------------------------------------------------------------------------
# SQLiteSnapshotStore
# ---------------------------------------------------------------------------


class SQLiteSnapshotStore:
    """SQLite implementation of ``SnapshotStore`` protocol.

    Captures daily portfolio value snapshots for equity-curve
    construction and drawdown analysis.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _row_to_snapshot(row: Row) -> PortfolioSnapshot:
        """Convert a database row to a ``PortfolioSnapshot``."""
        return PortfolioSnapshot(
            id=row["id"],
            portfolio_id=row["portfolio_id"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            portfolio_value=Decimal(row["portfolio_value"]),
            cash=Decimal(row["cash"]),
            positions_value=Decimal(row["positions_value"]),
            daily_pnl=Decimal(row["daily_pnl"]),
            daily_pnl_pct=float(row["daily_pnl_pct"]),
            cumulative_pnl=Decimal(row["cumulative_pnl"]),
            cumulative_pnl_pct=float(row["cumulative_pnl_pct"]),
            open_positions=int(row["open_positions"]),
            trades_today=int(row["trades_today"]),
        )

    # -- protocol methods ----------------------------------------------------

    def take_snapshot(self, snapshot: PortfolioSnapshot) -> str:
        """Persist a portfolio snapshot (INSERT OR REPLACE on portfolio_id + snapshot_date).

        Returns:
            The snapshot ID.
        """
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO portfolio_snapshots (
                    id, portfolio_id, snapshot_date, timestamp,
                    portfolio_value, cash, positions_value,
                    daily_pnl, daily_pnl_pct,
                    cumulative_pnl, cumulative_pnl_pct,
                    open_positions, trades_today
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.portfolio_id,
                    snapshot.snapshot_date.isoformat(),
                    snapshot.timestamp.isoformat(),
                    str(snapshot.portfolio_value),
                    str(snapshot.cash),
                    str(snapshot.positions_value),
                    str(snapshot.daily_pnl),
                    snapshot.daily_pnl_pct,
                    str(snapshot.cumulative_pnl),
                    snapshot.cumulative_pnl_pct,
                    snapshot.open_positions,
                    snapshot.trades_today,
                ),
            )
        return snapshot.id

    def get_snapshots(
        self,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PortfolioSnapshot]:
        """Retrieve snapshots for a portfolio within a date window.

        Returns:
            List of snapshots ordered by date ascending.
        """
        query = "SELECT * FROM portfolio_snapshots WHERE portfolio_id = ?"
        params: list[object] = [portfolio_id]
        if start_date is not None:
            query += " AND snapshot_date >= ?"
            params.append(start_date.isoformat())
        if end_date is not None:
            query += " AND snapshot_date <= ?"
            params.append(end_date.isoformat())
        query += " ORDER BY snapshot_date ASC"
        with self.db.connect() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [self._row_to_snapshot(r) for r in rows]
