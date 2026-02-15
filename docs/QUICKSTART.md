# Quick Start Guide

Get up and running with Beavr in 5 minutes.

## Prerequisites

- Python 3.11+
- A broker account (one of the following):
  - [Alpaca Markets](https://alpaca.markets/) (free paper trading, default)
  - [Webull OpenAPI](https://www.webull.com/openapi) (optional)

## Installation

```bash
# Clone the repository
git clone https://github.com/sigsegved/Beavr.git
cd Beavr

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Beavr
pip install -e ".[dev]"
```

## Configuration

1. **Set up Alpaca API credentials:**

```bash
cp .env.example .env
```

2. **Edit `.env` with your API keys:**

```bash
ALPACA_API_KEY=your_api_key_here
ALPACA_API_SECRET=your_api_secret_here
```

Get your API keys from the [Alpaca Dashboard](https://app.alpaca.markets/).

3. **Load environment variables:**

```bash
export $(grep -v '^#' .env | xargs)
```

## Your First Backtest

Run a Simple DCA strategy on SPY for 6 months:

```bash
bvr backtest run simple_dca SPY --start 2024-01-01 --end 2024-06-30
```

**Sample output:**
```
╭───────────────────── 📊 Backtest Results ─────────────────────╮
│                                                               │
│  🎯 Strategy: Simple DCA                                      │
│  📈 Symbols: SPY                                              │
│  📅 Period: 2024-01-01 → 2024-06-30                           │
│                                                               │
╰───────────────────────────────────────────────────────────────╯

💰 Performance
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Metric             ┃ Value            ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ Initial Cash       │ $10,000.00       │
│ Final Value        │ $10,151.78       │
│ Total Return       │ +1.52%           │
│ CAGR               │ 3.11%            │
│ Total Trades       │ 4                │
└────────────────────┴──────────────────┘
```

## Compare Strategies

Compare different strategies:

```bash
bvr backtest compare simple_dca dip_buy_dca SPY --start 2024-01-01 --end 2024-06-30
```

## List Available Strategies

```bash
bvr backtest strategies
```

**Output:**
```
📋 Available Strategies

• simple_dca - Simple DCA
  Dollar-cost average a fixed amount on a schedule

• dip_buy_dca - Dip Buy DCA
  Buy on dips with month-end fallback
```

## Next Steps

- [Configuration Guide](CONFIGURATION.md) - Customize your setup
- [Strategy Guide](STRATEGIES.md) - Learn about available strategies
- [Examples](../examples/strategies/) - Strategy configuration examples
