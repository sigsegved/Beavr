"""Tests for LLM usage tracking."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from beavr.llm.usage import UsageRecord, UsageTracker


class TestUsageRecord:
    """Tests for UsageRecord dataclass."""

    def test_create_minimal(self) -> None:
        """Record can be created with required fields only."""
        rec = UsageRecord(
            timestamp="2025-01-15T10:00:00+00:00",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
        )
        assert rec.model == "gpt-4o"
        assert rec.input_tokens == 100
        assert rec.output_tokens == 50
        assert rec.cache_read_tokens == 0
        assert rec.cache_write_tokens == 0
        assert rec.cost is None
        assert rec.agent == ""

    def test_create_full(self) -> None:
        """Record can be created with all fields."""
        rec = UsageRecord(
            timestamp="2025-01-15T10:00:00+00:00",
            model="claude-sonnet-4-20250514",
            input_tokens=1500,
            output_tokens=800,
            cache_read_tokens=200,
            cache_write_tokens=100,
            cost=0.0042,
            agent="due_diligence",
        )
        assert rec.agent == "due_diligence"
        assert rec.cost == 0.0042
        assert rec.cache_read_tokens == 200


class TestUsageTracker:
    """Tests for UsageTracker."""

    @pytest.fixture
    def tracker(self, tmp_path: Path) -> UsageTracker:
        """Create a tracker with a temp directory."""
        # Reset singleton for test isolation
        UsageTracker._instance = None
        return UsageTracker(usage_dir=tmp_path)

    @pytest.fixture
    def sample_records(self) -> list[UsageRecord]:
        """Create sample usage records."""
        return [
            UsageRecord(
                timestamp="2025-01-15T09:00:00+00:00",
                model="gpt-4o-mini",
                input_tokens=500,
                output_tokens=200,
                agent="news_monitor",
            ),
            UsageRecord(
                timestamp="2025-01-15T10:00:00+00:00",
                model="gpt-4o",
                input_tokens=1200,
                output_tokens=600,
                cost=0.003,
                agent="thesis_generator",
            ),
            UsageRecord(
                timestamp="2025-01-15T11:00:00+00:00",
                model="claude-sonnet-4-20250514",
                input_tokens=2000,
                output_tokens=1000,
                cache_read_tokens=300,
                cost=0.008,
                agent="due_diligence",
            ),
            UsageRecord(
                timestamp="2025-01-16T09:00:00+00:00",
                model="gpt-4o-mini",
                input_tokens=400,
                output_tokens=150,
                agent="morning_scanner",
            ),
        ]

    # ===== record & get_records =====

    def test_record_creates_file(self, tracker: UsageTracker) -> None:
        """Recording creates the JSONL file."""
        rec = UsageRecord(
            timestamp="2025-01-15T10:00:00+00:00",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
        )
        tracker.record(rec)
        assert tracker._usage_file.exists()

    def test_record_appends_jsonl(self, tracker: UsageTracker) -> None:
        """Multiple records are appended as separate lines."""
        for i in range(3):
            tracker.record(UsageRecord(
                timestamp=f"2025-01-15T1{i}:00:00+00:00",
                model="gpt-4o",
                input_tokens=100 * (i + 1),
                output_tokens=50,
            ))
        lines = tracker._usage_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_get_records_returns_all(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """get_records returns all saved records."""
        for rec in sample_records:
            tracker.record(rec)
        records = tracker.get_records()
        assert len(records) == 4

    def test_get_records_empty_file(self, tracker: UsageTracker) -> None:
        """get_records handles missing file gracefully."""
        records = tracker.get_records()
        assert records == []

    def test_get_records_since_filter(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """get_records filters by since date."""
        for rec in sample_records:
            tracker.record(rec)
        records = tracker.get_records(since=date(2025, 1, 16))
        assert len(records) == 1
        assert records[0].agent == "morning_scanner"

    def test_get_records_until_filter(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """get_records filters by until date."""
        for rec in sample_records:
            tracker.record(rec)
        records = tracker.get_records(until=date(2025, 1, 15))
        assert len(records) == 3

    def test_get_records_date_range(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """get_records filters by date range."""
        for rec in sample_records:
            tracker.record(rec)
        records = tracker.get_records(
            since=date(2025, 1, 15), until=date(2025, 1, 15)
        )
        assert len(records) == 3

    def test_get_records_skips_malformed_lines(self, tracker: UsageTracker) -> None:
        """get_records ignores corrupted lines."""
        tracker.record(UsageRecord(
            timestamp="2025-01-15T10:00:00+00:00",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
        ))
        # Append a bad line
        with open(tracker._usage_file, "a") as f:
            f.write("not valid json\n")
        records = tracker.get_records()
        assert len(records) == 1

    # ===== summarize =====

    def test_summarize_totals(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """summarize aggregates token counts correctly."""
        for rec in sample_records:
            tracker.record(rec)
        summary = tracker.summarize()
        assert summary.total_calls == 4
        assert summary.total_input_tokens == 500 + 1200 + 2000 + 400
        assert summary.total_output_tokens == 200 + 600 + 1000 + 150
        assert summary.total_cache_read_tokens == 300

    def test_summarize_cost(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """summarize aggregates cost as Decimal."""
        for rec in sample_records:
            tracker.record(rec)
        summary = tracker.summarize()
        assert summary.total_cost == Decimal("0.011")

    def test_summarize_by_model(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """summarize groups by model."""
        for rec in sample_records:
            tracker.record(rec)
        summary = tracker.summarize()
        assert "gpt-4o-mini" in summary.by_model
        assert summary.by_model["gpt-4o-mini"]["calls"] == 2
        assert summary.by_model["gpt-4o"]["calls"] == 1
        assert summary.by_model["claude-sonnet-4-20250514"]["calls"] == 1

    def test_summarize_by_agent(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """summarize groups by agent."""
        for rec in sample_records:
            tracker.record(rec)
        summary = tracker.summarize()
        assert len(summary.by_agent) == 4
        assert summary.by_agent["news_monitor"]["calls"] == 1

    def test_summarize_with_date_filter(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """summarize respects date filters."""
        for rec in sample_records:
            tracker.record(rec)
        summary = tracker.summarize(since=date(2025, 1, 16))
        assert summary.total_calls == 1
        assert summary.total_input_tokens == 400

    def test_summarize_empty(self, tracker: UsageTracker) -> None:
        """summarize returns zeros when no data."""
        summary = tracker.summarize()
        assert summary.total_calls == 0
        assert summary.total_input_tokens == 0
        assert summary.total_cost == Decimal("0")

    def test_summarize_timestamps(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """summarize tracks first and last call timestamps."""
        for rec in sample_records:
            tracker.record(rec)
        summary = tracker.summarize()
        assert summary.first_call == "2025-01-15T09:00:00+00:00"
        assert summary.last_call == "2025-01-16T09:00:00+00:00"

    # ===== summarize_daily =====

    def test_summarize_daily_groups_by_date(
        self, tracker: UsageTracker, sample_records: list[UsageRecord]
    ) -> None:
        """summarize_daily creates per-day summaries."""
        for rec in sample_records:
            tracker.record(rec)
        daily = tracker.summarize_daily()
        assert len(daily) == 2
        assert "2025-01-15" in daily
        assert "2025-01-16" in daily
        assert daily["2025-01-15"].total_calls == 3
        assert daily["2025-01-16"].total_calls == 1

    def test_summarize_daily_empty(self, tracker: UsageTracker) -> None:
        """summarize_daily returns empty dict when no data."""
        daily = tracker.summarize_daily()
        assert daily == {}

    # ===== singleton =====

    def test_get_instance_returns_same(self, tmp_path: Path) -> None:
        """get_instance returns the same tracker."""
        UsageTracker._instance = None
        t1 = UsageTracker.get_instance(usage_dir=tmp_path)
        t2 = UsageTracker.get_instance()
        assert t1 is t2
        # Cleanup
        UsageTracker._instance = None

    # ===== thread safety =====

    def test_concurrent_writes(self, tracker: UsageTracker) -> None:
        """Multiple threads can write concurrently without corruption."""
        import threading

        def write_records(start: int) -> None:
            for i in range(10):
                tracker.record(UsageRecord(
                    timestamp=f"2025-01-15T{10 + start}:{i:02d}:00+00:00",
                    model="gpt-4o",
                    input_tokens=100,
                    output_tokens=50,
                ))

        threads = [threading.Thread(target=write_records, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        records = tracker.get_records()
        assert len(records) == 50

    # ===== JSONL format =====

    def test_json_roundtrip(self, tracker: UsageTracker) -> None:
        """Records survive JSON serialization/deserialization."""
        original = UsageRecord(
            timestamp="2025-01-15T10:30:00+00:00",
            model="gpt-4o",
            input_tokens=1234,
            output_tokens=567,
            cache_read_tokens=89,
            cache_write_tokens=12,
            cost=0.0055,
            agent="thesis_generator",
        )
        tracker.record(original)
        records = tracker.get_records()
        assert len(records) == 1
        loaded = records[0]
        assert loaded.model == original.model
        assert loaded.input_tokens == original.input_tokens
        assert loaded.output_tokens == original.output_tokens
        assert loaded.cache_read_tokens == original.cache_read_tokens
        assert loaded.cache_write_tokens == original.cache_write_tokens
        assert loaded.cost == original.cost
        assert loaded.agent == original.agent
