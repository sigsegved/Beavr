#!/usr/bin/env python
"""
AI Investor - Fully Autonomous Paper Trading

This is the simple way to run AI Investor. Just run it and let the AI decide:
- What symbols to trade (scans market movers, news, etc.)
- When to buy/sell (technical analysis + market regime)
- How much to allocate (risk management)

Usage:
    python ai_investor.py              # Run once
    python ai_investor.py --continuous # Run continuously (daily)
    python ai_investor.py --status     # Check account status only

Requirements:
    - OPENAI_API_KEY in .env
    - ALPACA_API_KEY and ALPACA_API_SECRET in .env
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv()

# Set up logging
LOG_DIR = Path("logs/ai_investor")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "ai_investor.log"),
    ],
)

# Reduce noise from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger("ai_investor")


def check_env(need_openai: bool = True) -> bool:
    """Check required environment variables."""
    required = ["ALPACA_API_KEY", "ALPACA_API_SECRET"]
    if need_openai:
        required.append("OPENAI_API_KEY")
    
    missing = [k for k in required if not os.environ.get(k) or os.environ.get(k, "").startswith("your_")]
    
    if missing:
        print("❌ Missing environment variables:")
        for k in missing:
            print(f"   - {k}")
        print("\nSet these in your .env file:")
        print("   OPENAI_API_KEY=sk-...")
        return False
    return True


def get_alpaca_clients():
    """Initialize Alpaca clients."""
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical.stock import StockHistoricalDataClient
    
    api_key = os.environ["ALPACA_API_KEY"]
    api_secret = os.environ["ALPACA_API_SECRET"]
    
    trading = TradingClient(api_key, api_secret, paper=True)
    data = StockHistoricalDataClient(api_key, api_secret)
    
    return trading, data


def show_status():
    """Show account status."""
    trading, _ = get_alpaca_clients()
    
    account = trading.get_account()
    positions = trading.get_all_positions()
    
    print("\n" + "=" * 50)
    print("💰 ACCOUNT STATUS")
    print("=" * 50)
    print(f"Cash:            ${float(account.cash):>12,.2f}")
    print(f"Portfolio Value: ${float(account.portfolio_value):>12,.2f}")
    print(f"Buying Power:    ${float(account.buying_power):>12,.2f}")
    
    if positions:
        print("\n📊 POSITIONS:")
        total_pl = 0
        for p in positions:
            pl = float(p.unrealized_pl)
            total_pl += pl
            emoji = "🟢" if pl >= 0 else "🔴"
            print(f"   {p.symbol:6} {float(p.qty):>8.2f} @ ${float(p.current_price):>8.2f}  {emoji} ${pl:>+10.2f}")
        print(f"\n   Total P/L: ${total_pl:>+.2f}")
    else:
        print("\n📊 No positions")
    print()


def run_ai_cycle() -> dict:
    """Run one complete AI trading cycle."""
    from beavr.llm.client import LLMClient, LLMConfig
    from beavr.data.screener import MarketScreener, NewsScanner
    from beavr.data.alpaca import AlpacaDataFetcher
    from beavr.db.cache import BarCache
    from beavr.db.connection import Database
    from beavr.agents.symbol_selector import SymbolSelectorAgent
    from beavr.agents.market_analyst import MarketAnalystAgent
    from beavr.agents.swing_trader import SwingTraderAgent
    from beavr.agents.base import AgentContext
    from beavr.agents.indicators import build_agent_context_indicators, bars_to_dict_list
    from beavr.orchestrator.engine import OrchestratorEngine
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    
    api_key = os.environ["ALPACA_API_KEY"]
    api_secret = os.environ["ALPACA_API_SECRET"]
    
    result = {
        "timestamp": datetime.now().isoformat(),
        "symbols": [],
        "signals": [],
        "orders": [],
        "errors": [],
    }
    
    logger.info("=" * 50)
    logger.info("🤖 AI INVESTOR - Starting Analysis")
    logger.info("=" * 50)
    
    # Initialize clients
    trading = TradingClient(api_key, api_secret, paper=True)
    llm = LLMClient(LLMConfig(model="gpt-4.1"))  # Uses GitHub Copilot SDK
    screener = MarketScreener(api_key, api_secret)
    news_scanner = NewsScanner(api_key, api_secret)
    
    db = Database()
    cache = BarCache(db)
    data_fetcher = AlpacaDataFetcher(api_key, api_secret, cache=cache)
    
    # Get account state
    account = trading.get_account()
    positions = {p.symbol: Decimal(p.qty) for p in trading.get_all_positions()}
    cash = Decimal(account.cash)
    portfolio_value = Decimal(account.portfolio_value)
    
    logger.info(f"Account: ${portfolio_value:,.2f} (${cash:,.2f} cash)")
    
    # Calculate drawdown
    peak_value = portfolio_value  # TODO: track actual peak
    current_drawdown = 0.0
    
    # Step 1: Symbol Selection
    logger.info("\n📊 Step 1: AI selecting symbols to analyze...")
    
    # Build minimal context for symbol selection
    selection_ctx = AgentContext(
        current_date=date.today(),
        timestamp=datetime.now(),
        prices={},
        bars={},
        indicators={},
        cash=cash,
        positions=positions,
        portfolio_value=portfolio_value,
        current_drawdown=current_drawdown,
        peak_value=peak_value,
        risk_budget=1.0,
    )
    
    selector = SymbolSelectorAgent(llm, screener, news_scanner)
    selection = selector.analyze(selection_ctx)
    
    selected_symbols = selection.extra.get("selected_symbols", ["SPY", "QQQ", "AAPL"])
    market_theme = selection.extra.get("market_theme", "unknown")
    risk_assessment = selection.extra.get("risk_assessment", "medium")
    
    logger.info(f"Selected: {selected_symbols}")
    logger.info(f"Market theme: {market_theme}")
    logger.info(f"Risk: {risk_assessment}")
    
    result["symbols"] = selected_symbols
    result["market_theme"] = market_theme
    result["risk_assessment"] = risk_assessment
    
    # Step 2: Fetch data for selected symbols
    logger.info("\n📈 Step 2: Fetching market data...")
    
    today = date.today()
    start_date = today - timedelta(days=90)
    
    bars = data_fetcher.get_multi_bars(selected_symbols, start_date, today, "1Day")
    
    prices = {}
    for symbol, df in bars.items():
        if not df.empty:
            prices[symbol] = Decimal(str(df["close"].iloc[-1]))
    
    logger.info(f"Fetched data for {len(bars)} symbols")
    
    # Step 3: Build full context and run analysis
    logger.info("\n🧠 Step 3: AI analyzing market conditions...")
    
    indicators = build_agent_context_indicators(bars)
    bars_dict = {s: bars_to_dict_list(b, 20) for s, b in bars.items()}
    
    ctx = AgentContext(
        current_date=today,
        timestamp=datetime.now(),
        prices=prices,
        bars=bars_dict,
        indicators=indicators,
        cash=cash,
        positions=positions,
        portfolio_value=portfolio_value,
        current_drawdown=current_drawdown,
        peak_value=peak_value,
        risk_budget=1.0,
    )
    
    # Create agents
    market_analyst = MarketAnalystAgent(llm)
    swing_trader = SwingTraderAgent(llm)
    
    # Create orchestrator
    orchestrator = OrchestratorEngine(
        market_analyst=market_analyst,
        trading_agents=[swing_trader],
        max_position_pct=0.10,
        min_cash_pct=0.05,
    )
    
    # Run the orchestrator
    signals = orchestrator.run_daily_cycle(ctx)
    
    logger.info(f"\n📋 Generated {len(signals)} trading signals")
    
    result["signals"] = [
        {
            "symbol": s.symbol,
            "action": s.action,
            "amount": str(s.amount) if s.amount else None,
            "quantity": str(s.quantity) if s.quantity else None,
            "reason": s.reason,
            "confidence": s.confidence,
        }
        for s in signals
    ]
    
    # Step 4: Execute signals
    if signals:
        logger.info("\n💹 Step 4: Executing trades...")
        
        for signal in signals:
            try:
                logger.info(f"Executing: {signal.action.upper()} {signal.symbol}")
                
                if signal.action == "buy" and signal.amount:
                    price = prices.get(signal.symbol)
                    if price:
                        qty = float(signal.amount / price)
                        qty = round(qty, 4)
                        
                        if qty >= 0.001:
                            order = trading.submit_order(
                                MarketOrderRequest(
                                    symbol=signal.symbol,
                                    qty=qty,
                                    side=OrderSide.BUY,
                                    time_in_force=TimeInForce.DAY,
                                )
                            )
                            logger.info(f"  ✅ BUY order submitted: {qty} {signal.symbol}")
                            result["orders"].append({
                                "symbol": signal.symbol,
                                "side": "buy",
                                "qty": qty,
                                "status": "submitted",
                            })
                
                elif signal.action == "sell" and signal.quantity:
                    order = trading.submit_order(
                        MarketOrderRequest(
                            symbol=signal.symbol,
                            qty=float(signal.quantity),
                            side=OrderSide.SELL,
                            time_in_force=TimeInForce.DAY,
                        )
                    )
                    logger.info(f"  ✅ SELL order submitted: {signal.quantity} {signal.symbol}")
                    result["orders"].append({
                        "symbol": signal.symbol,
                        "side": "sell",
                        "qty": float(signal.quantity),
                        "status": "submitted",
                    })
                    
            except Exception as e:
                logger.error(f"  ❌ Order failed: {e}")
                result["errors"].append(str(e))
    else:
        logger.info("\n😴 No trades today - AI decided to hold")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = LOG_DIR / f"cycle_{timestamp}.json"
    with open(result_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    logger.info(f"\n📁 Results saved to: {result_file}")
    logger.info("=" * 50)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="AI Investor - Fully Autonomous Trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--status", action="store_true", help="Show account status only")
    parser.add_argument("--continuous", action="store_true", help="Run continuously (daily)")
    
    args = parser.parse_args()
    
    print("\n🤖 AI INVESTOR")
    print("   Fully autonomous trading powered by AI\n")
    
    if args.status:
        if not check_env(need_openai=False):
            sys.exit(1)
        show_status()
        return
    
    # Full run needs OpenAI
    if not check_env(need_openai=True):
        sys.exit(1)
    
    if args.continuous:
        print("Running in continuous mode (Ctrl+C to stop)\n")
        while True:
            try:
                # Check if market is open
                trading, _ = get_alpaca_clients()
                clock = trading.get_clock()
                
                if clock.is_open:
                    run_ai_cycle()
                    # Sleep until next day
                    logger.info("Sleeping until next trading day...")
                    time.sleep(24 * 60 * 60)
                else:
                    logger.info(f"Market closed. Next open: {clock.next_open}")
                    # Sleep 1 hour and check again
                    time.sleep(60 * 60)
                    
            except KeyboardInterrupt:
                logger.info("Stopped by user")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(60)
    else:
        # Single run
        show_status()
        
        print("Starting AI analysis...\n")
        result = run_ai_cycle()
        
        # Show summary
        print("\n" + "=" * 50)
        print("📋 SUMMARY")
        print("=" * 50)
        print(f"Symbols analyzed: {', '.join(result['symbols'])}")
        print(f"Market theme: {result.get('market_theme', 'N/A')}")
        print(f"Signals: {len(result['signals'])}")
        print(f"Orders: {len(result['orders'])}")
        
        if result['signals']:
            print("\nSignals:")
            for s in result['signals']:
                print(f"  {s['action'].upper():4} {s['symbol']:6} - {s['reason'][:50]}...")
        
        if result['orders']:
            print("\nOrders executed:")
            for o in result['orders']:
                print(f"  {o['side'].upper():4} {o['qty']:.4f} {o['symbol']}")
        
        if result['errors']:
            print("\nErrors:")
            for e in result['errors']:
                print(f"  ❌ {e}")
        
        print()
        show_status()


if __name__ == "__main__":
    main()
