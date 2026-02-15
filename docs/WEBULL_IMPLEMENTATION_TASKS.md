# Webull Integration — Implementation Tasks

**Spec:** [WEBULL_INTEGRATION.md](WEBULL_INTEGRATION.md)  
**Created:** February 15, 2026  
**Branch:** `ai_investor_redo`  
**Status:** In Progress

---

## Summary

| Phase | Tasks | Status |
|-------|-------|--------|
| **0 — Pre-work** | 4 | ⬜ Not started |
| **1 — Broker Abstraction Layer** | 10 | ⬜ Not started |
| **2 — Alpaca Adapter + Migration** | 9 | ⬜ Not started |
| **3 — Webull Adapter** | 8 | ⬜ Not started |
| **4 — Consumer Migration** | 7 | ⬜ Not started |
| **5 — Cleanup & Validation** | 5 | ⬜ Not started |
| **Total** | **43** | |

### Critical Rules (from project standards)
- **Decimal for ALL money** — never `float` for prices, quantities, values
- **Type hints everywhere** — every parameter and return type
- **Pydantic for domain objects** — no raw dicts for data models
- **Tests with every change** — this is a real-time financial system; bugs have real-world impact
- **Target ≥80% code coverage** on all new code

---

## Phase 0 — Pre-work & Infrastructure

> Set up coverage tooling and validate baseline before making any changes.

| ID | Task | Files | Size | Status | Depends On |
|----|------|-------|------|--------|------------|
| 0.1 | **Add pytest-cov and configure coverage** | `pyproject.toml` | S | ⬜ | — |
| | Add `pytest-cov` to dev dependencies. Add `[tool.coverage]` config targeting `src/beavr/`. Set `--cov` in `addopts`. Establish baseline coverage number. | | | | |
| 0.2 | **Run existing test suite — establish green baseline** | — | S | ⬜ | 0.1 |
| | `pytest tests/unit/ -v` must pass. `ruff check src/` must be clean. Record current coverage %. | | | | |
| 0.3 | **Add Webull SDK dependencies to pyproject.toml** | `pyproject.toml` | S | ⬜ | — |
| | Add optional `[webull]` extras group: `webull-python-sdk-core`, `webull-python-sdk-trade`, `webull-python-sdk-mdata`. Keep them optional so Alpaca-only users don't need them. | | | | |
| 0.4 | **Create `broker/` package skeleton** | `src/beavr/broker/__init__.py`, `broker/alpaca/__init__.py`, `broker/webull/__init__.py`, `tests/unit/broker/__init__.py` | S | ⬜ | — |
| | Empty `__init__.py` files only. Verify `import beavr.broker` works. | | | | |

### Validation Gate
```bash
pytest tests/unit/ -v          # All 218+ tests pass
ruff check src/                 # Clean
pytest --cov=beavr --cov-report=term-missing  # Baseline coverage recorded
```

---

## Phase 1 — Broker Abstraction Layer (New Code, No Migration)

> Define protocols and broker-agnostic models. This is the foundational contract layer.
> **All code in this phase is NEW — no existing code modified.**

