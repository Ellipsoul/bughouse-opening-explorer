"""Bounded-memory external-sort writer for the immutable packed trie."""

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib

from .adapter import ADAPTER_POLICY_VERSION, AdapterOutcome
from .packed import EDGE, NODE, UINT32, UINT64, _file_hash


@dataclass(frozen=True)
class StreamingBuildReport:
    build_id: str
    accepted_games: int
    skipped: dict[str, int]
    nodes: int
    edges: int
    endings: int
    temporary_bytes: int
    final_bytes: int


@dataclass(frozen=True)
class _LineGroup:
    moves: bytes
    start: int
    end: int


@dataclass(frozen=True)
class _OpenNode:
    id: int
    token: bytes | None
    ply: int


def _common_tokens(left: bytes | None, right: bytes | None) -> int:
    if left is None or right is None:
        return 0
    limit = min(len(left), len(right)) // 2
    for ply in range(limit):
        offset = ply * 2
        if left[offset : offset + 2] != right[offset : offset + 2]:
            return ply
    return limit


def _metadata_payload(row: sqlite3.Row) -> dict:
    return {
        "black_rating": row["black_rating"],
        "black_result": row["black_result"],
        "black_username": row["black_username"],
        "content_hash": row["content_hash"],
        "end_time": row["end_time"],
        "provenance_flags": json.loads(row["provenance_flags"]),
        "rated": bool(row["rated"]),
        "source": row["source"],
        "time_control": row["time_control"],
        "url": row["url"],
        "uuid": row["uuid"],
        "white_rating": row["white_rating"],
        "white_result": row["white_result"],
        "white_username": row["white_username"],
    }


