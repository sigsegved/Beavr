# Beavr MVP - Detailed Task Breakdown

**Purpose:** Task breakdown for parallel agent development  
**Date:** January 19, 2026

---

## Task Organization

Each task is designed to be **independently assignable** to an agent. Tasks include:
- Clear scope and deliverables
- Input dependencies (what must exist first)
- Output artifacts (what it produces)
- Acceptance criteria

### Task ID Format
- `P1-xx` = Phase 1 (Foundation & Storage)
- `P2-xx` = Phase 2 (Strategies & Backtesting)
- `P3-xx` = Phase 3 (CLI & Polish)

### Dependency Notation
- `requires: [P1-01, P1-02]` = Must complete these tasks first
- `parallel: true` = Can run in parallel with other tasks in same phase

---

## Phase 1: Foundation & Storage (Week 1-2)

### P1-01: Project Setup

**Scope:** Initialize Python project with Poetry, configure tooling, use ruff as linter, setup copilot-instructions.md, etc

**Deliverables:**
- `pyproject.toml` with dependencies
- `src/beavr/__init__.py` package structure
- `.gitignore`
- `ruff.toml` (linting config)
- `mypy.ini` or pyproject.toml mypy section
- `pytest.ini` or pyproject.toml pytest section
- `.env.example` (template for API keys)

**Dependencies:**
```toml
[tool.poetry.dependencies]
python = "^3.11"
alpaca-py = "^0.43"
pandas = "^2.0"
pydantic = "^2.0"
pydantic-settings = "^2.0"
typer = "^0.12"
rich = "^13.0"
python-dotenv = "^1.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
ruff = "^0.4"
mypy = "^1.8"
pandas-stubs = "^2.0"
```

**Acceptance Criteria:**
- [ ] `poetry install` succeeds
- [ ] `poetry run pytest` runs (even with no tests)
- [ ] `poetry run ruff check .` runs
- [ ] `poetry run mypy src/` runs
- [ ] Package is importable: `from beavr import __version__`

**Requires:** None  
**Parallel:** Yes (can start immediately)

---

### P1-02: Pydantic Models - Core

**Scope:** Create core Pydantic models for data representation

**Files to create:**
```
src/beavr/models/
├── __init__.py          # Re-export all models
├── bar.py               # OHLCV bar data
├── signal.py            # Strategy signals
├── trade.py             # Trade records
└── portfolio.py         # Portfolio state
```

**Model Specifications:**

```python
# bar.py
class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    
    model_config = ConfigDict(frozen=True)

# signal.py
class Signal(BaseModel):
    symbol: str
    action: Literal["buy", "sell", "hold"]
    amount: Decimal | None = None      # Dollar amount (for buys)
    quantity: Decimal | None = None    # Share quantity (for sells)
    reason: str
    timestamp: datetime

# trade.py
class Trade(BaseModel):
    id: str                            # UUID
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    price: Decimal
    amount: Decimal                    # Total dollar amount
    timestamp: datetime
    reason: str                        # "scheduled", "dip_buy", "fallback"

# portfolio.py
class Position(BaseModel):
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    
class PortfolioState(BaseModel):
    timestamp: datetime
    cash: Decimal
    positions: dict[str, Position]
    
    @property
    def total_value(self) -> Decimal:
        """Calculate with current prices - requires prices arg"""
        ...
    
    def value_at(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate total value given current prices"""
        position_value = sum(
            pos.quantity * prices.get(symbol, Decimal(0))
            for symbol, pos in self.positions.items()
        )
        return self.cash + position_value
```

**Acceptance Criteria:**
- [ ] All models are importable from `beavr.models`
- [ ] Models have proper type hints
- [ ] Models are immutable where appropriate (frozen=True)
- [ ] Unit tests for model validation
- [ ] `Decimal` used for all money/price/quantity fields (not float)

**Requires:** P1-01  
**Parallel:** Yes (after P1-01)

---

### P1-03: Pydantic Models - Config

**Scope:** Create configuration models for TOML parsing

**Files to create:**
```
src/beavr/models/
└── config.py            # Config schemas
```

**Model Specifications:**

```python
# config.py
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from pathlib import Path
from decimal import Decimal

class AlpacaConfig(BaseModel):
    api_key_env: str = "ALPACA_API_KEY"
    api_secret_env: str = "ALPACA_API_SECRET"
    paper: bool = True

class StrategyParams(BaseModel):
    """Base class for strategy parameters - extended by each strategy"""
    pass

class StrategyConfig(BaseModel):
    template: str                      # Strategy class name
    params: dict                       # Strategy-specific params

class AppConfig(BaseSettings):
    """Main application configuration"""
    alpaca: AlpacaConfig = AlpacaConfig()
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".beavr")
    db_path: Path | None = None        # Defaults to data_dir/beavr.db
    
    model_config = ConfigDict(
        env_prefix="BEAVR_",
        env_nested_delimiter="__"
    )
    
    @property
    def database_path(self) -> Path:
        return self.db_path or (self.data_dir / "beavr.db")

# Strategy-specific param models
class SimpleDCAParams(BaseModel):
    symbols: list[str] = ["SPY"]
    amount: Decimal = Decimal("500")
    frequency: Literal["weekly", "biweekly", "monthly"] = "monthly"
    day_of_month: int = Field(default=1, ge=1, le=28)
    day_of_week: int = Field(default=0, ge=0, le=6)  # 0=Monday

class DipBuyDCAParams(BaseModel):
    symbols: list[str] = ["SPY"]
    monthly_budget: Decimal = Decimal("500")
    dip_threshold: float = Field(default=0.02, ge=0.01, le=0.10)
    dip_buy_pct: float = Field(default=0.50, ge=0.1, le=1.0)
    lookback_days: int = Field(default=5, ge=2, le=20)
    fallback_days: int = Field(default=3, ge=1, le=5)
```

