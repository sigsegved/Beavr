"""LLM token usage tracking.

Records per-call token counts and costs to a local JSON-lines file.
Provides aggregation helpers for the ``bvr ai usage`` CLI command.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default usage log lives alongside other logs
_DEFAULT_USAGE_DIR = Path("logs/ai_investor")
_DEFAULT_USAGE_FILE = "llm_usage.jsonl"


@dataclass
class UsageRecord:
    """A single LLM call's token usage."""

    timestamp: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost: Optional[float] = None  # SDK-reported cost if available
    agent: str = ""  # Which agent made the call


@dataclass
class UsageSummary:
    """Aggregated usage statistics."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_calls: int = 0
    total_cost: Decimal = Decimal("0")
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    by_agent: dict[str, dict[str, int]] = field(default_factory=dict)
    first_call: Optional[str] = None
    last_call: Optional[str] = None


class UsageTracker:
    """Thread-safe LLM usage tracker that appends to a JSONL file.

    Designed to be shared by all LLMClient instances within a process.
    """

    _instance: Optional[UsageTracker] = None
    _lock = threading.Lock()

    def __init__(self, usage_dir: Optional[Path] = None) -> None:
        self._usage_file = (usage_dir or _DEFAULT_USAGE_DIR) / _DEFAULT_USAGE_FILE
        self._usage_file.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    @classmethod
    def get_instance(cls, usage_dir: Optional[Path] = None) -> UsageTracker:
        """Return the singleton tracker instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(usage_dir)
        return cls._instance

    def record(self, rec: UsageRecord) -> None:
        """Append a usage record to the JSONL file."""
        with self._write_lock:
            try:
                with open(self._usage_file, "a") as f:
                    f.write(json.dumps(asdict(rec)) + "\n")
            except Exception as e:
                logger.warning(f"Failed to write usage record: {e}")

    def get_records(
        self,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> list[UsageRecord]:
        """Read usage records, optionally filtered by date range."""
        if not self._usage_file.exists():
            return []

        records: list[UsageRecord] = []
        try:
            with open(self._usage_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rec_date = datetime.fromisoformat(data["timestamp"]).date()
                        if since and rec_date < since:
                            continue
                        if until and rec_date > until:
                            continue
                        records.append(UsageRecord(**data))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception as e:
            logger.warning(f"Failed to read usage file: {e}")

        return records

    def summarize(
        self,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> UsageSummary:
        """Build an aggregated usage summary."""
        records = self.get_records(since=since, until=until)
        summary = UsageSummary()

        for rec in records:
            summary.total_input_tokens += rec.input_tokens
            summary.total_output_tokens += rec.output_tokens
            summary.total_cache_read_tokens += rec.cache_read_tokens
            summary.total_cache_write_tokens += rec.cache_write_tokens
            summary.total_calls += 1
            if rec.cost is not None:
                summary.total_cost += Decimal(str(rec.cost))

            # By model
            model_stats = summary.by_model.setdefault(
                rec.model, {"input": 0, "output": 0, "calls": 0}
            )
            model_stats["input"] += rec.input_tokens
            model_stats["output"] += rec.output_tokens
            model_stats["calls"] += 1

            # By agent
            if rec.agent:
                agent_stats = summary.by_agent.setdefault(
                    rec.agent, {"input": 0, "output": 0, "calls": 0}
                )
                agent_stats["input"] += rec.input_tokens
                agent_stats["output"] += rec.output_tokens
                agent_stats["calls"] += 1

            if summary.first_call is None or rec.timestamp < summary.first_call:
                summary.first_call = rec.timestamp
            if summary.last_call is None or rec.timestamp > summary.last_call:
                summary.last_call = rec.timestamp

        return summary

    def summarize_daily(
        self,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> dict[str, UsageSummary]:
        """Build per-day usage summaries."""
        records = self.get_records(since=since, until=until)
        days: dict[str, list[UsageRecord]] = {}
        for rec in records:
            day_key = datetime.fromisoformat(rec.timestamp).strftime("%Y-%m-%d")
            days.setdefault(day_key, []).append(rec)

        result: dict[str, UsageSummary] = {}
        for day_key, day_records in sorted(days.items()):
            s = UsageSummary()
            for rec in day_records:
                s.total_input_tokens += rec.input_tokens
                s.total_output_tokens += rec.output_tokens
                s.total_cache_read_tokens += rec.cache_read_tokens
                s.total_cache_write_tokens += rec.cache_write_tokens
                s.total_calls += 1
                if rec.cost is not None:
                    s.total_cost += Decimal(str(rec.cost))

                model_stats = s.by_model.setdefault(
                    rec.model, {"input": 0, "output": 0, "calls": 0}
                )
                model_stats["input"] += rec.input_tokens
                model_stats["output"] += rec.output_tokens
                model_stats["calls"] += 1

            result[day_key] = s

        return result
