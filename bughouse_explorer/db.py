"""Frozen SQLite schema and writers for the opening-index reference.

This module intentionally contains no Chess.com fetching or archive-ledger behavior. Its legacy
``games`` input table remains only so the replay/index implementation can be exercised until it is
ported to consume the crawler database. The derived ``positions``, ``moves``, ``game_facts``, and
``games_meta`` tables are queried by the reference server and frontend.

Why the two extra indexes vs. the old standalone explorer.db:

* ``idx_positions_fen_hash`` — incremental indexing must look up a position across runs (the
  full-rebuild indexer kept the whole ``fen -> id`` map in RAM and never needed an on-disk index).
  We index an 8-byte :func:`fen_hash` rather than the ~70-byte FEN text — a ~6x smaller index —
  and verify the FEN on the (vanishingly rare) hash hit.
* ``idx_games_meta_uuid`` — to find which legacy-input ``games`` have not been indexed yet.
"""

import hashlib
import os
import sqlite3

# Bumped from "3": positions resolves a FEN by an indexed 8-byte hash (idx_positions_fen_hash)
# instead of a UNIQUE index over the full FEN text. ("3" itself trimmed the raw ``games`` table.)
SCHEMA_VERSION = "4"

# Mean-rating floor the explorer treats as "any" — the frontend's rating slider bottoms out here
# (frontend RATING_MIN), so the default/unfiltered view queries at exactly this threshold. The
# precomputed ``move_agg`` table is materialized at this same floor so that view is a keyed lookup
# rather than a full scan of game_facts. Keep the three in sync if the floor ever changes.
RATING_FLOOR = 1000


def fen_hash(fen):
    """Stable 64-bit signed hash of a position FEN — the on-disk position lookup key.

    Must be deterministic across processes (unlike the salted built-in ``hash``) so an incremental
    build can find positions written by an earlier run. Collisions are astronomically unlikely over
    ~21M positions and harmless anyway: the indexer verifies the FEN text on every hash hit.
    """
    return int.from_bytes(
        hashlib.blake2b(fen.encode(), digest_size=8).digest(), "big", signed=True
    )

# --- legacy index input ----------------------------------------------------
# This table is retained for the frozen indexer's fixtures and existing prebuilt databases. New
# Chess.com data is written only to the crawler database; a future adapter will replace this shape.
_LEGACY_GAME_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    uuid           TEXT PRIMARY KEY,
    end_time       INTEGER,
    time_control   TEXT,
    white_username TEXT,
    white_rating   INTEGER,
    white_result   TEXT,
    black_username TEXT,
    black_rating   INTEGER,
    black_result   TEXT,
    tcn            TEXT,
    url            TEXT
);
"""

# --- derived index (position graph) ----------------------------------------
_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id       INTEGER PRIMARY KEY,
    fen      TEXT    NOT NULL,
    fen_hash INTEGER NOT NULL   -- db.fen_hash(fen); the across-run lookup key (see below)
);
-- Lets an incremental run resolve an existing position by FEN (the in-memory fen->id cache only
-- holds positions touched in the current run) without indexing the full ~70-byte FEN string: we
-- index the 8-byte hash and verify the FEN text on a hit. NOT unique -- hash collisions are
-- allowed; FEN uniqueness is upheld by the indexer (its id cache + verified lookup never insert a
-- FEN twice), not by this index.
CREATE INDEX IF NOT EXISTS idx_positions_fen_hash ON positions(fen_hash);

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
    -- One fact per (position, move) a game played: a game that revisits a position (repetition)
    -- and plays a different move from it contributes one fact per distinct move, so every
    -- continuation actually played stays visible in the explorer.
    PRIMARY KEY (parent_id, move_id, game_id),
    CHECK (outcome IN (0, 1, 2))
);
-- Reverse lookup from a game to its facts. Lets username-filtered queries drive from a player's
-- games (few) instead of scanning every game at a busy position (~1.3M near the opening root);
-- server.MOVES_USER_SQL forces that join order with CROSS JOIN.
CREATE INDEX IF NOT EXISTS idx_facts_game ON game_facts(game_id, parent_id);

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

-- Precomputed per-move aggregate at the RATING_FLOOR mean-rating threshold, so the common
-- unfiltered landing view is a keyed lookup instead of re-aggregating ~1.3M game_facts rows on
-- every hit. Populated wholesale after indexing (see indexer.rebuild_move_agg). The PRIMARY KEY
-- doubles as the parent_id lookup index.
CREATE TABLE IF NOT EXISTS move_agg (
    parent_id   INTEGER NOT NULL,
    move_id     TEXT    NOT NULL,
    n           INTEGER NOT NULL,
    white_wins  INTEGER NOT NULL,
    black_wins  INTEGER NOT NULL,
    draws       INTEGER NOT NULL,
    PRIMARY KEY (parent_id, move_id)
);
"""

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# Names of the derived tables, so ``index --rebuild`` can drop exactly the index layer and leave
# the legacy input untouched. Order: children before the positions they reference (cosmetic; we
# drop by name, there are no FKs).
INDEX_TABLES = ["move_agg", "game_facts", "games_meta", "moves", "positions"]

MOVE_COLUMNS = ["parent_id", "move_id", "san", "from_sq", "to_sq", "drop_piece", "child_id"]

GAMES_META_COLUMNS = [
    "game_id", "uuid", "white_username", "white_rating",
    "black_username", "black_rating", "outcome",
    "url", "time_control", "end_time",
]


def connect(path):
    """Open the frozen reference database with its input and index tables present."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)  # so the default data/ dir works on a fresh clone
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_LEGACY_GAME_SCHEMA + _INDEX_SCHEMA + _META_SCHEMA)
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
    """Drop the derived index tables while leaving the legacy input intact."""
    with conn:
        for table in INDEX_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("DELETE FROM meta WHERE key IN ('max_ply', 'root_id')")


# --- derived index: batched writers (called by the indexer) ----------------

def write_positions(conn, rows):  # rows: (id, fen, fen_hash)
    conn.executemany(
        "INSERT OR REPLACE INTO positions (id, fen, fen_hash) VALUES (?, ?, ?)", rows
    )


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
