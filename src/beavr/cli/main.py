"""Beavr CLI - Entry point for the bvr command."""

import typer
from rich.console import Console

from beavr import __version__

app = typer.Typer(
    name="bvr",
    help="Beavr - Auto Trading Platform for retail investors",
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold green]beavr[/bold green] version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Beavr - Auto Trading Platform for retail investors."""
    pass


@app.command()
def status() -> None:
    """Show system status."""
    console.print("[bold]Beavr Status[/bold]")
    console.print(f"Version: {__version__}")
    console.print("[yellow]No strategies configured yet.[/yellow]")


if __name__ == "__main__":
    app()
