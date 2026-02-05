---
applyTo: "src/beavr/models/**/*.py"
---

# Model Development Rules

Models in this directory are **data containers only** - no business logic.

## Required Patterns

### All models inherit from Pydantic BaseModel
```python
from pydantic import BaseModel, Field

class MyModel(BaseModel):
    field: Type = Field(description="...")
```

### Use Decimal for ALL monetary values
```python
price: Decimal = Field(description="Price in USD")
quantity: Decimal = Field(description="Number of shares")
value: Decimal = Field(description="Total value")
```

### Add Field() with descriptions
```python
symbol: str = Field(description="Stock ticker symbol")
action: str = Field(description="Trade action: buy, sell, hold")
```

### Use frozen=True for immutable models
```python
model_config = {"frozen": True}
```

## Import Order
```python
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field
```

## Test File
Every model needs tests in `tests/unit/test_models.py`
