# Beavr AI Investor: Fleet Implementation Plan

> **Purpose**: This document is a complete, self-contained implementation plan for Copilot CLI `/fleet` mode.
> Each task is independent, testable, and should be committed separately after passing all validations.
>
> **Reference**: See `docs/BEAVR_AI_AUTOPSY.md` for full context on why each fix is needed.

---

## Environment & Conventions

```bash
# Setup
cd /Users/karthik/workspace/Beavr
source .venv/bin/activate

# The .env file contains ALPACA_API_KEY and ALPACA_SECRET_KEY for paper trading
# You MAY use these for integration testing against the Alpaca paper broker

# Test commands
pytest tests/unit/ -v              # Unit tests (MUST pass after every task)
ruff check src/                     # Lint (MUST pass after every task)

# Commit pattern (after EVERY task)
git add -A && git commit -m "<task-id>: <description>"
```

### Code Rules (from .github/copilot-instructions.md)
- **ALWAYS** use `Decimal` for money — never `float` for prices/quantities/values
- **ALWAYS** add complete type hints to every function
- **ALWAYS** use Pydantic `BaseModel` for domain objects
- **ALWAYS** write tests alongside code
- Use `from __future__ import annotations` at top of every file

---

## Task Dependency Graph

```
TASK-1 (analyze fix)     ──┐
TASK-2 (pre-screener)    ──┤── Independent, run in parallel
TASK-3 (time exits)      ──┤
TASK-4 (bracket orders)  ──┤
TASK-5 (max positions)   ──┤
TASK-6 (price guard)     ──┤
TASK-7 (trend filter)    ──┤
TASK-8 (vol sizing)      ──┘
                           │
TASK-9 (nightly review)  ──┤── Depends on TASK-3 (uses time-exit logic)
                           │
TASK-10 (trailing stops) ──┤── Depends on TASK-4 (uses bracket order infra)
                           │
TASK-11 (regime scaling) ──┤── Depends on TASK-5 (uses position cap infra)
                           │
TASK-12 (market brief)   ──┘── Independent but do last (new feature)
```

---

## TASK-1: Fix `bvr ai analyze` Return Type Crash

**Files to modify:**
- `src/beavr/cli/ai.py` (function `analyze_opportunities` at line ~310)

**Problem:** `analyze_opportunities()` returns `[]` on early exit but the caller at line 854 unpacks as `picks, market_view, risk_level = ...`, causing `ValueError`.

**Changes:**

1. In `analyze_opportunities()` (line ~310), change BOTH early returns:
   ```python
   # Line ~317: change
   return []
   # to:
   return [], "", ""

   # Line ~326: change
   return []
   # to:
   return [], "", ""
   ```

2. Fix the declared return type from `list[dict]` to `tuple[list[dict], str, str]`:
   ```python
   def analyze_opportunities(self, amount: Decimal, max_picks: int = 3) -> tuple[list[dict], str, str]:
   ```

3. Wrap the LLM call at line ~395 in try/except:
   ```python
   try:
       result: Analysis = self.llm.reason(
           system_prompt="You are a professional day trader...",
           user_prompt=prompt,
           output_schema=Analysis,
       )
   except Exception as e:
       logger.error(f"LLM analysis failed: {e}")
       return [], f"Analysis failed: {e}", "high"
   ```

4. Add quality filter to the `analyze` CLI command — after getting opportunities, filter using `is_quality_stock` with stricter criteria (min price $10):
   ```python
   opps = [o for o in investor.get_quality_opportunities() if o.get("price", 0) >= 10]
   ```

**Tests to write** (`tests/unit/test_analyze_command.py`):
```python
class TestAnalyzeOpportunities:
    def test_returns_tuple_on_empty_opportunities(self):
        """analyze_opportunities returns 3-tuple even when no opportunities."""
        investor = AIInvestor()
        # Mock get_quality_opportunities to return []
        investor.get_quality_opportunities = lambda: []
        result = investor.analyze_opportunities(Decimal("1000"))
        assert isinstance(result, tuple)
        assert len(result) == 3
        picks, view, risk = result
        assert picks == []

    def test_returns_tuple_on_no_technicals(self):
        """analyze_opportunities returns 3-tuple when technicals unavailable."""
        investor = AIInvestor()
        investor.get_quality_opportunities = lambda: [{"symbol": "XYZ", "price": 50.0, "change_pct": 5.0, "type": "gainer", "in_universe": False}]
        investor.get_technical_indicators = lambda s: None  # All fail
        result = investor.analyze_opportunities(Decimal("1000"))
        assert isinstance(result, tuple)
        assert len(result) == 3
```

**Validation:**
```bash
pytest tests/unit/test_analyze_command.py -v
ruff check src/beavr/cli/ai.py
```

**Commit:** `git commit -m "TASK-1: fix analyze_opportunities return type crash and add error handling"`

---

## TASK-2: Hard Pre-Screener in Research Pipeline

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (functions `_fetch_market_mover_events` at line ~1002, `_build_research_universe` at line ~1080)
- `src/beavr/cli/ai.py` (move `is_quality_stock` to a shared location)
- New file: `src/beavr/core/screener.py` (shared quality gate)

**Changes:**

