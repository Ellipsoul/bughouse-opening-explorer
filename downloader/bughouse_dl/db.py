"""SQLite storage: schema, game upserts, and the resume ledger.

Two tables carry the design:

* ``games`` — one row per board record, keyed by chess.com's ``uuid``. Because a uuid is
  unique per board, downloading several usernames into one DB dedups shared games for free.
* ``archives`` — the resume ledger: one row per ``(username, year, month)`` recording whether
  that month is fully downloaded. Past months are immutable on chess.com, so a ``complete``
  row is never re-fetched; only the current month is always refreshed.
"""

import json
import sqlite3
import time

SCHEMA_VERSION = "1"

_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_GAME_COLUMNS = [
    "uuid", "source_username", "year", "month", "end_time", "time_control",
    "time_class", "rated", "white_username", "white_rating", "white_result",
    "black_username", "black_rating", "black_result", "eco", "initial_setup",
    "fen", "tcn", "moves_json", "url",
]


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
    return conn


def completed_months(conn, username):
    """Return the set of (year, month) marked complete for this username."""
    rows = conn.execute(
        "SELECT year, month FROM archives WHERE username = ? AND status = 'complete'",
        (username,),
    ).fetchall()
    return {(r["year"], r["month"]) for r in rows}


def game_row(game, source_username, year, month, moves):
    """Flatten a chess.com game record into a tuple matching _GAME_COLUMNS."""
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
