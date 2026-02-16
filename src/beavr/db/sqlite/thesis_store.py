"""SQLite implementation of ThesisStore."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from beavr.models.thesis import (
    ThesisStatus,
    ThesisSummary,
    TradeDirection,
    TradeThesis,
    TradeType,
)

if TYPE_CHECKING:
    from beavr.db.sqlite.connection import Database


class SQLiteThesisStore:
    """
    SQLite implementation of the ThesisStore protocol.

    Manages the lifecycle of trade theses from draft through
    execution to closure or invalidation.
    """

    def __init__(self, db: Database) -> None:
        """Initialize the store."""
        self.db = db

    def save_thesis(self, thesis: TradeThesis) -> str:
        """
        Save a new thesis.

        Args:
            thesis: TradeThesis model to persist

        Returns:
            Thesis ID
        """
        invalidation_json = json.dumps(thesis.invalidation_conditions)

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO trade_theses
                (id, symbol, created_at, trade_type, direction, entry_rationale,
                 catalyst, catalyst_date, entry_price_target, profit_target,
                 stop_loss, expected_exit_date, max_hold_date, invalidation_conditions,
                 status, confidence, dd_approved, dd_report_id, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thesis.id,
                    thesis.symbol,
                    thesis.created_at.isoformat(),
                    thesis.trade_type.value,
                    thesis.direction.value,
                    thesis.entry_rationale,
                    thesis.catalyst,
                    thesis.catalyst_date.isoformat() if thesis.catalyst_date else None,
                    float(thesis.entry_price_target),
                    float(thesis.profit_target),
                    float(thesis.stop_loss),
                    thesis.expected_exit_date.isoformat(),
                    thesis.max_hold_date.isoformat(),
                    invalidation_json,
                    thesis.status.value,
                    thesis.confidence,
                    int(thesis.dd_approved),
                    thesis.dd_report_id,
                    thesis.source,
                    thesis.notes,
                ),
            )

        return thesis.id

    def get_thesis(self, thesis_id: str) -> Optional[TradeThesis]:
        """
        Get a thesis by ID.

        Args:
            thesis_id: Thesis ID

        Returns:
            TradeThesis or None
        """
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trade_theses WHERE id = ?",
                (thesis_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_thesis(row)

    def get_theses_by_symbol(self, symbol: str, status: Optional[ThesisStatus] = None) -> list[TradeThesis]:
        """
        Get theses for a symbol.

        Args:
            symbol: Trading symbol
            status: Optional status filter

        Returns:
            List of theses
        """
        with self.db.connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM trade_theses WHERE symbol = ? AND status = ? ORDER BY created_at DESC",
                    (symbol, status.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trade_theses WHERE symbol = ? ORDER BY created_at DESC",
                    (symbol,),
                ).fetchall()

        return [self._row_to_thesis(row) for row in rows]

    def get_active_theses(self, portfolio_id: Optional[str] = None) -> list[TradeThesis]:  # noqa: ARG002
        """
        Get all active theses (ready for execution).

        Args:
            portfolio_id: Optional portfolio ID filter (not yet implemented)

        Returns:
            List of active theses
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trade_theses 
                WHERE status IN ('draft', 'active') 
                ORDER BY confidence DESC, created_at DESC
                """,
            ).fetchall()

        return [self._row_to_thesis(row) for row in rows]

    def get_pending_dd(self, portfolio_id: Optional[str] = None) -> list[TradeThesis]:  # noqa: ARG002
        """
        Get theses awaiting DD approval.

        Args:
            portfolio_id: Optional portfolio ID filter (not yet implemented)

        Returns:
            List of theses needing DD
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trade_theses 
                WHERE status = 'active' AND dd_approved = 0
                ORDER BY confidence DESC
                """,
            ).fetchall()

        return [self._row_to_thesis(row) for row in rows]

    def get_theses_by_catalyst_date(self, target_date: date) -> list[TradeThesis]:
        """
        Get theses with catalyst on a specific date.

        Args:
            target_date: Catalyst date to search for

        Returns:
            List of matching theses
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trade_theses 
                WHERE catalyst_date = ? AND status IN ('draft', 'active', 'executed')
                ORDER BY confidence DESC
                """,
                (target_date.isoformat(),),
            ).fetchall()

        return [self._row_to_thesis(row) for row in rows]

    def update_thesis_status(self, thesis_id: str, status: ThesisStatus, position_id: Optional[int] = None) -> bool:
        """
        Update thesis status.

        Args:
            thesis_id: Thesis ID
            status: New status
            position_id: Optional position ID (when executed)

        Returns:
            True if updated
        """
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE trade_theses 
                SET status = ?, position_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, position_id, datetime.now().isoformat(), thesis_id),
            )
            return result.rowcount > 0

    def approve_dd(self, thesis_id: str, dd_report_id: str) -> bool:
        """
        Mark thesis as DD approved.

        Args:
            thesis_id: Thesis ID
            dd_report_id: DD report ID

        Returns:
            True if updated
        """
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE trade_theses 
                SET dd_approved = 1, dd_report_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (dd_report_id, datetime.now().isoformat(), thesis_id),
            )
            return result.rowcount > 0

    def update_thesis_confidence(self, thesis_id: str, confidence: float) -> bool:
        """
        Update thesis confidence level.

        Args:
            thesis_id: Thesis ID
            confidence: New confidence (0.0-1.0)

        Returns:
            True if updated
        """
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE trade_theses 
                SET confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (confidence, datetime.now().isoformat(), thesis_id),
            )
            return result.rowcount > 0

    def update_thesis(self, thesis: TradeThesis) -> bool:
        """
        Update a thesis with all its current values.

        Args:
            thesis: The thesis to update

        Returns:
            True if updated
        """
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE trade_theses 
                SET status = ?, confidence = ?, entry_price_target = ?, 
                    profit_target = ?, stop_loss = ?, dd_approved = ?,
                    dd_report_id = ?, position_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    thesis.status.value,
                    thesis.confidence,
                    str(thesis.entry_price_target) if thesis.entry_price_target else None,
                    str(thesis.profit_target) if thesis.profit_target else None,
                    str(thesis.stop_loss) if thesis.stop_loss else None,
                    int(thesis.dd_approved),
                    thesis.dd_report_id,
                    thesis.position_id,
                    datetime.now().isoformat(),
                    thesis.id,
                ),
            )
            return result.rowcount > 0

    def get_thesis_summaries(self, limit: int = 50) -> list[ThesisSummary]:
        """
        Get thesis summaries for display.

        Args:
            limit: Maximum summaries to return

        Returns:
            List of ThesisSummary
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, symbol, direction, trade_type, status, catalyst,
                       catalyst_date, confidence, dd_approved, created_at
                FROM trade_theses
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        summaries = []
        for row in rows:
            summaries.append(ThesisSummary(
                id=row[0],
                symbol=row[1],
                direction=TradeDirection(row[2]),
                trade_type=TradeType(row[3]),
                status=ThesisStatus(row[4]),
                catalyst=row[5],
                catalyst_date=date.fromisoformat(row[6]) if row[6] else None,
                confidence=row[7],
                dd_approved=bool(row[8]),
                created_at=datetime.fromisoformat(row[9]),
            ))

        return summaries

    def _row_to_thesis(self, row: tuple) -> TradeThesis:
        """Convert database row to TradeThesis."""
        # Row order matches SELECT * column order
        invalidation = json.loads(row[13]) if row[13] else []

        return TradeThesis(
            id=row[0],
            symbol=row[1],
            created_at=datetime.fromisoformat(row[2]),
            trade_type=TradeType(row[3]),
            direction=TradeDirection(row[4]),
            entry_rationale=row[5],
            catalyst=row[6],
            catalyst_date=date.fromisoformat(row[7]) if row[7] else None,
            entry_price_target=Decimal(str(row[8])),
            profit_target=Decimal(str(row[9])),
            stop_loss=Decimal(str(row[10])),
            expected_exit_date=date.fromisoformat(row[11]),
            max_hold_date=date.fromisoformat(row[12]),
            invalidation_conditions=invalidation,
            status=ThesisStatus(row[14]),
            confidence=row[15],
            dd_approved=bool(row[16]),
            dd_report_id=row[17],
            source=row[18],
            notes=row[19],
            position_id=row[20] if len(row) > 20 else None,
        )
