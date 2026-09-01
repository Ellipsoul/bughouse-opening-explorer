import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from bughouse_explorer.insights.material import build_material_insights
from bughouse_explorer.tcn import _PIECES, _T


STANDARD_INITIAL_SETUP = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
)
SNAPSHOT_SHA256 = "a" * 64
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _token(source: str, target: str) -> str:
    def index(square: str) -> int:
        return (int(square[1]) - 1) * 8 + ord(square[0]) - ord("a")

    return _T[index(source)] + _T[index(target)]


def _promotion_token(source: str, target: str, promotion: str) -> str:
    def index(square: str) -> int:
        return (int(square[1]) - 1) * 8 + ord(square[0]) - ord("a")

    source_index = index(source)
    target_index = index(target)
    direction = -8 if source_index < 16 else 8
    adjustment = target_index - (source_index + direction) + 1
    assert 0 <= adjustment <= 2
    encoded_target = 64 + _PIECES.index(promotion) * 3 + adjustment
    return _T[source_index] + _T[encoded_target]


def _drop_token(piece: str, target: str) -> str:
    target_index = (int(target[1]) - 1) * 8 + ord(target[0]) - ord("a")
    return _T[79 + _PIECES.index(piece)] + _T[target_index]


def _create_snapshot(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE players (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_username TEXT NOT NULL,
            state TEXT NOT NULL,
            tracking_started_at INTEGER
        );
        CREATE TABLE games (
            uuid TEXT PRIMARY KEY,
            end_time INTEGER,
            time_control TEXT,
            rated INTEGER,
            rules TEXT NOT NULL,
            tcn TEXT,
            initial_setup TEXT,
            url TEXT,
            source TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            content_hash TEXT NOT NULL
        );
        CREATE TABLE game_participants (
            game_uuid TEXT NOT NULL,
            color TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            rating INTEGER,
            result TEXT,
            rating_source TEXT NOT NULL,
            PRIMARY KEY (game_uuid, color)
        );
        """
    )
    return connection


def _add_player(
    connection: sqlite3.Connection,
    player_id: int,
    username: str,
    *,
    tracked: bool = True,
) -> None:
    connection.execute(
        "INSERT INTO players VALUES (?, ?, ?, 'eligible', ?)",
        (player_id, username.casefold(), username, 1_700_000_000 if tracked else None),
    )


def _add_game(
    connection: sqlite3.Connection,
    uuid: str,
    tcn: str,
    white_id: int,
    black_id: int,
    *,
    url: str | None = None,
    end_time: int | None = 1_700_000_000,
) -> None:
    connection.execute(
        """
        INSERT INTO games VALUES (
            ?, ?, '180', 1, 'bughouse', ?, ?,
            ?, 'public', '{}', ?
        )
        """,
        (uuid, end_time, tcn, STANDARD_INITIAL_SETUP, url, f"hash-{uuid}"),
    )
    connection.executemany(
        """
        INSERT INTO game_participants VALUES (?, ?, ?, 2000, ?, 'public')
        """,
        [
            (uuid, "white", white_id, "win"),
            (uuid, "black", black_id, "checkmated"),
        ],
    )


def test_build_records_a_capture_for_both_tracked_players(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "game-1",
        _token("e2", "e4") + _token("d7", "d5") + _token("e4", "d5"),
        1,
        2,
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    report = build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT p.username, g.analyzed_games, m.piece_type,
                   m.pieces_won, m.pieces_lost
            FROM players AS p
            JOIN player_game_counts AS g USING (player_id)
            JOIN player_material AS m USING (player_id)
            WHERE m.piece_type = 'pawn'
            ORDER BY p.username
            """
        ).fetchall()

    assert rows == [
        ("alice", 1, "pawn", 1, 0),
        ("bob", 1, "pawn", 0, 1),
    ]
    assert report.accepted_games == 1
    assert report.analyzed_games == 1
    assert report.replay_excluded_games == 0


