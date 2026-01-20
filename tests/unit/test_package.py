"""Test that the package is properly structured."""

from beavr import __version__


def test_version():
    """Test that version is defined."""
    assert __version__ == "0.1.0"


def test_package_import():
    """Test that all subpackages are importable."""
    import beavr.backtest
    import beavr.cli
    import beavr.core
    import beavr.data
    import beavr.db
    import beavr.models
    import beavr.strategies

    # All imports should succeed
    assert beavr.models is not None
    assert beavr.strategies is not None
    assert beavr.backtest is not None
    assert beavr.data is not None
    assert beavr.db is not None
    assert beavr.core is not None
    assert beavr.cli is not None
