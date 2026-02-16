"""
Beavr AI Investor CLI - Autonomous AI-powered trading.

Commands:
    bvr ai status     - Show portfolio and AI status
    bvr ai invest     - Invest a specified amount using AI
    bvr ai watch      - Monitor positions and auto-exit at targets
    bvr ai sell       - Sell positions (specific or all)
    bvr ai analyze    - Analyze market without trading
    bvr ai history    - Show trade history and performance
    bvr ai auto       - Run autonomous thesis-driven trading

Stop/Target Tracking:
    - AI positions are tracked in the SQLite database with entry price,
      stop loss %, and target % for each position.
    - Use 'bvr ai watch' to monitor positions and auto-exit when
      targets or stops are hit.
    - The watch command uses POLLING (not conditional orders).
    - For production, consider using Alpaca's bracket orders for
      server-side stop/target execution.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from beavr.broker.factory import BrokerFactory
from beavr.broker.models import OrderRequest
from beavr.core.config import get_settings
from beavr.db import AIPositionsRepository, Database

if TYPE_CHECKING:
    from beavr.agents.base import AgentContext
    from beavr.broker.protocols import BrokerProvider, MarketDataProvider, ScreenerProvider

# US Eastern timezone for market hours
ET = ZoneInfo("America/New_York")

ai_app = typer.Typer(
    name="ai",
    help="AI-powered autonomous trading",
    no_args_is_help=True,
)
console = Console()
logger = logging.getLogger(__name__)


# =============================================================================
# STOCK QUALITY FILTERS
# =============================================================================

# Large-cap, liquid stocks that support fractional trading
# These are preferred for trading due to liquidity and fractional support
QUALITY_UNIVERSE = {
    # Major ETFs (always liquid, always fractional)
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "TQQQ", "SQQQ", "ARKK", "XLF", "XLE", "XLK",
    "GLD", "SLV", "TLT", "HYG", "EEM", "VWO", "IEMG", "VEA",
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ASML",
    # Large-cap tech
    "AMD", "INTC", "CRM", "ORCL", "ADBE", "NFLX", "PYPL", "SQ", "SHOP", "UBER", "ABNB",
    "SNOW", "PLTR", "NET", "CRWD", "ZS", "DDOG", "MDB", "OKTA",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "BLK", "C", "WFC", "SCHW",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "BMY", "AMGN", "GILD",
    # Consumer
    "WMT", "COST", "HD", "MCD", "SBUX", "NKE", "DIS", "TGT", "LOW", "TJX",
    # Energy
    "XOM", "CVX", "COP", "SLB", "OXY", "EOG", "PXD",
    # Industrial
    "CAT", "BA", "HON", "UPS", "LMT", "RTX", "DE", "GE", "MMM",
    # Crypto-related (high volatility plays)
    "COIN", "MSTR", "MARA", "RIOT",
    # Popular meme/momentum stocks
    "GME", "AMC", "RIVN", "LCID", "NIO", "SOFI", "HOOD",
}

# Minimum requirements for non-universe stocks
MIN_PRICE = 5.0  # No penny stocks under $5
MAX_PRICE = 2000.0  # Allow higher priced stocks
MIN_AVG_VOLUME = 100_000  # Minimum average daily volume


def is_quality_stock(symbol: str, price: float = 0, volume: int = 0) -> bool:
    """Check if a stock meets quality criteria."""
    # Always allow quality universe
    if symbol in QUALITY_UNIVERSE:
        return True

    # Filter out penny stocks
    if price > 0 and price < MIN_PRICE:
        return False

    # Filter out extremely high priced (harder to trade)
    if price > MAX_PRICE:
        return False

    # Filter out illiquid names when volume is provided
    if volume > 0 and volume < MIN_AVG_VOLUME:
        return False

    # Filter out common patterns for problematic stocks
    if len(symbol) > 5:  # Most are warrants, units, etc.
        return False

    if any(c in symbol for c in ["."]):  # Special share classes (allow - for some ETFs)
        return False

    # Allow stocks that pass basic filters
    return True


# =============================================================================
# AI INVESTOR CORE
# =============================================================================

class AIInvestor:
    """Core AI investor functionality."""

    def __init__(self):
        """Initialize the AI investor."""
        self._broker: BrokerProvider | None = None
        self._data_provider: MarketDataProvider | None = None
        self._llm = None
        self._screener: ScreenerProvider | None = None
        self._db = None
        self._positions_repo = None

    @property
    def db(self):
        """Lazy load database connection."""
        if self._db is None:
            self._db = Database()
        return self._db

    @property
    def positions_repo(self):
        """Lazy load positions repository."""
        if self._positions_repo is None:
            self._positions_repo = AIPositionsRepository(self.db)
        return self._positions_repo

    @property
    def broker(self) -> BrokerProvider:
        """Lazy load broker provider."""
        if self._broker is None:
            self._broker = BrokerFactory.create_broker(get_settings())
        return self._broker

    @property
    def data_provider(self) -> MarketDataProvider:
        """Lazy load market data provider."""
        if self._data_provider is None:
            self._data_provider = BrokerFactory.create_data_provider(get_settings())
        return self._data_provider

    @property
    def llm(self):
        """Lazy load LLM client."""
        if self._llm is None:
            from beavr.llm.client import LLMClient
            self._llm = LLMClient()
        return self._llm

    @property
    def screener(self) -> ScreenerProvider:
        """Lazy load market screener."""
        if self._screener is None:
            screener = BrokerFactory.create_screener(get_settings())
            if screener is None:
                raise RuntimeError("Screener unavailable \u2014 check broker credentials")
            self._screener = screener
        return self._screener

    def get_account(self) -> dict:
        """Get account status."""
        account = self.broker.get_account()
        positions = self.broker.get_positions()

        return {
            "equity": account.equity,
            "cash": account.cash,
            "buying_power": account.buying_power,
            "positions": {
                p.symbol: {
                    "qty": p.qty,
                    "avg_entry": p.avg_cost,
                    "current_price": (p.market_value / p.qty) if p.qty else Decimal(0),
                    "market_value": p.market_value,
                    "pnl": p.unrealized_pl,
                    "pnl_pct": float(p.unrealized_pl / (p.avg_cost * p.qty) * 100) if p.avg_cost and p.qty else 0.0,
                }
                for p in positions
            }
        }

    def get_quality_opportunities(self) -> list[dict]:
        """Get market movers filtered for quality."""
        movers = self.screener.get_market_movers(top=20)

        opportunities = []
        for m in movers:
            price = float(m.get("price", 0))
            if is_quality_stock(m["symbol"], price):
                opportunities.append({
                    "symbol": m["symbol"],
                    "price": price,
                    "change_pct": m.get("percent_change", 0.0),
                    "type": m.get("type", "gainer"),
                    "in_universe": m["symbol"] in QUALITY_UNIVERSE,
                })

        # Sort to prioritize quality universe stocks
        opportunities.sort(key=lambda x: (not x["in_universe"], -abs(x["change_pct"])))

        return opportunities

    def get_technical_indicators(self, symbol: str) -> Optional[dict]:
        """Calculate technical indicators for a symbol."""
        try:
            bars = self.data_provider.get_bars(
                symbol,
                date.today() - timedelta(days=60),
                date.today(),
            )
            if bars.empty or len(bars) < 20:
                return None

            close = bars["close"]

            # RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # SMAs
            sma_10 = close.rolling(10).mean()
            sma_20 = close.rolling(20).mean()
            sma_50 = close.rolling(50).mean() if len(close) >= 50 else sma_20

            # Bollinger Bands
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std

            current_price = float(close.iloc[-1])

            return {
                "price": current_price,
                "rsi": float(rsi.iloc[-1]) if not rsi.empty else 50,
                "sma_10": float(sma_10.iloc[-1]),
                "sma_20": float(sma_20.iloc[-1]),
                "sma_50": float(sma_50.iloc[-1]) if len(close) >= 50 else None,
                "bb_upper": float(bb_upper.iloc[-1]),
                "bb_lower": float(bb_lower.iloc[-1]),
                "above_sma_20": current_price > float(sma_20.iloc[-1]),
                "oversold": float(rsi.iloc[-1]) < 30 if not rsi.empty else False,
                "overbought": float(rsi.iloc[-1]) > 70 if not rsi.empty else False,
            }
        except Exception as e:
            logger.warning(f"Could not get indicators for {symbol}: {e}")
            return None

    def analyze_opportunities(self, amount: Decimal, max_picks: int = 3) -> list[dict]:
        """Use AI to analyze and pick opportunities."""
        from pydantic import BaseModel, Field

        # Get quality opportunities
        opps = self.get_quality_opportunities()
        if not opps:
            return []

        # Get technicals for each
        with_technicals = []
        for opp in opps[:15]:  # Limit to top 15
            tech = self.get_technical_indicators(opp["symbol"])
            if tech:
                opp["technicals"] = tech
                with_technicals.append(opp)

        if not with_technicals:
            return []

        # Build context for AI
        context = "QUALITY STOCK OPPORTUNITIES:\n\n"
        for opp in with_technicals:
            tech = opp["technicals"]
            context += f"{opp['symbol']} ({opp['type'].upper()}):\n"
            context += f"  Price: ${tech['price']:.2f}, Change: {opp['change_pct']:+.1f}%\n"
            context += f"  RSI: {tech['rsi']:.1f}"
            if tech['oversold']:
                context += " (OVERSOLD)"
            elif tech['overbought']:
                context += " (OVERBOUGHT)"
            context += f"\n  SMA20: ${tech['sma_20']:.2f}, "
            context += "Above SMA20" if tech['above_sma_20'] else "Below SMA20"
            context += f"\n  Bollinger: ${tech['bb_lower']:.2f} - ${tech['bb_upper']:.2f}\n\n"

        # Structured output schema
        class Pick(BaseModel):
            symbol: str = Field(description="Stock symbol")
            allocation_pct: int = Field(ge=10, le=100, description="% of capital (10-100%)")
            strategy: str = Field(description="momentum, bounce, or breakout")
            rationale: str = Field(description="Why this is a good trade")
            entry_price: float = Field(description="Current entry price")
            stop_loss_pct: float = Field(ge=2, le=15, description="Stop loss % (2-15%)")
            target_pct: float = Field(ge=3, le=30, description="Profit target % (3-30%)")

        class Analysis(BaseModel):
            picks: list[Pick] = Field(description="1-4 stock picks, total allocation = 100%")
            market_view: str = Field(description="Brief market assessment")
            risk_level: str = Field(description="low, medium, or high")

        prompt = f"""Analyze these QUALITY stocks and pick the best 1-4 for deploying ${amount:.2f}.

