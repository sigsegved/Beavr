# Swing Reversal Trading Algorithm

## Overview

A state-machine based swing trading strategy that:
1. **Waits for dips** - Price drops X% from recent high
2. **Buys on reversal** - Confirmed by technical indicators
3. **Sells on profit or reversal** - Takes profits or cuts losses

## State Machine

```
┌─────────────┐
│  WATCHING   │ ← Monitor price, track recent high
└──────┬──────┘
       │ Price drops X% from high
       ▼
┌─────────────┐
│DIP_DETECTED │ ← Monitor for bullish reversal
└──────┬──────┘
       │ Reversal signal confirmed
       ▼
┌─────────────┐
│   HOLDING   │ ← Monitor for sell signal
└──────┬──────┘
       │ Profit target / Stop loss / Bearish reversal
       ▼
┌─────────────┐
│  WATCHING   │ ← Cycle repeats
└─────────────┘
```

## Reversal Detection Methods

### 1. EMA Crossover (`ema_cross`)
- **Buy**: Fast EMA crosses ABOVE slow EMA
- **Sell**: Fast EMA crosses BELOW slow EMA
- **Pros**: Clear signal, filters noise
- **Cons**: Lags behind price action

### 2. Momentum (`momentum`)
- **Buy**: Rate of change turns positive (> threshold)
- **Sell**: Rate of change turns negative (< -threshold)
- **Pros**: Faster than EMA
- **Cons**: More false signals in choppy markets

### 3. Higher Low / Lower High (`higher_low`)
- **Buy**: Current low > previous swing low
- **Sell**: Current high < previous swing high
- **Pros**: Classic price action pattern
- **Cons**: Needs good swing detection

### 4. Combined (`combined`)
- Requires 2 out of 3 methods to agree
- **Pros**: Fewer false signals
- **Cons**: May miss quick moves

## Optimal Parameters (from backtesting)

| Timeframe | dip_threshold | profit_target | stop_loss | EMA fast/slow |
|-----------|---------------|---------------|-----------|---------------|
| 5-minute  | 0.5-1%        | 1-2%          | 1-2%      | 3/8           |
| 1-hour    | 1.5-2%        | 2-3%          | 3%        | 5/13          |
| Daily     | 3-5%          | 5-10%         | 5%        | 8/21          |

## Key Findings from Backtesting

### BTC Jan-Jun 2025 Results (Hourly Data)

| Method | Return | Win Rate | Key Issue |
|--------|--------|----------|-----------|
| Buy & Hold | +16.83% | - | Best in uptrend |
| EMA Cross | -1.45% | 33% | Too slow |
| Momentum | -0.31% | 33% | Too many stops |
| Higher Low | -0.22% | 38% | False signals |
| Combined | -1.15% | 27% | Still too slow |

### Why Swing Trading Lost

1. **BTC was in an uptrend** - Buy & Hold wins in trends
2. **Hourly data too coarse** - Missed the micro-swings
3. **Stop losses triggered** - 5-10% swings within hours

### When Swing Trading Wins

- Sideways/choppy markets
- High volatility with mean reversion
- Shorter timeframes (5-15 min)
- Tighter profit targets (1-2%)

## Implementation: The 5-Minute Algorithm

Based on your chart analysis, here's the ideal algorithm:

```python
# Parameters for 5-minute BTC trading
params = SwingReversalParams(
    dip_threshold=0.01,     # 1% dip triggers monitoring
    profit_target=0.015,    # 1.5% profit target
    stop_loss=0.02,         # 2% stop loss
    reversal_method="momentum",  # Fastest signal
    ema_fast=3,             # 15 minutes (3 x 5min)
    ema_slow=8,             # 40 minutes (8 x 5min)
    momentum_threshold=0.003,  # 0.3% momentum
    use_reversal_sell=True,    # Exit on bearish reversal
)
```

## Phases Explained (From Your Chart)

### Purple Phase (WATCHING → DIP_DETECTED)
- Tracking recent high
- Price drops 1%+ from high
- Switch to monitoring for reversal

### Yellow Phase (DIP_DETECTED → HOLDING)
- Watching for bullish reversal
- Update recent low as price falls
- On reversal signal: BUY

### Cyan/Green Phase (HOLDING)
- Watching for:
  - Profit target (price up 1.5%+)
  - Stop loss (price down 2%+)
  - Bearish reversal signal
- On any: SELL

## Next Steps

1. **Add 5-minute data support** to Alpaca fetcher
2. **Paper trade** with real-time data
3. **Add trailing stop** to lock in profits
4. **Consider MACD** as additional signal
