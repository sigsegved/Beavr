# Configuration Guide

Beavr uses TOML files and environment variables for configuration.

## Environment Variables

Create a `.env` file in the project root:

```bash
# Alpaca API credentials (default broker)
ALPACA_API_KEY=your_api_key
ALPACA_API_SECRET=your_api_secret

# Webull API credentials (optional, for Webull broker)
WEBULL_APP_KEY=your_app_key
WEBULL_APP_SECRET=your_app_secret
WEBULL_ACCOUNT_ID=your_account_id  # optional, auto-discovered if omitted

# Optional: Database path (defaults to ~/.beavr/beavr.db)
BEAVR_DATABASE_PATH=~/.beavr/beavr.db
```

## Application Configuration

The application uses these settings (via Pydantic Settings):

| Setting | Environment Variable | Default | Description |
|---------|---------------------|---------|-------------|
| `database_path` | `BEAVR_DATABASE_PATH` | `~/.beavr/beavr.db` | SQLite database path |
| `alpaca_api_key` | `ALPACA_API_KEY` | (required) | Alpaca API key |
| `alpaca_api_secret` | `ALPACA_API_SECRET` | (required) | Alpaca API secret |
| `webull_app_key` | `WEBULL_APP_KEY` | (optional) | Webull app key |
| `webull_app_secret` | `WEBULL_APP_SECRET` | (optional) | Webull app secret |
| `webull_account_id` | `WEBULL_ACCOUNT_ID` | (optional) | Webull account ID |

## Broker Configuration

Beavr supports multiple brokers via a pluggable adapter layer. Configure the
active broker in your TOML config:

### Alpaca (default)

```toml
[broker]
provider = "alpaca"
paper = true  # Use paper trading
```

### Webull

> **Note:** Webull does not support paper trading. Use Alpaca for paper
> trading, then switch to Webull for live execution.

```toml
[broker]
provider = "webull"
paper = false  # Must be false — Webull is live-only

[broker.webull]
region = "us"  # "us" or "hk"
```

Set `WEBULL_APP_KEY`, `WEBULL_APP_SECRET`, and optionally `WEBULL_ACCOUNT_ID`
in your environment. Install extra dependencies:

```bash
pip install -e ".[webull]"
```

## Strategy Configuration

Strategies are configured via TOML files. Each file specifies a strategy template and its parameters.

### File Location

Strategy configs can be placed in:
- `~/.beavr/strategies/` - User strategies
- `examples/strategies/` - Example strategies

### TOML Structure

```toml
# Strategy template name (must match a registered strategy)
template = "simple_dca"

# Strategy-specific parameters
[params]
symbols = ["SPY", "QQQ"]
amount = 500
frequency = "monthly"
day_of_month = 1
```

### Available Parameters by Strategy

#### Simple DCA

```toml
template = "simple_dca"

[params]
symbols = ["SPY"]           # List of symbols to buy
amount = 500                # Amount to invest each period
frequency = "monthly"       # "daily", "weekly", "monthly"
day_of_month = 1            # Day to buy (for monthly frequency)
```

#### Dip Buy DCA

```toml
template = "dip_buy_dca"

[params]
symbols = ["SPY", "QQQ"]    # List of symbols to buy
monthly_budget = 500        # Total budget per month
dip_threshold = 0.02        # Buy threshold (2% = 0.02)
dip_buy_pct = 0.50          # % of budget to deploy per dip
lookback_days = 5           # Days to look back for high
fallback_days = 3           # Days before month-end for fallback
```

## Database

Beavr uses SQLite for storing:
- Historical price data cache (bar_cache table)
- Backtest results and metrics

The database is automatically created on first run.

### Manual Database Operations

```bash
# View database location
echo $BEAVR_DATABASE_PATH

# Reset database
rm ~/.beavr/beavr.db
```

## CLI Options

Most CLI commands accept options to override defaults:

```bash
# Specify initial capital
bvr backtest run simple_dca SPY --initial-cash 50000

# Custom date range
bvr backtest run simple_dca SPY --start 2020-01-01 --end 2024-01-01

# Export results to CSV
bvr backtest export <run-id> results.csv
```

## Broker API Notes

### Alpaca

- **Paper trading** keys work for all backtesting operations
- Data is fetched from Alpaca's historical data API
- Bars are cached locally to reduce API calls
- Supported timeframes: 1min, 5min, 15min, 30min, 1hour, 1day, 1week
- Supports screener and news APIs
- Get your API keys from: https://app.alpaca.markets/

### Webull

- **Live trading only** — paper/sandbox trading is not supported
- Requires OpenAPI SDK credentials (app key + app secret)
- Automatic account discovery if account ID is not provided
- Instrument IDs are cached locally in SQLite for performance
- Supported timeframes: 1min, 5min, 15min, 30min, 1hour, 1day, 1week
- Supports stocks and crypto (auto-detected by symbol format)
- Get your API keys from: https://www.webull.com/openapi