def test_build_records_one_material_game_high_for_both_presets_and_players(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "game-1",
        _token("e2", "e4") + _token("d7", "d5") + _token("e4", "d5"),
        1,
        2,
        url="https://www.chess.com/game/live/123456789",
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT p.username, h.preset, h.direction, h.rank,
                   h.net_material_x2, h.game_uuid, h.game_url,
                   h.player_color, h.position_fen
            FROM player_material_game_highs AS h
            JOIN players AS p USING (player_id)
            ORDER BY p.username, h.preset, h.direction
            """
        ).fetchall()

    final_fen = (
        "rnbqkbnr/ppp1pppp/8/3P4/8/8/PPPP1PPP/RNBQKBNR b KQkq -"
    )
    assert rows == [
        (
            "alice", "bughouse", "won", 1, 3, "game-1",
            "https://www.chess.com/game/live/123456789", "white", final_fen,
        ),
        (
            "alice", "standard", "won", 1, 2, "game-1",
            "https://www.chess.com/game/live/123456789", "white", final_fen,
        ),
        (
            "bob", "bughouse", "lost", 1, -3, "game-1",
            "https://www.chess.com/game/live/123456789", "black", final_fen,
        ),
        (
            "bob", "standard", "lost", 1, -2, "game-1",
            "https://www.chess.com/game/live/123456789", "black", final_fen,
        ),
    ]


def test_material_game_highs_rank_the_signed_net_not_gross_captures(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "queen-for-rook",
        _token("a2", "d8") + _token("a7", "a1"),
        1,
        2,
        url="https://www.chess.com/game/live/987654321",
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(snapshot, output, snapshot_sha256=SNAPSHOT_SHA256)

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT p.username, h.preset, h.direction, h.net_material_x2
            FROM player_material_game_highs AS h
            JOIN players AS p USING (player_id)
            ORDER BY p.username, h.preset
            """
        ).fetchall()

    assert rows == [
        ("alice", "bughouse", "won", 6),
        ("alice", "standard", "won", 8),
        ("bob", "bughouse", "lost", -6),
        ("bob", "standard", "lost", -8),
    ]


def test_material_game_highs_retain_only_the_best_three_games_per_preset(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    for game_uuid, target, url_id in (
        ("queen", "d8", 1),
        ("rook", "a8", 2),
        ("knight", "b8", 3),
        ("pawn", "a7", 4),
    ):
        _add_game(
            connection,
            game_uuid,
            _token("a2", target),
            1,
            2,
            url=f"https://www.chess.com/game/live/{url_id}",
        )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(snapshot, output, snapshot_sha256=SNAPSHOT_SHA256)

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT preset, rank, net_material_x2, game_uuid
            FROM player_material_game_highs
            WHERE player_id = 1 AND direction = 'won'
            ORDER BY preset, rank
            """
        ).fetchall()

    assert rows == [
        ("bughouse", 1, 14, "queen"),
        ("bughouse", 2, 8, "rook"),
        ("bughouse", 3, 6, "knight"),
        ("standard", 1, 18, "queen"),
        ("standard", 2, 10, "rook"),
        ("standard", 3, 6, "knight"),
    ]


def test_material_game_high_ties_prefer_newer_games_then_stable_identity(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    for game_uuid, end_time, url_id in (
        ("old", 100, 1),
        ("new-b", 200, 2),
        ("new-a", 200, 3),
        ("unknown-time", None, 4),
    ):
        _add_game(
            connection,
            game_uuid,
            _token("a2", "d8"),
            1,
            2,
            url=f"https://www.chess.com/game/live/{url_id}",
            end_time=end_time,
        )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(snapshot, output, snapshot_sha256=SNAPSHOT_SHA256)

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT rank, game_uuid, end_time
            FROM player_material_game_highs
            WHERE player_id = 1 AND preset = 'bughouse' AND direction = 'won'
            ORDER BY rank
            """
        ).fetchall()

    assert rows == [
        (1, "new-a", 200),
        (2, "new-b", 200),
        (3, "old", 100),
    ]