**Acceptance Criteria:**
- [ ] Can load config from TOML file
- [ ] Environment variable overrides work
- [ ] Validation errors are clear and helpful
- [ ] Default values are sensible
- [ ] Unit tests for config loading

**Requires:** P1-01  
**Parallel:** Yes (after P1-01)

---

### P1-04: SQLite Database - Connection & Schema

**Scope:** Set up SQLite database connection and schema management

**Files to create:**
```
src/beavr/db/
├── __init__.py
├── connection.py        # Database connection manager
└── schema.py            # Schema definitions and migrations
```

**Schema (from MVP.md):**

```sql
-- bars: Cache historical OHLCV data
CREATE TABLE IF NOT EXISTS bars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    timeframe TEXT NOT NULL,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp, timeframe)
);
CREATE INDEX IF NOT EXISTS idx_bars_symbol_time ON bars(symbol, timestamp);

-- backtest_runs: Metadata for each backtest
CREATE TABLE IF NOT EXISTS backtest_runs (
    id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- backtest_results: Performance metrics
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    final_value REAL NOT NULL,
    total_return REAL NOT NULL,
    cagr REAL,
    max_drawdown REAL,
    sharpe_ratio REAL,
    total_trades INTEGER NOT NULL,
    total_invested REAL NOT NULL,
    holdings_json TEXT,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);

-- backtest_trades: Individual trades in a backtest
CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,
    timestamp TEXT NOT NULL,
    reason TEXT,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_run ON backtest_trades(run_id);
```

**Connection Manager:**

```python
# connection.py
import sqlite3
from pathlib import Path
from contextlib import contextmanager

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_dir()
        self._init_schema()
    
    def _ensure_dir(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _init_schema(self):
        """Create tables if they don't exist"""
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
    
    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
```

**Acceptance Criteria:**
- [ ] Database file created in `~/.beavr/beavr.db`
- [ ] Schema is idempotent (can run multiple times)
- [ ] Connection context manager handles transactions
- [ ] Row factory returns dict-like objects
- [ ] Unit tests with in-memory database

**Requires:** P1-01  
**Parallel:** Yes (after P1-01)

---

### P1-05: SQLite Database - Data Cache Repository

**Scope:** Repository for caching Alpaca historical data

**Files to create:**
```
src/beavr/db/
└── cache.py             # Bar data caching
```

**Interface:**

```python
# cache.py
class BarCache:
    def __init__(self, db: Database):
        self.db = db
    
    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day"
    ) -> pd.DataFrame | None:
        """
        Retrieve cached bars for symbol/date range.
        Returns None if data not fully cached.
        Returns DataFrame with columns: timestamp, open, high, low, close, volume
        """
        ...
    
    def save_bars(
        self,
        symbol: str,
        bars: pd.DataFrame,
        timeframe: str = "1Day"
    ) -> None:
        """
        Save bars to cache. DataFrame must have columns:
        timestamp, open, high, low, close, volume
        """
        ...
    
    def has_data(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day"
    ) -> bool:
        """Check if we have complete data for date range"""
        ...
    
    def get_date_range(
        self,
        symbol: str,
        timeframe: str = "1Day"
    ) -> tuple[date, date] | None:
        """Get the date range we have cached for a symbol"""
        ...
```

**Acceptance Criteria:**
- [ ] Can save DataFrame of bars to cache
- [ ] Can retrieve cached bars as DataFrame
- [ ] Handles partial cache misses correctly
- [ ] Duplicate inserts are handled (UPSERT)
- [ ] Unit tests with in-memory database

**Requires:** P1-04  
**Parallel:** No (needs P1-04)

---

### P1-06: SQLite Database - Backtest Results Repository

**Scope:** Repository for storing and retrieving backtest results

**Files to create:**
```
src/beavr/db/
└── results.py           # Backtest results storage
```

**Interface:**

```python
# results.py
from dataclasses import dataclass

@dataclass
class BacktestMetrics:
    final_value: Decimal
    total_return: float        # As percentage (0.15 = 15%)
    cagr: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    total_trades: int
    total_invested: Decimal
    holdings: dict[str, Decimal]  # symbol -> shares

class BacktestResultsRepository:
    def __init__(self, db: Database):
        self.db = db
    
    def create_run(
        self,
        strategy_name: str,
        config: dict,
        start_date: date,
        end_date: date,
        initial_cash: Decimal
    ) -> str:
        """Create a new backtest run, returns run_id (UUID)"""
        ...
    
    def save_results(
        self,
        run_id: str,
        metrics: BacktestMetrics
    ) -> None:
        """Save metrics for a backtest run"""
        ...
    
    def save_trade(
        self,
        run_id: str,
        trade: Trade
    ) -> None:
        """Save a single trade to backtest history"""
        ...
    
    def save_trades(
        self,
        run_id: str,
        trades: list[Trade]
    ) -> None:
        """Batch save trades"""
        ...
    
    def get_run(self, run_id: str) -> dict | None:
        """Get run metadata"""
        ...
    
    def get_results(self, run_id: str) -> BacktestMetrics | None:
        """Get results for a run"""
        ...
    
    def get_trades(self, run_id: str) -> list[Trade]:
        """Get all trades for a run"""
        ...
    
    def list_runs(
        self,
        strategy_name: str | None = None,
        limit: int = 20
    ) -> list[dict]:
        """List recent backtest runs"""
        ...
```

