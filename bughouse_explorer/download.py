"""Orchestration: walk a player's monthly archives, keep bughouse games, store them.

Resume is month-granular. A month already marked ``complete`` is skipped (past months are
immutable on chess.com) unless ``force_refresh`` is set; the current/latest month is always
re-fetched because it can still change. Each month is saved in a single transaction, so
Ctrl-C mid-run leaves a consistent DB and the next run picks up where this one stopped.
"""

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from . import db

BUGHOUSE = "bughouse"


def _bughouse_rows(games):
    # Store the raw record (incl. chess.com's tcn) as-is; the indexer decodes tcn when it replays.
    return [db.game_row(game) for game in games if game.get("rules") == BUGHOUSE]


def download(client, conn, username, since=None, until=None, force_refresh=False, console=None):
    """Download a player's bughouse games into ``conn``. Returns a summary dict."""
    months = client.get_archive_months(username)
    if since:
        months = [m for m in months if m >= since]
    if until:
        months = [m for m in months if m <= until]

    if not months:
        return {"months": 0, "fetched": 0, "skipped": 0, "games": 0}

    current_month = months[-1]  # latest available archive is the mutable one
    done = set() if force_refresh else db.completed_months(conn, username)

    todo = [m for m in months if m == current_month or m not in done]
    skipped = len(months) - len(todo)
    total_games = 0

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("• {task.fields[games]} games"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task = progress.add_task(
            f"{username}", total=len(todo), games=0
        )
        for year, month in todo:
            progress.update(task, description=f"{username} {year}/{month:02d}")
            games = client.get_month_games(username, year, month)
            rows = _bughouse_rows(games)
            db.save_month(conn, username, year, month, rows)
            total_games += len(rows)
            progress.update(task, advance=1, games=total_games)

    return {
        "months": len(months),
        "fetched": len(todo),
        "skipped": skipped,
        "games": total_games,
    }
