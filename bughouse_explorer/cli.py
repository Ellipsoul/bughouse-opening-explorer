"""Command line for the SQLite crawler and frozen opening-explorer reference."""

import click
from rich.console import Console

from . import db, indexer, server
from .crawler.cli import crawl

DEFAULT_DB = "data/games.db"
console = Console()

_db_option = click.option(
    "--db", "db_path", default=DEFAULT_DB, show_default=True,
    help="Path to the legacy opening-index database.",
)


def _index(db_path, max_ply, rebuild):
    """Build the frozen reference index and return its summary."""
    try:
        summary = indexer.index(db_path, max_ply=max_ply, rebuild=rebuild, console=console)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]Indexed.[/green] {summary['new_games']} new game(s); index now holds "
        f"{summary['total_games']} games -> {summary['edges']} edges, {summary['facts']} facts."
    )
    return summary


@click.group()
def main():
    """Crawl Bughouse games or use the frozen opening-explorer reference."""


main.add_command(crawl)


@main.command()
@_db_option
@click.option("--max-ply", type=int, default=40, show_default=True,
              help="Plies recorded per game.")
@click.option("--rebuild", is_flag=True,
              help="Rebuild the index from the legacy input (needed to change --max-ply).")
def index(db_path, max_ply, rebuild):
    """Build the frozen position-graph reference from a legacy games database."""
    _index(db_path, max_ply, rebuild)


@main.command()
@_db_option
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8000, show_default=True)
def serve(db_path, host, port):
    """Serve the explorer web UI + JSON API from the database."""
    console.print(f"Serving http://{host}:{port}  (db: {db_path})")
    server.serve(db_path, host=host, port=port)


if __name__ == "__main__":
    main()