**Acceptance Criteria:**
- [ ] Can create run and get back UUID
- [ ] Can save and retrieve metrics
- [ ] Can save and retrieve trades
- [ ] Can list runs with optional filtering
- [ ] Unit tests with in-memory database

**Requires:** P1-04, P1-02 (for Trade model)  
**Parallel:** No (needs P1-04)

---

### P1-07: Alpaca Data Fetcher

**Scope:** Fetch historical bar data from Alpaca API

**Files to create:**
```
src/beavr/data/
├── __init__.py
└── alpaca.py            # Alpaca data fetching
```

**Interface:**

```python
# alpaca.py
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

class AlpacaDataFetcher:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        cache: BarCache | None = None
    ):
        self.client = StockHistoricalDataClient(api_key, api_secret)
        self.cache = cache
    
    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day"
    ) -> pd.DataFrame:
        """
        Fetch bars, using cache if available.
        
        Returns DataFrame with columns:
        - timestamp (datetime)
        - open, high, low, close (Decimal)
        - volume (int)
        """
        # Check cache first
        if self.cache:
            cached = self.cache.get_bars(symbol, start, end, timeframe)
            if cached is not None:
                return cached
        
        # Fetch from Alpaca
        bars_df = self._fetch_from_alpaca(symbol, start, end, timeframe)
        
        # Cache for next time
        if self.cache:
            self.cache.save_bars(symbol, bars_df, timeframe)
        
        return bars_df
    
    def get_multi_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
        timeframe: str = "1Day"
    ) -> dict[str, pd.DataFrame]:
        """Fetch bars for multiple symbols"""
        return {
            symbol: self.get_bars(symbol, start, end, timeframe)
            for symbol in symbols
        }
    
    def _fetch_from_alpaca(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str
    ) -> pd.DataFrame:
        """Direct Alpaca API call"""
        tf = TimeFrame.Day if timeframe == "1Day" else TimeFrame.Hour
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            start=datetime.combine(start, datetime.min.time()),
            end=datetime.combine(end, datetime.max.time()),
            timeframe=tf
        )
        bars = self.client.get_stock_bars(request)
        # Convert to DataFrame...
        ...
```

**Acceptance Criteria:**
- [ ] Can fetch daily bars from Alpaca
- [ ] Uses cache when available
- [ ] Handles Alpaca API errors gracefully
- [ ] Returns properly typed DataFrame
- [ ] Integration test with real Alpaca API (mark as slow)

**Requires:** P1-01, P1-05 (cache)  
**Parallel:** No (needs P1-05 for cache)

---

### P1-08: Config Loader

**Scope:** Load and validate configuration from TOML files

**Files to create:**
```
src/beavr/core/
├── __init__.py
└── config.py            # Config loading utilities
```

**Interface:**

```python
# config.py
import tomllib
from pathlib import Path

def load_app_config(config_path: Path | None = None) -> AppConfig:
    """
    Load application config from TOML file.
    
    Search order:
    1. Explicit path if provided
    2. ./beavr.toml (current directory)
    3. ~/.beavr/config.toml
    
    Environment variables override file values.
    """
    ...

def load_strategy_config(strategy_path: Path) -> StrategyConfig:
    """
    Load strategy config from TOML file.
    
    Example file:
    ```toml
    template = "simple_dca"
    
    [params]
    symbols = ["VOO"]
    amount = 500
    frequency = "monthly"
    ```
    """
    ...

def get_strategy_params(
    config: StrategyConfig,
    strategy_name: str
) -> BaseModel:
    """
    Parse and validate strategy params based on template.
    
    Returns appropriate params model (SimpleDCAParams, DipBuyDCAParams, etc.)
    """
    ...

def ensure_data_dir(config: AppConfig) -> None:
    """Create data directory if it doesn't exist"""
    config.data_dir.mkdir(parents=True, exist_ok=True)
```

**Acceptance Criteria:**
- [ ] Loads TOML config correctly
- [ ] Environment variables override file values
- [ ] Clear error messages for invalid config
- [ ] Strategy params are validated against schema
- [ ] Unit tests for various config scenarios

**Requires:** P1-03 (config models)  
**Parallel:** No (needs P1-03)

---

## Phase 2: Strategies & Backtesting (Week 3-4)

### P2-01: BaseStrategy Interface

**Scope:** Define the abstract base class for all strategies

**Files to create:**
```
src/beavr/strategies/
├── __init__.py
├── base.py              # BaseStrategy ABC
└── context.py           # StrategyContext
```

**Interface:**

