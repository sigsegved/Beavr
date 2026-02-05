---
applyTo: "tests/**/*.py"
---

# Testing Rules

## File Naming
- Unit tests: `tests/unit/test_<module>.py`
- Integration tests: `tests/integration/test_<feature>.py`

## Test Structure

```python
"""Tests for module_name."""

import pytest
from decimal import Decimal

from beavr.module.file import ClassName


class TestClassName:
    """Tests for ClassName."""
    
    # ===== Fixtures =====
    
    @pytest.fixture
    def instance(self) -> ClassName:
        """Create default instance."""
        return ClassName()
    
    # ===== Happy Path =====
    
    def test_method_returns_expected(self, instance: ClassName):
        """Method should return expected result."""
        result = instance.method(valid_input)
        assert result == expected
    
    # ===== Edge Cases =====
    
    def test_method_handles_empty(self, instance: ClassName):
        """Method should handle empty input."""
        result = instance.method([])
        assert result == []
    
    def test_method_handles_zero(self, instance: ClassName):
        """Method should handle zero value."""
        result = instance.method(Decimal("0"))
        assert result == Decimal("0")
    
    # ===== Error Cases =====
    
    def test_method_raises_on_invalid(self, instance: ClassName):
        """Method should raise ValueError on invalid input."""
        with pytest.raises(ValueError, match="must be positive"):
            instance.method(Decimal("-1"))
```

## Naming Convention
`test_<what>_<when>_<expected>` or `test_<what>_<condition>`

Examples:
- `test_evaluate_returns_signal_when_oversold`
- `test_calculate_raises_on_negative_input`
- `test_process_handles_empty_list`

## Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    (Decimal("100"), Decimal("110")),
    (Decimal("0"), Decimal("0")),
])
def test_calculate_various_inputs(self, input, expected):
    result = calculate(input)
    assert result == expected
```

## Running Tests
```bash
pytest tests/unit/test_<module>.py -v  # Specific file
pytest -k "test_method"                 # Pattern match
pytest --cov=beavr                      # With coverage
```