1. Create `src/beavr/core/screener.py` with a standalone quality gate:
   ```python
   """Stock quality screening for the research pipeline."""
   from __future__ import annotations

   import logging

   logger = logging.getLogger(__name__)

   # Large-cap, liquid stocks that always pass quality screening
   QUALITY_UNIVERSE: set[str] = {
       # ETFs
       "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "XLF", "XLE", "XLK",
       "GLD", "SLV", "TLT", "EEM", "VWO",
       # Mega-cap
       "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AVGO",
       # Large-cap tech
       "AMD", "INTC", "CRM", "ORCL", "ADBE", "NFLX", "PYPL", "SQ", "UBER",
       "SNOW", "PLTR", "NET", "CRWD", "ZS", "DDOG", "MDB",
       # Financials
       "JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "BLK", "C", "WFC",
       # Healthcare
       "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "AMGN", "GILD",
       # Consumer
       "WMT", "COST", "HD", "MCD", "SBUX", "NKE", "DIS", "TGT",
       # Energy
       "XOM", "CVX", "COP", "SLB",
       # Industrial
       "CAT", "BA", "HON", "UPS", "LMT", "RTX", "DE", "GE",
       # Crypto-adjacent
       "COIN", "MSTR",
   }

   # Minimum thresholds for the autonomous research pipeline
   MIN_RESEARCH_PRICE: float = 15.0
   MAX_RESEARCH_PRICE: float = 800.0
   MIN_RESEARCH_VOLUME: int = 500_000


   def passes_quality_gate(
       symbol: str,
       price: float = 0.0,
       avg_volume: int = 0,
   ) -> bool:
       """Hard quality gate for the autonomous research pipeline.

       Stocks that fail this check NEVER reach the LLM pipeline.
       This is distinct from the CLI quality check — it is stricter.
       """
       if symbol in QUALITY_UNIVERSE:
           return True
       if len(symbol) > 5:
           return False
       if "." in symbol:
           return False
       if 0 < price < MIN_RESEARCH_PRICE:
           return False
       if price > MAX_RESEARCH_PRICE:
           return False
       if 0 < avg_volume < MIN_RESEARCH_VOLUME:
           return False
       return True
   ```

2. In `v2_engine.py` `_fetch_market_mover_events()` (line ~1002), filter movers BEFORE creating events:
   ```python
   from beavr.core.screener import passes_quality_gate

   # Inside _fetch_market_mover_events, after getting movers list:
   for mover in movers:
       symbol = mover.get("symbol", "")
       price = float(mover.get("price", 0))
       if not symbol:
           continue
       if not passes_quality_gate(symbol, price=price):
           logger.debug(f"Screener rejected mover: {symbol} (price=${price:.2f})")
           continue
       # ... existing event creation code ...
   ```

3. In `_build_research_universe()` (line ~1080), add filtering:
   ```python
   # After building the symbols set, filter before returning:
   limited = [s for s in symbols if passes_quality_gate(s)][:self.config.max_research_symbols]
   ```

4. Update `cli/ai.py` to import from the new shared module instead of defining its own, and keep backward compatibility by aliasing.

**Tests to write** (`tests/unit/test_screener.py`):
```python
class TestQualityGate:
    @pytest.mark.parametrize("symbol,price,expected", [
        ("AAPL", 190.0, True),    # In quality universe
        ("SPY", 560.0, True),     # ETF
        ("DVLT", 0.72, False),    # Penny stock
        ("BMEA", 0.95, False),    # Sub-$1
        ("SNAP", 5.14, False),    # Below $15
        ("AMZN", 200.0, True),    # Quality universe
        ("XYZ", 50.0, True),     # Unknown but valid price
        ("ABCDEF", 50.0, False),  # Symbol too long
        ("BRK.B", 50.0, False),   # Has dot
    ])
    def test_passes_quality_gate(self, symbol, price, expected):
        assert passes_quality_gate(symbol, price=price) == expected
```

**Validation:**
```bash
pytest tests/unit/test_screener.py -v
pytest tests/unit/ -v  # Full suite
ruff check src/beavr/core/screener.py src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-2: add hard pre-screener to research pipeline, reject junk before LLM"`

---

## TASK-3: Time-Based Exit Enforcement (Deterministic)

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (function `_monitor_positions` at line ~1957)

**Changes:**

1. In `_monitor_positions()`, AFTER the existing stop/target checks, add thesis-based time checks:

   ```python
   # After the stop_pct / target_pct checks, BEFORE the debug log line:

   # Check time-based exits (thesis max_hold_date)
   if db_pos and self.thesis_repo:
       try:
           # Find the thesis for this position
           theses = self.thesis_repo.get_by_symbol(symbol)
           active_thesis = next(
               (t for t in theses if t.status in {ThesisStatus.EXECUTED, ThesisStatus.ACTIVE}),
               None,
           )
           if active_thesis:
               today = date.today()
               # Hard exit: past max_hold_date
               if active_thesis.max_hold_date and today > active_thesis.max_hold_date:
                   logger.info(
                       f"⏰ TIME EXIT: {symbol} past max_hold_date "
                       f"({active_thesis.max_hold_date})"
                   )
                   self._close_position(symbol, "time_exit", pnl_pct)
                   continue

               # Soft flag: past expected_exit_date (log warning)
               if active_thesis.expected_exit_date and today > active_thesis.expected_exit_date:
                   logger.warning(
                       f"⚠️ {symbol} past expected_exit_date "
                       f"({active_thesis.expected_exit_date}) — review needed"
                   )
       except Exception as e:
           logger.debug(f"Thesis lookup failed for {symbol}: {e}")
   ```

2. Add the required imports at the top of the function or file:
   ```python
   from datetime import date
   from beavr.models.thesis import ThesisStatus
   ```

**Tests to write** (`tests/unit/test_time_exits.py`):
```python
class TestTimeBasedExits:
    def test_closes_position_past_max_hold_date(self):
        """Position past max_hold_date is force-closed."""
        # Create mock orchestrator with mock broker, thesis_repo, positions_repo
        # Set thesis.max_hold_date to yesterday
        # Call _monitor_positions()
        # Assert _close_position was called with reason="time_exit"

    def test_holds_position_before_max_hold_date(self):
        """Position before max_hold_date is NOT closed."""
        # Set thesis.max_hold_date to next week
        # Call _monitor_positions()
        # Assert _close_position was NOT called

    def test_logs_warning_past_expected_exit_date(self):
        """Position past expected_exit_date logs warning but does not close."""
        # Set expected_exit_date to yesterday, max_hold_date to next week
        # Call _monitor_positions()
        # Assert warning logged, position NOT closed
```

**Validation:**
```bash
pytest tests/unit/test_time_exits.py -v
pytest tests/unit/ -v
ruff check src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-3: enforce time-based exits when position exceeds max_hold_date"`

---

## TASK-4: Bracket Orders on Entry (Stop + Target at Broker Level)

