"""Test configuration and fixtures for pytest."""

import pytest


@pytest.fixture
def sample_data() -> dict:
    """Sample fixture for testing."""
    return {"test": "data"}
