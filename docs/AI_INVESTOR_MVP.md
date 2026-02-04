# Beavr AI Investor - MVP

AI-powered multi-agent trading system for automated investing.

## Quick Start

### 1. Prerequisites

- **Python 3.11+** (required for GitHub Copilot SDK)
- **GitHub Copilot CLI** authenticated (`copilot` command available)
- **Alpaca Paper Trading Account**

### 2. Set Up Environment Variables

Add your Alpaca credentials to `.env`:

```bash
# .env
ALPACA_API_KEY=your_alpaca_key
ALPACA_API_SECRET=your_alpaca_secret
ALPACA_PAPER=true
```

**Note:** No OpenAI key needed! The AI Investor uses GitHub Copilot SDK for LLM inference, which authenticates via the Copilot CLI.

### 3. Install Dependencies

```bash
pip install -e ".[ai]"
pip install github-copilot-sdk
```

### 4. Run the Autonomous Agent

```bash
# Test mode (analyze but don't trade)
python3.11 autonomous_agent.py --test

# Live paper trading
python3.11 autonomous_agent.py

# Custom configuration
python3.11 autonomous_agent.py --profit-target 1.5 --max-loss 2.0 --scan-interval 10
```

## How It Works

The AI Investor uses multiple specialized agents that work together:

### Agents

1. **Market Analyst** - Analyzes market conditions and determines the regime:
   - Bull: Sustained uptrend, favorable for long positions
   - Bear: Sustained downtrend, defensive posture
   - Sideways: Range-bound, mean-reversion opportunities
   - Volatile: High uncertainty, reduced position sizes

2. **Swing Trader** - Identifies multi-day trading opportunities:
   - Looks for oversold bounces (RSI < 35)
   - Trend continuation after pullbacks
   - Support/resistance bounces

### Decision Flow

```
┌─────────────────────────────────────────────────┐
│              Daily Trading Cycle                │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. Fetch Market Data (Alpaca)                  │
│       ↓                                         │
│  2. Calculate Technical Indicators              │
│       ↓                                         │
│  3. Market Analyst → Determine Regime           │
│       ↓                                         │
│  4. Swing Trader → Find Opportunities           │
│       ↓                                         │
│  5. Apply Risk Gates & Position Limits          │
│       ↓                                         │
│  6. Execute Orders (Alpaca Paper)               │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Risk Management

- **Max Drawdown**: 20% default (triggers kill switch)
- **Max Position Size**: 10% of portfolio per symbol
- **Min Cash Reserve**: 5% kept as buffer
- **Progressive De-risking**: Position sizes reduced in drawdown

## Configuration

### Command Line Options

```bash
python run_ai_investor.py --help

Options:
  --once          Run single cycle instead of continuous
  --symbols       Symbols to trade (default: SPY, QQQ, AAPL, MSFT, GOOGL)
  --log-level     DEBUG, INFO, WARNING, ERROR
  --log-dir       Directory for log files (default: logs/ai_investor)
  --model         OpenAI model (gpt-4o-mini, gpt-4o, gpt-4-turbo)
  --dry-run       Show account info but don't run strategy
```

### Example Usage

```bash
# Trade tech stocks only
python run_ai_investor.py --once --symbols AAPL MSFT GOOGL NVDA

# Use a more powerful model
python run_ai_investor.py --once --model gpt-4o

# Debug mode with verbose logging
python run_ai_investor.py --once --log-level DEBUG
```

## Monitoring

### Log Files

All activity is logged to `logs/ai_investor/`:

- `paper_trading.log` - Main log file
- `cycle_YYYYMMDD_HHMMSS.json` - Detailed cycle results

### Cycle Results

Each cycle produces a JSON file with:

```json
{
  "cycle_number": 1,
  "start_time": "2024-01-15T10:00:00",
  "account": {
    "cash": "10000.00",
    "portfolio_value": "10500.00"
  },
  "signals": [
    {
      "symbol": "AAPL",
      "action": "buy",
      "amount": "500.00",
      "reason": "RSI oversold at 28, price near lower BB",
      "confidence": 0.75
    }
  ],
  "orders": [...],
  "errors": [],
  "orchestrator_summary": {...}
}
```

## Architecture

```
src/beavr/
├── agents/                 # AI Agents
│   ├── base.py            # BaseAgent interface
│   ├── market_analyst.py  # Market regime detection
│   ├── swing_trader.py    # Swing trading signals
│   └── indicators.py      # Technical indicators
├── llm/                   # LLM Integration
│   └── client.py          # OpenAI client wrapper
├── orchestrator/          # Multi-agent coordination
│   ├── engine.py          # Orchestrator engine
│   └── blackboard.py      # Shared state
├── strategies/ai/         # Strategy integration
│   └── multi_agent.py     # Beavr strategy adapter
└── paper_trading.py       # Paper trading runner
```

## Cost Estimation

Using `gpt-4o-mini` (default):
- ~$0.01-0.05 per trading cycle
- ~$0.30-1.50 per month (running daily)

Using `gpt-4o`:
- ~$0.10-0.30 per trading cycle
- ~$3-10 per month (running daily)

## Safety Features

1. **Paper Trading Only** - MVP only supports paper trading
2. **Kill Switch** - Automatically flattens positions at max drawdown
3. **Position Limits** - Caps individual positions at 10% of portfolio
4. **Cash Reserve** - Maintains 5% cash buffer
5. **Conviction Filter** - Ignores low-confidence signals

## Troubleshooting

### "OpenAI API key required"
Add your OpenAI API key to `.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

### "No trading days found"
The market may be closed. Check if it's a weekend or holiday.

### "LLM request failed"
Check your OpenAI API key and ensure you have credits.

### Low confidence signals
The AI is being conservative. This is expected in uncertain markets.

## Next Steps

- [ ] Add more trading agents (momentum, mean reversion)
- [ ] Implement news/sentiment analysis
- [ ] Add position tracking and P&L reporting
- [ ] Support for live trading (with additional safety checks)