{context}

RULES:
1. Only pick from the stocks listed above - they are pre-screened for quality
2. Total allocation MUST equal 100%
3. Each pick gets 20-50% of capital (or 100% if only one good opportunity)
4. Look for:
   - Momentum: Strong gainers with RSI not overbought, above SMA20
   - Bounce: Oversold stocks (RSI < 30) that are quality names
   - Breakout: Stocks breaking above resistance (Bollinger upper)
5. Set appropriate stop-loss (2-15%) and target (3-30%) for each
6. If fewer good opportunities, concentrate in the best ones

Be decisive - we want to deploy this capital."""

        result: Analysis = self.llm.reason(
            system_prompt="You are a professional day trader. Pick quality setups with clear risk/reward.",
            user_prompt=prompt,
            output_schema=Analysis,
        )

        # Convert to standard format
        picks = []
        for pick in result.picks[:max_picks]:
            # Find the opportunity data
            opp_data = next((o for o in with_technicals if o["symbol"] == pick.symbol), None)
            if not opp_data:
                continue

            picks.append({
                "symbol": pick.symbol,
                "amount": amount * Decimal(str(pick.allocation_pct)) / 100,
                "allocation_pct": pick.allocation_pct,
                "strategy": pick.strategy,
                "rationale": pick.rationale,
                "price": Decimal(str(pick.entry_price)),
                "stop_loss_pct": pick.stop_loss_pct,
                "target_pct": pick.target_pct,
                "technicals": opp_data.get("technicals", {}),
            })

        return picks, result.market_view, result.risk_level

    def execute_buy(self, symbol: str, amount: Decimal, test_mode: bool = False) -> bool:
        """Execute a buy order."""
        try:
            # Get current price
            bars = self.data_provider.get_bars(symbol, date.today() - timedelta(days=5), date.today())
            if bars.empty:
                return False

            price = Decimal(str(bars["close"].iloc[-1]))
            qty = float(amount / price)

            if test_mode:
                console.print(f"  [yellow][TEST][/yellow] Would BUY {qty:.4f} {symbol} @ ${price:.2f} = ${amount:.2f}")
                return True

            # Try fractional first
            try:
                self.broker.submit_order(
                    OrderRequest(
                        symbol=symbol,
                        quantity=Decimal(str(round(qty, 4))),
                        side="buy",
                        order_type="market",
                        tif="day",
                    )
                )
                console.print(f"  [green]✅ BUY[/green] {qty:.4f} {symbol} @ ~${price:.2f} = ${amount:.2f}")
                return True
            except Exception as e:
                if "not fractionable" in str(e):
                    whole_qty = int(qty)
                    if whole_qty >= 1:
                        self.broker.submit_order(
                            OrderRequest(
                                symbol=symbol,
                                quantity=Decimal(str(whole_qty)),
                                side="buy",
                                order_type="market",
                                tif="day",
                            )
                        )
                        actual = Decimal(whole_qty) * price
                        console.print(f"  [green]✅ BUY[/green] {whole_qty} {symbol} @ ~${price:.2f} = ${actual:.2f} (whole shares)")
                        return True
                    else:
                        console.print(f"  [yellow]⚠️  Skip[/yellow] {symbol} - price too high for 1 share")
                        return False
                raise
        except Exception as e:
            console.print(f"  [red]❌ Failed[/red] {symbol}: {e}")
            return False

    def execute_sell(self, symbol: str, qty: Decimal, test_mode: bool = False) -> bool:
        """Execute a sell order."""
        try:
            if test_mode:
                console.print(f"  [yellow][TEST][/yellow] Would SELL {qty} {symbol}")
                return True

            self.broker.submit_order(
                OrderRequest(
                    symbol=symbol,
                    quantity=qty,
                    side="sell",
                    order_type="market",
                    tif="day",
                )
            )
            console.print(f"  [green]✅ SOLD[/green] {qty} {symbol}")
            return True
        except Exception as e:
            console.print(f"  [red]❌ Failed[/red] {symbol}: {e}")
            return False


# Global investor instance
_investor: Optional[AIInvestor] = None


def get_investor() -> AIInvestor:
    """Get or create the AI investor instance."""
    global _investor
    if _investor is None:
        _investor = AIInvestor()
    return _investor


# =============================================================================
# CLI COMMANDS
# =============================================================================

@ai_app.command()
def status() -> None:
    """Show portfolio status and AI readiness."""
    investor = get_investor()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Fetching account data...", total=None)
        account = investor.get_account()

    # Account summary
    console.print()
    console.print(Panel.fit(
        f"[bold]Portfolio Value:[/bold] ${account['equity']:,.2f}\n"
        f"[bold]Cash Available:[/bold] ${account['cash']:,.2f}\n"
        f"[bold]Buying Power:[/bold] ${account['buying_power']:,.2f}",
        title="💰 Account Status",
    ))

    # Positions table
    if account["positions"]:
        table = Table(title="📊 Positions")
        table.add_column("Symbol", style="cyan")
        table.add_column("Shares", justify="right")
        table.add_column("Avg Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("Value", justify="right")
        table.add_column("P/L", justify="right")
        table.add_column("P/L %", justify="right")

        total_pnl = Decimal(0)
        for symbol, pos in account["positions"].items():
            pnl_style = "green" if pos["pnl"] >= 0 else "red"
            table.add_row(
                symbol,
                f"{pos['qty']:.4f}",
                f"${pos['avg_entry']:.2f}",
                f"${pos['current_price']:.2f}",
                f"${pos['market_value']:.2f}",
                f"[{pnl_style}]${pos['pnl']:.2f}[/{pnl_style}]",
                f"[{pnl_style}]{pos['pnl_pct']:+.2f}%[/{pnl_style}]",
            )
            total_pnl += pos["pnl"]

        console.print()
        console.print(table)

        pnl_style = "green" if total_pnl >= 0 else "red"
        console.print(f"\n[bold]Total P/L:[/bold] [{pnl_style}]${total_pnl:.2f}[/{pnl_style}]")
    else:
        console.print("\n[dim]No open positions[/dim]")


@ai_app.command()
def invest(
    amount: float = typer.Argument(..., help="Amount to invest in USD"),
    target: float = typer.Option(5.0, "--target", "-t", help="Profit target %"),
    stop: float = typer.Option(5.0, "--stop", "-s", help="Stop loss %"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm trades"),
    test: bool = typer.Option(False, "--test", help="Test mode (no real trades)"),
) -> None:
    """Invest a specified amount using AI analysis.
    
    Positions are tracked in the database with stop/target levels.
    Use 'bvr ai watch' afterwards to monitor and auto-exit positions.
    """
    investor = get_investor()
    amount_dec = Decimal(str(amount))

    # Check account
    account = investor.get_account()
    if amount_dec > account["cash"]:
        console.print(f"[red]Insufficient cash![/red] Have ${account['cash']:.2f}, need ${amount_dec:.2f}")
        raise typer.Exit(1)

    console.print()
    console.print(Panel.fit(
        f"[bold]Amount:[/bold] ${amount_dec:,.2f}\n"
        f"[bold]Profit Target:[/bold] {target}%\n"
        f"[bold]Stop Loss:[/bold] {stop}%\n"
        f"[bold]Mode:[/bold] {'TEST' if test else 'LIVE'}",
        title="🚀 AI Investor",
    ))

    # Analyze opportunities
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("🔍 Scanning quality stocks...", total=None)
        picks, market_view, risk_level = investor.analyze_opportunities(amount_dec)

    if not picks:
        console.print("[yellow]No quality opportunities found right now.[/yellow]")
        raise typer.Exit(0)

    # Show market view
    risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(risk_level, "white")
    console.print(f"\n[bold]Market View:[/bold] {market_view}")
    console.print(f"[bold]Risk Level:[/bold] [{risk_color}]{risk_level.upper()}[/{risk_color}]")

    # Show picks
    table = Table(title="\n📋 Investment Plan")
    table.add_column("Symbol", style="cyan")
    table.add_column("Amount", justify="right")
    table.add_column("Alloc", justify="right")
    table.add_column("Strategy", style="yellow")
    table.add_column("Target", justify="right", style="green")
    table.add_column("Stop", justify="right", style="red")

    total = Decimal(0)
    for pick in picks:
        table.add_row(
            pick["symbol"],
            f"${pick['amount']:.2f}",
            f"{pick['allocation_pct']}%",
            pick["strategy"],
            f"+{pick['target_pct']}%",
            f"-{pick['stop_loss_pct']}%",
        )
        total += pick["amount"]

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] ${total:.2f}")

    # Show rationales
    console.print("\n[bold]Analysis:[/bold]")
    for pick in picks:
        tech = pick.get("technicals", {})
        console.print(f"  [cyan]{pick['symbol']}[/cyan]: {pick['rationale'][:100]}...")
        if tech:
            console.print(f"    RSI: {tech.get('rsi', 'N/A'):.1f}, Price: ${tech.get('price', 0):.2f}")

    # Confirm
    if not test and not yes:
        console.print()
        confirm = typer.confirm("Execute trades?", default=False)
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    # Execute
    console.print("\n[bold]💰 Executing trades...[/bold]")
    executed = []
    for pick in picks:
        if investor.execute_buy(pick["symbol"], pick["amount"], test_mode=test):
            executed.append(pick)

    if not executed:
        console.print("[red]No trades executed![/red]")
        raise typer.Exit(1)

    # Track positions in database
    if not test:
        for pick in executed:
            try:
                investor.positions_repo.open_position(
                    symbol=pick["symbol"],
                    quantity=pick["amount"] / pick["price"],
                    entry_price=pick["price"],
                    stop_loss_pct=pick.get("stop_loss_pct", stop),
                    target_pct=pick.get("target_pct", target),
                    strategy=pick.get("strategy"),
                    rationale=pick.get("rationale"),
                )
            except Exception as e:
                logger.warning(f"Could not track {pick['symbol']} in DB: {e}")

    total_executed = sum(p["amount"] for p in executed)
    console.print(f"\n[green]✅ Deployed ${total_executed:.2f} across {len(executed)} positions[/green]")
    console.print("\n[dim]Tip: Use 'bvr ai watch' to monitor positions and auto-exit at targets.[/dim]")


@ai_app.command()
def watch(
    target: float = typer.Option(5.0, "--target", "-t", help="Default profit target % (overridden by DB values)"),
    stop: float = typer.Option(5.0, "--stop", "-s", help="Default stop loss % (overridden by DB values)"),
    interval: int = typer.Option(5, "--interval", "-i", help="Check interval (minutes)"),
    test: bool = typer.Option(False, "--test", help="Test mode (no real sells)"),
) -> None:
    """Monitor positions and auto-exit at targets.
    
    Uses stop/target levels from the database if available (set during invest).
    Falls back to --target and --stop values for positions not in DB.
    
    Note: This uses POLLING, not conditional orders. For production use,
    consider Alpaca's bracket orders for server-side stop/target execution.
    """
    investor = get_investor()

    account = investor.get_account()
    if not account["positions"]:
        console.print("[yellow]No positions to watch.[/yellow]")
        raise typer.Exit(0)

    # Show tracked positions from DB
    db_positions = investor.positions_repo.get_open_positions()
    db_symbols = {p.symbol for p in db_positions}

    console.print(Panel.fit(
        f"[bold]Default Target:[/bold] +{target}%\n"
        f"[bold]Default Stop:[/bold] -{stop}%\n"
        f"[bold]Check Interval:[/bold] {interval} minutes\n"
        f"[bold]DB-Tracked:[/bold] {len(db_positions)} positions\n"
        f"[bold]Mode:[/bold] {'TEST' if test else 'LIVE'}",
        title="👁️  Position Monitor",
    ))

    # Show positions with their targets
    if db_positions:
        console.print("\n[bold]Tracked Positions (from DB):[/bold]")
        for p in db_positions:
            console.print(f"  {p.symbol}: Stop -{p.stop_loss_pct}% | Target +{p.target_pct}%")

    untracked = set(account["positions"].keys()) - db_symbols
    if untracked:
        console.print(f"\n[dim]Untracked (using defaults): {', '.join(untracked)}[/dim]")

    console.print("\nPress Ctrl+C to stop\n")

    try:
        while True:
            _check_exits(investor, target, stop, test)

            # Check if any positions left
            account = investor.get_account()
            if not account["positions"]:
                console.print("\n[green]All positions closed![/green]")
                break

            time.sleep(interval * 60)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped monitoring.[/yellow]")


def _check_exits(investor: AIInvestor, default_target: float, default_stop: float, test: bool) -> None:
    """Check positions for exit signals using DB-tracked or default stop/target levels."""
    account = investor.get_account()

    console.print(f"\n[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] Checking positions...")

    for symbol, pos in account["positions"].items():
        pnl_pct = pos["pnl_pct"]
        pnl_style = "green" if pos["pnl"] >= 0 else "red"

        # Get position-specific stop/target from DB, or use defaults
        db_pos = investor.positions_repo.get_open_position(symbol)
        if db_pos:
            target = db_pos.target_pct
            stop = db_pos.stop_loss_pct
        else:
            target = default_target
            stop = default_stop

        console.print(f"  {symbol}: ${pos['market_value']:.2f} ([{pnl_style}]{pnl_pct:+.2f}%[/{pnl_style}])")

        sold = False
        exit_reason: Optional[str] = None

        if pnl_pct >= target:
            console.print(f"    [green]🎯 PROFIT TARGET HIT! (+{target}%)[/green]")
            sold = investor.execute_sell(symbol, pos["qty"], test_mode=test)
            exit_reason = "target_hit"
        elif pnl_pct <= -stop:
            console.print(f"    [red]🛑 STOP LOSS HIT! (-{stop}%)[/red]")
            sold = investor.execute_sell(symbol, pos["qty"], test_mode=test)
            exit_reason = "stop_loss"

        if sold and exit_reason and db_pos and not test:
            investor.positions_repo.close_position(
                db_pos.id,
                pos["current_price"],
                exit_reason,
            )


@ai_app.command()
def sell(
    symbol: Optional[str] = typer.Argument(None, help="Symbol to sell (omit for all)"),
    all_positions: bool = typer.Option(False, "--all", "-a", help="Sell all positions"),
    test: bool = typer.Option(False, "--test", help="Test mode"),
) -> None:
    """Sell positions."""
    investor = get_investor()
    account = investor.get_account()

    if not account["positions"]:
        console.print("[yellow]No positions to sell.[/yellow]")
        raise typer.Exit(0)

    positions_to_sell = []

    if all_positions or symbol is None:
        positions_to_sell = list(account["positions"].items())
    elif symbol:
        if symbol.upper() not in account["positions"]:
            console.print(f"[red]No position in {symbol.upper()}[/red]")
            raise typer.Exit(1)
        positions_to_sell = [(symbol.upper(), account["positions"][symbol.upper()])]

    console.print(f"\n[bold]Selling {len(positions_to_sell)} position(s)...[/bold]")

    total_value = Decimal(0)
    total_pnl = Decimal(0)

    for sym, pos in positions_to_sell:
        if investor.execute_sell(sym, pos["qty"], test_mode=test):
            total_value += pos["market_value"]
            total_pnl += pos["pnl"]
            # Close position in DB
            if not test:
                db_pos = investor.positions_repo.get_open_position(sym)
                if db_pos:
                    investor.positions_repo.close_position(
                        db_pos.id,
                        pos["current_price"],
                        "manual_sell"
                    )

    pnl_style = "green" if total_pnl >= 0 else "red"
    console.print(f"\n[bold]Total Value:[/bold] ${total_value:.2f}")
    console.print(f"[bold]Total P/L:[/bold] [{pnl_style}]${total_pnl:.2f}[/{pnl_style}]")


@ai_app.command()
def analyze(
    amount: float = typer.Option(1000.0, "--amount", "-a", help="Amount to analyze for"),
) -> None:
    """Analyze market opportunities without trading."""
    investor = get_investor()
    amount_dec = Decimal(str(amount))

    console.print(f"\n[bold]🔍 Analyzing opportunities for ${amount_dec:,.2f}...[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning quality stocks...", total=None)
        opps = investor.get_quality_opportunities()

        progress.update(task, description="Getting technical indicators...")
        with_tech = []
        for opp in opps[:10]:
            tech = investor.get_technical_indicators(opp["symbol"])
            if tech:
                opp["technicals"] = tech
                with_tech.append(opp)

        progress.update(task, description="AI analyzing opportunities...")
        picks, market_view, risk_level = investor.analyze_opportunities(amount_dec)

    # Show all opportunities
    table = Table(title="Quality Opportunities")
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Price", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("RSI", justify="right")
    table.add_column("Signal")

    for opp in with_tech:
        tech = opp.get("technicals", {})
        change_style = "green" if opp["change_pct"] > 0 else "red"

        signal = ""
        if tech.get("oversold"):
            signal = "[green]OVERSOLD[/green]"
        elif tech.get("overbought"):
            signal = "[red]OVERBOUGHT[/red]"
        elif tech.get("above_sma_20"):
            signal = "[cyan]BULLISH[/cyan]"

        table.add_row(
            opp["symbol"],
            opp["type"].upper(),
            f"${tech.get('price', opp['price']):.2f}",
            f"[{change_style}]{opp['change_pct']:+.1f}%[/{change_style}]",
            f"{tech.get('rsi', 0):.1f}",
            signal,
        )

    console.print(table)

    # Show AI picks
    if picks:
        risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(risk_level, "white")
        console.print(f"\n[bold]Market View:[/bold] {market_view}")
        console.print(f"[bold]Risk Level:[/bold] [{risk_color}]{risk_level.upper()}[/{risk_color}]")

        console.print("\n[bold]AI Recommendations:[/bold]")
        for pick in picks:
            console.print(f"  [cyan]{pick['symbol']}[/cyan] ({pick['strategy']}): ${pick['amount']:.2f}")
            console.print(f"    {pick['rationale'][:80]}...")
    else:
        console.print("\n[yellow]AI found no compelling opportunities right now.[/yellow]")


@ai_app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of positions to show"),
    show_open: bool = typer.Option(False, "--open", "-o", help="Show only open positions"),
) -> None:
    """Show AI trading history and performance."""
    investor = get_investor()

    # Get positions
    if show_open:
        positions = investor.positions_repo.get_open_positions()
        title = "Open AI Positions"
    else:
        positions = investor.positions_repo.get_all_positions(limit=limit)
        title = f"AI Trading History (last {limit})"

    if not positions:
        console.print("[dim]No AI trading history found.[/dim]")
        raise typer.Exit(0)

    # Show positions table
    table = Table(title=title)
    table.add_column("Symbol", style="cyan")
    table.add_column("Status")
    table.add_column("Entry", justify="right")
    table.add_column("Exit", justify="right")
    table.add_column("Stop", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("P/L", justify="right")
    table.add_column("Date")

    for pos in positions:
        status_style = {
            "open": "yellow",
            "closed_target": "green",
            "closed_stop": "red",
            "closed_manual": "blue",
        }.get(pos.status, "white")

        pnl_str = ""
        if pos.pnl is not None:
            pnl_style = "green" if pos.pnl >= 0 else "red"
            pnl_str = f"[{pnl_style}]${pos.pnl:.2f} ({pos.pnl_pct:+.1f}%)[/{pnl_style}]"

        table.add_row(
            pos.symbol,
            f"[{status_style}]{pos.status}[/{status_style}]",
            f"${pos.entry_price:.2f}",
            f"${pos.exit_price:.2f}" if pos.exit_price else "-",
            f"-{pos.stop_loss_pct}%",
            f"+{pos.target_pct}%",
            pnl_str,
            pos.entry_timestamp.strftime("%Y-%m-%d"),
        )

    console.print(table)

    # Show summary
    summary = investor.positions_repo.get_performance_summary()
    console.print()
    console.print(Panel.fit(
        f"[bold]Total Positions:[/bold] {summary['total_positions']}\n"
        f"[bold]Open:[/bold] {summary['open_positions']} | [bold]Closed:[/bold] {summary['closed_positions']}\n"
        f"[bold]Win Rate:[/bold] {summary['win_rate']:.1f}% ({summary['winning_trades']}W / {summary['losing_trades']}L)\n"
        f"[bold]Total P/L:[/bold] ${summary['total_pnl']:.2f}\n"
        f"[bold]Avg P/L:[/bold] {summary['avg_pnl_pct']:.1f}%",
        title="📊 Performance Summary",
    ))


# =============================================================================
# AUTONOMOUS TRADING
# =============================================================================

def _setup_auto_logging(log_file: Path) -> None:
    """Set up logging for autonomous mode."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # File handler for autonomous mode
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # Also add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
    root_logger.addHandler(console_handler)

    # Reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)



