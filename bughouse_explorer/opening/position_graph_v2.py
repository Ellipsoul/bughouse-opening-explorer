"""Lossless v1-to-v2 repacking for the transposition-aware position graph."""

from array import array
import json
import re
import shutil
import sys
from pathlib import Path
import uuid
import zlib

from .packed import _file_hash
from .position_graph_packed import (
    EDGE_V1,
    EDGE_V2,
    GAME_V2,
    POSITION_V1,
    POSITION_V2,
    STATE_V1,
    STATE_V2,
    UINT32,
    UINT64,
)


_CHESS_COM_LIVE_URL = re.compile(
    r"https://www\.chess\.com/game/live/([0-9]+)/?\Z"
)
_UINT32_LIMIT = 1 << 32


def _records(path, record, *, chunk_records=65_536):
    with path.open("rb") as stream:
        while chunk := stream.read(record.size * chunk_records):
            if len(chunk) % record.size:
                raise ValueError(f"partial record in {path.name}")
            yield from record.iter_unpack(chunk)


def _require_uint32(value, field):
    if not 0 <= value < _UINT32_LIMIT:
        raise ValueError(f"{field} exceeds the v2 uint32 capacity")
    return value


def _require_uint8(value, field):
    if not 0 <= value < 256:
        raise ValueError(f"{field} exceeds the v2 uint8 capacity")
    return value


def _require_uint16(value, field):
    if not 0 <= value < 65_536:
        raise ValueError(f"{field} exceeds the v2 uint16 capacity")
    return value


def _copy_posting(source, output, start, count):
    output_start = output.tell() // UINT32.size
    _require_uint32(output_start, "membership offset")
    if output_start + count > _UINT32_LIMIT:
        raise ValueError("membership range exceeds the v2 uint32 capacity")
    source.seek(start * UINT32.size)
    remaining = count * UINT32.size
    while remaining:
        chunk = source.read(min(remaining, 8 * 1024 * 1024))
        if not chunk:
            raise ValueError("membership range extends past memberships.bin")
        output.write(chunk)
        remaining -= len(chunk)
    return output_start


def _intern(value, values, index, field):
    try:
        return index[value]
    except KeyError:
        identifier = len(values)
        _require_uint8(identifier, field)
        values.append(value)
        index[value] = identifier
        return identifier


def _encode_rating(value, field):
    if value is None:
        return 0xFFFF
    if not 0 <= value < 0xFFFF:
        raise ValueError(f"{field} exceeds the v2 uint16 capacity")
    return value


def _numeric_game_url(value):
    if value is None:
        return 0xFFFFFFFFFFFFFFFF
    match = _CHESS_COM_LIVE_URL.fullmatch(value)
    if match is None:
        raise ValueError(f"unsupported non-Chess.com game URL: {value!r}")
    numeric_id = int(match.group(1))
    if not 0 <= numeric_id < 0xFFFFFFFFFFFFFFFF:
        raise ValueError("Chess.com game id exceeds the v2 uint64 capacity")
    return numeric_id


