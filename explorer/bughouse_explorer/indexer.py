"""Build ``explorer.db`` from the downloader's ``games.db``.

Replays each game's moves on a single-board engine and records, per ply, the *edge identity*
(``moves``) and a *per-game fact* (``game_facts``) linking that game to the move it played from
each position. All statistics (frequency, win-rate, rating, username/side) are computed later by
the query server aggregating these facts — nothing is pre-aggregated here,
so the data isn't pruned by `min_games` (that became a live query parameter) and every game's
actual lines remain queryable by username.
"""

import argparse
import json
import sqlite3

from . import db
from .engine import Board, label

DRAW_CODES = {
    "repetition", "agreed", "stalemate", "insufficient", "50move",
    "timevsinsufficient", "timevsinsufficientmaterial",
}

def classify(white_result, black_result):
    """Return the outcome code 0=white win, 1=black win, 2=draw, or None to skip the game."""
    if white_result == "win":
        return 0
    if black_result == "win":
        return 1
    if white_result in DRAW_CODES or black_result in DRAW_CODES:
        return 2
    return None


def _meta_row(game, game_id, outcome):
    return (
        game_id, game["uuid"],
        game["white_username"], game["white_rating"],
        game["black_username"], game["black_rating"],
        outcome,
        game["url"], game["time_control"], game["end_time"],
    )


def build(games_db, out_db, max_ply=40, batch=50000):
    """Stream the games into ``out_db`` in bounded memory.

    The only large structure kept in RAM is the ``fen -> id`` map; positions/moves/facts/meta are
    buffered in small batches and flushed to SQLite, whose primary keys do the cross-game dedup
    (``moves`` on ``(parent_id, move_id)``, ``game_facts`` on ``(parent_id, game_id)``).
    """
    import os

    if os.path.exists(out_db):
        os.remove(out_db)  # rebuild from scratch
    src = sqlite3.connect(games_db)
    src.row_factory = sqlite3.Row

    out = db.create(out_db)
    # Throwaway, rebuildable index: trade durability for bulk-load speed, but keep memory bounded.
    # Crucially, temp storage stays on disk (no temp_store=MEMORY) and we skip VACUUM — an in-memory
    # VACUUM of the multi-GB output was what OOM-killed an earlier full build. mmap is disabled so the
    # growing DB file's pages don't inflate process RSS.
    out.execute("PRAGMA synchronous=OFF")
    out.execute("PRAGMA journal_mode=OFF")
    out.execute("PRAGMA mmap_size=0")

    ids = {}  # fen -> int
    position_buf, move_buf, fact_buf, meta_buf = [], [], [], []

    def pid(fen):
        i = ids.get(fen)
        if i is None:
            i = ids[fen] = len(ids)
            position_buf.append((i, fen))
        return i

    def flush():
        with out:
            db.write_positions(out, position_buf)
            db.write_moves(out, move_buf)
            db.write_game_facts(out, fact_buf)
            db.write_games_meta(out, meta_buf)
        position_buf.clear()
        move_buf.clear()
        fact_buf.clear()
        meta_buf.clear()

    game_id = 0
    for game in src.execute("SELECT * FROM games"):  # streamed, not fetchall()
        outcome = classify(game["white_result"], game["black_result"])
        if outcome is None:
            continue
        meta_buf.append(_meta_row(game, game_id, outcome))
        rating_sum = (game["white_rating"] or 0) + (game["black_rating"] or 0)

        board = Board()
        fen = board.position_key()
        seen = set()  # positions already recorded for this game (dedup transpositions)
        for move in json.loads(game["moves_json"])[:max_ply]:
            parent_fen = fen
            move_id, san = label(board, move)
            from_sq, to_sq, drop_piece = move.get("from"), move["to"], move.get("drop")
            board.apply(move)
            fen = board.position_key()
            parent_id, child_id = pid(parent_fen), pid(fen)
            move_buf.append((parent_id, move_id, san, from_sq, to_sq, drop_piece, child_id))
            if parent_fen not in seen:
                seen.add(parent_fen)
                fact_buf.append((parent_id, move_id, game_id, outcome, rating_sum))
        game_id += 1
        if len(move_buf) >= batch:
            flush()

    flush()
    # The start position's id, so the frontend can bootstrap navigation without a fen->id lookup
    # (there is no fen index anymore). Captured before ids is cleared below.
    root_id = ids[Board().position_key()]
    with out:
        out.execute("INSERT OR REPLACE INTO meta VALUES ('max_ply', ?)", (str(max_ply),))
        out.execute("INSERT OR REPLACE INTO meta VALUES ('root_id', ?)", (str(root_id),))
    src.close()
    n_edges = out.execute("SELECT COUNT(*) FROM moves").fetchone()[0]
    n_facts = out.execute("SELECT COUNT(*) FROM game_facts").fetchone()[0]

    # Compact and defragment the index B-trees (the streaming load inserts in non-key order, so the
    # PKs/indexes the query server range-scans end up fragmented). Free the fen->id map first and
    # force temp storage onto disk: an in-memory VACUUM of a multi-GB file is what OOM-killed an
    # earlier build, whereas an on-disk VACUUM streams through a tiny page cache.
    ids.clear()
    out.execute("PRAGMA temp_store=FILE")
    out.execute("VACUUM")
    out.close()
    return {"games": game_id, "edges": n_edges, "facts": n_facts}


def main(argv=None):
    p = argparse.ArgumentParser(description="Build explorer.db (per-game facts) from games.db.")
    p.add_argument("--games-db", required=True, help="Input games.db from bughouse-downloader.")
    p.add_argument("--out", required=True, help="Output explorer.db path.")
    p.add_argument("--max-ply", type=int, default=40, help="Plies recorded per game (default 40).")
    args = p.parse_args(argv)

    summary = build(args.games_db, args.out, max_ply=args.max_ply)
    print(f"Indexed {summary['games']} games -> {summary['edges']} edges, "
          f"{summary['facts']} facts. Wrote {args.out}")


if __name__ == "__main__":
    main()