```python
# context.py
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import pandas as pd

@dataclass
class StrategyContext:
    """Context provided to strategy during evaluation"""
    # Current evaluation point
    current_date: date
    
    # Market data
    prices: dict[str, Decimal]              # symbol -> current close price
    bars: dict[str, pd.DataFrame]           # symbol -> historical bars up to current_date
    
    # Portfolio state
    cash: Decimal
    positions: dict[str, Decimal]           # symbol -> shares held
    
    # Budget tracking (for DCA strategies)
    period_budget: Decimal                  # Budget for current period
    period_spent: Decimal                   # Amount spent so far this period
    
    # Calendar helpers
    day_of_month: int
    day_of_week: int                        # 0=Monday
    days_to_month_end: int
    is_first_trading_day_of_month: bool
    is_last_trading_day_of_month: bool

# base.py
from abc import ABC, abstractmethod
from typing import ClassVar

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies"""
    
    # Metadata - override in subclass
    name: ClassVar[str] = "Base Strategy"
    description: ClassVar[str] = ""
    version: ClassVar[str] = "1.0.0"
    
    def __init__(self, params: BaseModel):
        """Initialize with validated params"""
        self.params = params
    
    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """
        Evaluate strategy and return signals.
        
        Called once per trading day during backtest.
        Return empty list for no action.
        """
        pass
    
    @property
    @abstractmethod
    def symbols(self) -> list[str]:
        """Symbols this strategy trades"""
        pass
    
    def on_period_start(self, ctx: StrategyContext) -> None:
        """Called at start of each budget period (month/week)"""
        pass
    
    def on_period_end(self, ctx: StrategyContext) -> None:
        """Called at end of each budget period"""
        pass
```

**Acceptance Criteria:**
- [ ] BaseStrategy is properly abstract
- [ ] StrategyContext has all needed fields
- [ ] Type hints are complete
- [ ] Can subclass and implement evaluate()
- [ ] Unit tests for context creation

**Requires:** P1-02 (models)  
**Parallel:** Yes (after P1-02)

---

### P2-02: Strategy Registry

**Scope:** Registry for discovering and loading strategies

**Files to create:**
```
src/beavr/strategies/
└── registry.py          # @register_strategy decorator
```

**Interface:**

```python
# registry.py
from typing import Type

_REGISTRY: dict[str, Type[BaseStrategy]] = {}

def register_strategy(name: str):
    """
    Decorator to register a strategy class.
    
    Usage:
        @register_strategy("simple_dca")
        class SimpleDCAStrategy(BaseStrategy):
            ...
    """
    def decorator(cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
        if name in _REGISTRY:
            raise ValueError(f"Strategy '{name}' already registered")
        _REGISTRY[name] = cls
        return cls
    return decorator

def get_strategy(name: str) -> Type[BaseStrategy]:
    """Get strategy class by name"""
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(f"Unknown strategy: '{name}'. Available: {available}")
    return _REGISTRY[name]

def list_strategies() -> list[str]:
    """List all registered strategy names"""
    return list(_REGISTRY.keys())

def create_strategy(name: str, params: dict) -> BaseStrategy:
    """
    Create strategy instance with params.
    
    Validates params against strategy's param model.
    """
    strategy_cls = get_strategy(name)
    # Get param model from strategy class...
    validated_params = ...
    return strategy_cls(validated_params)
```

**Acceptance Criteria:**
- [ ] Decorator registers strategies correctly
- [ ] Can retrieve by name
- [ ] Clear error for unknown strategy
- [ ] Can list all registered strategies
- [ ] create_strategy validates params

**Requires:** P2-01  
**Parallel:** No (needs P2-01)

---

### P2-03: Simple DCA Strategy

**Scope:** Implement simple dollar-cost averaging strategy

**Files to create:**
```
src/beavr/strategies/
└── simple_dca.py        # Simple DCA implementation
```

**Logic:**
```
Every [frequency] on [day]:
  For each symbol:
    Buy [amount * weight] dollars worth
```

**Implementation:**

```python
# simple_dca.py
@register_strategy("simple_dca")
class SimpleDCAStrategy(BaseStrategy):
    name = "Simple DCA"
    description = "Buy fixed amount at regular intervals"
    version = "1.0.0"
    
    params: SimpleDCAParams
    
    def __init__(self, params: SimpleDCAParams):
        self.params = params
    
    @property
    def symbols(self) -> list[str]:
        return self.params.symbols
    
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        signals = []
        
        if not self._is_buy_day(ctx):
            return signals
        
        # Calculate per-symbol amount
        amount_per_symbol = self.params.amount / len(self.params.symbols)
        
        for symbol in self.params.symbols:
            if ctx.cash >= amount_per_symbol:
                signals.append(Signal(
                    symbol=symbol,
                    action="buy",
                    amount=amount_per_symbol,
                    reason="scheduled",
                    timestamp=datetime.combine(ctx.current_date, datetime.min.time())
                ))
        
        return signals
    
    def _is_buy_day(self, ctx: StrategyContext) -> bool:
        if self.params.frequency == "monthly":
            return ctx.day_of_month == self.params.day_of_month
        elif self.params.frequency == "weekly":
            return ctx.day_of_week == self.params.day_of_week
        elif self.params.frequency == "biweekly":
            # Every other week on specified day
            ...
        return False
```

**Acceptance Criteria:**
- [ ] Buys on correct schedule (monthly/weekly/biweekly)
- [ ] Handles multiple symbols
- [ ] Respects available cash
- [ ] Signals have correct amounts
- [ ] Unit tests for each frequency