**Files to modify:**
- `src/beavr/broker/models.py` (add `BracketOrderRequest` model)
- `src/beavr/broker/protocols.py` (add `submit_bracket_order` to protocol)
- `src/beavr/broker/alpaca/broker.py` (implement bracket order submission)
- `src/beavr/orchestrator/v2_engine.py` (update `_execute_trade` at line ~1841)

**Changes:**

1. Add `BracketOrderRequest` to `src/beavr/broker/models.py`:
   ```python
   class BracketOrderRequest(BaseModel):
       """Bracket order: entry + stop loss + take profit submitted together."""

       model_config = {"frozen": True}

       symbol: str = Field(description="Ticker symbol")
       side: Literal["buy", "sell"] = Field(description="Order side")
       quantity: Optional[Decimal] = Field(default=None)
       notional: Optional[Decimal] = Field(default=None)
       tif: Literal["day", "gtc"] = Field(default="gtc")
       # Bracket legs
       take_profit_price: Decimal = Field(description="Take profit limit price")
       stop_loss_price: Decimal = Field(description="Stop loss price")

       @model_validator(mode="after")
       def _validate_quantity_xor_notional(self) -> BracketOrderRequest:
           has_qty = self.quantity is not None
           has_notional = self.notional is not None
           if has_qty == has_notional:
               raise ValueError("Exactly one of 'quantity' or 'notional' must be provided")
           return self
   ```

2. Add `submit_bracket_order` to `BrokerProvider` protocol in `src/beavr/broker/protocols.py`:
   ```python
   def submit_bracket_order(self, order: BracketOrderRequest) -> OrderResult:
       """Submit a bracket order (entry + stop + target)."""
       ...
   ```

3. Implement in `src/beavr/broker/alpaca/broker.py` using Alpaca's `order_class="bracket"`:
   ```python
   def submit_bracket_order(self, order: BracketOrderRequest) -> OrderResult:
       """Submit bracket order via Alpaca."""
       kwargs = {
           "symbol": order.symbol,
           "side": order.side,
           "type": "market",
           "time_in_force": order.tif,
           "order_class": "bracket",
           "take_profit": {"limit_price": float(order.take_profit_price)},
           "stop_loss": {"stop_price": float(order.stop_loss_price)},
       }
       if order.notional is not None:
           kwargs["notional"] = float(order.notional)
       else:
           kwargs["qty"] = float(order.quantity)

       alpaca_order = self._client.submit_order(**kwargs)
       return OrderResult(
           order_id=str(alpaca_order.id),
           symbol=order.symbol,
           side=order.side,
           order_type="market",
           status=str(alpaca_order.status),
           filled_qty=Decimal(str(alpaca_order.filled_qty or 0)),
           filled_avg_price=(
               Decimal(str(alpaca_order.filled_avg_price))
               if alpaca_order.filled_avg_price else None
           ),
           submitted_at=alpaca_order.submitted_at,
       )
   ```

4. Update `_execute_trade()` in `v2_engine.py` (line ~1841) to use bracket orders:
   ```python
   # Replace the existing OrderRequest submission with:
   from beavr.broker.models import BracketOrderRequest

   # Try bracket order first, fall back to simple order
   try:
       bracket_request = BracketOrderRequest(
           symbol=thesis.symbol,
           side="buy",
           notional=Decimal(str(round(float(position_value), 2))),
           tif="gtc",
           take_profit_price=thesis.profit_target,
           stop_loss_price=thesis.stop_loss,
       )
       order = self._broker.submit_bracket_order(bracket_request)
       logger.info(f"   ✅ Bracket order submitted: {order.order_id}")
       logger.info(f"   🎯 Target: ${thesis.profit_target:.2f} | 🛑 Stop: ${thesis.stop_loss:.2f}")
   except (AttributeError, NotImplementedError):
       # Broker doesn't support bracket orders — fall back
       logger.warning("Broker does not support bracket orders, using simple market order")
       order_request = OrderRequest(
           symbol=thesis.symbol,
           notional=Decimal(str(round(float(position_value), 2))),
           side="buy",
           order_type="market",
           tif="day",
       )
       order = self._broker.submit_order(order_request)
   ```

**Tests to write** (`tests/unit/test_bracket_orders.py`):
```python
class TestBracketOrderRequest:
    def test_bracket_order_valid(self):
        order = BracketOrderRequest(
            symbol="AAPL",
            side="buy",
            notional=Decimal("1000"),
            take_profit_price=Decimal("200"),
            stop_loss_price=Decimal("170"),
        )
        assert order.symbol == "AAPL"
        assert order.take_profit_price == Decimal("200")

    def test_bracket_order_requires_qty_or_notional(self):
        with pytest.raises(ValueError):
            BracketOrderRequest(
                symbol="AAPL", side="buy",
                take_profit_price=Decimal("200"),
                stop_loss_price=Decimal("170"),
            )

class TestExecuteTradeWithBracket:
    def test_execute_trade_uses_bracket_order(self):
        """_execute_trade should attempt bracket order first."""
        # Mock broker with submit_bracket_order
        # Call _execute_trade with a thesis
        # Assert submit_bracket_order was called (not submit_order)

    def test_execute_trade_falls_back_to_simple_order(self):
        """_execute_trade falls back if broker lacks bracket support."""
        # Mock broker WITHOUT submit_bracket_order
        # Call _execute_trade
        # Assert submit_order was called as fallback
```

**Validation:**
```bash
pytest tests/unit/test_bracket_orders.py -v
pytest tests/unit/ -v
ruff check src/beavr/broker/ src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-4: add bracket order support (stop + target at broker level on entry)"`

---

## TASK-5: Max Positions Cap

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (class `V2Config` at line ~197, functions `_execute_swing_trades` at line ~1790 and `_execute_power_hour`)

**Changes:**

1. Add `max_open_positions` to `V2Config`:
   ```python
   max_open_positions: int = 8  # Maximum simultaneous positions
   min_position_value: float = 500.0  # Minimum $ per position
   ```

