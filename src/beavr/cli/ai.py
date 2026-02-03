"""
Beavr AI Investor CLI - Autonomous AI-powered trading.

Commands:
    bvr ai status     - Show portfolio and AI status
    bvr ai invest     - Invest a specified amount using AI
    bvr ai watch      - Monitor positions and auto-exit at targets
    bvr ai sell       - Sell positions (specific or all)
    bvr ai analyze    - Analyze market without trading
"""

import logging
import os
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from beavr.core.config import get_settings

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
        self._trading = None
        self._data = None
        self._llm = None
        self._screener = None
        self._fetcher = None
    
    @property
    def trading(self):
        """Lazy load trading client."""
        if self._trading is None:
            from alpaca.trading.client import TradingClient
            settings = get_settings()
            self._trading = TradingClient(
                settings.alpaca_api_key,
                settings.alpaca_api_secret,
                paper=True,
            )
        return self._trading
    
    @property
    def data(self):
        """Lazy load data client."""
        if self._data is None:
            from alpaca.data.historical.stock import StockHistoricalDataClient
            settings = get_settings()
            self._data = StockHistoricalDataClient(
                settings.alpaca_api_key,
                settings.alpaca_api_secret,
            )
        return self._data
    
    @property
    def llm(self):
        """Lazy load LLM client."""
        if self._llm is None:
            from beavr.llm.client import LLMClient
            self._llm = LLMClient()
        return self._llm
    
    @property
    def screener(self):
        """Lazy load market screener."""
        if self._screener is None:
            from beavr.data.screener import MarketScreener
            settings = get_settings()
            self._screener = MarketScreener(
                settings.alpaca_api_key,
                settings.alpaca_api_secret,
            )
        return self._screener
    
    @property
    def fetcher(self):
        """Lazy load data fetcher."""
        if self._fetcher is None:
            from beavr.data.alpaca import AlpacaDataFetcher
            settings = get_settings()
            self._fetcher = AlpacaDataFetcher(
                settings.alpaca_api_key,
                settings.alpaca_api_secret,
            )
        return self._fetcher
    
    def get_account(self) -> dict:
        """Get account status."""
        account = self.trading.get_account()
        positions = self.trading.get_all_positions()
        
        return {
            "equity": Decimal(account.equity),
            "cash": Decimal(account.cash),
            "buying_power": Decimal(account.buying_power),
            "positions": {
                p.symbol: {
                    "qty": Decimal(p.qty),
                    "avg_entry": Decimal(p.avg_entry_price),
                    "current_price": Decimal(p.current_price),
                    "market_value": Decimal(p.market_value),
                    "pnl": Decimal(p.unrealized_pl),
                    "pnl_pct": float(p.unrealized_plpc) * 100,
                }
                for p in positions
            }
        }
    
    def get_quality_opportunities(self) -> list[dict]:
        """Get market movers filtered for quality."""
        result = self.screener.get_market_movers(top_n=20)
        
        opportunities = []
        
        # Filter gainers
        for m in result.top_gainers:
            if is_quality_stock(m.symbol, float(m.price)):
                opportunities.append({
                    "symbol": m.symbol,
                    "price": float(m.price),
                    "change_pct": m.percent_change,
                    "type": "gainer",
                    "in_universe": m.symbol in QUALITY_UNIVERSE,
                })
        
        # Filter losers (potential bounces)
        for m in result.top_losers:
            if is_quality_stock(m.symbol, float(m.price)):
                opportunities.append({
                    "symbol": m.symbol,
                    "price": float(m.price),
                    "change_pct": m.percent_change,
                    "type": "loser",
                    "in_universe": m.symbol in QUALITY_UNIVERSE,
                })
        
        # Sort to prioritize quality universe stocks
        opportunities.sort(key=lambda x: (not x["in_universe"], -abs(x["change_pct"])))
        
        return opportunities
    
    def get_technical_indicators(self, symbol: str) -> Optional[dict]:
        """Calculate technical indicators for a symbol."""
        try:
            bars = self.fetcher.get_bars(
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
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        
        try:
            # Get current price
            bars = self.fetcher.get_bars(symbol, date.today() - timedelta(days=5), date.today())
            if bars.empty:
                return False
            
            price = Decimal(str(bars["close"].iloc[-1]))
            qty = float(amount / price)
            
            if test_mode:
                console.print(f"  [yellow][TEST][/yellow] Would BUY {qty:.4f} {symbol} @ ${price:.2f} = ${amount:.2f}")
                return True
            
            # Try fractional first
            try:
                self.trading.submit_order(
                    MarketOrderRequest(
                        symbol=symbol,
                        qty=round(qty, 4),
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY,
                    )
                )
                console.print(f"  [green]✅ BUY[/green] {qty:.4f} {symbol} @ ~${price:.2f} = ${amount:.2f}")
                return True
            except Exception as e:
                if "not fractionable" in str(e):
                    whole_qty = int(qty)
                    if whole_qty >= 1:
                        self.trading.submit_order(
                            MarketOrderRequest(
                                symbol=symbol,
                                qty=whole_qty,
                                side=OrderSide.BUY,
                                time_in_force=TimeInForce.DAY,
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
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        
        try:
            if test_mode:
                console.print(f"  [yellow][TEST][/yellow] Would SELL {qty} {symbol}")
                return True
            
            self.trading.submit_order(
                MarketOrderRequest(
                    symbol=symbol,
                    qty=float(qty),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
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
    watch: bool = typer.Option(False, "--watch", "-w", help="Monitor after investing"),
) -> None:
    """Invest a specified amount using AI analysis."""
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
    
    total_executed = sum(p["amount"] for p in executed)
    console.print(f"\n[green]✅ Deployed ${total_executed:.2f} across {len(executed)} positions[/green]")
    
    # Watch mode
    if watch and not test:
        console.print(f"\n[bold]👁️  Monitoring every 5 minutes[/bold]")
        console.print(f"  Target: +{target}% | Stop: -{stop}%")
        console.print("  Press Ctrl+C to stop\n")
        
        try:
            while True:
                time.sleep(300)
                _check_exits(investor, target, stop, test)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped monitoring.[/yellow]")


@ai_app.command()
def watch(
    target: float = typer.Option(5.0, "--target", "-t", help="Profit target %"),
    stop: float = typer.Option(5.0, "--stop", "-s", help="Stop loss %"),
    interval: int = typer.Option(5, "--interval", "-i", help="Check interval (minutes)"),
    test: bool = typer.Option(False, "--test", help="Test mode (no real sells)"),
) -> None:
    """Monitor positions and auto-exit at targets."""
    investor = get_investor()
    
    account = investor.get_account()
    if not account["positions"]:
        console.print("[yellow]No positions to watch.[/yellow]")
        raise typer.Exit(0)
    
    console.print(Panel.fit(
        f"[bold]Profit Target:[/bold] +{target}%\n"
        f"[bold]Stop Loss:[/bold] -{stop}%\n"
        f"[bold]Check Interval:[/bold] {interval} minutes\n"
        f"[bold]Mode:[/bold] {'TEST' if test else 'LIVE'}",
        title="👁️  Position Monitor",
    ))
    
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


def _check_exits(investor: AIInvestor, target: float, stop: float, test: bool) -> None:
    """Check positions for exit signals."""
    account = investor.get_account()
    
    console.print(f"\n[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] Checking positions...")
    
    for symbol, pos in account["positions"].items():
        pnl_pct = pos["pnl_pct"]
        pnl_style = "green" if pos["pnl"] >= 0 else "red"
        
        console.print(f"  {symbol}: ${pos['market_value']:.2f} ([{pnl_style}]{pnl_pct:+.2f}%[/{pnl_style}])")
        
        if pnl_pct >= target:
            console.print(f"    [green]🎯 PROFIT TARGET HIT![/green]")
            investor.execute_sell(symbol, pos["qty"], test_mode=test)
        elif pnl_pct <= -stop:
            console.print(f"    [red]🛑 STOP LOSS HIT![/red]")
            investor.execute_sell(symbol, pos["qty"], test_mode=test)


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
