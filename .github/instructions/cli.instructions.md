---
applyTo: "src/beavr/cli/**/*.py"
---

# CLI Development Rules

Use Typer + Rich for all CLI commands.

## Required Pattern

```python
"""
Command description.

Usage:
    bvr mycommand subcommand [OPTIONS]
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="Command group description",
    no_args_is_help=True,
)
console = Console()


@app.command()
def subcommand(
    # Required positional
    symbol: str = typer.Argument(..., help="Stock symbol"),
    
    # Optional with default
    amount: Optional[Decimal] = typer.Option(
        None, "--amount", "-a", help="Amount in USD"
    ),
    
    # Flag
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose output"
    ),
) -> None:
    """
    Brief description shown in --help.
    
    Detailed description for command.
    """
    # Validate input
    if amount is not None and amount <= 0:
        console.print("[red]Error:[/red] Amount must be positive")
        raise typer.Exit(1)
    
    # Show progress
    with console.status("Processing..."):
        result = do_work(symbol)
    
    # Display results
    console.print(f"[green]Success:[/green] {result}")
```

## Rich Output Patterns

```python
# Tables
table = Table(title="Results")
table.add_column("Symbol", style="cyan")
table.add_column("Value", justify="right")
table.add_row("SPY", "$100.00")
console.print(table)

# Status
with console.status("Loading..."):
    data = fetch()

# Colors
console.print("[green]Success[/green]")
console.print("[red]Error:[/red] message")
console.print("[yellow]Warning:[/yellow] message")
```

## Registration
Register new commands in `src/beavr/cli/main.py`:
```python
from beavr.cli.mycommand import app as mycommand_app
app.add_typer(mycommand_app, name="mycommand")
```
