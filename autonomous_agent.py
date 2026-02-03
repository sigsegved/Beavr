#!/usr/bin/env python3.11
"""
AUTONOMOUS AI TRADING AGENT
===========================

A fully autonomous trading agent that:
- Monitors the market continuously during trading hours
- Makes its own buy/sell decisions based on AI analysis
- Works towards configurable goals (profit targets, risk limits)
- Trades independently without human intervention
- Logs all decisions for monitoring

Uses GitHub Copilot SDK for LLM inference - no API key needed!
Just needs your Copilot CLI to be authenticated.

Usage:
    python3.11 autonomous_agent.py           # Start the autonomous agent
    python3.11 autonomous_agent.py --test    # Test run (analyze but don't trade)

The agent will:
1. Wait for market open (or start immediately if market is open)
2. Scan for opportunities every 15-30 minutes
3. Execute trades when it finds good setups
4. Monitor positions and take profits / cut losses
5. Log everything to logs/autonomous/
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AgentGoals:
    """Trading goals for the autonomous agent."""
    
    # Daily targets
    daily_profit_target_pct: float = 2.0      # Target 2% daily profit
    daily_max_loss_pct: float = 3.0           # Stop trading at 3% loss
    
    # Position management
    take_profit_pct: float = 5.0              # Take profit at 5% gain
    stop_loss_pct: float = 3.0                # Cut loss at 3% loss
    trailing_stop_pct: float = 2.0            # Trailing stop at 2%
    
    # Risk limits
    max_position_pct: float = 15.0            # Max 15% in single position
    max_positions: int = 5                     # Max 5 concurrent positions
    min_cash_pct: float = 20.0                # Keep 20% cash minimum
    
    # Trading frequency
    scan_interval_minutes: int = 15           # Scan every 15 minutes
    min_hold_minutes: int = 30                # Hold positions at least 30 min


@dataclass
class AgentState:
    """Tracks the agent's runtime state."""
    
    start_time: datetime = field(default_factory=datetime.now)
    starting_portfolio_value: Decimal = Decimal("0")
    peak_portfolio_value: Decimal = Decimal("0")
    
    # Daily tracking
    trades_today: int = 0
    profit_today: Decimal = Decimal("0")
    
    # Position tracking
    position_entry_prices: Dict[str, Decimal] = field(default_factory=dict)
    position_entry_times: Dict[str, datetime] = field(default_factory=dict)
    position_high_prices: Dict[str, Decimal] = field(default_factory=dict)
    
    # Status
    is_running: bool = True
    last_scan_time: Optional[datetime] = None
    last_trade_time: Optional[datetime] = None


# =============================================================================
# LOGGING SETUP
# =============================================================================

LOG_DIR = Path("logs/autonomous")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Create detailed log file with timestamp
log_file = LOG_DIR / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file),
    ],
)

