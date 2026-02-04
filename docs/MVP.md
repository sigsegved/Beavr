# Beavr MVP - Backtesting First

**Version:** 1.0  
**Date:** January 19, 2026  
**Goal:** Backtest DCA strategies before deploying to paper trading

---

## Overview

The MVP focuses on **backtesting only** - no live trading. We build the core architecture properly so it's extensible for paper trading later.

### MVP Scope

| In Scope | Out of Scope (Later) |
|----------|---------------------|
| ✅ Simple DCA strategy | ❌ Live/paper trading |
| ✅ Dip Buy DCA strategy | ❌ Swing trading strategy |
| ✅ Alpaca historical data | ❌ Real-time data streaming |
| ✅ Backtesting engine | ❌ Order execution |
| ✅ Performance metrics | ❌ Notifications |
| ✅ CLI for running backtests | ❌ Virtual sub-accounts |
| ✅ TOML configuration | ❌ Lot tracking |
| ✅ SQLite storage (data cache, results) | ❌ Trade reconciliation |
| ✅ Core models (Pydantic) | ❌ Broker adapters |

---

## Architecture (MVP Subset)

We implement a subset of the full architecture, but with the same structure so it's easy to extend.

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLI Layer (bvr)                          │
│  bvr backtest | bvr config                                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Core Engine                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Strategy   │  │  Backtest   │  │   Config    │                 │
│  │  Engine     │  │  Engine     │  │   Loader    │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Data Layer                                     │
│  ┌─────────────┐  ┌─────────────┐                                  │
│  │  Alpaca     │  │  Indicators │                                  │
│  │  Data       │  │  (pandas-ta)│                                  │
│  └─────────────┘  └─────────────┘                                  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                  │
│  ┌─────────────────────────────────────────────┐                   │
│  │  SQLite (Data Cache, Backtest Results)      │                   │
│  └─────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Project Structure (MVP)

```
beavr/
├── src/
│   └── beavr/
│       ├── __init__.py
│       │
│       ├── models/                  # Pydantic models
│       │   ├── __init__.py
│       │   ├── bar.py               # OHLCV bar data
│       │   ├── signal.py            # Strategy signals
│       │   ├── trade.py             # Simulated trades
│       │   ├── portfolio.py         # Portfolio state
│       │   └── config.py            # Config schemas
│       │
│       ├── strategies/              # Strategy implementations
│       │   ├── __init__.py
│       │   ├── base.py              # BaseStrategy ABC
│       │   ├── registry.py          # @register_strategy
│       │   ├── simple_dca.py        # Simple DCA
│       │   └── dip_buy_dca.py       # Dip Buy DCA
│       │
│       ├── backtest/                # Backtesting engine
│       │   ├── __init__.py
│       │   ├── engine.py            # Main backtest loop
│       │   ├── portfolio.py         # Simulated portfolio
│       │   └── metrics.py           # Performance calculations
│       │
│       ├── data/                    # Data fetching
│       │   ├── __init__.py
│       │   ├── alpaca.py            # Alpaca historical data
│       │   └── indicators.py        # Technical indicators
│       │
│       ├── db/                      # Storage layer
│       │   ├── __init__.py
│       │   ├── connection.py        # SQLite connection
│       │   ├── cache.py             # Data caching
│       │   └── results.py           # Backtest results storage
│       │
│       ├── core/                    # Core utilities
│       │   ├── __init__.py
│       │   └── config.py            # Config loading
│       │
│       └── cli/                     # CLI commands
│           ├── __init__.py
│           ├── main.py              # Entry point: bvr
│           └── backtest.py          # bvr backtest
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── examples/
│   └── strategies/
│       ├── simple_dca.toml
│       └── dip_buy_dca.toml
│
├── pyproject.toml
└── README.md
```

---

## Phase 1: Backtesting (MVP)

### 1.1 Strategies to Implement

#### Strategy 1: Simple DCA

Buy a fixed dollar amount at regular intervals, regardless of price.

