"""Unit tests for SQLite database connection and schema."""

import tempfile
from pathlib import Path

import pytest

from beavr.db import SCHEMA_VERSION, Database


class TestDatabase:
    """Tests for the Database class."""

    def test_in_memory_database(self) -> None:
        """Test creating an in-memory database."""
        db = Database(":memory:")
        assert db.db_path == ":memory:"
        assert db._is_memory is True
        db.close()

    def test_schema_created(self) -> None:
        """Test that schema tables are created."""
        db = Database(":memory:")

        # Check that all tables exist
        assert db.table_exists("bars")
        assert db.table_exists("backtest_runs")
        assert db.table_exists("backtest_results")
        assert db.table_exists("backtest_trades")
        db.close()

    def test_schema_is_idempotent(self) -> None:
        """Test that schema can be applied multiple times."""
        db = Database(":memory:")

        # Apply schema again - should not raise
        db._init_schema()
        db._init_schema()

        # Tables should still exist
        assert db.table_exists("bars")
        db.close()

    def test_context_manager_commit(self) -> None:
        """Test that context manager commits on success."""
        db = Database(":memory:")

        with db.connect() as conn:
            conn.execute("""
                INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                VALUES ('SPY', '2024-01-15', 450.0, 455.0, 448.0, 453.5, 1000000, '1Day')
            """)

        # Data should be persisted
        assert db.get_row_count("bars") == 1
        db.close()

    def test_context_manager_rollback(self) -> None:
        """Test that context manager rolls back on exception."""
        db = Database(":memory:")

        try:
            with db.connect() as conn:
                conn.execute("""
                    INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                    VALUES ('SPY', '2024-01-15', 450.0, 455.0, 448.0, 453.5, 1000000, '1Day')
                """)
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Data should NOT be persisted
        assert db.get_row_count("bars") == 0
        db.close()

    def test_row_factory(self) -> None:
        """Test that row factory returns dict-like objects."""
        db = Database(":memory:")

        with db.connect() as conn:
            conn.execute("""
                INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                VALUES ('SPY', '2024-01-15', 450.0, 455.0, 448.0, 453.5, 1000000, '1Day')
            """)

        with db.connect() as conn:
            cursor = conn.execute("SELECT * FROM bars")
            row = cursor.fetchone()

        # Row should be dict-like
        assert row["symbol"] == "SPY"
        assert row["close"] == 453.5
        assert row["volume"] == 1000000
        db.close()

    def test_execute_simple_query(self) -> None:
        """Test the execute helper method."""
        db = Database(":memory:")

        with db.connect() as conn:
            conn.execute("""
                INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                VALUES ('SPY', '2024-01-15', 450.0, 455.0, 448.0, 453.5, 1000000, '1Day')
            """)

        cursor = db.execute("SELECT COUNT(*) FROM bars")
        result = cursor.fetchone()
        assert result[0] == 1
        db.close()

    def test_executemany(self) -> None:
        """Test bulk insert with executemany."""
        db = Database(":memory:")

        bars = [
            ("SPY", "2024-01-15", 450.0, 455.0, 448.0, 453.5, 1000000, "1Day"),
            ("SPY", "2024-01-16", 453.0, 458.0, 451.0, 456.5, 1100000, "1Day"),
            ("SPY", "2024-01-17", 456.0, 460.0, 454.0, 458.5, 1200000, "1Day"),
        ]

        db.executemany("""
            INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, bars)

        assert db.get_row_count("bars") == 3
        db.close()

    def test_file_database(self) -> None:
        """Test creating a file-based database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)

            # File should exist
            assert db_path.exists()

            # Insert some data
            with db.connect() as conn:
                conn.execute("""
                    INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                    VALUES ('SPY', '2024-01-15', 450.0, 455.0, 448.0, 453.5, 1000000, '1Day')
                """)

            # Create new connection to same file
            db2 = Database(db_path)
            assert db2.get_row_count("bars") == 1

    def test_nested_directory_creation(self) -> None:
        """Test that nested directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nested" / "dir" / "test.db"
            db = Database(db_path)

            # File should exist in nested directory
            assert db_path.exists()
            assert db_path.parent.exists()

    def test_unique_constraint(self) -> None:
        """Test that unique constraint on bars is enforced."""
        db = Database(":memory:")

        with db.connect() as conn:
            conn.execute("""
                INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                VALUES ('SPY', '2024-01-15', 450.0, 455.0, 448.0, 453.5, 1000000, '1Day')
            """)

        # Inserting duplicate should fail
        with pytest.raises(Exception), db.connect() as conn:
            conn.execute("""
                    INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                    VALUES ('SPY', '2024-01-15', 460.0, 465.0, 458.0, 463.5, 1100000, '1Day')
                """)
        db.close()


class TestSchemaVersion:
    """Tests for schema versioning."""

    def test_schema_version_exists(self) -> None:
        """Test that schema version is defined."""
        assert SCHEMA_VERSION == 1
