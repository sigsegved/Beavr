#!/usr/bin/env python
"""
AI Investor Paper Trading Runner

This script runs the AI Investor on your Alpaca paper trading account.

Setup:
1. Set OPENAI_API_KEY in your .env file
2. Ensure Alpaca credentials are set (ALPACA_API_KEY, ALPACA_API_SECRET)
3. Run: python run_ai_investor.py

Options:
    --once          Run single cycle instead of continuous
    --symbols       Symbols to trade (default: SPY, QQQ, AAPL, MSFT, GOOGL)
    --log-level     Logging level (DEBUG, INFO, WARNING, ERROR)
    --model         OpenAI model (default: gpt-4o-mini)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

# Load environment
load_dotenv()


def check_env():
    """Check required environment variables."""
    required = {
        "ALPACA_API_KEY": "Alpaca API key",
        "ALPACA_API_SECRET": "Alpaca API secret",
        "OPENAI_API_KEY": "OpenAI API key",
    }

    missing = []
    for key, desc in required.items():
        val = os.environ.get(key)
        if not val or val.startswith("your_"):
            missing.append(f"  - {key}: {desc}")

    if missing:
        print("❌ Missing required environment variables:")
        print("\n".join(missing))
        print("\nPlease set these in your .env file:")
        print("  OPENAI_API_KEY=sk-...")
        print("  ALPACA_API_KEY=...")
        print("  ALPACA_API_SECRET=...")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(
        description="AI Investor Paper Trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run single cycle instead of continuous",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["SPY", "QQQ", "AAPL", "MSFT", "GOOGL"],
        help="Symbols to trade (ignored if --market-movers is set)",
    )
    parser.add_argument(
        "--market-movers",
        action="store_true",
        help="Use top market movers (gainers/losers) instead of fixed symbols",
    )
    parser.add_argument(
        "--movers-count",
        type=int,
        default=5,
        help="Number of market movers to trade (default: 5)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/ai_investor",
        help="Directory for log files",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model to use (gpt-4o-mini, gpt-4o, gpt-4-turbo)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show account info but don't run strategy",
    )

    args = parser.parse_args()

    # Check environment
    if not check_env():
        sys.exit(1)

    # Import after env check to avoid errors
    from beavr.paper_trading import (
        PaperTradingConfig,
        PaperTradingRunner,
        setup_logging,
    )

    # Set up logging
    log_file = Path(args.log_dir) / "paper_trading.log"
    setup_logging(args.log_level, str(log_file))

    print("=" * 60)
    print("🤖 AI Investor Paper Trading")
    print("=" * 60)
    
    if args.market_movers:
        print(f"Mode: Dynamic (top {args.movers_count} market movers)")
    else:
        print(f"Symbols: {', '.join(args.symbols)}")
    print(f"Model: {args.model}")
    print(f"Log directory: {args.log_dir}")
    print()

    # Create config
    config = PaperTradingConfig(
        symbols=args.symbols,
        log_dir=args.log_dir,
        llm_model=args.model,
        use_market_movers=args.market_movers,
        movers_count=args.movers_count,
    )

    # Create runner
    runner = PaperTradingRunner(config)
    
    # Show trading symbols
    if args.market_movers:
        print(f"📊 Discovered Symbols: {', '.join(runner._trading_symbols)}")
        print()

    # Show account info
    account = runner.get_account()
    print("💰 Account Status:")
    print(f"   Status: {account['status']}")
    print(f"   Cash: ${account['cash']:,.2f}")
    print(f"   Portfolio Value: ${account['portfolio_value']:,.2f}")
    print()

    positions = runner.get_position_details()
    if positions:
        print("📈 Current Positions:")
        for p in positions:
            pl_emoji = "🟢" if float(p["unrealized_pl"]) >= 0 else "🔴"
            print(
                f"   {p['symbol']}: {p['qty']:.4f} shares @ ${p['current_price']:.2f} "
                f"({pl_emoji} ${p['unrealized_pl']:.2f}, {p['unrealized_plpc']:.1%})"
            )
    else:
        print("📈 No current positions")
    print()

    if args.dry_run:
        print("Dry run mode - not executing strategy")
        return

    print("=" * 60)
    print("Starting AI Strategy...")
    print("=" * 60)

    # Run
    if args.once:
        result = runner.run_cycle()

        # Show results
        print()
        print("=" * 60)
        print("📋 Cycle Results")
        print("=" * 60)
        print(f"Duration: {result['duration_seconds']:.1f}s")
        print(f"Signals: {len(result['signals'])}")
        print(f"Orders: {len(result['orders'])}")
        print(f"Errors: {len(result['errors'])}")

        if result["signals"]:
            print("\n📊 Signals:")
            for s in result["signals"]:
                print(f"   {s['action'].upper()} {s['symbol']}: {s['reason'][:60]}...")

        if result["orders"]:
            print("\n📝 Orders:")
            for o in result["orders"]:
                print(f"   {o['side']} {o['qty']} {o['symbol']} - {o['status']}")

        if result["errors"]:
            print("\n❌ Errors:")
            for e in result["errors"]:
                print(f"   {e}")

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = Path(args.log_dir) / f"result_{timestamp}.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nFull results saved to: {result_file}")

    else:
        print("Running in continuous mode. Press Ctrl+C to stop.")
        runner.run_continuous()


if __name__ == "__main__":
    main()
