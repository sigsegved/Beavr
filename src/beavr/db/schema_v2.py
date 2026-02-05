"""V2 schema additions for AI Investor thesis-driven trading."""

# Additional tables for AI Investor v2
# These extend the existing schema with thesis management,
# due diligence tracking, and market events.

SCHEMA_V2_SQL = """
-- market_events: News and events from News Monitor
CREATE TABLE IF NOT EXISTS market_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    symbol TEXT,
    headline TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    url TEXT,
    timestamp TEXT NOT NULL,
    event_date TEXT,
    importance TEXT NOT NULL DEFAULT 'medium',
    -- Structured data (varies by event type)
    earnings_date TEXT,
    estimate_eps REAL,
    actual_eps REAL,
    estimate_revenue REAL,
    actual_revenue REAL,
    analyst_firm TEXT,
    old_rating TEXT,
    new_rating TEXT,
    old_price_target REAL,
    new_price_target REAL,
    insider_name TEXT,
    insider_title TEXT,
    transaction_value REAL,
    -- Processing status
    processed INTEGER DEFAULT 0,
    processed_at TEXT,
    thesis_generated INTEGER DEFAULT 0,
    thesis_id TEXT,
    -- Raw data
    raw_data TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_market_events_symbol ON market_events(symbol);
CREATE INDEX IF NOT EXISTS idx_market_events_type ON market_events(event_type);
CREATE INDEX IF NOT EXISTS idx_market_events_timestamp ON market_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_market_events_processed ON market_events(processed);

-- trade_theses: Investment hypotheses
CREATE TABLE IF NOT EXISTS trade_theses (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    created_at TEXT NOT NULL,
    trade_type TEXT NOT NULL,  -- day_trade, swing, position
    direction TEXT NOT NULL DEFAULT 'long',
    entry_rationale TEXT NOT NULL,
    catalyst TEXT NOT NULL,
    catalyst_date TEXT,
    entry_price_target REAL NOT NULL,
    profit_target REAL NOT NULL,
    stop_loss REAL NOT NULL,
    expected_exit_date TEXT NOT NULL,
    max_hold_date TEXT NOT NULL,
    invalidation_conditions TEXT,  -- JSON array
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, active, executed, closed, invalidated
    confidence REAL DEFAULT 0.5,
    dd_approved INTEGER DEFAULT 0,
    dd_report_id TEXT,
    source TEXT,
    notes TEXT,
    -- Position link (once executed)
    position_id INTEGER,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trade_theses_symbol ON trade_theses(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_theses_status ON trade_theses(status);
CREATE INDEX IF NOT EXISTS idx_trade_theses_catalyst_date ON trade_theses(catalyst_date);

-- dd_reports: Due diligence analysis reports
CREATE TABLE IF NOT EXISTS dd_reports (
    id TEXT PRIMARY KEY,
    thesis_id TEXT,
    symbol TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    recommendation TEXT NOT NULL,  -- approve, reject, conditional
    confidence REAL NOT NULL,
    -- Analysis sections
    fundamental_summary TEXT NOT NULL,
    technical_summary TEXT NOT NULL,
    catalyst_assessment TEXT NOT NULL,
    risk_factors TEXT,  -- JSON array
    -- Company data at DD time
    market_cap REAL,
    pe_ratio REAL,
    revenue_growth REAL,
    institutional_ownership REAL,
    -- Recommendations
    recommended_entry REAL NOT NULL,
    recommended_target REAL NOT NULL,
    recommended_stop REAL NOT NULL,
    recommended_position_size_pct REAL NOT NULL,
    -- Rationale
    approval_rationale TEXT,
    rejection_rationale TEXT,
    conditions TEXT,  -- JSON array
    -- Metadata
    data_sources_used TEXT,  -- JSON array
    processing_time_ms REAL DEFAULT 0,
    llm_model TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (thesis_id) REFERENCES trade_theses(id)
);

CREATE INDEX IF NOT EXISTS idx_dd_reports_symbol ON dd_reports(symbol);
CREATE INDEX IF NOT EXISTS idx_dd_reports_thesis ON dd_reports(thesis_id);
CREATE INDEX IF NOT EXISTS idx_dd_reports_recommendation ON dd_reports(recommendation);

-- ai_positions_v2: Enhanced positions with thesis links
-- This extends the original ai_positions with thesis integration
CREATE TABLE IF NOT EXISTS ai_positions_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id TEXT NOT NULL,
    dd_report_id TEXT,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_timestamp TEXT NOT NULL,
    -- Price targets (from thesis, may be adjusted)
    stop_loss_price REAL NOT NULL,
    target_price REAL NOT NULL,
    -- Time management
    trade_type TEXT NOT NULL,
    expected_exit_date TEXT NOT NULL,
    max_hold_date TEXT NOT NULL,
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'open',  -- open, closed_target, closed_stop, closed_time, closed_invalidated, closed_manual
    exit_price REAL,
    exit_timestamp TEXT,
    exit_type TEXT,  -- target_hit, stop_hit, time_exit, thesis_invalidated, manual
    -- Performance
    realized_pnl REAL,
    realized_pnl_pct REAL,
    -- Metadata
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (thesis_id) REFERENCES trade_theses(id),
    FOREIGN KEY (dd_report_id) REFERENCES dd_reports(id)
);

CREATE INDEX IF NOT EXISTS idx_ai_positions_v2_thesis ON ai_positions_v2(thesis_id);
CREATE INDEX IF NOT EXISTS idx_ai_positions_v2_symbol ON ai_positions_v2(symbol);
CREATE INDEX IF NOT EXISTS idx_ai_positions_v2_status ON ai_positions_v2(status);

-- position_reviews: Audit trail for position management decisions
CREATE TABLE IF NOT EXISTS position_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    review_date TEXT NOT NULL,
    current_price REAL,
    unrealized_pnl REAL,
    unrealized_pnl_pct REAL,
    days_held INTEGER,
    thesis_status TEXT,  -- intact, weakening, invalidated
    catalyst_status TEXT,  -- pending, occurred, missed
    action TEXT NOT NULL,  -- hold, exit_full, exit_partial, adjust_stop
    action_rationale TEXT,
    exit_type TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (position_id) REFERENCES ai_positions_v2(id)
);

CREATE INDEX IF NOT EXISTS idx_position_reviews_position ON position_reviews(position_id);
CREATE INDEX IF NOT EXISTS idx_position_reviews_date ON position_reviews(review_date);

-- watchlist: Active symbols being monitored
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL,
    reason TEXT,
    priority INTEGER DEFAULT 0,
    thesis_id TEXT,
    active INTEGER DEFAULT 1,
    
    FOREIGN KEY (thesis_id) REFERENCES trade_theses(id)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_active ON watchlist(active);
CREATE INDEX IF NOT EXISTS idx_watchlist_priority ON watchlist(priority);
"""

# Schema version for v2 additions
SCHEMA_V2_VERSION = 3
