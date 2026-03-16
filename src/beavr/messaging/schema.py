"""Database schema for the messaging audit log."""

SCHEMA_MESSAGING_SQL = """
-- messaging_log: Audit trail for all inbound and outbound messages
CREATE TABLE IF NOT EXISTS messaging_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,
    platform TEXT NOT NULL,
    sender_id TEXT,
    notification_type TEXT,
    priority TEXT,
    command TEXT,
    raw_text TEXT,
    response_text TEXT,
    symbol TEXT,
    is_verified INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_messaging_log_direction
    ON messaging_log(direction);
CREATE INDEX IF NOT EXISTS idx_messaging_log_platform
    ON messaging_log(platform);
CREATE INDEX IF NOT EXISTS idx_messaging_log_timestamp
    ON messaging_log(timestamp);

-- verified_users: Registered messaging users
CREATE TABLE IF NOT EXISTS verified_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    UNIQUE(platform, platform_user_id)
);

-- pending_confirmations: Trading commands awaiting /confirm
CREATE TABLE IF NOT EXISTS pending_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    command TEXT NOT NULL,
    symbol TEXT NOT NULL,
    amount TEXT,
    quantity TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_pending_confirmations_chat
    ON pending_confirmations(chat_id);
CREATE INDEX IF NOT EXISTS idx_pending_confirmations_status
    ON pending_confirmations(status);
"""
