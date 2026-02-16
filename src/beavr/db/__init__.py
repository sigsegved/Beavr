"""Database layer — Protocol interfaces + SQLite implementations.

Usage:
    # Protocol types (for type hints in business logic)
    from beavr.db.protocols import ThesisStore, DDReportStore, EventStore

    # SQLite implementations (for composition roots)
    from beavr.db.sqlite import SQLiteThesisStore, SQLiteDDReportStore

    # Factory (convenience)
    from beavr.db.factory import create_sqlite_stores

Backward-compatible re-exports from original file locations are provided
below so existing code continues to work without import changes.
"""

# --- Backward-compatible re-exports (original locations) ---
# These keep existing imports like `from beavr.db import ThesisRepository` working.
from beavr.db.ai_positions import AIPosition, AIPositionsRepository, AITrade
from beavr.db.cache import BarCache
from beavr.db.connection import Database
from beavr.db.dd_reports_repo import DDReportsRepository
from beavr.db.events_repo import EventsRepository

# --- Factory ---
from beavr.db.factory import StoreBundle, create_sqlite_stores

# --- New Protocol re-exports ---
from beavr.db.protocols import (
    BarCacheStore,
    DDReportStore,
    DecisionStore,
    EventStore,
    PortfolioStore,
    SnapshotStore,
    ThesisStore,
)
from beavr.db.results import BacktestMetrics, BacktestResultsRepository
from beavr.db.schema import SCHEMA_SQL, SCHEMA_VERSION
from beavr.db.schema_v2 import SCHEMA_V2_SQL, SCHEMA_V2_VERSION
from beavr.db.thesis_repo import ThesisRepository

__all__ = [
    # Original (backward compat)
    "AIPosition",
    "AIPositionsRepository",
    "AITrade",
    "BacktestMetrics",
    "BacktestResultsRepository",
    "BarCache",
    "Database",
    "SCHEMA_SQL",
    "SCHEMA_VERSION",
    "DDReportsRepository",
    "EventsRepository",
    "SCHEMA_V2_SQL",
    "SCHEMA_V2_VERSION",
    "ThesisRepository",
    # Protocols
    "BarCacheStore",
    "DDReportStore",
    "DecisionStore",
    "EventStore",
    "PortfolioStore",
    "SnapshotStore",
    "ThesisStore",
    # Factory
    "StoreBundle",
    "create_sqlite_stores",
]

