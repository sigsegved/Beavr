"""SQLite database connection management."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Generator, Optional, Union

from beavr.db.sqlite.schema import SCHEMA_SQL
from beavr.db.sqlite.schema_v2 import SCHEMA_V2_SQL

if TYPE_CHECKING:
    from sqlite3 import Connection


class Database:
    """
    SQLite database connection manager.

    Handles connection lifecycle, schema initialization, and transactions.

    Attributes:
        db_path: Path to the SQLite database file or ":memory:" for in-memory
    """

    def __init__(self, db_path: Optional[Union[Path, str]] = None):
        """
        Initialize the database.

        Args:
            db_path: Path to database file or ":memory:" for in-memory database.
                     If None, uses the default path from AppConfig.
        """
        if db_path is None:
            from beavr.models.config import AppConfig
            config = AppConfig()
            db_path = config.database_path

        # Convert to string for sqlite3
        self.db_path = str(db_path) if isinstance(db_path, Path) else db_path
        self._is_memory = self.db_path == ":memory:"

        # For in-memory databases, keep a persistent connection
        self._memory_conn: Optional[Connection] = None

        if not self._is_memory:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            # Also apply v2 schema for AI Investor thesis support
            conn.executescript(SCHEMA_V2_SQL)

    @contextmanager
    def connect(self) -> Generator[Connection, None, None]:
        """
        Get a database connection as a context manager.

        Handles transaction commit/rollback automatically.
        Returns dict-like Row objects for query results.

        For in-memory databases, reuses the same connection.
        For file databases, creates a new connection each time.

        Example:
            with db.connect() as conn:
                cursor = conn.execute("SELECT * FROM bars")
                rows = cursor.fetchall()
        """
        if self._is_memory:
            # For in-memory databases, use a persistent connection
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:")
                self._memory_conn.row_factory = sqlite3.Row
            try:
                yield self._memory_conn
                self._memory_conn.commit()
            except Exception:
                self._memory_conn.rollback()
                raise
        else:
            # For file databases, create a new connection
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Execute a single SQL statement.

        For simple queries that don't need explicit transaction control.

        Args:
            sql: SQL statement to execute
            params: Parameters for the statement

        Returns:
            Cursor with query results
        """
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor

    def executemany(self, sql: str, params_list: list) -> None:
        """
        Execute a SQL statement with multiple parameter sets.

        Useful for bulk inserts.

        Args:
            sql: SQL statement to execute
            params_list: List of parameter tuples
        """
        with self.connect() as conn:
            conn.executemany(sql, params_list)

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            return cursor.fetchone() is not None

    def get_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table."""
        with self.connect() as conn:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
            result = cursor.fetchone()
            return result[0] if result else 0

    def close(self) -> None:
        """Close the database connection (for in-memory databases)."""
        if self._memory_conn is not None:
            self._memory_conn.close()
            self._memory_conn = None
