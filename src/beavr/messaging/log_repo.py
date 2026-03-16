"""Repository for messaging audit logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from beavr.db.connection import Database

logger = logging.getLogger(__name__)


class MessagingLogRepository:
    """Repository for messaging audit log CRUD operations.

    Stores every inbound command and outbound notification for audit.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def log_outbound(
        self,
        *,
        platform: str,
        notification_type: str,
        priority: str,
        message_text: str,
        symbol: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Log an outbound notification.

        Returns:
            The log entry ID.
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messaging_log
                (direction, platform, notification_type, priority,
                 raw_text, symbol, success, error_message, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "outbound",
                    platform,
                    notification_type,
                    priority,
                    message_text,
                    symbol,
                    1 if success else 0,
                    error_message,
                    datetime.utcnow().isoformat(),
                    json.dumps(metadata) if metadata else None,
                ),
            )
            return cursor.lastrowid or 0

    def log_inbound(
        self,
        *,
        platform: str,
        sender_id: str,
        command: str,
        raw_text: str,
        response_text: Optional[str] = None,
        symbol: Optional[str] = None,
        is_verified: bool = False,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Log an inbound command with its response.

        Returns:
            The log entry ID.
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messaging_log
                (direction, platform, sender_id, command, raw_text,
                 response_text, symbol, is_verified, success,
                 error_message, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "inbound",
                    platform,
                    sender_id,
                    command,
                    raw_text,
                    response_text,
                    symbol,
                    1 if is_verified else 0,
                    1 if success else 0,
                    error_message,
                    datetime.utcnow().isoformat(),
                    json.dumps(metadata) if metadata else None,
                ),
            )
            return cursor.lastrowid or 0

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent log entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of log entry dicts, newest first.
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, direction, platform, sender_id, notification_type,
                       priority, command, raw_text, response_text, symbol,
                       is_verified, success, error_message, timestamp, metadata
                FROM messaging_log
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
