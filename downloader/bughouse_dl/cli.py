"""Command-line entry point: ``bughouse-dl USERNAME [options]``."""

import sys

import click
from rich.console import Console

from . import db
from .api import ApiError, ChessComClient, PlayerNotFound
from .download import download

console = Console()


def _parse_month(ctx, param, value):
    if value is None:
        return None
    try:
        year, month = value.split("/")
        return (int(year), int(month))
    except ValueError:
        raise click.BadParameter(f"expected YYYY/MM, got {value!r}")


@click.command()
@click.argument("username")
@click.option("--db", "db_path", default="games.db", show_default=True,
              help="SQLite database path.")
@click.option("--from", "since", callback=_parse_month, default=None,
              help="Earliest month to fetch, as YYYY/MM.")
@click.option("--to", "until", callback=_parse_month, default=None,
              help="Latest month to fetch, as YYYY/MM.")
@click.option("--force-refresh", is_flag=True,
              help="Re-fetch every month, ignoring the resume ledger.")
def main(username, db_path, since, until, force_refresh):
    """Download all of USERNAME's bughouse games from chess.com into a SQLite database."""
    conn = db.connect(db_path)
    client = ChessComClient()
    try:
        summary = download(
            client, conn, username,
            since=since, until=until, force_refresh=force_refresh, console=console,
        )
    except PlayerNotFound:
        console.print(f"[red]No chess.com player named '{username}'.[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped. Completed months are saved; "
                      "re-run to resume.[/yellow]")
        sys.exit(130)
    except ApiError as exc:
        console.print(f"[red]API error:[/red] {exc}")
        sys.exit(1)
    finally:
        conn.close()

    console.print(
        f"[green]Done.[/green] {username}: {summary['games']} bughouse games from "
        f"{summary['fetched']} month(s) fetched, {summary['skipped']} skipped "
        f"(already complete). DB: {db_path}"
    )


if __name__ == "__main__":
    main()