def test_build_keeps_raw_color_drops_and_rank_normalizes_the_combined_view(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "opposite-colour-drops",
        _drop_token("n", "e6") + _drop_token("n", "e3"),
        1,
        2,
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        color_rows = insights.execute(
            """
            SELECT p.username, d.player_color, d.piece_type, d.square, d.drops
            FROM players AS p
            JOIN player_drop_squares AS d USING (player_id)
            WHERE d.drops <> 0
            ORDER BY p.username, d.player_color, d.piece_type, d.square
            """
        ).fetchall()
        combined_rows = insights.execute(
            """
            SELECT username, piece_type, square, drops
            FROM player_drop_heatmaps_combined
            WHERE drops <> 0
            ORDER BY username, piece_type, square
            """
        ).fetchall()

    assert color_rows == [
        ("alice", "white", "knight", "e6", 1),
        ("bob", "black", "knight", "e3", 1),
    ]
    assert combined_rows == [
        ("alice", "knight", "e6", 1),
        ("bob", "knight", "e6", 1),
    ]


def test_drop_heatmap_view_exposes_piece_total_and_square_proportion(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "two-white-knight-drops",
        (
            _drop_token("n", "e6")
            + _drop_token("p", "a3")
            + _drop_token("n", "d5")
        ),
        1,
        2,
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT square, drops, piece_drops, drop_proportion
            FROM player_drop_heatmaps
            WHERE username = 'alice' AND piece_type = 'knight' AND drops <> 0
            ORDER BY square
            """
        ).fetchall()

    assert rows == [("d5", 1, 2, 0.5), ("e6", 1, 2, 0.5)]


def test_build_records_king_height_from_each_players_back_rank(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    moves = [
        _token("a2", "a3"),
        _token("e7", "e5"),
        _token("a3", "a4"),
        _token("e8", "e7"),
        _token("a4", "a5"),
        _token("e7", "e6"),
    ]
    _add_game(connection, "opposite-directions", "".join(moves), 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT p.username, h.height, h.games
            FROM players AS p
            JOIN player_king_height AS h USING (player_id)
            WHERE h.games <> 0
            ORDER BY p.username
            """
        ).fetchall()
        scores = insights.execute(
            """
            SELECT username, analyzed_games, weighted_height_sum,
                   average_king_height
            FROM player_king_height_scores
            ORDER BY username
            """
        ).fetchall()

    assert rows == [("alice", 1, 1), ("bob", 3, 1)]
    assert scores == [("alice", 1, 1, 1.0), ("bob", 1, 3, 3.0)]


def test_zero_game_player_has_zero_buckets_and_no_average(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        result = insights.execute(
            """
            SELECT s.analyzed_games, s.weighted_height_sum,
                   s.average_king_height, count(h.height), sum(h.games)
            FROM player_king_height_scores AS s
            JOIN player_king_height AS h USING (player_id)
            WHERE s.username = 'alice'
            GROUP BY s.player_id
            """
        ).fetchone()

    assert result == (0, 0, None, 8, 0)


def test_same_account_in_both_seats_contributes_one_game_at_the_higher_height(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    moves = [
        _token("a2", "a3"),
        _token("e7", "e5"),
        _token("a3", "a4"),
        _token("e8", "e7"),
        _token("a4", "a5"),
        _token("e7", "e6"),
    ]
    _add_game(connection, "same-account", "".join(moves), 1, 1)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        counts = insights.execute(
            """
            SELECT g.eligible_games, g.analyzed_games, h.height, h.games
            FROM player_game_counts AS g
            JOIN player_king_height AS h USING (player_id)
            WHERE h.games <> 0
            """
        ).fetchall()

    assert counts == [(1, 1, 3, 1)]


def test_height_eight_game_is_stored_as_sparse_public_evidence(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    moves = [
        _token("e2", "e4"), _token("a7", "a6"),
        _token("e1", "e2"), _token("a6", "a5"),
        _token("e2", "e3"), _token("b8", "a6"),
        _token("e3", "d4"), _token("a6", "b8"),
        _token("d4", "c5"), _token("b8", "a6"),
        _token("c5", "b6"), _token("a6", "b8"),
        _token("b6", "a7"), _token("b8", "a6"),
        _token("a7", "a8"),
    ]
    _add_game(
        connection,
        "white-crossing",
        "".join(moves),
        1,
        2,
        url="https://www.chess.com/game/live/123456789",
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        height_eight = insights.execute(
            """
            SELECT p.username, e.game_uuid, e.game_url, e.end_time, e.player_color
            FROM king_height_eight_games AS e
            JOIN players AS p USING (player_id)
            """
        ).fetchall()

    assert height_eight == [
        (
            "alice",
            "white-crossing",
            "https://www.chess.com/game/live/123456789",
            1_700_000_000,
            "white",
        )
    ]


def test_undefined_tcn_fragment_excludes_the_whole_game_and_records_anomaly(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    capture_prefix = (
        _token("e2", "e4")
        + _token("d7", "d5")
        + _token("e4", "d5")
    )
    _add_game(
        connection,
        "undefined-tail",
        capture_prefix + "undefineda",
        1,
        2,
        url="https://www.chess.com/game/live/135792468",
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    report = build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        alice = insights.execute(
            """
            SELECT g.eligible_games, g.analyzed_games,
                   g.replay_excluded_games, sum(m.pieces_won)
            FROM players AS p
            JOIN player_game_counts AS g USING (player_id)
            JOIN player_material AS m USING (player_id)
            WHERE p.username = 'alice'
            GROUP BY p.player_id
            """
        ).fetchone()
        anomalies = insights.execute(
            "SELECT game_uuid, reason FROM material_anomalies"
        ).fetchall()
        king_height_games = insights.execute(
            """
            SELECT sum(h.games)
            FROM players AS p
            JOIN player_king_height AS h USING (player_id)
            WHERE p.username = 'alice'
            """
        ).fetchone()[0]
        height_eight_games = insights.execute(
            "SELECT count(*) FROM king_height_eight_games"
        ).fetchone()[0]
        material_game_highs = insights.execute(
            "SELECT count(*) FROM player_material_game_highs"
        ).fetchone()[0]

    assert alice == (1, 0, 1, 0)
    assert anomalies == [("undefined-tail", "undefined_tcn_fragment")]
    assert king_height_games == 0
    assert height_eight_games == 0
    assert material_game_highs == 0
    assert report.accepted_games == 1
    assert report.analyzed_games == 0
    assert report.replay_excluded_games == 1


def test_structural_replay_failure_does_not_keep_prefix_captures(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    moves = [
        _token("e2", "e4"),
        _token("d7", "d5"),
        _token("e4", "d5"),
        _token("a7", "a6"),
        _token("e4", "e5"),  # e4 is empty after White captured on d5.
    ]
    _add_game(connection, "bad-replay", "".join(moves), 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        won = insights.execute(
            """
            SELECT sum(m.pieces_won)
            FROM players AS p
            JOIN player_material AS m USING (player_id)
            WHERE p.username = 'alice'
            """
        ).fetchone()[0]
        anomaly = insights.execute(
            """
            SELECT reason, ply_index, move_token
            FROM material_anomalies
            WHERE game_uuid = 'bad-replay'
            """
        ).fetchone()

    assert won == 0
    assert anomaly == ("missing_source_piece", 4, moves[4])


def test_malformed_tail_does_not_keep_prefix_drop_counts(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "drop-before-undefined-tail",
        _drop_token("q", "d5") + _token("a7", "a6") + "undefineda",
        1,
        2,
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        result = insights.execute(
            """
            SELECT g.analyzed_games, g.replay_excluded_games, sum(d.drops)
            FROM players AS p
            JOIN player_game_counts AS g USING (player_id)
            JOIN player_drop_squares AS d USING (player_id)
            WHERE p.username = 'alice'
            GROUP BY p.player_id
            """
        ).fetchone()

    assert result == (0, 1, 0)


def test_same_account_combines_both_seats_drops_but_counts_one_game(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_game(
        connection,
        "same-account-drops",
        _drop_token("n", "e6") + _drop_token("b", "c3"),
        1,
        1,
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        combined_games = insights.execute(
            "SELECT analyzed_games FROM player_game_counts"
        ).fetchone()[0]
        color_games = insights.execute(
            """
            SELECT player_color, analyzed_games
            FROM player_drop_color_game_counts
            ORDER BY player_color
            """
        ).fetchall()
        drops = insights.execute(
            """
            SELECT player_color, piece_type, square, drops
            FROM player_drop_squares
            WHERE drops <> 0
            ORDER BY player_color, piece_type, square
            """
        ).fetchall()

    assert combined_games == 1
    assert color_games == [("black", 1), ("white", 1)]
    assert drops == [
        ("black", "bishop", "c3", 1),
        ("white", "knight", "e6", 1),
    ]


def test_capturing_a_promoted_piece_counts_as_capturing_a_pawn(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    moves = [
        _token("h2", "h3"),
        _token("a7", "a6"),
        _token("h3", "h4"),
        _token("a6", "a5"),
        _token("a2", "a7"),
        _token("h7", "h6"),
        _promotion_token("a7", "a8", "q"),
        _promotion_token("b7", "a8", "q"),
    ]
    _add_game(
        connection,
        "promoted-capture",
        "".join(moves),
        1,
        2,
        url="https://www.chess.com/game/live/246813579",
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT p.username, m.piece_type, m.pieces_won, m.pieces_lost
            FROM players AS p
            JOIN player_material AS m USING (player_id)
            WHERE m.pieces_won <> 0 OR m.pieces_lost <> 0
            ORDER BY p.username, m.piece_type
            """
        ).fetchall()
        game_highs = insights.execute(
            """
            SELECT p.username, h.preset, h.direction, h.net_material_x2
            FROM player_material_game_highs AS h
            JOIN players AS p USING (player_id)
            ORDER BY p.username, h.preset
            """
        ).fetchall()

    assert rows == [
        ("alice", "pawn", 0, 1),
        ("alice", "rook", 1, 0),
        ("bob", "pawn", 1, 0),
        ("bob", "rook", 0, 1),
    ]
    assert game_highs == [
        ("alice", "bughouse", "won", 5),
        ("alice", "standard", "won", 8),
        ("bob", "bughouse", "lost", -5),
        ("bob", "standard", "lost", -8),
    ]


def test_capturing_a_dropped_piece_uses_the_dropped_piece_type(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    moves = [
        _drop_token("q", "e4"),
        _token("d7", "d5"),
        _token("a2", "a3"),
        _token("d5", "e4"),
    ]
    _add_game(connection, "dropped-capture", "".join(moves), 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT p.username, m.pieces_won, m.pieces_lost
            FROM players AS p
            JOIN player_material AS m USING (player_id)
            WHERE m.piece_type = 'queen'
            ORDER BY p.username
            """
        ).fetchall()

    assert rows == [("alice", 0, 1), ("bob", 1, 0)]


def test_duplicate_tcn_plus_symbol_decodes_as_a_bishop_drop(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    moves = [
        _drop_token("b", "e4"),
        _token("d7", "d5"),
        _token("a2", "a3"),
        _token("d5", "e4"),
    ]
    _add_game(connection, "bishop-drop", "".join(moves), 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        bishop_rows = insights.execute(
            """
            SELECT p.username, m.pieces_won, m.pieces_lost
            FROM players AS p
            JOIN player_material AS m USING (player_id)
            WHERE m.piece_type = 'bishop'
            ORDER BY p.username
            """
        ).fetchall()
        anomalies = insights.execute(
            "SELECT count(*) FROM material_anomalies"
        ).fetchone()[0]

    assert bishop_rows == [("alice", 0, 1), ("bob", 1, 0)]
    assert anomalies == 0


def test_en_passant_counts_the_removed_pawn(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    moves = [
        _token("e2", "e4"),
        _token("a7", "a6"),
        _token("e4", "e5"),
        _token("d7", "d5"),
        _token("e5", "d6"),
    ]
    _add_game(connection, "en-passant", "".join(moves), 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        rows = insights.execute(
            """
            SELECT p.username, m.pieces_won, m.pieces_lost
            FROM players AS p
            JOIN player_material AS m USING (player_id)
            WHERE m.piece_type = 'pawn'
            ORDER BY p.username
            """
        ).fetchall()

    assert rows == [("alice", 1, 0), ("bob", 0, 1)]


def test_a_future_permanently_tracked_player_is_included_on_the_next_build(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob", tracked=False)
    _add_game(
        connection,
        "game-1",
        _token("e2", "e4") + _token("d7", "d5") + _token("e4", "d5"),
        1,
        2,
    )
    connection.commit()
    connection.close()

    first_output = tmp_path / "first-insights.db"
    build_material_insights(
        snapshot,
        first_output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )
    with sqlite3.connect(first_output) as insights:
        first_players = insights.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()

    with sqlite3.connect(snapshot) as connection:
        connection.execute(
            "UPDATE players SET tracking_started_at = 1700000001 WHERE username = 'bob'"
        )
        connection.commit()

    second_output = tmp_path / "second-insights.db"
    build_material_insights(
        snapshot,
        second_output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )
    with sqlite3.connect(second_output) as insights:
        second_players = insights.execute(
            "SELECT username FROM players ORDER BY username"
        ).fetchall()

    assert first_players == [("alice",)]
    assert second_players == [("alice",), ("bob",)]


def test_database_exposes_build_metadata_and_derived_material_scores(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "game-1",
        _token("e2", "e4") + _token("d7", "d5") + _token("e4", "d5"),
        1,
        2,
    )
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    report = build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        build = insights.execute(
            """
            SELECT dataset_version, schema_version, source_snapshot_sha256,
                   adapter_policy_version, analyzer_version,
                       king_height_analyzer_version, drop_heatmap_analyzer_version,
                       material_game_highs_analyzer_version,
                   cohort_policy, accepted_games,
                   analyzed_games, replay_excluded_games, tracked_players,
                   accepted_plies, analyzed_plies
            FROM insight_builds
            """
        ).fetchone()
        scores = insights.execute(
            """
            SELECT username, material_won, material_lost, net_material,
                   average_material_won_per_game
            FROM player_material_scores
            WHERE preset = 'bughouse'
            ORDER BY username
            """
        ).fetchall()

    assert build == (
        report.dataset_version,
            4,
        SNAPSHOT_SHA256,
        "opening-adapter-v2-short-non-checkmate",
        "player-material-v1",
        "player-king-height-v1",
            "player-drop-heatmap-v1",
            "player-material-game-highs-v1",
        "permanent-tracking-v1",
        1,
        1,
        0,
        2,
        3,
        3,
    )
    assert scores == [
        ("alice", 1.5, 0.0, 1.5, 1.5),
        ("bob", 0.0, 1.5, -1.5, 0.0),
    ]


def test_drop_heatmap_schema_and_analyzer_are_recorded_in_build_identity(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    report = build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        build = insights.execute(
            """
            SELECT schema_version, drop_heatmap_analyzer_version,
                   material_game_highs_analyzer_version
            FROM insight_builds
            """
        ).fetchone()

    assert build == (
        4,
        "player-drop-heatmap-v1",
        "player-material-game-highs-v1",
    )
    assert report.schema_version == 4
    assert report.drop_heatmap_analyzer_version == "player-drop-heatmap-v1"


def test_build_script_verifies_the_snapshot_and_writes_a_result_report(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "game-1",
        _token("e2", "e4") + _token("d7", "d5") + _token("e4", "d5"),
        1,
        2,
    )
    connection.commit()
    connection.close()
    snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()

    output = tmp_path / "insights.db"
    result_path = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "build_player_insights.py"),
            str(snapshot),
            str(output),
            "--snapshot-sha256",
            snapshot_sha256,
            "--result",
            str(result_path),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    stdout_payload = json.loads(completed.stdout)
    result_payload = json.loads(result_path.read_text())
    assert stdout_payload == result_payload
    assert result_payload["accepted_games"] == 1
    assert result_payload["analyzed_games"] == 1
    assert result_payload["schema_version"] == 4
    assert result_payload["material_analyzer_version"] == "player-material-v1"
    assert result_payload["king_height_analyzer_version"] == "player-king-height-v1"
    assert result_payload["drop_heatmap_analyzer_version"] == "player-drop-heatmap-v1"
    assert (
        result_payload["material_game_highs_analyzer_version"]
        == "player-material-game-highs-v1"
    )
    assert result_payload["cohort_policy"] == "permanent-tracking-v1"
    assert result_payload["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_adapter_exclusions_are_counted_in_the_insights_database(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(connection, "empty", "", 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    report = build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        skips = insights.execute(
            "SELECT reason, games FROM adapter_skips ORDER BY reason"
        ).fetchall()

    assert skips == [("empty_tcn", 1)]
    assert report.adapter_skips == {"empty_tcn": 1}


def test_wrong_side_move_is_a_counted_replay_anomaly(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    bad_token = _token("e7", "e6")
    _add_game(connection, "wrong-side", bad_token, 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        anomaly = insights.execute(
            """
            SELECT reason, ply_index, move_token
            FROM material_anomalies
            WHERE game_uuid = 'wrong-side'
            """
        ).fetchone()

    assert anomaly == ("wrong_side_piece", 0, bad_token)


def test_drop_onto_an_occupied_square_is_a_counted_replay_anomaly(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    bad_token = _drop_token("q", "e2")
    _add_game(connection, "occupied-drop", bad_token, 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        anomaly = insights.execute(
            """
            SELECT reason, ply_index, move_token
            FROM material_anomalies
            WHERE game_uuid = 'occupied-drop'
            """
        ).fetchone()

    assert anomaly == ("occupied_drop", 0, bad_token)


def test_self_capture_is_a_counted_replay_anomaly(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    bad_token = _token("e2", "e1")
    _add_game(connection, "self-capture", bad_token, 1, 2)
    connection.commit()
    connection.close()

    output = tmp_path / "insights.db"
    build_material_insights(
        snapshot,
        output,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    with sqlite3.connect(output) as insights:
        anomaly = insights.execute(
            """
            SELECT reason, ply_index, move_token
            FROM material_anomalies
            WHERE game_uuid = 'self-capture'
            """
        ).fetchone()

    assert anomaly == ("self_capture", 0, bad_token)


def test_repeated_builds_are_byte_identical(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    connection = _create_snapshot(snapshot)
    _add_player(connection, 1, "Alice")
    _add_player(connection, 2, "Bob")
    _add_game(
        connection,
        "game-1",
        _token("e2", "e4") + _token("d7", "d5") + _token("e4", "d5"),
        1,
        2,
    )
    connection.commit()
    connection.close()

    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    first_report = build_material_insights(
        snapshot,
        first,
        snapshot_sha256=SNAPSHOT_SHA256,
    )
    second_report = build_material_insights(
        snapshot,
        second,
        snapshot_sha256=SNAPSHOT_SHA256,
    )

    assert first_report.dataset_version == second_report.dataset_version
    assert first.read_bytes() == second.read_bytes()
