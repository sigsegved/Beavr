# AI Investor v2 Implementation Tasks

**Branch**: `ai_investor_redo`  
**Started**: February 4, 2026  
**Architecture**: [V2_ARCHITECTURE.md](./ai_investor/V2_ARCHITECTURE.md)

---

## Overview

This document tracks the implementation of the v2 AI Investor system. Tasks are organized by implementation phase, following the architecture review recommendations.

---

## Phase 1: Core Models and Database Schema

### Task 1.1: Trade Thesis Model ✅
**Status**: Complete  
**Files**: `src/beavr/models/thesis.py`

Create the `TradeThesis` Pydantic model with all required fields:
- Identification (id, symbol, created_at)
- Classification (trade_type: day_trade, swing, position)
- Core hypothesis (direction, entry_rationale, catalyst, catalyst_date)
- Price targets (entry_price_target, profit_target, stop_loss)
- Time management (expected_exit_date, max_hold_date)
- Invalidation conditions
- Status tracking (status, confidence, dd_approved, dd_report)

### Task 1.2: Due Diligence Report Model ✅
**Status**: Complete  
**Files**: `src/beavr/models/dd_report.py`

Create the `DueDiligenceReport` Pydantic model:
- Verdict (recommendation: approve/reject/conditional, confidence)
- Analysis sections (fundamental, technical, catalyst, risk_factors)
- Adjusted targets (recommended entry, target, stop, position_size_pct)
- Rationale (approval or rejection reason)

### Task 1.3: Market Event Model ✅
**Status**: Complete  
**Files**: `src/beavr/models/market_event.py`

Create the `MarketEvent` Pydantic model:
- Event classification (event_type enum)
- Event details (symbol, headline, summary, source, timestamp)
- Importance rating (high/medium/low)
- Structured data fields (earnings_date, estimates, etc.)

### Task 1.4: Morning Candidate Model ✅
**Status**: Complete  
**Files**: `src/beavr/models/morning_candidate.py`

Create the `MorningCandidate` Pydantic model:
- Scan identification (symbol, scan_type)
- Pre-market data (price, change_pct, volume)
- Technical levels (resistance, support, rsi)
- Preliminary assessment and ranking

### Task 1.5: Database Schema Migration ✅
**Status**: Complete  
**Files**: `src/beavr/db/schema_v2.py`

Create v2 database tables:
- `market_events` - News Monitor events
- `trade_theses` - Active and historical theses
- `dd_reports` - Due diligence reports
- `ai_positions_v2` - Enhanced positions with thesis links
- `position_reviews` - Audit trail for position management

### Task 1.6: Repository Classes ✅
**Status**: Complete  
**Files**: `src/beavr/db/thesis_repo.py`, `src/beavr/db/events_repo.py`, `src/beavr/db/dd_reports_repo.py`

Implement CRUD operations for new models:
- ThesisRepository: create, update, get_active, get_by_symbol, close
- EventsRepository: create, get_recent, get_by_symbol, mark_processed
- DDReportsRepository: create, get_by_thesis, get_approval_stats

---

## Phase 2: Research Pipeline (Continuous)

### Task 2.1: News Monitor Agent
**Status**: In Progress  
**Files**: `src/beavr/agents/news_monitor.py`

Implement the News Monitor agent:
- Alpaca News API integration
- Event classification and importance scoring
- 15-minute polling loop (configurable)
- Event storage to database
- Filter for "medium" and higher importance

**Data Sources (Initial)**:
- Alpaca News API (included with trading account)
- Yahoo Finance earnings calendar (free)
- SEC EDGAR RSS feeds (free)

### Task 2.2: Thesis Generator Agent
**Status**: Not Started  
**Files**: `src/beavr/agents/thesis_generator.py`

Implement the Thesis Generator agent:
- Event-driven mode (process News Monitor events)
- Scheduled mode (nightly watchlist review)
- LLM reasoning for thesis formation
- Quality gate (min confidence threshold)
- Thesis storage to database

**LLM Prompt Focus**:
- Catalyst identification
- Price target derivation
- Time horizon assessment
- Invalidation condition definition

### Task 2.3: Watchlist Manager
**Status**: Not Started  
**Files**: `src/beavr/agents/watchlist_manager.py`

Implement watchlist management:
- Track active theses by symbol
- Priority ranking based on catalyst proximity
- Integration with Morning Scanner
- CLI commands for manual watchlist management

---

## Phase 3: Morning Scanner

