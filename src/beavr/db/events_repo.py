"""Repository for market events."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from beavr.models.market_event import (
    EventImportance,
    EventSummary,
    EventType,
    MarketEvent,
)

if TYPE_CHECKING:
    from beavr.db.connection import Database


class EventsRepository:
    """
    Repository for market event CRUD operations.
    
    Manages events from the News Monitor, tracking their
    processing status and thesis generation.
    """
    
    def __init__(self, db: Database) -> None:
        """Initialize the repository."""
        self.db = db
    
    def create(self, event: MarketEvent) -> str:
        """
        Store a new market event.
        
        Args:
            event: MarketEvent to persist
            
        Returns:
            Event ID
        """
        raw_data_json = json.dumps(event.raw_data) if event.raw_data else None
        
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO market_events
                (id, event_type, symbol, headline, summary, source, url, timestamp,
                 event_date, importance, earnings_date, estimate_eps, actual_eps,
                 estimate_revenue, actual_revenue, analyst_firm, old_rating, new_rating,
                 old_price_target, new_price_target, insider_name, insider_title,
                 transaction_value, processed, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.event_type.value,
                    event.symbol,
                    event.headline,
                    event.summary,
                    event.source,
                    event.url,
                    event.timestamp.isoformat(),
                    event.event_date.isoformat() if event.event_date else None,
                    event.importance.value,
                    event.earnings_date.isoformat() if event.earnings_date else None,
                    float(event.estimate_eps) if event.estimate_eps else None,
                    float(event.actual_eps) if event.actual_eps else None,
                    float(event.estimate_revenue) if event.estimate_revenue else None,
                    float(event.actual_revenue) if event.actual_revenue else None,
                    event.analyst_firm,
                    event.old_rating,
                    event.new_rating,
                    float(event.old_price_target) if event.old_price_target else None,
                    float(event.new_price_target) if event.new_price_target else None,
                    event.insider_name,
                    event.insider_title,
                    float(event.transaction_value) if event.transaction_value else None,
                    int(event.processed),
                    raw_data_json,
                ),
            )
        
        return event.id
    
    def get(self, event_id: str) -> Optional[MarketEvent]:
        """
        Get an event by ID.
        
        Args:
            event_id: Event ID
            
        Returns:
            MarketEvent or None
        """
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM market_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_event(row)
    
    def get_recent(
        self,
        limit: int = 50,
        importance: Optional[EventImportance] = None,
        event_type: Optional[EventType] = None,
    ) -> list[MarketEvent]:
        """
        Get recent events with optional filters.
        
        Args:
            limit: Maximum events to return
            importance: Filter by importance level
            event_type: Filter by event type
            
        Returns:
            List of events
        """
        query = "SELECT * FROM market_events WHERE 1=1"
        params: list = []
        
        if importance:
            query += " AND importance = ?"
            params.append(importance.value)
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_by_symbol(self, symbol: str, limit: int = 20) -> list[MarketEvent]:
        """
        Get events for a specific symbol.
        
        Args:
            symbol: Trading symbol
            limit: Maximum events to return
            
        Returns:
            List of events for the symbol
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM market_events 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (symbol, limit),
            ).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_unprocessed(self, min_importance: EventImportance = EventImportance.MEDIUM) -> list[MarketEvent]:
        """
        Get events that haven't been processed yet.
        
        Args:
            min_importance: Minimum importance level
            
        Returns:
            List of unprocessed events
        """
        # Order importance: high > medium > low
        importance_order = {
            EventImportance.HIGH: 3,
            EventImportance.MEDIUM: 2,
            EventImportance.LOW: 1,
        }
        min_order = importance_order.get(min_importance, 2)
        
        valid_importances = [
            imp.value for imp, order in importance_order.items()
            if order >= min_order
        ]
        
        placeholders = ",".join("?" * len(valid_importances))
        
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM market_events 
                WHERE processed = 0 AND importance IN ({placeholders})
                ORDER BY 
                    CASE importance 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        ELSE 3 
                    END,
                    timestamp DESC
                """,
                valid_importances,
            ).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def mark_processed(self, event_id: str, thesis_id: Optional[str] = None) -> bool:
        """
        Mark an event as processed.
        
        Args:
            event_id: Event ID
            thesis_id: Optional thesis ID if thesis was generated
            
        Returns:
            True if updated
        """
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE market_events 
                SET processed = 1, processed_at = ?, thesis_generated = ?, thesis_id = ?
                WHERE id = ?
                """,
                (
                    datetime.now().isoformat(),
                    1 if thesis_id else 0,
                    thesis_id,
                    event_id,
                ),
            )
            return result.rowcount > 0
    
    def get_upcoming_earnings(self, days_ahead: int = 7) -> list[MarketEvent]:
        """
        Get upcoming earnings events.
        
        Args:
            days_ahead: Number of days to look ahead
            
        Returns:
            List of upcoming earnings events
        """
        today = date.today()
        end_date = date.today().replace(day=today.day + days_ahead)
        
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM market_events 
                WHERE event_type = 'earnings_upcoming'
                  AND earnings_date >= ?
                  AND earnings_date <= ?
                ORDER BY earnings_date ASC
                """,
                (today.isoformat(), end_date.isoformat()),
            ).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_summaries(self, limit: int = 50) -> list[EventSummary]:
        """
        Get event summaries for display.
        
        Args:
            limit: Maximum summaries to return
            
        Returns:
            List of EventSummary
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, event_type, symbol, headline, importance, timestamp, processed
                FROM market_events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        
        return [
            EventSummary(
                id=row[0],
                event_type=EventType(row[1]),
                symbol=row[2],
                headline=row[3],
                importance=EventImportance(row[4]),
                timestamp=datetime.fromisoformat(row[5]),
                processed=bool(row[6]),
            )
            for row in rows
        ]
    
    def _row_to_event(self, row: tuple) -> MarketEvent:
        """Convert database row to MarketEvent."""
        raw_data = json.loads(row[25]) if row[25] else None
        
        return MarketEvent(
            id=row[0],
            event_type=EventType(row[1]),
            symbol=row[2],
            headline=row[3],
            summary=row[4],
            source=row[5],
            url=row[6],
            timestamp=datetime.fromisoformat(row[7]),
            event_date=date.fromisoformat(row[8]) if row[8] else None,
            importance=EventImportance(row[9]),
            earnings_date=date.fromisoformat(row[10]) if row[10] else None,
            estimate_eps=Decimal(str(row[11])) if row[11] else None,
            actual_eps=Decimal(str(row[12])) if row[12] else None,
            estimate_revenue=Decimal(str(row[13])) if row[13] else None,
            actual_revenue=Decimal(str(row[14])) if row[14] else None,
            analyst_firm=row[15],
            old_rating=row[16],
            new_rating=row[17],
            old_price_target=Decimal(str(row[18])) if row[18] else None,
            new_price_target=Decimal(str(row[19])) if row[19] else None,
            insider_name=row[20],
            insider_title=row[21],
            transaction_value=Decimal(str(row[22])) if row[22] else None,
            processed=bool(row[23]),
            processed_at=datetime.fromisoformat(row[24]) if row[24] else None,
            raw_data=raw_data,
        )