**Requires:** P2-01, P2-02, P1-03 (SimpleDCAParams)  
**Parallel:** Yes (after P2-02)

---

### P2-04: Dip Buy DCA Strategy

**Scope:** Implement dip-buying DCA strategy

**Files to create:**
```
src/beavr/strategies/
└── dip_buy_dca.py       # Dip Buy DCA implementation
```

**Logic:**
```
Each day:
  Calculate recent high (lookback_days)
  If current price <= recent_high * (1 - dip_threshold):
    Buy dip_buy_pct of remaining monthly budget
    
On last fallback_days of month:
  Deploy remaining budget evenly
```

**Implementation:**

```python
# dip_buy_dca.py
@register_strategy("dip_buy_dca")
class DipBuyDCAStrategy(BaseStrategy):
    name = "Dip Buy DCA"
    description = "Buy on dips with month-end fallback"
    version = "1.0.0"
    
    params: DipBuyDCAParams
    
    @property
    def symbols(self) -> list[str]:
        return self.params.symbols
    
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        signals = []
        remaining_budget = ctx.period_budget - ctx.period_spent
        
        if remaining_budget <= 0:
            return signals
        
        for symbol in self.params.symbols:
            price = ctx.prices[symbol]
            recent_high = self._get_recent_high(ctx.bars[symbol])
            drop_pct = (recent_high - price) / recent_high
            
            # Check for dip
            if drop_pct >= self.params.dip_threshold:
                amount = remaining_budget * Decimal(str(self.params.dip_buy_pct))
                if amount >= Decimal("10"):  # Minimum order
                    signals.append(Signal(
                        symbol=symbol,
                        action="buy",
                        amount=amount,
                        reason="dip_buy",
                        timestamp=...
                    ))
                    remaining_budget -= amount
            
            # Check for month-end fallback
            elif ctx.days_to_month_end <= self.params.fallback_days:
                amount = remaining_budget / len(self.params.symbols)
                if amount >= Decimal("10"):
                    signals.append(Signal(
                        symbol=symbol,
                        action="buy",
                        amount=amount,
                        reason="fallback",
                        timestamp=...
                    ))
        
        return signals
    
    def _get_recent_high(self, bars: pd.DataFrame) -> Decimal:
        """Get highest close in lookback period"""
        recent = bars.tail(self.params.lookback_days)
        return Decimal(str(recent['close'].max()))
```

**Acceptance Criteria:**
- [ ] Detects dips correctly
- [ ] Buys correct percentage on dip
- [ ] Fallback triggers on last N days of month
- [ ] Tracks budget spent per period
- [ ] Unit tests for dip detection and fallback

**Requires:** P2-01, P2-02, P1-03 (DipBuyDCAParams)  
**Parallel:** Yes (after P2-02)

---

### P2-05: Simulated Portfolio

**Scope:** Track portfolio state during backtest simulation

**Files to create:**
```
src/beavr/backtest/
├── __init__.py
└── portfolio.py         # Simulated portfolio
```

**Interface:**

```python
# portfolio.py
class SimulatedPortfolio:
    def __init__(self, initial_cash: Decimal):
        self.cash = initial_cash
        self.positions: dict[str, Decimal] = {}  # symbol -> shares
        self.trades: list[Trade] = []
        self.initial_cash = initial_cash
    
    def buy(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        timestamp: datetime,
        reason: str
    ) -> Trade | None:
        """
        Execute a buy order.
        
        Returns Trade if executed, None if insufficient cash.
        """
        if amount > self.cash:
            return None
        
        shares = amount / price
        self.cash -= amount
        self.positions[symbol] = self.positions.get(symbol, Decimal(0)) + shares
        
        trade = Trade(
            id=str(uuid4()),
            symbol=symbol,
            side="buy",
            quantity=shares,
            price=price,
            amount=amount,
            timestamp=timestamp,
            reason=reason
        )
        self.trades.append(trade)
        return trade
    
    def sell(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        timestamp: datetime,
        reason: str
    ) -> Trade | None:
        """
        Execute a sell order.
        
        Returns Trade if executed, None if insufficient shares.
        """
        ...
    
    def get_position(self, symbol: str) -> Decimal:
        """Get shares held for symbol"""
        return self.positions.get(symbol, Decimal(0))
    
    def get_value(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate total portfolio value"""
        position_value = sum(
            shares * prices[symbol]
            for symbol, shares in self.positions.items()
        )
        return self.cash + position_value
    
    def get_state(self, timestamp: datetime, prices: dict[str, Decimal]) -> PortfolioState:
        """Get current state as PortfolioState model"""
        ...
```

**Acceptance Criteria:**
- [ ] Tracks cash correctly after trades
- [ ] Tracks positions correctly
- [ ] Calculates value correctly
- [ ] Handles insufficient cash/shares
- [ ] All trades are recorded
- [ ] Unit tests for buy/sell/value

**Requires:** P1-02 (Trade, PortfolioState models)  
**Parallel:** Yes (after P1-02)

---

### P2-06: Performance Metrics Calculator

**Scope:** Calculate performance metrics from backtest results

**Files to create:**
```
src/beavr/backtest/
└── metrics.py           # Performance calculations
```

**Metrics to calculate:**

