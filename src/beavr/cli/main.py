"""Beavr CLI - Entry point for the bvr command."""

import typer
from rich.console import Console

from beavr import __version__
from beavr.cli.ai import ai_app
from beavr.cli.backtest import backtest_app

app = typer.Typer(
    name="bvr",
    help="Beavr - Auto Trading Platform for retail investors",
    add_completion=False,
)
app.add_typer(backtest_app, name="backtest")
app.add_typer(ai_app, name="ai")
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold green]beavr[/bold green] version {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(  # noqa: ARG001
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Beavr - Auto Trading Platform for retail investors."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command()
def status() -> None:
    """Show system status."""
    console.print("[bold]Beavr Status[/bold]")
    console.print(f"Version: {__version__}")
    console.print("[yellow]No strategies configured yet.[/yellow]")


if __name__ == "__main__":
    app()