2. In `_execute_swing_trades()` (line ~1790) and `_execute_power_hour()`, add position count check BEFORE the loop:
   ```python
   # Get current position count
   current_positions = self._broker.get_positions() if self._broker else []
   if len(current_positions) >= self.config.max_open_positions:
       logger.info(
           f"Position cap reached ({len(current_positions)}/{self.config.max_open_positions}) "
           f"— no new entries until a position is closed"
       )
       return
   ```

3. In `_execute_trade()`, add position value minimum check:
   ```python
   if position_value < Decimal(str(self.config.min_position_value)):
       logger.warning(
           f"Position value ${position_value:.2f} below minimum "
           f"${self.config.min_position_value:.2f} — skipping"
       )
       return False
   ```

**Tests to write** (`tests/unit/test_position_cap.py`):
```python
class TestPositionCap:
    def test_blocks_new_entry_when_at_max(self):
        """No new entries when position count equals max."""
        # Mock broker returning 8 positions
        # Call _execute_swing_trades with approved theses
        # Assert no orders submitted

    def test_allows_entry_when_below_max(self):
        """New entries allowed when below cap."""
        # Mock broker returning 5 positions
        # Call _execute_swing_trades
        # Assert order submitted

    def test_min_position_value_enforced(self):
        """Positions below min_position_value are rejected."""
        # Set thesis that would result in $200 position
        # Assert _execute_trade returns False
```

**Validation:**
```bash
pytest tests/unit/test_position_cap.py -v
pytest tests/unit/ -v
ruff check src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-5: enforce max position cap (8) and min position value ($500)"`

---

## TASK-6: Price Guard Check Before Entry

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (function `_execute_trade` at line ~1841)

**Changes:**

1. After the `position_value` check, add a live-price vs. thesis-target guard:
   ```python
   # Get live price from broker data
   try:
       live_bars = self._data_provider.get_bars(
           thesis.symbol,
           date.today() - timedelta(days=2),
           date.today(),
       ) if self._data_provider else None

       if live_bars is not None and not live_bars.empty:
           live_price = Decimal(str(live_bars["close"].iloc[-1]))
           entry_target = thesis.entry_price_target

           if entry_target > 0:
               deviation_pct = float((live_price - entry_target) / entry_target * 100)
               if deviation_pct > 3.0:
                   logger.info(
                       f"   ⏭️ Skipping {thesis.symbol}: live price ${live_price:.2f} "
                       f"is {deviation_pct:.1f}% above entry target ${entry_target:.2f}"
                   )
                   self._log_decision(
                       decision_type="entry_skipped",
                       action="skip",
                       symbol=thesis.symbol,
                       thesis_id=thesis.id,
                       reasoning=f"Live price {deviation_pct:.1f}% above target",
                   )
                   return False

               # Use live price for share calculation instead of thesis target
               current_price = live_price
           else:
               current_price = thesis.entry_price_target
       else:
           current_price = thesis.entry_price_target
   except Exception as e:
       logger.warning(f"Could not fetch live price for {thesis.symbol}: {e}")
       current_price = thesis.entry_price_target
   ```

2. Remove the `# TODO: Get live price` comment and the line `current_price = thesis.entry_price_target`.

**Tests to write** (`tests/unit/test_price_guard.py`):
```python
class TestPriceGuard:
    def test_skips_when_price_above_threshold(self):
        """Skips entry when live price > 3% above thesis target."""
        # Mock data_provider returning price 5% above thesis target
        # Assert _execute_trade returns False

    def test_allows_when_price_within_threshold(self):
        """Allows entry when live price within 3% of target."""
        # Mock data_provider returning price 1% above thesis target
        # Assert _execute_trade proceeds

    def test_uses_live_price_for_share_calculation(self):
        """Share calculation uses live price, not thesis target."""
        # Verify shares = position_value / live_price
```

**Validation:**
```bash
pytest tests/unit/test_price_guard.py -v
pytest tests/unit/ -v
ruff check src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-6: add price guard — skip entry if live price >3% above thesis target"`

---

## TASK-7: Trend Filter in Swing Trader Prompt

**Files to modify:**
- `src/beavr/agents/swing_trader.py` (function `get_system_prompt` at line ~76)

**Changes:**

1. Replace the current system prompt with a momentum-aware version. The key changes to the prompt:
   - Add a **TREND FILTER** rule: "Only consider RSI < 35 setups IF price is above the 50-day SMA"
   - Add a **DO NOT BUY** list: stocks below 50-SMA with RSI < 40, negative catalyst reactions
   - Keep the existing position sizing and risk management sections

   Specifically, in the `get_system_prompt` method, replace the `BUY SIGNALS TO LOOK FOR:` section:

   ```python
   BUY SIGNALS TO LOOK FOR:
   - MOMENTUM: Price > SMA50, RSI between 50-70, volume expanding (strong uptrend)
   - PULLBACK IN UPTREND: Price > SMA50, temporarily below SMA20, RSI 35-50 (buy the dip IF trend intact)
   - BREAKOUT: Price breaking above Bollinger upper band with volume > 1.5x average
   - OVERSOLD BOUNCE (ONLY if trend intact): RSI < 35 BUT price MUST be above 50-day SMA

   DO NOT BUY (FALLING KNIFE FILTER):
   - RSI < 40 AND price below 50-day SMA (broken trend + weak momentum = falling knife)
   - Stock with positive news but negative price reaction (market knows something)
   - Stock down >15% in last 20 days without clear catalyst resolution
   - Price below both SMA20 and SMA50 (confirmed downtrend)
   ```

2. Keep all other sections (sell signals, position sizing, risk management) unchanged.

**Tests to write** (`tests/unit/test_swing_trader_prompt.py`):
```python
class TestSwingTraderPrompt:
    def test_prompt_contains_trend_filter(self):
        """System prompt should include trend filter rules."""
        agent = SwingTraderAgent(llm=mock_llm)
        prompt = agent.get_system_prompt()
        assert "50-day SMA" in prompt or "SMA50" in prompt
        assert "FALLING KNIFE" in prompt or "falling knife" in prompt

    def test_prompt_rejects_oversold_in_downtrend(self):
        """Prompt should warn against buying RSI < 40 below SMA50."""
        agent = SwingTraderAgent(llm=mock_llm)
        prompt = agent.get_system_prompt()
        assert "below 50-day SMA" in prompt or "below SMA50" in prompt
```

