import json
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from bughouse_explorer.insights.export import (
    export_drop_heatmap_insights,
    export_king_height_insights,
    export_material_game_highs,
    export_material_insights,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _create_insights(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE insight_builds (
                dataset_version TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                source_snapshot_sha256 TEXT NOT NULL,
                adapter_policy_version TEXT NOT NULL,
                analyzer_version TEXT NOT NULL,
                king_height_analyzer_version TEXT NOT NULL,
                drop_heatmap_analyzer_version TEXT NOT NULL,
                material_game_highs_analyzer_version TEXT NOT NULL,
                cohort_policy TEXT NOT NULL,
                accepted_games INTEGER NOT NULL,
                analyzed_games INTEGER NOT NULL,
                replay_excluded_games INTEGER NOT NULL,
                tracked_players INTEGER NOT NULL,
                accepted_plies INTEGER NOT NULL,
                analyzed_plies INTEGER NOT NULL
            );
            CREATE TABLE players (
                player_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_username TEXT NOT NULL,
                tracking_started_at INTEGER NOT NULL,
                source_state TEXT NOT NULL
            );
            CREATE TABLE player_game_counts (
                player_id INTEGER PRIMARY KEY,
                eligible_games INTEGER NOT NULL,
                analyzed_games INTEGER NOT NULL,
                replay_excluded_games INTEGER NOT NULL
            );
            CREATE TABLE player_material (
                player_id INTEGER NOT NULL,
                piece_type TEXT NOT NULL,
                pieces_won INTEGER NOT NULL,
                pieces_lost INTEGER NOT NULL,
                PRIMARY KEY (player_id, piece_type)
            );
            CREATE TABLE player_material_game_highs (
                player_id INTEGER NOT NULL,
                preset TEXT NOT NULL,
                direction TEXT NOT NULL,
                rank INTEGER NOT NULL,
                net_material_x2 INTEGER NOT NULL,
                game_uuid TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                game_url TEXT NOT NULL,
                end_time INTEGER,
                player_color TEXT NOT NULL,
                position_fen TEXT NOT NULL,
                PRIMARY KEY (player_id, preset, direction, rank)
            );
            CREATE TABLE material_piece_values (
                preset TEXT NOT NULL,
                piece_type TEXT NOT NULL,
                value_x2 INTEGER NOT NULL,
                PRIMARY KEY (preset, piece_type)
            );
            CREATE TABLE player_king_height (
                player_id INTEGER NOT NULL,
                height INTEGER NOT NULL,
                games INTEGER NOT NULL,
                PRIMARY KEY (player_id, height)
            );
            CREATE TABLE king_height_eight_games (
                player_id INTEGER NOT NULL,
                game_uuid TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                game_url TEXT,
                end_time INTEGER,
                player_color TEXT NOT NULL,
                PRIMARY KEY (player_id, game_uuid)
            );
            CREATE TABLE player_drop_squares (
                player_id INTEGER NOT NULL,
                player_color TEXT NOT NULL,
                piece_type TEXT NOT NULL,
                square TEXT NOT NULL,
                drops INTEGER NOT NULL,
                PRIMARY KEY (player_id, player_color, piece_type, square)
            );
            CREATE TABLE player_drop_color_game_counts (
                player_id INTEGER NOT NULL,
                player_color TEXT NOT NULL,
                eligible_games INTEGER NOT NULL,
                analyzed_games INTEGER NOT NULL,
                replay_excluded_games INTEGER NOT NULL,
                PRIMARY KEY (player_id, player_color)
            );
            """
        )
        connection.execute(
            "INSERT INTO insight_builds VALUES (?, 4, ?, ?, ?, ?, ?, ?, ?, 1, 1, 0, 1, 3, 3)",
            (
                "dataset-1",
                "a" * 64,
                "adapter-v1",
                "analyzer-v1",
                "king-height-v1",
                "drop-heatmap-v1",
                "material-game-highs-v1",
                "cohort-v1",
            ),
        )
        connection.execute(
            "INSERT INTO players VALUES (1, 'alice', 'Alice', 1700000000, 'eligible')"
        )
        connection.execute("INSERT INTO player_game_counts VALUES (1, 1, 1, 0)")
        connection.executemany(
            "INSERT INTO player_material VALUES (1, ?, ?, ?)",
            [
                ("pawn", 2, 1),
                ("knight", 3, 4),
                ("bishop", 5, 6),
                ("rook", 7, 8),
                ("queen", 9, 10),
            ],
        )
        connection.executemany(
            "INSERT INTO material_piece_values VALUES (?, ?, ?)",
            [
                ("bughouse", "pawn", 3),
                ("bughouse", "knight", 6),
                ("bughouse", "bishop", 6),
                ("bughouse", "rook", 8),
                ("bughouse", "queen", 14),
                ("standard", "pawn", 2),
                ("standard", "knight", 6),
                ("standard", "bishop", 6),
                ("standard", "rook", 10),
                ("standard", "queen", 18),
            ],
        )
        connection.executemany(
            "INSERT INTO player_material_game_highs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    1, "bughouse", "won", 1, 6, "internal-win", "hash-win",
                    "https://www.chess.com/game/live/111", 1_700_000_000,
                    "white",
                    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -",
                ),
                (
                    1, "bughouse", "lost", 1, -5, "internal-loss", "hash-loss",
                    "https://www.chess.com/game/live/222", 1_600_000_000,
                    "black",
                    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -",
                ),
                (
                    1, "standard", "won", 1, 8, "internal-win", "hash-win",
                    "https://www.chess.com/game/live/111", 1_700_000_000,
                    "white",
                    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -",
                ),
                (
                    1, "standard", "lost", 1, -8, "internal-loss", "hash-loss",
                    "https://www.chess.com/game/live/222", 1_600_000_000,
                    "black",
                    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -",
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO player_king_height VALUES (1, ?, ?)",
            [(height, 1 if height == 8 else 0) for height in range(1, 9)],
        )
        connection.execute(
            """
            INSERT INTO king_height_eight_games VALUES (
                1, 'internal-game-id', 'hash-game',
                'https://www.chess.com/game/live/123456789',
                1700000000, 'white'
            )
            """
        )
        connection.executemany(
            "INSERT INTO player_drop_color_game_counts VALUES (1, ?, 1, 1, 0)",
            [("white",), ("black",)],
        )
        connection.executemany(
            "INSERT INTO player_drop_squares VALUES (1, ?, ?, ?, ?)",
            [
                (
                    player_color,
                    piece_type,
                    f"{file_}{rank}",
                    (
                        3
                        if player_color == "white" and piece_type == "knight"
                        and file_ == "e" and rank == 6
                        else 1
                        if player_color == "black" and piece_type == "knight"
                        and file_ == "e" and rank == 3
                        else 0
                    ),
                )
                for player_color in ("white", "black")
                for piece_type in ("pawn", "knight", "bishop", "rook", "queen")
                for rank in range(1, 9)
                for file_ in "abcdefgh"
            ],
        )


def test_export_material_insights_writes_a_compact_deterministic_frontend_contract(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-material.json"
    _create_insights(database)

    report = export_material_insights(database, output)

    payload = json.loads(output.read_text())
    assert payload == {
        "schemaVersion": 1,
        "dataset": {
            "version": "dataset-1",
            "sourceSnapshotSha256": "a" * 64,
            "adapterPolicy": "adapter-v1",
            "analyzerVersion": "analyzer-v1",
            "cohortPolicy": "cohort-v1",
            "acceptedGames": 1,
            "analyzedGames": 1,
            "replayExcludedGames": 0,
            "trackedPlayers": 1,
        },
        "pieceOrder": ["pawn", "knight", "bishop", "rook", "queen"],
        "pieceValues": {
            "bughouse": [1.5, 3, 3, 4, 7],
            "standard": [1, 3, 3, 5, 9],
        },
        "players": [
            {
                "username": "alice",
                "displayName": "Alice",
                "eligibleGames": 1,
                "analyzedGames": 1,
                "replayExcludedGames": 0,
                "pieces": [[2, 1], [3, 4], [5, 6], [7, 8], [9, 10]],
            }
        ],
    }
    assert output.read_bytes().endswith(b"\n")
    assert report.players == 1
    assert report.output_bytes == output.stat().st_size


def test_export_material_game_highs_writes_only_public_ranked_game_evidence(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-material-game-highs.json"
    _create_insights(database)

    report = export_material_game_highs(database, output)

    payload = json.loads(output.read_text())
    assert payload == {
        "schemaVersion": 1,
        "dataset": {
            "version": "dataset-1",
            "sourceSnapshotSha256": "a" * 64,
            "adapterPolicy": "adapter-v1",
            "materialGameHighsAnalyzerVersion": "material-game-highs-v1",
            "cohortPolicy": "cohort-v1",
            "acceptedGames": 1,
            "analyzedGames": 1,
            "replayExcludedGames": 0,
            "trackedPlayers": 1,
        },
        "presetOrder": ["bughouse", "standard"],
        "directionOrder": ["won", "lost"],
        "players": [
            {
                "username": "alice",
                "displayName": "Alice",
                "analyzedGames": 1,
                "gamesByPreset": [
                    {
                        "won": [{
                            "url": "https://www.chess.com/game/live/111",
                            "endTime": 1_700_000_000,
                            "color": "white",
                            "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -",
                            "netMaterialX2": 6,
                        }],
                        "lost": [{
                            "url": "https://www.chess.com/game/live/222",
                            "endTime": 1_600_000_000,
                            "color": "black",
                            "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -",
                            "netMaterialX2": -5,
                        }],
                    },
                    {
                        "won": [{
                            "url": "https://www.chess.com/game/live/111",
                            "endTime": 1_700_000_000,
                            "color": "white",
                            "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -",
                            "netMaterialX2": 8,
                        }],
                        "lost": [{
                            "url": "https://www.chess.com/game/live/222",
                            "endTime": 1_600_000_000,
                            "color": "black",
                            "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -",
                            "netMaterialX2": -8,
                        }],
                    },
                ],
            }
        ],
    }
    assert "internal-win" not in output.read_text()
    assert "hash-win" not in output.read_text()
    assert output.read_bytes().endswith(b"\n")
    assert report.players == 1
    assert report.games == 4


def test_export_material_game_highs_cli_verifies_database_and_reports_projection(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-material-game-highs.json"
    _create_insights(database)
    database_sha256 = hashlib.sha256(database.read_bytes()).hexdigest()

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "export_material_game_highs.py"),
            str(database),
            str(output),
            "--database-sha256",
            database_sha256,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["dataset_version"] == "dataset-1"
    assert report["players"] == 1
    assert report["games"] == 4
    assert report["output"] == str(output.resolve())
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_export_material_game_highs_rejects_noncontiguous_ranks(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-material-game-highs.json"
    _create_insights(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE player_material_game_highs
            SET rank = 2
            WHERE preset = 'bughouse' AND direction = 'won'
            """
        )

    with pytest.raises(ValueError, match="ranks must be contiguous from one"):
        export_material_game_highs(database, output)

    assert not output.exists()


def test_repeated_material_game_high_exports_are_byte_identical(tmp_path):
    database = tmp_path / "insights.db"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _create_insights(database)

    first_report = export_material_game_highs(database, first)
    second_report = export_material_game_highs(database, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_report.output_sha256 == second_report.output_sha256


def test_export_king_height_insights_writes_only_distribution_and_public_game_links(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-king-height.json"
    _create_insights(database)

    report = export_king_height_insights(database, output)

    payload = json.loads(output.read_text())
    assert payload == {
        "schemaVersion": 1,
        "dataset": {
            "version": "dataset-1",
            "sourceSnapshotSha256": "a" * 64,
            "adapterPolicy": "adapter-v1",
            "kingHeightAnalyzerVersion": "king-height-v1",
            "cohortPolicy": "cohort-v1",
            "acceptedGames": 1,
            "analyzedGames": 1,
            "replayExcludedGames": 0,
            "trackedPlayers": 1,
        },
        "heightOrder": [1, 2, 3, 4, 5, 6, 7, 8],
        "players": [
            {
                "username": "alice",
                "displayName": "Alice",
                "analyzedGames": 1,
                "heights": [0, 0, 0, 0, 0, 0, 0, 1],
                "heightEightGames": [
                    {
                        "url": "https://www.chess.com/game/live/123456789",
                        "endTime": 1700000000,
                        "color": "white",
                    }
                ],
            }
        ],
    }
    assert "internal-game-id" not in output.read_text()
    assert output.read_bytes().endswith(b"\n")
    assert report.players == 1
    assert report.height_eight_games == 1


def test_export_drop_heatmaps_writes_fixed_order_integer_counts_only(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-drop-heatmaps.json"
    _create_insights(database)

    report = export_drop_heatmap_insights(database, output)

    payload = json.loads(output.read_text())
    assert payload["schemaVersion"] == 1
    assert payload["dataset"]["dropHeatmapAnalyzerVersion"] == "drop-heatmap-v1"
    assert payload["pieceOrder"] == ["pawn", "knight", "bishop", "rook", "queen"]
    assert payload["squareOrder"] == [
        f"{file_}{rank}" for rank in range(1, 9) for file_ in "abcdefgh"
    ]
    assert payload["players"] == [
        {
            "username": "alice",
            "displayName": "Alice",
            "analyzedGames": 1,
            "analyzedGamesByColor": [1, 1],
            "dropsByColor": [
                [
                    [0] * 64,
                    [0] * 44 + [3] + [0] * 19,
                    [0] * 64,
                    [0] * 64,
                    [0] * 64,
                ],
                [
                    [0] * 64,
                    [0] * 20 + [1] + [0] * 43,
                    [0] * 64,
                    [0] * 64,
                    [0] * 64,
                ],
            ],
        }
    ]
    assert output.read_bytes().endswith(b"\n")
    assert "internal-game-id" not in output.read_text()
    assert report.players == 1
    assert report.drop_events == 4


def test_export_drop_heatmap_cli_verifies_database_and_reports_projection(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-drop-heatmaps.json"
    _create_insights(database)
    database_sha256 = hashlib.sha256(database.read_bytes()).hexdigest()

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "export_drop_heatmap_insights.py"),
            str(database),
            str(output),
            "--database-sha256",
            database_sha256,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["dataset_version"] == "dataset-1"
    assert report["players"] == 1
    assert report["drop_events"] == 4
    assert report["output"] == str(output.resolve())
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_export_drop_heatmaps_rejects_incomplete_square_rows(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-drop-heatmaps.json"
    _create_insights(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            DELETE FROM player_drop_squares
            WHERE player_id = 1 AND piece_type = 'queen' AND square = 'h8'
            """
        )

    with pytest.raises(ValueError, match="exactly 640 color drop-square rows"):
        export_drop_heatmap_insights(database, output)

    assert not output.exists()


def test_repeated_drop_heatmap_exports_are_byte_identical(tmp_path):
    database = tmp_path / "insights.db"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _create_insights(database)

    first_report = export_drop_heatmap_insights(database, first)
    second_report = export_drop_heatmap_insights(database, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_report.output_sha256 == second_report.output_sha256


def test_export_king_height_cli_verifies_database_and_reports_projection(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-king-height.json"
    _create_insights(database)
    database_sha256 = hashlib.sha256(database.read_bytes()).hexdigest()

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "export_king_height_insights.py"),
            str(database),
            str(output),
            "--database-sha256",
            database_sha256,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["dataset_version"] == "dataset-1"
    assert report["players"] == 1
    assert report["height_eight_games"] == 1
    assert report["output"] == str(output.resolve())
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_export_king_height_rejects_incomplete_or_unreconciled_rows(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-king-height.json"
    _create_insights(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM player_king_height WHERE player_id = 1 AND height = 7"
        )

    with pytest.raises(ValueError, match="exactly eight king-height rows"):
        export_king_height_insights(database, output)

    assert not output.exists()


def test_repeated_king_height_exports_are_byte_identical(tmp_path):
    database = tmp_path / "insights.db"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _create_insights(database)

    first_report = export_king_height_insights(database, first)
    second_report = export_king_height_insights(database, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_report.output_sha256 == second_report.output_sha256


def test_export_material_insights_rejects_incomplete_piece_rows(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-material.json"
    _create_insights(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM player_material WHERE player_id = 1 AND piece_type = 'queen'"
        )

    with pytest.raises(ValueError, match="exactly five material rows"):
        export_material_insights(database, output)

    assert not output.exists()


def test_export_cli_verifies_the_database_and_reports_the_static_artifact(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-material.json"
    _create_insights(database)
    database_sha256 = hashlib.sha256(database.read_bytes()).hexdigest()

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "export_player_insights.py"),
            str(database),
            str(output),
            "--database-sha256",
            database_sha256,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["dataset_version"] == "dataset-1"
    assert report["players"] == 1
    assert report["output"] == str(output.resolve())
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_export_cli_can_atomically_replace_the_checked_frontend_artifact(tmp_path):
    database = tmp_path / "insights.db"
    output = tmp_path / "player-material.json"
    _create_insights(database)
    output.write_text("stale\n")

    subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "export_player_insights.py"),
            str(database),
            str(output),
            "--database-sha256",
            hashlib.sha256(database.read_bytes()).hexdigest(),
            "--replace",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(output.read_text())["dataset"]["version"] == "dataset-1"
