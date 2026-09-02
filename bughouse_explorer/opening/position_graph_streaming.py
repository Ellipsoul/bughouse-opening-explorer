"""Bounded-memory full replay builder for packed position-graph artifacts."""

from collections import Counter
from dataclasses import dataclass
import hashlib
import heapq
import json
import mmap
from pathlib import Path
import sqlite3
import struct
import zlib

from bughouse_explorer.engine import Board, label
from bughouse_explorer.tcn import decode_tcn

from .adapter import ADAPTER_POLICY_VERSION, AdapterOutcome
from .packed import _file_hash
from .position_graph import identity_key, result_bucket
from .position_graph_packed import (
    EDGE,
    POSITION,
    STATE,
    UINT64,
    _metadata_payload,
    _state_context,
    _write_uint32s,
)


@dataclass(frozen=True)
class StreamingGraphBuildReport:
    build_id: str
    accepted_games: int
    skipped: dict[str, int]
    positions: int
    states: int
    edges: int
    memberships: int
    temporary_bytes: int
    final_bytes: int


@dataclass(frozen=True)
class SharedPositionDiscoveryReport:
    shared_positions_path: Path
    accepted_games: int
    skipped: dict[str, int]
    input_digest: str
    shared_positions: int
    temporary_bytes: int


class _Groups:
    """Merge-friendly grouped view over an id-ordered SQLite cursor."""

    def __init__(self, rows):
        self.rows = iter(rows)
        self.pending = next(self.rows, None)

    def take(self, record_id):
        values = []
        while self.pending is not None and self.pending[0] < record_id:
            raise ValueError("membership references a missing structural record")
        while self.pending is not None and self.pending[0] == record_id:
            values.append(tuple(self.pending[1:]))
            self.pending = next(self.rows, None)
        return values


SHARED_RECORD = struct.Struct(">20sI")
IDENTITY_BYTES = 20
REPLAY_SKIP_REASON = "position_replay_error"
GRAPH_REPLAY_POLICY_VERSION = "skip-unreplayable-source-game-v1"


class PositionReplayError(ValueError):
    """One source game cannot be deterministically converted into positions."""


class _SortedKeys:
    def __init__(self, path):
        path = Path(path)
        size = path.stat().st_size
        if size % IDENTITY_BYTES:
            raise ValueError("shared-position key file has a partial record")
        self.stream = path.open("rb")
        self.buffer = (
            mmap.mmap(self.stream.fileno(), 0, access=mmap.ACCESS_READ)
            if size
            else None
        )
        self.count = size // IDENTITY_BYTES

    def contains(self, key):
        if len(key) != IDENTITY_BYTES:
            raise ValueError("position identity has an unexpected width")
        left = 0
        right = self.count
        while left < right:
            middle = (left + right) // 2
            current = self.buffer[
                middle * IDENTITY_BYTES : (middle + 1) * IDENTITY_BYTES
            ]
            if current < key:
                left = middle + 1
            else:
                right = middle
        return left < self.count and self.buffer[
            left * IDENTITY_BYTES : (left + 1) * IDENTITY_BYTES
        ] == key

    def close(self):
        if self.buffer is not None:
            self.buffer.close()
        self.stream.close()


