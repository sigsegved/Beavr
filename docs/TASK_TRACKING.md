# Auto Consolidation - Task Tracking

**Spec:** [SPEC_AUTO_CONSOLIDATION.md](SPEC_AUTO_CONSOLIDATION.md)  
**Branch:** `ai_investor_redo`  
**Started:** 2026-02-16  
**Baseline:** 543 unit tests passing

---

## Phase 1: Auto Consolidation ✅
- [x] 1.1 Delete V1 `auto()` function (lines ~1017-1299) and V1-only helpers (`_get_market_status`, `_wait_until`, `_log_state`)
- [x] 1.2 Rename `auto_v2()` → `auto()`, update Typer decorator from `"auto-v2"` to default
- [x] 1.3 Update help text, remove V2 qualifiers
- [x] 1.4 Update/remove tests referencing old auto
- [x] 1.5 Verify `bvr ai auto --help` works
- [x] 1.6 Commit Phase 1

## Phase 2: Repository Abstraction Layer
- [ ] 2.1 Create `src/beavr/db/protocols.py` with Protocol interfaces
- [ ] 2.2 Create `src/beavr/db/sqlite/` directory structure
- [ ] 2.3 Move `Database` + schemas into `sqlite/` (keep backward compat re-exports)
- [ ] 2.4 Refactor `ThesisRepository` → `SQLiteThesisStore`
- [ ] 2.5 Refactor `DDReportsRepository` → `SQLiteDDReportStore`
- [ ] 2.6 Refactor `EventsRepository` → `SQLiteEventStore`
- [ ] 2.7 Refactor `AIPositionsRepository` → `SQLitePositionStore`
- [ ] 2.8 Refactor `BarCache` → `SQLiteBarCacheStore`
- [ ] 2.9 Create `StoreBundle` + `create_sqlite_stores()` factory
- [ ] 2.10 Update `db/__init__.py` with backward-compat re-exports
- [ ] 2.11 Update imports in CLI, orchestrator, agents
- [ ] 2.12 Write Protocol conformance tests
- [ ] 2.13 Commit Phase 2

## Phase 3: Portfolio Models, Schema & Sessions
- [ ] 3.1 Create `PortfolioRecord`, `PortfolioDecision`, `PortfolioSnapshot` models
- [ ] 3.2 Add new tables to V2 schema (portfolios, portfolio_decisions, portfolio_snapshots)
- [ ] 3.3 Add `portfolio_id` to existing V2 tables
- [ ] 3.4 Create `SQLitePortfolioStore`, `SQLiteDecisionStore`, `SQLiteSnapshotStore`
- [ ] 3.5 Update factory with new stores
- [ ] 3.6 Build portfolio setup wizard (interactive CLI)
- [ ] 3.7 Add non-interactive flags (`--portfolio`, `--mode`, `--aggressiveness`, `--directive`)
- [ ] 3.8 Implement aggressiveness → config override mapping
- [ ] 3.9 Wire per-portfolio state files
- [ ] 3.10 Wire stores into orchestrator
- [ ] 3.11 Add decision logging throughout orchestrator
- [ ] 3.12 Add daily snapshot capture
- [ ] 3.13 Write comprehensive tests
- [ ] 3.14 Commit Phase 3

## Phase 4: Clean Slate Command
- [ ] 4.1 Implement `delete_portfolio()` and `delete_all_data()` in stores
- [ ] 4.2 Implement `bvr ai reset` command with interactive flow
- [ ] 4.3 Add DD report file + state file cleanup
- [ ] 4.4 Write tests
- [ ] 4.5 Commit Phase 4

## Phase 5: Earnings Integration
- [ ] 5.1 Create `EarningsCalendarFetcher` (Alpha Vantage + yfinance)
- [ ] 5.2 Fix `get_upcoming_earnings()` date bug
- [ ] 5.3 Create `EarningsPlayAgent`
- [ ] 5.4 Add earnings scan to orchestrator overnight phase
- [ ] 5.5 Add `[earnings]` config section to TOML
- [ ] 5.6 Add `bvr ai earnings` CLI command
- [ ] 5.7 Add dependencies to pyproject.toml
- [ ] 5.8 Write tests
- [ ] 5.9 Commit Phase 5

## Phase 6: Final Validation
- [ ] 6.1 Full test suite passes
- [ ] 6.2 Lint clean: `ruff check src/`
- [ ] 6.3 Coverage >= 80%
- [ ] 6.4 Final commit