# =============================================================================
# V2 AI INVESTOR COMMANDS
# =============================================================================


def _build_agent_context_for_symbols(investor: AIInvestor, symbols: list[str]) -> AgentContext:
    """Build a minimal AgentContext for one or more symbols.

    This is used by v2 CLI commands (thesis/DD) so they can call the
    v2 agents directly with a consistent context object.
    """
    from beavr.agents.base import AgentContext
    from beavr.agents.indicators import bars_to_dict_list, calculate_indicators

    account = investor.get_account()

    bars: dict[str, list[dict]] = {}
    indicators: dict[str, dict[str, float]] = {}
    prices: dict[str, Decimal] = {}

    end = date.today()
    start = end - timedelta(days=180)

    for symbol in symbols:
        symbol_u = symbol.upper()
        df = None

        # Retry with exponential backoff for connection errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                df = investor.data_provider.get_bars(symbol_u, start, end)
                break  # Success
            except (ConnectionError, ConnectionResetError, OSError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"Connection error for {symbol_u}, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Failed to fetch bars for {symbol_u} after {max_retries} attempts: {e}")
                    df = None
            except Exception as e:
                # Non-connection errors, don't retry
                logger.warning(f"Error fetching bars for {symbol_u}: {e}")
                df = None
                break

        if df is None or df.empty:
            bars[symbol_u] = []
            indicators[symbol_u] = {}
            prices[symbol_u] = Decimal("0")
            continue

        # Prefer timestamp index (nicer prompts / bar dict dates)
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")

        # Current price from last close
        try:
            prices[symbol_u] = df["close"].iloc[-1]
        except Exception:
            prices[symbol_u] = Decimal("0")

        bars[symbol_u] = bars_to_dict_list(df, n=20)
        indicators[symbol_u] = calculate_indicators(df)

    ctx = AgentContext(
        current_date=date.today(),
        timestamp=datetime.now(),
        prices=prices,
        bars=bars,
        indicators=indicators,
        cash=account["cash"],
        positions={sym: pos["qty"] for sym, pos in account["positions"].items()},
        portfolio_value=account["equity"],
        current_drawdown=0.0,
        peak_value=account["equity"],
        risk_budget=1.0,
        regime=None,
        regime_confidence=0.0,
        events=[],
    )

    return ctx


