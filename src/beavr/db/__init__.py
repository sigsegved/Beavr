"""Database layer for SQLite persistence."""

from beavr.db.ai_positions import AIPosition, AIPositionsRepository, AITrade
from beavr.db.cache import BarCache
from beavr.db.connection import Database
from beavr.db.dd_reports_repo import DDReportsRepository
from beavr.db.events_repo import EventsRepository
from beavr.db.results import BacktestMetrics, BacktestResultsRepository
from beavr.db.schema import SCHEMA_SQL, SCHEMA_VERSION
from beavr.db.schema_v2 import SCHEMA_V2_SQL, SCHEMA_V2_VERSION
from beavr.db.thesis_repo import ThesisRepository

__all__ = [
    # Original
    "AIPosition",
    "AIPositionsRepository",
    "AITrade",
    "BacktestMetrics",
    "BacktestResultsRepository",
    "BarCache",
    "Database",
    "SCHEMA_SQL",
    "SCHEMA_VERSION",
    # V2 additions
    "DDReportsRepository",
    "EventsRepository",
    "SCHEMA_V2_SQL",
    "SCHEMA_V2_VERSION",
    "ThesisRepository",
]