def build_streaming_packed_index(
    outcomes,
    directory,
    *,
    source_fingerprint: str,
    temporary_directory,
) -> StreamingBuildReport:
    """Write a sorted packed artifact while retaining only one line group and path.

    ``temporary_directory`` is mandatory so callers explicitly choose disposable
    capacity and never fall back to the live crawler database or its directory.
    """
    directory = Path(directory)
    temporary_directory = Path(temporary_directory)
    if directory.exists():
        raise FileExistsError(directory)
    if temporary_directory.exists():
        raise FileExistsError(temporary_directory)
    directory.mkdir(parents=True)
    temporary_directory.mkdir(parents=True)
    staging_path = temporary_directory / "opening-stream.sqlite3"
    skipped = Counter()

    connection = sqlite3.connect(staging_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=FILE;
            CREATE TABLE staged_games(
                moves BLOB NOT NULL,
                uuid TEXT NOT NULL,
                white_username TEXT NOT NULL,
                black_username TEXT NOT NULL,
                white_rating INTEGER,
                black_rating INTEGER,
                white_result TEXT,
                black_result TEXT,
                end_time INTEGER,
                time_control TEXT,
                rated INTEGER NOT NULL,
                url TEXT,
                source TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                provenance_flags TEXT NOT NULL,
                PRIMARY KEY(moves, uuid)
            ) WITHOUT ROWID;
            CREATE TABLE posting_entries(
                posting_key TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                PRIMARY KEY(posting_key, ordinal)
            ) WITHOUT ROWID;
            CREATE TABLE trie_nodes(
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL,
                ply INTEGER NOT NULL,
                interval_start INTEGER NOT NULL,
                interval_end INTEGER,
                edge_start INTEGER NOT NULL DEFAULT 0,
                edge_count INTEGER NOT NULL DEFAULT 0,
                ending_start INTEGER NOT NULL DEFAULT 0,
                ending_count INTEGER NOT NULL DEFAULT 0,
                terminal_ordinal INTEGER NOT NULL DEFAULT -1
            );
            CREATE TABLE trie_edges(
                parent_id INTEGER NOT NULL,
                move_token BLOB NOT NULL,
                child_id INTEGER NOT NULL,
                PRIMARY KEY(parent_id, move_token)
            ) WITHOUT ROWID;
            """
        )
        accepted = 0
        insert = connection.execute
        for outcome in outcomes:
            if not isinstance(outcome, AdapterOutcome):
                raise TypeError("streaming writer requires AdapterOutcome records")
            if outcome.game is None:
                if not outcome.skip_reason:
                    raise ValueError("excluded adapter outcome requires a skip reason")
                skipped[outcome.skip_reason] += 1
                continue
            game = outcome.game
            insert(
                """
                INSERT INTO staged_games VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "".join(game.move_tokens).encode("ascii"),
                    game.uuid,
                    game.white_username,
                    game.black_username,
                    game.white_rating,
                    game.black_rating,
                    game.white_result,
                    game.black_result,
                    game.end_time,
                    game.time_control,
                    int(game.rated),
                    game.url,
                    game.source,
                    game.content_hash,
                    json.dumps(game.provenance_flags, separators=(",", ":")),
                ),
            )
            accepted += 1
        if not accepted:
            raise ValueError("packed artifacts require at least one accepted game")
        connection.commit()

        digest = hashlib.blake2b(digest_size=20)
        digest.update(b"opening-trie-v1\0")
        digest.update(source_fingerprint.encode())
        offsets_path = directory / "game_offsets.bin"
        games_path = directory / "games.bin"
        endings_path = directory / "endings.bin"
        ordinal = 0
        ending_count = 0

        def line_groups():
            nonlocal ordinal
            rows = iter(
                connection.execute(
                    "SELECT * FROM staged_games ORDER BY moves, uuid"
                )
            )
            pending = next(rows, None)
            while pending is not None:
                moves = bytes(pending["moves"])
                start = ordinal
                while pending is not None and bytes(pending["moves"]) == moves:
                    row = pending
                    digest.update(b"\0")
                    digest.update(row["uuid"].encode())
                    digest.update(b"\0")
                    digest.update(moves)
                    digest.update(b"\0")
                    digest.update(row["content_hash"].encode())
                    offsets_stream.write(UINT64.pack(games_stream.tell()))
                    games_stream.write(
                        zlib.compress(
                            json.dumps(
                                _metadata_payload(row),
                                separators=(",", ":"),
                                sort_keys=True,
                            ).encode(),
                            level=6,
                        )
                    )
                    for key in (
                        f"white\0{row['white_username']}",
                        f"black\0{row['black_username']}",
                        f"result\0{row['white_result'] or 'unknown'}",
                    ):
                        connection.execute(
                            "INSERT INTO posting_entries VALUES (?, ?)",
                            (key, ordinal),
                        )
                    ordinal += 1
                    pending = next(rows, None)
                yield _LineGroup(moves, start, ordinal)

        connection.execute(
            "INSERT INTO trie_nodes(id, parent_id, ply, interval_start) VALUES (0, -1, 0, 0)"
        )
        next_node_id = 1
        open_path = [_OpenNode(0, None, 0)]
        previous_moves = None
        with games_path.open("wb") as games_stream, offsets_path.open(
            "wb"
        ) as offsets_stream, endings_path.open("wb") as endings_stream:
            groups = iter(line_groups())
            current = next(groups, None)
            following = next(groups, None)
            while current is not None:
                shared = max(
                    _common_tokens(previous_moves, current.moves),
                    _common_tokens(current.moves, following.moves if following else None),
                )
                line_plies = len(current.moves) // 2
                support = current.end - current.start
                target_depth = (
                    line_plies if support > 1 else min(line_plies, shared + 1)
                )
                reuse_depth = min(
                    _common_tokens(previous_moves, current.moves),
                    target_depth,
                    len(open_path) - 1,
                )
                while len(open_path) - 1 > reuse_depth:
                    closing = open_path.pop()
                    connection.execute(
                        "UPDATE trie_nodes SET interval_end=? WHERE id=?",
                        (current.start, closing.id),
                    )
                for ply in range(reuse_depth + 1, target_depth + 1):
                    token = current.moves[(ply - 1) * 2 : ply * 2]
                    parent = open_path[-1]
                    node_id = next_node_id
                    next_node_id += 1
                    connection.execute(
                        """
                        INSERT INTO trie_nodes(
                            id, parent_id, ply, interval_start
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (node_id, parent.id, ply, current.start),
                    )
                    connection.execute(
                        "INSERT INTO trie_edges VALUES (?, ?, ?)",
                        (parent.id, token, node_id),
                    )
                    open_path.append(_OpenNode(node_id, token, ply))
                terminal_node = open_path[target_depth]
                if support == 1:
                    connection.execute(
                        "UPDATE trie_nodes SET terminal_ordinal=? WHERE id=?",
                        (current.start, terminal_node.id),
                    )
                if target_depth == line_plies:
                    connection.execute(
                        """
                        UPDATE trie_nodes
                        SET ending_start=?, ending_count=?
                        WHERE id=?
                        """,
                        (ending_count, support, terminal_node.id),
                    )
                    for ending_ordinal in range(current.start, current.end):
                        endings_stream.write(UINT32.pack(ending_ordinal))
                    ending_count += support
                previous_moves = current.moves
                current = following
                following = next(groups, None)

            while open_path:
                closing = open_path.pop()
                connection.execute(
                    "UPDATE trie_nodes SET interval_end=? WHERE id=?",
                    (accepted, closing.id),
                )
            offsets_stream.write(UINT64.pack(games_stream.tell()))
        connection.commit()

        edge_count = 0
        current_parent = None
        current_edge_start = 0
        current_edge_count = 0
        with (directory / "edges.bin").open("wb") as edge_stream:
            for row in connection.execute(
                "SELECT parent_id, move_token, child_id FROM trie_edges ORDER BY parent_id, move_token"
            ):
                parent_id = row["parent_id"]
                if current_parent is not None and parent_id != current_parent:
                    connection.execute(
                        "UPDATE trie_nodes SET edge_start=?, edge_count=? WHERE id=?",
                        (current_edge_start, current_edge_count, current_parent),
                    )
                    current_edge_start = edge_count
                    current_edge_count = 0
                current_parent = parent_id
                edge_stream.write(EDGE.pack(bytes(row["move_token"]), row["child_id"]))
                edge_count += 1
                current_edge_count += 1
            if current_parent is not None:
                connection.execute(
                    "UPDATE trie_nodes SET edge_start=?, edge_count=? WHERE id=?",
                    (current_edge_start, current_edge_count, current_parent),
                )

        with (directory / "nodes.bin").open("wb") as node_stream:
            for row in connection.execute("SELECT * FROM trie_nodes ORDER BY id"):
                node_stream.write(
                    NODE.pack(
                        row["parent_id"],
                        row["ply"],
                        row["interval_start"],
                        row["interval_end"],
                        row["edge_start"],
                        row["edge_count"],
                        row["ending_start"],
                        row["ending_count"],
                        row["terminal_ordinal"],
                    )
                )

        posting_index = {}
        with (directory / "postings.bin").open("wb") as posting_stream:
            active_key = None
            active_offset = 0
            active_count = 0
            for row in connection.execute(
                "SELECT posting_key, ordinal FROM posting_entries ORDER BY posting_key, ordinal"
            ):
                key = row["posting_key"]
                if active_key is not None and key != active_key:
                    posting_index[active_key] = {
                        "offset": active_offset,
                        "count": active_count,
                    }
                    active_offset = posting_stream.tell()
                    active_count = 0
                active_key = key
                posting_stream.write(UINT32.pack(row["ordinal"]))
                active_count += 1
            if active_key is not None:
                posting_index[active_key] = {
                    "offset": active_offset,
                    "count": active_count,
                }
        (directory / "postings.json").write_text(
            json.dumps(posting_index, separators=(",", ":"), sort_keys=True)
        )

        results = sorted(
            key.removeprefix("result\0")
            for key in posting_index
            if key.startswith("result\0")
        )
        files = [
            "edges.bin",
            "endings.bin",
            "game_offsets.bin",
            "games.bin",
            "nodes.bin",
            "postings.bin",
            "postings.json",
        ]
        build_id = digest.hexdigest()
        manifest = {
            "adapter_policy": ADAPTER_POLICY_VERSION,
            "build_id": build_id,
            "dataset_version": build_id,
            "edge_record_bytes": EDGE.size,
            "edges": edge_count,
            "endings": ending_count,
            "files": {
                name: {
                    "bytes": (directory / name).stat().st_size,
                    "sha256": _file_hash(directory / name),
                }
                for name in files
            },
            "format_version": "packed-prefix-interval-v2",
            "game_metadata_codec": "zlib-json-v1",
            "games": accepted,
            "node_record_bytes": NODE.size,
            "node_semantics": "exact-decoded-move-prefix-v1",
            "nodes": next_node_id,
            "postings": "sorted",
            "results": results,
            "source_fingerprint": source_fingerprint,
            "terminal_policy": "first-distinct-support-one-or-game-end-v1",
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        connection.commit()
        temporary_bytes = staging_path.stat().st_size
        final_bytes = sum((directory / name).stat().st_size for name in files)
    finally:
        connection.close()

    staging_path.unlink()
    temporary_directory.rmdir()
    return StreamingBuildReport(
        build_id=build_id,
        accepted_games=accepted,
        skipped=dict(sorted(skipped.items())),
        nodes=next_node_id,
        edges=edge_count,
        endings=ending_count,
        temporary_bytes=temporary_bytes,
        final_bytes=final_bytes,
    )
