# Webull Integration — Design Specification

**Version:** 1.1  
**Date:** February 15, 2026  
**Status:** Final — Approved for Implementation  
**Author:** Beavr Developer Agent

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Goals & Non-Goals](#3-goals--non-goals)
4. [Current Architecture Analysis](#4-current-architecture-analysis)
5. [Proposed Architecture](#5-proposed-architecture)
6. [Broker Abstraction Layer](#6-broker-abstraction-layer)
7. [Market Data Abstraction Layer](#7-market-data-abstraction-layer)
8. [Webull Adapter Implementation](#8-webull-adapter-implementation)
9. [Configuration Design](#9-configuration-design)
10. [Migration Plan for Existing Code](#10-migration-plan-for-existing-code)
11. [Key Differences & Edge Cases](#11-key-differences--edge-cases)
12. [Testing Strategy](#12-testing-strategy)
13. [Implementation Phases](#13-implementation-phases)
14. [Open Questions](#14-open-questions)

---

## 1. Executive Summary

This document specifies the design for integrating Webull as a second broker platform in Beavr. Today, Beavr is hard-wired to Alpaca — the `alpaca-py` SDK is imported directly in data fetching, order execution, account queries, and screening. There is no broker abstraction.

The proposed design introduces a **Broker Protocol** and **Market Data Protocol** — Python `Protocol` classes that define the contracts for trading and data operations. Alpaca and Webull each get an **adapter** implementing these protocols. A **factory** selects the right adapter based on user configuration. All existing code (strategies, agents, orchestrator, CLI, backtest) will depend only on the protocols, never on SDK-specific types.

The Webull Python SDK (published on PyPI as `webull-python-sdk-*` packages) provides REST+gRPC trading APIs, REST+gRPC+MQTT market data, and gRPC trade event streaming. The SDK is added as a standard pip dependency alongside `alpaca-py`.

### Key Design Decisions (Resolved)

| Decision | Resolution |
|----------|------------|
| **Paper trading** | Webull provides a UAT/sandbox environment at `us-openapi-alb.uat.webullbroker.com`. Same APIs for paper and live — identical to Alpaca's model. Adapter uses `api_client.add_endpoint()` to switch. |
| **SDK packaging** | Standard pip dependency (`webull-python-sdk-core`, `webull-python-sdk-trade`, `webull-python-sdk-mdata` etc.) in `pyproject.toml`, same as `alpaca-py`. The vendored `openapi-python-sdk/` folder is for reference only. |
| **Screener/News** | Mixed-provider mode: data/news/screening can come from Alpaca while trading uses Webull. Trading is single-broker only. |
| **Market clock** | Always sourced from the brokerage API. Alpaca: `get_clock()`. Webull: `get_trade_calendar()` + system time. |
| **Instrument cache** | In-memory with SQLite persistence. Survives restarts, minimizes API calls on startup. |
| **Migration** | Immediate. No deprecation wrappers. The `data/` module is removed and all imports updated directly. |

---

## 2. Problem Statement

### 2.1 Alpaca Lock-in

Beavr is coupled to Alpaca in **four independent locations** that each create Alpaca SDK clients directly:

| Location | What it does | SDK Types Used |
|----------|-------------|----------------|
| `data/alpaca.py` → `AlpacaDataFetcher` | Historical bars | `StockHistoricalDataClient`, `CryptoHistoricalDataClient`, `StockBarsRequest` |
| `paper_trading.py` → `PaperTradingRunner` | Live execution | `TradingClient`, `MarketOrderRequest`, `OrderSide`, `TimeInForce` |
| `cli/ai.py` → `AIInvestor` | CLI execution | `TradingClient`, `StockHistoricalDataClient`, `MarketOrderRequest` |
| `orchestrator/v2_engine.py` → `V2AutonomousOrchestrator` | Autonomous trading | Receives untyped `Any` clients, calls `.get_account()`, `.submit_order()` |

Additionally:
- `data/screener.py` → `MarketScreener` uses Alpaca's `ScreenerClient` and `NewsClient`
- `backtest/engine.py` → `BacktestEngine` type-hints `AlpacaDataFetcher` directly
- `models/config.py` → `AlpacaConfig` is the only broker config model

### 2.2 Order Execution Duplication

Order submission logic is duplicated in three places: `PaperTradingRunner`, `AIInvestor` CLI, and `TradeExecutorAgent` (mock). Each builds `MarketOrderRequest` independently with slightly different error handling and fractional-share fallback logic.

### 2.3 Why Webull

- Webull supports both **paper and live trading** (via separate environments)
- Rich order types: Market, Limit, Stop, Stop-Limit, Trailing Stop, Market-on-Open, Market-on-Close
- Combo orders: OTO, OCO, OTOCO (stop-loss + take-profit in one request)
- Multi-market support: US, HK, JP
- Real-time streaming via MQTT + gRPC trade events
- Tick-level data and depth-of-book quotes
- Users should be able to **choose their broker** without changing strategies or agent logic

---

## 3. Goals & Non-Goals

### Goals

1. **Broker-agnostic architecture** — strategies, agents, orchestrator, and backtest engine depend on protocols, not SDK types
2. **Webull trading support** — place, modify, cancel orders; query account, positions, order history
3. **Webull market data support** — historical bars, snapshots, instrument resolution
4. **User-selectable broker** — single config field (`broker = "alpaca"` or `broker = "webull"`) switches the entire platform
5. **Consolidate order execution** — one code path for submitting orders, used by all callers
6. **Maintain backward compatibility** — existing Alpaca users experience no breaking changes
7. **Paper trading parity** — both Alpaca and Webull paper trading must work

### Non-Goals (for this iteration)

- Real-time streaming quotes (MQTT) — future enhancement
- gRPC trade event streaming — future enhancement
- Options trading via Webull — future enhancement
- Multi-market (HK/JP) support — US only for now
- Webull combo orders (OTO/OCO/OTOCO) — future enhancement
- Webull screener/news (not available in their SDK) — keep using Alpaca news for now, or make news optional
- Short selling via Webull — future enhancement

---

## 4. Current Architecture Analysis

### 4.1 Data Flow Today

```
                    ┌──────────────────────────────────┐
                    │         alpaca-py SDK             │
                    │  (TradingClient, DataClient, ...) │
                    └────────┬──────────┬───────────────┘
                             │          │
              ┌──────────────┘          └───────────────┐
              ▼                                         ▼
    ┌──────────────────┐                     ┌──────────────────┐
    │ AlpacaDataFetcher│                     │   TradingClient  │
    │   (data/alpaca)  │                     │  (used directly) │
    └────────┬─────────┘                     └────┬────┬────────┘
             │                                    │    │
    ┌────────┴──────────────────┐                 │    │
    ▼                           ▼                 │    │
BacktestEngine           StrategyContext          │    │
    │                         │                   │    │
    ▼                         ▼                   │    │
Strategy.evaluate() ──▶ list[Signal]              │    │
                                                  │    │
    ┌─────────────────────────────────────────────┘    │
    ▼                                                  ▼
PaperTradingRunner                            AIInvestor CLI
(submit_order)                                (submit_order)
```

### 4.2 What's Broker-Agnostic Today

These components have **no direct Alpaca dependency** and will work as-is:

| Component | Why it's clean |
|-----------|---------------|
| `BaseStrategy` + all strategies | Receive `StrategyContext`, return `list[Signal]` |
| `Signal`, `Trade`, `Position`, `PortfolioState` models | Pure Pydantic, no SDK types |
| `Bar` model | Generic OHLCV, no SDK dependency |
| All agents except `SymbolSelectorAgent` | Use `AgentContext` / `AgentProposal`, no broker calls |
| `SimulatedPortfolio` (backtest) | Pure simulation |
| `OrchestratorEngine` (v1) | Returns signals, doesn't execute |
| `Blackboard` | Shared state, no broker dependency |
| LLM layer | Completely independent |

### 4.3 What Needs Refactoring

| Component | Current Coupling | Required Change |
|-----------|-----------------|-----------------|
| `AlpacaDataFetcher` | Wraps `alpaca-py` data clients | Keep as Alpaca adapter, implement protocol |
| `PaperTradingRunner` | Creates `TradingClient` directly | Use broker protocol instead |
| `AIInvestor` CLI | Creates `TradingClient` + `DataClient` directly | Use factory to get broker adapter |
| `V2AutonomousOrchestrator` | Receives untyped Alpaca clients | Accept protocol types |
| `BacktestEngine` | Type-hints `AlpacaDataFetcher` | Type-hint `MarketDataProvider` protocol |
| `MarketScreener` | Uses Alpaca `ScreenerClient` | Make screening optional / broker-specific |
| `NewsScanner` | Uses Alpaca `NewsClient` | Make news optional / broker-specific |
| `AlpacaConfig` | Alpaca-specific config model | Generalize to `BrokerConfig` with subclasses |
| `AppConfig` | Has `alpaca: AlpacaConfig` field | Add `broker` discriminator field |

---

## 5. Proposed Architecture

### 5.1 Layered Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                                    │
│                                                                             │
│   CLI (AIInvestor)  │  Orchestrator  │  BacktestEngine  │  PaperTrading    │
│                                                                             │
│   Depends on: BrokerProvider + MarketDataProvider protocols                  │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BROKER ABSTRACTION LAYER (NEW)                       │
│                                                                             │
│   ┌───────────────────────┐     ┌────────────────────────┐                  │
│   │   BrokerProvider      │     │  MarketDataProvider    │                  │
│   │   (Protocol)          │     │  (Protocol)            │                  │
│   │                       │     │                        │                  │
│   │   • get_account()     │     │  • get_bars()          │                  │
│   │   • get_positions()   │     │  • get_snapshot()      │                  │
│   │   • submit_order()    │     │  • get_bars_multi()    │                  │
│   │   • cancel_order()    │     │                        │                  │
│   │   • get_order()       │     │                        │                  │
│   │   • get_orders()      │     │                        │                  │
│   │   • is_market_open()  │     │                        │                  │
│   └───────────┬───────────┘     └────────────┬───────────┘                  │
│               │                              │                              │
│       ┌───────┴───────┐              ┌───────┴───────┐                      │
│       ▼               ▼              ▼               ▼                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐                 │
│  │  Alpaca  │   │  Webull  │   │  Alpaca  │   │  Webull  │                 │
│  │  Broker  │   │  Broker  │   │  Data    │   │  Data    │                 │
│  │  Adapter │   │  Adapter │   │  Adapter │   │  Adapter │                 │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘                 │
│       │               │              │               │                      │
└───────┼───────────────┼──────────────┼───────────────┼──────────────────────┘
        ▼               ▼              ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐
   │ alpaca-py│   │  webull  │   │ alpaca-py│   │   webull     │
   │   SDK    │   │   SDK    │   │   SDK    │   │    SDK       │
   └──────────┘   └──────────┘   └──────────┘   └──────────────┘
```

### 5.2 Factory Pattern

```
┌──────────────────────────────┐
│     User Config (TOML)       │
│                              │
│  [broker]                    │
│  provider = "webull"         │
│  paper = true                │
│                              │
│  [broker.webull]             │
│  app_key_env = "WEBULL_..."  │
│  app_secret_env = "WEBULL_." │
│  account_id_env = "WEBULL_." │
│  region = "us"               │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      BrokerFactory           │
│                              │
│  create_broker(config)       │──▶ BrokerProvider
│  create_data_provider(config)│──▶ MarketDataProvider
└──────────────────────────────┘
```

---

## 6. Broker Abstraction Layer

### 6.1 Broker-Agnostic Domain Models

New models in `src/beavr/models/broker.py` that both adapters map to/from:

```python
class AccountInfo(BaseModel):
    """Broker-agnostic account information."""
    account_id: str
    cash: Decimal
    portfolio_value: Decimal
    buying_power: Decimal
    currency: str = "USD"

class BrokerPosition(BaseModel):
    """Broker-agnostic position from the broker."""
    symbol: str
    quantity: Decimal
    market_value: Decimal
    avg_cost: Decimal
    unrealized_pl: Decimal
    side: Literal["long", "short"]

class OrderRequest(BaseModel):
    """Broker-agnostic order request."""
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Optional[Decimal] = None    # shares
    notional: Optional[Decimal] = None    # dollar amount (fractional)
    order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"]
    time_in_force: Literal["day", "gtc", "ioc"]
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    extended_hours: bool = False
    client_order_id: Optional[str] = None

class OrderResult(BaseModel):
    """Broker-agnostic order result."""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    filled_quantity: Decimal
    filled_avg_price: Optional[Decimal]
    status: Literal["pending", "accepted", "partial", "filled", "cancelled", "failed"]
    submitted_at: datetime
    filled_at: Optional[datetime]

class MarketClock(BaseModel):
    """Broker-agnostic market clock."""
    is_open: bool
    next_open: datetime
    next_close: datetime
```

### 6.2 BrokerProvider Protocol

```python
class BrokerProvider(Protocol):
    """Protocol for broker trading operations.
    
    All broker adapters (Alpaca, Webull, etc.) implement this interface.
    Application code depends ONLY on this protocol.
    """

    def get_account(self) -> AccountInfo: ...

    def get_positions(self) -> list[BrokerPosition]: ...

    def get_position(self, symbol: str) -> Optional[BrokerPosition]: ...

    def submit_order(self, order: OrderRequest) -> OrderResult: ...

    def cancel_order(self, order_id: str) -> None: ...

    def get_order(self, order_id: str) -> OrderResult: ...

    def list_orders(
        self,
        status: Literal["open", "closed", "all"] = "open",
        limit: int = 50,
    ) -> list[OrderResult]: ...

    def get_clock(self) -> MarketClock: ...

    @property
    def supports_fractional(self) -> bool: ...

    @property
    def broker_name(self) -> str: ...
```

### 6.3 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use `Protocol` (structural typing), not ABC | Adapters don't need to inherit; easier testing with simple mocks |
| `OrderRequest` uses `symbol` not `instrument_id` | Adapters handle symbol→instrument_id translation internally |
| `quantity` and `notional` are both optional on `OrderRequest` | Supports both share-based and dollar-based orders; adapter validates which are supported |
| All Decimal, no float | Per Beavr coding standards |
| Sync methods only (no async) | Current codebase is synchronous; async can be added later |
| `client_order_id` on `OrderRequest` | Critical for Beavr's lot tracking — both Alpaca and Webull support it |

---

## 7. Market Data Abstraction Layer

### 7.1 MarketDataProvider Protocol

```python
class MarketDataProvider(Protocol):
    """Protocol for market data operations."""

    def get_bars(
        self,
        symbol: str,
        timeframe: Literal["1min", "5min", "15min", "30min", "1hour", "1day", "1week"],
        start: date,
        end: date,
    ) -> pd.DataFrame: ...
    # Returns DataFrame with columns: open, high, low, close, volume (all Decimal)

    def get_bars_multi(
        self,
        symbols: list[str],
        timeframe: Literal["1min", "5min", "15min", "30min", "1hour", "1day", "1week"],
        start: date,
        end: date,
    ) -> dict[str, pd.DataFrame]: ...

    def get_snapshot(
        self,
        symbols: list[str],
    ) -> dict[str, dict]: ...
    # Returns {symbol: {price, open, high, low, close, volume, ...}}

    @property
    def provider_name(self) -> str: ...
```

### 7.2 Timeframe Mapping

The protocol uses human-readable timeframe strings. Each adapter maps these internally:

| Protocol | Alpaca (`TimeFrame`) | Webull (`Timespan`) |
|----------|---------------------|---------------------|
| `"1min"` | `TimeFrame.Minute` | `Timespan.M1` |
| `"5min"` | `TimeFrame(5, TimeFrameUnit.Minute)` | `Timespan.M5` |
| `"15min"` | `TimeFrame(15, TimeFrameUnit.Minute)` | `Timespan.M15` |
| `"30min"` | `TimeFrame(30, TimeFrameUnit.Minute)` | `Timespan.M30` |
| `"1hour"` | `TimeFrame.Hour` | `Timespan.M60` |
| `"1day"` | `TimeFrame.Day` | `Timespan.D` |
| `"1week"` | `TimeFrame.Week` | `Timespan.W` |

### 7.3 Screener & News — Optional Capabilities

Not every broker provides screener or news APIs. These remain **optional, broker-specific capabilities** accessed via a separate protocol:

```python
class ScreenerProvider(Protocol):
    """Optional — not all brokers support screening."""
    def get_market_movers(self, top: int = 20) -> list[dict]: ...
    def get_most_actives(self, top: int = 20) -> list[dict]: ...

class NewsProvider(Protocol):
    """Optional — not all brokers support news."""
    def get_news(self, symbols: list[str], limit: int = 10) -> list[dict]: ...
```

Alpaca implements both. Webull implements neither (its SDK has no screener/news).

**Mixed-provider mode:** When trading via Webull, the system can still use Alpaca's screener and news APIs for data enrichment. The factory supports independent provider selection:

- **Trading** → single broker only (Webull OR Alpaca, never both)
- **Market data** → can come from either broker (configurable)
- **Screener/News** → always Alpaca (only provider with these APIs), requires Alpaca API keys even when trading via Webull

The factory accepts separate config for `data_provider` and `news_provider` in addition to `broker`:

```toml
[broker]
provider = "webull"       # Trading via Webull
paper = true

[data]
provider = "webull"       # Market data from Webull (default: same as broker)

[news]
provider = "alpaca"       # News/screener from Alpaca (requires Alpaca keys)
```

When `[news]` is configured, the factory creates an Alpaca-backed `ScreenerProvider` and `NewsProvider` regardless of the trading broker. If no Alpaca keys are available and Webull is the broker, screener/news features are simply unavailable — agents that depend on them skip those steps gracefully.

---

## 8. Webull Adapter Implementation

### 8.1 File Structure

```
src/beavr/
├── broker/                          # NEW - Broker abstraction
│   ├── __init__.py                  # Exports protocols + factory
│   ├── protocols.py                 # BrokerProvider, MarketDataProvider, ScreenerProvider, NewsProvider
│   ├── models.py                    # AccountInfo, OrderRequest, OrderResult, etc.
│   ├── factory.py                   # BrokerFactory — creates broker/data/news providers from config
│   ├── alpaca/                      # Alpaca adapter (refactored from existing code)
│   │   ├── __init__.py
│   │   ├── broker.py                # AlpacaBroker(BrokerProvider)
│   │   ├── data.py                  # AlpacaMarketData(MarketDataProvider)
│   │   ├── screener.py             # AlpacaScreener(ScreenerProvider) — moved from data/screener.py
│   │   └── news.py                 # AlpacaNews(NewsProvider) — moved from data/screener.py
│   └── webull/                      # NEW - Webull adapter
│       ├── __init__.py
│       ├── broker.py                # WebullBroker(BrokerProvider)
│       ├── data.py                  # WebullMarketData(MarketDataProvider)
│       └── instrument_cache.py      # Symbol↔instrument_id cache (in-memory + SQLite)
├── data/                            # DELETED (all imports updated to broker/)
```

### 8.2 WebullBroker Adapter — Key Considerations

#### Symbol → instrument_id Resolution

The biggest difference: Alpaca uses symbols directly (`"AAPL"`), Webull requires numeric `instrument_id`. The Webull adapter must:

1. Maintain an **`InstrumentCache`** (symbol → instrument_id mapping)
2. Call `api.instrument.get_instrument(symbols, category)` on cache miss
3. Cache results in memory + optionally SQLite for persistence
4. All public methods accept `symbol: str` — the adapter resolves internally

```
User calls: broker.submit_order(OrderRequest(symbol="AAPL", ...))
                │
                ▼
    WebullBroker.submit_order()
        │
        ├── instrument_cache.resolve("AAPL") → "913256135"
        │       │ (cache miss)
        │       └── api.instrument.get_instrument(["AAPL"], "US_STOCK")
        │
        └── api.order.place_order(
                account_id=self.account_id,
                instrument_id="913256135",
                side=OrderSide.BUY,
                ...
            )
```

#### Account ID Management

Webull requires `account_id` for every trading call. Alpaca doesn't (implicit from API key). The Webull adapter:

1. Accepts `account_id` from config, OR
2. Auto-discovers via `api.account.get_app_subscriptions()` on first use
3. Caches the account_id for subsequent calls

#### Pagination Handling

Webull position and order list endpoints are paginated (cursor-based, max 100 per page). The adapter **auto-paginates** and returns complete lists, matching Alpaca's behavior of returning all results.

#### Fractional Shares

Webull supports dollar-based orders via `OrderEntrustType.AMOUNT`. When `OrderRequest.notional` is set (instead of `quantity`), the adapter uses amount-based ordering. The `supports_fractional` property returns `True`.

### 8.3 WebullMarketData Adapter — Key Considerations

#### Category Mapping

Webull requires a `category` parameter for all data calls. The adapter auto-detects:

| Symbol Pattern | Category |
|---------------|----------|
| Contains `/` (e.g., `BTC/USD`) | `CRYPTO` |
| In known ETF list or ends with common ETF patterns | `US_ETF` |
| Default | `US_STOCK` |

This can be refined with instrument metadata lookups.

#### Bar Limit

Webull returns max 1200 bars per request (vs Alpaca's 10000). For large date ranges, the adapter must **paginate** by making multiple requests with adjusted date ranges and concatenating results.

#### DataFrame Format

The adapter normalizes Webull's response to match the same DataFrame format `AlpacaDataFetcher` returns:
- Index: `DatetimeIndex` (UTC)
- Columns: `open`, `high`, `low`, `close`, `volume` (all `Decimal`)
- Sorted ascending by timestamp

### 8.4 Paper Trading with Webull

Webull provides a dedicated **UAT/sandbox environment** for paper trading, confirmed via their official developer documentation:

- **Production endpoint:** `api.webull.com`
- **Test/UAT endpoint:** `us-openapi-alb.uat.webullbroker.com`

This is functionally identical to Alpaca's `paper=True` model — same APIs, separate environment. The Webull adapter implements this via the SDK's `add_endpoint()` method:

```
When paper=True:
    api_client.add_endpoint("us", "us-openapi-alb.uat.webullbroker.com")

When paper=False:
    Uses default endpoint (api.webull.com) from endpoints.json
```

Users provide the same `app_key`/`app_secret` credentials for both environments (Webull's developer portal issues separate sandbox keys). The `paper: bool` config flag controls which endpoint is used — no code changes needed between paper and live.

---

## 9. Configuration Design

### 9.1 Updated Config Model

```python
class BrokerConfig(BaseModel):
    """Base broker configuration."""
    provider: Literal["alpaca", "webull"] = "alpaca"
    paper: bool = True

class AlpacaConfig(BrokerConfig):
    """Alpaca-specific broker configuration."""
    provider: Literal["alpaca"] = "alpaca"
    api_key_env: str = "ALPACA_API_KEY"
    api_secret_env: str = "ALPACA_API_SECRET"

class WebullConfig(BrokerConfig):
    """Webull-specific broker configuration."""
    provider: Literal["webull"] = "webull"
    app_key_env: str = "WEBULL_APP_KEY"
    app_secret_env: str = "WEBULL_APP_SECRET"
    account_id_env: str = "WEBULL_ACCOUNT_ID"
    region: Literal["us", "hk", "jp"] = "us"

class DataProviderConfig(BaseModel):
    """Market data provider config. Defaults to same as broker."""
    provider: Literal["alpaca", "webull"] | None = None  # None = follow broker

class NewsProviderConfig(BaseModel):
    """News/screener provider config. Independent of trading broker."""
    provider: Literal["alpaca"] | None = None  # Only Alpaca supports news/screener

class AppConfig(BaseSettings):
    """Updated main application config."""
    broker: BrokerConfig = Field(default_factory=AlpacaConfig)
    data: DataProviderConfig = Field(default_factory=DataProviderConfig)
    news: NewsProviderConfig = Field(default_factory=NewsProviderConfig)
    # When broker=webull and news.provider=alpaca, Alpaca keys must also be set
    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)  # For mixed-provider mode
    # ... rest unchanged
```

### 9.2 TOML Configuration

**Alpaca (default — backward compatible):**

```toml
[broker]
provider = "alpaca"
paper = true

[broker.alpaca]
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"
```

**Webull (with Alpaca news/screener):**

```toml
[broker]
provider = "webull"
paper = true

[broker.webull]
app_key_env = "WEBULL_APP_KEY"
app_secret_env = "WEBULL_APP_SECRET"
account_id_env = "WEBULL_ACCOUNT_ID"
region = "us"

# Use Alpaca for news/screener (Webull SDK has no news API)
[news]
provider = "alpaca"

# Alpaca credentials needed for news/screener even when trading via Webull
[alpaca]
api_key_env = "ALPACA_API_KEY"
api_secret_env = "ALPACA_API_SECRET"
```

### 9.3 Environment Variables

| Variable | Broker | Description |
|----------|--------|-------------|
| `ALPACA_API_KEY` | Alpaca | API key |
| `ALPACA_API_SECRET` | Alpaca | API secret |
| `WEBULL_APP_KEY` | Webull | App key from developer portal |
| `WEBULL_APP_SECRET` | Webull | App secret from developer portal |
| `WEBULL_ACCOUNT_ID` | Webull | Account ID (optional — auto-discovered if omitted) |

### 9.4 V2 TOML Update

The `ai_investor_v2.toml` `[system]` section gains a broker reference:

```toml
[system]
mode = "paper"
broker = "webull"   # NEW — which broker to use
# ... rest unchanged
```

Or the system reads from the global `[broker]` config section.

---

## 10. Migration Plan for Existing Code

### 10.1 Changes by Component

| Component | File(s) | Change Description |
|-----------|---------|-------------------|
| **Broker protocols** | `broker/protocols.py` (NEW) | Define `BrokerProvider`, `MarketDataProvider`, `ScreenerProvider`, `NewsProvider` protocols |
| **Broker models** | `broker/models.py` (NEW) | Define `AccountInfo`, `OrderRequest`, `OrderResult`, `BrokerPosition`, `MarketClock` |
| **Broker factory** | `broker/factory.py` (NEW) | `create_broker(config) → BrokerProvider`, `create_data_provider(config) → MarketDataProvider` |
| **Alpaca broker adapter** | `broker/alpaca/broker.py` (NEW) | Extract trading logic from `PaperTradingRunner` + `AIInvestor` into `AlpacaBroker` class |
| **Alpaca data adapter** | `broker/alpaca/data.py` (NEW) | Wrap existing `AlpacaDataFetcher`, implement `MarketDataProvider` protocol |
| **Alpaca screener** | `broker/alpaca/screener.py` (NEW) | Move from `data/screener.py`, implement `ScreenerProvider` |
| **Webull broker adapter** | `broker/webull/broker.py` (NEW) | Implement `BrokerProvider` using webull SDK |
| **Webull data adapter** | `broker/webull/data.py` (NEW) | Implement `MarketDataProvider` using webull SDK |
| **Webull instrument cache** | `broker/webull/instrument_cache.py` (NEW) | Symbol-to-instrument_id resolution — in-memory with SQLite persistence |
| **Config models** | `models/config.py` | Add `BrokerConfig`, `WebullConfig`, update `AppConfig` |
| **PaperTradingRunner** | `paper_trading.py` | Replace direct Alpaca calls → use `BrokerProvider` |
| **AIInvestor CLI** | `cli/ai.py` | Replace lazy Alpaca clients → use factory |
| **V2 Orchestrator** | `orchestrator/v2_engine.py` | Type `_trading_client` as `BrokerProvider`, `_data_client` as `MarketDataProvider` |
| **BacktestEngine** | `backtest/engine.py` | Type-hint `MarketDataProvider` instead of `AlpacaDataFetcher` |
| **Remove `data/` module** | `data/alpaca.py`, `data/screener.py`, `data/__init__.py` | Delete entirely, update all imports to use `broker/` |

### 10.2 What Does NOT Change

- All strategy classes (`BaseStrategy`, `SimpleDCAStrategy`, etc.)
- All agent classes (they use `AgentContext`, not broker types)
- `StrategyContext` dataclass
- `Signal`, `Trade`, `Position`, `PortfolioState` models
- `SimulatedPortfolio` (backtest)
- `OrchestratorEngine` (v1)
- `Blackboard`
- LLM layer
- All existing tests against strategies/agents

### 10.3 Migration Notes

- `AlpacaConfig` remains valid and becomes the default
- `data/alpaca.py`, `data/screener.py`, and `data/__init__.py` are **deleted** — all imports updated to `broker.alpaca.*`
- Existing TOML configs without `[broker]` section default to Alpaca
- Environment variable names don't change
- All internal references to `AlpacaDataFetcher` are replaced with `MarketDataProvider` protocol

---

## 11. Key Differences & Edge Cases

### 11.1 Alpaca vs Webull — Adapter Responsibilities

| Capability | Alpaca Adapter | Webull Adapter |
|-----------|----------------|----------------|
| **Symbol handling** | Pass-through (`"AAPL"`) | Resolve to `instrument_id` via cache |
| **Account ID** | Implicit (from API key) | Explicit (from config or auto-discovered) |
| **Order quantity** | `qty` parameter | `qty` + `instrument_id` + `order_entrust_type=QTY` |
| **Fractional/notional** | `notional` parameter | `order_entrust_type=AMOUNT` |
| **Paper trading** | `paper=True` on `TradingClient` | `add_endpoint()` to UAT: `us-openapi-alb.uat.webullbroker.com` |
| **Market clock** | `get_clock()` API | `get_trade_calendar(market, start, end)` + system time comparison |
| **Crypto detection** | Symbol contains `/` | `Category.CRYPTO` |
| **Extended hours** | `extended_hours=True` on order | `extended_hours_trading=True` on order |
| **Bar pagination** | Up to 10000 bars | Max 1200; adapter auto-paginates |
| **Position list** | `get_all_positions()` (all at once) | Paginated (`page_size=100`), adapter collects all |
| **Order list** | Filter by `status` | Separate endpoints: `list_today_orders`, `list_open_orders` |
| **Screener** | Yes (`ScreenerClient`) | Not available — returns empty / raises |
| **News** | Yes (`NewsClient`) | Not available — returns empty / raises |

### 11.2 Edge Cases to Handle

1. **Webull instrument_id not found**: If `get_instrument()` returns no match for a symbol, raise a clear `BrokerError` with guidance.

2. **Webull pagination exhaustion**: If position/order lists are extremely long, implement max-page safety limits.

3. **Webull rate limiting**: The SDK supports `add_custom_headers()` for rate limit categories. The adapter should implement exponential backoff on 429 responses.

4. **Order type support mismatch**: If a user requests `trailing_stop` and the broker doesn't support it (unlikely for both), raise `UnsupportedOrderTypeError`.

5. **Market clock for Webull**: Webull doesn't have a real-time clock endpoint like Alpaca. Implement via `get_trade_calendar()` + system time comparison. Always use the brokerage API — never hardcode market hours.

6. **Currency normalization**: Webull returns multi-currency balances. For US region, sum only USD values. The adapter handles this internally.

---

## 12. Testing Strategy

### 12.1 Test Layers

```
┌──────────────────────────────────────────────────────────┐
│                    Integration Tests                      │
│    (Real SDK calls with paper/sandbox credentials)        │
│    tests/integration/broker/test_alpaca_live.py           │
│    tests/integration/broker/test_webull_live.py           │
└──────────────────────────────────────────────────────────┘
                          │
┌──────────────────────────────────────────────────────────┐
│                    Adapter Unit Tests                      │
│    (Mock SDK clients, verify protocol compliance)         │
│    tests/unit/broker/test_alpaca_broker.py                │
│    tests/unit/broker/test_webull_broker.py                │
│    tests/unit/broker/test_alpaca_data.py                  │
│    tests/unit/broker/test_webull_data.py                  │
│    tests/unit/broker/test_factory.py                      │
└──────────────────────────────────────────────────────────┘
                          │
┌──────────────────────────────────────────────────────────┐
│                    Protocol Conformance Tests              │
│    (Verify both adapters satisfy the protocol contract)   │
│    tests/unit/broker/test_protocol_conformance.py         │
└──────────────────────────────────────────────────────────┘
                          │
┌──────────────────────────────────────────────────────────┐
│                  Existing Tests (Unchanged)                │
│    All strategy, agent, backtest tests continue to pass   │
│    using mock/stub implementations of the protocols       │
└──────────────────────────────────────────────────────────┘
```

### 12.2 Mock Broker for Tests

A `MockBroker(BrokerProvider)` is provided in test fixtures that simulates order execution in memory. This replaces the scattered Alpaca mocks currently used in tests and ensures all tests are broker-agnostic.

### 12.3 Protocol Conformance Tests

A shared test suite that both `AlpacaBroker` and `WebullBroker` run against, verifying:
- `get_account()` returns valid `AccountInfo`
- `submit_order()` → `get_order()` round-trip
- `get_positions()` returns `list[BrokerPosition]` with correct types
- `cancel_order()` on open order succeeds
- `list_orders()` filtering works
- All Decimal fields are actually Decimal (not float)

---

## 13. Implementation Phases

### Phase 1: Broker Abstraction (No new broker yet)

**Goal:** Introduce protocols and refactor Alpaca usage behind them. Zero behavioral change.

| Task | Files | Effort |
|------|-------|--------|
| Define `BrokerProvider`, `MarketDataProvider` protocols | `broker/protocols.py` | S |
| Define broker-agnostic models | `broker/models.py` | S |
| Implement `AlpacaBroker` adapter | `broker/alpaca/broker.py` | M |
| Implement `AlpacaMarketData` adapter | `broker/alpaca/data.py` | M |
| Move screener/news to `broker/alpaca/` | `broker/alpaca/screener.py`, `news.py` | S |
| Implement `BrokerFactory` (with mixed-provider support) | `broker/factory.py` | M |
| Update `AppConfig` with `BrokerConfig`, `DataProviderConfig`, `NewsProviderConfig` | `models/config.py` | S |
| Refactor `PaperTradingRunner` to use `BrokerProvider` | `paper_trading.py` | M |
| Refactor `AIInvestor` CLI to use factory | `cli/ai.py` | L |
| Refactor `V2AutonomousOrchestrator` to use protocols | `orchestrator/v2_engine.py` | M |
| Refactor `BacktestEngine` to use `MarketDataProvider` | `backtest/engine.py` | S |
| Delete `data/` module, update all imports | `data/`, all consumers | M |
| Write protocol conformance tests | `tests/unit/broker/` | M |
| Write Alpaca adapter unit tests | `tests/unit/broker/` | M |
| Verify all existing tests still pass | — | S |

**Validation:** `pytest` passes, `ruff check src/` clean, all existing behavior unchanged.

### Phase 2: Webull Adapter

**Goal:** Implement Webull broker and data adapters. Users can switch brokers.

| Task | Files | Effort |
|------|-------|--------|
| Add Webull SDK pip packages as dependencies | `pyproject.toml` | S |
| Implement `InstrumentCache` (in-memory + SQLite) | `broker/webull/instrument_cache.py` | M |
| Implement `WebullBroker` adapter | `broker/webull/broker.py` | L |
| Implement `WebullMarketData` adapter | `broker/webull/data.py` | L |
| Add `WebullConfig` model | `models/config.py` | S |
| Update factory for Webull | `broker/factory.py` | S |
| Write Webull adapter unit tests (mocked SDK) | `tests/unit/broker/` | M |
| Run protocol conformance tests against Webull adapter | `tests/unit/broker/` | S |
| Write integration tests (sandbox credentials) | `tests/integration/broker/` | M |
| Update CLI help text / status display for broker name | `cli/ai.py` | S |
| Documentation & QUICKSTART update | `docs/` | S |

**Validation:** Protocol conformance tests pass for both adapters. `bvr ai status` works with both `--broker alpaca` and `--broker webull`.

### Phase 3: Polish & Advanced Features (Future)

- Webull MQTT streaming for real-time quotes
- Webull gRPC trade events for order status streaming
- Combo orders (OTO/OCO/OTOCO)
- Multi-market support (HK, JP)
- Options trading
- Short selling

---

## 14. Resolved Decisions

All open questions have been resolved. Summary of decisions:

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | **Paper trading** | Webull provides a UAT sandbox at `us-openapi-alb.uat.webullbroker.com`. Same APIs for paper and live. Use `api_client.add_endpoint()` to switch. | Confirmed from Webull developer docs. Identical model to Alpaca. |
| 2 | **SDK packaging** | Standard pip dependency in `pyproject.toml`: `webull-python-sdk-core`, `webull-python-sdk-trade`, `webull-python-sdk-mdata`. The vendored `openapi-python-sdk/` is reference only. | Consistent with how `alpaca-py` is managed. |
| 3 | **Screener/News** | Mixed-provider mode. Trading is single-broker, but data/news/screener can come from Alpaca even when trading via Webull. | Webull SDK lacks screener/news. Alpaca keys required for these features when using Webull. |
| 4 | **Market clock** | Always from the brokerage API. Alpaca: `get_clock()`. Webull: `get_trade_calendar()` + system time. Never hardcoded. | Ensures correctness across holidays and schedule changes. |
| 5 | **Instrument cache** | In-memory with SQLite persistence. Survives restarts, fast lookups, minimal API calls. | Avoids repeated `get_instrument()` calls on every startup. |
| 6 | **`data/` module** | Remove immediately. Update all imports to `broker/`. No deprecation wrappers. | Single user (author), no external consumers to support. |

---

*This spec is finalized and approved for implementation. Work will follow the phased plan in Section 13.*
