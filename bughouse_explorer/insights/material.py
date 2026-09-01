"""Build lifetime capture-material insights from an immutable crawler snapshot."""

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Callable

from bughouse_explorer.engine import Board
from bughouse_explorer.opening.adapter import (
    ADAPTER_POLICY_VERSION,
    CrawlerSnapshotAdapter,
)
from bughouse_explorer.tcn import _PIECES, _T


MATERIAL_ANALYZER_VERSION = "player-material-v1"
KING_HEIGHT_ANALYZER_VERSION = "player-king-height-v1"
DROP_HEATMAP_ANALYZER_VERSION = "player-drop-heatmap-v1"
MATERIAL_GAME_HIGHS_ANALYZER_VERSION = "player-material-game-highs-v1"
ANALYZER_VERSION = MATERIAL_ANALYZER_VERSION
COHORT_POLICY = "permanent-tracking-v1"
PIECE_TYPES = ("pawn", "knight", "bishop", "rook", "queen")
PLAYER_COLORS = ("white", "black")
PIECE_NAMES = {
    "p": "pawn",
    "n": "knight",
    "b": "bishop",
    "r": "rook",
    "q": "queen",
}
PIECE_VALUES_X2 = {
    "bughouse": {"pawn": 3, "knight": 6, "bishop": 6, "rook": 8, "queen": 14},
    "standard": {"pawn": 2, "knight": 6, "bishop": 6, "rook": 10, "queen": 18},
}
SQUARES = tuple(f"{file_}{rank}" for rank in range(1, 9) for file_ in "abcdefgh")
_TCN_INDEX = {}
for _index, _character in enumerate(_T):
    _TCN_INDEX.setdefault(_character, _index)
_FILES = "abcdefgh"


@dataclass(frozen=True)
class MaterialBuildReport:
    dataset_version: str
    schema_version: int
    adapter_policy_version: str
    material_analyzer_version: str
    king_height_analyzer_version: str
    drop_heatmap_analyzer_version: str
    material_game_highs_analyzer_version: str
    cohort_policy: str
    accepted_games: int
    analyzed_games: int
    replay_excluded_games: int
    tracked_players: int
    accepted_plies: int
    analyzed_plies: int
    adapter_skips: dict[str, int]


class MaterialReplayError(ValueError):
    """A counted game-level replay failure with a stable diagnostic code."""

    def __init__(self, reason: str, ply_index: int, move_token: str):
        super().__init__(reason)
        self.reason = reason
        self.ply_index = ply_index
        self.move_token = move_token


@dataclass(frozen=True)
class _MaterialGameHigh:
    net_material_x2: int
    game_uuid: str
    content_hash: str
    game_url: str
    end_time: int | None
    player_color: str
    position_fen: str


@dataclass
class _PlayerAggregate:
    eligible_games: int = 0
    analyzed_games: int = 0
    replay_excluded_games: int = 0
    won: Counter | None = None
    lost: Counter | None = None
    king_heights: Counter | None = None
    drop_squares: Counter | None = None
    drop_eligible_games: Counter | None = None
    drop_analyzed_games: Counter | None = None
    drop_replay_excluded_games: Counter | None = None
    material_game_highs: dict | None = None

    def __post_init__(self):
        self.won = Counter() if self.won is None else self.won
        self.lost = Counter() if self.lost is None else self.lost
        self.king_heights = Counter() if self.king_heights is None else self.king_heights
        self.drop_squares = Counter() if self.drop_squares is None else self.drop_squares
        self.drop_eligible_games = (
            Counter() if self.drop_eligible_games is None else self.drop_eligible_games
        )
        self.drop_analyzed_games = (
            Counter() if self.drop_analyzed_games is None else self.drop_analyzed_games
        )
        self.drop_replay_excluded_games = (
            Counter()
            if self.drop_replay_excluded_games is None
            else self.drop_replay_excluded_games
        )
        self.material_game_highs = (
            {} if self.material_game_highs is None else self.material_game_highs
        )