| ID | Task | Files | Size | Status | Depends On |
|----|------|-------|------|--------|------------|
| 1.1 | **Define broker-agnostic domain models** | `src/beavr/broker/models.py` | M | ⬜ | 0.4 |
| | Implement all Pydantic models per spec §6.1: | | | | |
| | • `AccountInfo` — equity, cash, buying_power, currency (all `Decimal`) | | | | |
| | • `BrokerPosition` — symbol, qty, market_value, avg_cost, unrealized_pl, side | | | | |
| | • `OrderRequest` — symbol, side, order_type, tif, quantity?, notional?, limit_price?, stop_price?, client_order_id? | | | | |
| | • `OrderResult` — order_id, client_order_id, symbol, side, order_type, status, filled_qty, filled_avg_price, submitted_at, filled_at | | | | |
| | • `MarketClock` — is_open, next_open, next_close | | | | |
| | • `BrokerError` exception class with error_code, message, broker_name | | | | |
| | **Acceptance:** All fields use `Decimal` for money. Models are `frozen=True`. Full type hints. | | | | |
| 1.2 | **Write unit tests for broker models** | `tests/unit/broker/test_models.py` | M | ⬜ | 1.1 |
| | Test creation, immutability, Decimal enforcement, validation errors on bad input, serialization round-trips, factory helpers. ≥15 tests. | | | | |
| 1.3 | **Define `BrokerProvider` protocol** | `src/beavr/broker/protocols.py` | M | ⬜ | 1.1 |
| | Per spec §6.2 — `Protocol` class (structural typing, NOT ABC): | | | | |
| | • `get_account() → AccountInfo` | | | | |
| | • `get_positions() → list[BrokerPosition]` | | | | |
| | • `submit_order(order: OrderRequest) → OrderResult` | | | | |
| | • `cancel_order(order_id: str) → OrderResult` | | | | |
| | • `get_order(order_id: str) → OrderResult` | | | | |
| | • `list_orders(status: str | None, limit: int) → list[OrderResult]` | | | | |
| | • `is_market_open() → bool` | | | | |
| | • `get_clock() → MarketClock` | | | | |
| | • `broker_name: str` (property) | | | | |
| | • `supports_fractional: bool` (property) | | | | |
| 1.4 | **Define `MarketDataProvider` protocol** | `src/beavr/broker/protocols.py` | M | ⬜ | 1.1 |
| | Per spec §7.1: | | | | |
| | • `get_bars(symbol, start, end, timeframe) → pd.DataFrame` | | | | |
| | • `get_bars_multi(symbols, start, end, timeframe) → dict[str, pd.DataFrame]` | | | | |
| | • `get_snapshot(symbol) → dict` | | | | |
| | • `provider_name: str` (property) | | | | |
| | Timeframe: `Literal["1min","5min","15min","30min","1hour","1day","1week"]` | | | | |
| 1.5 | **Define `ScreenerProvider` and `NewsProvider` protocols** | `src/beavr/broker/protocols.py` | S | ⬜ | — |
| | Per spec §7.3: | | | | |
| | • `ScreenerProvider`: `get_market_movers()`, `get_most_actives()` | | | | |
| | • `NewsProvider`: `get_news(symbols, limit)` | | | | |
| | These are optional capabilities — not all brokers implement them. | | | | |
| 1.6 | **Implement `MockBroker` test double** | `tests/unit/broker/conftest.py` | M | ⬜ | 1.3, 1.4 |
| | In-memory broker mock implementing `BrokerProvider` + `MarketDataProvider`. Simulates order fills, tracks positions, returns canned bars. This replaces scattered Alpaca mocks. | | | | |
| | **Critical:** Must enforce Decimal types, reject float inputs, validate all order fields. | | | | |
| 1.7 | **Write protocol conformance test suite** | `tests/unit/broker/test_protocol_conformance.py` | L | ⬜ | 1.6 |
| | Shared parametrized test suite that ANY adapter must pass: | | | | |
| | • `get_account()` returns valid `AccountInfo` with Decimal fields | | | | |
| | • `submit_order()` → `get_order()` round-trip: order_id matches, status correct | | | | |
| | • `submit_order()` with invalid symbol → raises `BrokerError` | | | | |
| | • `get_positions()` returns `list[BrokerPosition]`, Decimal qty | | | | |
| | • `cancel_order()` on open order → status is cancelled | | | | |
| | • `cancel_order()` on filled order → raises `BrokerError` | | | | |
| | • `list_orders()` with status filter works | | | | |
| | • `is_market_open()` returns `bool` | | | | |
| | • `get_bars()` returns DataFrame with correct columns (open,high,low,close,volume), DatetimeIndex, Decimal values | | | | |
| | • `get_bars_multi()` returns dict keyed by symbol | | | | |
| | • All Decimal fields are actually `Decimal`, never `float` | | | | |
| | **≥20 test cases.** Parametrized to run against MockBroker initially, then Alpaca + Webull adapters. | | | | |
| 1.8 | **Update `models/config.py` — add broker config models** | `src/beavr/models/config.py` | M | ⬜ | — |
| | Per spec §9.1: | | | | |
| | • Keep existing `AlpacaConfig` unchanged (backward compat) | | | | |
| | • Add `WebullConfig(BaseModel)` — app_key_env, app_secret_env, account_id_env, region | | | | |
| | • Add `BrokerProviderConfig(BaseModel)` — provider ("alpaca"\|"webull"), paper, alpaca?, webull? | | | | |
| | • Add `DataProviderConfig(BaseModel)` — provider (optional, defaults to broker) | | | | |
| | • Add `NewsProviderConfig(BaseModel)` — provider (optional, "alpaca" only) | | | | |
| | • Update `AppConfig` to include optional `broker: BrokerProviderConfig` field | | | | |
| | **Keep `AppConfig.alpaca` field for backward compat — existing TOML configs still work.** | | | | |
| 1.9 | **Write unit tests for new config models** | `tests/unit/test_config.py` | M | ⬜ | 1.8 |
| | Test `WebullConfig`, `BrokerProviderConfig`, `DataProviderConfig`, `NewsProviderConfig`. Test TOML loading with broker section. Test backward compat: config without `[broker]` defaults to Alpaca. ≥10 new tests. | | | | |
| 1.10 | **Implement `BrokerFactory`** | `src/beavr/broker/factory.py` | M | ⬜ | 1.3, 1.4, 1.8 |
| | Per spec §5.2: | | | | |
| | • `create_broker(config) → BrokerProvider` | | | | |
| | • `create_data_provider(config) → MarketDataProvider` | | | | |
| | • `create_screener(config) → ScreenerProvider | None` | | | | |
| | • `create_news_provider(config) → NewsProvider | None` | | | | |
| | Support mixed-provider mode: trading from one broker, data/news from another. | | | | |
| | **Initially only Alpaca is wired up. Webull raises `NotImplementedError` until Phase 3.** | | | | |

### Validation Gate
```bash
pytest tests/unit/broker/ -v   # All protocol + model tests pass
ruff check src/beavr/broker/   # Clean
pytest --cov=beavr.broker --cov-report=term-missing  # ≥90% coverage on broker/
```

