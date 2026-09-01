"""Export the material-insights SQLite artifact as compact static JSON."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


PIECE_ORDER = ("pawn", "knight", "bishop", "rook", "queen")
PRESET_ORDER = ("bughouse", "standard")
DIRECTION_ORDER = ("won", "lost")
PLAYER_COLOR_ORDER = ("white", "black")
SQUARE_ORDER = tuple(
    f"{file_}{rank}" for rank in range(1, 9) for file_ in "abcdefgh"
)


@dataclass(frozen=True)
class MaterialExportReport:
    dataset_version: str
    players: int
    output_bytes: int
    output_sha256: str


@dataclass(frozen=True)
class KingHeightExportReport:
    dataset_version: str
    players: int
    height_eight_games: int
    output_bytes: int
    output_sha256: str


@dataclass(frozen=True)
class DropHeatmapExportReport:
    dataset_version: str
    players: int
    drop_events: int
    output_bytes: int
    output_sha256: str


@dataclass(frozen=True)
class MaterialGameHighsExportReport:
    dataset_version: str
    players: int
    games: int
    output_bytes: int
    output_sha256: str


def export_material_insights(
    database_path: str | Path,
    output_path: str | Path,
    *,
    replace: bool = False,
) -> MaterialExportReport:
    """Write a deterministic browser-safe projection of one insight database."""
    database_path = Path(database_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists() and not replace:
        raise FileExistsError(output_path)

    source_uri = f"file:{database_path}?mode=ro&immutable=1"
    with sqlite3.connect(source_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        build = connection.execute("SELECT * FROM insight_builds").fetchone()
        if build is None:
            raise ValueError("insight database has no build record")
        players = connection.execute(
            """
            SELECT p.player_id, p.username, p.display_username,
                   g.eligible_games, g.analyzed_games,
                   g.replay_excluded_games
            FROM players AS p
            JOIN player_game_counts AS g USING (player_id)
            ORDER BY p.username
            """
        ).fetchall()
        material_rows = connection.execute(
            """
            SELECT player_id, piece_type, pieces_won, pieces_lost
            FROM player_material
            ORDER BY player_id, piece_type
            """
        ).fetchall()
        value_rows = connection.execute(
            """
            SELECT preset, piece_type, value_x2
            FROM material_piece_values
            """
        ).fetchall()

    material_by_player = {
        row["player_id"]: {
            piece_type: [0, 0]
            for piece_type in PIECE_ORDER
        }
        for row in players
    }
    if len(material_rows) != len(players) * len(PIECE_ORDER):
        raise ValueError("each player must have exactly five material rows")
    for row in material_rows:
        try:
            material_by_player[row["player_id"]][row["piece_type"]] = [
                row["pieces_won"],
                row["pieces_lost"],
            ]
        except KeyError as error:
            raise ValueError("unexpected player or piece row") from error

    piece_values = {
        preset: {piece_type: None for piece_type in PIECE_ORDER}
        for preset in PRESET_ORDER
    }
    for row in value_rows:
        try:
            piece_values[row["preset"]][row["piece_type"]] = row["value_x2"] / 2
        except KeyError as error:
            raise ValueError("unexpected material value row") from error
    if any(
        value is None
        for preset in PRESET_ORDER
        for value in piece_values[preset].values()
    ):
        raise ValueError("material value presets are incomplete")

    payload = {
        "schemaVersion": 1,
        "dataset": {
            "version": build["dataset_version"],
            "sourceSnapshotSha256": build["source_snapshot_sha256"],
            "adapterPolicy": build["adapter_policy_version"],
            "analyzerVersion": build["analyzer_version"],
            "cohortPolicy": build["cohort_policy"],
            "acceptedGames": build["accepted_games"],
            "analyzedGames": build["analyzed_games"],
            "replayExcludedGames": build["replay_excluded_games"],
            "trackedPlayers": build["tracked_players"],
        },
        "pieceOrder": list(PIECE_ORDER),
        "pieceValues": {
            preset: [piece_values[preset][piece_type] for piece_type in PIECE_ORDER]
            for preset in PRESET_ORDER
        },
        "players": [
            {
                "username": row["username"],
                "displayName": row["display_username"],
                "eligibleGames": row["eligible_games"],
                "analyzedGames": row["analyzed_games"],
                "replayExcludedGames": row["replay_excluded_games"],
                "pieces": [
                    material_by_player[row["player_id"]][piece_type]
                    for piece_type in PIECE_ORDER
                ],
            }
            for row in players
        ],
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        if replace:
            os.replace(temporary_path, output_path)
        else:
            os.link(temporary_path, output_path)
            temporary_path.unlink()
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return MaterialExportReport(
        dataset_version=build["dataset_version"],
        players=len(players),
        output_bytes=len(encoded),
        output_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def export_material_game_highs(
    database_path: str | Path,
    output_path: str | Path,
    *,
    replace: bool = False,
) -> MaterialGameHighsExportReport:
    """Write the deterministic browser projection for per-game material highs."""
    database_path = Path(database_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists() and not replace:
        raise FileExistsError(output_path)

    source_uri = f"file:{database_path}?mode=ro&immutable=1"
    with sqlite3.connect(source_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        build = connection.execute("SELECT * FROM insight_builds").fetchone()
        if build is None:
            raise ValueError("insight database has no build record")
        players = connection.execute(
            """
            SELECT p.player_id, p.username, p.display_username, g.analyzed_games
            FROM players AS p
            JOIN player_game_counts AS g USING (player_id)
            ORDER BY p.username
            """
        ).fetchall()
        high_rows = connection.execute(
            """
            SELECT player_id, preset, direction, rank, net_material_x2,
                   game_url, end_time, player_color, position_fen
            FROM player_material_game_highs
            ORDER BY player_id, preset, direction, rank
            """
        ).fetchall()

    player_ids = {row["player_id"] for row in players}
    games_by_player = {
        player_id: {
            preset: {direction: [] for direction in DIRECTION_ORDER}
            for preset in PRESET_ORDER
        }
        for player_id in player_ids
    }
    for row in high_rows:
        player_id = row["player_id"]
        preset = row["preset"]
        direction = row["direction"]
        net_material_x2 = row["net_material_x2"]
        url = row["game_url"]
        fen = row["position_fen"]
        if (
            player_id not in games_by_player
            or preset not in PRESET_ORDER
            or direction not in DIRECTION_ORDER
        ):
            raise ValueError("unexpected material game-high row")
        games = games_by_player[player_id][preset][direction]
        if row["rank"] != len(games) + 1 or len(games) >= 3:
            raise ValueError("material game-high ranks must be contiguous from one")
        if (
            (direction == "won" and net_material_x2 <= 0)
            or (direction == "lost" and net_material_x2 >= 0)
        ):
            raise ValueError("material game-high direction and score disagree")
        if not isinstance(url, str) or not url.startswith(
            "https://www.chess.com/game/"
        ):
            raise ValueError("material game highs require a public Chess.com URL")
        if (
            not isinstance(fen, str)
            or len(fen.split()) != 4
            or len(fen.split()[0].split("/")) != 8
        ):
            raise ValueError("material game highs require a four-field FEN")
        if row["player_color"] not in ("white", "black", "both"):
            raise ValueError("material game highs require a player color")
        games.append(
            {
                "url": url,
                "endTime": row["end_time"],
                "color": row["player_color"],
                "fen": fen,
                "netMaterialX2": net_material_x2,
            }
        )

    payload = {
        "schemaVersion": 1,
        "dataset": {
            "version": build["dataset_version"],
            "sourceSnapshotSha256": build["source_snapshot_sha256"],
            "adapterPolicy": build["adapter_policy_version"],
            "materialGameHighsAnalyzerVersion": build[
                "material_game_highs_analyzer_version"
            ],
            "cohortPolicy": build["cohort_policy"],
            "acceptedGames": build["accepted_games"],
            "analyzedGames": build["analyzed_games"],
            "replayExcludedGames": build["replay_excluded_games"],
            "trackedPlayers": build["tracked_players"],
        },
        "presetOrder": list(PRESET_ORDER),
        "directionOrder": list(DIRECTION_ORDER),
        "players": [
            {
                "username": row["username"],
                "displayName": row["display_username"],
                "analyzedGames": row["analyzed_games"],
                "gamesByPreset": [
                    {
                        direction: games_by_player[row["player_id"]][preset][
                            direction
                        ]
                        for direction in DIRECTION_ORDER
                    }
                    for preset in PRESET_ORDER
                ],
            }
            for row in players
        ],
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        if replace:
            os.replace(temporary_path, output_path)
        else:
            os.link(temporary_path, output_path)
            temporary_path.unlink()
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return MaterialGameHighsExportReport(
        dataset_version=build["dataset_version"],
        players=len(players),
        games=len(high_rows),
        output_bytes=len(encoded),
        output_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def export_king_height_insights(
    database_path: str | Path,
    output_path: str | Path,
    *,
    replace: bool = False,
) -> KingHeightExportReport:
    """Write the deterministic browser projection for average king height."""
    database_path = Path(database_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists() and not replace:
        raise FileExistsError(output_path)

    source_uri = f"file:{database_path}?mode=ro&immutable=1"
    with sqlite3.connect(source_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        build = connection.execute("SELECT * FROM insight_builds").fetchone()
        if build is None:
            raise ValueError("insight database has no build record")
        players = connection.execute(
            """
            SELECT p.player_id, p.username, p.display_username, g.analyzed_games
            FROM players AS p
            JOIN player_game_counts AS g USING (player_id)
            ORDER BY p.username
            """
        ).fetchall()
        height_rows = connection.execute(
            """
            SELECT player_id, height, games
            FROM player_king_height
            ORDER BY player_id, height
            """
        ).fetchall()
        height_eight_rows = connection.execute(
            """
            SELECT player_id, game_url, end_time, player_color
            FROM king_height_eight_games
            ORDER BY player_id, end_time DESC, game_url
            """
        ).fetchall()

    player_ids = {row["player_id"] for row in players}
    heights_by_player = {player_id: {} for player_id in player_ids}
    if len(height_rows) != len(players) * 8:
        raise ValueError("each player must have exactly eight king-height rows")
    for row in height_rows:
        player_id = row["player_id"]
        height = row["height"]
        games = row["games"]
        if player_id not in heights_by_player or height not in range(1, 9):
            raise ValueError("unexpected player or king-height row")
        if height in heights_by_player[player_id] or games < 0:
            raise ValueError("invalid duplicate or negative king-height row")
        heights_by_player[player_id][height] = games

    games_by_player = {player_id: [] for player_id in player_ids}
    for row in height_eight_rows:
        player_id = row["player_id"]
        url = row["game_url"]
        if player_id not in games_by_player:
            raise ValueError("unexpected player in height-eight games")
        if not isinstance(url, str) or not url.startswith(
            "https://www.chess.com/game/"
        ):
            raise ValueError("height-eight games require a public Chess.com URL")
        games_by_player[player_id].append(
            {
                "url": url,
                "endTime": row["end_time"],
                "color": row["player_color"],
            }
        )

    for row in players:
        counts = heights_by_player[row["player_id"]]
        if set(counts) != set(range(1, 9)):
            raise ValueError("each player must have heights one through eight")
        if sum(counts.values()) != row["analyzed_games"]:
            raise ValueError("king-height counts must sum to analyzed games")
        if len(games_by_player[row["player_id"]]) != counts[8]:
            raise ValueError("height-eight links must match the height-eight bucket")

    payload = {
        "schemaVersion": 1,
        "dataset": {
            "version": build["dataset_version"],
            "sourceSnapshotSha256": build["source_snapshot_sha256"],
            "adapterPolicy": build["adapter_policy_version"],
            "kingHeightAnalyzerVersion": build["king_height_analyzer_version"],
            "cohortPolicy": build["cohort_policy"],
            "acceptedGames": build["accepted_games"],
            "analyzedGames": build["analyzed_games"],
            "replayExcludedGames": build["replay_excluded_games"],
            "trackedPlayers": build["tracked_players"],
        },
        "heightOrder": list(range(1, 9)),
        "players": [
            {
                "username": row["username"],
                "displayName": row["display_username"],
                "analyzedGames": row["analyzed_games"],
                "heights": [
                    heights_by_player[row["player_id"]][height]
                    for height in range(1, 9)
                ],
                "heightEightGames": games_by_player[row["player_id"]],
            }
            for row in players
        ],
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        if replace:
            os.replace(temporary_path, output_path)
        else:
            os.link(temporary_path, output_path)
            temporary_path.unlink()
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return KingHeightExportReport(
        dataset_version=build["dataset_version"],
        players=len(players),
        height_eight_games=len(height_eight_rows),
        output_bytes=len(encoded),
        output_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def export_drop_heatmap_insights(
    database_path: str | Path,
    output_path: str | Path,
    *,
    replace: bool = False,
) -> DropHeatmapExportReport:
    """Write the deterministic browser projection for piece drop heat maps."""
    database_path = Path(database_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists() and not replace:
        raise FileExistsError(output_path)

    source_uri = f"file:{database_path}?mode=ro&immutable=1"
    with sqlite3.connect(source_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        build = connection.execute("SELECT * FROM insight_builds").fetchone()
        if build is None:
            raise ValueError("insight database has no build record")
        players = connection.execute(
            """
            SELECT p.player_id, p.username, p.display_username, g.analyzed_games
            FROM players AS p
            JOIN player_game_counts AS g USING (player_id)
            ORDER BY g.analyzed_games DESC, p.username
            """
        ).fetchall()
        drop_rows = connection.execute(
            """
            SELECT player_id, player_color, piece_type, square, drops
            FROM player_drop_squares
            ORDER BY player_id, player_color, piece_type, square
            """
        ).fetchall()
        color_count_rows = connection.execute(
            """
            SELECT player_id, player_color, eligible_games, analyzed_games,
                   replay_excluded_games
            FROM player_drop_color_game_counts
            ORDER BY player_id, player_color
            """
        ).fetchall()

    player_ids = {row["player_id"] for row in players}
    drops_by_player = {
        player_id: {
            player_color: {piece_type: {} for piece_type in PIECE_ORDER}
            for player_color in PLAYER_COLOR_ORDER
        }
        for player_id in player_ids
    }
    expected_rows = (
        len(players)
        * len(PLAYER_COLOR_ORDER)
        * len(PIECE_ORDER)
        * len(SQUARE_ORDER)
    )
    if len(drop_rows) != expected_rows:
        raise ValueError("each player must have exactly 640 color drop-square rows")
    for row in drop_rows:
        player_id = row["player_id"]
        player_color = row["player_color"]
        piece_type = row["piece_type"]
        square = row["square"]
        drops = row["drops"]
        if (
            player_id not in drops_by_player
            or player_color not in PLAYER_COLOR_ORDER
            or piece_type not in PIECE_ORDER
            or square not in SQUARE_ORDER
            or drops < 0
        ):
            raise ValueError("unexpected or invalid drop-square row")
        piece_squares = drops_by_player[player_id][player_color][piece_type]
        if square in piece_squares:
            raise ValueError("duplicate drop-square row")
        piece_squares[square] = drops

    expected_squares = set(SQUARE_ORDER)
    for colors in drops_by_player.values():
        for pieces in colors.values():
            if any(set(squares) != expected_squares for squares in pieces.values()):
                raise ValueError("each color and piece must have all 64 drop squares")

    analyzed_games_by_player = {
        player_id: {} for player_id in player_ids
    }
    if len(color_count_rows) != len(players) * len(PLAYER_COLOR_ORDER):
        raise ValueError("each player must have exactly two color game-count rows")
    for row in color_count_rows:
        player_id = row["player_id"]
        player_color = row["player_color"]
        if (
            player_id not in analyzed_games_by_player
            or player_color not in PLAYER_COLOR_ORDER
            or player_color in analyzed_games_by_player[player_id]
            or row["eligible_games"]
            != row["analyzed_games"] + row["replay_excluded_games"]
        ):
            raise ValueError("unexpected or unreconciled color game-count row")
        analyzed_games_by_player[player_id][player_color] = row["analyzed_games"]

    payload = {
        "schemaVersion": 1,
        "dataset": {
            "version": build["dataset_version"],
            "sourceSnapshotSha256": build["source_snapshot_sha256"],
            "adapterPolicy": build["adapter_policy_version"],
            "dropHeatmapAnalyzerVersion": build["drop_heatmap_analyzer_version"],
            "cohortPolicy": build["cohort_policy"],
            "acceptedGames": build["accepted_games"],
            "analyzedGames": build["analyzed_games"],
            "replayExcludedGames": build["replay_excluded_games"],
            "trackedPlayers": build["tracked_players"],
        },
        "pieceOrder": list(PIECE_ORDER),
        "squareOrder": list(SQUARE_ORDER),
        "players": [
            {
                "username": row["username"],
                "displayName": row["display_username"],
                "analyzedGames": row["analyzed_games"],
                "analyzedGamesByColor": [
                    analyzed_games_by_player[row["player_id"]][player_color]
                    for player_color in PLAYER_COLOR_ORDER
                ],
                "dropsByColor": [
                    [
                        [
                            drops_by_player[row["player_id"]][player_color]
                            [piece_type][square]
                            for square in SQUARE_ORDER
                        ]
                        for piece_type in PIECE_ORDER
                    ]
                    for player_color in PLAYER_COLOR_ORDER
                ],
            }
            for row in players
        ],
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        if replace:
            os.replace(temporary_path, output_path)
        else:
            os.link(temporary_path, output_path)
            temporary_path.unlink()
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return DropHeatmapExportReport(
        dataset_version=build["dataset_version"],
        players=len(players),
        drop_events=sum(row["drops"] for row in drop_rows),
        output_bytes=len(encoded),
        output_sha256=hashlib.sha256(encoded).hexdigest(),
    )