@ai_app.command()
def news(
    symbols: Optional[str] = typer.Option(
        None, "--symbols", "-s", help="Comma-separated symbols to monitor (default: all)"
    ),
    hours: int = typer.Option(
        24, "--hours", "-h", help="Look back N hours for events"
    ),
) -> None:
    """
    Monitor news and detect trading events.
    
    Uses the NewsMonitorAgent to classify events and identify
    potential trading opportunities.
    """
    from beavr.agents import NewsMonitorAgent
    from beavr.llm import LLMClient, get_agent_config

    console.print()
    console.print(Panel.fit(
        "[bold]📰 News Monitor[/bold]\n"
        f"Looking back: {hours} hours\n"
        f"Symbols: {symbols or 'All universe'}",
        title="AI Investor V2",
    ))

    # Parse symbols (for future use with news filtering)
    _ = [s.strip().upper() for s in symbols.split(",")] if symbols else None

    # Initialize agent
    config = get_agent_config("news_monitor")
    llm = LLMClient(config)
    _agent = NewsMonitorAgent(llm)  # Agent ready for real news API integration

    with console.status("[bold green]Scanning for market events..."):
        # This would normally scan real news sources
        # For now we demonstrate the agent structure
        console.print("\n[dim]News monitor agent initialized[/dim]")
        console.print(f"[dim]Model: {config.model}[/dim]")
        console.print(f"[dim]Temperature: {config.temperature}[/dim]")

    console.print("\n[yellow]Note:[/yellow] Real-time news integration requires external API setup.")
    console.print("See [link=docs/ai_investor/V2_ARCHITECTURE.md]V2 Architecture[/link] for details.")