---

## Phase 2 — Alpaca Adapter (Wrap Existing Code Behind Protocols)

> Extract Alpaca-specific logic into adapter classes that implement the protocols.
> **Goal: Zero behavioral change. Just reorganization.**

| ID | Task | Files | Size | Status | Depends On |
|----|------|-------|------|--------|------------|
| 2.1 | **Implement `AlpacaBroker` adapter** | `src/beavr/broker/alpaca/broker.py` | L | ⬜ | 1.3 |
| | Implements `BrokerProvider` protocol. Extracts trading logic from `PaperTradingRunner`, `AIInvestor`, and `V2AutonomousOrchestrator`: | | | | |
| | • `__init__(api_key, api_secret, paper)` — creates `TradingClient` | | | | |
| | • `get_account()` — calls `TradingClient.get_account()`, maps to `AccountInfo` | | | | |
| | • `get_positions()` — calls `get_all_positions()`, maps to `list[BrokerPosition]` | | | | |
| | • `submit_order(OrderRequest)` — builds `MarketOrderRequest`/`LimitOrderRequest`, handles fractional→notional fallback, maps to `OrderResult` | | | | |
| | • `cancel_order()`, `get_order()`, `list_orders()` — wrapper around `TradingClient` methods | | | | |
| | • `is_market_open()` / `get_clock()` — wrapper around `TradingClient.get_clock()` | | | | |
| | **Critical: Consolidate the 3 separate order submission code paths into ONE.** This is a major correctness improvement — currently order logic is duplicated with inconsistent error handling. | | | | |
| 2.2 | **Write `AlpacaBroker` unit tests** | `tests/unit/broker/test_alpaca_broker.py` | L | ⬜ | 2.1 |
| | Mock `TradingClient` with `unittest.mock.patch`. Test: | | | | |
| | • `get_account()` maps all Alpaca fields to `AccountInfo` correctly (Decimal!) | | | | |
| | • `get_positions()` maps all fields, handles empty positions | | | | |
| | • `submit_order()` with qty → `MarketOrderRequest` with `qty` | | | | |
| | • `submit_order()` with notional → `MarketOrderRequest` with `notional` | | | | |
| | • `submit_order()` fractional fallback: shares → notional when fractional not available | | | | |
| | • `submit_order()` error handling: invalid symbol, insufficient funds, market closed | | | | |
| | • `cancel_order()` success + already-filled error | | | | |
| | • `get_clock()` mapping, `is_market_open()` | | | | |
| | • `broker_name` returns `"alpaca"` | | | | |
| | **≥20 tests. Every error path tested.** | | | | |
| 2.3 | **Run protocol conformance tests against `AlpacaBroker`** | `tests/unit/broker/test_protocol_conformance.py` | S | ⬜ | 2.1, 1.7 |
| | Add `AlpacaBroker` (with mocked SDK) to the conformance test parametrization. All conformance tests must pass. | | | | |
| 2.4 | **Implement `AlpacaMarketData` adapter** | `src/beavr/broker/alpaca/data.py` | M | ⬜ | 1.4 |
| | Wraps existing `AlpacaDataFetcher` logic, implements `MarketDataProvider`: | | | | |
| | • Move core fetching logic from `data/alpaca.py` | | | | |
| | • `get_bars(symbol, start, end, timeframe)` → calls existing fetch logic | | | | |
| | • `get_bars_multi(symbols, start, end, timeframe)` → wraps existing multi-bar logic | | | | |
| | • `get_snapshot(symbol)` → new, calls Alpaca snapshot API | | | | |
| | • Timeframe mapping: protocol strings → `alpaca.data.timeframe.TimeFrame` | | | | |
| | • Preserve caching behavior (BarCache integration) | | | | |
| 2.5 | **Write `AlpacaMarketData` unit tests** | `tests/unit/broker/test_alpaca_data.py` | M | ⬜ | 2.4 |
| | Adapt existing `test_alpaca.py` mock patterns. Test: | | | | |
| | • `get_bars()` returns correct DataFrame format (DatetimeIndex, Decimal values) | | | | |
| | • `get_bars_multi()` returns dict keyed by symbol | | | | |
| | • Timeframe mapping: all 7 protocol timeframes map correctly | | | | |
| | • Caching: second call serves from cache, not API | | | | |
| | • Crypto detection: symbols with `/` route to `CryptoHistoricalDataClient` | | | | |
| | • API error handling: maps to `BrokerError` with clear message | | | | |
| | **≥15 tests.** | | | | |
| 2.6 | **Move `MarketScreener` → `AlpacaScreener`** | `src/beavr/broker/alpaca/screener.py` | S | ⬜ | 1.5 |
| | Move from `data/screener.py` → `broker/alpaca/screener.py`. Implement `ScreenerProvider` protocol. Keep same logic, just new location + protocol compliance. | | | | |
| 2.7 | **Move `NewsScanner` → `AlpacaNews`** | `src/beavr/broker/alpaca/news.py` | S | ⬜ | 1.5 |
| | Move from `data/screener.py` → `broker/alpaca/news.py`. Implement `NewsProvider` protocol. Keep same logic, just new location + protocol compliance. | | | | |
| 2.8 | **Wire factory for Alpaca** | `src/beavr/broker/factory.py` | S | ⬜ | 2.1, 2.4, 2.6, 2.7 |
| | Update `BrokerFactory` to instantiate `AlpacaBroker`, `AlpacaMarketData`, `AlpacaScreener`, `AlpacaNews` when `provider="alpaca"`. | | | | |
| 2.9 | **Write factory unit tests** | `tests/unit/broker/test_factory.py` | M | ⬜ | 2.8 |
| | Test: | | | | |
| | • `create_broker("alpaca", ...)` returns `AlpacaBroker` instance | | | | |
| | • `create_data_provider("alpaca", ...)` returns `AlpacaMarketData` instance | | | | |
| | • `create_broker("webull", ...)` raises `NotImplementedError` (until Phase 3) | | | | |
| | • Default config (no `[broker]` section) → Alpaca | | | | |
| | • Mixed-provider: broker=alpaca, news=alpaca → both created | | | | |
| | **≥8 tests.** | | | | |