| Metric | Formula |
|--------|---------|
| Total Return | (final - initial) / initial |
| CAGR | (final / initial)^(1/years) - 1 |
| Max Drawdown | max((peak - trough) / peak) |
| Sharpe Ratio | mean(daily_returns) / std(daily_returns) * sqrt(252) |
| Total Invested | sum(buy amounts) |
| Avg Cost Basis | total_invested / total_shares |

**Interface:**

```python
# metrics.py
@dataclass
class BacktestMetrics:
    initial_cash: Decimal
    final_value: Decimal
    total_return: float
    cagr: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    total_trades: int
    total_invested: Decimal
    holdings: dict[str, Decimal]

def calculate_metrics(
    initial_cash: Decimal,
    final_value: Decimal,
    daily_values: list[Decimal],
    trades: list[Trade],
    start_date: date,
    end_date: date
) -> BacktestMetrics:
    """Calculate all performance metrics"""
    ...

def calculate_total_return(initial: Decimal, final: Decimal) -> float:
    """Calculate simple total return as percentage"""
    return float((final - initial) / initial)

def calculate_cagr(
    initial: Decimal,
    final: Decimal,
    years: float
) -> float | None:
    """Calculate compound annual growth rate"""
    if years <= 0:
        return None
    return (float(final / initial) ** (1 / years)) - 1

def calculate_max_drawdown(daily_values: list[Decimal]) -> float | None:
    """Calculate maximum drawdown from peak"""
    if not daily_values:
        return None
    ...

def calculate_sharpe_ratio(
    daily_values: list[Decimal],
    risk_free_rate: float = 0.0
) -> float | None:
    """Calculate annualized Sharpe ratio"""
    if len(daily_values) < 2:
        return None
    ...
```

**Acceptance Criteria:**
- [ ] All metrics calculated correctly
- [ ] Handles edge cases (no trades, short periods)
- [ ] Returns None for incalculable metrics
- [ ] Unit tests with known values

**Requires:** P1-02 (Trade model)  
**Parallel:** Yes (after P1-02)

---

### P2-07: Backtest Engine

**Scope:** Main backtesting loop that ties everything together

**Files to create:**
```
src/beavr/backtest/
└── engine.py            # Main backtest loop
```

**Interface:**

```python
# engine.py
@dataclass
class BacktestResult:
    run_id: str
    strategy_name: str
    start_date: date
    end_date: date
    metrics: BacktestMetrics
    trades: list[Trade]
    daily_values: list[tuple[date, Decimal]]  # For charting

class BacktestEngine:
    def __init__(
        self,
        data_fetcher: AlpacaDataFetcher,
        results_repo: BacktestResultsRepository | None = None
    ):
        self.data = data_fetcher
        self.results_repo = results_repo
    
    def run(
        self,
        strategy: BaseStrategy,
        start_date: date,
        end_date: date,
        initial_cash: Decimal
    ) -> BacktestResult:
        """
        Run backtest simulation.
        
        1. Fetch historical data
        2. Initialize portfolio
        3. Loop through each trading day
        4. Evaluate strategy and execute signals
        5. Calculate metrics
        6. Store results (if repo provided)
        """
        # Create run record
        run_id = str(uuid4())
        
        # Fetch data
        bars = self.data.get_multi_bars(
            strategy.symbols,
            start_date,
            end_date
        )
        
        # Get trading days
        trading_days = self._get_trading_days(bars, start_date, end_date)
        
        # Initialize
        portfolio = SimulatedPortfolio(initial_cash)
        daily_values = []
        
        # Budget tracking (for DCA strategies)
        current_month = None
        period_spent = Decimal(0)
        
        # Main loop
        for day in trading_days:
            # Reset period tracking on new month
            if day.month != current_month:
                current_month = day.month
                period_spent = Decimal(0)
            
            # Build context
            ctx = self._build_context(
                day, bars, portfolio, period_spent, ...
            )
            
            # Get signals
            signals = strategy.evaluate(ctx)
            
            # Execute signals
            for signal in signals:
                if signal.action == "buy":
                    trade = portfolio.buy(
                        symbol=signal.symbol,
                        amount=signal.amount,
                        price=ctx.prices[signal.symbol],
                        timestamp=datetime.combine(day, datetime.min.time()),
                        reason=signal.reason
                    )
                    if trade:
                        period_spent += trade.amount
            
            # Track daily value
            daily_values.append((day, portfolio.get_value(ctx.prices)))
        
        # Calculate metrics
        metrics = calculate_metrics(
            initial_cash=initial_cash,
            final_value=daily_values[-1][1],
            daily_values=[v for _, v in daily_values],
            trades=portfolio.trades,
            start_date=start_date,
            end_date=end_date
        )
        
        # Store results
        if self.results_repo:
            self.results_repo.create_run(...)
            self.results_repo.save_results(run_id, metrics)
            self.results_repo.save_trades(run_id, portfolio.trades)
        
        return BacktestResult(
            run_id=run_id,
            strategy_name=strategy.name,
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            trades=portfolio.trades,
            daily_values=daily_values
        )
    
    def _build_context(self, day, bars, portfolio, period_spent, ...) -> StrategyContext:
        """Build strategy context for a given day"""
        ...
    
    def _get_trading_days(self, bars, start, end) -> list[date]:
        """Extract trading days from bar data"""
        ...
```