@ai_app.command()
def thesis(
    event: str = typer.Argument(..., help="Description of the market event"),
    symbol: Optional[str] = typer.Option(
        None, "--symbol", "-s", help="Symbol related to the event"
    ),
    save: bool = typer.Option(
        False, "--save", help="Save thesis to database"
    ),
) -> None:
    """
    Generate investment thesis from a market event.
    
    Uses the ThesisGeneratorAgent to create a hypothesis with
    trade type classification (day trade, swing short/medium/long).
    """
    from beavr.agents import ThesisGeneratorAgent
    from beavr.llm import LLMClient, get_agent_config
    from beavr.models import EventImportance, EventType, MarketEvent

    if not symbol:
        console.print("[red]Error:[/red] --symbol is required to generate a thesis from a manual event")
        raise typer.Exit(1)

    console.print()
    console.print(Panel.fit(
        f"[bold]💡 Thesis Generator[/bold]\n"
        f"Event: {event[:80]}{'...' if len(event) > 80 else ''}\n"
        f"Symbol: {symbol or 'To be determined'}",
        title="AI Investor V2",
    ))

    # Initialize agent
    config = get_agent_config("thesis_generator")
    llm = LLMClient(config)
    agent = ThesisGeneratorAgent(llm)

    # Create event object
    market_event = MarketEvent(
        event_type=EventType.NEWS_CATALYST,
        symbol=symbol.upper(),
        headline=event,
        summary=event,
        source="manual_input",
        importance=EventImportance.MEDIUM,
    )

    ctx = _build_agent_context_for_symbols(investor=get_investor(), symbols=[symbol])

    with console.status("[bold green]Generating investment thesis..."):
        thesis_obj = agent.generate_thesis_from_event(market_event, ctx)

    if not thesis_obj:
        console.print("\n[yellow]NO THESIS[/yellow] - event did not produce a tradeable hypothesis.")
        raise typer.Exit(0)

    console.print()
    table = Table(title="📋 Generated Thesis")
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Thesis ID", thesis_obj.id)
    table.add_row("Symbol", thesis_obj.symbol)
    table.add_row("Direction", thesis_obj.direction.value)
    table.add_row("Trade Type", thesis_obj.trade_type.value)
    table.add_row("Entry Target", f"${thesis_obj.entry_price_target:.2f}")
    table.add_row("Profit Target", f"${thesis_obj.profit_target:.2f} (+{thesis_obj.target_pct:.1f}%)")
    table.add_row("Stop Loss", f"${thesis_obj.stop_loss:.2f} (-{thesis_obj.stop_pct:.1f}%)")
    table.add_row("R/R", f"{thesis_obj.risk_reward_ratio:.2f}:1")
    table.add_row("Expected Exit", thesis_obj.expected_exit_date.isoformat())
    table.add_row("Max Hold", thesis_obj.max_hold_date.isoformat())
    table.add_row("Catalyst", thesis_obj.catalyst[:120])
    table.add_row("Rationale", thesis_obj.entry_rationale[:120])
    table.add_row("Confidence", f"{thesis_obj.confidence:.0%}")

    console.print(table)

    if save:
        try:
            from beavr.db.thesis_repo import ThesisRepository

            repo = ThesisRepository(get_investor().db)
            repo.create(thesis_obj)
            console.print("\n[green]✓[/green] Thesis saved to database")
        except Exception as e:
            console.print(f"\n[yellow]Warning:[/yellow] Could not save thesis to DB: {e}")


