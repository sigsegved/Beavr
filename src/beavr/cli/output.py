"""Rich output formatting for CLI commands."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from beavr.backtest.engine import BacktestResult


def _format_money(value: Decimal | float) -> str:
    """Format a value as currency."""
    val = float(value) if isinstance(value, Decimal) else value
    return f"${val:,.2f}"


def _format_percent(value: Decimal | float, show_sign: bool = True) -> str:
    """Format a value as percentage."""
    val = float(value) if isinstance(value, Decimal) else value
    val_pct = val * 100
    if show_sign and val >= 0:
        return f"+{val_pct:.2f}%"
    return f"{val_pct:.2f}%"


def _format_shares(value: Decimal | float) -> str:
    """Format a value as shares."""
    val = float(value) if isinstance(value, Decimal) else value
    return f"{val:.4f}"


def print_backtest_result(result: BacktestResult, console: Console) -> None:
    """Print formatted backtest results."""
    metrics = result.metrics
    
    # Header
    strategy_name = result.config.strategy_name
    console.print()
    console.print(
        Panel(
            f"[bold cyan]📊 Backtest Results: {strategy_name}[/bold cyan]",
            expand=False,
        )
    )
    
    # Strategy Info
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Label", style="dim")
    info_table.add_column("Value")
    
    symbols = ", ".join(result.config.symbols)
    start_date = result.config.start_date.strftime("%Y-%m-%d")
    end_date = result.config.end_date.strftime("%Y-%m-%d")
    years = (result.config.end_date - result.config.start_date).days / 365.25
    
    info_table.add_row("Strategy:", strategy_name)
    info_table.add_row("Symbols:", symbols)
    info_table.add_row("Period:", f"{start_date} to {end_date} ({years:.1f} years)")
    
    console.print(info_table)
    console.print()
    
    # Performance Section
    console.print("[bold]💰 Performance[/bold]")
    console.print("─" * 40)
    
    perf_table = Table(show_header=False, box=None, padding=(0, 2))
    perf_table.add_column("Label", style="dim")
    perf_table.add_column("Value", justify="right")
    
    initial_cash = result.config.initial_cash
    final_value = result.final_value
    total_return = metrics.total_return
    cagr = metrics.cagr
    
    # Color for returns
    return_color = "green" if float(total_return) >= 0 else "red"
    cagr_color = "green" if float(cagr) >= 0 else "red"
    
    perf_table.add_row("Initial Cash:", _format_money(initial_cash))
    perf_table.add_row("Total Invested:", _format_money(metrics.total_invested))
    perf_table.add_row("Final Value:", _format_money(final_value))
    perf_table.add_row(
        "Total Return:",
        f"[{return_color}]{_format_percent(total_return)}[/{return_color}]"
    )
    perf_table.add_row(
        "CAGR:",
        f"[{cagr_color}]{_format_percent(cagr)}[/{cagr_color}]"
    )
    
    console.print(perf_table)
    console.print()
    
    # Risk Section
    console.print("[bold]📉 Risk[/bold]")
    console.print("─" * 40)
    
    risk_table = Table(show_header=False, box=None, padding=(0, 2))
    risk_table.add_column("Label", style="dim")
    risk_table.add_column("Value", justify="right")
    
    max_dd = metrics.max_drawdown
    sharpe = metrics.sharpe_ratio
    
    dd_color = "red" if float(max_dd) < -0.1 else "yellow" if float(max_dd) < 0 else "green"
    
    risk_table.add_row(
        "Max Drawdown:",
        f"[{dd_color}]{_format_percent(max_dd, show_sign=False)}[/{dd_color}]"
    )
    if sharpe is not None:
        sharpe_color = "green" if float(sharpe) > 1 else "yellow" if float(sharpe) > 0 else "red"
        risk_table.add_row(
            "Sharpe Ratio:",
            f"[{sharpe_color}]{float(sharpe):.2f}[/{sharpe_color}]"
        )
    else:
        risk_table.add_row("Sharpe Ratio:", "[dim]N/A[/dim]")
    
    console.print(risk_table)
    console.print()
    
    # Trades Section
    console.print("[bold]📈 Trades[/bold]")
    console.print("─" * 40)
    
    trades_table = Table(show_header=False, box=None, padding=(0, 2))
    trades_table.add_column("Label", style="dim")
    trades_table.add_column("Value", justify="right")
    
    total_trades = metrics.total_trades
    buy_trades = metrics.buy_trades
    sell_trades = metrics.sell_trades
    
    trades_table.add_row("Total Trades:", str(total_trades))
    trades_table.add_row("Buy Trades:", str(buy_trades))
    trades_table.add_row("Sell Trades:", str(sell_trades))
    
    console.print(trades_table)
    console.print()
    
    # Holdings Section
    if result.final_positions:
        console.print("[bold]💼 Holdings[/bold]")
        console.print("─" * 40)
        
        holdings_table = Table(show_header=True, box=None, padding=(0, 2))
        holdings_table.add_column("Symbol", style="bold")
        holdings_table.add_column("Shares", justify="right")
        holdings_table.add_column("Avg Cost", justify="right")
        holdings_table.add_column("Value", justify="right")
        
        for symbol, position in result.final_positions.items():
            price = result.final_prices.get(symbol, Decimal("0"))
            value = position.quantity * price
            holdings_table.add_row(
                symbol,
                _format_shares(position.quantity),
                _format_money(position.avg_cost),
                _format_money(value),
            )
        
        console.print(holdings_table)
        console.print()
    
    console.print(f"[dim]Run ID: {result.run_id}[/dim]")


def print_comparison_table(
    results: list[BacktestResult],
    console: Console,
) -> None:
    """Print side-by-side comparison of multiple strategies."""
    console.print()
    console.print(
        Panel("[bold cyan]📊 Strategy Comparison[/bold cyan]", expand=False)
    )
    
    table = Table(show_header=True)
    table.add_column("Metric", style="dim")
    
    for result in results:
        table.add_column(result.config.strategy_name, justify="right")
    
    # Add rows
    table.add_row(
        "Total Return",
        *[_format_percent(r.metrics.total_return) for r in results]
    )
    table.add_row(
        "CAGR",
        *[_format_percent(r.metrics.cagr) for r in results]
    )
    table.add_row(
        "Max Drawdown",
        *[_format_percent(r.metrics.max_drawdown, show_sign=False) for r in results]
    )
    table.add_row(
        "Sharpe Ratio",
        *[
            f"{float(r.metrics.sharpe_ratio):.2f}" if r.metrics.sharpe_ratio else "N/A"
            for r in results
        ]
    )
    table.add_row(
        "Total Trades",
        *[str(r.metrics.total_trades) for r in results]
    )
    table.add_row(
        "Final Value",
        *[_format_money(r.final_value) for r in results]
    )
    
    console.print(table)
    console.print()


def print_run_list(runs: list[dict], console: Console) -> None:
    """Print list of past backtest runs."""
    if not runs:
        console.print("[yellow]No backtest runs found.[/yellow]")
        return
    
    table = Table(show_header=True)
    table.add_column("Run ID", style="dim")
    table.add_column("Strategy")
    table.add_column("Symbols")
    table.add_column("Period")
    table.add_column("Return", justify="right")
    table.add_column("Created", style="dim")
    
    for run in runs:
        run_id = run.get("id", run.get("run_id", ""))[:8] + "..."
        strategy = run.get("strategy_name", "N/A")
        symbols = run.get("symbols", "N/A")
        
        start = run.get("start_date", "")
        end = run.get("end_date", "")
        period = f"{start} to {end}" if start and end else "N/A"
        
        total_return = run.get("total_return")
        if total_return is not None:
            return_str = _format_percent(Decimal(str(total_return)))
        else:
            return_str = "N/A"
        
        created = run.get("created_at", "N/A")
        if created:
            if hasattr(created, "strftime"):
                created = created.strftime("%Y-%m-%d")
            elif isinstance(created, str) and len(created) > 10:
                created = created[:10]
        
        table.add_row(run_id, strategy, symbols, period, return_str, str(created))
    
    console.print(table)


def print_run_detail(run: dict, console: Console) -> None:
    """Print details of a specific backtest run."""
    console.print()
    console.print(
        Panel(f"[bold cyan]📊 Backtest Run Details[/bold cyan]", expand=False)
    )
    
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Label", style="dim")
    info_table.add_column("Value")
    
    info_table.add_row("Run ID:", str(run.get("id", run.get("run_id", "N/A"))))
    info_table.add_row("Strategy:", str(run.get("strategy_name", "N/A")))
    info_table.add_row("Symbols:", str(run.get("symbols", "N/A")))
    info_table.add_row("Period:", f"{run.get('start_date', '')} to {run.get('end_date', '')}")
    info_table.add_row("Initial Cash:", _format_money(Decimal(str(run.get("initial_cash", 0)))))
    
    created = run.get("created_at", "N/A")
    if hasattr(created, "strftime"):
        created = created.strftime("%Y-%m-%d %H:%M:%S")
    info_table.add_row("Created:", str(created))
    
    console.print(info_table)
    console.print()
    
    # Results if available
    if "total_return" in run:
        console.print("[bold]💰 Performance[/bold]")
        console.print("─" * 40)
        
        perf_table = Table(show_header=False, box=None, padding=(0, 2))
        perf_table.add_column("Label", style="dim")
        perf_table.add_column("Value", justify="right")
        
        perf_table.add_row("Total Return:", _format_percent(Decimal(str(run.get("total_return", 0)))))
        perf_table.add_row("CAGR:", _format_percent(Decimal(str(run.get("cagr", 0)))))
        perf_table.add_row("Max Drawdown:", _format_percent(Decimal(str(run.get("max_drawdown", 0))), show_sign=False))
        perf_table.add_row("Final Value:", _format_money(Decimal(str(run.get("final_value", 0)))))
        perf_table.add_row("Total Trades:", str(run.get("total_trades", 0)))
        
        console.print(perf_table)
        console.print()


def export_to_json(result: BacktestResult) -> str:
    """Export result as JSON."""
    data = {
        "run_id": result.run_id,
        "config": {
            "strategy_name": result.config.strategy_name,
            "symbols": result.config.symbols,
            "start_date": result.config.start_date.isoformat(),
            "end_date": result.config.end_date.isoformat(),
            "initial_cash": str(result.config.initial_cash),
        },
        "metrics": {
            "total_return": str(result.metrics.total_return),
            "cagr": str(result.metrics.cagr),
            "max_drawdown": str(result.metrics.max_drawdown),
            "sharpe_ratio": str(result.metrics.sharpe_ratio) if result.metrics.sharpe_ratio else None,
            "total_invested": str(result.metrics.total_invested),
            "total_trades": result.metrics.total_trades,
            "buy_trades": result.metrics.buy_trades,
            "sell_trades": result.metrics.sell_trades,
        },
        "final_value": str(result.final_value),
        "final_cash": str(result.final_cash),
        "final_positions": {
            symbol: {
                "quantity": str(pos.quantity),
                "avg_cost": str(pos.avg_cost),
            }
            for symbol, pos in result.final_positions.items()
        },
        "trades": [
            {
                "symbol": t.symbol,
                "side": t.side,
                "quantity": str(t.quantity),
                "price": str(t.price),
                "amount": str(t.amount),
                "timestamp": t.timestamp.isoformat(),
                "reason": t.reason,
            }
            for t in result.trades
        ],
    }
    return json.dumps(data, indent=2)


def export_to_csv(result: BacktestResult) -> str:
    """Export trades as CSV."""
    output = StringIO()
    
    # Header
    output.write("timestamp,symbol,side,quantity,price,amount,reason\n")
    
    # Trades
    for trade in result.trades:
        output.write(
            f"{trade.timestamp.isoformat()},"
            f"{trade.symbol},"
            f"{trade.side},"
            f"{trade.quantity},"
            f"{trade.price},"
            f"{trade.amount},"
            f"{trade.reason}\n"
        )
    
    return output.getvalue()
