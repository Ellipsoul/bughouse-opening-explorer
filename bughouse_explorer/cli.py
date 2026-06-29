"""Unified command line for the Bughouse Opening Explorer.

One tool, one database. Subcommands:

* ``download USERNAME`` — fetch a player's bughouse games from chess.com into the raw store.
* ``index``             — incrementally build the position graph from the raw store.
* ``serve``             — run the local query server + web UI.
* ``update USERNAME``   — ``download`` then ``index`` in one step.

Everything reads and writes the same ``--db`` file (default ``data/games.db``): the raw downloaded
games and the derived index live side by side, so there is no separate database to manage.
"""

import sys

import click
from rich.console import Console

from . import db, indexer, server
from .api import ApiError, ChessComClient, PlayerNotFound
from .download import download as run_download

DEFAULT_DB = "data/games.db"
console = Console()

_db_option = click.option(
    "--db", "db_path", default=DEFAULT_DB, show_default=True,
    help="Path to the bughouse database (raw games + index in one file).",
)


def _parse_month(ctx, param, value):
    if value is None:
        return None
    try:
        year, month = value.split("/")
        return (int(year), int(month))
    except ValueError:
        raise click.BadParameter(f"expected YYYY/MM, got {value!r}")


def _download(username, db_path, since, until, force_refresh):
    """Shared download body used by both `download` and `update`. Returns the summary dict."""
    conn = db.connect(db_path)
    client = ChessComClient()
    try:
        summary = run_download(
            client, conn, username,
            since=since, until=until, force_refresh=force_refresh, console=console,
        )
    except PlayerNotFound:
        console.print(f"[red]No chess.com player named '{username}'.[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped. Completed months are saved; re-run to resume.[/yellow]")
        sys.exit(130)
    except ApiError as exc:
        console.print(f"[red]API error:[/red] {exc}")
        sys.exit(1)
    finally:
        conn.close()
    console.print(
        f"[green]Downloaded.[/green] {username}: {summary['games']} bughouse games from "
        f"{summary['fetched']} month(s) fetched, {summary['skipped']} skipped (already complete)."
    )
    return summary


def _index(db_path, max_ply, rebuild):
    """Shared index body used by both `index` and `update`. Returns the summary dict."""
    try:
        summary = indexer.index(db_path, max_ply=max_ply, rebuild=rebuild, console=console)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    console.print(
        f"[green]Indexed.[/green] {summary['new_games']} new game(s); index now holds "
        f"{summary['total_games']} games -> {summary['edges']} edges, {summary['facts']} facts."
    )
    return summary


@click.group()
def main():
    """Download, index, and serve chess.com bughouse openings from one database."""


@main.command()
@click.argument("username")
@_db_option
@click.option("--from", "since", callback=_parse_month, default=None,
              help="Earliest month to fetch, as YYYY/MM.")
@click.option("--to", "until", callback=_parse_month, default=None,
              help="Latest month to fetch, as YYYY/MM.")
@click.option("--force-refresh", is_flag=True,
              help="Re-fetch every month, ignoring the resume ledger.")
def download(username, db_path, since, until, force_refresh):
    """Download USERNAME's bughouse games from chess.com into the database."""
    _download(username, db_path, since, until, force_refresh)
    console.print(f"DB: {db_path} — run [bold]bughouse-explorer index[/bold] to build the explorer.")


@main.command()
@_db_option
@click.option("--max-ply", type=int, default=40, show_default=True,
              help="Plies recorded per game.")
@click.option("--rebuild", is_flag=True,
              help="Drop and rebuild the whole index from the raw games (needed to change --max-ply).")
def index(db_path, max_ply, rebuild):
    """Incrementally build the position-graph index from the downloaded games."""
    _index(db_path, max_ply, rebuild)


@main.command()
@_db_option
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8000, show_default=True)
def serve(db_path, host, port):
    """Serve the explorer web UI + JSON API from the database."""
    console.print(f"Serving http://{host}:{port}  (db: {db_path})")
    server.serve(db_path, host=host, port=port)


@main.command()
@click.argument("username")
@_db_option
@click.option("--from", "since", callback=_parse_month, default=None,
              help="Earliest month to fetch, as YYYY/MM.")
@click.option("--to", "until", callback=_parse_month, default=None,
              help="Latest month to fetch, as YYYY/MM.")
@click.option("--force-refresh", is_flag=True,
              help="Re-fetch every month, ignoring the resume ledger.")
@click.option("--max-ply", type=int, default=40, show_default=True,
              help="Plies recorded per game (used on first build).")
def update(username, db_path, since, until, force_refresh, max_ply):
    """Download USERNAME's new games and incrementally index them in one step."""
    _download(username, db_path, since, until, force_refresh)
    _index(db_path, max_ply, rebuild=False)
    console.print(f"DB: {db_path} — run [bold]bughouse-explorer serve[/bold] to browse.")


if __name__ == "__main__":
    main()
