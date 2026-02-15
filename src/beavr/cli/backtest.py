"""CLI commands for backtesting."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from beavr.cli.output import (
    export_to_csv,
    export_to_json,
    print_backtest_result,
    print_comparison_table,
    print_run_detail,
    print_run_list,
)

backtest_app = typer.Typer(help="Backtesting commands")
console = Console()


def _parse_date(date_str: str) -> date:
    """Parse a date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise typer.BadParameter(f"Invalid date format: {date_str}. Use YYYY-MM-DD.") from e


def _load_config(config_path: Path) -> dict:
    """Load strategy configuration from a TOML file."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found]

    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError as e:
        raise typer.BadParameter(f"Config file not found: {config_path}") from e
    except Exception as e:
        raise typer.BadParameter(f"Error reading config file: {e}") from e


def _get_alpaca_credentials() -> tuple[str, str]:
    """Get Alpaca API credentials from environment or config."""
    from beavr.core.config import load_app_config

    config = load_app_config()
    api_key = config.alpaca.get_api_key()
    api_secret = config.alpaca.get_api_secret()

    if not api_key or not api_secret:
        console.print("[red]Error: Alpaca API credentials not found.[/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables.[/yellow]")
        raise typer.Exit(1)

    return api_key, api_secret


@backtest_app.command("run")
def run_backtest(
    strategy: str = typer.Argument(..., help="Strategy name (simple_dca, dip_buy_dca)"),
    start: str = typer.Option(..., "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="End date (YYYY-MM-DD)"),
    symbols: Optional[str] = typer.Option(
        "VOO", "--symbols", help="Comma-separated symbols (e.g., VOO,VTI)"
    ),
    cash: float = typer.Option(10000, "--cash", "-c", help="Initial cash"),
    config: Optional[Path] = typer.Option(
        None, "--config", help="Strategy config file (TOML)"
    ),
    output: str = typer.Option(
        "table", "--output", "-o", help="Output format: table, json, csv"
    ),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to database"),
    hourly: bool = typer.Option(False, "--hourly", help="Use hourly data for dip detection"),
) -> None:
    """Run a backtest for a strategy."""
    from beavr.backtest.engine import BacktestEngine
    from beavr.broker.factory import BrokerFactory
    from beavr.core.config import load_app_config
    from beavr.db.connection import Database
    from beavr.db.results import BacktestResultsRepository
    from beavr.strategies.registry import create_strategy, get_strategy

    # Parse dates
    start_date = _parse_date(start)
    end_date = _parse_date(end)

    if start_date >= end_date:
        console.print("[red]Error: Start date must be before end date.[/red]")
        raise typer.Exit(1)

    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.split(",")] if symbols else ["VOO"]

    # Load strategy config if provided
    strategy_params: dict = {}
    if config:
        file_config = _load_config(config)
        strategy_params = file_config.get("params", {})
        # Override strategy name if in config
        if "strategy" in file_config:
            strategy = file_config["strategy"]
        # Override symbols if in config
        if "symbols" in file_config:
            symbol_list = file_config["symbols"]

    # Ensure symbols are in strategy params
    strategy_params["symbols"] = symbol_list

    # Add hourly data option if enabled
    if hourly:
        strategy_params["use_hourly_data"] = True

    # Verify strategy exists
    try:
        get_strategy(strategy)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e

    # Create strategy instance
    try:
        strategy_instance = create_strategy(strategy, strategy_params)
    except Exception as e:
        console.print(f"[red]Error creating strategy: {e}[/red]")
        raise typer.Exit(1) from e

    # Get app config
    app_config = load_app_config()
    app_config.ensure_data_dir()

    # Set up dependencies
    db = Database(app_config.database_path)

    # Create data provider via factory
    data_fetcher = BrokerFactory.create_data_provider(app_config)

    # Results repository
    results_repo = BacktestResultsRepository(db) if save else None

    console.print(f"[bold]Running backtest: {strategy}[/bold]")
    console.print(f"Symbols: {', '.join(symbol_list)}")
    console.print(f"Period: {start_date} to {end_date}")
    console.print(f"Initial cash: ${cash:,.2f}")
    console.print()

    with console.status("[bold green]Fetching data and running backtest..."):
        # Create and run engine
        engine = BacktestEngine(
            data_fetcher=data_fetcher,
            results_repo=results_repo,
        )

        result = engine.run(
            strategy=strategy_instance,
            start_date=start_date,
            end_date=end_date,
            initial_cash=Decimal(str(cash)),
        )

    # Output results
    if output == "json":
        console.print(export_to_json(result))
    elif output == "csv":
        console.print(export_to_csv(result))
    else:  # table
        print_backtest_result(result, console)


@backtest_app.command("compare")
def compare_strategies(
    strategies: str = typer.Argument(..., help="Comma-separated strategies to compare"),
    start: str = typer.Option(..., "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="End date (YYYY-MM-DD)"),
    symbols: Optional[str] = typer.Option(
        "VOO", "--symbols", help="Comma-separated symbols"
    ),
    cash: float = typer.Option(10000, "--cash", "-c", help="Initial cash"),
) -> None:
    """Compare multiple strategies."""
    from beavr.backtest.engine import BacktestEngine
    from beavr.broker.factory import BrokerFactory
    from beavr.core.config import load_app_config
    from beavr.strategies.registry import create_strategy, get_strategy

    # Parse inputs
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    symbol_list = [s.strip().upper() for s in symbols.split(",")] if symbols else ["VOO"]
    strategy_names = [s.strip() for s in strategies.split(",")]

    if len(strategy_names) < 2:
        console.print("[red]Error: Provide at least 2 strategies to compare.[/red]")
        raise typer.Exit(1)

    # Verify all strategies exist
    for name in strategy_names:
        try:
            get_strategy(name)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from e

    # Get app config
    app_config = load_app_config()
    app_config.ensure_data_dir()

    data_fetcher = BrokerFactory.create_data_provider(app_config)

    results = []

    for name in strategy_names:
        console.print(f"Running backtest for [bold]{name}[/bold]...")

        strategy_params = {"symbols": symbol_list}
        strategy_instance = create_strategy(name, strategy_params)

        engine = BacktestEngine(
            data_fetcher=data_fetcher,
            results_repo=None,  # Don't save comparison runs
        )

        result = engine.run(
            strategy=strategy_instance,
            start_date=start_date,
            end_date=end_date,
            initial_cash=Decimal(str(cash)),
        )
        results.append(result)

    print_comparison_table(results, console)

@backtest_app.command("list")
def list_runs(
    strategy: Optional[str] = typer.Option(
        None, "--strategy", help="Filter by strategy name"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum runs to show"),
) -> None:
    """List past backtest runs."""
    from beavr.core.config import load_app_config
    from beavr.db.connection import Database
    from beavr.db.results import BacktestResultsRepository

    app_config = load_app_config()
    db = Database(app_config.database_path)
    repo = BacktestResultsRepository(db)

    runs = repo.list_runs(strategy_name=strategy, limit=limit)
    print_run_list(runs, console)


@backtest_app.command("show")
def show_run(
    run_id: str = typer.Argument(..., help="Run ID to show"),
) -> None:
    """Show details of a backtest run."""
    from beavr.core.config import load_app_config
    from beavr.db.connection import Database
    from beavr.db.results import BacktestResultsRepository

    app_config = load_app_config()
    db = Database(app_config.database_path)
    repo = BacktestResultsRepository(db)

    run = repo.get_run(run_id)
    if not run:
        console.print(f"[red]Error: Run not found: {run_id}[/red]")
        raise typer.Exit(1)

    # Get results too
    results = repo.get_results(run_id)
    if results:
        run.update(results)

    print_run_detail(run, console)


@backtest_app.command("export")
def export_run(
    run_id: str = typer.Argument(..., help="Run ID to export"),
    format: str = typer.Option("json", "--format", "-f", help="Export format: json, csv"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file (defaults to stdout)"
    ),
) -> None:
    """Export a backtest run's results."""
    from beavr.core.config import load_app_config
    from beavr.db.connection import Database
    from beavr.db.results import BacktestResultsRepository

    app_config = load_app_config()
    db = Database(app_config.database_path)
    repo = BacktestResultsRepository(db)

    run = repo.get_run(run_id)
    if not run:
        console.print(f"[red]Error: Run not found: {run_id}[/red]")
        raise typer.Exit(1)

    results = repo.get_results(run_id)
    trades = repo.get_trades(run_id)

    if format == "json":
        import json
        data = {
            "run": run,
            "results": results,
            "trades": [
                {
                    "symbol": t["symbol"],
                    "side": t["side"],
                    "quantity": t["quantity"],
                    "price": t["price"],
                    "amount": t["amount"],
                    "timestamp": t["timestamp"],
                    "reason": t["reason"],
                }
                for t in trades
            ],
        }
        content = json.dumps(data, indent=2, default=str)
    elif format == "csv":
        lines = ["timestamp,symbol,side,quantity,price,amount,reason"]
        for t in trades:
            lines.append(
                f"{t['timestamp']},{t['symbol']},{t['side']},"
                f"{t['quantity']},{t['price']},{t['amount']},{t['reason']}"
            )
        content = "\n".join(lines)
    else:
        console.print(f"[red]Error: Unknown format: {format}[/red]")
        raise typer.Exit(1)

    if output:
        output.write_text(content)
        console.print(f"[green]Exported to {output}[/green]")
    else:
        console.print(content)


@backtest_app.command("strategies")
def list_strategies() -> None:
    """List available strategies."""
    from rich.table import Table

    from beavr.strategies.registry import get_strategy_info, list_strategies

    strategies = list_strategies()

    if not strategies:
        console.print("[yellow]No strategies registered.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Name", style="bold")
    table.add_column("Description")

    for name in strategies:
        info = get_strategy_info(name)
        description = info.get("description", "") if info else ""
        table.add_row(name, description)

    console.print(table)