```
Every month on the 1st:
  Buy $500 of SPY
```

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `symbols` | list[str] | `["SPY"]` | Symbols to buy |
| `amount` | Decimal | `500` | Dollar amount per buy |
| `frequency` | str | `"monthly"` | `"weekly"`, `"biweekly"`, `"monthly"` |
| `day_of_month` | int | `1` | Day to execute (for monthly) |
| `day_of_week` | int | `0` | Day to execute (for weekly, 0=Monday) |

#### Strategy 2: Dip Buy DCA

Buy on dips throughout the period, with fallback to deploy remaining budget at period end.

```
Each day, check:
  If price dropped ≥2% from recent high:
    Buy 50% of remaining monthly budget
    
On last 3 days of month:
  If budget remaining:
    Deploy remaining budget evenly
```

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `symbols` | list[str] | `["SPY"]` | Symbols to buy |
| `monthly_budget` | Decimal | `500` | Total budget per month |
| `dip_threshold` | float | `0.02` | Buy when price drops this % from recent high |
| `dip_buy_pct` | float | `0.50` | % of remaining budget to deploy on dip |
| `lookback_days` | int | `5` | Days to look back for recent high |
| `fallback_days` | int | `3` | Days before month-end to trigger fallback |

### 1.2 Storage Layer

SQLite for persistence. MVP needs two things:
1. **Data Cache** - Avoid re-fetching historical data from Alpaca
2. **Backtest Results** - Store results for comparison

#### Schema

```sql
-- Cache historical OHLCV data from Alpaca
CREATE TABLE bars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    timeframe TEXT NOT NULL,           -- "1Day", "1Hour", etc.
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp, timeframe)
);

CREATE INDEX idx_bars_symbol_time ON bars(symbol, timestamp);

-- Store backtest results for comparison
CREATE TABLE backtest_runs (
    id TEXT PRIMARY KEY,               -- UUID
    strategy_name TEXT NOT NULL,
    config_json TEXT NOT NULL,         -- Strategy params as JSON
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    
    -- Performance metrics
    initial_cash REAL NOT NULL,
    final_value REAL NOT NULL,
    total_return REAL NOT NULL,
    cagr REAL,
    max_drawdown REAL,
    sharpe_ratio REAL,
    
    -- Trade stats
    total_trades INTEGER NOT NULL,
    total_invested REAL NOT NULL,
    
    -- Holdings at end
    holdings_json TEXT,                -- {"SPY": 123.45}
    
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);

-- Individual trades in a backtest
CREATE TABLE backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,                -- "buy" or "sell"
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,              -- Dollar amount
    timestamp TEXT NOT NULL,
    reason TEXT,                       -- "dip_buy", "scheduled", "fallback"
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);

CREATE INDEX idx_backtest_trades_run ON backtest_trades(run_id);
```

#### Data Cache Usage

```python
# data/alpaca.py
class AlpacaDataFetcher:
    def __init__(self, db: Database):
        self.db = db
        self.client = StockHistoricalDataClient(...)
    
    def get_bars(
        self, 
        symbol: str, 
        start: date, 
        end: date,
        timeframe: str = "1Day"
    ) -> pd.DataFrame:
        """Fetch bars, using cache when available."""
        
        # Check cache first
        cached = self.db.get_cached_bars(symbol, start, end, timeframe)
        if cached is not None:
            return cached
        
        # Fetch from Alpaca
        bars = self._fetch_from_alpaca(symbol, start, end, timeframe)
        
        # Cache for next time
        self.db.cache_bars(symbol, bars, timeframe)
        
        return bars
```

### 1.3 Core Models

