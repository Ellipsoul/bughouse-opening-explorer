"""Schema and write helpers for the unified bughouse database.

One SQLite file now holds both layers of the pipeline:

* **Raw store** (written by ``download``): ``games`` — one row per board, keyed by chess.com's
  ``uuid`` (so downloading several usernames dedups shared games for free) — and ``archives``,
  the resume ledger (one row per ``(username, year, month)``; ``complete`` months are never
  re-fetched).
* **Derived index** (written by ``index``): ``positions``, ``moves``, ``game_facts``,
  ``games_meta`` — the per-game position graph the query server aggregates live. ``index`` reads
  ``games`` from the same file, so there is no separate ``games.db``.

The ``meta(key, value)`` table is shared: the raw layer stores ``schema_version``; the index
stores ``max_ply`` and ``root_id``. The keys never collide.

Why the two extra indexes vs. the old standalone explorer.db:

* ``idx_positions_fen`` — incremental indexing must look up a position by FEN across runs (the
  full-rebuild indexer kept the whole ``fen -> id`` map in RAM and never needed an on-disk index).
* ``idx_games_meta_uuid`` — to find which raw ``games`` have not been indexed yet.
"""

import json
import os
import sqlite3
import time

# Bumped from "1": the raw store and the derived index now coexist in one file.
SCHEMA_VERSION = "2"

# --- raw store (downloaded games + resume ledger) --------------------------
_RAW_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    uuid           TEXT PRIMARY KEY,
    source_username TEXT,
    year           INTEGER,
    month          INTEGER,
    end_time       INTEGER,
    time_control   TEXT,
    time_class     TEXT,
    rated          INTEGER,
    white_username TEXT,
    white_rating   INTEGER,
    white_result   TEXT,
    black_username TEXT,
    black_rating   INTEGER,
    black_result   TEXT,
    eco            TEXT,
    initial_setup  TEXT,
    fen            TEXT,
    tcn            TEXT,
    moves_json     TEXT,
    url            TEXT
);
CREATE INDEX IF NOT EXISTS idx_games_end_time ON games(end_time);
CREATE INDEX IF NOT EXISTS idx_games_white ON games(white_username);
CREATE INDEX IF NOT EXISTS idx_games_black ON games(black_username);

CREATE TABLE IF NOT EXISTS archives (
    username   TEXT,
    year       INTEGER,
    month      INTEGER,
    status     TEXT,
    game_count INTEGER,
    fetched_at INTEGER,
    PRIMARY KEY (username, year, month)
);
"""

# --- derived index (position graph) ----------------------------------------
_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id  INTEGER PRIMARY KEY,
    fen TEXT NOT NULL
);
-- Lets an incremental run resolve an existing position by FEN (the in-memory fen->id cache only
-- holds positions touched in the current run). Unique because the indexer never emits a FEN twice.
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_fen ON positions(fen);

CREATE TABLE IF NOT EXISTS moves (
    parent_id  INTEGER NOT NULL,
    move_id    TEXT    NOT NULL,
    san        TEXT    NOT NULL,
    from_sq    TEXT,              -- null for drops
    to_sq      TEXT    NOT NULL,
    drop_piece TEXT,              -- null for non-drops
    child_id   INTEGER NOT NULL,
    PRIMARY KEY (parent_id, move_id)
);

CREATE TABLE IF NOT EXISTS game_facts (
    parent_id       INTEGER NOT NULL,
    move_id         TEXT    NOT NULL,
    game_id         INTEGER NOT NULL,
    outcome         INTEGER NOT NULL,   -- denormalized from games_meta so the common (no-username)
                                        -- path can aggregate win/draw/loss without joining games_meta
    rating_sum      INTEGER NOT NULL,   -- white_rating + black_rating, for the rating filter
    PRIMARY KEY (parent_id, game_id),
    CHECK (outcome IN (0, 1, 2))
);

CREATE TABLE IF NOT EXISTS games_meta (
    game_id         INTEGER PRIMARY KEY,
    uuid            TEXT    NOT NULL,
    white_username  TEXT    NOT NULL,
    white_rating    INTEGER NOT NULL,
    black_username  TEXT    NOT NULL,
    black_rating    INTEGER NOT NULL,
    outcome         INTEGER NOT NULL,   -- 0 = white win, 1 = black win, 2 = draw.
    url             TEXT    NOT NULL,
    time_control    TEXT    NOT NULL,
    end_time        INTEGER NOT NULL,
    CHECK (outcome IN (0, 1, 2))
);
CREATE INDEX IF NOT EXISTS idx_meta_white ON games_meta(white_username);
CREATE INDEX IF NOT EXISTS idx_meta_black ON games_meta(black_username);
-- Lets an incremental run skip games that are already indexed (anti-join on games.uuid).
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_meta_uuid ON games_meta(uuid);
"""

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# Names of the derived tables, so ``index --rebuild`` can drop exactly the index layer and leave
# the raw store untouched. Order: children before the positions they reference (cosmetic; we drop
# by name, there are no FKs).
INDEX_TABLES = ["game_facts", "games_meta", "moves", "positions"]

