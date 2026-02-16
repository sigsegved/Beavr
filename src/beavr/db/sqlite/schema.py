"""SQLite database schema definitions."""

# Schema SQL for creating all tables
# This schema is idempotent - can be run multiple times safely
SCHEMA_SQL = """
-- bars: Cache historical OHLCV data from Alpaca
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
CREATE INDEX IF NOT EXISTS idx_bars_symbol_timeframe ON bars(symbol, timeframe);

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

-- backtest_results: Performance metrics for a run
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

-- ai_positions: Track AI investor positions with stop/target levels
-- This integrates AI trading with the main portfolio tracking system
CREATE TABLE IF NOT EXISTS ai_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_amount REAL NOT NULL,
    stop_loss_pct REAL NOT NULL,
    target_pct REAL NOT NULL,
    strategy TEXT,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'open',  -- open, closed_target, closed_stop, closed_manual
    entry_timestamp TEXT NOT NULL,
    exit_timestamp TEXT,
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL,
    pnl_pct REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_positions_symbol ON ai_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_ai_positions_status ON ai_positions(status);

-- ai_trades: All AI investor trade executions (both entry and exit)
CREATE TABLE IF NOT EXISTS ai_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,  -- BUY or SELL
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,
    timestamp TEXT NOT NULL,
    reason TEXT,
    FOREIGN KEY (position_id) REFERENCES ai_positions(id)
);

CREATE INDEX IF NOT EXISTS idx_ai_trades_position ON ai_trades(position_id);
CREATE INDEX IF NOT EXISTS idx_ai_trades_symbol ON ai_trades(symbol);
"""

# Version for future migrations
SCHEMA_VERSION = 2