### Validation Gate
```bash
pytest tests/unit/broker/ -v   # All adapter + conformance tests pass
ruff check src/beavr/broker/   # Clean
pytest --cov=beavr.broker --cov-report=term-missing  # ≥85% on broker/
```

---

## Phase 3 — Webull Adapter

> Implement Webull broker and data adapters using the Webull SDK.

| ID | Task | Files | Size | Status | Depends On |
|----|------|-------|------|--------|------------|
| 3.1 | **Implement `InstrumentCache`** | `src/beavr/broker/webull/instrument_cache.py` | M | ⬜ | 0.3 |
| | Per spec §8.2 — symbol↔instrument_id resolution: | | | | |
| | • In-memory `dict[str, str]` cache (symbol → instrument_id) | | | | |
| | • SQLite persistence: `instrument_cache` table (symbol, instrument_id, category, exchange, updated_at) | | | | |
| | • `resolve(symbol, category) → str` — check memory → check SQLite → call API → cache both | | | | |
| | • `resolve_batch(symbols, category) → dict[str, str]` — batch resolution for efficiency | | | | |
| | • Auto-detect category from symbol pattern (per spec §8.3): `/` → CRYPTO, default → US_STOCK | | | | |
| | • TTL: 24 hours for cached entries; force-refresh option | | | | |
| | **Critical: This is the biggest difference between Alpaca and Webull. Must be rock-solid.** | | | | |
| 3.2 | **Write `InstrumentCache` unit tests** | `tests/unit/broker/test_instrument_cache.py` | L | ⬜ | 3.1 |
| | Mock the Webull `api.instrument.get_instrument()` call. Test: | | | | |
| | • Cache miss → API call → cache populated (memory + SQLite) | | | | |
| | • Cache hit (memory) → no API call | | | | |
| | • Cache hit (SQLite, memory cleared) → restored from DB, no API call | | | | |
| | • Batch resolution: mix of cached + uncached → only uncached symbols hit API | | | | |
| | • TTL expiry → re-fetches from API | | | | |
| | • Unknown symbol → raises `BrokerError` with clear message | | | | |
| | • Category auto-detection: `BTC/USD` → CRYPTO, `AAPL` → US_STOCK | | | | |
| | • Thread safety (if applicable) | | | | |
| | **≥15 tests.** | | | | |
| 3.3 | **Implement `WebullBroker` adapter** | `src/beavr/broker/webull/broker.py` | XL | ⬜ | 1.3, 3.1 |
| | Implements `BrokerProvider` protocol using Webull SDK: | | | | |
| | • `__init__(app_key, app_secret, account_id, region, paper)` — creates `ApiClient`, sets endpoint for paper/live | | | | |
| | • Paper trading: `api_client.add_endpoint("us", "us-openapi-alb.uat.webullbroker.com")` | | | | |
| | • `get_account()` — calls `api.account.get_account_balance()`, maps to `AccountInfo` (USD only, multi-currency normalization) | | | | |
| | • `get_positions()` — calls `api.account.get_account_position()`, **auto-paginates** (max 100/page), maps to `list[BrokerPosition]` | | | | |
| | • `submit_order()` — resolves symbol→instrument_id via cache, builds order with `place_order()`, handles `QTY` vs `AMOUNT` entrust type | | | | |
| | • `cancel_order()` — calls `api.order.cancel_order()` | | | | |
| | • `get_order()` — calls `api.order.query_order_detail()`, maps to `OrderResult` | | | | |
| | • `list_orders()` — combines `list_today_orders()` + `list_open_orders()`, auto-paginates | | | | |
| | • `is_market_open()` / `get_clock()` — calls `api.trade_calendar.get_trade_calendar()` + system time comparison | | | | |
| | • Account ID auto-discovery via `api.account.get_app_subscriptions()` when not provided | | | | |
| | • Rate limiting: exponential backoff on 429 responses | | | | |
| | • Max-page safety limits on pagination (prevent infinite loops) | | | | |
| | **Critical edge cases:** | | | | |
| | • Instrument not found → clear `BrokerError` | | | | |
| | • Order rejected → map Webull error to `BrokerError` with actionable message | | | | |
| | • Rate limited → retry with backoff, then raise | | | | |
| 3.4 | **Write `WebullBroker` unit tests** | `tests/unit/broker/test_webull_broker.py` | XL | ⬜ | 3.3 |
| | Mock `ApiClient` and all Webull SDK calls. Test: | | | | |
| | • `get_account()` maps Webull balance response → `AccountInfo` (Decimal!) | | | | |
| | • `get_account()` multi-currency → sums USD only | | | | |
| | • `get_positions()` single page, multi-page pagination, empty positions | | | | |
| | • `submit_order()` qty-based → `OrderEntrustType.QTY` | | | | |
| | • `submit_order()` notional-based → `OrderEntrustType.AMOUNT` | | | | |
| | • `submit_order()` symbol resolution through instrument cache | | | | |
| | • `submit_order()` instrument not found → `BrokerError` | | | | |
| | • `cancel_order()` success + error cases | | | | |
| | • `get_order()` maps all fields correctly | | | | |
| | • `list_orders()` pagination + status filter | | | | |
| | • `get_clock()` with `get_trade_calendar()` — market open, closed, holiday | | | | |
| | • Paper mode → correct endpoint set | | | | |
| | • Live mode → default endpoint | | | | |
| | • Account ID auto-discovery from subscriptions | | | | |
| | • Rate limit retry (mock 429 then success) | | | | |
| | **≥25 tests. Every error path tested.** | | | | |
| 3.5 | **Run protocol conformance tests against `WebullBroker`** | `tests/unit/broker/test_protocol_conformance.py` | S | ⬜ | 3.3, 1.7 |
| | Add `WebullBroker` (with mocked SDK) to conformance parametrization. All tests must pass. | | | | |
| 3.6 | **Implement `WebullMarketData` adapter** | `src/beavr/broker/webull/data.py` | L | ⬜ | 1.4, 3.1 |
| | Implements `MarketDataProvider` using Webull SDK: | | | | |
| | • `get_bars(symbol, start, end, timeframe)` — calls `api.market_data.get_history_bar()`, **auto-paginates** (max 1200 bars), normalizes to DataFrame | | | | |
| | • `get_bars_multi(symbols, start, end, timeframe)` — calls `api.market_data.get_batch_history_bar()` or iterates | | | | |
| | • `get_snapshot(symbol)` — calls `api.market_data.get_snapshot()` | | | | |
| | • Timeframe mapping: protocol strings → `Timespan` enum (`"1day"` → `Timespan.D`, etc.) | | | | |
| | • Category auto-detection from symbol | | | | |
| | • DataFrame normalization: `DatetimeIndex` (UTC), columns `[open, high, low, close, volume]`, all Decimal, sorted ascending | | | | |
| | **Critical: Bar pagination for large date ranges. Webull max 1200 bars vs Alpaca's 10000.** | | | | |
| 3.7 | **Write `WebullMarketData` unit tests** | `tests/unit/broker/test_webull_data.py` | L | ⬜ | 3.6 |
| | Mock Webull market data API. Test: | | | | |
| | • `get_bars()` single request (≤1200 bars) → correct DataFrame | | | | |
| | • `get_bars()` pagination (>1200 bars) → multiple requests concatenated | | | | |
| | • `get_bars_multi()` returns dict keyed by symbol | | | | |
| | • `get_snapshot()` returns latest data | | | | |
| | • Timeframe mapping: all 7 protocol timeframes map to correct `Timespan` | | | | |
| | • Category detection: crypto, stock, ETF | | | | |
| | • DataFrame format: correct index type, column names, Decimal values, UTC, sorted | | | | |
| | • API error → `BrokerError` | | | | |
| | **≥15 tests.** | | | | |
| 3.8 | **Wire factory for Webull** | `src/beavr/broker/factory.py` | S | ⬜ | 3.3, 3.6 |
| | Update factory to instantiate `WebullBroker` and `WebullMarketData` when `provider="webull"`. Update factory tests. Support mixed-mode: broker=webull, news=alpaca. | | | | |