_GAME_COLUMNS = [
    "uuid", "source_username", "year", "month", "end_time", "time_control",
    "time_class", "rated", "white_username", "white_rating", "white_result",
    "black_username", "black_rating", "black_result", "eco", "initial_setup",
    "fen", "tcn", "moves_json", "url",
]

MOVE_COLUMNS = ["parent_id", "move_id", "san", "from_sq", "to_sq", "drop_piece", "child_id"]

GAMES_META_COLUMNS = [
    "game_id", "uuid", "white_username", "white_rating",
    "black_username", "black_rating", "outcome",
    "url", "time_control", "end_time",
]


def connect(path):
    """Open (creating if needed) the unified database with all tables present."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)  # so the default data/ dir works on a fresh clone
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_RAW_SCHEMA + _INDEX_SCHEMA + _META_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
    return conn


def create_index_schema(conn):
    """(Re)create just the derived index tables/indexes — used after a rebuild drops them."""
    conn.executescript(_INDEX_SCHEMA)
    conn.commit()


def drop_index(conn):
    """Drop the derived index tables (and their indexes); leave the raw store intact."""
    with conn:
        for table in INDEX_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("DELETE FROM meta WHERE key IN ('max_ply', 'root_id')")


# --- raw store: game upserts + resume ledger -------------------------------

def completed_months(conn, username):
    """Return the set of (year, month) marked complete for this username."""
    rows = conn.execute(
        "SELECT year, month FROM archives WHERE username = ? AND status = 'complete'",
        (username,),
    ).fetchall()
    return {(r["year"], r["month"]) for r in rows}


def game_row(game, source_username, year, month, moves):
    """Flatten a chess.com game record into a tuple matching ``_GAME_COLUMNS``."""
    white = game.get("white", {})
    black = game.get("black", {})
    return (
        game["uuid"],
        source_username,
        year,
        month,
        game.get("end_time"),
        game.get("time_control"),
        game.get("time_class"),
        1 if game.get("rated") else 0,
        white.get("username"),
        white.get("rating"),
        white.get("result"),
        black.get("username"),
        black.get("rating"),
        black.get("result"),
        game.get("eco"),
        game.get("initial_setup"),
        game.get("fen"),
        game.get("tcn"),
        json.dumps(moves, separators=(",", ":")),
        game.get("url"),
    )


def save_month(conn, username, year, month, rows, status="complete"):
    """Upsert a month's games and mark the archive — atomically in one transaction.

    Committing per-month is what makes stop/resume safe: an interrupt mid-month rolls
    back only the in-flight month, leaving every earlier month intact.
    """
    placeholders = ", ".join(["?"] * len(_GAME_COLUMNS))
    columns = ", ".join(_GAME_COLUMNS)
    with conn:  # BEGIN ... COMMIT, or ROLLBACK on exception
        conn.executemany(
            f"INSERT OR REPLACE INTO games ({columns}) VALUES ({placeholders})",
            rows,
        )
        conn.execute(
            "INSERT OR REPLACE INTO archives "
            "(username, year, month, status, game_count, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, year, month, status, len(rows), int(time.time())),
        )


# --- derived index: batched writers (called by the indexer) ----------------

def write_positions(conn, rows):  # rows: (id, fen)
    conn.executemany("INSERT OR REPLACE INTO positions (id, fen) VALUES (?, ?)", rows)


def write_moves(conn, rows):
    # OR IGNORE: the streaming indexer re-emits an edge once per game it appears in; the first
    # write wins and the rest are skipped (the moves PK is (parent_id, move_id)).
    placeholders = ", ".join(["?"] * len(MOVE_COLUMNS))
    conn.executemany(
        f"INSERT OR IGNORE INTO moves ({', '.join(MOVE_COLUMNS)}) VALUES ({placeholders})",
        rows,
    )


def write_game_facts(conn, rows):  # rows: (parent_id, move_id, game_id, outcome, rating_sum)
    conn.executemany(
        "INSERT OR IGNORE INTO game_facts "
        "(parent_id, move_id, game_id, outcome, rating_sum) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )


def write_games_meta(conn, rows):
    placeholders = ", ".join(["?"] * len(GAMES_META_COLUMNS))
    # OR IGNORE: a game already indexed (same game_id) is skipped, keeping re-indexing idempotent.
    conn.executemany(
        f"INSERT OR IGNORE INTO games_meta ({', '.join(GAMES_META_COLUMNS)}) "
        f"VALUES ({placeholders})",
        rows,
    )