**Validation:**
```bash
pytest tests/unit/test_swing_trader_prompt.py -v
pytest tests/unit/ -v
ruff check src/beavr/agents/swing_trader.py
```

**Commit:** `git commit -m "TASK-7: add trend filter to swing trader — reject falling knives"`

---

## TASK-8: Volatility-Adjusted Position Sizing

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (function `_execute_trade` at line ~1841)
- New file: `src/beavr/core/sizing.py`

**Changes:**

1. Create `src/beavr/core/sizing.py`:
   ```python
   """Position sizing based on volatility and risk budget."""
   from __future__ import annotations

   from decimal import Decimal


   def calculate_position_size(
       portfolio_value: Decimal,
       stop_distance_pct: float,
       max_risk_per_trade: float = 0.02,
       min_position_pct: float = 0.05,
       max_position_pct: float = 0.20,
   ) -> Decimal:
       """Calculate position size so max loss = risk_pct of portfolio.

       Volatile stocks (wide stop) get SMALLER positions.
       Tight-stop setups get LARGER positions.

       Args:
           portfolio_value: Total portfolio value.
           stop_distance_pct: Stop loss distance as percentage (e.g., 5.0 for 5%).
           max_risk_per_trade: Max portfolio risk per trade (default 2%).
           min_position_pct: Minimum position as % of portfolio.
           max_position_pct: Maximum position as % of portfolio.

       Returns:
           Dollar amount to invest in this position.
       """
       if stop_distance_pct <= 0:
           stop_distance_pct = 5.0  # Default 5% stop

       risk_amount = portfolio_value * Decimal(str(max_risk_per_trade))
       raw_size = risk_amount / Decimal(str(stop_distance_pct / 100))

       min_size = portfolio_value * Decimal(str(min_position_pct))
       max_size = portfolio_value * Decimal(str(max_position_pct))

       return max(min_size, min(max_size, raw_size))
   ```

2. In `_execute_trade()`, replace the flat `max_position_pct` sizing with:
   ```python
   from beavr.core.sizing import calculate_position_size

   # Replace the existing position sizing block with:
   stop_pct = float(thesis.stop_pct) if thesis.stop_pct > 0 else 5.0
   max_position = calculate_position_size(
       portfolio_value=portfolio_value,
       stop_distance_pct=stop_pct,
       max_risk_per_trade=0.02,
       min_position_pct=0.05,
       max_position_pct=float(self.config.max_position_pct),
   )
   ```

**Tests to write** (`tests/unit/test_sizing.py`):
```python
class TestPositionSizing:
    def test_wider_stop_gets_smaller_position(self):
        pv = Decimal("10000")
        wide = calculate_position_size(pv, stop_distance_pct=12.0)
        narrow = calculate_position_size(pv, stop_distance_pct=4.0)
        assert wide < narrow

    def test_respects_max_position(self):
        result = calculate_position_size(Decimal("10000"), stop_distance_pct=1.0)
        assert result <= Decimal("2000")  # 20% of 10K

    def test_respects_min_position(self):
        result = calculate_position_size(Decimal("10000"), stop_distance_pct=50.0)
        assert result >= Decimal("500")  # 5% of 10K

    def test_handles_zero_stop(self):
        result = calculate_position_size(Decimal("10000"), stop_distance_pct=0)
        assert result > 0
```

**Validation:**
```bash
pytest tests/unit/test_sizing.py -v
pytest tests/unit/ -v
ruff check src/beavr/core/sizing.py src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-8: volatility-adjusted position sizing — wide stop = smaller position"`

---

## TASK-9: Nightly Position Review Pass (Depends on TASK-3)

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (add `_nightly_position_review` method, call from overnight DD cycle)

**Changes:**

1. Add `_nightly_position_review()` method to `V2AutonomousOrchestrator`:

   ```python
   def _nightly_position_review(self) -> None:
       """Review all held positions against their theses.

       Runs during OVERNIGHT_DD phase. Deterministic checks first,
       then LLM escalation for ambiguous cases.

       Queues exits for:
       - Positions past max_hold_date (immediate)
       - Positions where thesis invalidation conditions triggered
       - Positions where catalyst date passed without expected move
       """
       if not self._broker or not self.thesis_repo:
           return

       logger.info("=" * 60)
       logger.info("🌙 NIGHTLY POSITION REVIEW")
       logger.info("=" * 60)

       positions = self._broker.get_positions()
       if not positions:
           logger.info("No positions to review")
           return

       today = date.today()
       exit_queue: list[tuple[str, str]] = []  # (symbol, reason)

       for pos in positions:
           symbol = pos.symbol

           # Find active thesis
           try:
               theses = self.thesis_repo.get_by_symbol(symbol)
               thesis = next(
                   (t for t in theses if t.status in {ThesisStatus.EXECUTED, ThesisStatus.ACTIVE}),
                   None,
               )
           except Exception:
               thesis = None

           if not thesis:
               logger.warning(f"  ⚠️ {symbol}: No active thesis found (orphaned position)")
               continue

           # Check 1: Past max_hold_date
           if thesis.max_hold_date and today > thesis.max_hold_date:
               days_over = (today - thesis.max_hold_date).days
               exit_queue.append((symbol, f"past max_hold_date by {days_over} days"))
               continue

           # Check 2: Past expected_exit_date by more than 5 days
           if thesis.expected_exit_date and today > thesis.expected_exit_date + timedelta(days=5):
               exit_queue.append((symbol, f"past expected_exit_date by {(today - thesis.expected_exit_date).days} days"))
               continue

           # Check 3: Catalyst date passed (if specified and in the past)
           if thesis.catalyst_date and today > thesis.catalyst_date + timedelta(days=3):
               cost_basis = pos.avg_cost * pos.qty
               pnl_pct = float(pos.unrealized_pl / cost_basis * 100) if cost_basis > 0 else 0.0
               if pnl_pct < -2.0:
                   exit_queue.append((symbol, f"catalyst passed {thesis.catalyst_date}, position at {pnl_pct:.1f}%"))
                   continue

           logger.info(f"  ✅ {symbol}: Thesis intact")

       # Log results
       if exit_queue:
           logger.info(f"\n🚨 {len(exit_queue)} positions flagged for exit:")
           for sym, reason in exit_queue:
               logger.info(f"  ❌ {sym}: {reason}")
               self._log_decision(
                   decision_type="nightly_review_exit",
                   action="queue_exit",
                   symbol=sym,
                   reasoning=reason,
               )
       else:
           logger.info("\n✅ All positions pass nightly review")

       self._save_state()
   ```