@ai_app.command()
def dd(
    thesis_id: Optional[str] = typer.Option(
        None, "--thesis-id", "-t", help="Thesis ID to analyze"
    ),
    symbol: Optional[str] = typer.Option(
        None, "--symbol", "-s", help="Symbol to research"
    ),
    rationale: Optional[str] = typer.Option(
        None, "--rationale", "-r", help="Investment rationale"
    ),
    trade_type: str = typer.Option(
        "swing_short",
        "--trade-type",
        help="Trade type for ad-hoc DD when --symbol is used (day_trade, swing_short, swing_medium, swing_long)",
    ),
    catalyst: str = typer.Option(
        "Manual DD analysis",
        "--catalyst",
        help="Catalyst description for ad-hoc DD when --symbol is used",
    ),
    save: bool = typer.Option(
        True, "--save/--no-save", help="Save DD report to logs/dd_reports/"
    ),
) -> None:
    """
    Run deep due diligence analysis.
    
    Uses the DueDiligenceAgent to perform comprehensive research.
    Best run during non-market hours for deep analysis.
    
    The DD report includes:
    - Trade type classification (day/swing)
    - Entry/exit strategy
    - Risk assessment
    - Price targets
    """
    from beavr.agents import DueDiligenceAgent
    from beavr.llm import LLMClient, get_agent_config
    from beavr.models import TradeThesis, TradeType

    # Validate input
    if not thesis_id and not symbol:
        console.print("[red]Error:[/red] Provide either --thesis-id or --symbol")
        raise typer.Exit(1)

    console.print()
    console.print(Panel.fit(
        f"[bold]🔬 Due Diligence Agent[/bold]\n"
        f"{'Thesis ID: ' + str(thesis_id) if thesis_id else 'Symbol: ' + (symbol or 'N/A')}\n"
        f"Save report: {save}",
        title="AI Investor V2",
    ))

    # Check market hours
    now = datetime.now(ET)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    if market_open <= now <= market_close and now.weekday() < 5:
        console.print("\n[yellow]⚠ Market is open.[/yellow] DD analysis is best run during non-market hours.")
        console.print("Consider running this command before market open or after close.\n")

    # Create or load thesis
    thesis_obj: TradeThesis

    if thesis_id:
        try:
            from beavr.db.thesis_repo import ThesisRepository

            repo = ThesisRepository(get_investor().db)
            loaded = repo.get(thesis_id)
            if loaded is None:
                console.print(f"[red]Error:[/red] No thesis found with id '{thesis_id}'")
                raise typer.Exit(1)
            thesis_obj = loaded
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to load thesis from DB: {e}")
            raise typer.Exit(1) from e
    else:
        if not symbol:
            console.print("[red]Error:[/red] Provide either --thesis-id or --symbol")
            raise typer.Exit(1)

        try:
            trade_type_enum = TradeType(trade_type.lower())
        except Exception as err:
            console.print("[red]Error:[/red] Invalid --trade-type. Use: day_trade, swing_short, swing_medium, swing_long")
            raise typer.Exit(1) from err

        sym = symbol.upper()
        ctx_for_price = _build_agent_context_for_symbols(investor=get_investor(), symbols=[sym])
        current_price = ctx_for_price.prices.get(sym, Decimal("0"))
        if current_price <= 0:
            console.print(f"[red]Error:[/red] Could not fetch price/bars for {sym}")
            raise typer.Exit(1)

        # Build a reasonable placeholder thesis around current price.
        entry = current_price.quantize(Decimal("0.01"))
        profit_target = (current_price * (Decimal("1") + Decimal(str(trade_type_enum.default_target_pct)) / Decimal("100"))).quantize(
            Decimal("0.01")
        )
        stop_loss = (current_price * (Decimal("1") - Decimal(str(trade_type_enum.default_stop_pct)) / Decimal("100"))).quantize(
            Decimal("0.01")
        )

        today = date.today()
        expected_exit_days = {
            TradeType.DAY_TRADE: 0,
            TradeType.SWING_SHORT: 10,
            TradeType.SWING_MEDIUM: 45,
            TradeType.SWING_LONG: 180,
        }[trade_type_enum]

        thesis_obj = TradeThesis(
            symbol=sym,
            trade_type=trade_type_enum,
            entry_rationale=rationale or f"Perform due diligence on {sym} for a potential trade",
            catalyst=catalyst,
            entry_price_target=entry,
            profit_target=profit_target,
            stop_loss=stop_loss,
            expected_exit_date=today + timedelta(days=expected_exit_days),
            max_hold_date=today + timedelta(days=trade_type_enum.max_hold_days),
            invalidation_conditions=[
                "Breaks key support / invalidates technical setup",
                "Catalyst no longer valid or negative new information emerges",
            ],
            source="manual_dd",
        )

    # Build agent context (include the thesis symbol)
    ctx = _build_agent_context_for_symbols(investor=get_investor(), symbols=[thesis_obj.symbol])

    # Initialize agent (save handled by CLI so we can print exact file paths)
    config = get_agent_config("due_diligence")
    llm = LLMClient(config)
    agent = DueDiligenceAgent(llm, save_reports=False)

    console.print(f"[dim]Model: {config.model} (optimized for deep research)[/dim]")

    with console.status("[bold green]Running deep due diligence analysis..."):
        report = agent.analyze_thesis(thesis_obj, ctx)

    console.print()
    console.print(Panel.fit(
        f"[bold]{report.recommendation.value.upper()}[/bold] ({report.recommended_trade_type.value})\n"
        f"Confidence: {report.confidence:.0%}\n\n"
        f"Entry: ${report.recommended_entry:.2f}\n"
        f"Target: ${report.recommended_target:.2f} (+{report.target_pct:.1f}%)\n"
        f"Stop: ${report.recommended_stop:.2f} (-{report.stop_pct:.1f}%)\n"
        f"R/R: {report.risk_reward_ratio:.2f}:1\n\n"
        f"Summary: {report.executive_summary}",
        title="🔬 Due Diligence Report",
    ))

    if report.day_trade_plan:
        console.print(Panel.fit(
            f"Entry Window: {report.day_trade_plan.entry_window_start} - {report.day_trade_plan.entry_window_end} ET\n"
            f"Exit Deadline: {report.day_trade_plan.exit_deadline} ET\n"
            f"Confirmation: {report.day_trade_plan.opening_range_confirmation}",
            title="⚡ Day Trade Plan",
        ))

    if report.swing_trade_plan:
        console.print(Panel.fit(
            f"Entry Strategy: {report.swing_trade_plan.entry_strategy}\n"
            f"Key Dates: {', '.join(report.swing_trade_plan.key_dates_to_monitor) if report.swing_trade_plan.key_dates_to_monitor else 'N/A'}",
            title="📆 Swing Trade Plan",
        ))

    if save:
        try:
            json_path, md_path = report.save("logs/dd_reports")
            console.print(f"\n[green]✓[/green] JSON saved to {json_path}")
            console.print(f"[green]✓[/green] Markdown saved to {md_path}")
        except Exception as e:
            console.print(f"\n[yellow]Warning:[/yellow] Failed to save report: {e}")


