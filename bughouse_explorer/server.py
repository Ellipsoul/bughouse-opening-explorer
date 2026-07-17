"""Local query server for the Bughouse Opening Explorer.

Aggregates the per-game facts in ``explorer.db`` on demand, so every filter — minimum rating,
White/Black username — is just a WHERE over one join. The database stays on disk; only small JSON
results reach the browser.

Filtering by username: ``white`` and/or ``black`` query params match the corresponding seat in
``games_meta``. Supplying one filters that side; supplying both filters the exact pairing
(White=X vs Black=Y) — the same join, one extra predicate.
"""

import argparse
import os
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import db

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
  FROM game_facts f
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

# Username-filtered path. Driving from game_facts would scan every game at the position (~1.3M near
# the root); instead drive from the player's games via games_meta's username index and seek their
# facts through idx_facts_game(game_id, parent_id). CROSS JOIN pins that join order (SQLite won't
# pick it on cost alone). Same result shape as MOVES_SQL; {user} is one or both seat predicates.
MOVES_USER_SQL = """
WITH agg AS (
  SELECT f.move_id,
         COUNT(*) AS n,
         SUM(f.outcome = 0) AS white_wins,
         SUM(f.outcome = 1) AS black_wins,
         SUM(f.outcome = 2) AS draws
  FROM games_meta g CROSS JOIN game_facts f
  WHERE {user} AND f.game_id = g.game_id AND f.parent_id = :pid AND f.rating_sum / 2.0 >= :rmin
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

# Fast path for the default view (no username filter, rating at the floor): read the precomputed
# move_agg table instead of aggregating game_facts live. Same shape as MOVES_SQL's result.
MOVES_AGG_SQL = """
SELECT a.move_id, m.san, m.from_sq, m.to_sq, m.drop_piece, m.child_id, p.fen AS child_fen,
       a.n, a.white_wins, a.black_wins, a.draws
FROM move_agg a
JOIN moves m ON m.parent_id = :pid AND m.move_id = a.move_id
JOIN positions p ON p.id = m.child_id
WHERE a.parent_id = :pid AND a.n >= :min_games
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


def normalize_fen(fen):
    """Reduce a pasted FEN to the 4-field form positions are keyed by (see Board.position_key).

    Positions store ``placement side castling ep`` with no half/full-move counters, so a standard
    6-field FEN must be trimmed to its first four whitespace-separated tokens before lookup. A
    crazyhouse/bughouse FEN also appends a pocket to the placement, either bracketed (e.g.
    ``...RNBQKBNR[QQpp]``) or as a ninth ``/``-delimited segment (e.g. ``...RNBQKBNR/QQpp``);
    positions here carry no holdings, so both forms are stripped.
    """
    tokens = fen.split()
    if len(tokens) < 4:
        raise HTTPException(status_code=400, detail="malformed FEN")
    tokens = tokens[:4]
    tokens[0] = re.sub(r"\[.*?\]", "", tokens[0])  # drop the crazyhouse/bughouse pocket
    tokens[0] = "/".join(tokens[0].split("/")[:8])  # drop bughouse holdings (9th slash segment)
    return " ".join(tokens)


_FILES = "abcdefgh"


def _placement_map(placement):
    """Parse a FEN placement field into a {square: piece} dict, e.g. {'e4': 'P'}."""
    board = {}
    for i, row in enumerate(placement.split("/")):
        rank = 8 - i
        f = 0
        for ch in row:
            if ch.isdigit():
                f += int(ch)
            elif f < 8 and 1 <= rank <= 8:  # ignore anything that would run off the board
                board[_FILES[f] + str(rank)] = ch
                f += 1
    return board


def fen_lookup_keys(key):
    """Yield the position keys to try for a pasted FEN, reconciling en-passant conventions.

    The indexer records the en-passant target after *every* double pawn push (engine.py), but
    lichess (and other strict exporters) only write the ep square when a capture is actually legal,
    emitting ``-`` otherwise. So when a pasted FEN has ep ``-`` we also try the square a pawn would
    have skipped (inferred from the placement); when it has a square we also try ``-``. The exact
    key is tried first, so an unambiguous match always wins.
    """
    placement, side, castling, ep = key.split(" ")
    yield key
    if ep == "-":
        board = _placement_map(placement)
        if side == "b":  # white just moved: ep target on rank 3 behind a white pawn on rank 4
            for f in _FILES:
                if board.get(f + "4") == "P" and f + "3" not in board and f + "2" not in board:
                    yield f"{placement} {side} {castling} {f}3"
        else:            # black just moved: ep target on rank 6 behind a black pawn on rank 5
            for f in _FILES:
                if board.get(f + "5") == "p" and f + "6" not in board and f + "7" not in board:
                    yield f"{placement} {side} {castling} {f}6"
    else:
        yield f"{placement} {side} {castling} -"