### Validation Gate
```bash
pytest tests/unit/broker/ -v   # All tests pass (Alpaca + Webull + conformance)
ruff check src/beavr/broker/   # Clean
pytest --cov=beavr.broker --cov-report=term-missing  # ≥85% on broker/
```

---

## Phase 4 — Consumer Migration

> Update all existing code that directly uses Alpaca SDK to use the broker protocols instead.
> **Goal: No behavioral change. Same functionality, broker-agnostic types.**

| ID | Task | Files | Size | Status | Depends On |
|----|------|-------|------|--------|------------|
| 4.1 | **Migrate `BacktestEngine`** | `src/beavr/backtest/engine.py`, `backtest/hf_engine.py` | S | ⬜ | 2.4 |
| | • Change type hint from `AlpacaDataFetcher` → `MarketDataProvider` | | | | |
| | • Update import: `from beavr.broker.protocols import MarketDataProvider` | | | | |
| | • No logic changes — `AlpacaMarketData` has same interface | | | | |
| | • Verify `test_backtest_engine.py` still passes (MockDataFetcher may need protocol compliance) | | | | |
| 4.2 | **Migrate `PaperTradingRunner`** | `src/beavr/paper_trading.py` | L | ⬜ | 2.1, 2.4 |
| | • Remove all direct Alpaca SDK imports | | | | |
| | • Use `BrokerFactory.create_broker()` + `create_data_provider()` instead of raw client creation | | | | |
| | • Replace `self.trading_client.submit_order(MarketOrderRequest(...))` with `self.broker.submit_order(OrderRequest(...))` | | | | |
| | • Replace `self.trading_client.get_account()` with `self.broker.get_account()` | | | | |
| | • Replace `self.trading_client.get_clock()` with `self.broker.get_clock()` | | | | |
| | **This is one of the highest-risk migrations — paper trading runner handles real money.** | | | | |
| 4.3 | **Migrate `AIInvestor` CLI** | `src/beavr/cli/ai.py` | L | ⬜ | 2.1, 2.4, 1.10 |
| | • Remove lazy Alpaca client properties (`trading`, `data`) | | | | |
| | • Replace with `broker: BrokerProvider` and `data_provider: MarketDataProvider` from factory | | | | |
| | • Replace `execute_buy()` / `execute_sell()` to use `self.broker.submit_order(OrderRequest(...))` | | | | |
| | • Replace `get_account()` to use `self.broker.get_account()` | | | | |
| | • Replace `_get_market_status()` to use `self.broker.get_clock()` | | | | |
| | • Replace `AlpacaDataFetcher` usage with `self.data_provider` | | | | |
| | **Second highest-risk migration — this is the primary user-facing entry point.** | | | | |
| 4.4 | **Migrate `V2AutonomousOrchestrator`** | `src/beavr/orchestrator/v2_engine.py` | M | ⬜ | 2.1, 2.4, 2.6, 2.7 |
| | • Replace `_trading_client: Any` with `_broker: BrokerProvider` | | | | |
| | • Replace `_data_client: Any` with `_data_provider: MarketDataProvider` | | | | |
| | • Update `set_trading_client()` → `set_providers()` accepting protocol types | | | | |
| | • Replace `MarketScreener` + `NewsScanner` construction with `ScreenerProvider` + `NewsProvider` from factory | | | | |
| | • Replace `CompanyNameCache` Alpaca get_asset call with a provider-agnostic method | | | | |
| | • Replace `submit_order(MarketOrderRequest(...))` calls with `broker.submit_order(OrderRequest(...))` | | | | |
| 4.5 | **Migrate `cli/backtest.py`** | `src/beavr/cli/backtest.py` | S | ⬜ | 2.4, 1.10 |
| | • Replace `AlpacaDataFetcher` import with factory call | | | | |
| | • Remove `_get_alpaca_credentials()` helper → use factory | | | | |
| 4.6 | **Delete `data/` module** | `src/beavr/data/alpaca.py`, `data/screener.py`, `data/__init__.py` | M | ⬜ | 4.1-4.5 |
| | • Delete the entire `data/` directory | | | | |
| | • Search for ALL remaining imports of `beavr.data` across the codebase and update | | | | |
| | • Update `models/__init__.py` if needed | | | | |
| | • **Verify no remaining references to `beavr.data` exist** | | | | |
| 4.7 | **Update `broker/__init__.py` exports** | `src/beavr/broker/__init__.py` | S | ⬜ | 4.6 |
| | Export all public APIs: `BrokerProvider`, `MarketDataProvider`, `ScreenerProvider`, `NewsProvider`, `AccountInfo`, `OrderRequest`, `OrderResult`, `BrokerPosition`, `MarketClock`, `BrokerFactory`. | | | | |