**Acceptance Criteria:**
- [ ] Runs complete backtest simulation
- [ ] Handles period (month) transitions
- [ ] Builds context correctly for each day
- [ ] Executes signals and updates portfolio
- [ ] Calculates and stores results
- [ ] Integration test with simple strategy

**Requires:** P2-01, P2-05, P2-06, P1-07, P1-06  
**Parallel:** No (needs most of Phase 2)

---

## Phase 3: CLI & Polish (Week 5-6)

### P3-01: CLI Main Entry Point

**Scope:** Set up main CLI application with Typer

**Files to create:**
```
src/beavr/cli/
├── __init__.py
└── main.py              # Entry point
```

**Interface:**

```python
# main.py
import typer
from rich.console import Console

app = typer.Typer(
    name="bvr",
    help="Beavr - Automated trading backtesting and execution"
)
console = Console()

@app.callback()
def main():
    """Beavr CLI"""
    pass

@app.command()
def version():
    """Show version"""
    from beavr import __version__
    console.print(f"Beavr v{__version__}")

# Subcommand groups will be added by other tasks
# app.add_typer(backtest_app, name="backtest")
```

**pyproject.toml entry:**
```toml
[tool.poetry.scripts]
bvr = "beavr.cli.main:app"
```

**Acceptance Criteria:**
- [ ] `bvr --help` works
- [ ] `bvr version` shows version
- [ ] Rich console is configured
- [ ] Entry point is registered in pyproject.toml

**Requires:** P1-01  
**Parallel:** Yes (after P1-01)

---

### P3-02: CLI Backtest Command

**Scope:** Implement `bvr backtest` command

**Files to create:**
```
src/beavr/cli/
└── backtest.py          # bvr backtest commands
```

**Commands:**

```bash
# Run a backtest
bvr backtest run simple_dca --start 2020-01-01 --end 2025-01-01 --cash 10000

# Run with config file
bvr backtest run simple_dca --config ~/.beavr/strategies/my_dca.toml

# Compare strategies
bvr backtest compare simple_dca dip_buy_dca --start 2020-01-01 --end 2025-01-01

# List past runs
bvr backtest list

# Show details of a run
bvr backtest show <run_id>

# Export results
bvr backtest export <run_id> --format csv --output results.csv
```

**Interface:**

```python
# backtest.py
import typer
from datetime import date
from decimal import Decimal
from pathlib import Path

backtest_app = typer.Typer(help="Backtesting commands")

@backtest_app.command("run")
def run_backtest(
    strategy: str = typer.Argument(..., help="Strategy name (simple_dca, dip_buy_dca)"),
    start: str = typer.Option(..., "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="End date (YYYY-MM-DD)"),
    cash: float = typer.Option(10000, "--cash", "-c", help="Initial cash"),
    config: Path | None = typer.Option(None, "--config", help="Strategy config file"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json, csv")
):
    """Run a backtest for a strategy"""
    ...

@backtest_app.command("compare")
def compare_strategies(
    strategies: list[str] = typer.Argument(..., help="Strategies to compare"),
    start: str = typer.Option(..., "--start", "-s"),
    end: str = typer.Option(..., "--end", "-e"),
    cash: float = typer.Option(10000, "--cash", "-c")
):
    """Compare multiple strategies"""
    ...

@backtest_app.command("list")
def list_runs(
    strategy: str | None = typer.Option(None, "--strategy", help="Filter by strategy"),
    limit: int = typer.Option(20, "--limit", "-n")
):
    """List past backtest runs"""
    ...

@backtest_app.command("show")
def show_run(
    run_id: str = typer.Argument(..., help="Run ID to show")
):
    """Show details of a backtest run"""
    ...
```

**Acceptance Criteria:**
- [ ] `bvr backtest run` executes backtest
- [ ] Supports config file override
- [ ] Output formats work (table, json, csv)
- [ ] `bvr backtest list` shows past runs
- [ ] `bvr backtest compare` works
- [ ] Clear error messages for invalid inputs

**Requires:** P2-07, P3-01  
**Parallel:** No (needs P2-07)

---

### P3-03: Rich Output Formatting

**Scope:** Beautiful terminal output for backtest results

**Files to create:**
```
src/beavr/cli/
└── output.py            # Output formatting
```

**Output Example:**
```
📊 Backtest Results: Dip Buy DCA
════════════════════════════════════════════════════════════════

Strategy:     dip_buy_dca
Symbol:       VOO
Period:       2020-01-01 to 2025-01-01 (5 years)

💰 Performance
────────────────────────────────────────
Initial Cash:      $10,000.00
Total Invested:    $10,000.00
Final Value:       $17,616.00
Total Return:      +76.16%
CAGR:              +11.98%
Benchmark (B&H):   +72.34%
vs Benchmark:      +3.82%

📉 Risk
────────────────────────────────────────
Max Drawdown:      -18.42%
Sharpe Ratio:      0.87

📈 Trades
────────────────────────────────────────
Total Trades:      127
Dip Buys:          67 (52.8%)
Fallback Buys:     60 (47.2%)

💼 Holdings
────────────────────────────────────────
VOO:               37.48 shares @ $266.79 avg
Current Price:     $470.02
```

**Interface:**