def discover_shared_positions(
    outcomes,
    directory,
    *,
    source_fingerprint: str,
    chunk_bytes=64 * 1024 * 1024,
    progress_callback=None,
) -> SharedPositionDiscoveryReport:
    """External-sort distinct ``(placement, game)`` facts into shared keys."""
    directory = Path(directory)
    if chunk_bytes < 1:
        raise ValueError("chunk_bytes must be positive")
    if directory.exists():
        raise FileExistsError(directory)
    directory.mkdir(parents=True)
    records_per_chunk = max(1, chunk_bytes // SHARED_RECORD.size)
    buffer = []
    chunks = []
    accepted = 0
    skipped = Counter()
    digest = hashlib.blake2b(digest_size=20)
    digest.update(b"opening-position-graph-v1\0")
    digest.update(source_fingerprint.encode())

    def flush_chunk():
        if not buffer:
            return
        buffer.sort()
        path = directory / f"chunk-{len(chunks):06d}.bin"
        with path.open("wb") as stream:
            previous = None
            for record in buffer:
                if record != previous:
                    stream.write(record)
                    previous = record
        chunks.append(path)
        buffer.clear()

    for outcome in outcomes:
        if not isinstance(outcome, AdapterOutcome):
            raise TypeError("shared-position discovery requires AdapterOutcome records")
        if outcome.game is None:
            if not outcome.skip_reason:
                raise ValueError("excluded adapter outcome requires a skip reason")
            skipped[outcome.skip_reason] += 1
            continue
        game = outcome.game
        try:
            seen = _discover_position_keys(game)
        except PositionReplayError:
            skipped[REPLAY_SKIP_REASON] += 1
            continue
        ordinal = accepted
        if ordinal >= 2**32:
            raise OverflowError("packed graph supports fewer than 2^32 games")
        accepted += 1
        for value in (game.uuid, "".join(game.move_tokens), game.content_hash):
            digest.update(b"\0")
            digest.update(value.encode())
        buffer.extend(SHARED_RECORD.pack(key, ordinal) for key in seen)
        if len(buffer) >= records_per_chunk:
            flush_chunk()
        if progress_callback is not None and accepted % 10_000 == 0:
            progress_callback(accepted)
    flush_chunk()
    if not accepted:
        raise ValueError("shared-position discovery requires an accepted game")

    streams = [path.open("rb") for path in chunks]
    heap = []
    for index, stream in enumerate(streams):
        record = stream.read(SHARED_RECORD.size)
        if record:
            heapq.heappush(heap, (record, index))
    shared_path = directory / "shared-position-keys.bin"
    shared_positions = 0
    with shared_path.open("wb") as shared_stream:
        active_key = None
        active_count = 0
        while heap:
            record, index = heapq.heappop(heap)
            key = record[:IDENTITY_BYTES]
            if key != active_key:
                if active_key is not None and active_count >= 2:
                    shared_stream.write(active_key)
                    shared_positions += 1
                active_key = key
                active_count = 1
            else:
                active_count += 1
            following = streams[index].read(SHARED_RECORD.size)
            if following:
                heapq.heappush(heap, (following, index))
        if active_key is not None and active_count >= 2:
            shared_stream.write(active_key)
            shared_positions += 1
    for stream in streams:
        stream.close()
    for path in chunks:
        path.unlink()
    return SharedPositionDiscoveryReport(
        shared_positions_path=shared_path,
        accepted_games=accepted,
        skipped=dict(sorted(skipped.items())),
        input_digest=digest.hexdigest(),
        shared_positions=shared_positions,
        temporary_bytes=sum(path.stat().st_size for path in directory.iterdir()),
    )


def _edge_key(parent_state_key, move_token, child_state_key):
    return identity_key("edge", parent_state_key + move_token + child_state_key)


def _outcome_code(game):
    return {"win": 0, "draw": 1, "loss": 2}[result_bucket(game)]


def _discover_position_keys(game):
    """Replay only enough state for pass-one placement discovery."""
    board = Board()
    seen = {identity_key("position", board.placement())}
    try:
        decoded = decode_tcn("".join(game.move_tokens))
        if len(decoded) != len(game.move_tokens):
            raise ValueError("decoded move count changed")
        for move in decoded:
            board.apply(move)
            seen.add(identity_key("position", board.placement()))
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise PositionReplayError(
            f"cannot replay source game {game.uuid}: "
            f"{type(error).__name__}: {error}"
        ) from error
    return seen


def _replay_game(game):
    """Replay one source game or classify it as unusable graph input."""
    board = Board()
    root_placement = board.placement()
    root_fen = board.position_key()
    transitions = []
    try:
        decoded = decode_tcn("".join(game.move_tokens))
        if len(decoded) != len(game.move_tokens):
            raise ValueError("decoded move count changed")
        for move_token_text, move in zip(game.move_tokens, decoded, strict=True):
            move_token = move_token_text.encode("ascii")
            parent_fen = board.position_key()
            parent_state_key = identity_key("state", parent_fen)
            _move_id, move_label = label(board, move)
            board.apply(move)
            child_placement = board.placement()
            child_fen = board.position_key()
            child_position_key = identity_key("position", child_placement)
            child_state_key = identity_key("state", child_fen)
            transitions.append(
                (
                    child_position_key,
                    child_placement,
                    child_state_key,
                    child_fen,
                    _edge_key(parent_state_key, move_token, child_state_key),
                    parent_state_key,
                    move_token,
                    move_label,
                )
            )
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise PositionReplayError(
            f"cannot replay source game {game.uuid}: "
            f"{type(error).__name__}: {error}"
        ) from error
    return root_placement, root_fen, transitions, board.position_key()


def _counts(rows):
    counts = Counter(row[1] for row in rows)
    return counts[0], counts[1], counts[2]


def build_streaming_position_graph(
    outcomes,
    directory,
    *,
    source_fingerprint: str,
    temporary_directory,
    flush_memberships: int = 100_000,
    progress_callback=None,
    shared_positions_path=None,
    terminal_policy: str = "full-replay-game-end-v1",
    expected_accepted_games=None,
    expected_skipped=None,
    expected_input_digest=None,
) -> StreamingGraphBuildReport:
    """Replay every accepted game and emit a full, cycle-safe position graph.

    The staging database stores 160-bit identities and distinct-game facts.  It
    never stores a move-prefix trie. When ``shared_positions_path`` is supplied,
    replay remains complete but materialization ends one edge after the last
    placement reached by at least two games. ``temporary_directory`` is mandatory
    so large scratch capacity is explicit.
    """
    directory = Path(directory)
    temporary_directory = Path(temporary_directory)
    if directory.exists():
        raise FileExistsError(directory)
    if temporary_directory.exists():
        raise FileExistsError(temporary_directory)
    if flush_memberships < 1:
        raise ValueError("flush_memberships must be positive")
    expected_policy = (
        "last-shared-placement-plus-one-or-game-end-v1"
        if shared_positions_path is not None
        else "full-replay-game-end-v1"
    )
    if terminal_policy != expected_policy:
        raise ValueError("terminal policy does not match the materialization mode")
    directory.mkdir(parents=True)
    temporary_directory.mkdir(parents=True)
    shared_positions = (
        _SortedKeys(shared_positions_path)
        if shared_positions_path is not None
        else None
    )
    staging_path = temporary_directory / "opening-position-graph.sqlite3"
    connection = sqlite3.connect(staging_path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute("PRAGMA cache_size=-262144")
    connection.executescript(
        """
        CREATE TABLE positions(
            key BLOB PRIMARY KEY,
            placement TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE states(
            key BLOB PRIMARY KEY,
            position_key BLOB NOT NULL,
            fen TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE edges(
            key BLOB PRIMARY KEY,
            parent_state_key BLOB NOT NULL,
            move_token BLOB NOT NULL,
            child_state_key BLOB NOT NULL,
            move_label TEXT NOT NULL,
            UNIQUE(parent_state_key, move_token)
        ) WITHOUT ROWID;
        CREATE TABLE position_games(
            position_key BLOB NOT NULL,
            ordinal INTEGER NOT NULL,
            PRIMARY KEY(position_key, ordinal)
        ) WITHOUT ROWID;
        CREATE TABLE state_games(
            state_key BLOB NOT NULL,
            ordinal INTEGER NOT NULL,
            outcome INTEGER NOT NULL,
            PRIMARY KEY(state_key, ordinal)
        ) WITHOUT ROWID;
        CREATE TABLE edge_games(
            edge_key BLOB NOT NULL,
            ordinal INTEGER NOT NULL,
            outcome INTEGER NOT NULL,
            PRIMARY KEY(edge_key, ordinal)
        ) WITHOUT ROWID;
        CREATE TABLE endings(
            state_key BLOB NOT NULL,
            ordinal INTEGER NOT NULL,
            PRIMARY KEY(state_key, ordinal)
        ) WITHOUT ROWID;
        CREATE TABLE posting_entries(
            posting_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            PRIMARY KEY(posting_key, ordinal)
        ) WITHOUT ROWID;
        CREATE TABLE game_uuids(
            uuid TEXT PRIMARY KEY
        ) WITHOUT ROWID;
        CREATE TRIGGER position_hash_collision BEFORE INSERT ON positions
        WHEN EXISTS(
            SELECT 1 FROM positions
            WHERE key=NEW.key AND placement<>NEW.placement
        ) BEGIN
            SELECT RAISE(ABORT, 'position hash collision');
        END;
        CREATE TRIGGER state_hash_collision BEFORE INSERT ON states
        WHEN EXISTS(
            SELECT 1 FROM states
            WHERE key=NEW.key AND (position_key<>NEW.position_key OR fen<>NEW.fen)
        ) BEGIN
            SELECT RAISE(ABORT, 'state hash collision');
        END;
        CREATE TRIGGER edge_identity_collision BEFORE INSERT ON edges
        WHEN EXISTS(
            SELECT 1 FROM edges
            WHERE key=NEW.key AND (
                parent_state_key<>NEW.parent_state_key
                OR move_token<>NEW.move_token
                OR child_state_key<>NEW.child_state_key
                OR move_label<>NEW.move_label
            )
        ) BEGIN
            SELECT RAISE(ABORT, 'edge hash collision');
        END;
        CREATE TRIGGER edge_replay_conflict BEFORE INSERT ON edges
        WHEN EXISTS(
            SELECT 1 FROM edges
            WHERE parent_state_key=NEW.parent_state_key
              AND move_token=NEW.move_token
              AND (child_state_key<>NEW.child_state_key OR move_label<>NEW.move_label)
        ) BEGIN
            SELECT RAISE(ABORT, 'state and token map to multiple children');
        END;
        """
    )

    skipped = Counter()
    accepted = 0
    digest = hashlib.blake2b(digest_size=20)
    digest.update(b"opening-position-graph-v1\0")
    digest.update(source_fingerprint.encode())
    buffers = {
        "positions": [],
        "states": [],
        "edges": [],
        "position_games": [],
        "state_games": [],
        "edge_games": [],
        "endings": [],
        "posting_entries": [],
        "game_uuids": [],
    }

    def flush():
        with connection:
            connection.executemany(
                "INSERT OR IGNORE INTO positions VALUES (?, ?)", buffers["positions"]
            )
            connection.executemany(
                "INSERT OR IGNORE INTO states VALUES (?, ?, ?)", buffers["states"]
            )
            connection.executemany(
                "INSERT OR IGNORE INTO edges VALUES (?, ?, ?, ?, ?)", buffers["edges"]
            )
            connection.executemany(
                "INSERT OR IGNORE INTO position_games VALUES (?, ?)",
                buffers["position_games"],
            )
            connection.executemany(
                "INSERT OR IGNORE INTO state_games VALUES (?, ?, ?)",
                buffers["state_games"],
            )
            connection.executemany(
                "INSERT OR IGNORE INTO edge_games VALUES (?, ?, ?)",
                buffers["edge_games"],
            )
            connection.executemany(
                "INSERT OR IGNORE INTO endings VALUES (?, ?)", buffers["endings"]
            )
            connection.executemany(
                "INSERT OR IGNORE INTO posting_entries VALUES (?, ?)",
                buffers["posting_entries"],
            )
            # Duplicate UUIDs are a corpus error, not two games with shared support.
            connection.executemany(
                "INSERT INTO game_uuids VALUES (?)", buffers["game_uuids"]
            )
        for values in buffers.values():
            values.clear()

    offsets_path = directory / "game_offsets.bin"
    games_path = directory / "games.bin"
    try:
        with games_path.open("wb") as games_stream, offsets_path.open("wb") as offsets_stream:
            for outcome in outcomes:
                if not isinstance(outcome, AdapterOutcome):
                    raise TypeError("streaming graph writer requires AdapterOutcome records")
                if outcome.game is None:
                    if not outcome.skip_reason:
                        raise ValueError("excluded adapter outcome requires a skip reason")
                    skipped[outcome.skip_reason] += 1
                    continue
                game = outcome.game
                try:
                    root_placement, root_fen, transitions, final_fen = _replay_game(
                        game
                    )
                except PositionReplayError:
                    skipped[REPLAY_SKIP_REASON] += 1
                    continue
                ordinal = accepted
                if ordinal >= 2**32:
                    raise OverflowError("packed graph supports fewer than 2^32 games")
                accepted += 1
                buffers["game_uuids"].append((game.uuid,))
                for value in (game.uuid, "".join(game.move_tokens), game.content_hash):
                    digest.update(b"\0")
                    digest.update(value.encode())
                offsets_stream.write(UINT64.pack(games_stream.tell()))
                games_stream.write(
                    zlib.compress(
                        json.dumps(
                            _metadata_payload(game), separators=(",", ":"), sort_keys=True
                        ).encode(),
                        level=6,
                    )
                )
                buffers["posting_entries"].extend(
                    (
                        (f"white\0{game.white_username.casefold()}", ordinal),
                        (f"black\0{game.black_username.casefold()}", ordinal),
                    )
                )

                root_position_key = identity_key("position", root_placement)
                root_state_key = identity_key("state", root_fen)
                seen_positions = {root_position_key}
                seen_states = {root_state_key}
                seen_edges = set()
                buffers["positions"].append((root_position_key, root_placement))
                buffers["states"].append(
                    (root_state_key, root_position_key, root_fen)
                )
                last_shared_position_index = 0
                for index, transition in enumerate(transitions, 1):
                    child_position_key = transition[0]
                    if shared_positions is not None and shared_positions.contains(
                        child_position_key
                    ):
                        last_shared_position_index = index

                materialized_edges = len(transitions)
                if shared_positions is not None:
                    materialized_edges = min(
                        materialized_edges, last_shared_position_index + 1
                    )
                for (
                    child_position_key,
                    child_placement,
                    child_state_key,
                    child_fen,
                    edge_key,
                    parent_state_key,
                    move_token,
                    move_label,
                ) in transitions[:materialized_edges]:
                    buffers["positions"].append(
                        (child_position_key, child_placement)
                    )
                    buffers["states"].append(
                        (child_state_key, child_position_key, child_fen)
                    )
                    buffers["edges"].append(
                        (
                            edge_key,
                            parent_state_key,
                            move_token,
                            child_state_key,
                            move_label,
                        )
                    )
                    seen_positions.add(child_position_key)
                    seen_states.add(child_state_key)
                    seen_edges.add(edge_key)

                outcome_code = _outcome_code(game)
                buffers["position_games"].extend(
                    (key, ordinal) for key in seen_positions
                )
                buffers["state_games"].extend(
                    (key, ordinal, outcome_code) for key in seen_states
                )
                buffers["edge_games"].extend(
                    (key, ordinal, outcome_code) for key in seen_edges
                )
                if materialized_edges == len(transitions):
                    buffers["endings"].append(
                        (identity_key("state", final_fen), ordinal)
                    )
                if len(buffers["state_games"]) >= flush_memberships:
                    flush()
                if progress_callback is not None and accepted % 10_000 == 0:
                    progress_callback(accepted)
            if buffers["game_uuids"]:
                flush()
            if not accepted:
                raise ValueError("packed graph artifacts require at least one accepted game")
            offsets_stream.write(UINT64.pack(games_stream.tell()))

        observed_skipped = dict(sorted(skipped.items()))
        observed_input_digest = digest.hexdigest()
        if (
            expected_accepted_games is not None
            and accepted != expected_accepted_games
        ):
            raise ValueError("accepted game count changed between graph build passes")
        if expected_skipped is not None and observed_skipped != expected_skipped:
            raise ValueError("skipped game accounting changed between graph build passes")
        if (
            expected_input_digest is not None
            and observed_input_digest != expected_input_digest
        ):
            raise ValueError(
                "accepted game content or order changed between graph build passes"
            )

        connection.executescript(
            """
            CREATE TABLE position_ids(
                id INTEGER PRIMARY KEY,
                key BLOB NOT NULL UNIQUE
            );
            CREATE TABLE state_ids(
                id INTEGER PRIMARY KEY,
                key BLOB NOT NULL UNIQUE
            );
            CREATE TABLE edge_ids(
                id INTEGER PRIMARY KEY,
                key BLOB NOT NULL UNIQUE,
                parent_state_id INTEGER NOT NULL,
                child_state_id INTEGER NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO position_ids VALUES (?, ?)",
            enumerate(
                row[0] for row in connection.execute(
                    "SELECT key FROM positions ORDER BY key, placement"
                )
            ),
        )
        connection.executemany(
            "INSERT INTO state_ids VALUES (?, ?)",
            enumerate(
                row[0]
                for row in connection.execute("SELECT key FROM states ORDER BY key, fen")
            ),
        )
        edge_select = connection.execute(
            """
            SELECT e.key, parent.id, child.id
            FROM edges AS e
            JOIN state_ids AS parent ON parent.key=e.parent_state_key
            JOIN state_ids AS child ON child.key=e.child_state_key
            ORDER BY parent.id, e.move_token, child.id
            """
        )
        connection.executemany(
            "INSERT INTO edge_ids VALUES (?, ?, ?, ?)",
            ((index, *row) for index, row in enumerate(edge_select)),
        )
        connection.execute(
            "CREATE INDEX edge_ids_parent ON edge_ids(parent_state_id, id)"
        )
        connection.commit()

        positions_count = connection.execute(
            "SELECT COUNT(*) FROM position_ids"
        ).fetchone()[0]
        states_count = connection.execute("SELECT COUNT(*) FROM state_ids").fetchone()[0]
        edges_count = connection.execute("SELECT COUNT(*) FROM edge_ids").fetchone()[0]

        position_memberships = _Groups(
            connection.execute(
                """
                SELECT ids.id, facts.ordinal
                FROM position_games AS facts
                JOIN position_ids AS ids ON ids.key=facts.position_key
                ORDER BY ids.id, facts.ordinal
                """
            )
        )
        state_memberships = _Groups(
            connection.execute(
                """
                SELECT ids.id, facts.ordinal, facts.outcome
                FROM state_games AS facts
                JOIN state_ids AS ids ON ids.key=facts.state_key
                ORDER BY ids.id, facts.ordinal
                """
            )
        )
        ending_memberships = _Groups(
            connection.execute(
                """
                SELECT ids.id, facts.ordinal
                FROM endings AS facts
                JOIN state_ids AS ids ON ids.key=facts.state_key
                ORDER BY ids.id, facts.ordinal
                """
            )
        )
        edge_memberships = _Groups(
            connection.execute(
                """
                SELECT ids.id, facts.ordinal, facts.outcome
                FROM edge_games AS facts
                JOIN edge_ids AS ids ON ids.key=facts.edge_key
                ORDER BY ids.id, facts.ordinal
                """
            )
        )
        edge_ranges = _Groups(
            connection.execute(
                """
                SELECT parent_state_id, MIN(id), COUNT(*)
                FROM edge_ids
                GROUP BY parent_state_id
                ORDER BY parent_state_id
                """
            )
        )

        membership_cursor = 0
        strings_path = directory / "strings.bin"
        memberships_path = directory / "memberships.bin"
        with strings_path.open("wb") as strings, memberships_path.open(
            "wb"
        ) as memberships, (directory / "positions.bin").open(
            "wb"
        ) as positions_stream, (directory / "states.bin").open("wb") as states_stream:
            for position_id, placement in connection.execute(
                """
                SELECT ids.id, positions.placement
                FROM position_ids AS ids
                JOIN positions ON positions.key=ids.key
                ORDER BY ids.id
                """
            ):
                encoded = placement.encode("ascii")
                string_offset = strings.tell()
                strings.write(encoded)
                rows = position_memberships.take(position_id)
                ordinals = [row[0] for row in rows]
                posting_start = membership_cursor
                _write_uint32s(memberships, ordinals)
                membership_cursor += len(ordinals)
                positions_stream.write(
                    POSITION.pack(
                        string_offset, len(encoded), posting_start, len(ordinals)
                    )
                )

            for state_id, position_id, fen in connection.execute(
                """
                SELECT state_ids.id, position_ids.id, states.fen
                FROM state_ids
                JOIN states ON states.key=state_ids.key
                JOIN position_ids ON position_ids.key=states.position_key
                ORDER BY state_ids.id
                """
            ):
                state_rows = state_memberships.take(state_id)
                state_ordinals = [row[0] for row in state_rows]
                state_start = membership_cursor
                _write_uint32s(memberships, state_ordinals)
                membership_cursor += len(state_ordinals)
                ending_rows = ending_memberships.take(state_id)
                ending_ordinals = [row[0] for row in ending_rows]
                ending_start = membership_cursor
                _write_uint32s(memberships, ending_ordinals)
                membership_cursor += len(ending_ordinals)
                ranges = edge_ranges.take(state_id)
                if ranges:
                    edge_start, edge_count = ranges[0]
                else:
                    edge_start, edge_count = 0, 0
                states_stream.write(
                    STATE.pack(
                        position_id,
                        edge_start,
                        edge_count,
                        state_start,
                        len(state_ordinals),
                        ending_start,
                        len(ending_ordinals),
                        *_counts(state_rows),
                        *_state_context(fen),
                    )
                )

            with (directory / "edges.bin").open("wb") as edges_stream:
                for (
                    edge_id,
                    child_position_id,
                    child_state_id,
                    move_token,
                    move_label,
                ) in connection.execute(
                    """
                    SELECT edge_ids.id, child_state.position_key_id,
                           edge_ids.child_state_id, edges.move_token, edges.move_label
                    FROM edge_ids
                    JOIN edges ON edges.key=edge_ids.key
                    JOIN (
                        SELECT state_ids.id, position_ids.id AS position_key_id
                        FROM state_ids
                        JOIN states ON states.key=state_ids.key
                        JOIN position_ids ON position_ids.key=states.position_key
                    ) AS child_state ON child_state.id=edge_ids.child_state_id
                    ORDER BY edge_ids.id
                    """
                ):
                    label_bytes = move_label.encode("utf-8")
                    label_offset = strings.tell()
                    strings.write(label_bytes)
                    rows = edge_memberships.take(edge_id)
                    ordinals = [row[0] for row in rows]
                    posting_start = membership_cursor
                    _write_uint32s(memberships, ordinals)
                    membership_cursor += len(ordinals)
                    edges_stream.write(
                        EDGE.pack(
                            child_position_id,
                            child_state_id,
                            move_token,
                            label_offset,
                            len(label_bytes),
                            posting_start,
                            len(ordinals),
                            *_counts(rows),
                        )
                    )

        posting_index = {}
        with (directory / "postings.bin").open("wb") as stream:
            cursor = iter(
                connection.execute(
                    "SELECT posting_key, ordinal FROM posting_entries ORDER BY posting_key, ordinal"
                )
            )
            pending = next(cursor, None)
            while pending is not None:
                key = pending[0]
                values = []
                while pending is not None and pending[0] == key:
                    values.append(pending[1])
                    pending = next(cursor, None)
                posting_index[key] = {"offset": stream.tell(), "count": len(values)}
                _write_uint32s(stream, values)
        (directory / "postings.json").write_text(
            json.dumps(posting_index, separators=(",", ":"), sort_keys=True)
        )

        root_placement_key = identity_key("position", Board().placement())
        root_state_key = identity_key("state", Board().position_key())
        root_position_id = connection.execute(
            "SELECT id FROM position_ids WHERE key=?", (root_placement_key,)
        ).fetchone()[0]
        root_state_id = connection.execute(
            "SELECT id FROM state_ids WHERE key=?", (root_state_key,)
        ).fetchone()[0]
        files = [
            "edges.bin",
            "game_offsets.bin",
            "games.bin",
            "memberships.bin",
            "positions.bin",
            "postings.bin",
            "postings.json",
            "states.bin",
            "strings.bin",
        ]
        build_id = observed_input_digest
        manifest = {
            "adapter_policy": ADAPTER_POLICY_VERSION,
            "build_id": build_id,
            "dataset_version": build_id,
            "edge_record_bytes": EDGE.size,
            "edges": edges_count,
            "files": {
                name: {
                    "bytes": (directory / name).stat().st_size,
                    "sha256": _file_hash(directory / name),
                }
                for name in files
            },
            "format_version": "packed-position-graph-v1",
            "games": accepted,
            "node_semantics": "piece-placement-v1",
            "position_record_bytes": POSITION.size,
            "positions": positions_count,
            "root_node_id": root_position_id,
            "root_state_id": root_state_id,
            "replay_policy": GRAPH_REPLAY_POLICY_VERSION,
            "source_fingerprint": source_fingerprint,
            "state_record_bytes": STATE.size,
            "state_semantics": "side-castling-en-passant-v1",
            "states": states_count,
            "support_semantics": "distinct-game-membership-v1",
            "terminal_policy": terminal_policy,
        }
        if shared_positions is not None:
            manifest["shared_positions"] = shared_positions.count
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        temporary_bytes = staging_path.stat().st_size
        final_bytes = sum((directory / name).stat().st_size for name in files) + (
            directory / "manifest.json"
        ).stat().st_size
        return StreamingGraphBuildReport(
            build_id=build_id,
            accepted_games=accepted,
            skipped=observed_skipped,
            positions=positions_count,
            states=states_count,
            edges=edges_count,
            memberships=membership_cursor,
            temporary_bytes=temporary_bytes,
            final_bytes=final_bytes,
        )
    finally:
        connection.close()
        if shared_positions is not None:
            shared_positions.close()


def build_two_pass_position_graph(
    outcomes_factory,
    directory,
    *,
    source_fingerprint: str,
    temporary_directory,
    flush_memberships: int = 100_000,
    discovery_progress_callback=None,
    progress_callback=None,
) -> StreamingGraphBuildReport:
    """Build the production graph without retaining dead support-one tails.

    The first pass proves which piece placements occur in at least two distinct
    games. The second pass replays every game and retains its path through the
    last such placement, plus one source edge. A unique bridge to later shared
    play is therefore retained in full; only a tail proven never to re-enter
    shared play is omitted.
    """
    directory = Path(directory)
    temporary_directory = Path(temporary_directory)
    if directory.exists():
        raise FileExistsError(directory)
    if temporary_directory.exists():
        raise FileExistsError(temporary_directory)
    temporary_directory.mkdir(parents=True)
    discovery = discover_shared_positions(
        outcomes_factory(),
        temporary_directory / "shared-position-discovery",
        source_fingerprint=source_fingerprint,
        progress_callback=discovery_progress_callback,
    )
    report = build_streaming_position_graph(
        outcomes_factory(),
        directory,
        source_fingerprint=source_fingerprint,
        temporary_directory=temporary_directory / "graph-staging",
        flush_memberships=flush_memberships,
        progress_callback=progress_callback,
        shared_positions_path=discovery.shared_positions_path,
        terminal_policy="last-shared-placement-plus-one-or-game-end-v1",
        expected_accepted_games=discovery.accepted_games,
        expected_skipped=discovery.skipped,
        expected_input_digest=discovery.input_digest,
    )
    if report.accepted_games != discovery.accepted_games:
        raise ValueError("accepted game count changed between graph build passes")
    if report.skipped != discovery.skipped:
        raise ValueError("skipped game accounting changed between graph build passes")
    if report.build_id != discovery.input_digest:
        raise ValueError("accepted game content or order changed between graph build passes")
    return StreamingGraphBuildReport(
        build_id=report.build_id,
        accepted_games=report.accepted_games,
        skipped=report.skipped,
        positions=report.positions,
        states=report.states,
        edges=report.edges,
        memberships=report.memberships,
        temporary_bytes=sum(
            path.stat().st_size
            for path in temporary_directory.rglob("*")
            if path.is_file()
        ),
        final_bytes=report.final_bytes,
    )
