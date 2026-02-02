"""Fixtures for integration tests."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


@pytest.fixture
def alpaca_credentials() -> tuple[str, str]:
    """Get Alpaca API credentials from environment.

    Skips test if credentials are not available.
    """
    api_key = os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_API_SECRET")

    if not api_key or not api_secret:
        pytest.skip("ALPACA_API_KEY and ALPACA_API_SECRET required for integration tests")

    return api_key, api_secret
