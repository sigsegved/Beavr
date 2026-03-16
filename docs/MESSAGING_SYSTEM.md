# Beavr Messaging & Notification System — Design Document

## 1. Overview

Add a messaging layer to Beavr that:

1. **Sends notifications** when the system generates DD reports, takes market actions (buy/sell), or detects important events.
2. **Accepts commands** from a verified user to trigger actions (run analysis, buy/sell stocks).
3. **Provides an audit trail** — all messages (sent and received) are visible in the IM channel.

### Why Telegram?

Starting with **Telegram Bot API** because it:
- Doesn't require a phone number for the *bot* (only the user needs one)
- Has a simple, well-documented HTTP API
- Supports message formatting (Markdown), inline keyboards, and file attachments
- Allows restricting the bot to a single verified chat ID (strong access control)
- Is free with no rate-limiting concerns at our scale
- Has Python libraries (`python-telegram-bot`) with async support

The system is designed with an **abstraction layer** so Discord, Slack, or other providers can be added later.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────┐
│                  Beavr Core                      │
│                                                  │
│  Orchestrator ──► NotificationService            │
│  DD Agent     ──►   │                            │
│  Trade Exec   ──►   │                            │
│  Position Mgr ──►   │                            │
│                     ▼                            │
│              MessagingProvider (Protocol)         │
│                     │                            │
│         ┌───────────┼───────────┐                │
│         ▼           ▼           ▼                │
│    Telegram      Discord     Slack               │
│    Provider     (future)    (future)              │
│                                                  │
│  CommandRouter  ◄── MessagingProvider (inbound)  │
│      │                                           │
│      ├──► AnalyzeCommand                         │
│      ├──► BuyCommand                             │
│      ├──► SellCommand                            │
│      ├──► StatusCommand                          │
│      └──► HelpCommand                            │
└─────────────────────────────────────────────────┘
```

### Key Components

| Component | Responsibility |
|-----------|----------------|
| `MessagingProvider` | Protocol defining send/receive interface (like `BrokerProvider`) |
| `TelegramProvider` | Telegram Bot API implementation |
| `NotificationService` | Dispatches system events to all configured providers |
| `CommandRouter` | Routes inbound messages to command handlers |
| `CommandHandler` | Base class for individual commands (analyze, buy, sell, status) |
| `AuthGuard` | Validates that inbound messages come from verified user(s) |

---

## 3. Data Models

```python
# src/beavr/models/messaging.py

class MessagePriority(str, Enum):
    LOW = "low"           # Informational (daily summaries)
    MEDIUM = "medium"     # DD reports, position updates
    HIGH = "high"         # Trade executed, stop loss hit
    CRITICAL = "critical" # System errors, large losses

class NotificationType(str, Enum):
    DD_REPORT = "dd_report"
    TRADE_EXECUTED = "trade_executed"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_HIT = "stop_loss_hit"
    TARGET_HIT = "target_hit"
    MARKET_EVENT = "market_event"
    SYSTEM_ERROR = "system_error"
    COMMAND_RESPONSE = "command_response"

class OutboundMessage(BaseModel):
    notification_type: NotificationType
    priority: MessagePriority
    title: str
    body: str
    symbol: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class InboundCommand(BaseModel):
    raw_text: str
    command: str          # e.g. "analyze", "buy", "sell", "status"
    args: list[str]       # parsed arguments
    sender_id: str        # platform-specific user ID
    platform: str         # "telegram", "discord", etc.
    timestamp: datetime
    is_verified: bool     # set by AuthGuard

class CommandResult(BaseModel):
    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
```

---

## 4. Provider Protocol

Following the same PEP 544 pattern as `BrokerProvider`:

```python
# src/beavr/messaging/protocols.py