```python
# output.py
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def print_backtest_result(result: BacktestResult, console: Console):
    """Print formatted backtest results"""
    ...

def print_comparison_table(results: list[BacktestResult], console: Console):
    """Print side-by-side comparison"""
    ...

def print_run_list(runs: list[dict], console: Console):
    """Print list of past runs"""
    ...

def export_to_json(result: BacktestResult) -> str:
    """Export result as JSON"""
    ...

def export_to_csv(result: BacktestResult) -> str:
    """Export trades as CSV"""
    ...
```

**Acceptance Criteria:**
- [ ] Results are beautifully formatted
- [ ] Comparison table is clear
- [ ] Colors and emojis enhance readability
- [ ] JSON export is valid JSON
- [ ] CSV export is valid CSV

**Requires:** P2-07 (BacktestResult)  
**Parallel:** Yes (after P2-07)

---

### P3-04: Unit Tests - Models

**Scope:** Unit tests for all Pydantic models

**Files to create:**
```
tests/unit/
├── __init__.py
├── test_models_bar.py
├── test_models_signal.py
├── test_models_trade.py
├── test_models_portfolio.py
└── test_models_config.py
```

**Coverage:**
- Model instantiation
- Validation (valid and invalid inputs)
- Computed properties
- Serialization/deserialization

**Requires:** P1-02, P1-03  
**Parallel:** Yes (after models complete)

---

### P3-05: Unit Tests - Strategies

**Scope:** Unit tests for strategy implementations

**Files to create:**
```
tests/unit/
├── test_strategy_simple_dca.py
└── test_strategy_dip_buy_dca.py
```

**Test Cases:**
- Simple DCA: monthly/weekly/biweekly schedules
- Dip Buy: dip detection, fallback trigger
- Budget tracking
- Signal generation

**Requires:** P2-03, P2-04  
**Parallel:** Yes (after strategies complete)

---

### P3-06: Unit Tests - Backtest Engine

**Scope:** Unit tests for backtest engine and metrics

**Files to create:**
```
tests/unit/
├── test_backtest_portfolio.py
├── test_backtest_metrics.py
└── test_backtest_engine.py
```

**Test Cases:**
- Portfolio: buy/sell/value calculations
- Metrics: all calculations with known values
- Engine: full simulation with mock data

**Requires:** P2-05, P2-06, P2-07  
**Parallel:** Yes (after backtest complete)

---

### P3-07: Integration Tests

**Scope:** Integration tests with real Alpaca API

**Files to create:**
```
tests/integration/
├── __init__.py
├── conftest.py          # Fixtures (API keys, etc.)
├── test_alpaca_data.py
└── test_full_backtest.py
```

**Test Cases:**
- Fetch real data from Alpaca
- Run full backtest with real data
- Verify results are reasonable

**Note:** Mark as `@pytest.mark.slow` for CI

**Requires:** P2-07  
**Parallel:** Yes (after backtest complete)

---

### P3-08: Documentation

**Scope:** User documentation and examples

**Files to create:**
```
README.md                # Project overview
docs/
├── QUICKSTART.md        # Getting started guide
├── CONFIGURATION.md     # Config reference
└── STRATEGIES.md        # Strategy reference
examples/
└── strategies/
    ├── simple_dca.toml
    └── dip_buy_dca.toml
```

**Acceptance Criteria:**
- [ ] README has clear overview and quickstart
- [ ] All config options documented
- [ ] Example configs work out of the box
- [ ] CLI commands documented

**Requires:** All Phase 2 tasks  
**Parallel:** Yes (after Phase 2)

---

## Task Dependency Graph

```
Phase 1 (Foundation):
P1-01 ─────┬─────┬─────┬─────┐
           │     │     │     │
           ▼     ▼     ▼     │
        P1-02  P1-03  P1-04  │
           │     │     │     │
           │     │     ├─────┼───► P1-05 ───► P1-07
           │     │     │     │
           │     │     └─────┼───► P1-06
           │     │           │
           │     └───────────┼───► P1-08
           │                 │
           └─────────────────┘

Phase 2 (Strategies & Backtesting):
P1-02 ───► P2-01 ───► P2-02 ───┬───► P2-03
                               │
                               └───► P2-04

P1-02 ───► P2-05
P1-02 ───► P2-06

P2-01 + P2-05 + P2-06 + P1-07 + P1-06 ───► P2-07

Phase 3 (CLI & Polish):
P1-01 ───► P3-01
P2-07 + P3-01 ───► P3-02
P2-07 ───► P3-03

Tests can run in parallel once dependencies are met.
```

---

## Agent Assignment Recommendations

### Agent 1: Data & Storage
- P1-01 (Project Setup)
- P1-04 (Database Connection)
- P1-05 (Bar Cache)
- P1-06 (Results Repository)
- P1-07 (Alpaca Data Fetcher)

### Agent 2: Models & Config
- P1-02 (Core Models)
- P1-03 (Config Models)
- P1-08 (Config Loader)

### Agent 3: Strategies
- P2-01 (BaseStrategy)
- P2-02 (Registry)
- P2-03 (Simple DCA)
- P2-04 (Dip Buy DCA)

### Agent 4: Backtest Engine
- P2-05 (Simulated Portfolio)
- P2-06 (Metrics Calculator)
- P2-07 (Backtest Engine)

### Agent 5: CLI & Output
- P3-01 (CLI Main)
- P3-02 (Backtest Command)
- P3-03 (Rich Output)

### Agent 6: Testing & Docs
- P3-04 through P3-08
