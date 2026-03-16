"""Tests for messaging auth guard."""

import os

import pytest

from beavr.messaging.auth import (
    MAX_MESSAGE_LENGTH,
    AuthGuard,
    sanitize_input,
    validate_symbol,
)


class TestAuthGuard:
    """Tests for AuthGuard."""

    @pytest.fixture
    def guard(self) -> AuthGuard:
        """Create a guard with one pre-verified chat ID."""
        return AuthGuard(verified_chat_ids=["12345"])

    def test_is_verified_with_known_id(self, guard: AuthGuard) -> None:
        assert guard.is_verified("12345") is True

    def test_is_not_verified_with_unknown_id(self, guard: AuthGuard) -> None:
        assert guard.is_verified("99999") is False

    def test_add_verified(self, guard: AuthGuard) -> None:
        guard.add_verified("67890")
        assert guard.is_verified("67890") is True

    def test_remove_verified(self, guard: AuthGuard) -> None:
        guard.remove_verified("12345")
        assert guard.is_verified("12345") is False

    def test_remove_nonexistent_does_not_raise(self, guard: AuthGuard) -> None:
        guard.remove_verified("nonexistent")  # should not raise

    def test_empty_init(self) -> None:
        g = AuthGuard()
        assert len(g.verified_chat_ids) == 0

    def test_multiple_chat_ids(self) -> None:
        g = AuthGuard(verified_chat_ids=["111", "222", "333"])
        assert g.is_verified("111") is True
        assert g.is_verified("222") is True
        assert g.is_verified("333") is True
        assert g.is_verified("444") is False


class TestSanitizeInput:
    """Tests for sanitize_input."""

    def test_strips_whitespace(self) -> None:
        assert sanitize_input("  hello  ") == "hello"

    def test_truncates_long_input(self) -> None:
        long_text = "a" * 1000
        result = sanitize_input(long_text)
        assert len(result) == MAX_MESSAGE_LENGTH

    def test_normal_input_unchanged(self) -> None:
        assert sanitize_input("/buy AAPL $500") == "/buy AAPL $500"

    def test_empty_input(self) -> None:
        assert sanitize_input("") == ""


class TestValidateSymbol:
    """Tests for validate_symbol."""

    def test_valid_symbols(self) -> None:
        assert validate_symbol("AAPL") is True
        assert validate_symbol("SPY") is True
        assert validate_symbol("A") is True
        assert validate_symbol("GOOGL") is True

    def test_lowercase_accepted(self) -> None:
        assert validate_symbol("aapl") is True

    def test_invalid_symbols(self) -> None:
        assert validate_symbol("") is False
        assert validate_symbol("TOOLONG") is False
        assert validate_symbol("12345") is False
        assert validate_symbol("AA-BB") is False
        assert validate_symbol("A B") is False

    def test_numbers_rejected(self) -> None:
        assert validate_symbol("SPY1") is False
