"""Local query server for the Bughouse Opening Explorer.

Aggregates the per-game facts in ``explorer.db`` on demand, so every filter — minimum rating,
White/Black username — is just a WHERE over one join. The database stays on disk; only small JSON
results reach the browser.

Filtering by username: ``white`` and/or ``black`` query params match the corresponding seat in
``games_meta``. Supplying one filters that side; supplying both filters the exact pairing
(White=X vs Black=Y) — the same join, one extra predicate.
"""

import argparse
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Aggregate facts by move_id first (collapsing tens of thousands of games to a few dozen moves),
# using the denormalized fact columns so games_meta is joined only when a username filter is set.
# Then join moves/positions for identity, on the aggregated handful of moves only.
MOVES_SQL = """
WITH agg AS (
  SELECT f.move_id,
         COUNT(*) AS n,
         SUM(f.outcome = 0) AS white_wins,
         SUM(f.outcome = 1) AS black_wins,
         SUM(f.outcome = 2) AS draws
  FROM game_facts f {meta_join}
  WHERE f.parent_id = :pid {where}
  GROUP BY f.move_id
  HAVING COUNT(*) >= :min_games
)
SELECT a.move_id, m.san, m.from_sq, m.to_sq, m.drop_piece, m.child_id, p.fen AS child_fen,
       a.n, a.white_wins, a.black_wins, a.draws
FROM agg a
JOIN moves m ON m.parent_id = :pid AND m.move_id = a.move_id
JOIN positions p ON p.id = m.child_id
ORDER BY a.n DESC
"""

GAMES_SQL = """
SELECT g.white_username, g.white_rating, g.black_username, g.black_rating,
       g.outcome, g.url, g.time_control
FROM games_meta g
WHERE g.game_id IN (
        SELECT game_id FROM game_facts WHERE parent_id = :pid)
  AND {filters}
ORDER BY MIN(g.white_rating, g.black_rating) DESC, g.white_rating + g.black_rating DESC
LIMIT :limit
"""

USERNAMES_SQL = """
SELECT u, SUM(c) AS c FROM (
    SELECT white_username u, COUNT(*) c FROM games_meta GROUP BY white_username
    UNION ALL
    SELECT black_username u, COUNT(*) c FROM games_meta GROUP BY black_username
) GROUP BY u ORDER BY c DESC
"""


def create_app(db_path):
    app = FastAPI(title="Bughouse Opening Explorer")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    def rows(sql, params):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def rating_clauses(rmin, white, black):
        clauses = ["(g.white_rating + g.black_rating) / 2.0 >= :rmin"]
        params = {"rmin": rmin}
        if white:
            clauses.append("g.white_username = :white")
            params["white"] = white
        if black:
            clauses.append("g.black_username = :black")
            params["black"] = black
        return clauses, params

    @app.get("/api/meta")
    def meta():
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}

    @app.get("/api/usernames")
    def usernames():
        return [{"name": r["u"], "count": r["c"]} for r in conn.execute(USERNAMES_SQL) if r["u"]]

    @app.get("/api/moves")
    def moves(pid: int, rmin: float = 0,
              white: str | None = None, black: str | None = None, min_games: int = 5):
        params = {"pid": pid, "rmin": rmin, "min_games": min_games}
        where = " AND f.rating_sum / 2.0 >= :rmin"
        meta_join = ""
        if white or black:  # only join games_meta when filtering by username
            meta_join = "JOIN games_meta g ON g.game_id = f.game_id"
            if white:
                where += " AND g.white_username = :white"
                params["white"] = white
            if black:
                where += " AND g.black_username = :black"
                params["black"] = black
        return rows(MOVES_SQL.format(meta_join=meta_join, where=where), params)

    @app.get("/api/games")
    def games(pid: int, rmin: float = 0,
              white: str | None = None, black: str | None = None, limit: int = 8):
        clauses, params = rating_clauses(rmin, white, black)
        params.update(pid=pid, limit=limit)
        return rows(GAMES_SQL.format(filters=" AND ".join(clauses)), params)

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
    return app


def serve(db_path="data/games.db", host="127.0.0.1", port=8000):
    """Run the query server against the unified database (blocking)."""
    import uvicorn

    uvicorn.run(create_app(db_path), host=host, port=port)


def main(argv=None):
    p = argparse.ArgumentParser(description="Serve the bughouse database over a local JSON API.")
    p.add_argument("--db", default="data/games.db", help="Path to the bughouse database.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    serve(args.db, args.host, args.port)


if __name__ == "__main__":
    main()
