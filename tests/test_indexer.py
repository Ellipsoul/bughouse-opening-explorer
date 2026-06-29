"""Tests for incremental indexing: new games are appended, re-runs are idempotent, and an
incremental build yields the same graph as a full rebuild (positions are shared across runs)."""

import json

from bughouse_explorer import db, indexer


def _insert_game(conn, uuid, moves, white_result="win", black_result="resigned",
                 white="alice", black="bob", wr=1600, br=1500):
    conn.execute(
        "INSERT INTO games (uuid, white_username, white_rating, white_result, "
        "black_username, black_rating, black_result, url, time_control, end_time, moves_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uuid, white, wr, white_result, black, br, black_result,
         f"https://chess.com/game/{uuid}", "180", 1700000000, json.dumps(moves)),
    )
    conn.commit()


# Two games that transpose through 1.e4: they must share the root and the post-e4 position.
GAME_A = [{"from": "e2", "to": "e4"}, {"from": "e7", "to": "e5"}]   # 1.e4 e5
GAME_B = [{"from": "e2", "to": "e4"}, {"from": "c7", "to": "c5"}]   # 1.e4 c5


def _counts(db_path):
    conn = db.connect(db_path)
    n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
         for t in ("positions", "moves", "game_facts", "games_meta")}
    conn.close()
    return n


def test_incremental_append_and_idempotency(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    _insert_game(conn, "A", GAME_A)
    conn.close()

    s1 = indexer.index(path)
    assert s1["new_games"] == 1
    assert _counts(path) == {"positions": 3, "moves": 2, "game_facts": 2, "games_meta": 1}

    # Add a second, transposing game and re-index: only the new game is processed.
    conn = db.connect(path)
    _insert_game(conn, "B", GAME_B)
    conn.close()

    s2 = indexer.index(path)
    assert s2["new_games"] == 1
    assert s2["total_games"] == 2
    # Positions: start, post-e4 (shared), post-e5, post-c5 = 4 (the shared ones were not duplicated).
    assert _counts(path) == {"positions": 4, "moves": 3, "game_facts": 4, "games_meta": 2}

    # Re-running with nothing new is a no-op.
    s3 = indexer.index(path)
    assert s3["new_games"] == 0
    assert _counts(path) == {"positions": 4, "moves": 3, "game_facts": 4, "games_meta": 2}


def test_root_and_meta(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    _insert_game(conn, "A", GAME_A)
    conn.close()
    indexer.index(path)

    conn = db.connect(path)
    meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    assert meta["max_ply"] == "40"
    # The start position both games begin from is the indexed root, and gets id 0.
    assert meta["root_id"] == "0"
    # Two facts at the root for game A's e4 in a one-game db -> here just one game so one fact.
    root_facts = conn.execute("SELECT COUNT(*) FROM game_facts WHERE parent_id = 0").fetchone()[0]
    assert root_facts == 1
    conn.close()


def test_incremental_matches_rebuild(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    _insert_game(conn, "A", GAME_A)
    conn.close()
    indexer.index(path)
    conn = db.connect(path)
    _insert_game(conn, "B", GAME_B)
    conn.close()
    indexer.index(path)
    incremental = _counts(path)

    # A full rebuild from the same raw games must reproduce the identical graph shape.
    indexer.index(path, rebuild=True)
    assert _counts(path) == incremental


def test_rebuild_changes_max_ply(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    _insert_game(conn, "A", GAME_A)
    conn.close()
    indexer.index(path, max_ply=40)

    # Changing max_ply without --rebuild is refused...
    try:
        indexer.index(path, max_ply=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when changing max_ply without rebuild")

    # ...but a rebuild applies it: only the first ply is recorded, so just 2 positions / 1 move.
    indexer.index(path, max_ply=1, rebuild=True)
    counts = _counts(path)
    assert counts["positions"] == 2
    assert counts["moves"] == 1
    assert counts["game_facts"] == 1