### Task 3.1: Pre-Market Data Collection
**Status**: Deferred (using existing data layer initially)  
**Files**: `src/beavr/data/premarket.py`

Implement pre-market data fetching:
- Alpaca pre-market quotes (requires subscription)
- Gap calculation (vs previous close)
- Volume comparison to average
- Technical level identification

### Task 3.2: Morning Scanner Agent (Technical) ✅
**Status**: Complete  
**Files**: `src/beavr/agents/morning_scanner.py`

Implemented the Morning Scanner:
- Gap detection (configurable threshold, default 3%)
- Volume surge detection (2x average)
- Quality filter application (price, volume, extreme moves)
- Candidate ranking by conviction score
- Thesis cross-reference support

**Scan Types**:
- `gap_up`: Stocks gapping up significantly
- `volume_surge`: Unusual pre-market volume
- `breakout`: Breaking technical resistance
- `sector_leader`: Best performer in hot sector
- `thesis_setup`: Aligns with active thesis

### Task 3.3: Scanner/Thesis Cross-Reference ✅
**Status**: Complete  
**Files**: `src/beavr/agents/morning_scanner.py`

Scanner cross-references with active theses:
- If scanned stock has active thesis, boost priority
- Sets scan_type to THESIS_SETUP for alignment
- Adds thesis_id to candidate for tracking

---

## Phase 4: Due Diligence Agent

### Task 4.1: DD Data Collection
**Status**: Deferred (using existing indicator data initially)  
**Files**: `src/beavr/data/fundamentals.py`

Implement fundamental data collection:
- Yahoo Finance for basic fundamentals (free)
- Market cap, P/E, P/S, revenue growth
- Institutional ownership percentage
- Insider transaction summary (SEC Form 4)
- Analyst ratings summary

### Task 4.2: Due Diligence Agent Core ✅
**Status**: Complete  
**Files**: `src/beavr/agents/dd_agent.py`

Implemented the DD Agent:
- Comprehensive LLM-based analysis
- Structured DDAnalysisOutput schema
- analyze_thesis() method for thesis-based DD
- quick_dd() method for momentum plays
- Validation rules (confidence threshold, R/R check)
- Graceful error handling with reject-on-error

**DD Analysis Framework**:
1. Fundamental check (real revenue, reasonable valuation)
2. Technical analysis (support/resistance, trend)
3. Catalyst verification (still valid, timing)
4. Risk assessment (downside, known risks)
5. Position sizing recommendation

### Task 4.3: DD CLI Command
**Status**: Not Started  
**Files**: `src/beavr/cli/ai.py`

Add `bvr ai dd <symbol>` command:
- Manual DD trigger for any symbol
- Display formatted DD report
- Optional: save to database

---

## Phase 5: Trade Execution

### Task 5.1: Trade Executor Agent
**Status**: Not Started  
**Files**: `src/beavr/agents/trade_executor.py`

Implement the Trade Executor:
- Position sizing (fixed fractional method)
- Order type selection (market for momentum, limit for thesis)
- Alpaca order submission
- Position record creation with thesis attachment
- Error handling and retry logic

### Task 5.2: Position Manager Agent
**Status**: Not Started  
**Files**: `src/beavr/agents/position_manager.py`

Implement the Position Manager:
- Price-based exit checks (stop/target)
- Time-based exit checks (expected date, max hold)
- Thesis validation (is thesis still intact?)
- Invalidation condition monitoring
- Partial profit taking (configurable)
- Position review logging

### Task 5.3: Exit Execution
**Status**: Not Started  
**Files**: `src/beavr/agents/position_manager.py`

Implement exit logic:
- Market sell for stop/target hits
- Scheduled exit for time-based exits
- Thesis invalidation exit
- Partial position exits
- Exit type classification and logging

---

## Phase 6: Orchestration and CLI

### Task 6.1: V2 Orchestrator Engine
**Status**: Not Started  
**Files**: `src/beavr/orchestrator/engine_v2.py`

Implement the v2 orchestrator:
- Continuous research loop (always on)
- Market hours execution loop
- Position management loop
- State persistence
- Graceful shutdown handling

### Task 6.2: Scheduler
**Status**: Not Started  
**Files**: `src/beavr/orchestrator/scheduler.py`

Implement task scheduling:
- News Monitor: every 15 minutes (all hours)
- Thesis Review: daily at 8 PM ET
- Morning Scan: 4 AM - 9:30 AM ET
- Position Check: every 5 minutes (market hours)
- Market hour detection

### Task 6.3: CLI Updates
**Status**: Not Started  
**Files**: `src/beavr/cli/ai.py`

