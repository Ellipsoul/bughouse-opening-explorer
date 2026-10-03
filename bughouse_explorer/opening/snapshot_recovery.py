"""Read-only recovery gates tied to the selected snapshot's actual crawl run."""

from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from bughouse_explorer.crawler.domain import eligibility_window


def audit_connection(c, run_id):
    run = c.execute(
        "SELECT status,started_at,ended_at FROM crawl_runs WHERE id=?", (run_id,)
    ).fetchone()
    if not run or run[0] != "complete" or run[2] is None:
        raise ValueError("recovery requires an explicitly completed crawl run")
    latest = c.execute(
        "SELECT id FROM crawl_runs ORDER BY started_at DESC,id DESC LIMIT 1"
    ).fetchone()
    if latest != (run_id,):
        raise ValueError("selected run is not the snapshot latest policy window")
    lower, upper = eligibility_window(datetime.fromtimestamp(run[1], timezone.utc))
    queries = {
        "remaining_jobs": (
            "SELECT count(*) FROM crawl_jobs WHERE status IN ('queued','leased','deferred','failed')",
            (),
        ),
        "active_runs": (
            "SELECT count(*) FROM crawl_runs WHERE status='running' OR ended_at IS NULL",
            (),
        ),
        "tracked_without_outcome": (
            """SELECT count(*) FROM players WHERE tracking_started_at IS NOT NULL
        AND full_crawl_completed_at IS NULL AND archive_unavailable_at IS NULL""",
            (),
        ),
        "qualification_pointer": (
            """SELECT count(*) FROM players p LEFT JOIN games g ON g.uuid=p.qualifying_game_uuid
        LEFT JOIN game_participants gp ON gp.game_uuid=p.qualifying_game_uuid AND gp.player_id=p.id
        WHERE (p.state='eligible' OR p.qualifying_game_uuid IS NOT NULL OR p.qualifying_rating IS NOT NULL OR p.qualifying_at IS NOT NULL)
        AND (p.qualifying_game_uuid IS NULL OR p.qualifying_rating IS NULL OR p.qualifying_at IS NULL
        OR gp.player_id IS NULL OR gp.rating IS NOT p.qualifying_rating
        OR gp.rating_source NOT IN ('public','callback_pgn') OR g.end_time IS NOT p.qualifying_at)""",
            (),
        ),
        "eligible_window": (
            """SELECT count(*) FROM players WHERE state='eligible' AND
        (qualifying_rating<2000 OR qualifying_at<? OR qualifying_at>?)""",
            (lower, upper),
        ),
        "eligible_observation": (
            """SELECT count(*) FROM players p WHERE state='eligible' AND NOT EXISTS(
        SELECT 1 FROM game_participants gp JOIN games g ON g.uuid=gp.game_uuid
        WHERE gp.player_id=p.id AND gp.rating_source IN ('public','callback_pgn')
        AND gp.rating>=2000 AND g.end_time BETWEEN ? AND ?)""",
            (lower, upper),
        ),
    }
    violations = {
        name: c.execute(sql, parameters).fetchone()[0]
        for name, (sql, parameters) in queries.items()
    }
    violations["foreign_keys"] = sum(1 for _ in c.execute("PRAGMA foreign_key_check"))
    quick = c.execute("PRAGMA quick_check").fetchall()
    if quick != [("ok",)] or any(violations.values()):
        raise ValueError(
            f"snapshot invariant failure: {violations}; quick_check={quick}"
        )
    return {
        "run_id": run_id,
        "window": [lower, upper],
        "quick_check": "ok",
        "violations": violations,
        "games": c.execute("SELECT count(*) FROM games").fetchone()[0],
        "participants": c.execute("SELECT count(*) FROM game_participants").fetchone()[
            0
        ],
        "tracked_players": c.execute(
            "SELECT count(*) FROM players WHERE tracking_started_at IS NOT NULL"
        ).fetchone()[0],
    }


def audit_snapshot(path, run_id):
    path = Path(path).resolve()
    if path.name == "crawler.db" and path.parent.name == "data":
        raise ValueError("use immutable snapshots, never data/crawler.db")
    with sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True) as c:
        return audit_connection(c, run_id)