```python
# models/bar.py
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal

class Bar(BaseModel):
    """OHLCV bar data"""
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

# models/signal.py
from typing import Literal

class Signal(BaseModel):
    """Trading signal from strategy"""
    symbol: str
    action: Literal["buy", "sell", "hold"]
    amount: Decimal | None = None      # Dollar amount
    quantity: Decimal | None = None    # Shares
    reason: str

# models/trade.py
class Trade(BaseModel):
    """Executed (simulated) trade"""
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    price: Decimal
    amount: Decimal
    timestamp: datetime
    reason: str

# models/portfolio.py
class PortfolioState(BaseModel):
    """Snapshot of portfolio at a point in time"""
    timestamp: datetime
    cash: Decimal
    positions: dict[str, Decimal]      # symbol -> shares
    total_value: Decimal

# models/config.py
class StrategyConfig(BaseModel):
    """Strategy configuration from TOML"""
    template: str
    params: dict
    
class AppConfig(BaseModel):
    """Main app configuration"""
    alpaca_api_key: str
    alpaca_api_secret: str
    data_dir: Path = Path("~/.beavr").expanduser()
```

### 1.4 Backtesting Engine

#### What It Does

1. Load historical OHLCV data from Alpaca (with caching)
2. Simulate strategy execution day-by-day
3. Track simulated portfolio (cash, shares, value)
4. Calculate performance metrics
5. Store results in SQLite for comparison

#### Backtest Loop

```python
# backtest/engine.py
class BacktestEngine:
    def __init__(self, db: Database, data_fetcher: AlpacaDataFetcher):
        self.db = db
        self.data = data_fetcher
    
    def run(
        self,
        strategy: BaseStrategy,
        start: date,
        end: date,
        initial_cash: Decimal
    ) -> BacktestResult:
        """Run backtest simulation"""
        
        # Create run record
        run_id = str(uuid4())
        
        # Fetch historical data (cached)
        bars = self.data.get_bars(strategy.symbols, start, end)
        
        # Initialize portfolio
        portfolio = SimulatedPortfolio(cash=initial_cash)
        daily_values = []
        
        # Simulate day by day
        for day in trading_days(start, end):
            day_bars = bars[bars['date'] == day]
            
            # Build context for strategy
            ctx = StrategyContext(
                timestamp=day,
                prices=get_prices(day_bars),
                bars=get_historical_bars(bars, day),
                cash_available=portfolio.cash,
                positions=portfolio.positions,
                # ... calendar info
            )
            
            # Get signals from strategy
            signals = strategy.evaluate(ctx)
            
            # Execute signals
            for signal in signals:
                if signal.action == "buy":
                    trade = portfolio.buy(
                        symbol=signal.symbol,
                        amount=signal.amount,
                        price=ctx.prices[signal.symbol],
                        reason=signal.reason
                    )
                    self.db.save_trade(run_id, trade)
            
            # Track daily value
            daily_values.append(portfolio.value(ctx.prices))
        
        # Calculate metrics
        metrics = calculate_metrics(
            initial_cash=initial_cash,
            final_value=daily_values[-1],
            daily_values=daily_values,
            trades=portfolio.trades
        )
        
        # Store results
        self.db.save_backtest_result(run_id, strategy, metrics)
        
        return BacktestResult(run_id=run_id, metrics=metrics, trades=portfolio.trades)
```

#### Simulated Portfolio

```python
# backtest/portfolio.py
class SimulatedPortfolio:
    def __init__(self, cash: Decimal):
        self.cash = cash
        self.positions: dict[str, Decimal] = {}  # symbol -> shares
        self.trades: list[Trade] = []
    
    def buy(self, symbol: str, amount: Decimal, price: Decimal, reason: str) -> Trade:
        """Simulate a buy order at given price"""
        shares = amount / price
        self.cash -= amount
        self.positions[symbol] = self.positions.get(symbol, Decimal(0)) + shares
        
        trade = Trade(
            symbol=symbol,
            side="buy",
            quantity=shares,
            price=price,
            amount=amount,
            timestamp=datetime.now(),
            reason=reason
        )
        self.trades.append(trade)
        return trade
    
    def value(self, prices: dict[str, Decimal]) -> Decimal:
        """Calculate total portfolio value"""
        positions_value = sum(
            shares * prices[symbol] 
            for symbol, shares in self.positions.items()
        )
        return self.cash + positions_value
```

