"""High-frequency backtest engine for minute-level strategies."""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from uuid import uuid4

import pandas as pd

from beavr.data.alpaca import AlpacaDataFetcher
from beavr.models.trade import Trade
from beavr.strategies.base import BaseStrategy


@dataclass
class HFBacktestResult:
    """Result of a high-frequency backtest."""
    run_id: str
    strategy_name: str
    start_date: date
    end_date: date
    initial_cash: Decimal
    final_cash: Decimal
    final_value: Decimal
    total_return: float
    max_drawdown: float
    trades: list[Trade]
    num_bars: int
    timeframe: str


@dataclass
class HFPortfolio:
    """Simple portfolio tracker for HF backtesting."""
    cash: Decimal
    positions: dict = field(default_factory=dict)  # symbol -> {"shares": Decimal, "avg_price": Decimal}

    def buy(self, symbol: str, shares: Decimal, price: Decimal) -> bool:
        """Execute a buy order."""
        cost = shares * price
        if cost > self.cash:
            return False

        self.cash -= cost
        if symbol not in self.positions:
            self.positions[symbol] = {"shares": Decimal("0"), "avg_price": Decimal("0")}

        # Update average price
        pos = self.positions[symbol]
        total_shares = pos["shares"] + shares
        if total_shares > 0:
            pos["avg_price"] = (pos["shares"] * pos["avg_price"] + shares * price) / total_shares
        pos["shares"] = total_shares
        return True

    def sell(self, symbol: str, shares: Decimal, price: Decimal) -> bool:
        """Execute a sell order."""
        if symbol not in self.positions:
            return False
        pos = self.positions[symbol]
        if shares > pos["shares"]:
            return False

        self.cash += shares * price
        pos["shares"] -= shares
        if pos["shares"] == 0:
            del self.positions[symbol]
        return True

    def get_value(self, prices: dict[str, Decimal]) -> Decimal:
        """Get total portfolio value."""
        value = self.cash
        for symbol, pos in self.positions.items():
            if symbol in prices:
                value += pos["shares"] * prices[symbol]
        return value


@dataclass
class HFContext:
    """Context passed to strategy on each bar."""
    timestamp: datetime
    current_date: date
    bars: dict[str, pd.DataFrame]  # All bars up to current point
    current_prices: dict[str, Decimal]
    cash: Decimal
    positions: dict
    portfolio_value: Decimal


class HFBacktestEngine:
    """High-frequency backtest engine supporting minute/5-minute bars."""

    def __init__(self, data_fetcher: AlpacaDataFetcher):
        self.data = data_fetcher

    def run(
        self,
        strategy: BaseStrategy,
        start_date: date,
        end_date: date,
        initial_cash: Decimal,
        timeframe: str = "5Min",  # "1Min" or "5Min"
    ) -> HFBacktestResult:
        """Run high-frequency backtest."""
        run_id = str(uuid4())

        # Map timeframe
        alpaca_tf = "1Min" if timeframe in ["1Min", "1min"] else "1Hour"
        if timeframe in ["5Min", "5min"]:
            alpaca_tf = "1Min"  # Fetch 1min and resample

        print(f"Fetching {alpaca_tf} data for {strategy.symbols}...")

        # Fetch minute data
        all_bars = {}
        for symbol in strategy.symbols:
            bars = self.data.get_bars(symbol, start_date, end_date, alpaca_tf)
            if timeframe in ["5Min", "5min"] and not bars.empty:
                bars = self._resample_to_5min(bars)
            all_bars[symbol] = bars
            print(f"  {symbol}: {len(bars)} bars")

        if not all_bars or all(df.empty for df in all_bars.values()):
            raise ValueError("No data fetched")

        # Get all unique timestamps
        timestamps = set()
        for df in all_bars.values():
            if not df.empty and "timestamp" in df.columns:
                timestamps.update(df["timestamp"].tolist())
        timestamps = sorted(timestamps)
        print(f"Total timestamps: {len(timestamps)}")

        # Initialize
        portfolio = HFPortfolio(cash=initial_cash)
        trades = []
        peak_value = initial_cash
        max_drawdown = Decimal("0")

        # Main loop - iterate through each bar
        for i, ts in enumerate(timestamps):
            if i % 5000 == 0:
                print(f"  Processing bar {i}/{len(timestamps)}...")

            # Build context with bars up to this point
            current_bars = {}
            current_prices = {}
            for symbol, df in all_bars.items():
                if df.empty:
                    continue
                mask = df["timestamp"] <= ts
                current_bars[symbol] = df[mask].copy()
                if not current_bars[symbol].empty:
                    current_prices[symbol] = Decimal(str(current_bars[symbol]["close"].iloc[-1]))

            if not current_prices:
                continue

            portfolio_value = portfolio.get_value(current_prices)

            # Track drawdown
            if portfolio_value > peak_value:
                peak_value = portfolio_value
            drawdown = (peak_value - portfolio_value) / peak_value if peak_value > 0 else Decimal("0")
            if drawdown > max_drawdown:
                max_drawdown = drawdown

            ctx = HFContext(
                timestamp=ts,
                current_date=ts.date() if isinstance(ts, datetime) else ts,
                bars=current_bars,
                current_prices=current_prices,
                cash=portfolio.cash,
                positions=portfolio.positions.copy(),
                portfolio_value=portfolio_value,
            )

            # Get signals from strategy
            signals = strategy.evaluate_hf(ctx) if hasattr(strategy, "evaluate_hf") else []

            # Execute signals
            for signal in signals:
                symbol = signal.symbol
                price = current_prices.get(symbol)
                if price is None:
                    continue

                if signal.action == "buy":
                    amount = signal.amount or Decimal("0")
                    shares = amount / price if price > 0 else Decimal("0")
                    if portfolio.buy(symbol, shares, price):
                        trades.append(Trade(
                            symbol=symbol,
                            side="buy",
                            quantity=shares,
                            price=price,
                            amount=amount,
                            timestamp=ts if isinstance(ts, datetime) else datetime.combine(ts, time.min),
                            reason=signal.reason or "buy",
                        ))

                elif signal.action == "sell":
                    shares = signal.quantity or Decimal("0")
                    if portfolio.sell(symbol, shares, price):
                        trades.append(Trade(
                            symbol=symbol,
                            side="sell",
                            quantity=shares,
                            price=price,
                            amount=shares * price,
                            timestamp=ts if isinstance(ts, datetime) else datetime.combine(ts, time.min),
                            reason=signal.reason or "sell",
                        ))

        # Final valuation
        final_prices = {}
        for symbol, df in all_bars.items():
            if not df.empty:
                final_prices[symbol] = Decimal(str(df["close"].iloc[-1]))

        final_value = portfolio.get_value(final_prices)
        total_return = float((final_value - initial_cash) / initial_cash)

        return HFBacktestResult(
            run_id=run_id,
            strategy_name=strategy.name,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            final_cash=portfolio.cash,
            final_value=final_value,
            total_return=total_return,
            max_drawdown=float(max_drawdown),
            trades=trades,
            num_bars=len(timestamps),
            timeframe=timeframe,
        )

    def _resample_to_5min(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resample 1-minute bars to 5-minute bars."""
        if df.empty:
            return df

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

        resampled = df.resample("5min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

        resampled = resampled.reset_index()
        return resampled
