"""Paper trading runner for AI Investor.

This module provides the paper trading execution layer that connects
the AI strategy to a broker via the broker abstraction layer.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from beavr.broker.models import AccountInfo, BrokerPosition, OrderRequest, OrderResult
from beavr.broker.protocols import BrokerProvider, MarketDataProvider, ScreenerProvider
from beavr.models.signal import Signal
from beavr.strategies.ai.multi_agent import MultiAgentParams, MultiAgentStrategy

logger = logging.getLogger(__name__)


@dataclass
class PaperTradingConfig:
    """Configuration for paper trading."""

    symbols: list[str] = field(default_factory=lambda: ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL"])
    initial_cash: Decimal = Decimal("100000")
    max_drawdown: float = 0.20
    max_position_pct: float = 0.10
    min_cash_pct: float = 0.05
    llm_model: str = "gpt-4o-mini"
    log_dir: str = "logs/ai_investor"
    run_interval_hours: int = 24  # How often to run (for scheduling)
    
    # Dynamic symbol discovery
    use_market_movers: bool = False  # Use top gainers/losers instead of fixed symbols
    movers_count: int = 5  # Number of movers to trade
    min_price: float = 5.0  # Min price for movers
    max_price: float = 500.0  # Max price for movers


class PaperTradingRunner:
    """
    Executes AI trading strategy against a broker via the abstraction layer.

    Features:
    - Broker-agnostic via BrokerProvider / MarketDataProvider protocols
    - Fetches real-time market data
    - Executes AI strategy decisions
    - Logs all decisions and trades
    - Handles order execution with proper error handling
    """

    def __init__(
        self,
        broker: BrokerProvider,
        data_provider: MarketDataProvider,
        config: Optional[PaperTradingConfig] = None,
        screener: Optional[ScreenerProvider] = None,
    ) -> None:
        """Initialize paper trading runner.

        Args:
            broker: Broker provider for account/order operations.
            data_provider: Market data provider for historical bars.
            config: Paper trading configuration.
            screener: Optional screener for market movers discovery.
        """
        self.config = config or PaperTradingConfig()
        self.broker = broker
        self.data_provider = data_provider
        self.screener = screener

        # Set up logging directory
        self.log_dir = Path(self.config.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Determine symbols to trade
        self._trading_symbols = self._get_trading_symbols()

        # Initialize strategy
        self.strategy = MultiAgentStrategy(
            MultiAgentParams(
                symbols=self._trading_symbols,
                max_drawdown=self.config.max_drawdown,
                max_position_pct=self.config.max_position_pct,
                min_cash_pct=self.config.min_cash_pct,
                llm_model=self.config.llm_model,
            )
        )

        # Track state
        self._last_run: Optional[datetime] = None
        self._run_count = 0

    def _get_trading_symbols(self) -> list[str]:
        """Get symbols to trade - either fixed or from market movers."""
        if self.screener and self.config.use_market_movers:
            logger.info("Discovering tradeable symbols from market movers...")
            mover_list = self.screener.get_market_movers(top=self.config.movers_count)
            # Filter by price range
            movers = [
                m["symbol"]
                for m in mover_list
                if "symbol" in m
                and self.config.min_price <= float(m.get("price", 0)) <= self.config.max_price
            ]
            # Always include SPY for market context
            if "SPY" not in movers:
                movers = ["SPY"] + movers
            return movers
        return self.config.symbols

    def get_account(self) -> dict[str, Any]:
        """Get current account state."""
        account: AccountInfo = self.broker.get_account()
        return {
            "cash": account.cash,
            "portfolio_value": account.equity,
            "buying_power": account.buying_power,
            "equity": account.equity,
            "last_equity": account.equity,
            "status": "active",
        }

    def get_positions(self) -> dict[str, Decimal]:
        """Get current positions."""
        positions: list[BrokerPosition] = self.broker.get_positions()
        return {p.symbol: p.qty for p in positions}

    def get_position_details(self) -> list[dict[str, Any]]:
        """Get detailed position information."""
        positions: list[BrokerPosition] = self.broker.get_positions()
        details: list[dict[str, Any]] = []
        for p in positions:
            current_price = p.market_value / p.qty if p.qty else Decimal("0")
            cost_basis = p.avg_cost * p.qty if p.qty else Decimal("0")
            unrealized_plpc = (
                float(p.unrealized_pl / cost_basis) if cost_basis else 0.0
            )
            details.append({
                "symbol": p.symbol,
                "qty": p.qty,
                "market_value": p.market_value,
                "avg_entry_price": p.avg_cost,
                "current_price": current_price,
                "unrealized_pl": p.unrealized_pl,
                "unrealized_plpc": unrealized_plpc,
            })
        return details

    def run_cycle(self) -> dict[str, Any]:
        """
        Run one trading cycle.

        Returns:
            Dictionary with cycle results
        """
        cycle_start = datetime.now()
        self._run_count += 1

        logger.info("=" * 60)
        logger.info(f"Starting Trading Cycle #{self._run_count} at {cycle_start}")
        logger.info("=" * 60)

        result = {
            "cycle_number": self._run_count,
            "start_time": cycle_start.isoformat(),
            "signals": [],
            "orders": [],
            "errors": [],
        }

        try:
            # Step 1: Get account state
            account = self.get_account()
            positions = self.get_positions()

            logger.info(f"Account: Cash=${account['cash']:,.2f}, Portfolio=${account['portfolio_value']:,.2f}")
            logger.info(f"Positions: {len(positions)} symbols")

            result["account"] = {k: str(v) for k, v in account.items()}
            result["positions"] = {k: str(v) for k, v in positions.items()}

            # Step 2: Refresh symbols if using market movers
            if self.config.use_market_movers:
                logger.info("Refreshing tradeable symbols from market movers...")
                self._trading_symbols = self._get_trading_symbols()
                # Update strategy with new symbols
                self.strategy = MultiAgentStrategy(
                    MultiAgentParams(
                        symbols=self._trading_symbols,
                        max_drawdown=self.config.max_drawdown,
                        max_position_pct=self.config.max_position_pct,
                        min_cash_pct=self.config.min_cash_pct,
                        llm_model=self.config.llm_model,
                    )
                )
                logger.info(f"Trading symbols: {self._trading_symbols}")
                result["trading_symbols"] = self._trading_symbols

            # Step 3: Fetch market data
            logger.info("Fetching market data...")
            today = date.today()
            start_date = today - timedelta(days=90)  # Get 90 days of history

            bars = self.data_provider.get_bars_multi(
                symbols=self._trading_symbols,
                start=start_date,
                end=today,
                timeframe="1day",
            )

            # Get current prices
            prices = {}
            for symbol, df in bars.items():
                if not df.empty:
                    prices[symbol] = Decimal(str(df["close"].iloc[-1]))

            logger.info(f"Fetched data for {len(bars)} symbols")

            # Step 4: Build strategy context
            from beavr.strategies.context import StrategyContext

            ctx = StrategyContext(
                current_date=today,
                prices=prices,
                bars=bars,
                cash=account["cash"],
                positions=positions,
                period_budget=account["cash"],  # Use cash as budget
                period_spent=Decimal("0"),
                day_of_month=today.day,
                day_of_week=today.weekday(),
                days_to_month_end=0,  # Not used by AI strategy
                is_first_trading_day_of_month=False,
                is_last_trading_day_of_month=False,
            )

            # Step 5: Run AI strategy
            logger.info("Running AI strategy...")
            signals = self.strategy.evaluate(ctx)

            logger.info(f"Strategy generated {len(signals)} signals")
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

            # Step 6: Execute signals
            for signal in signals:
                try:
                    order_result = self._execute_signal(signal, prices)
                    result["orders"].append(order_result)
                except Exception as e:
                    error = f"Failed to execute {signal.symbol} {signal.action}: {e}"
                    logger.error(error)
                    result["errors"].append(error)

            # Step 6: Get orchestrator summary
            orchestrator_summary = self.strategy.get_orchestrator_summary()
            if orchestrator_summary:
                result["orchestrator_summary"] = self._serialize_summary(orchestrator_summary)

        except Exception as e:
            error = f"Cycle failed: {e}"
            logger.error(error, exc_info=True)
            result["errors"].append(error)

        # Finalize
        cycle_end = datetime.now()
        result["end_time"] = cycle_end.isoformat()
        result["duration_seconds"] = (cycle_end - cycle_start).total_seconds()

        self._last_run = cycle_end

        # Log results
        self._log_cycle_result(result)

        logger.info(f"Cycle complete. Duration: {result['duration_seconds']:.1f}s")
        logger.info("=" * 60)

        return result

    def _execute_signal(
        self, signal: Signal, prices: dict[str, Decimal]
    ) -> dict[str, Any]:
        """
        Execute a trading signal via the broker.

        Args:
            signal: Trading signal
            prices: Current prices

        Returns:
            Order result dictionary
        """
        logger.info(f"Executing: {signal}")

        if signal.action == "buy" and signal.amount:
            # Calculate quantity from amount
            price = prices.get(signal.symbol)
            if not price:
                raise ValueError(f"No price for {signal.symbol}")

            qty = signal.amount / price
            qty = qty.quantize(Decimal("0.0001"))  # Round to 4 decimals

            if qty < Decimal("0.001"):
                raise ValueError(f"Quantity too small: {qty}")

            order_req = OrderRequest(
                symbol=signal.symbol,
                quantity=qty,
                side="buy",
                order_type="market",
                tif="day",
            )

        elif signal.action == "sell" and signal.quantity:
            order_req = OrderRequest(
                symbol=signal.symbol,
                quantity=signal.quantity,
                side="sell",
                order_type="market",
                tif="day",
            )

        else:
            raise ValueError(f"Invalid signal: {signal}")

        # Submit order
        order: OrderResult = self.broker.submit_order(order_req)

        result = {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "qty": str(order.filled_qty),
            "status": order.status,
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            "signal_reason": signal.reason,
        }

        logger.info(f"Order submitted: {result['order_id']} - {result['side']} {result['qty']} {result['symbol']}")

        return result

    def _serialize_summary(self, summary: dict) -> dict:
        """Serialize orchestrator summary for JSON logging."""
        result = {}
        for key, value in summary.items():
            if isinstance(value, (Decimal, datetime, date)):
                result[key] = str(value)
            elif isinstance(value, dict):
                result[key] = self._serialize_summary(value)
            elif isinstance(value, list):
                result[key] = [
                    self._serialize_summary(v) if isinstance(v, dict) else str(v) if isinstance(v, (Decimal, datetime)) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _log_cycle_result(self, result: dict) -> None:
        """Log cycle result to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"cycle_{timestamp}.json"

        with open(log_file, "w") as f:
            json.dump(result, f, indent=2, default=str)

        logger.info(f"Cycle log saved to: {log_file}")

    def run_continuous(self, check_interval_minutes: int = 60) -> None:
        """
        Run continuously, executing cycles at configured intervals.

        Args:
            check_interval_minutes: How often to check if we should run
        """
        logger.info(f"Starting continuous paper trading (interval: {self.config.run_interval_hours}h)")

        while True:
            try:
                # Check if market is open
                clock = self.broker.get_clock()

                if clock.is_open:
                    # Run if we haven't run today or interval has passed
                    should_run = self._should_run_cycle()

                    if should_run:
                        self.run_cycle()
                else:
                    logger.info(f"Market closed. Next open: {clock.next_open}")

                # Sleep until next check
                logger.info(f"Sleeping {check_interval_minutes} minutes...")
                time.sleep(check_interval_minutes * 60)

            except KeyboardInterrupt:
                logger.info("Interrupted by user. Stopping.")
                break
            except Exception as e:
                logger.error(f"Error in continuous loop: {e}")
                time.sleep(60)  # Wait a minute on error

    def _should_run_cycle(self) -> bool:
        """Check if we should run a new cycle."""
        if self._last_run is None:
            return True

        elapsed = datetime.now() - self._last_run
        return elapsed.total_seconds() >= (self.config.run_interval_hours * 3600)


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Set up logging for paper trading.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to log to
    """
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce noise from other libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> None:
    """Main entry point for paper trading.

    .. deprecated::
        Direct script execution is no longer supported after the broker
        abstraction migration.  Use the ``bvr ai run`` CLI command instead,
        which properly injects broker and data-provider instances via
        ``BrokerFactory``.
    """
    raise RuntimeError(
        "Direct paper_trading.py execution is no longer supported. "
        "Use 'bvr ai run' CLI command instead, or construct "
        "PaperTradingRunner with broker/data_provider arguments."
    )


if __name__ == "__main__":
    main()