def _captured_square(board: Board, move: dict) -> str | None:
    if "drop" in move:
        return None
    source = move["from"]
    target = move["to"]
    piece = board.board[source]
    if target in board.board:
        return target
    if piece in "Pp" and source[0] != target[0] and target == board.ep:
        return target[0] + source[1]
    return None


def _square(index: int) -> str:
    return _FILES[index % 8] + str(index // 8 + 1)


def _decode_token(token: str) -> dict:
    if len(token) != 2:
        raise ValueError("TCN move token must contain exactly two characters")
    source_index = _TCN_INDEX[token[0]]
    target_index = _TCN_INDEX[token[1]]
    move = {}

    if target_index > 63:
        move["promotion"] = _PIECES[(target_index - 64) // 3]
        target_index = (
            source_index
            + (-8 if source_index < 16 else 8)
            + ((target_index - 64) % 3)
            - 1
        )

    if source_index > 75:
        move["drop"] = _PIECES[source_index - 79]
    else:
        move["from"] = _square(source_index)
    move["to"] = _square(target_index)
    return move


def _analyze_game(move_tokens: tuple[str, ...]):
    board = Board()
    promoted = set()
    captures = (Counter(), Counter())
    king_heights = [1, 1]
    drop_squares = (Counter(), Counter())

    for ply_index, token in enumerate(move_tokens):
        move = _decode_token(token)
        side = 0 if board.white_to_move else 1
        if "drop" in move:
            if move["to"] in board.board:
                raise MaterialReplayError("occupied_drop", ply_index, token)
            drop_squares[side][(PIECE_NAMES[move["drop"]], move["to"])] += 1
            promoted.discard(move["to"])
            board.apply(move)
            continue

        source = move["from"]
        target = move["to"]
        if source not in board.board:
            raise MaterialReplayError(
                "missing_source_piece", ply_index, token
            )
        if board.board[source].isupper() != board.white_to_move:
            raise MaterialReplayError("wrong_side_piece", ply_index, token)
        moving_was_promoted = source in promoted
        moving_piece = board.board[source]
        capture_square = _captured_square(board, move)
        if capture_square is not None:
            captured_board_symbol = board.board[capture_square]
            if captured_board_symbol.isupper() == board.white_to_move:
                raise MaterialReplayError("self_capture", ply_index, token)
            captured_symbol = captured_board_symbol.lower()
            captured_piece = "p" if capture_square in promoted else captured_symbol
            captures[side][PIECE_NAMES[captured_piece]] += 1

        promoted.discard(source)
        if capture_square is not None:
            promoted.discard(capture_square)
        if "promotion" in move or moving_was_promoted:
            promoted.add(target)
        if moving_piece == "K":
            king_heights[0] = max(king_heights[0], int(target[1]))
        elif moving_piece == "k":
            king_heights[1] = max(king_heights[1], 9 - int(target[1]))
        board.apply(move)

    return captures, tuple(king_heights), drop_squares, board.position_key()


def _material_score_x2(captures: Counter, preset: str) -> int:
    values = PIECE_VALUES_X2[preset]
    return sum(captures[piece_type] * values[piece_type] for piece_type in PIECE_TYPES)


def _material_game_high_order(candidate: _MaterialGameHigh, direction: str):
    score_order = (
        -candidate.net_material_x2
        if direction == "won"
        else candidate.net_material_x2
    )
    end_time_order = (
        (1, 0) if candidate.end_time is None else (0, -candidate.end_time)
    )
    return (score_order, *end_time_order, candidate.game_uuid)


def _retain_material_game_high(
    aggregate: _PlayerAggregate,
    preset: str,
    direction: str,
    candidate: _MaterialGameHigh,
) -> None:
    highs = aggregate.material_game_highs.setdefault((preset, direction), [])
    highs.append(candidate)
    highs.sort(key=lambda item: _material_game_high_order(item, direction))
    del highs[3:]


def _create_schema(connection: sqlite3.Connection) -> None:
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
            player_id INTEGER PRIMARY KEY REFERENCES players(player_id),
            eligible_games INTEGER NOT NULL,
            analyzed_games INTEGER NOT NULL,
            replay_excluded_games INTEGER NOT NULL
        );
        CREATE TABLE player_material (
            player_id INTEGER NOT NULL REFERENCES players(player_id),
            piece_type TEXT NOT NULL CHECK (
                piece_type IN ('pawn', 'knight', 'bishop', 'rook', 'queen')
            ),
            pieces_won INTEGER NOT NULL,
            pieces_lost INTEGER NOT NULL,
            PRIMARY KEY (player_id, piece_type)
        ) WITHOUT ROWID;
        CREATE TABLE player_material_game_highs (
            player_id INTEGER NOT NULL REFERENCES players(player_id),
            preset TEXT NOT NULL CHECK (preset IN ('bughouse', 'standard')),
            direction TEXT NOT NULL CHECK (direction IN ('won', 'lost')),
            rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 3),
            net_material_x2 INTEGER NOT NULL CHECK (
                (direction = 'won' AND net_material_x2 > 0)
                OR (direction = 'lost' AND net_material_x2 < 0)
            ),
            game_uuid TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            game_url TEXT NOT NULL CHECK (
                game_url LIKE 'https://www.chess.com/game/%'
            ),
            end_time INTEGER,
            player_color TEXT NOT NULL CHECK (
                player_color IN ('white', 'black', 'both')
            ),
            position_fen TEXT NOT NULL,
            PRIMARY KEY (player_id, preset, direction, rank),
            UNIQUE (player_id, preset, direction, game_uuid)
        ) WITHOUT ROWID;
        CREATE TABLE player_king_height (
            player_id INTEGER NOT NULL REFERENCES players(player_id),
            height INTEGER NOT NULL CHECK (height BETWEEN 1 AND 8),
            games INTEGER NOT NULL CHECK (games >= 0),
            PRIMARY KEY (player_id, height)
        ) WITHOUT ROWID;
        CREATE TABLE player_drop_color_game_counts (
            player_id INTEGER NOT NULL REFERENCES players(player_id),
            player_color TEXT NOT NULL CHECK (
                player_color IN ('white', 'black')
            ),
            eligible_games INTEGER NOT NULL CHECK (eligible_games >= 0),
            analyzed_games INTEGER NOT NULL CHECK (analyzed_games >= 0),
            replay_excluded_games INTEGER NOT NULL CHECK (
                replay_excluded_games >= 0
            ),
            PRIMARY KEY (player_id, player_color)
        ) WITHOUT ROWID;
        CREATE TABLE player_drop_squares (
            player_id INTEGER NOT NULL REFERENCES players(player_id),
            player_color TEXT NOT NULL CHECK (
                player_color IN ('white', 'black')
            ),
            piece_type TEXT NOT NULL CHECK (
                piece_type IN ('pawn', 'knight', 'bishop', 'rook', 'queen')
            ),
            square TEXT NOT NULL CHECK (
                length(square) = 2
                AND substr(square, 1, 1) BETWEEN 'a' AND 'h'
                AND substr(square, 2, 1) BETWEEN '1' AND '8'
            ),
            drops INTEGER NOT NULL CHECK (drops >= 0),
            PRIMARY KEY (player_id, player_color, piece_type, square)
        ) WITHOUT ROWID;
        CREATE TABLE king_height_eight_games (
            player_id INTEGER NOT NULL REFERENCES players(player_id),
            game_uuid TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            game_url TEXT,
            end_time INTEGER,
            player_color TEXT NOT NULL CHECK (
                player_color IN ('white', 'black', 'both')
            ),
            PRIMARY KEY (player_id, game_uuid)
        ) WITHOUT ROWID;
        CREATE TABLE material_anomalies (
            game_uuid TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            reason TEXT NOT NULL,
            ply_index INTEGER,
            move_token TEXT
        );
        CREATE TABLE adapter_skips (
            reason TEXT PRIMARY KEY,
            games INTEGER NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE material_piece_values (
            preset TEXT NOT NULL CHECK (preset IN ('bughouse', 'standard')),
            piece_type TEXT NOT NULL CHECK (
                piece_type IN ('pawn', 'knight', 'bishop', 'rook', 'queen')
            ),
            value_x2 INTEGER NOT NULL,
            PRIMARY KEY (preset, piece_type)
        ) WITHOUT ROWID;
        CREATE VIEW player_material_scores AS
        SELECT
            p.player_id,
            p.username,
            p.display_username,
            v.preset,
            g.eligible_games,
            g.analyzed_games,
            g.replay_excluded_games,
            sum(m.pieces_won * v.value_x2) / 2.0 AS material_won,
            sum(m.pieces_lost * v.value_x2) / 2.0 AS material_lost,
            sum((m.pieces_won - m.pieces_lost) * v.value_x2) / 2.0
                AS net_material,
            (sum(m.pieces_won * v.value_x2) / 2.0)
                / NULLIF(g.analyzed_games, 0) AS average_material_won_per_game,
            (sum(m.pieces_lost * v.value_x2) / 2.0)
                / NULLIF(g.analyzed_games, 0) AS average_material_lost_per_game
        FROM players AS p
        JOIN player_game_counts AS g USING (player_id)
        JOIN player_material AS m USING (player_id)
        JOIN material_piece_values AS v USING (piece_type)
        GROUP BY p.player_id, v.preset;
        CREATE VIEW player_king_height_scores AS
        SELECT
            p.player_id,
            p.username,
            p.display_username,
            g.eligible_games,
            g.analyzed_games,
            g.replay_excluded_games,
            sum(h.height * h.games) AS weighted_height_sum,
            1.0 * sum(h.height * h.games)
                / NULLIF(g.analyzed_games, 0) AS average_king_height
        FROM players AS p
        JOIN player_game_counts AS g USING (player_id)
        JOIN player_king_height AS h USING (player_id)
        GROUP BY p.player_id;
        CREATE VIEW player_drop_heatmaps AS
        SELECT
            p.player_id,
            p.username,
            p.display_username,
            d.player_color,
            c.eligible_games,
            c.analyzed_games,
            c.replay_excluded_games,
            d.piece_type,
            d.square,
            d.drops,
            sum(d.drops) OVER (
                PARTITION BY d.player_id, d.player_color, d.piece_type
            ) AS piece_drops,
            1.0 * d.drops / NULLIF(
                sum(d.drops) OVER (
                    PARTITION BY d.player_id, d.player_color, d.piece_type
                ),
                0
            )
                AS drop_proportion
        FROM players AS p
        JOIN player_drop_color_game_counts AS c USING (player_id)
        JOIN player_drop_squares AS d USING (player_id)
        WHERE c.player_color = d.player_color;
        CREATE VIEW player_drop_heatmaps_combined AS
        SELECT
            p.player_id,
            p.username,
            p.display_username,
            g.analyzed_games,
            white.piece_type,
            white.square,
            white.drops + black.drops AS drops,
            sum(white.drops + black.drops) OVER (
                PARTITION BY white.player_id, white.piece_type
            ) AS piece_drops,
            1.0 * (white.drops + black.drops) / NULLIF(
                sum(white.drops + black.drops) OVER (
                    PARTITION BY white.player_id, white.piece_type
                ),
                0
            ) AS drop_proportion
        FROM players AS p
        JOIN player_game_counts AS g USING (player_id)
        JOIN player_drop_squares AS white
            ON white.player_id = p.player_id
            AND white.player_color = 'white'
        JOIN player_drop_squares AS black
            ON black.player_id = white.player_id
            AND black.player_color = 'black'
            AND black.piece_type = white.piece_type
            AND substr(black.square, 1, 1) = substr(white.square, 1, 1)
            AND CAST(substr(black.square, 2, 1) AS INTEGER)
                = 9 - CAST(substr(white.square, 2, 1) AS INTEGER);
        """
    )


def _dataset_version(snapshot_sha256: str) -> str:
    identity = json.dumps(
        {
            "adapter_policy_version": ADAPTER_POLICY_VERSION,
            "material_analyzer_version": MATERIAL_ANALYZER_VERSION,
            "king_height_analyzer_version": KING_HEIGHT_ANALYZER_VERSION,
            "drop_heatmap_analyzer_version": DROP_HEATMAP_ANALYZER_VERSION,
            "material_game_highs_analyzer_version": (
                MATERIAL_GAME_HIGHS_ANALYZER_VERSION
            ),
            "cohort_policy": COHORT_POLICY,
            "source_snapshot_sha256": snapshot_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(identity).hexdigest()[:40]


def build_material_insights(
    snapshot_path: str | Path,
    output_path: str | Path,
    *,
    snapshot_sha256: str,
    progress: Callable[[dict], None] | None = None,
    progress_interval: int = 100_000,
) -> MaterialBuildReport:
    """Build a new SQLite insight artifact; an existing output is never replaced."""
    snapshot_path = Path(snapshot_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError(output_path)
    snapshot_sha256 = snapshot_sha256.casefold()
    if len(snapshot_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in snapshot_sha256
    ):
        raise ValueError("snapshot_sha256 must contain 64 hexadecimal characters")
    dataset_version = _dataset_version(snapshot_sha256)

    source_uri = f"file:{snapshot_path}?mode=ro&immutable=1"
    with sqlite3.connect(source_uri, uri=True) as source:
        source.row_factory = sqlite3.Row
        tracked_rows = source.execute(
            """
            SELECT id, username, display_username, tracking_started_at, state
            FROM players
            WHERE tracking_started_at IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

    player_by_username = {row["username"]: row for row in tracked_rows}
    aggregates = {row["id"]: _PlayerAggregate() for row in tracked_rows}
    accepted_games = 0
    analyzed_games = 0
    replay_excluded_games = 0
    accepted_plies = 0
    analyzed_plies = 0
    anomalies = []
    height_eight_games = []
    adapter_skips = Counter()

    for outcome in CrawlerSnapshotAdapter(snapshot_path).iter_outcomes():
        game = outcome.game
        if game is None:
            adapter_skips[outcome.skip_reason or "unknown"] += 1
            continue
        accepted_games += 1
        accepted_plies += len(game.move_tokens)
        seats = (
            player_by_username.get(game.white_username),
            player_by_username.get(game.black_username),
        )
        tracked_ids = {row["id"] for row in seats if row is not None}
        for player_id in tracked_ids:
            aggregates[player_id].eligible_games += 1
        for side, row in enumerate(seats):
            if row is not None:
                aggregates[row["id"]].drop_eligible_games[PLAYER_COLORS[side]] += 1

        try:
            if "undefined" in "".join(game.move_tokens).casefold():
                anomalies.append(
                    (
                        game.uuid,
                        game.content_hash,
                        "undefined_tcn_fragment",
                        None,
                        None,
                    )
                )
                raise ValueError("counted_material_anomaly")
            captures, king_heights, drop_squares, position_fen = _analyze_game(
                game.move_tokens
            )
        except MaterialReplayError as error:
            replay_excluded_games += 1
            for player_id in tracked_ids:
                aggregates[player_id].replay_excluded_games += 1
            for side, row in enumerate(seats):
                if row is not None:
                    aggregates[row["id"]].drop_replay_excluded_games[
                        PLAYER_COLORS[side]
                    ] += 1
            anomalies.append(
                (
                    game.uuid,
                    game.content_hash,
                    error.reason,
                    error.ply_index,
                    error.move_token,
                )
            )
            continue
        except (IndexError, KeyError, ValueError) as error:
            replay_excluded_games += 1
            for player_id in tracked_ids:
                aggregates[player_id].replay_excluded_games += 1
            for side, row in enumerate(seats):
                if row is not None:
                    aggregates[row["id"]].drop_replay_excluded_games[
                        PLAYER_COLORS[side]
                    ] += 1
            if str(error) != "counted_material_anomaly":
                anomalies.append(
                    (game.uuid, game.content_hash, "replay_error", None, None)
                )
            continue

        analyzed_games += 1
        analyzed_plies += len(game.move_tokens)
        for player_id in tracked_ids:
            aggregates[player_id].analyzed_games += 1
        for side, row in enumerate(seats):
            if row is None:
                continue
            aggregate = aggregates[row["id"]]
            aggregate.won.update(captures[side])
            aggregate.lost.update(captures[1 - side])
            player_color = PLAYER_COLORS[side]
            aggregate.drop_analyzed_games[player_color] += 1
            aggregate.drop_squares.update(
                {
                    (player_color, piece_type, square): count
                    for (piece_type, square), count in drop_squares[side].items()
                }
            )
        won_by_player = {}
        lost_by_player = {}
        colors_by_player = {}
        for side, row in enumerate(seats):
            if row is None:
                continue
            player_id = row["id"]
            won_by_player.setdefault(player_id, Counter()).update(captures[side])
            lost_by_player.setdefault(player_id, Counter()).update(captures[1 - side])
            colors_by_player.setdefault(player_id, []).append(PLAYER_COLORS[side])
        if isinstance(game.url, str) and game.url.startswith(
            "https://www.chess.com/game/"
        ):
            for player_id, won in won_by_player.items():
                lost = lost_by_player[player_id]
                colors = colors_by_player[player_id]
                player_color = colors[0] if len(colors) == 1 else "both"
                for preset in PIECE_VALUES_X2:
                    net_material_x2 = (
                        _material_score_x2(won, preset)
                        - _material_score_x2(lost, preset)
                    )
                    if net_material_x2 == 0:
                        continue
                    direction = "won" if net_material_x2 > 0 else "lost"
                    _retain_material_game_high(
                        aggregates[player_id],
                        preset,
                        direction,
                        _MaterialGameHigh(
                            net_material_x2=net_material_x2,
                            game_uuid=game.uuid,
                            content_hash=game.content_hash,
                            game_url=game.url,
                            end_time=game.end_time,
                            player_color=player_color,
                            position_fen=position_fen,
                        ),
                    )
        heights_by_player = {}
        height_eight_colors = {}
        for side, row in enumerate(seats):
            if row is not None:
                heights_by_player[row["id"]] = max(
                    heights_by_player.get(row["id"], 1),
                    king_heights[side],
                )
                if king_heights[side] == 8:
                    height_eight_colors.setdefault(row["id"], []).append(side)
        for player_id, height in heights_by_player.items():
            aggregates[player_id].king_heights[height] += 1
            if height == 8:
                colors = height_eight_colors[player_id]
                player_color = (
                    "both" if len(colors) > 1
                    else "white" if colors[0] == 0
                    else "black"
                )
                height_eight_games.append(
                    (
                        player_id,
                        game.uuid,
                        game.content_hash,
                        game.url,
                        game.end_time,
                        player_color,
                    )
                )
        if progress is not None and accepted_games % progress_interval == 0:
            progress(
                {
                    "accepted_games": accepted_games,
                    "accepted_plies": accepted_plies,
                    "analyzed_games": analyzed_games,
                    "replay_excluded_games": replay_excluded_games,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output_path) as output:
        output.execute("PRAGMA foreign_keys=ON")
        _create_schema(output)
        output.execute(
            """
            INSERT INTO insight_builds (
                dataset_version, schema_version, source_snapshot_sha256,
                adapter_policy_version, analyzer_version,
                king_height_analyzer_version, drop_heatmap_analyzer_version,
                material_game_highs_analyzer_version,
                cohort_policy, accepted_games, analyzed_games,
                replay_excluded_games, tracked_players, accepted_plies,
                analyzed_plies
            ) VALUES (?, 4, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_version,
                snapshot_sha256,
                ADAPTER_POLICY_VERSION,
                MATERIAL_ANALYZER_VERSION,
                KING_HEIGHT_ANALYZER_VERSION,
                DROP_HEATMAP_ANALYZER_VERSION,
                MATERIAL_GAME_HIGHS_ANALYZER_VERSION,
                COHORT_POLICY,
                accepted_games,
                analyzed_games,
                replay_excluded_games,
                len(tracked_rows),
                accepted_plies,
                analyzed_plies,
            ),
        )
        output.executemany(
            "INSERT INTO players VALUES (?, ?, ?, ?, ?)",
            [
                (
                    row["id"],
                    row["username"],
                    row["display_username"],
                    row["tracking_started_at"],
                    row["state"],
                )
                for row in tracked_rows
            ],
        )
        output.executemany(
            "INSERT INTO player_game_counts VALUES (?, ?, ?, ?)",
            [
                (
                    player_id,
                    aggregate.eligible_games,
                    aggregate.analyzed_games,
                    aggregate.replay_excluded_games,
                )
                for player_id, aggregate in aggregates.items()
            ],
        )
        output.executemany(
            "INSERT INTO player_material VALUES (?, ?, ?, ?)",
            [
                (
                    player_id,
                    piece_type,
                    aggregate.won[piece_type],
                    aggregate.lost[piece_type],
                )
                for player_id, aggregate in aggregates.items()
                for piece_type in PIECE_TYPES
            ],
        )
        output.executemany(
            "INSERT INTO player_material_game_highs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    player_id,
                    preset,
                    direction,
                    rank,
                    candidate.net_material_x2,
                    candidate.game_uuid,
                    candidate.content_hash,
                    candidate.game_url,
                    candidate.end_time,
                    candidate.player_color,
                    candidate.position_fen,
                )
                for player_id, aggregate in aggregates.items()
                for preset in PIECE_VALUES_X2
                for direction in ("won", "lost")
                for rank, candidate in enumerate(
                    aggregate.material_game_highs.get((preset, direction), []),
                    start=1,
                )
            ],
        )
        output.executemany(
            "INSERT INTO material_anomalies VALUES (?, ?, ?, ?, ?)",
            anomalies,
        )
        output.executemany(
            "INSERT INTO player_king_height VALUES (?, ?, ?)",
            [
                (player_id, height, aggregate.king_heights[height])
                for player_id, aggregate in aggregates.items()
                for height in range(1, 9)
            ],
        )
        output.executemany(
            "INSERT INTO player_drop_color_game_counts VALUES (?, ?, ?, ?, ?)",
            [
                (
                    player_id,
                    player_color,
                    aggregate.drop_eligible_games[player_color],
                    aggregate.drop_analyzed_games[player_color],
                    aggregate.drop_replay_excluded_games[player_color],
                )
                for player_id, aggregate in aggregates.items()
                for player_color in PLAYER_COLORS
            ],
        )
        output.executemany(
            "INSERT INTO player_drop_squares VALUES (?, ?, ?, ?, ?)",
            [
                (
                    player_id,
                    player_color,
                    piece_type,
                    square,
                    aggregate.drop_squares[(player_color, piece_type, square)],
                )
                for player_id, aggregate in aggregates.items()
                for player_color in PLAYER_COLORS
                for piece_type in PIECE_TYPES
                for square in SQUARES
            ],
        )
        output.executemany(
            "INSERT INTO king_height_eight_games VALUES (?, ?, ?, ?, ?, ?)",
            height_eight_games,
        )
        output.executemany(
            "INSERT INTO adapter_skips VALUES (?, ?)",
            sorted(adapter_skips.items()),
        )
        output.executemany(
            "INSERT INTO material_piece_values VALUES (?, ?, ?)",
            [
                (preset, piece_type, value_x2)
                for preset, values in PIECE_VALUES_X2.items()
                for piece_type, value_x2 in values.items()
            ],
        )
        output.commit()

    return MaterialBuildReport(
        dataset_version=dataset_version,
        schema_version=4,
        adapter_policy_version=ADAPTER_POLICY_VERSION,
        material_analyzer_version=MATERIAL_ANALYZER_VERSION,
        king_height_analyzer_version=KING_HEIGHT_ANALYZER_VERSION,
        drop_heatmap_analyzer_version=DROP_HEATMAP_ANALYZER_VERSION,
        material_game_highs_analyzer_version=MATERIAL_GAME_HIGHS_ANALYZER_VERSION,
        cohort_policy=COHORT_POLICY,
        accepted_games=accepted_games,
        analyzed_games=analyzed_games,
        replay_excluded_games=replay_excluded_games,
        tracked_players=len(tracked_rows),
        accepted_plies=accepted_plies,
        analyzed_plies=analyzed_plies,
        adapter_skips=dict(sorted(adapter_skips.items())),
    )
