"""Factory for creating store bundles backed by different storage engines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from beavr.db.protocols import (
        BarCacheStore,
        DDReportStore,
        EventStore,
        ThesisStore,
    )


@dataclass
class StoreBundle:
    """All stores wired to the same backend.

    Provides convenient access to all repository stores
    from a single object. Used at composition roots (CLI, tests)
    to wire up the full dependency graph.
    """

    theses: ThesisStore
    dd_reports: DDReportStore
    events: EventStore
    bar_cache: BarCacheStore


def create_sqlite_stores(db_path: Optional[str] = None) -> StoreBundle:
    """Create all stores backed by SQLite.

    Args:
        db_path: Optional path to SQLite database file.
                 If None, uses the default path from AppConfig.
                 Use ":memory:" for in-memory testing.

    Returns:
        StoreBundle with all stores wired to the same SQLite database.
    """
    from beavr.db.sqlite.bar_cache_store import SQLiteBarCacheStore
    from beavr.db.sqlite.connection import Database
    from beavr.db.sqlite.dd_report_store import SQLiteDDReportStore
    from beavr.db.sqlite.event_store import SQLiteEventStore
    from beavr.db.sqlite.thesis_store import SQLiteThesisStore

    db = Database(db_path)
    return StoreBundle(
        theses=SQLiteThesisStore(db),
        dd_reports=SQLiteDDReportStore(db),
        events=SQLiteEventStore(db),
        bar_cache=SQLiteBarCacheStore(db),
    )