2. Call from `_run_overnight_dd_cycle()` BEFORE the DD cycle:
   ```python
   def _run_overnight_dd_cycle(self) -> None:
       # Step 0: Nightly position review
       self._nightly_position_review()

       # Step 1: Earnings calendar scan
       self._scan_earnings_calendar()
       # ... rest of existing code ...
   ```

**Tests to write** (`tests/unit/test_nightly_review.py`):
```python
class TestNightlyPositionReview:
    def test_flags_position_past_max_hold(self):
        """Position past max_hold_date is flagged for exit."""

    def test_flags_position_past_expected_exit(self):
        """Position 5+ days past expected_exit_date is flagged."""

    def test_keeps_position_with_valid_thesis(self):
        """Position with valid, non-expired thesis is kept."""

    def test_flags_failed_catalyst_with_loss(self):
        """Position with passed catalyst and negative P/L is flagged."""

    def test_handles_missing_thesis(self):
        """Orphaned position (no thesis) logs warning but doesn't crash."""
```

**Validation:**
```bash
pytest tests/unit/test_nightly_review.py -v
pytest tests/unit/ -v
ruff check src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-9: add nightly position review — flag stale/invalidated positions for exit"`

---

## TASK-10: Trailing Stop Logic (Depends on TASK-4)

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (function `_monitor_positions` at line ~1957)

**Changes:**

1. Add trailing stop tracking to `SystemState`:
   ```python
   # In SystemState class, add:
   trailing_stops: dict[str, float] = Field(
       default_factory=dict,
       description="Symbol -> highest price seen (for trailing stop calculation)"
   )
   ```

2. In `_monitor_positions()`, add trailing stop logic AFTER existing checks but BEFORE the debug log:
   ```python
   # Trailing stop: ratchet up as price advances
   if pnl_pct > 3.0:  # Only activate after +3%
       current_price_float = float(pos.market_value / pos.qty) if pos.qty > 0 else 0.0
       highest = self.state.trailing_stops.get(symbol, current_price_float)

       if current_price_float > highest:
           self.state.trailing_stops[symbol] = current_price_float
           highest = current_price_float

       # Trail at 4% below highest price seen
       trail_stop_price = highest * 0.96
       if current_price_float < trail_stop_price and pnl_pct > 0:
           logger.info(
               f"📉 TRAILING STOP: {symbol} dropped below trail "
               f"(${current_price_float:.2f} < ${trail_stop_price:.2f})"
           )
           self._close_position(symbol, "trailing_stop", pnl_pct)
           self.state.trailing_stops.pop(symbol, None)
           continue
   ```

3. In `_close_position()`, clean up trailing stop state:
   ```python
   # After removing from active lists:
   self.state.trailing_stops.pop(symbol, None)
   ```

**Tests to write** (`tests/unit/test_trailing_stops.py`):
```python
class TestTrailingStops:
    def test_trailing_stop_activates_after_3pct_gain(self):
        """Trailing stop only activates when position is up > 3%."""

    def test_trailing_stop_ratchets_up(self):
        """Highest price tracked is updated, never ratcheted down."""

    def test_trailing_stop_exits_on_4pct_drop(self):
        """Position exits when price drops 4% from highest seen."""

    def test_trailing_stop_cleans_up_on_exit(self):
        """Trailing stop state is removed when position closes."""
```

**Validation:**
```bash
pytest tests/unit/test_trailing_stops.py -v
pytest tests/unit/ -v
ruff check src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-10: add trailing stop logic — ratchet up after +3%, trail at 4% below peak"`

---

## TASK-11: Regime-Based Exposure Scaling (Depends on TASK-5)

**Files to modify:**
- `src/beavr/orchestrator/v2_engine.py` (functions `_execute_swing_trades`, `_execute_power_hour`, and `V2Config`)

**Changes:**

1. Add regime scaling config to `V2Config`:
   ```python
   # Regime-based position limits
   regime_max_positions: dict[str, int] = Field(default_factory=lambda: {
       "bull": 8,
       "sideways": 5,
       "bear": 2,
       "volatile": 3,
   })
   regime_size_multiplier: dict[str, float] = Field(default_factory=lambda: {
       "bull": 1.0,
       "sideways": 0.7,
       "bear": 0.4,
       "volatile": 0.3,
   })
   ```

2. Add a helper method:
   ```python
   def _get_regime_adjusted_limits(self) -> tuple[int, float]:
       """Get position limit and size multiplier for current market regime."""
       # Get latest regime from market analyst (if available)
       regime = "sideways"  # Default
       if hasattr(self, '_last_regime') and self._last_regime:
           regime = self._last_regime

       max_pos = self.config.regime_max_positions.get(
           regime, self.config.max_open_positions
       )
       multiplier = self.config.regime_size_multiplier.get(regime, 1.0)
       return max_pos, multiplier
   ```

3. In `_execute_swing_trades()` and `_execute_power_hour()`, replace the static position cap with regime-aware one:
   ```python
   max_positions, size_multiplier = self._get_regime_adjusted_limits()
   current_positions = self._broker.get_positions() if self._broker else []
   if len(current_positions) >= max_positions:
       logger.info(
           f"Regime '{regime}' position cap reached "
           f"({len(current_positions)}/{max_positions})"
       )
       return
   ```

