"""Tests for messaging log repository."""

import pytest

from beavr.db.connection import Database
from beavr.messaging.log_repo import MessagingLogRepository


@pytest.fixture
def repo() -> MessagingLogRepository:
    """Create a MessagingLogRepository with an in-memory database."""
    db = Database(":memory:")
    return MessagingLogRepository(db)


class TestMessagingLogRepository:
    """Tests for MessagingLogRepository."""

    def test_log_outbound(self, repo: MessagingLogRepository) -> None:
        entry_id = repo.log_outbound(
            platform="telegram",
            notification_type="dd_report",
            priority="medium",
            message_text="DD Report: AAPL APPROVED",
            symbol="AAPL",
        )
        assert entry_id > 0

    def test_log_inbound(self, repo: MessagingLogRepository) -> None:
        entry_id = repo.log_inbound(
            platform="telegram",
            sender_id="12345",
            command="status",
            raw_text="/status",
            response_text="Portfolio: $10,000",
            is_verified=True,
        )
        assert entry_id > 0

    def test_get_recent(self, repo: MessagingLogRepository) -> None:
        repo.log_outbound(
            platform="telegram",
            notification_type="trade_executed",
            priority="high",
            message_text="BUY AAPL",
            symbol="AAPL",
        )
        repo.log_inbound(
            platform="telegram",
            sender_id="12345",
            command="status",
            raw_text="/status",
        )

        entries = repo.get_recent(limit=10)
        assert len(entries) == 2
        # Most recent first
        assert entries[0]["direction"] == "inbound"
        assert entries[1]["direction"] == "outbound"

    def test_get_recent_empty(self, repo: MessagingLogRepository) -> None:
        entries = repo.get_recent()
        assert entries == []

    def test_log_outbound_failure(self, repo: MessagingLogRepository) -> None:
        entry_id = repo.log_outbound(
            platform="telegram",
            notification_type="system_error",
            priority="critical",
            message_text="Error occurred",
            success=False,
            error_message="Connection refused",
        )
        assert entry_id > 0

        entries = repo.get_recent(limit=1)
        assert entries[0]["success"] == 0
        assert entries[0]["error_message"] == "Connection refused"

    def test_log_with_metadata(self, repo: MessagingLogRepository) -> None:
        repo.log_outbound(
            platform="telegram",
            notification_type="dd_report",
            priority="medium",
            message_text="test",
            metadata={"thesis_id": "abc123"},
        )
        entries = repo.get_recent(limit=1)
        assert entries[0]["metadata"] is not None
