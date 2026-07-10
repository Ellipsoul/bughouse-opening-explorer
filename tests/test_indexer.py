"""Tests for incremental indexing: new games are appended, re-runs are idempotent, and an
incremental build yields the same graph as a full rebuild (positions are shared across runs)."""

from bughouse_explorer import db, indexer
from bughouse_explorer.tcn import _T


def _encode_tcn(moves):
    """Inverse of ``decode_tcn`` for plain from/to moves — enough for these tests' fixtures.

    A square's tcn index is ``(rank - 1) * 8 + file``; each ply is the two chars for from, to.
    """
    def idx(sq):
        return (int(sq[1]) - 1) * 8 + "abcdefgh".index(sq[0])
    return "".join(_T[idx(m["from"])] + _T[idx(m["to"])] for m in moves)


def _insert_game(conn, uuid, moves, white_result="win", black_result="resigned",
                 white="alice", black="bob", wr=1600, br=1500):
    conn.execute(
        "INSERT INTO games (uuid, white_username, white_rating, white_result, "
        "black_username, black_rating, black_result, url, time_control, end_time, tcn) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uuid, white, wr, white_result, black, br, black_result,
         f"https://chess.com/game/{uuid}", "180", 1700000000, _encode_tcn(moves)),
    )
    conn.commit()


# Two games that transpose through 1.e4: they must share the root and the post-e4 position.
GAME_A = [{"from": "e2", "to": "e4"}, {"from": "e7", "to": "e5"}]   # 1.e4 e5
GAME_B = [{"from": "e2", "to": "e4"}, {"from": "c7", "to": "c5"}]   # 1.e4 c5

# A game that returns to the start position and plays a different move from it the second time
# (1.Nf3 Nf6 2.Ng1 Ng8 3.e4). Both moves actually played from the repeated position must get a
# fact, or the game's real continuation is invisible in the explorer — which then railroads
# navigation around the repetition loop and falsely reports the line drawn by repetition.
GAME_LOOP = [
    {"from": "g1", "to": "f3"}, {"from": "g8", "to": "f6"},
    {"from": "f3", "to": "g1"}, {"from": "f6", "to": "g8"},
    {"from": "e2", "to": "e4"},
]


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


def test_revisited_position_records_each_distinct_move(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    _insert_game(conn, "L", GAME_LOOP)
    conn.close()
    indexer.index(path)

    conn = db.connect(path)
    root = int(conn.execute("SELECT value FROM meta WHERE key = 'root_id'").fetchone()[0])
    root_moves = {r[0] for r in conn.execute(
        "SELECT move_id FROM game_facts WHERE parent_id = ?", (root,))}
    # Both first-move choices from the (revisited) start position are recorded...
    assert root_moves == {"g1f3", "e2e4"}
    # ...while a move replayed from the same position still counts once: 5 plies from 5 distinct
    # (position, move) pairs -> 5 facts.
    assert conn.execute("SELECT COUNT(*) FROM game_facts").fetchone()[0] == 5
    conn.close()


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