### 1.5 Performance Metrics

After backtest completes, calculate:

| Metric | Description |
|--------|-------------|
| **Total Return** | (Final Value - Initial Value) / Initial Value |
| **CAGR** | Compound Annual Growth Rate |
| **Max Drawdown** | Largest peak-to-trough decline |
| **Sharpe Ratio** | Risk-adjusted return (if we have daily returns) |
| **Total Invested** | Sum of all buy amounts |
| **Number of Trades** | How many buys executed |
| **Avg Cost Basis** | Total invested / Total shares |
| **Current Value** | Shares × Final Price |

### 1.6 CLI Commands

```bash
# Run backtest with default config
bvr backtest simple_dca --start 2020-01-01 --end 2025-01-01

# Run backtest with custom config
bvr backtest dip_buy_dca --config ~/.beavr/strategies/my_dip_dca.toml

# Compare strategies
bvr backtest compare simple_dca dip_buy_dca --start 2020-01-01 --end 2025-01-01

# Output formats
bvr backtest simple_dca --output table    # Default: rich table
bvr backtest simple_dca --output json     # JSON for further analysis
bvr backtest simple_dca --output csv      # CSV export
```

### 1.5 Configuration

#### Strategy Config (TOML)

```toml
# ~/.beavr/strategies/my_simple_dca.toml
template = "simple_dca"

[params]
symbols = ["VOO"]
amount = 500
frequency = "monthly"
day_of_month = 1
```

```toml
# ~/.beavr/strategies/my_dip_dca.toml
template = "dip_buy_dca"

[params]
symbols = ["VOO", "QQQ"]
weights = { VOO = 0.6, QQQ = 0.4 }
monthly_budget = 1000
dip_threshold = 0.02
dip_buy_pct = 0.50
lookback_days = 5
fallback_days = 3
```

#### Main Config (for Alpaca API keys)

```toml
# ~/.beavr/config.toml
[alpaca]
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"

# Use paper API for free historical data
# No trading in MVP - just data fetching
```

### 1.6 Example Output

```
$ bvr backtest dip_buy_dca --start 2020-01-01 --end 2025-01-01

📊 Backtest Results: Dip Buy DCA
════════════════════════════════════════════════════════════════

Strategy:     dip_buy_dca
Symbol:       VOO
Period:       2020-01-01 to 2025-01-01 (5 years)

💰 Performance
────────────────────────────────────────
Initial Cash:      $30,000.00
Total Invested:    $30,000.00
Final Value:       $52,847.32
Total Return:      +76.16%
CAGR:              +11.98%
Benchmark (B&H):   +72.34%  (Buy & Hold $30k on day 1)
vs Benchmark:      +3.82%

📉 Risk
────────────────────────────────────────
Max Drawdown:      -18.42%
Sharpe Ratio:      0.87

📈 Trades
────────────────────────────────────────
Total Trades:      127
Avg Trade Size:    $236.22
Dip Buys:          67 (52.8%)
Fallback Buys:     60 (47.2%)

💼 Holdings
────────────────────────────────────────
VOO:               112.45 shares
Avg Cost Basis:    $266.79
Current Price:     $470.02
Unrealized Gain:   +76.16%
```

---

## Phase 2: Paper Trading (Post-MVP)

Once backtesting validates the strategy, deploy to Alpaca paper trading.

### What Changes

| Component | Backtesting (Phase 1) | Paper Trading (Phase 2) |
|-----------|----------------------|------------------------|
| Data | Historical bars (cached) | Real-time quotes |
| Execution | Simulated | Alpaca paper orders |
| Portfolio | SimulatedPortfolio | Alpaca account state + local tracking |
| Scheduling | N/A (replay historical) | APScheduler (daily/weekly) |
| Storage | Data cache, backtest results | + Live trade log, lot tracking |

### New Components Needed