**Tests to write** (`tests/unit/test_regime_scaling.py`):
```python
class TestRegimeScaling:
    def test_bear_regime_limits_positions(self):
        """Bear regime allows max 2 positions."""

    def test_bull_regime_allows_full_positions(self):
        """Bull regime allows max 8 positions."""

    def test_size_multiplier_reduces_in_volatility(self):
        """Volatile regime reduces position size to 30%."""
```

**Validation:**
```bash
pytest tests/unit/test_regime_scaling.py -v
pytest tests/unit/ -v
ruff check src/beavr/orchestrator/v2_engine.py
```

**Commit:** `git commit -m "TASK-11: regime-based exposure scaling — fewer/smaller positions in bear/volatile"`

---

## TASK-12: Market Briefing System (New Feature)

**New files to create:**
- `src/beavr/agents/market_briefing.py`
- `src/beavr/messaging/commands/briefing.py`
- `tests/unit/test_market_briefing.py`

**Files to modify:**
- `src/beavr/cli/ai.py` (add `bvr ai brief` command and register briefing command handler)
- `src/beavr/messaging/api.py` (add `get_market_brief` to protocol)
- `src/beavr/messaging/api_impl.py` (implement `get_market_brief`)

**Changes:**

1. Create `src/beavr/agents/market_briefing.py`:
   ```python
   """Market Briefing Agent — generates on-demand market outlook."""
   from __future__ import annotations

   import logging
   from datetime import date, datetime
   from decimal import Decimal
   from typing import ClassVar, Optional

   from pydantic import BaseModel, Field

   from beavr.agents.base import AgentContext, AgentProposal, BaseAgent

   logger = logging.getLogger(__name__)

   SECTOR_ETFS = ["XLE", "XLK", "XLF", "XLV", "XLI", "XLU", "XLP", "XLY", "XLC", "XLRE"]
   INDEX_SYMBOLS = ["SPY", "QQQ"]


   class IndexSnapshot(BaseModel):
       symbol: str
       price: float
       change_pct: float
       rsi: float
       above_sma20: bool
       above_sma50: bool
       signal: str = Field(description="bullish, bearish, or neutral")


   class SectorPerformance(BaseModel):
       name: str
       etf: str
       change_pct: float


   class MarketBrief(BaseModel):
       """Structured market briefing."""
       generated_at: datetime = Field(default_factory=datetime.now)
       regime: str = Field(description="bull, bear, sideways, or volatile")
       regime_confidence: float = Field(ge=0.0, le=1.0)
       risk_posture: str = Field(description="aggressive, moderate, cautious, or defensive")
       indices: list[IndexSnapshot] = Field(description="Key index data")
       leading_sectors: list[str] = Field(description="Top performing sectors")
       lagging_sectors: list[str] = Field(description="Worst performing sectors")
       rotation_theme: str = Field(description="1-sentence sector rotation summary")
       portfolio_summary: str = Field(description="2-3 sentence portfolio context")
       portfolio_warnings: list[str] = Field(description="Specific portfolio risks")
       key_takeaways: list[str] = Field(description="3-5 actionable bullet points")
       watch_list: list[str] = Field(description="Symbols to monitor")
       raw_summary: str = Field(description="Full narrative summary (3-5 paragraphs)")


   class MarketBriefingAgent(BaseAgent):
       """Generates on-demand market briefing with outlook."""

       name: ClassVar[str] = "Market Briefing"
       role: ClassVar[str] = "analyst"
       description: ClassVar[str] = "On-demand market outlook and portfolio briefing"
       version: ClassVar[str] = "1.0.0"

       def get_system_prompt(self) -> str:
           return """You are a senior market strategist providing a comprehensive briefing.

   Your briefing should cover:
   1. MARKET REGIME: Classify as bull/bear/sideways/volatile with confidence
   2. INDEX ANALYSIS: SPY/QQQ trend, momentum, key levels
   3. SECTOR ROTATION: Which sectors are leading/lagging and why
   4. PORTFOLIO CONTEXT: How current holdings relate to market conditions
   5. ACTIONABLE OUTLOOK: 3-5 specific, actionable recommendations

   Be direct and decisive. This is a trading desk briefing, not academic analysis.
   Focus on what matters for trading decisions TODAY and THIS WEEK."""

       def generate_brief(self, ctx: AgentContext, portfolio_info: str = "") -> MarketBrief:
           """Generate a market brief from current context."""
           user_prompt = self._build_brief_prompt(ctx, portfolio_info)

           brief: MarketBrief = self.llm.reason(
               system_prompt=self.get_system_prompt(),
               user_prompt=user_prompt,
               output_schema=MarketBrief,
           )
           return brief

       def _build_brief_prompt(self, ctx: AgentContext, portfolio_info: str) -> str:
           index_text = []
           sector_text = []

           for symbol, inds in ctx.indicators.items():
               if symbol in ("SPY", "QQQ"):
                   index_text.append(
                       f"{symbol}: ${inds.get('current_price', 0):.2f}, "
                       f"RSI={inds.get('rsi_14', 0):.1f}, "
                       f"vs SMA20={inds.get('price_vs_sma20', 0):+.1f}%, "
                       f"vs SMA50={inds.get('price_vs_sma50', 0):+.1f}%, "
                       f"5d={inds.get('change_5d', 0):+.1f}%"
                   )
               elif symbol.startswith("XL") or symbol == "XLRE":
                   sector_text.append(
                       f"{symbol}: 5d={inds.get('change_5d', 0):+.1f}%, "
                       f"RSI={inds.get('rsi_14', 0):.1f}"
                   )

           return f"""Generate a market briefing for {ctx.current_date}.

   INDEX DATA:
   {chr(10).join(index_text) if index_text else "No index data available"}

   SECTOR ETFs:
   {chr(10).join(sector_text) if sector_text else "No sector data available"}

   PORTFOLIO:
   {portfolio_info or "No portfolio data available"}

   Cash: ${ctx.cash:,.2f}
   Portfolio Value: ${ctx.portfolio_value:,.2f}
   Drawdown: {ctx.current_drawdown:.1%}
   """

       def analyze(self, ctx: AgentContext) -> AgentProposal:
           """Required by BaseAgent but briefing uses generate_brief() instead."""
           return AgentProposal(
               agent_name=self.name,
               timestamp=datetime.now(),
               signals=[],
               conviction=0.0,
               rationale="Use generate_brief() for market briefing",
               risk_score=0.0,
               risk_factors=[],
               model_version=self.version,
           )
   ```

