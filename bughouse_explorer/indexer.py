"""Build the position-graph index from the raw ``games`` table, in the same database file.

Replays each game's moves on a single-board engine and records, per ply, the *edge identity*
(``moves``) and a *per-game fact* (``game_facts``) linking that game to the move it played from
each position. All statistics (frequency, win-rate, rating, username/side) are computed later by
the query server aggregating these facts — nothing is pre-aggregated here.

Indexing is **incremental**: it processes only games that have no ``games_meta`` row yet, so a
routine update after downloading a few new players is cheap and never re-reads the multi-GB raw
store. ``rebuild=True`` drops the index layer and reindexes every game (the one-time initial
build, and the way to change ``max_ply``).

Because the raw games and the index share one file, the reader and writer are the same connection
and games are read in **batches** (``fetchall``) rather than one long cursor: a cursor left open
across commits would pin the WAL so it could never checkpoint, and it would grow without bound for
the whole build. With each batch fully materialized before it is processed, no reader is open at
commit time, so the WAL is checkpoint-truncated after every flush and stays small.
"""

import json

from . import db
from .engine import Board, label

DRAW_CODES = {
    "repetition", "agreed", "stalemate", "insufficient", "50move",
    "timevsinsufficient", "timevsinsufficientmaterial",
}

# SQLite's default bound-parameter limit is 999; stay under it for the `uuid IN (...)` fetch.
_UUID_CHUNK = 900
# Games materialized per read (bounds memory; the reader is closed before the batch is processed).
_READ_BATCH = 5000


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


def _game_batches(conn, new_uuids):
    """Yield lists of game rows, each fetched with ``fetchall`` so no cursor stays open.

    ``new_uuids is None`` -> bootstrap/rebuild: paginate every game by rowid.
    otherwise            -> incremental: fetch just the listed (un-indexed) games in chunks.
    """
    if new_uuids is None:
        last = 0
        while True:
            rows = conn.execute(
                "SELECT rowid AS _rid, * FROM games WHERE rowid > ? ORDER BY rowid LIMIT ?",
                (last, _READ_BATCH),
            ).fetchall()
            if not rows:
                return
            last = rows[-1]["_rid"]
            yield rows
    else:
        for i in range(0, len(new_uuids), _UUID_CHUNK):
            chunk = new_uuids[i:i + _UUID_CHUNK]
            placeholders = ",".join("?" * len(chunk))
            yield conn.execute(
                f"SELECT * FROM games WHERE uuid IN ({placeholders})", chunk
            ).fetchall()


def index(db_path, max_ply=40, rebuild=False, batch=50000, console=None):
    """Incrementally index ``db_path`` (or fully rebuild it). Returns a summary dict.

    The only large structure kept in RAM is the ``fen -> id`` cache, which grows with positions
    touched *this run* — small for an incremental update, the full set for a rebuild (same as the
    old standalone builder).
    """
    conn = db.connect(db_path)  # also ensures every table/index exists
    # Safe journaling: the irreplaceable raw store shares this file, so the old reckless
    # journal_mode=OFF is gone. The dominant cost is the Python move-replay, so WAL is ~free.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA mmap_size=0")  # keep RSS bounded on a multi-GB file

    if rebuild:
        db.drop_index(conn)
        db.create_index_schema(conn)

    existing_ply = conn.execute("SELECT value FROM meta WHERE key = 'max_ply'").fetchone()
    if existing_ply is not None and int(existing_ply[0]) != max_ply:
        conn.close()
        raise ValueError(
            f"index already built with max_ply={existing_ply[0]}; "
            f"pass rebuild=True to change it to {max_ply}"
        )

    next_game_id = conn.execute("SELECT COALESCE(MAX(game_id), -1) + 1 FROM games_meta").fetchone()[0]
    next_pos_id = conn.execute("SELECT COALESCE(MAX(id), -1) + 1 FROM positions").fetchone()[0]
    bootstrap = next_game_id == 0  # games_meta empty -> positions empty too
    lookup_disk = not bootstrap    # only then can an existing position be on disk

    # Find the un-indexed games up front (covered by indexes; no heavy columns read). For a
    # bootstrap/rebuild there is nothing indexed, so we stream every game instead.
    new_uuids = None
    if not bootstrap:
        new_uuids = [r[0] for r in conn.execute(
            "SELECT g.uuid FROM games g LEFT JOIN games_meta m ON m.uuid = g.uuid "
            "WHERE m.uuid IS NULL"
        )]
    total = (conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
             if bootstrap else len(new_uuids))

    ids = {}  # fen -> id, for positions seen this run; misses fall back to the on-disk index
    position_buf, move_buf, fact_buf, meta_buf = [], [], [], []

    def pid(fen):
        nonlocal next_pos_id
        i = ids.get(fen)
        if i is not None:
            return i
        if lookup_disk:
            row = conn.execute("SELECT id FROM positions WHERE fen = ?", (fen,)).fetchone()
            if row is not None:
                ids[fen] = row[0]
                return row[0]
        i = next_pos_id
        next_pos_id += 1
        ids[fen] = i
        position_buf.append((i, fen))
        return i

    def flush():
        with conn:
            db.write_positions(conn, position_buf)
            db.write_moves(conn, move_buf)
            db.write_game_facts(conn, fact_buf)
            db.write_games_meta(conn, meta_buf)
        position_buf.clear()
        move_buf.clear()
        fact_buf.clear()
        meta_buf.clear()
        # No reader is open here (batches are fetched with fetchall), so the WAL can be fully
        # checkpointed and truncated — this is what keeps it from growing for the whole build.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    progress, task = _make_progress(console, total)
    game_id = next_game_id
    n_new = 0
    try:
        for rows in _game_batches(conn, new_uuids):
            for game in rows:
                if progress is not None:
                    progress.advance(task)
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
                n_new += 1
                if len(move_buf) >= batch:
                    flush()
            flush()  # flush at each read-batch boundary (also truncates the WAL)

        # The start position's id, so the frontend can bootstrap navigation. Stable across runs
        # (resolved from disk on incremental); the final flush persists it on a brand-new db.
        root_id = pid(Board().position_key())
        flush()
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('max_ply', ?)", (str(max_ply),))
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('root_id', ?)", (str(root_id),))
    finally:
        if progress is not None:
            progress.stop()

    n_edges = conn.execute("SELECT COUNT(*) FROM moves").fetchone()[0]
    n_facts = conn.execute("SELECT COUNT(*) FROM game_facts").fetchone()[0]
    n_games = conn.execute("SELECT COUNT(*) FROM games_meta").fetchone()[0]

    if rebuild:
        # Compact/defragment the freshly-loaded index B-trees (streaming inserts land in non-key
        # order). Free the fen cache and force temp storage to disk first: an in-memory VACUUM of
        # the multi-GB file is what OOM-killed an earlier build.
        ids.clear()
        conn.execute("PRAGMA temp_store=FILE")
        conn.execute("VACUUM")
    conn.close()
    return {"new_games": n_new, "total_games": n_games, "edges": n_edges, "facts": n_facts}


def _make_progress(console, total):
    """Return (Progress, task_id) when a console is given, else (None, None)."""
    if console is None:
        return None, None
    from rich.progress import (
        BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn,
    )
    progress = Progress(
        TextColumn("[bold blue]indexing"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("games"),
        TimeElapsedColumn(),
        console=console,
    )
    progress.start()
    task = progress.add_task("indexing", total=total)
    return progress, task