def _repack_games(source, output):
    offsets = source / "game_offsets.bin"
    offsets_bytes = offsets.read_bytes()
    if len(offsets_bytes) % UINT64.size:
        raise ValueError("partial record in game_offsets.bin")
    game_count = len(offsets_bytes) // UINT64.size - 1

    usernames = []
    username_ids = {}
    results = []
    result_ids = {}
    sources = []
    source_ids = {}
    provenance_sets = []
    provenance_ids = {}

    with (source / "games.bin").open("rb") as compressed, (
        output / "games.bin"
    ).open("wb") as games:
        for ordinal in range(game_count):
            start = UINT64.unpack_from(offsets_bytes, ordinal * UINT64.size)[0]
            end = UINT64.unpack_from(offsets_bytes, (ordinal + 1) * UINT64.size)[0]
            compressed.seek(start)
            metadata = json.loads(zlib.decompress(compressed.read(end - start)))
            white_username_id = username_ids.setdefault(
                metadata["white_username"], len(usernames)
            )
            if white_username_id == len(usernames):
                usernames.append(metadata["white_username"])
            black_username_id = username_ids.setdefault(
                metadata["black_username"], len(usernames)
            )
            if black_username_id == len(usernames):
                usernames.append(metadata["black_username"])
            provenance = tuple(metadata["provenance_flags"])
            games.write(
                GAME_V2.pack(
                    uuid.UUID(metadata["uuid"]).bytes,
                    _numeric_game_url(metadata["url"]),
                    _require_uint32(white_username_id, "username id"),
                    _require_uint32(black_username_id, "username id"),
                    _encode_rating(metadata["white_rating"], "white rating"),
                    _encode_rating(metadata["black_rating"], "black rating"),
                    _intern(
                        metadata["white_result"], results, result_ids, "result id"
                    ),
                    _intern(
                        metadata["black_result"], results, result_ids, "result id"
                    ),
                    _intern(metadata["source"], sources, source_ids, "source id"),
                    _intern(
                        provenance,
                        provenance_sets,
                        provenance_ids,
                        "provenance id",
                    ),
                )
            )

    username_cursor = 0
    with (output / "usernames.bin").open("wb") as strings, (
        output / "username_offsets.bin"
    ).open("wb") as offset_stream:
        for username in usernames:
            offset_stream.write(
                UINT32.pack(_require_uint32(username_cursor, "username offset"))
            )
            encoded = username.encode("utf-8")
            strings.write(encoded)
            username_cursor += len(encoded)
        offset_stream.write(
            UINT32.pack(_require_uint32(username_cursor, "username offset"))
        )

    (output / "game_dictionaries.json").write_text(
        json.dumps(
            {
                "provenance_flag_sets": [list(value) for value in provenance_sets],
                "results": results,
                "sources": sources,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return game_count, len(usernames)


def repack_position_graph_v2(source_directory, output_directory):
    """Repack an immutable v1 artifact without changing graph semantics or IDs."""
    source = Path(source_directory)
    output = Path(output_directory)
    if output.exists():
        raise FileExistsError(output)
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("format_version") != "packed-position-graph-v1":
        raise ValueError("source must use packed-position-graph-v1")
    for field in ("games", "positions", "states", "edges"):
        if not 0 <= manifest.get(field, -1) < _UINT32_LIMIT:
            raise ValueError(f"{field} exceeds the v2 uint32 capacity")
    for name, expected in manifest["files"].items():
        candidate = source / name
        if candidate.stat().st_size != expected["bytes"]:
            raise ValueError(f"source size mismatch: {name}")
        if _file_hash(candidate) != expected["sha256"]:
            raise ValueError(f"source hash mismatch: {name}")
    output.mkdir(parents=True)

    position_state_counts = array("B", [0]) * manifest["positions"]
    for state in _records(source / "states.bin", STATE_V1):
        position_id = state[0]
        if position_state_counts[position_id] == 255:
            raise ValueError("position has too many state contexts for v2 analysis")
        position_state_counts[position_id] += 1

    state_indegrees = array("B", [0]) * manifest["states"]
    for edge in _records(source / "edges.bin", EDGE_V1):
        child_state_id = edge[1]
        if state_indegrees[child_state_id] == 255:
            raise ValueError("state has too many incoming edges for v2 analysis")
        state_indegrees[child_state_id] += 1

    position_starts = array("I", [0]) * manifest["positions"]
    state_starts = array("I", [0]) * manifest["states"]
    if position_starts.itemsize != UINT32.size or sys.byteorder != "little":
        raise RuntimeError("v2 repacking requires little-endian four-byte arrays")

    with (source / "memberships.bin").open("rb") as source_memberships, (
        output / "memberships.bin"
    ).open("wb") as memberships, (output / "positions.bin").open(
        "wb"
    ) as positions:
        for position_id, row in enumerate(
            _records(source / "positions.bin", POSITION_V1)
        ):
            string_offset, string_length, start, count = row
            new_start = _copy_posting(
                source_memberships, memberships, start, count
            )
            position_starts[position_id] = new_start
            positions.write(
                POSITION_V2.pack(
                    _require_uint32(string_offset, "position string offset"),
                    _require_uint8(string_length, "position string length"),
                    new_start,
                    _require_uint32(count, "position support"),
                )
            )

        with (output / "states.bin").open("wb") as states:
            for state_id, row in enumerate(
                _records(source / "states.bin", STATE_V1)
            ):
                (
                    position_id,
                    edge_start,
                    edge_count,
                    start,
                    count,
                    ending_start,
                    ending_count,
                    wins,
                    draws,
                    losses,
                    side,
                    castling_mask,
                    ep_square,
                ) = row
                if count != wins + draws + losses:
                    raise ValueError("state outcome counts do not equal support")
                if position_state_counts[position_id] == 1:
                    new_start = position_starts[position_id]
                else:
                    new_start = _copy_posting(
                        source_memberships, memberships, start, count
                    )
                state_starts[state_id] = new_start
                new_ending_start = _copy_posting(
                    source_memberships, memberships, ending_start, ending_count
                )
                states.write(
                    STATE_V2.pack(
                        position_id,
                        _require_uint32(edge_start, "edge offset"),
                        _require_uint8(edge_count, "outgoing edge count"),
                        new_start,
                        _require_uint32(count, "state support"),
                        new_ending_start,
                        _require_uint16(ending_count, "ending count"),
                        _require_uint32(wins, "state wins"),
                        _require_uint32(draws, "state draws"),
                        side,
                        castling_mask,
                        ep_square,
                    )
                )

        with (output / "edges.bin").open("wb") as edges:
            for row in _records(source / "edges.bin", EDGE_V1):
                (
                    _child_position_id,
                    child_state_id,
                    move_token,
                    label_offset,
                    label_length,
                    start,
                    count,
                    wins,
                    draws,
                    losses,
                ) = row
                if count != wins + draws + losses:
                    raise ValueError("edge outcome counts do not equal support")
                # Every game enters the root implicitly.  Even when a cycle gives
                # it one structural incoming edge, that edge's games are only a
                # subset of the root state's games.
                if (
                    child_state_id != manifest["root_state_id"]
                    and state_indegrees[child_state_id] == 1
                ):
                    new_start = state_starts[child_state_id]
                else:
                    new_start = _copy_posting(
                        source_memberships, memberships, start, count
                    )
                edges.write(
                    EDGE_V2.pack(
                        child_state_id,
                        move_token,
                        _require_uint32(label_offset, "edge label offset"),
                        _require_uint8(label_length, "edge label length"),
                        new_start,
                        _require_uint32(count, "edge support"),
                        _require_uint32(wins, "edge wins"),
                        _require_uint32(draws, "edge draws"),
                    )
                )

    for name in ("strings.bin", "postings.bin", "postings.json"):
        shutil.copyfile(source / name, output / name)
    game_count, username_count = _repack_games(source, output)
    if game_count != manifest["games"]:
        raise ValueError("game offset count does not match manifest")

    files = [
        "edges.bin",
        "game_dictionaries.json",
        "games.bin",
        "memberships.bin",
        "positions.bin",
        "postings.bin",
        "postings.json",
        "states.bin",
        "strings.bin",
        "username_offsets.bin",
        "usernames.bin",
    ]
    output_manifest = dict(manifest)
    output_manifest.update(
        {
            "edge_record_bytes": EDGE_V2.size,
            "files": {
                name: {
                    "bytes": (output / name).stat().st_size,
                    "sha256": _file_hash(output / name),
                }
                for name in files
            },
            "format_version": "packed-position-graph-v2",
            "game_metadata_semantics": "browser-visible-chess-com-v1",
            "game_record_bytes": GAME_V2.size,
            "membership_storage": "shared-equal-postings-v1",
            "position_record_bytes": POSITION_V2.size,
            "state_record_bytes": STATE_V2.size,
            "usernames": username_count,
        }
    )
    (output / "manifest.json").write_text(
        json.dumps(output_manifest, indent=2, sort_keys=True) + "\n"
    )
    return output_manifest["build_id"]