@runtime_checkable
class MessagingProvider(Protocol):
    """Protocol for messaging integrations (Telegram, Discord, Slack)."""

    @property
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'telegram')."""
        ...

    async def send_message(self, message: OutboundMessage) -> bool:
        """Send a notification message. Returns True on success."""
        ...

    async def start_listening(self) -> None:
        """Start listening for inbound commands (long-polling or webhook)."""
        ...

    async def stop_listening(self) -> None:
        """Stop the listener gracefully."""
        ...

    def set_command_callback(
        self, callback: Callable[[InboundCommand], Awaitable[CommandResult]]
    ) -> None:
        """Register the callback invoked when a command is received."""
        ...
```

---

## 5. Security Design

### 5.1 Authentication — Chat ID Allowlist

```
User registers once:
1. User starts chat with bot → bot receives chat_id.
2. User sends /verify <one-time-token>.
3. Bot matches token to pre-generated token in config/env.
4. Bot stores chat_id as verified.
5. All future messages from unverified chat_ids are rejected + logged.
```

**Implementation:**

- **Verified chat IDs** stored in environment variable `BEAVR_TELEGRAM__VERIFIED_CHAT_IDS` (comma-separated).
- **One-time verification token** stored in `BEAVR_TELEGRAM__VERIFY_TOKEN` (random UUID, set by admin).
- Once verified, the chat ID is appended to the allowlist and persisted to the database.
- Every inbound message is checked against the allowlist **before** any command processing.

### 5.2 Command Authorization — Tiered Permissions

| Tier | Commands | Risk Level |
|------|----------|------------|
| **Read-only** | `/status`, `/help`, `/history` | None — info only |
| **Analysis** | `/analyze <symbol>`, `/dd <symbol>` | Low — triggers LLM analysis, no trades |
| **Trading** | `/buy <symbol> <amount>`, `/sell <symbol>` | High — executes real trades |

**Trading commands require confirmation:**

```
User: /buy AAPL $500
Bot:  ⚠️ CONFIRM TRADE
      Action: BUY AAPL
      Amount: $500.00
      Current Price: $185.42
      Est. Shares: 2.696
      
      Reply /confirm within 60s to execute, /cancel to abort.
      
User: /confirm
Bot:  ✅ Order submitted: BUY 2.696 AAPL @ market
      Order ID: abc123
```

### 5.3 Rate Limiting

- Max **10 trading commands per hour** per user.
- Max **30 total commands per hour** per user.
- Prevents accidental rapid-fire or compromised account abuse.

### 5.4 Input Sanitization

- All inbound text is stripped, length-limited (max 500 chars), and validated against command patterns.
- Symbol inputs are validated against known ticker format (1-5 uppercase alphanumeric).
- Amount inputs are validated as positive `Decimal` values.
- No shell execution, no eval, no dynamic code — commands map to predefined handler functions only.

### 5.5 Audit Logging

- Every inbound command and outbound notification is logged to the database (`messaging_log` table).
- All messages are also visible in the Telegram chat history (natural audit trail).
- Rejected/unauthorized attempts are logged with sender details for security review.

---

## 6. Configuration

Extends `AppConfig` with a new `MessagingConfig`:

```python
# Added to src/beavr/models/config.py

class TelegramConfig(BaseModel):
    bot_token_env: str = Field(
        default="BEAVR_TELEGRAM_BOT_TOKEN",
        description="Env var name for Telegram bot token"
    )
    verified_chat_ids: list[str] = Field(
        default_factory=list,
        description="Pre-verified Telegram chat IDs"
    )
    verify_token_env: str = Field(
        default="BEAVR_TELEGRAM_VERIFY_TOKEN",
        description="Env var name for one-time verification token"
    )

class MessagingConfig(BaseModel):
    enabled: bool = Field(default=False, description="Enable messaging system")
    provider: Literal["telegram"] = Field(
        default="telegram", description="Messaging provider"
    )
    telegram: Optional[TelegramConfig] = Field(default=None)
    notify_on_dd: bool = Field(default=True, description="Notify on DD reports")
    notify_on_trade: bool = Field(default=True, description="Notify on trades")
    notify_on_stop_loss: bool = Field(default=True, description="Notify on stop hits")
    notify_on_target: bool = Field(default=True, description="Notify on target hits")
    accept_commands: bool = Field(default=True, description="Accept inbound commands")
```

**Environment variables:**

```bash
# Telegram bot token (from @BotFather)
export BEAVR_TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."

# One-time verification token (generate with `python -c "import uuid; print(uuid.uuid4())"`)
export BEAVR_TELEGRAM_VERIFY_TOKEN="a1b2c3d4-..."

# Pre-verified chat IDs (optional, can verify at runtime)
export BEAVR_MESSAGING__TELEGRAM__VERIFIED_CHAT_IDS="12345678,87654321"
```

---

## 7. Notification Integration Points

Where the system hooks into existing Beavr code:

| Location | Event | Message |
|----------|-------|---------|
| `dd_agent.py` — after report generation | DD report approved/rejected | Full DD summary with recommendation, entry/target/stop |
| `trade_executor.py` — after order placed | Trade executed | Symbol, side, quantity, price, order ID |
| `position_manager.py` — on exit trigger | Stop/target/time exit | Symbol, exit reason, P/L |
| `v2_engine.py` — on high-importance event | Market event detected | Event headline, symbol, importance |
| `v2_engine.py` — on system error | System error | Error message, component that failed |

### Example DD Notification

```
📊 DD REPORT: AAPL — APPROVED (87% confidence)

Trade Type: Swing Short (1-2 weeks)
Entry: $185.00 | Target: $195.00 | Stop: $180.00
Position Size: 5% of portfolio

Executive Summary:
Strong Q1 earnings catalyst with institutional accumulation.
Technical breakout above $184 resistance with volume confirmation.

Bull Case: iPhone 17 cycle drives 15% upside
Bear Case: China tariff escalation caps gains
Base Case: Gradual grind to $195 on earnings momentum

Risk Factors:
• Trade war escalation
• AI spending slowdown
• Broader market correction
```

### Example Trade Notification

```
🔔 TRADE EXECUTED

Action: BUY AAPL
Shares: 27
Entry Price: $185.23
Total Cost: $5,001.21
Stop Loss: $180.00 (-2.8%)
Target: $195.00 (+5.3%)

Thesis: Q1 earnings momentum + iPhone 17 cycle
DD Report: #dd-2026-0312-aapl
```

---

## 8. Command Reference

| Command | Description | Tier | Example |
|---------|-------------|------|---------|
| `/help` | List available commands | Read | `/help` |
| `/status` | Portfolio summary (cash, positions, P/L) | Read | `/status` |
| `/positions` | List open positions with current P/L | Read | `/positions` |
| `/history [n]` | Last N trades (default 10) | Read | `/history 5` |
| `/analyze <symbol>` | Run AI analysis on a symbol | Analysis | `/analyze AAPL` |
| `/dd <symbol>` | Trigger full DD report | Analysis | `/dd TSLA` |
| `/buy <symbol> <amount>` | Buy stock (requires /confirm) | Trading | `/buy AAPL $500` |
| `/sell <symbol> [qty]` | Sell position (requires /confirm) | Trading | `/sell AAPL` |
| `/cancel` | Cancel pending confirmation | Trading | `/cancel` |
| `/confirm` | Confirm pending trade | Trading | `/confirm` |

---

## 9. File Structure

```
src/beavr/
├── messaging/                    # NEW — Messaging system
│   ├── __init__.py
│   ├── protocols.py              # MessagingProvider protocol
│   ├── service.py                # NotificationService (dispatch)
│   ├── auth.py                   # AuthGuard + verification
│   ├── commands/                 # Command handlers
│   │   ├── __init__.py
│   │   ├── router.py            # CommandRouter
│   │   ├── base.py              # BaseCommandHandler
│   │   ├── status.py            # /status, /positions, /history
│   │   ├── analyze.py           # /analyze, /dd
│   │   └── trading.py           # /buy, /sell, /confirm, /cancel
│   ├── formatters.py            # Message formatting (DD, trades, etc.)
│   └── providers/               # Provider implementations
│       ├── __init__.py
│       ├── telegram.py          # TelegramProvider
│       └── factory.py           # Provider factory
├── models/
│   └── messaging.py             # NEW — Message models
├── db/
│   └── messaging_log.py         # NEW — Audit log repository
```

---

## 10. Database Schema

```sql
-- Messaging audit log
CREATE TABLE IF NOT EXISTS messaging_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,           -- 'inbound' or 'outbound'
    platform TEXT NOT NULL,            -- 'telegram', 'discord', etc.
    sender_id TEXT,                    -- platform user ID (inbound)
    notification_type TEXT,            -- NotificationType value
    priority TEXT,                     -- MessagePriority value
    command TEXT,                      -- parsed command (inbound)
    raw_text TEXT,                     -- original message text
    response_text TEXT,                -- bot response (for commands)
    symbol TEXT,                       -- related symbol if any
    is_verified BOOLEAN DEFAULT FALSE, -- was sender verified?
    success BOOLEAN DEFAULT TRUE,      -- delivery/execution success
    error_message TEXT,                -- error details if failed
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSON                      -- extra context
);

-- Verified users
CREATE TABLE IF NOT EXISTS verified_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    verified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(platform, platform_user_id)
);

-- Pending confirmations (for trading commands)
CREATE TABLE IF NOT EXISTS pending_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    command TEXT NOT NULL,             -- 'buy' or 'sell'
    symbol TEXT NOT NULL,
    amount TEXT,                       -- Decimal as string
    quantity TEXT,                     -- Decimal as string
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,     -- 60s TTL
    status TEXT DEFAULT 'pending'     -- pending | confirmed | cancelled | expired
);
```

---

## 11. Dependencies

```toml
# Added to pyproject.toml [project.optional-dependencies]
messaging = [
    "python-telegram-bot>=21.0",
]
```

The `python-telegram-bot` library provides:
- Async Telegram Bot API wrapper
- Long-polling and webhook support
- Message parsing and keyboard builders
- Rate limiting built-in

---

## 12. Implementation Plan

### Phase 1 — Core Infrastructure
1. Create `models/messaging.py` (data models)
2. Create `messaging/protocols.py` (provider protocol)
3. Create `messaging/auth.py` (AuthGuard)
4. Add `MessagingConfig` to `models/config.py`
5. Add `messaging_log` schema to database

### Phase 2 — Telegram Provider + Outbound Notifications
6. Create `messaging/providers/telegram.py`
7. Create `messaging/providers/factory.py`
8. Create `messaging/formatters.py` (DD reports, trades → formatted messages)
9. Create `messaging/service.py` (NotificationService)
10. Hook into `dd_agent.py`, `trade_executor.py`, `position_manager.py`

### Phase 3 — Inbound Commands
11. Create `messaging/commands/base.py` (BaseCommandHandler)
12. Create `messaging/commands/router.py` (CommandRouter)
13. Create `messaging/commands/status.py` (/status, /positions, /history)
14. Create `messaging/commands/analyze.py` (/analyze, /dd)
15. Create `messaging/commands/trading.py` (/buy, /sell, /confirm, /cancel)

### Phase 4 — Integration & Testing
16. Integrate listener into `v2_engine.py` autonomous loop
17. Add CLI command `bvr messaging setup` for verification flow
18. Write unit tests for all components
19. Integration test with Telegram sandbox

---

## 13. Extending to Other Providers

Adding a new provider (e.g., Discord) requires:

1. **Create provider class** implementing `MessagingProvider` protocol:
   ```python
   class DiscordProvider:
       provider_name = "discord"
       async def send_message(self, msg: OutboundMessage) -> bool: ...
       async def start_listening(self) -> None: ...
       ...
   ```

2. **Add config model**:
   ```python
   class DiscordConfig(BaseModel):
       bot_token_env: str = "BEAVR_DISCORD_BOT_TOKEN"
       guild_id: str
       channel_id: str
   ```

3. **Register in factory**:
   ```python
   # messaging/providers/factory.py
   def create_provider(config: MessagingConfig) -> MessagingProvider:
       if config.provider == "discord":
           return DiscordProvider(config.discord)
   ```

4. **Add dependency**:
   ```toml
   discord = ["discord.py>=2.0"]
   ```

No changes needed to `NotificationService`, `CommandRouter`, formatters, or command handlers — they all work through the protocol abstraction.

---

## 14. Open Questions

1. **Multiple providers simultaneously?** Current design supports one active provider. Should we support sending to both Telegram and Discord at once? (Recommendation: start single, add multi-dispatch later if needed.)

2. **File attachments?** DD reports could be sent as PDF/Markdown file attachments. Worth implementing in Phase 1? (Recommendation: start with inline text, add file attachments in a follow-up.)

3. **Scheduled summaries?** Should the bot send a daily portfolio summary at market close? (Recommendation: yes, add as a post-Phase 3 enhancement.)

---

*Awaiting approval to proceed with implementation.*