# Reduce noise
for lib in ["httpx", "httpcore", "openai", "urllib3"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger("autonomous_agent")


# =============================================================================
# AUTONOMOUS AGENT
# =============================================================================

class AutonomousAgent:
    """
    Fully autonomous AI trading agent.
    
    This agent operates independently, making all trading decisions
    based on market analysis and working towards configured goals.
    """
    
    def __init__(self, goals: AgentGoals, test_mode: bool = False):
        """Initialize the autonomous agent."""
        self.goals = goals
        self.test_mode = test_mode
        self.state = AgentState()
        
        # Check environment
        self._check_env()
        
        # Initialize clients
        self._init_clients()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        logger.info("=" * 60)
        logger.info("🤖 AUTONOMOUS AI TRADING AGENT INITIALIZED")
        logger.info("=" * 60)
        logger.info(f"Mode: {'TEST (no real trades)' if test_mode else 'LIVE PAPER TRADING'}")
        logger.info(f"Goals: {goals.daily_profit_target_pct}% daily target, {goals.daily_max_loss_pct}% max loss")
        logger.info(f"Log file: {log_file}")
        logger.info("=" * 60)
    
    def _check_env(self):
        """Verify required environment variables."""
        # Only Alpaca credentials required - LLM uses GitHub Copilot SDK (no API key needed!)
        required = ["ALPACA_API_KEY", "ALPACA_API_SECRET"]
        missing = [k for k in required if not os.environ.get(k) or os.environ.get(k, "").startswith("your_")]
        
        if missing:
            logger.error(f"Missing environment variables: {missing}")
            logger.error("Please set these in your .env file")
            sys.exit(1)
    
    def _init_clients(self):
        """Initialize all required clients."""
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.data.historical.stock import StockHistoricalDataClient
        
        from beavr.llm.client import LLMClient, LLMConfig
        from beavr.data.screener import MarketScreener, NewsScanner
        from beavr.data.alpaca import AlpacaDataFetcher
        from beavr.db.cache import BarCache
        from beavr.db.connection import Database
        
        api_key = os.environ["ALPACA_API_KEY"]
        api_secret = os.environ["ALPACA_API_SECRET"]
        
        # Trading client
        self.trading = TradingClient(api_key, api_secret, paper=True)
        self.OrderSide = OrderSide
        self.TimeInForce = TimeInForce
        self.MarketOrderRequest = MarketOrderRequest
        
        # Data clients
        self.data_client = StockHistoricalDataClient(api_key, api_secret)
        self.screener = MarketScreener(api_key, api_secret)
        self.news_scanner = NewsScanner(api_key, api_secret)
        
        # Data fetcher with cache
        db = Database()
        cache = BarCache(db)
        self.data_fetcher = AlpacaDataFetcher(api_key, api_secret, cache=cache)
        
        # LLM client (uses GitHub Copilot SDK - no API key needed!)
        self.llm = LLMClient(
            LLMConfig(model="gpt-4.1", temperature=0.3)
        )
        
        logger.info("All clients initialized successfully")
    
    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        logger.info("\n⚠️  Shutdown signal received...")
        self.state.is_running = False
    
    # =========================================================================
    # MARKET STATUS
    # =========================================================================
    
    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        clock = self.trading.get_clock()
        return clock.is_open
    
    def get_time_to_open(self) -> timedelta:
        """Get time until market opens."""
        clock = self.trading.get_clock()
        if clock.is_open:
            return timedelta(0)
        return clock.next_open - datetime.now(clock.next_open.tzinfo)
    
    def get_time_to_close(self) -> timedelta:
        """Get time until market closes."""
        clock = self.trading.get_clock()
        if not clock.is_open:
            return timedelta(0)
        return clock.next_close - datetime.now(clock.next_close.tzinfo)
    
    # =========================================================================
    # ACCOUNT & POSITIONS
    # =========================================================================
    
    def get_account_state(self) -> Dict[str, Any]:
        """Get current account state."""
        account = self.trading.get_account()
        positions = self.trading.get_all_positions()
        
        return {
            "cash": Decimal(account.cash),
            "portfolio_value": Decimal(account.portfolio_value),
            "buying_power": Decimal(account.buying_power),
            "positions": {p.symbol: {
                "qty": Decimal(p.qty),
                "market_value": Decimal(p.market_value),
                "avg_entry": Decimal(p.avg_entry_price),
                "current_price": Decimal(p.current_price),
                "unrealized_pl": Decimal(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
            } for p in positions}
        }
    
    def get_daily_pnl(self) -> tuple[Decimal, float]:
        """Calculate today's P&L."""
        account = self.get_account_state()
        current_value = account["portfolio_value"]
        
        if self.state.starting_portfolio_value == 0:
            self.state.starting_portfolio_value = current_value
            self.state.peak_portfolio_value = current_value
        
        # Update peak
        if current_value > self.state.peak_portfolio_value:
            self.state.peak_portfolio_value = current_value
        
        pnl = current_value - self.state.starting_portfolio_value
        pnl_pct = float(pnl / self.state.starting_portfolio_value * 100) if self.state.starting_portfolio_value else 0
        
        return pnl, pnl_pct
    
    # =========================================================================
    # TRADING DECISIONS
    # =========================================================================
    
    def analyze_market(self) -> Dict[str, Any]:
        """Run full market analysis using AI agents."""
        from beavr.agents.symbol_selector import SymbolSelectorAgent
        from beavr.agents.market_analyst import MarketAnalystAgent
        from beavr.agents.swing_trader import SwingTraderAgent
        from beavr.agents.base import AgentContext
        from beavr.agents.indicators import build_agent_context_indicators, bars_to_dict_list
        from beavr.orchestrator.engine import OrchestratorEngine
        
        logger.info("🔍 Starting market analysis...")
        
        account = self.get_account_state()
        
        # Calculate drawdown
        pnl, pnl_pct = self.get_daily_pnl()
        current_drawdown = max(0, -pnl_pct / 100)
        
        # Step 1: Symbol Selection
        logger.info("  📊 AI selecting symbols...")
        
        selection_ctx = AgentContext(
            current_date=date.today(),
            timestamp=datetime.now(),
            prices={},
            bars={},
            indicators={},
            cash=account["cash"],
            positions={s: p["qty"] for s, p in account["positions"].items()},
            portfolio_value=account["portfolio_value"],
            current_drawdown=current_drawdown,
            peak_value=self.state.peak_portfolio_value,
            risk_budget=1.0,
        )
        
        selector = SymbolSelectorAgent(self.llm, self.screener, self.news_scanner)
        selection = selector.analyze(selection_ctx)
        
        symbols = selection.extra.get("selected_symbols", ["SPY", "QQQ"])
        market_theme = selection.extra.get("market_theme", "unknown")
        risk_level = selection.extra.get("risk_assessment", "medium")
        
        logger.info(f"  Selected: {symbols}")
        logger.info(f"  Theme: {market_theme}, Risk: {risk_level}")
        
        # Step 2: Fetch data
        logger.info("  📈 Fetching market data...")
        
        today = date.today()
        start_date = today - timedelta(days=60)
        
        # Fetch bars with error handling for each symbol
        bars = {}
        for symbol in symbols:
            try:
                symbol_bars = self.data_fetcher.get_bars(symbol, start_date, today, "1Day")
                if not symbol_bars.empty:
                    bars[symbol] = symbol_bars
                else:
                    logger.warning(f"  No data for {symbol}")
            except Exception as e:
                logger.warning(f"  Failed to fetch {symbol}: {e}")
        
        if not bars:
            logger.error("  No market data available for any symbol")
            return {"symbols": [], "signals": [], "prices": {}, "account": account}
        
        prices = {}
        for symbol, df in bars.items():
            if not df.empty:
                prices[symbol] = Decimal(str(df["close"].iloc[-1]))
        
        # Step 3: Run analysis
        logger.info("  🧠 AI analyzing opportunities...")
        
        indicators = build_agent_context_indicators(bars)
        bars_dict = {s: bars_to_dict_list(b, 20) for s, b in bars.items()}
        
        ctx = AgentContext(
            current_date=today,
            timestamp=datetime.now(),
            prices=prices,
            bars=bars_dict,
            indicators=indicators,
            cash=account["cash"],
            positions={s: p["qty"] for s, p in account["positions"].items()},
            portfolio_value=account["portfolio_value"],
            current_drawdown=current_drawdown,
            peak_value=self.state.peak_portfolio_value,
            risk_budget=1.0 if risk_level == "low" else 0.7 if risk_level == "medium" else 0.4,
        )
        
        market_analyst = MarketAnalystAgent(self.llm)
        swing_trader = SwingTraderAgent(self.llm)
        
        orchestrator = OrchestratorEngine(
            market_analyst=market_analyst,
            trading_agents=[swing_trader],
            max_position_pct=self.goals.max_position_pct / 100,
            min_cash_pct=self.goals.min_cash_pct / 100,
        )
        
        signals = orchestrator.run_daily_cycle(ctx)
        
        return {
            "symbols": symbols,
            "market_theme": market_theme,
            "risk_level": risk_level,
            "signals": signals,
            "prices": prices,
            "account": account,
        }
    
    def check_position_exits(self) -> List[Dict[str, Any]]:
        """Check if any positions should be exited."""
        exits = []
        account = self.get_account_state()
        
        for symbol, pos in account["positions"].items():
            entry_price = self.state.position_entry_prices.get(symbol, pos["avg_entry"])
            current_price = pos["current_price"]
            pnl_pct = float((current_price - entry_price) / entry_price * 100)
            
            # Update high water mark for trailing stop
            if symbol not in self.state.position_high_prices:
                self.state.position_high_prices[symbol] = current_price
            elif current_price > self.state.position_high_prices[symbol]:
                self.state.position_high_prices[symbol] = current_price
            
            high_price = self.state.position_high_prices[symbol]
            drawdown_from_high = float((high_price - current_price) / high_price * 100)
            
            reason = None
            
            # Check take profit
            if pnl_pct >= self.goals.take_profit_pct:
                reason = f"TAKE PROFIT: +{pnl_pct:.1f}% >= {self.goals.take_profit_pct}%"
            
            # Check stop loss
            elif pnl_pct <= -self.goals.stop_loss_pct:
                reason = f"STOP LOSS: {pnl_pct:.1f}% <= -{self.goals.stop_loss_pct}%"
            
            # Check trailing stop (only if in profit)
            elif pnl_pct > 0 and drawdown_from_high >= self.goals.trailing_stop_pct:
                reason = f"TRAILING STOP: {drawdown_from_high:.1f}% from high"
            
            if reason:
                exits.append({
                    "symbol": symbol,
                    "qty": pos["qty"],
                    "reason": reason,
                    "pnl_pct": pnl_pct,
                })
        
        return exits
    
    # =========================================================================
    # TRADE EXECUTION
    # =========================================================================
    
    def execute_buy(self, symbol: str, amount: Decimal, reason: str) -> bool:
        """Execute a buy order."""
        if self.test_mode:
            logger.info(f"  [TEST] Would BUY ${amount:.2f} of {symbol}: {reason}")
            return True
        
        try:
            # Get current price
            account = self.get_account_state()
            
            # Check if we have enough cash
            min_cash = account["portfolio_value"] * Decimal(str(self.goals.min_cash_pct / 100))
            available = account["cash"] - min_cash
            
            if amount > available:
                logger.warning(f"  Reducing {symbol} buy from ${amount:.2f} to ${available:.2f} (cash limit)")
                amount = available
            
            if amount < Decimal("10"):
                logger.warning(f"  Skipping {symbol} buy - amount too small: ${amount:.2f}")
                return False
            
            # Get price and calculate quantity
            bars = self.data_fetcher.get_bars(symbol, date.today() - timedelta(days=5), date.today())
            if bars.empty:
                logger.error(f"  Cannot get price for {symbol}")
                return False
            
            price = Decimal(str(bars["close"].iloc[-1]))
            qty = float(amount / price)
            qty = round(qty, 4)
            
            if qty < 0.001:
                logger.warning(f"  Skipping {symbol} buy - quantity too small")
                return False
            
            # Execute
            order = self.trading.submit_order(
                self.MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=self.OrderSide.BUY,
                    time_in_force=self.TimeInForce.DAY,
                )
            )
            
            # Track position
            self.state.position_entry_prices[symbol] = price
            self.state.position_entry_times[symbol] = datetime.now()
            self.state.trades_today += 1
            self.state.last_trade_time = datetime.now()
            
            logger.info(f"  ✅ BUY {qty:.4f} {symbol} @ ~${price:.2f} = ${amount:.2f}")
            logger.info(f"     Reason: {reason}")
            
            self._log_trade("BUY", symbol, qty, price, reason)
            return True
            
        except Exception as e:
            logger.error(f"  ❌ BUY failed for {symbol}: {e}")
            return False
    
    def execute_sell(self, symbol: str, qty: Decimal, reason: str) -> bool:
        """Execute a sell order."""
        if self.test_mode:
            logger.info(f"  [TEST] Would SELL {qty} {symbol}: {reason}")
            return True
        
        try:
            order = self.trading.submit_order(
                self.MarketOrderRequest(
                    symbol=symbol,
                    qty=float(qty),
                    side=self.OrderSide.SELL,
                    time_in_force=self.TimeInForce.DAY,
                )
            )
            
            # Clean up tracking
            self.state.position_entry_prices.pop(symbol, None)
            self.state.position_entry_times.pop(symbol, None)
            self.state.position_high_prices.pop(symbol, None)
            self.state.trades_today += 1
            self.state.last_trade_time = datetime.now()
            
            logger.info(f"  ✅ SELL {qty} {symbol}")
            logger.info(f"     Reason: {reason}")
            
            self._log_trade("SELL", symbol, float(qty), None, reason)
            return True
            
        except Exception as e:
            logger.error(f"  ❌ SELL failed for {symbol}: {e}")
            return False
    
    def _log_trade(self, side: str, symbol: str, qty: float, price: Optional[Decimal], reason: str):
        """Log trade to JSON file."""
        trade_log = LOG_DIR / "trades.jsonl"
        
        trade = {
            "timestamp": datetime.now().isoformat(),
            "side": side,
            "symbol": symbol,
            "qty": qty,
            "price": str(price) if price else None,
            "reason": reason,
        }
        
        with open(trade_log, "a") as f:
            f.write(json.dumps(trade) + "\n")
    
    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    def run(self):
        """Main agent loop."""
        logger.info("\n🚀 AUTONOMOUS AGENT STARTING...")
        
        # Get initial account state
        account = self.get_account_state()
        self.state.starting_portfolio_value = account["portfolio_value"]
        self.state.peak_portfolio_value = account["portfolio_value"]
        
        logger.info(f"Starting portfolio value: ${account['portfolio_value']:,.2f}")
        logger.info(f"Starting cash: ${account['cash']:,.2f}")
        logger.info(f"Starting positions: {len(account['positions'])}")
        
        # Initialize position tracking for existing positions
        for symbol, pos in account["positions"].items():
            if symbol not in self.state.position_entry_prices:
                self.state.position_entry_prices[symbol] = pos["avg_entry"]
                self.state.position_entry_times[symbol] = datetime.now()
                self.state.position_high_prices[symbol] = pos["current_price"]
        
        while self.state.is_running:
            try:
                # Check if market is open
                if not self.is_market_open():
                    time_to_open = self.get_time_to_open()
                    
                    if time_to_open.total_seconds() > 0:
                        # If more than 30 minutes to open, sleep longer
                        if time_to_open.total_seconds() > 1800:
                            logger.info(f"⏰ Market opens in {time_to_open}. Sleeping...")
                            time.sleep(min(time_to_open.total_seconds() - 1800, 3600))
                        else:
                            logger.info(f"⏰ Market opens in {time_to_open}. Pre-market analysis...")
                            self._run_cycle()
                            time.sleep(60)
                    continue
                
                # Market is open - run trading cycle
                self._run_cycle()
                
                # Check daily limits
                pnl, pnl_pct = self.get_daily_pnl()
                
                if pnl_pct >= self.goals.daily_profit_target_pct:
                    logger.info(f"🎯 DAILY PROFIT TARGET REACHED: +{pnl_pct:.2f}%")
                    logger.info("Pausing new trades for today...")
                    # Still monitor positions but don't open new ones
                    time.sleep(self.goals.scan_interval_minutes * 60)
                    continue
                
                if pnl_pct <= -self.goals.daily_max_loss_pct:
                    logger.warning(f"🛑 DAILY MAX LOSS REACHED: {pnl_pct:.2f}%")
                    logger.warning("Stopping trading for today...")
                    # Wait until market close
                    time.sleep(self.get_time_to_close().total_seconds())
                    continue
                
                # Sleep until next scan
                logger.info(f"💤 Next scan in {self.goals.scan_interval_minutes} minutes...")
                time.sleep(self.goals.scan_interval_minutes * 60)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(60)
        
        self._shutdown()
    
    def _run_cycle(self):
        """Run one trading cycle."""
        logger.info("\n" + "=" * 50)
        logger.info(f"📍 TRADING CYCLE - {datetime.now().strftime('%H:%M:%S')}")
        logger.info("=" * 50)
        
        # Log current state
        try:
            pnl, pnl_pct = self.get_daily_pnl()
            account = self.get_account_state()
        except Exception as e:
            logger.error(f"Failed to get account state: {e}")
            return
        
        emoji = "🟢" if pnl >= 0 else "🔴"
        logger.info(f"Portfolio: ${account['portfolio_value']:,.2f} ({emoji} ${pnl:,.2f} / {pnl_pct:+.2f}%)")
        logger.info(f"Cash: ${account['cash']:,.2f}")
        logger.info(f"Positions: {len(account['positions'])}")
        
        # Step 1: Check position exits
        logger.info("\n📊 Checking positions for exit signals...")
        try:
            exits = self.check_position_exits()
            
            for exit_signal in exits:
                logger.info(f"  🚨 EXIT SIGNAL: {exit_signal['symbol']} - {exit_signal['reason']}")
                self.execute_sell(exit_signal["symbol"], exit_signal["qty"], exit_signal["reason"])
        except Exception as e:
            logger.error(f"Error checking exits: {e}")
        
        # Step 2: Look for new opportunities (if we have capacity)
        num_positions = len(account["positions"])
        
        if num_positions < self.goals.max_positions:
            logger.info(f"\n🔍 Looking for opportunities (have {num_positions}/{self.goals.max_positions} positions)...")
            
            try:
                analysis = self.analyze_market()
                
                for signal in analysis["signals"]:
                    if signal.action == "buy" and signal.amount:
                        # Check if we already have this position
                        if signal.symbol in account["positions"]:
                            logger.info(f"  Skipping {signal.symbol} - already have position")
                            continue
                        
                        # Check position limit
                        if num_positions >= self.goals.max_positions:
                            logger.info(f"  Skipping {signal.symbol} - at max positions")
                            break
                        
                        # Execute buy
                        if self.execute_buy(signal.symbol, signal.amount, signal.reason):
                            num_positions += 1
                    
                    elif signal.action == "sell" and signal.quantity:
                        self.execute_sell(signal.symbol, signal.quantity, signal.reason)
            except Exception as e:
                logger.error(f"Error analyzing market: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        else:
            logger.info(f"\n⏸️  At max positions ({num_positions}), only monitoring exits")
        
        self.state.last_scan_time = datetime.now()
        
        # Save state
        try:
            self._save_state()
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def _save_state(self):
        """Save current state to file."""
        state_file = LOG_DIR / "state.json"
        
        pnl, pnl_pct = self.get_daily_pnl()
        account = self.get_account_state()
        
        state = {
            "timestamp": datetime.now().isoformat(),
            "portfolio_value": str(account["portfolio_value"]),
            "cash": str(account["cash"]),
            "daily_pnl": str(pnl),
            "daily_pnl_pct": pnl_pct,
            "trades_today": self.state.trades_today,
            "positions": {s: str(p["qty"]) for s, p in account["positions"].items()},
            "is_running": self.state.is_running,
        }
        
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
    
    def _shutdown(self):
        """Graceful shutdown."""
        logger.info("\n" + "=" * 50)
        logger.info("🛑 AUTONOMOUS AGENT SHUTTING DOWN")
        logger.info("=" * 50)
        
        pnl, pnl_pct = self.get_daily_pnl()
        account = self.get_account_state()
        
        logger.info(f"Final portfolio value: ${account['portfolio_value']:,.2f}")
        logger.info(f"Session P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)")
        logger.info(f"Trades executed: {self.state.trades_today}")
        logger.info(f"Log file: {log_file}")
        logger.info("=" * 50)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Autonomous AI Trading Agent")
    parser.add_argument("--test", action="store_true", help="Test mode (analyze but don't trade)")
    parser.add_argument("--profit-target", type=float, default=2.0, help="Daily profit target %%")
    parser.add_argument("--max-loss", type=float, default=3.0, help="Daily max loss %%")
    parser.add_argument("--scan-interval", type=int, default=15, help="Minutes between scans")
    
    args = parser.parse_args()
    
    goals = AgentGoals(
        daily_profit_target_pct=args.profit_target,
        daily_max_loss_pct=args.max_loss,
        scan_interval_minutes=args.scan_interval,
    )
    
    agent = AutonomousAgent(goals, test_mode=args.test)
    agent.run()


if __name__ == "__main__":
    main()