2. Create `src/beavr/messaging/commands/briefing.py`:
   ```python
   """Briefing command handler: /brief."""
   from __future__ import annotations

   import logging
   from typing import TYPE_CHECKING, Optional

   from beavr.messaging.commands.base import BaseCommandHandler
   from beavr.models.messaging import CommandResult, InboundCommand

   if TYPE_CHECKING:
       from beavr.messaging.api import BeavrAPI

   logger = logging.getLogger(__name__)


   class BriefingCommandHandler(BaseCommandHandler):
       """Handles /brief — generate on-demand market briefing."""

       command_names: list[str] = ["brief", "briefing", "market"]
       tier: str = "analysis"
       description: str = "Get an on-demand market briefing with outlook"

       def __init__(self, api: Optional[BeavrAPI] = None) -> None:
           self._api = api

       async def handle(self, command: InboundCommand) -> CommandResult:
           if not self._api:
               return CommandResult(success=False, message="❌ System not connected.")

           try:
               brief = self._api.get_market_brief()
               if not brief:
                   return CommandResult(
                       success=False,
                       message="❌ Could not generate market brief. Try again later.",
                   )

               # Format for Telegram (max 4096 chars)
               lines = [
                   f"📊 BEAVR MARKET BRIEF — {brief.generated_at.strftime('%b %d, %Y')}",
                   f"{'━' * 30}",
                   f"",
                   f"🏛️ Regime: {brief.regime.upper()} ({brief.regime_confidence:.0%} confidence)",
                   f"Risk Posture: {brief.risk_posture}",
                   f"",
               ]

               if brief.leading_sectors:
                   lines.append(f"📈 Leading: {', '.join(brief.leading_sectors[:3])}")
               if brief.lagging_sectors:
                   lines.append(f"📉 Lagging: {', '.join(brief.lagging_sectors[:3])}")
               if brief.rotation_theme:
                   lines.append(f"🔄 {brief.rotation_theme}")

               lines.append("")

               if brief.portfolio_warnings:
                   lines.append("⚠️ Portfolio Warnings:")
                   for w in brief.portfolio_warnings[:3]:
                       lines.append(f"  • {w}")
                   lines.append("")

               if brief.key_takeaways:
                   lines.append("🎯 Key Takeaways:")
                   for t in brief.key_takeaways[:5]:
                       lines.append(f"  • {t}")

               msg = "\n".join(lines)
               # Telegram limit
               if len(msg) > 4000:
                   msg = msg[:3997] + "..."

               return CommandResult(success=True, message=msg)

           except Exception as e:
               logger.exception("Error generating market brief")
               return CommandResult(success=False, message=f"❌ Brief failed: {e}")
   ```

3. Add `get_market_brief` to BeavrAPI protocol in `src/beavr/messaging/api.py`:
   ```python
   def get_market_brief(self) -> Optional[Any]:
       """Generate an on-demand market briefing."""
       ...
   ```

4. Implement in `src/beavr/messaging/api_impl.py` (delegate to the agent).

5. Add CLI command in `src/beavr/cli/ai.py`:
   ```python
   @ai_app.command()
   def brief() -> None:
       """Get a market briefing with outlook and portfolio context."""
       investor = get_investor()
       # ... build context, call agent, render with Rich panels ...
   ```

6. Register `BriefingCommandHandler` in the router setup (around line ~2268):
   ```python
   from beavr.messaging.commands.briefing import BriefingCommandHandler
   cmd_router.register(BriefingCommandHandler(api=api))
   ```

**Tests to write** (`tests/unit/test_market_briefing.py`):
```python
class TestMarketBrief:
    def test_brief_model_validates(self):
        """MarketBrief Pydantic model validates correctly."""

    def test_briefing_agent_builds_prompt(self):
        """Agent builds prompt with index and sector data."""

    def test_briefing_command_handler_formats_output(self):
        """Telegram command formats brief within 4096 char limit."""

    def test_brief_handles_no_data(self):
        """Brief handles case when no market data is available."""
```

**Validation:**
```bash
pytest tests/unit/test_market_briefing.py -v
pytest tests/unit/ -v
ruff check src/beavr/agents/market_briefing.py src/beavr/messaging/commands/briefing.py src/beavr/cli/ai.py
```

**Commit:** `git commit -m "TASK-12: add market briefing system — CLI, Telegram, and API"`

---

## Final Validation (Run After All Tasks)

```bash
# Full test suite
pytest tests/unit/ -v

# Lint everything
ruff check src/

# Check for type hint completeness
grep -rn "def .*[^)]$" src/beavr/core/ src/beavr/agents/market_briefing.py | grep -v "->.*:" | head -10

# Verify all commits
git log --oneline -15

# Integration smoke test (uses .env for Alpaca paper trading)
source .env 2>/dev/null
bvr ai analyze --amount 1000
bvr ai brief
bvr ai status
```

---

## Copilot CLI Execution Instructions

To run this plan with `/fleet`:

```
Shift+Tab  (enter plan mode)

Read docs/FLEET_IMPLEMENTATION_PLAN.md and implement ALL 12 tasks.

Use /fleet to parallelize TASK-1 through TASK-8 (they are independent).
Then run TASK-9 through TASK-11 (they have dependencies).
Finally run TASK-12.

For each task:
1. Read the task specification carefully
2. Make the code changes described
3. Write the tests specified
4. Run: pytest tests/unit/ -v && ruff check src/
5. If tests pass: git add -A && git commit -m "<task-id>: <description>"
6. If tests fail: fix the issue and re-run tests

Use the .env file for any integration testing against Alpaca paper broker.
Follow all conventions in .github/copilot-instructions.md:
- Decimal for money (NEVER float)
- Complete type hints on every function
- Pydantic BaseModel for domain objects

Accept plan and build on autopilot + /fleet
```