### Validation Gate
```bash
pytest tests/unit/ -v            # ALL existing 218+ tests pass
pytest tests/unit/broker/ -v     # All broker tests pass
ruff check src/                  # Clean (entire codebase)
grep -r "from beavr.data" src/   # Zero results — old module fully removed
grep -r "alpaca-py" src/beavr/ --include="*.py" | grep -v broker/alpaca/  # No Alpaca SDK outside broker/alpaca/
```

---

## Phase 5 — Cleanup, Coverage & Validation

> Final quality assurance pass. Ensure all tests pass, coverage meets target, documentation is updated.

| ID | Task | Files | Size | Status | Depends On |
|----|------|-------|------|--------|------------|
| 5.1 | **Update existing test mocks for broker-agnostic types** | `tests/unit/test_backtest_engine.py`, `tests/unit/test_alpaca.py`, `tests/unit/test_cli_ai_v2_commands.py` | M | ⬜ | 4.1-4.6 |
| | • Update `MockDataFetcher` in backtest tests to implement `MarketDataProvider` protocol | | | | |
| | • Update `test_alpaca.py` → move relevant tests to `tests/unit/broker/test_alpaca_data.py` or adapt | | | | |
| | • Update CLI test mocks to use `MockBroker` instead of Alpaca-specific fakes | | | | |
| 5.2 | **Write integration tests** | `tests/integration/broker/test_alpaca_live.py`, `tests/integration/broker/test_webull_live.py` | M | ⬜ | Phase 3, Phase 4 |
| | • Alpaca: real paper-trading API calls (gated by env vars + `@pytest.mark.slow`) | | | | |
| | • Webull: real sandbox API calls (gated by env vars + `@pytest.mark.slow`) | | | | |
| | • Run protocol conformance test suite against real APIs | | | | |
| 5.3 | **Full coverage audit** | — | M | ⬜ | 5.1 |
| | • Run `pytest --cov=beavr --cov-report=html` | | | | |
| | • Identify any file below 80% coverage | | | | |
| | • Write targeted tests for uncovered paths | | | | |
| | • **Goal: ≥80% overall, ≥85% on `broker/` module** | | | | |
| 5.4 | **Update documentation** | `docs/QUICKSTART.md`, `docs/CONFIGURATION.md`, `README.md` | S | ⬜ | Phase 4 |
| | • Add Webull setup instructions | | | | |
| | • Document `[broker]` TOML config | | | | |
| | • Document environment variables | | | | |
| | • Update architecture diagrams | | | | |
| 5.5 | **Final validation sweep** | — | S | ⬜ | 5.1-5.4 |
| | Full validation: | | | | |
| | • `pytest` — all tests pass | | | | |
| | • `ruff check src/` — no lint errors | | | | |
| | • `mypy src/beavr/broker/` — no type errors | | | | |
| | • `bvr --help` works | | | | |
| | • No `float` used for money anywhere in `broker/` | | | | |