@ai_app.command()
def power_hour(
    amount: float = typer.Argument(..., help="Amount in USD to invest"),
    test: bool = typer.Option(
        True, "--test/--live", help="Test mode (no real trades)"
    ),
) -> None:
    """
    Execute Power Hour trading strategy.

    Power Hour strategy:
    1. Wait until 9:35 AM (after 5-min opening range)
    2. Analyze opening range breakout/breakdown
    3. Enter positions based on morning momentum
    4. Exit all positions by 10:30 AM (within 1 hour)

    This is a day trading strategy focused on the first hour of market open.
    """
    from beavr.agents import PositionManagerAgent, TradeExecutorAgent
    from beavr.llm import LLMClient, get_agent_config

    console.print()
    console.print(Panel.fit(
        f"[bold]⚡ Power Hour Strategy[/bold]\n\n"
        f"Amount: ${amount:,.2f}\n"
        f"Mode: {'TEST (no real trades)' if test else '[red]LIVE[/red]'}\n\n"
        f"Window: 9:35 AM - 10:30 AM ET\n"
        f"Strategy: Opening range breakout",
        title="AI Investor V2",
    ))

    # Check if we're in the right time window
    now = datetime.now(ET)
    opening_range_end = now.replace(hour=9, minute=35, second=0, microsecond=0)
    power_hour_end = now.replace(hour=10, minute=30, second=0, microsecond=0)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)

    if now.weekday() >= 5:
        console.print("\n[red]Error:[/red] Market is closed (weekend)")
        raise typer.Exit(1)

    if now < market_open:
        wait_time = (market_open - now).total_seconds() / 60
        console.print(f"\n[yellow]Market opens in {wait_time:.0f} minutes[/yellow]")
        console.print("Power Hour starts at 9:35 AM ET")
        raise typer.Exit(0)

    if now > power_hour_end:
        console.print("\n[yellow]Power Hour window has ended (10:30 AM)[/yellow]")
        console.print("Run this command between 9:30 AM - 10:30 AM ET")
        raise typer.Exit(0)

    if now < opening_range_end:
        wait_secs = (opening_range_end - now).total_seconds()
        console.print(f"\n[yellow]Waiting for opening range to form ({wait_secs:.0f}s)...[/yellow]")

    # Initialize agents
    executor_config = get_agent_config("trade_executor")
    executor_llm = LLMClient(executor_config)
    executor = TradeExecutorAgent(executor_llm)

    position_config = get_agent_config("position_manager")
    position_llm = LLMClient(position_config)
    _position_manager = PositionManagerAgent(position_llm)  # For exit monitoring

    console.print(f"\n[dim]Executor model: {executor_config.model}[/dim]")
    console.print(f"[dim]Position manager model: {position_config.model}[/dim]")

    # Check if execution is allowed
    can_execute, reason = executor.can_execute_now()
    if not can_execute:
        console.print(f"\n[yellow]Cannot execute:[/yellow] {reason}")
        raise typer.Exit(0)

    console.print("\n[green]✓[/green] Execution window is open")
    console.print("[dim]Power Hour strategy would analyze opening range and execute trades[/dim]")

    if test:
        console.print("\n[yellow]TEST MODE:[/yellow] No real trades will be executed")
    else:
        console.print("\n[red]LIVE MODE:[/red] Real trades would be executed")