Update CLI commands for v2:
- `bvr ai auto` - Major rework for v2 flow
- `bvr ai thesis list` - List active theses
- `bvr ai thesis show <id>` - Show thesis details
- `bvr ai thesis create` - Manual thesis creation
- `bvr ai news` - View recent market events
- `bvr ai dd <symbol>` - Trigger DD manually
- `bvr ai scan` - Run morning scan manually

### Task 6.4: Configuration
**Status**: Not Started  
**Files**: `config/ai_investor_v2.toml`, `src/beavr/core/config.py`

Create v2 configuration:
- Agent parameters (intervals, thresholds)
- Quality filter settings
- Trade type profiles (day/swing/position)
- Risk management settings
- LLM settings (model, tokens)

---

## Phase 7: Testing and Validation

### Task 7.1: Unit Tests - Models
**Status**: Not Started  
**Files**: `tests/unit/test_models_v2.py`

Write unit tests for new models:
- TradeThesis validation
- DueDiligenceReport validation
- MarketEvent validation
- MorningCandidate validation

### Task 7.2: Unit Tests - Agents
**Status**: Not Started  
**Files**: `tests/unit/test_agents_v2.py`

Write unit tests for agents:
- News Monitor event processing
- Thesis Generator thesis creation
- Morning Scanner candidate ranking
- DD Agent report generation
- Position Manager exit decisions

### Task 7.3: Unit Tests - Repositories
**Status**: Not Started  
**Files**: `tests/unit/test_db_v2.py`

Write unit tests for repositories:
- CRUD operations for all new tables
- Query filtering and ordering
- Status transitions

### Task 7.4: Integration Tests
**Status**: Not Started  
**Files**: `tests/integration/test_ai_investor_v2.py`

Write integration tests:
- Full pipeline flow (event → thesis → DD → execute)
- Position management lifecycle
- Circuit breaker triggers

### Task 7.5: Paper Trading Validation
**Status**: Not Started  

Run v2 system in paper trading mode:
- Monitor for 1 week minimum
- Track thesis accuracy
- Measure DD rejection rate
- Validate position management

---

## Completion Checklist

- [x] Phase 1: Core Models and Database Schema
  - [x] Task 1.1: Trade Thesis Model
  - [x] Task 1.2: Due Diligence Report Model
  - [x] Task 1.3: Market Event Model
  - [x] Task 1.4: Morning Candidate Model
  - [x] Task 1.5: Database Schema Migration
  - [x] Task 1.6: Repository Classes
- [ ] Phase 2: Research Pipeline
  - [ ] Task 2.1: News Monitor Agent
  - [ ] Task 2.2: Thesis Generator Agent
  - [ ] Task 2.3: Watchlist Manager
- [x] Phase 3: Morning Scanner
  - [ ] Task 3.1: Pre-Market Data Collection (deferred)
  - [x] Task 3.2: Morning Scanner Agent
  - [x] Task 3.3: Scanner/Thesis Cross-Reference
- [x] Phase 4: Due Diligence Agent
  - [ ] Task 4.1: DD Data Collection (deferred)
  - [x] Task 4.2: Due Diligence Agent Core
  - [ ] Task 4.3: DD CLI Command
- [ ] Phase 5: Trade Execution
  - [ ] Task 5.1: Trade Executor Agent
  - [ ] Task 5.2: Position Manager Agent
  - [ ] Task 5.3: Exit Execution
- [ ] Phase 6: Orchestration and CLI
  - [ ] Task 6.1: V2 Orchestrator Engine
  - [ ] Task 6.2: Scheduler
  - [ ] Task 6.3: CLI Updates
  - [ ] Task 6.4: Configuration
- [x] Phase 7: Testing and Validation
  - [x] Task 7.1: Unit Tests - Models
  - [ ] Task 7.2: Unit Tests - Agents
  - [ ] Task 7.3: Unit Tests - Repositories
  - [ ] Task 7.4: Integration Tests
  - [ ] Task 7.5: Paper Trading Validation

---

## Notes

### Dependencies
- `alpaca-py` for news API and trading (existing)
- `yfinance` for fundamental data (add to dependencies)
- LLM client (existing)

### Risk Items
- Alpaca News API rate limits
- LLM cost accumulation during continuous research
- Pre-market data availability (may need Alpaca subscription upgrade)

### Success Criteria
- All unit tests passing
- 1 week successful paper trading
- DD rejection rate between 20-40%
- Thesis accuracy > 50%
