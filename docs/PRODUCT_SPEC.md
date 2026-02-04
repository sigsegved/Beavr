# Beavr - Auto Trading Platform
## Product Specification

**Version:** 3.0  
**Date:** January 19, 2026  
**Status:** Planning Phase

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Strategy System](#3-strategy-system)
4. [Configuration](#4-configuration)
5. [CLI Reference](#5-cli-reference)
6. [Development Roadmap](#6-development-roadmap)
7. [Risk & Compliance](#7-risk--compliance)
8. [Success Metrics](#8-success-metrics)
9. [Open Questions](#9-open-questions)
10. [Appendix](#appendix)

---

## 1. Executive Summary

Beavr is an open-source automated trading platform designed to help retail investors build wealth through algorithmic trading strategies. The platform emphasizes **simplicity** and **extensibility** - strategies are Python classes with a common interface, configured via TOML.

### 1.1 Core Strategies (Initial Release)

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **DCA Dip** | Buy on dips with month-end fallback | Long-term ETF accumulation (SPY, VOO, QQQ) |
| **Volatility Swing** | Buy dips, sell bounces | Short-term trading of volatile stocks (TSLA, NVDA) |

### 1.2 Key Design Principles

- **Simple** - Strategy templates with TOML configuration; most users never write code
- **Extensible** - Common strategy interface for power users and community contributions
- **Transparent** - Full visibility into trading decisions and portfolio state
- **Safe** - Paper trading first, position limits, comprehensive logging

### 1.3 Architecture Highlights

- **Virtual Sub-Accounts**: Run multiple strategies with isolated allocations on a single Alpaca account
- **Lot-Based Tracking**: Track the same asset across strategies via local ledger
- **Strategy Interface**: Python classes with `BaseStrategy` interface - testable, type-safe, IDE-friendly
- **TOML Parameters**: Users configure strategy behavior via parameters, not code
- **Built-in Templates**: Ship with common strategies (DCA, Swing, Momentum, Mean Reversion)

### 1.4 Technology Stack

| Component | Technology |
|-----------|------------|
| Broker Integration | Alpaca-py (official SDK) |
| Backtesting | VectorBT or backtesting.py |
| Technical Analysis | pandas-ta (local computation) |
| Scheduling | APScheduler |
| CLI | Typer + Rich |
| Configuration | TOML + Pydantic |
| Local Database | SQLite |

---

## 2. System Architecture

### 2.1 High-Level Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLI Layer (bvr)                          │
│  bvr init | bvr run | bvr backtest | bvr status | bvr config       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Core Engine                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Strategy   │  │  Portfolio  │  │  Scheduler  │                 │
│  │  Engine     │  │  Manager    │  │  Service    │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
│         │               │                                           │
│  ┌─────────────────────────────────────────────┐                   │
│  │              Plugin Registry                │                   │
│  │  Indicators | Strategies                    │                   │
│  └─────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Integration Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Broker     │  │  Market     │  │  Notifier   │                 │
│  │  Adapter    │  │  Data       │  │  Service    │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                  │
│  ┌─────────────────────────────────────────────┐                   │
│  │  SQLite Database (Lot Ledger, Trades, State)│                   │
│  └─────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      External Services                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Alpaca     │  │  Alpaca     │  │  Discord/   │                 │
│  │  Trading    │  │  Market Data│  │  Email      │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Virtual Sub-Accounts

Since Alpaca retail accounts are limited to one account, Beavr implements **virtual sub-accounts** to isolate strategy allocations.

```
┌──────────────────────────────────────────────────────────────────┐
│                    Alpaca Physical Account                       │
│                    Total: $10,000                                │
│   ┌──────────────────────────────────────────────────────────┐   │
│   │ Positions: TSLA(10), SPY(5), QQQ(3)                      │   │
│   └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                              │
                    Beavr Virtual Accounting
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ Strategy: DCA │     │ Strategy:     │     │   Unallocated │
│ Budget: $6,000│     │ Swing         │     │   Cash: $500  │
│               │     │ Budget: $3,500│     │               │
│ Positions:    │     │               │     │               │
│  SPY: 5 shares│     │ Positions:    │     │               │
│  QQQ: 3 shares│     │  TSLA: 10     │     │               │
│ Cash: $1,200  │     │ Cash: $800    │     │               │
└───────────────┘     └───────────────┘     └───────────────┘
```

**Key Concepts:**
- **Physical Account**: One Alpaca account with aggregated positions
- **Virtual Accounts**: Beavr tracks per-strategy allocations in SQLite
- **Lot Tracking**: Each purchase is tagged with `strategy_id` via `client_order_id`
- **Reconciliation**: Periodic sync between Beavr ledger and Alpaca positions

### 2.3 Lot-Based Position Tracking

When multiple strategies trade the same asset:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Alpaca Position: TSLA                       │
│                     Total: 15 shares @ $248.50 avg              │
└─────────────────────────────────────────────────────────────────┘
                              │
                    Beavr Lot Ledger (SQLite)
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
┌─────────────────────────┐           ┌─────────────────────────┐
│      Lot #1 (Swing)     │           │      Lot #2 (Custom)    │
│  Strategy: swing_trades │           │  Strategy: my_strategy  │
│  Shares: 10             │           │  Shares: 5              │
│  Entry: $245.00         │           │  Entry: $255.00         │
│  Date: 2026-01-15       │           │  Date: 2026-01-18       │
│  Order: ord_abc123      │           │  Order: ord_def456      │
└─────────────────────────┘           └─────────────────────────┘
```

---

## 3. Strategy System

### 3.1 How It Works

Strategies are **Python classes** implementing a common interface. Users configure them via **TOML parameters** - most users never write Python code.

```
┌─────────────────────────────────────────────────────────────────┐
│                     User's TOML Config                          │
│  ~/.beavr/strategies/my_dca.toml                                │
├─────────────────────────────────────────────────────────────────┤
│  template = "dca_dip"        # Which strategy class to use      │
│  [params]                    # Strategy-specific parameters     │
│  dip_threshold = 0.02                                           │
│  symbols = ["SPY", "QQQ"]                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Python Strategy Class                         │
│  beavr/strategies/dca_dip.py                                    │
├─────────────────────────────────────────────────────────────────┤
│  class DCADipStrategy(BaseStrategy):                            │
│      dip_threshold: float = Field(0.02, ge=0.01, le=0.10)       │
│      symbols: list[str] = ["SPY"]                               │
│                                                                 │
│      def evaluate(self, ctx: StrategyContext) -> list[Signal]:  │
│          # Strategy logic here                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principle:** TOML defines **parameters** (what values), Python defines **logic** (how it works).

### 3.2 Built-in Strategy Templates

| Template | Description | Budget Reset | Default Interval |
|----------|-------------|--------------|------------------|
| `dca_dip` | Buy dips with month-end fallback | Monthly | Daily |
| `volatility_swing` | Buy dips, sell bounces | Never (reuse capital) | 5 minutes |
| `momentum` | Buy trending assets | Never | Daily |
| `mean_reversion` | Buy oversold, sell overbought | Never | Hourly |
| `rebalance` | Periodic portfolio rebalancing | Monthly | Weekly |

### 3.3 Built-in Indicators

Computed locally using pandas-ta (Alpaca provides only raw OHLCV):

| Type | Description | Params |
|------|-------------|--------|
| `sma` | Simple Moving Average | `period` |
| `ema` | Exponential Moving Average | `period` |
| `rsi` | Relative Strength Index | `period` |
| `macd` | MACD histogram | `fast`, `slow`, `signal` |
| `bollinger` | Bollinger Bands | `period`, `std` |
| `atr` | Average True Range | `period` |
| `daily_change` | % change from previous close | - |
| `range_high` | Highest price in lookback | `period` |
| `range_low` | Lowest price in lookback | `period` |

### 3.4 Custom Strategies (Plugins)

**Most users don't need this.** The built-in templates cover common use cases. But if you want to write your own strategy logic, you can create custom Python classes.

**Where code lives:**

| Location | What | Who Maintains |
|----------|------|---------------|
| `beavr/strategies/` | Built-in templates (`dca_dip`, `volatility_swing`) | Beavr project |
| `~/.beavr/plugins/strategies/` | Your custom strategies | You |

**Why use plugins instead of modifying Beavr source?**
- Your code survives Beavr upgrades
- No need to fork the repo
- Keep proprietary strategies private
- Share with others without contributing to main repo

**Example:** Create `~/.beavr/plugins/strategies/my_rsi.py`, add `@register_strategy("my_rsi")` decorator, then reference it in TOML with `template = "my_rsi"`.

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for full code examples.

---

## 4. Configuration

### 4.1 Main Configuration

```toml
# ~/.beavr/config.toml

[broker]
name = "alpaca"
paper_trading = true
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"

[portfolio]
total_allocation = 10000
reserve_cash_pct = 5                # Keep 5% as buffer

# Enable strategies and set allocations
[strategies.my_etf_dca]
enabled = true
allocation = 6000

[strategies.my_swing]
enabled = true
allocation = 3500

[notifications]
enabled = true

[notifications.discord]
enabled = true
webhook_url_env = "DISCORD_WEBHOOK"
events = ["trade", "error", "daily_summary"]

[logging]
level = "INFO"
file = "~/.beavr/logs/beavr.log"

[schedule]
timezone = "America/New_York"
```

### 4.2 Strategy Configuration Examples

#### DCA for ETFs

```toml
# ~/.beavr/strategies/my_etf_dca.toml

template = "dca_dip"

[params]
symbols = ["VOO", "QQQ"]
weights = { VOO = 0.6, QQQ = 0.4 }
dip_threshold = 0.02        # Buy on 2% dips
dip_buy_pct = 0.50          # Use 50% of remaining budget on dip
fallback_days = 3           # Deploy remaining in last 3 days

[schedule]
interval = "1d"
at = "10:00"
market_hours_only = true
```

#### Swing Trading

```toml
# ~/.beavr/strategies/my_swing.toml

template = "volatility_swing"

[params]
symbols = ["AAPL", "MSFT", "GOOGL"]
entry_drop_pct = 0.04       # Wait for 4% drop
take_profit_pct = 0.03      # Take profit at 3%
stop_loss_pct = 0.04        # Tighter stop loss
max_hold_days = 7           # Exit faster
position_size = 300         # Smaller positions

[schedule]
interval = "15m"
market_hours_only = true
```

---

## 5. CLI Reference

```bash
# Setup
bvr init                    # Initialize configuration
bvr config                  # View/edit configuration

# Strategies
bvr strategy list           # List available strategies
bvr strategy add <name>     # Add a strategy to portfolio
bvr strategy validate       # Validate strategy TOML files

# Portfolio
bvr portfolio               # View portfolio allocations
bvr portfolio reconcile     # Sync with Alpaca positions

# Trading
bvr run                     # Start the trading engine (daemon)
bvr run --paper             # Paper trading mode
bvr stop                    # Stop the trading engine
bvr status                  # Check engine status

# Analysis
bvr backtest <strategy>     # Backtest a strategy
bvr logs                    # View trading logs
bvr trades                  # View trade history
bvr lots                    # View lot-level positions
```

---

## 6. Development Roadmap

### Phase 1: Foundation (Weeks 1-4)
- [ ] Project setup (Poetry, testing, CI/CD)
- [ ] Core data models (Pydantic)
- [ ] Configuration management (TOML)
- [ ] SQLite database setup (lot ledger)
- [ ] Alpaca broker integration
- [ ] Basic CLI scaffold (Typer + Rich)

### Phase 2: Strategy Engine (Weeks 5-8)
- [ ] `BaseStrategy` interface and `StrategyContext`
- [ ] Strategy registry with `@register_strategy` decorator
- [ ] Indicator computation service (pandas-ta)
- [ ] Signal generation and validation
- [ ] Built-in: `DCADipStrategy`, `VolatilitySwingStrategy`

### Phase 3: Portfolio & Trading (Weeks 9-12)
- [ ] Virtual sub-account manager
- [ ] Lot tracking and ledger
- [ ] Order management with `client_order_id` tagging
- [ ] Position reconciliation with Alpaca
- [ ] Paper trading mode

### Phase 4: Polish (Weeks 13-16)
- [ ] Plugin auto-discovery
- [ ] Notifications (Discord, email)
- [ ] Comprehensive CLI commands
- [ ] Backtesting integration
- [ ] Documentation & examples
- [ ] Beta release

### Phase 5: Enhancement (Future)
- [ ] Web dashboard
- [ ] LLM strategy generation
- [ ] Multi-broker support (Schwab, IBKR)
- [ ] Community strategy marketplace

---

## 7. Risk & Compliance

### 7.1 Trading Risks
- Market risk: Strategies may lose money
- Execution risk: Orders may not fill at expected prices
- System risk: Bugs could cause unintended trades

### 7.2 Mitigations
- Paper trading mode for testing
- Position limits and stop losses
- Comprehensive logging
- Lot-level tracking for full audit trail
- Reconciliation with Alpaca to catch discrepancies
- Clear disclaimers in documentation

### 7.3 Compliance
- Alpaca handles regulatory compliance
- Users responsible for tax reporting
- Lot tracking enables accurate cost basis reporting
- No financial advice provided

---

## 8. Success Metrics

### 8.1 Technical
- 95%+ test coverage
- <100ms CLI response time
- 99.9% uptime for daemon
- Zero discrepancies in lot reconciliation

### 8.2 Community
- 1000+ GitHub stars in year 1
- 10+ community-contributed strategies and indicators
- Active Discord community

### 8.3 Trading
- Successful paper trading for 3+ months
- Documented strategy performance
- User success stories

---

## 9. Open Questions

1. **Backtesting**: Build custom or integrate VectorBT?
2. **Web UI**: Priority for Phase 5 or community contribution?
3. **Strategy marketplace**: How to handle trust/verification?
4. **Multi-broker**: When to prioritize beyond Alpaca?

---

## Appendix

### A. Existing Open Source Projects Analysis

#### A.1 Evaluated Projects

| Project | Language | Stars | Focus | Pros | Cons |
|---------|----------|-------|-------|------|------|
| **Freqtrade** | Python | 46k | Crypto trading | Mature, excellent backtesting, Telegram integration, ML support | Crypto-focused, complex for equity trading |
| **Zipline-Reloaded** | Python | 1.6k | Backtesting | Industry standard for backtesting, pandas integration | Backtesting only, no live trading |
| **Alpaca-py** | Python | 1.1k | Broker API | Official SDK, stocks + crypto, commission-free, paper trading | Just an API wrapper, no strategy engine |
| **Blankly** | Python | 2.4k | Multi-asset | Same code for backtest/live, multiple brokers | Less mature, company pivoted |
| **Superalgos** | JavaScript | 5.2k | Visual algo design | Visual editor, complete platform | Very complex, crypto-focused, heavy |
| **VectorBT** | Python | 5k+ | Backtesting | Extremely fast backtesting | Research tool, not trading engine |
| **Jesse** | Python | 5k+ | Crypto trading | Clean design, good docs | Crypto only |

#### A.2 Key Findings

1. **No perfect fit exists** - Most mature projects are crypto-focused
2. **Equity trading gap** - Few open-source options for stock/ETF algorithmic trading
3. **Alpaca is the broker of choice** - Commission-free, great API, paper trading support
4. **Python dominates** - Best ecosystem for financial libraries and ML integration

---

### B. Architecture Options Considered

#### B.1 Option A: Build on Freqtrade

**Approach:** Fork/extend Freqtrade to support equity trading via Alpaca

| Pros | Cons |
|------|------|
| Mature codebase with 46k stars | Crypto-centric architecture |
| Excellent backtesting engine | Significant refactoring needed |
| Telegram/WebUI built-in | Complex plugin system to learn |
| ML/hyperopt support | Overkill for simple strategies |
| Large community | GPL license may be restrictive |

**Effort:** High (3-6 months to adapt)  
**Risk:** Medium-High (architecture mismatch)

#### B.2 Option B: Build on Blankly

**Approach:** Use Blankly as base framework, extend with strategy engine

| Pros | Cons |
|------|------|
| Designed for multi-asset | Company pivoted, less active |
| Same code for backtest/live | Smaller community |
| Alpaca integration exists | Beta quality in some areas |
| Clean Python architecture | Limited documentation |

**Effort:** Medium (2-4 months)  
**Risk:** Medium (maintenance concerns)

#### B.3 Option C: Build Fresh with Alpaca-py

**Approach:** Custom build using Alpaca-py SDK + composable architecture

| Pros | Cons |
|------|------|
| Complete control over design | More upfront work |
| Clean, modern architecture | No free backtesting engine |
| Optimized for our use case | Must build many components |
| Permissive licensing (Apache 2.0) | Longer initial timeline |
| Easier to maintain long-term | |

**Effort:** Medium-High (3-5 months for MVP)  
**Risk:** Low-Medium (clear path, no legacy)

#### B.4 Option D: Hybrid Approach (Selected)

**Approach:** Fresh build using best-of-breed components

**Justification:**
1. **Right-sized solution** - Not over-engineered, but extensible
2. **Equity-first** - Built for stocks/ETFs from day one
3. **Best components** - Leverage mature libraries where they excel
4. **Clean CLI UX** - Full control over the `bvr` command experience
5. **LLM-ready** - Architecture supports future AI strategy generation
6. **Community-friendly** - Apache 2.0 license, Python for accessibility

**Effort:** Medium (3-4 months for MVP)  
**Risk:** Low (proven components, clear architecture)

---

### C. Alpaca API Constraints

Important limitations discovered during research:

| Feature | Alpaca Reality |
|---------|----------------|
| **Multiple Accounts** | Retail Trading API = 1 account only. Broker API requires business registration. |
| **Technical Indicators** | None provided. Alpaca delivers raw OHLCV bars only. |
| **Order Tagging** | `client_order_id` field (up to 128 chars) available for custom metadata |
| **Free Tier** | IEX exchange data, 200 API calls/min, 30 websocket symbols |
| **Algo Trader Plus** | $99/mo: All exchanges, 10K API calls/min, unlimited websockets |

**Implications for Beavr:**
- Virtual sub-accounts (multiple strategies on one physical account)
- Local indicator computation using pandas-ta
- Lot-based tracking for same-asset positions across strategies

---

### D. Future Multi-Broker Support

#### D.1 Broker Landscape

| Broker | API Type | Order Tagging | Fractional | Commissions |
|--------|----------|---------------|------------|-------------|
| **Alpaca** | REST + WebSocket | `client_order_id` (128 chars) | ✅ | Free |
| **Charles Schwab** | REST | `client_order_id` | ❌ | $0 stocks |
| **Interactive Brokers** | TWS/Client Portal | `clientId` + `orderId` | ✅ (some) | Tiered |
| **Robinhood** | REST (unofficial) | Limited | ✅ | Free |
| **Tradier** | REST | `tag` field | ❌ | $0 stocks |

#### D.2 Multi-Broker Configuration (Future)

```toml
# ~/.beavr/config.toml

[broker]
primary = "alpaca"

[broker.alpaca]
enabled = true
paper_trading = true
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"

[broker.schwab]
enabled = false
client_id_env = "SCHWAB_CLIENT_ID"
client_secret_env = "SCHWAB_CLIENT_SECRET"
```

---

### E. Resolved Design Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Config format | **TOML** | No gotchas, Python standard |
| Database | **SQLite** | Simple, file-based, perfect for lot tracking |
| Portfolio model | **Virtual sub-accounts** | Multiple strategies on one Alpaca account |
| Indicators | **Local computation** | Alpaca provides only raw OHLCV |
| Strategy definition | **Python classes** | Type-safe, testable, IDE-friendly |
| Extensibility | **Plugin system** | `@register_*` decorators for custom code |
| Multi-broker | **Adapter pattern** | Abstract interface with normalized models |

---

## Related Documents

- [IMPLEMENTATION.md](IMPLEMENTATION.md) - Technical implementation details, code examples, data models, and project structure