### Final Validation Gate
```bash
pytest -v                                              # ALL tests pass
ruff check src/                                        # Clean
pytest --cov=beavr --cov-report=term-missing           # ≥80% overall
pytest --cov=beavr.broker --cov-report=term-missing    # ≥85% on broker/
grep -rn "float" src/beavr/broker/ --include="*.py" | grep -v "# noqa"  # Audit for float usage
```

---

## Dependency Graph

```
Phase 0 (Pre-work)
    │
    ├── 0.1 Coverage setup ──────────────────────────────────────────┐
    ├── 0.2 Green baseline ──────────────────────────────────────────┤
    ├── 0.3 Webull SDK deps ─────────────────────────────┐           │
    └── 0.4 Package skeleton ──┐                         │           │
                               │                         │           │
Phase 1 (Abstraction)          │                         │           │
    │                          │                         │           │
    ├── 1.1 Broker models ◄────┘                         │           │
    ├── 1.2 Model tests ◄──── 1.1                       │           │
    ├── 1.3 BrokerProvider ◄── 1.1                      │           │
    ├── 1.4 MarketDataProvider ◄── 1.1                  │           │
    ├── 1.5 Screener/News ─────────────────────────┐     │           │
    ├── 1.6 MockBroker ◄────── 1.3, 1.4            │     │           │
    ├── 1.7 Conformance tests ◄── 1.6              │     │           │
    ├── 1.8 Config models ─────────────────────┐    │     │           │
    ├── 1.9 Config tests ◄──── 1.8             │    │     │           │
    └── 1.10 Factory ◄──────── 1.3, 1.4, 1.8  │    │     │           │
                               │                │    │     │           │
Phase 2 (Alpaca Adapter)       │                │    │     │           │
    │                          │                │    │     │           │
    ├── 2.1 AlpacaBroker ◄──── 1.3             │    │     │           │
    ├── 2.2 Broker tests ◄──── 2.1             │    │     │           │
    ├── 2.3 Conformance ◄───── 2.1, 1.7        │    │     │           │
    ├── 2.4 AlpacaMarketData ◄── 1.4           │    │     │           │
    ├── 2.5 Data tests ◄────── 2.4             │    │     │           │
    ├── 2.6 AlpacaScreener ◄──────────────────────── 1.5  │           │
    ├── 2.7 AlpacaNews ◄──────────────────────────── 1.5  │           │
    ├── 2.8 Wire factory ◄──── 2.1,2.4,2.6,2.7│         │           │
    └── 2.9 Factory tests ◄─── 2.8            │         │           │
                               │                │         │           │
Phase 3 (Webull Adapter)       │                │         │           │
    │                          │                │         │           │
    ├── 3.1 InstrumentCache ◄──────────────────────────── 0.3        │
    ├── 3.2 Cache tests ◄───── 3.1             │                     │
    ├── 3.3 WebullBroker ◄──── 1.3, 3.1        │                     │
    ├── 3.4 Broker tests ◄──── 3.3             │                     │
    ├── 3.5 Conformance ◄───── 3.3, 1.7        │                     │
    ├── 3.6 WebullMarketData ◄── 1.4, 3.1      │                     │
    ├── 3.7 Data tests ◄────── 3.6             │                     │
    └── 3.8 Wire factory ◄──── 3.3, 3.6        │                     │
                               │                │                     │
Phase 4 (Migration)            │                │                     │
    │                          │                │                     │
    ├── 4.1 BacktestEngine ◄── 2.4             │                     │
    ├── 4.2 PaperTrading ◄──── 2.1, 2.4        │                     │
    ├── 4.3 AIInvestor CLI ◄── 2.1, 2.4, 1.10  │                     │
    ├── 4.4 V2 Orchestrator ◄── 2.1, 2.4, 2.6, 2.7                  │
    ├── 4.5 Backtest CLI ◄──── 2.4, 1.10       │                     │
    ├── 4.6 Delete data/ ◄──── 4.1-4.5         │                     │
    └── 4.7 Exports ◄───────── 4.6             │                     │
                               │                │                     │
Phase 5 (Cleanup)              │                │                     │
    │                          │                │                     │
    ├── 5.1 Update test mocks ◄── 4.1-4.6      │                     │
    ├── 5.2 Integration tests ◄── Phase 3+4    │                     │
    ├── 5.3 Coverage audit ◄──── 5.1 ──────────────────────────────── 0.1
    ├── 5.4 Documentation ◄──── Phase 4                               │
    └── 5.5 Final validation ◄── 5.1-5.4                             │
```

