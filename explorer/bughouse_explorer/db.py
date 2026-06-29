"""Schema and write helpers for ``explorer.db`` — a per-game facts graph.

The query server aggregates these tables live, so any filter (rating, username, side) is just a
WHERE over the same join — nothing is pre-aggregated by those dimensions. The only baked-in choice
is ``max_ply`` (how deep games are recorded).

* ``positions`` — id <-> FEN.
* ``moves`` — edge identity (one row per position->move): san/squares/child. No stats.
* ``game_facts`` — one row per (game, position, move played): the per-game plies. This is what
  makes username/side filtering possible — it links each game to the moves it played.
* ``games_meta`` — per-game metadata incl. a precomputed ``outcome`` so win/draw/loss is a simple
  SUM at query time.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id  INTEGER PRIMARY KEY,
    fen TEXT NOT NULL   -- not UNIQUE: dedup is done by the indexer's in-memory fen->id map (the only
                        -- writer), and the app navigates by integer id, so no fen->id index is needed
);

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
                                        -- The per-game result badge is derived from this; the raw
                                        -- white_result/black_result strings are not stored.
    url             TEXT    NOT NULL,
    time_control    TEXT    NOT NULL,
    end_time        INTEGER NOT NULL,
    CHECK (outcome IN (0, 1, 2))
);
CREATE INDEX IF NOT EXISTS idx_meta_white ON games_meta(white_username);
CREATE INDEX IF NOT EXISTS idx_meta_black ON games_meta(black_username);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

MOVE_COLUMNS = ["parent_id", "move_id", "san", "from_sq", "to_sq", "drop_piece", "child_id"]

GAMES_META_COLUMNS = [
    "game_id", "uuid", "white_username", "white_rating",
    "black_username", "black_rating", "outcome",
    "url", "time_control", "end_time",
]


def create(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _insert_many(conn, table, columns, rows):
    placeholders = ", ".join(["?"] * len(columns))
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        rows,
    )


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
    _insert_many(conn, "games_meta", GAMES_META_COLUMNS, rows)