def create_app(db_path):
    app = FastAPI(title="Bughouse Opening Explorer")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    def rows(sql, params):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # The precomputed summary table may be absent on an older/partially-built database; fall back to
    # live aggregation when it is, so the server still works before the next reindex.
    has_move_agg = bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='move_agg'").fetchone())

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

    # The database is read-only while serving, so query results are stable until the next data
    # refresh (which restarts the process and clears these caches). Aggregating a busy position —
    # e.g. the opening tree's root, ~1.3M game_facts rows — costs seconds; memoizing collapses
    # every repeat hit to a dict lookup. LRU bounds keep filtered variants from growing unbounded
    # while the common unfiltered views stay hot.
    @app.get("/api/meta")
    def meta():
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}

    @lru_cache(maxsize=1)
    def usernames_cached():
        return [{"name": r["u"], "count": r["c"]} for r in conn.execute(USERNAMES_SQL) if r["u"]]

    @app.get("/api/usernames")
    def usernames():
        return usernames_cached()

    @lru_cache(maxsize=4096)
    def moves_cached(pid, rmin, white, black, min_games):
        # Default view (no username filter, rating at/below the floor): the precomputed move_agg
        # table already holds this exact aggregation, so serve it as a keyed lookup.
        if has_move_agg and not white and not black and rmin <= db.RATING_FLOOR:
            return rows(MOVES_AGG_SQL, {"pid": pid, "min_games": min_games})
        params = {"pid": pid, "rmin": rmin, "min_games": min_games}
        if white or black:  # username filter: use the player-driven query (see MOVES_USER_SQL)
            user = []
            if white:
                user.append("g.white_username = :white")
                params["white"] = white
            if black:
                user.append("g.black_username = :black")
                params["black"] = black
            return rows(MOVES_USER_SQL.format(user=" AND ".join(user)), params)
        return rows(MOVES_SQL.format(where=" AND f.rating_sum / 2.0 >= :rmin"), params)

    @app.get("/api/moves")
    def moves(pid: int, rmin: float = 0,
              white: str | None = None, black: str | None = None, min_games: int = 5):
        return moves_cached(pid, rmin, white, black, min_games)

    @app.get("/api/position")
    def position(fen: str):
        # Resolve a FEN to its position id, mirroring the indexer's hash-then-verify lookup: probe
        # the indexed fen_hash, then confirm the FEN text (hashes may collide). Several ep variants
        # are tried (see fen_lookup_keys) so lichess-style FENs match. 404 if none are indexed.
        for key in fen_lookup_keys(normalize_fen(fen)):
            h = db.fen_hash(key)
            for r in conn.execute("SELECT id, fen FROM positions WHERE fen_hash = ?", (h,)):
                if r["fen"] == key:
                    return {"id": r["id"], "fen": key}
        raise HTTPException(status_code=404, detail="not_found")

    @lru_cache(maxsize=4096)
    def games_cached(pid, rmin, white, black, limit):
        clauses, params = rating_clauses(rmin, white, black)
        params.update(pid=pid, limit=limit)
        return rows(GAMES_SQL.format(filters=" AND ".join(clauses)), params)

    @app.get("/api/games")
    def games(pid: int, rmin: float = 0,
              white: str | None = None, black: str | None = None, limit: int = 8):
        return games_cached(pid, rmin, white, black, limit)

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
    return app


def app_factory():
    """Build the app from the db path in the environment. Used when running multiple worker
    processes, where uvicorn imports this factory in each worker rather than sharing one app."""
    return create_app(os.environ["BUGHOUSE_DB"])


def serve(db_path="data/games.db", host="127.0.0.1", port=8000, workers=1):
    """Run the query server against the unified database (blocking).

    Each worker is a separate process with its own connection and result cache, so CPU-bound
    aggregations run in parallel instead of serializing on one process's GIL.
    """
    import uvicorn

    if workers and workers > 1:
        os.environ["BUGHOUSE_DB"] = db_path
        uvicorn.run("bughouse_explorer.server:app_factory", factory=True,
                    host=host, port=port, workers=workers)
    else:
        uvicorn.run(create_app(db_path), host=host, port=port)


def main(argv=None):
    p = argparse.ArgumentParser(description="Serve the bughouse database over a local JSON API.")
    p.add_argument("--db", default="data/games.db", help="Path to the bughouse database.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--workers", type=int, default=1, help="Number of worker processes.")
    args = p.parse_args(argv)
    serve(args.db, args.host, args.port, args.workers)


if __name__ == "__main__":
    main()