---

## Parallelization Opportunities

Tasks that can be **developed simultaneously** by independent agents/devs:

| Parallel Track A | Parallel Track B | Parallel Track C |
|-----------------|-----------------|-----------------|
| **1.1** Broker models | **1.5** Screener/News protocols | **1.8** Config models |
| **1.2** Model tests | | **1.9** Config tests |
| **1.3** BrokerProvider | | |
| **1.4** MarketDataProvider | | |

After 1.x converges:

| Track A (Alpaca) | Track B (Webull) |
|-----------------|-----------------|
| **2.1** AlpacaBroker | **3.1** InstrumentCache |
| **2.2** Broker tests | **3.2** Cache tests |
| **2.4** AlpacaMarketData | **3.3** WebullBroker |
| **2.5** Data tests | **3.4** Broker tests |
| **2.6** AlpacaScreener | **3.6** WebullMarketData |
| **2.7** AlpacaNews | **3.7** Data tests |

Phase 4 (Migration) must be done serially — each migration touches shared code.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Order execution regression** | HIGH — real money at stake | Protocol conformance tests + explicit error path tests for every order scenario. Run integration tests against paper/sandbox before any live use. |
| **Float leaks in Decimal fields** | HIGH — rounding errors compound | Grep audit in CI. Conformance tests explicitly assert `isinstance(x, Decimal)` on every money field. |
| **Webull instrument_id resolution failure** | MEDIUM — orders fail silently | InstrumentCache has explicit error on miss. Integration test validates real symbol resolution. |
| **Webull pagination bug** | MEDIUM — missing positions/orders | Max-page safety limits. Tests with multi-page mock responses. |
| **Rate limiting during market hours** | MEDIUM — missed trades | Exponential backoff built into adapter. Logging on retries. |
| **Breaking existing tests during migration** | LOW — but annoying | Run full test suite after every Phase 4 task. Never merge with failing tests. |
| **Config backward compatibility** | LOW — existing users can't start app | Test: config without `[broker]` section defaults to Alpaca. |

---

## Test Count Targets

| Module | Existing Tests | New Tests (min) | Target Total |
|--------|---------------|-----------------|--------------|
| `broker/models.py` | 0 | 15 | 15 |
| `broker/protocols.py` | 0 | 5 (type checks) | 5 |
| `broker/factory.py` | 0 | 10 | 10 |
| `broker/alpaca/broker.py` | 0 | 20 | 20 |
| `broker/alpaca/data.py` | 13 (existing `test_alpaca.py`) | 15 | 28 |
| `broker/alpaca/screener.py` | 0 | 5 | 5 |
| `broker/alpaca/news.py` | 0 | 5 | 5 |
| `broker/webull/instrument_cache.py` | 0 | 15 | 15 |
| `broker/webull/broker.py` | 0 | 25 | 25 |
| `broker/webull/data.py` | 0 | 15 | 15 |
| Protocol conformance | 0 | 20 | 20 |
| Config (new models) | 16 (existing) | 10 | 26 |
| **Total new broker tests** | | **≥160** | |

Combined with existing 218+ tests → **≥378 tests total.**

---

## Acceptance Criteria (Definition of Done)

- [ ] `pytest` — all tests pass (zero failures)
- [ ] `ruff check src/` — zero lint errors
- [ ] Coverage: ≥80% overall, ≥85% on `broker/`
- [ ] No `float` for money anywhere in `broker/` (grep audit)
- [ ] No Alpaca SDK imports outside `broker/alpaca/` (grep audit)
- [ ] No `beavr.data` imports anywhere (module deleted)
- [ ] Existing TOML configs (no `[broker]` section) still work → defaults to Alpaca
- [ ] `bvr ai status` works with both Alpaca and Webull (paper mode)
- [ ] Protocol conformance tests pass for both adapters
- [ ] All new code has complete type hints
- [ ] All new domain models use Pydantic `BaseModel`