```
beavr/
├── brokers/
│   └── alpaca/
│       ├── adapter.py       # Submit orders to Alpaca
│       └── auth.py          # API authentication
│
├── core/
│   ├── executor.py          # Run strategy, submit orders
│   └── scheduler.py         # Schedule strategy runs
│
└── cli/
    └── run.py               # bvr run command
```

### Paper Trading Config

```toml
# ~/.beavr/config.toml
[broker]
name = "alpaca"
paper_trading = true          # Use paper API
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"

[strategies.my_dip_dca]
enabled = true
# No allocation needed for DCA - uses strategy's monthly_budget param
```

### Paper Trading Commands

```bash
# Start paper trading (runs as daemon)
bvr run --paper

# Check status
bvr status

# View trades
bvr trades

# Stop
bvr stop
```

---

## Implementation Plan

### Week 1-2: Foundation & Storage

- [ ] Project setup (Poetry, pytest, ruff, mypy)
- [ ] Pydantic models (`Bar`, `Signal`, `Trade`, `PortfolioState`, `Config`)
- [ ] SQLite database setup
  - [ ] Connection manager
  - [ ] Schema migrations
  - [ ] Data cache (bars table)
  - [ ] Results storage (backtest_runs, backtest_results, backtest_trades)
- [ ] Alpaca data fetcher with caching
- [ ] Basic TOML config loading

### Week 3-4: Strategies & Backtesting

- [ ] `BaseStrategy` interface
- [ ] `SimpleDCAStrategy` implementation
- [ ] `DipBuyDCAStrategy` implementation
- [ ] `SimulatedPortfolio` class
- [ ] Backtesting engine (day-by-day simulation)
- [ ] Performance metrics calculation
- [ ] Store backtest results in SQLite

### Week 5-6: CLI & Polish

- [ ] CLI: `bvr backtest` command
- [ ] Rich output formatting (tables, progress)
- [ ] Compare command (`bvr backtest compare`)
- [ ] List past results (`bvr backtest list`)
- [ ] JSON/CSV export
- [ ] Unit tests for strategies
- [ ] Integration tests with real Alpaca data
- [ ] Documentation

### Post-MVP: Paper Trading

- [ ] Alpaca broker adapter
- [ ] Order submission
- [ ] Scheduler (APScheduler)
- [ ] `bvr run` command
- [ ] Extend SQLite for live trade logging

---

## Technical Decisions

### Dependencies (MVP)

```toml
[tool.poetry.dependencies]
python = "^3.11"
alpaca-py = "^0.43"       # Historical data from Alpaca
pandas = "^2.0"           # Data manipulation
pydantic = "^2.0"         # Config & model validation
typer = "^0.12"           # CLI
rich = "^13.0"            # Beautiful terminal output
python-dotenv = "^1.0"    # Load API keys from .env

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
ruff = "^0.4"             # Linting & formatting
mypy = "^1.8"             # Type checking
```

### Data Source

Using Alpaca's free tier:
- IEX exchange data (good enough for daily DCA backtesting)
- 200 API calls/min (sufficient for historical data fetch)
- No cost for paper trading account

### Why Not VectorBT or backtesting.py?

For MVP, a simple custom backtester is sufficient:
- Our strategies are simple (buy on schedule/dip)
- We don't need complex position sizing or portfolio optimization
- Easier to understand and debug
- Can always integrate VectorBT later for advanced features

---

## Success Criteria

MVP is complete when:

1. ✅ Can run `bvr backtest simple_dca` and see performance metrics
2. ✅ Can run `bvr backtest dip_buy_dca` and see performance metrics  
3. ✅ Can compare both strategies against buy-and-hold benchmark
4. ✅ Can configure strategies via TOML
5. ✅ Results are reproducible with same parameters

Post-MVP success:

6. ⏳ Can deploy validated strategy to Alpaca paper trading
7. ⏳ Strategy runs automatically on schedule
8. ⏳ Can view paper trading results