@ai_app.command()
def auto(
    target_return: float = typer.Option(20.0, "--target", "-t", help="Target return % (annualized)"),
    max_drawdown: float = typer.Option(10.0, "--max-dd", help="Maximum drawdown %"),
    day_trade_target: float = typer.Option(5.0, "--dt-target", help="Day trade profit target %"),
    day_trade_stop: float = typer.Option(3.0, "--dt-stop", help="Day trade stop loss %"),
    daily_limit: int = typer.Option(5, "--daily-limit", "-d", help="Maximum trades per day"),
    capital_pct: float = typer.Option(80.0, "--capital", "-c", help="% of portfolio to use"),
    research_interval: int = typer.Option(15, "--research-interval", help="Research cycle interval (minutes)"),
    test: bool = typer.Option(False, "--test", help="Test mode (no real trades)"),
    once: bool = typer.Option(False, "--once", help="Run one cycle then exit"),
) -> None:
    """
    Run autonomous AI trading (thesis-driven).
    
    This is the FULLY AUTOMATED trading system that:
    
    1. OVERNIGHT (8 PM - 6 AM): Deep DD research on candidates
    2. PRE-MARKET (4 AM - 9:30 AM): Morning momentum scan
    3. POWER HOUR (9:35 - 10:30 AM): Day trade execution
    4. MARKET HOURS (10:30 AM - 4 PM): Position management
    5. AFTER HOURS (4 PM - 8 PM): Learning & prep
    
    The system runs 24/7, coordinating all AI agents:
    - News Monitor (continuous)
    - Thesis Generator (event-driven)
    - Due Diligence Agent (overnight)
    - Morning Scanner (pre-market)
    - Trade Executor (market hours)
    - Position Manager (market hours)
    
    Example:
        bvr ai auto --target 20 --max-dd 10 --dt-target 5 --dt-stop 3 &
    """
    from beavr.agents import (
        DueDiligenceAgent,
        MorningScannerAgent,
        NewsMonitorAgent,
        PositionManagerAgent,
        ThesisGeneratorAgent,
        TradeExecutorAgent,
    )
    from beavr.db import DDReportsRepository, EventsRepository, ThesisRepository
    from beavr.llm import LLMClient, get_agent_config
    from beavr.orchestrator import V2AutonomousOrchestrator, V2Config

    investor = get_investor()

    # Set up logging
    log_dir = Path("logs/ai_investor")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"v2_auto_{datetime.now().strftime('%Y%m%d')}.log"
    _setup_auto_logging(log_file)

    logger.info("=" * 60)
    logger.info("🤖 AUTONOMOUS AI TRADING")
    logger.info("=" * 60)
    logger.info(f"Target Return: {target_return}%")
    logger.info(f"Max Drawdown: {max_drawdown}%")
    logger.info(f"Day Trade: +{day_trade_target}% / -{day_trade_stop}%")
    logger.info(f"Daily Trade Limit: {daily_limit}")
    logger.info(f"Capital Allocation: {capital_pct}%")
    logger.info(f"Research Interval: {research_interval} minutes")
    logger.info(f"Mode: {'TEST' if test else 'LIVE'}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 60)

    console.print(Panel.fit(
        f"[bold]🤖 Autonomous AI Trading[/bold]\n\n"
        f"Target Return: {target_return}%\n"
        f"Max Drawdown: {max_drawdown}%\n"
        f"Day Trade: +{day_trade_target}% / -{day_trade_stop}% (R/R {day_trade_target/day_trade_stop:.1f}:1)\n"
        f"Daily Limit: {daily_limit} trades\n"
        f"Capital: {capital_pct}%\n\n"
        f"Research Interval: {research_interval} min\n"
        f"Mode: {'[yellow]TEST[/yellow]' if test else '[green]LIVE[/green]'}\n"
        f"Log: {log_file}",
        title="Autonomous Trading",
    ))

    # Build configuration
    config = V2Config(
        max_daily_loss_pct=3.0,  # 3% daily max loss
        max_drawdown_pct=max_drawdown,
        capital_allocation_pct=capital_pct / 100,
        daily_trade_limit=daily_limit,
        day_trade_target_pct=day_trade_target,
        day_trade_stop_pct=day_trade_stop,
        news_poll_interval=research_interval * 60,
        market_research_interval=research_interval * 60,
        state_file=str(log_dir / "v2_state.json"),
        log_dir=str(log_dir),
    )

    # Initialize agents
    console.print("\n[dim]Initializing agents...[/dim]")

    news_config = get_agent_config("news_monitor")
    news_llm = LLMClient(news_config)
    news_monitor = NewsMonitorAgent(news_llm)

    thesis_config = get_agent_config("thesis_generator")
    thesis_llm = LLMClient(thesis_config)
    thesis_generator = ThesisGeneratorAgent(thesis_llm)

    dd_config = get_agent_config("due_diligence")
    dd_llm = LLMClient(dd_config)
    dd_agent = DueDiligenceAgent(dd_llm)

    scanner_config = get_agent_config("morning_scanner")
    scanner_llm = LLMClient(scanner_config)
    morning_scanner = MorningScannerAgent(scanner_llm)

    executor_config = get_agent_config("trade_executor")
    executor_llm = LLMClient(executor_config)
    trade_executor = TradeExecutorAgent(executor_llm)

    position_config = get_agent_config("position_manager")
    position_llm = LLMClient(position_config)
    position_manager = PositionManagerAgent(position_llm)

    console.print("[green]✓[/green] Agents initialized")

    # Initialize repositories
    thesis_repo = ThesisRepository(investor.db)
    dd_repo = DDReportsRepository(investor.db)
    events_repo = EventsRepository(investor.db)

    console.print("[green]✓[/green] Database connected")

    # Create orchestrator
    orchestrator = V2AutonomousOrchestrator(
        news_monitor=news_monitor,
        thesis_generator=thesis_generator,
        dd_agent=dd_agent,
        morning_scanner=morning_scanner,
        trade_executor=trade_executor,
        position_manager=position_manager,
        thesis_repo=thesis_repo,
        dd_repo=dd_repo,
        events_repo=events_repo,
        positions_repo=investor.positions_repo,
        config=config,
    )

    # Set trading clients (unless test mode)
    if not test:
        orchestrator.set_trading_client(investor.broker, investor.data_provider)
    
    # Set context builder
    orchestrator.set_context_builder(
        lambda symbols: _build_agent_context_for_symbols(investor, symbols)
    )

    console.print("[green]✓[/green] Orchestrator ready")

    # Show account status
    try:
        account = investor.get_account()
        console.print("\n[bold]Account Status[/bold]")
        console.print(f"  Portfolio Value: ${account['equity']:,.2f}")
        console.print(f"  Cash Available: ${account['cash']:,.2f}")
        console.print(f"  Open Positions: {len(account['positions'])}")
        if account['positions']:
            for sym, pos in account['positions'].items():
                console.print(f"    {sym}: ${pos['market_value']:.2f} ({pos['pnl_pct']:+.1f}%)")
    except Exception as e:
        logger.warning(f"Could not get account status: {e}")

    console.print(f"\n[bold green]Starting Autonomous Trading{'...' if not once else ' (single cycle)'}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        if once:
            # Run one cycle for testing
            logger.info("Running single cycle (--once flag)")
            phase = orchestrator._get_current_phase()
            logger.info(f"Current phase: {phase.value}")
            
            if phase.value == "overnight_dd":
                orchestrator._run_overnight_dd_cycle()
            elif phase.value == "pre_market":
                candidates = orchestrator._run_pre_market_scan()
                logger.info(f"Pre-market candidates: {candidates}")
            elif phase.value == "power_hour":
                orchestrator._execute_power_hour([])
            else:
                orchestrator._monitor_positions()
            
            logger.info("Single cycle complete")
        else:
            # Run the full autonomous loop
            orchestrator.run()
            
    except KeyboardInterrupt:
        logger.info("⛔ Shutdown requested")
        orchestrator.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

    console.print("\n[bold]Autonomous Trading stopped[/bold]")

