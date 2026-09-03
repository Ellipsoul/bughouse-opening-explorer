"""Validated atomic publication pointer for immutable index versions."""

from dataclasses import dataclass
import hashlib
import json
import mmap
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import time

from .packed import EDGE, NODE, UINT32, UINT64, _file_hash
from .position_graph_packed import (
    EDGE as GRAPH_EDGE,
    EDGE_V2 as GRAPH_EDGE_V2,
    GAME_V2 as GRAPH_GAME_V2,
    POSITION as GRAPH_POSITION,
    POSITION_V2 as GRAPH_POSITION_V2,
    STATE as GRAPH_STATE,
    STATE_V2 as GRAPH_STATE_V2,
)


@dataclass(frozen=True)
class PublishedVersion:
    artifact: Path
    build_id: str
    format: str


RUNTIME_ATTESTATION_FILENAME = "opening-artifact-attestation.json"
RUNTIME_ATTESTATION_FORMAT = "opening-artifact-runtime-attestation-v1"


def _canonical_json(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _is_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_component_name(name):
    if not isinstance(name, str):
        return False
    candidate = PurePosixPath(name)
    return (
        candidate.as_posix() == name
        and not candidate.is_absolute()
        and len(candidate.parts) == 1
        and name not in {"", ".", "..", "manifest.json"}
    )


def _fixed_records(path, record, *, chunk_records=65_536):
    with path.open("rb") as stream:
        while chunk := stream.read(record.size * chunk_records):
            if len(chunk) % record.size:
                raise ValueError(f"partial packed record: {path.name}")
            yield from record.iter_unpack(chunk)


def _validate_position_graph_v2_envelope(path, manifest):
    """Validate v2 metadata and fixed-width file boundaries without scanning rows."""
    if manifest.get("terminal_policy") not in {
        "full-replay-game-end-v1",
        "last-shared-placement-plus-one-or-game-end-v1",
    }:
        raise ValueError("packed graph terminal policy mismatch")
    if manifest.get("replay_policy") not in {
        "strict-source-game-v1",
        "skip-unreplayable-source-game-v1",
    }:
        raise ValueError("packed graph replay policy mismatch")
    if manifest.get("game_metadata_semantics") != "browser-visible-chess-com-v1":
        raise ValueError("packed graph game metadata semantics mismatch")
    if manifest.get("membership_storage") != "shared-equal-postings-v1":
        raise ValueError("packed graph membership storage mismatch")
    if min(
        manifest.get("games", 0),
        manifest.get("positions", 0),
        manifest.get("states", 0),
    ) < 1:
        raise ValueError("packed graph requires games, positions, and states")
    if manifest["terminal_policy"].startswith("last-shared"):
        shared_count = manifest.get("shared_positions")
        if (
            not isinstance(shared_count, int)
            or not 0 <= shared_count <= manifest["positions"]
        ):
            raise ValueError("packed graph shared-position count mismatch")
    for field, record, count, filename in (
        (
            "position_record_bytes",
            GRAPH_POSITION_V2,
            manifest["positions"],
            "positions.bin",
        ),
        ("state_record_bytes", GRAPH_STATE_V2, manifest["states"], "states.bin"),
        ("edge_record_bytes", GRAPH_EDGE_V2, manifest["edges"], "edges.bin"),
        ("game_record_bytes", GRAPH_GAME_V2, manifest["games"], "games.bin"),
    ):
        if manifest.get(field) != record.size:
            raise ValueError(f"packed {field.replace('_', ' ')} mismatch")
        if (path / filename).stat().st_size != count * record.size:
            raise ValueError(f"packed {filename} record size mismatch")

    membership_bytes = (path / "memberships.bin").stat().st_size
    if membership_bytes % UINT32.size:
        raise ValueError("packed graph membership record size mismatch")
    membership_count = membership_bytes // UINT32.size
    if not 0 <= manifest["root_node_id"] < manifest["positions"]:
        raise ValueError("packed graph root position mismatch")
    if not 0 <= manifest["root_state_id"] < manifest["states"]:
        raise ValueError("packed graph root state mismatch")

    dictionaries = json.loads((path / "game_dictionaries.json").read_text())
    if set(dictionaries) != {"provenance_flag_sets", "results", "sources"}:
        raise ValueError("packed graph game dictionary shape mismatch")
    if any(not 0 < len(dictionaries[name]) <= 256 for name in dictionaries):
        raise ValueError("packed graph game dictionary cardinality mismatch")
    username_count = manifest.get("usernames")
    if not isinstance(username_count, int) or username_count < 1:
        raise ValueError("packed graph username count mismatch")
    if (path / "username_offsets.bin").stat().st_size != (
        username_count + 1
    ) * UINT32.size:
        raise ValueError("packed graph username offset count mismatch")
    username_size = (path / "usernames.bin").stat().st_size
    return membership_count, dictionaries, username_count, username_size


def _validate_position_graph_v2(path, manifest, phases, started):
    """Structurally validate v2 with bounded resident memory."""
    membership_count, dictionaries, username_count, username_size = (
        _validate_position_graph_v2_envelope(path, manifest)
    )
    previous = 0
    for index, (offset,) in enumerate(
        _fixed_records(path / "username_offsets.bin", UINT32)
    ):
        if offset < previous or offset > username_size:
            raise ValueError(f"packed graph username offset mismatch: {index}")
        previous = offset
    if previous != username_size:
        raise ValueError("packed graph final username offset mismatch")

    strings_size = (path / "strings.bin").stat().st_size
    for position_id, (string_start, string_length, game_start, game_count) in enumerate(
        _fixed_records(path / "positions.bin", GRAPH_POSITION_V2)
    ):
        if string_start + string_length > strings_size:
            raise ValueError(f"packed position string mismatch: {position_id}")
        if game_start + game_count > membership_count:
            raise ValueError(f"packed position membership mismatch: {position_id}")
        if game_count > manifest["games"]:
            raise ValueError(f"packed position support mismatch: {position_id}")

    next_edge_id = 0
    root_position_id = None
    for state_id, state in enumerate(
        _fixed_records(path / "states.bin", GRAPH_STATE_V2)
    ):
        (
            position_id,
            edge_start,
            edge_count,
            game_start,
            game_count,
            ending_start,
            ending_count,
            wins,
            draws,
            side,
            castling_mask,
            ep_square,
        ) = state
        if state_id == manifest["root_state_id"]:
            root_position_id = position_id
        if position_id >= manifest["positions"]:
            raise ValueError(f"packed state position mismatch: {state_id}")
        if edge_start + edge_count > manifest["edges"]:
            raise ValueError(f"packed state edge range mismatch: {state_id}")
        if edge_count:
            if edge_start != next_edge_id:
                raise ValueError(f"packed state edge ownership mismatch: {state_id}")
            next_edge_id += edge_count
        if game_start + game_count > membership_count:
            raise ValueError(f"packed state membership mismatch: {state_id}")
        if ending_start + ending_count > membership_count:
            raise ValueError(f"packed state ending mismatch: {state_id}")
        if ending_count > game_count:
            raise ValueError(f"packed state ending support mismatch: {state_id}")
        if wins + draws > game_count:
            raise ValueError(f"packed state outcome count mismatch: {state_id}")
        if side not in (0, 1) or castling_mask > 15:
            raise ValueError(f"packed state context mismatch: {state_id}")
        if ep_square != 255 and ep_square > 63:
            raise ValueError(f"packed state en-passant mismatch: {state_id}")
    if next_edge_id != manifest["edges"]:
        raise ValueError("packed graph has unowned edges")
    if root_position_id != manifest["root_node_id"]:
        raise ValueError("packed graph root node/state mismatch")

    for edge_id, edge in enumerate(
        _fixed_records(path / "edges.bin", GRAPH_EDGE_V2)
    ):
        (
            child_state_id,
            _move_token,
            label_start,
            label_length,
            game_start,
            game_count,
            wins,
            draws,
        ) = edge
        if child_state_id >= manifest["states"]:
            raise ValueError(f"packed edge child state mismatch: {edge_id}")
        if label_start + label_length > strings_size:
            raise ValueError(f"packed edge label mismatch: {edge_id}")
        if game_start + game_count > membership_count:
            raise ValueError(f"packed edge membership mismatch: {edge_id}")
        if wins + draws > game_count:
            raise ValueError(f"packed edge outcome count mismatch: {edge_id}")

    for ordinal, game in enumerate(_fixed_records(path / "games.bin", GRAPH_GAME_V2)):
        (
            _uuid,
            _url,
            white_username_id,
            black_username_id,
            _white_rating,
            _black_rating,
            white_result_id,
            black_result_id,
            source_id,
            provenance_id,
        ) = game
        if white_username_id >= username_count or black_username_id >= username_count:
            raise ValueError(f"packed game username mismatch: {ordinal}")
        if (
            white_result_id >= len(dictionaries["results"])
            or black_result_id >= len(dictionaries["results"])
            or source_id >= len(dictionaries["sources"])
            or provenance_id >= len(dictionaries["provenance_flag_sets"])
        ):
            raise ValueError(f"packed game dictionary mismatch: {ordinal}")

    if phases is not None:
        phases["structural_validation"] = {
            "edges": manifest["edges"],
            "nodes": manifest["positions"],
            "states": manifest["states"],
            "scaling": "streamed_position_state_edge_and_game_records",
            "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
        }
    return PublishedVersion(
        path.resolve(), manifest["build_id"], "packed-position-graph"
    )


def _validate_relational(path):
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise ValueError(f"relational quick_check failed: {quick_check}")
        metadata = {
            key: json.loads(value)
            for key, value in connection.execute("SELECT key, value FROM metadata")
        }
        games = connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        nodes = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        root = connection.execute(
            "SELECT interval_start, interval_end FROM nodes WHERE id=0"
        ).fetchone()
        if games != metadata["games"] or nodes != metadata["nodes"]:
            raise ValueError("relational manifest count mismatch")
        if games and root != (0, games):
            raise ValueError("relational root interval mismatch")
        bad_terminals = connection.execute(
            """
            SELECT COUNT(*) FROM nodes
            WHERE terminal_ordinal IS NOT NULL
              AND (terminal_ordinal < interval_start OR terminal_ordinal >= interval_end)
            """
        ).fetchone()[0]
        if bad_terminals:
            raise ValueError("relational terminal outside node interval")
    return PublishedVersion(path.resolve(), metadata["build_id"], "sqlite")


def _validate_artifact(path, phases=None):
    path = Path(path)
    if path.is_file():
        return _validate_relational(path)
    if path.is_dir() and (path / "manifest.json").is_file():
        started = time.perf_counter_ns()
        manifest = json.loads((path / "manifest.json").read_text())
        if phases is not None:
            phases["manifest_parse"] = {
                "bytes": (path / "manifest.json").stat().st_size,
                "scaling": "constant",
                "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
            }

        started = time.perf_counter_ns()
        candidates = {}
        for name, expected in manifest["files"].items():
            candidate = path / name
            if candidate.stat().st_size != expected["bytes"]:
                raise ValueError(f"packed size mismatch: {name}")
            candidates[name] = candidate
        if phases is not None:
            phases["component_stat"] = {
                "files": len(candidates),
                "scaling": "file_count",
                "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
            }

        started = time.perf_counter_ns()
        for name, expected in manifest["files"].items():
            candidate = candidates[name]
            if _file_hash(candidate) != expected["sha256"]:
                raise ValueError(f"packed hash mismatch: {name}")
        if phases is not None:
            phases["component_checksum"] = {
                "bytes": sum(record["bytes"] for record in manifest["files"].values()),
                "files": len(candidates),
                "scaling": "artifact_bytes",
                "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
            }

        started = time.perf_counter_ns()
        if manifest.get("format_version") == "packed-position-graph-v2":
            return _validate_position_graph_v2(path, manifest, phases, started)
        if manifest.get("format_version") == "packed-position-graph-v1":
            if manifest.get("terminal_policy") not in {
                "full-replay-game-end-v1",
                "last-shared-placement-plus-one-or-game-end-v1",
            }:
                raise ValueError("packed graph terminal policy mismatch")
            if manifest.get("replay_policy") not in {
                "strict-source-game-v1",
                "skip-unreplayable-source-game-v1",
            }:
                raise ValueError("packed graph replay policy mismatch")
            if min(
                manifest.get("games", 0),
                manifest.get("positions", 0),
                manifest.get("states", 0),
            ) < 1:
                raise ValueError("packed graph requires games, positions, and states")
            if manifest["terminal_policy"].startswith("last-shared"):
                shared_count = manifest.get("shared_positions")
                if (
                    not isinstance(shared_count, int)
                    or not 0 <= shared_count <= manifest["positions"]
                ):
                    raise ValueError("packed graph shared-position count mismatch")
            if (
                (path / "positions.bin").stat().st_size
                != manifest["positions"] * GRAPH_POSITION.size
            ):
                raise ValueError("packed position record size mismatch")
            if (
                (path / "states.bin").stat().st_size
                != manifest["states"] * GRAPH_STATE.size
            ):
                raise ValueError("packed state record size mismatch")
            if (
                (path / "edges.bin").stat().st_size
                != manifest["edges"] * GRAPH_EDGE.size
            ):
                raise ValueError("packed graph edge record size mismatch")
            membership_bytes = (path / "memberships.bin").stat().st_size
            if membership_bytes % UINT32.size:
                raise ValueError("packed graph membership record size mismatch")
            membership_count = membership_bytes // UINT32.size
            if (path / "game_offsets.bin").stat().st_size != (
                manifest["games"] + 1
            ) * UINT64.size:
                raise ValueError("packed graph game offset count mismatch")
            if not 0 <= manifest["root_node_id"] < manifest["positions"]:
                raise ValueError("packed graph root position mismatch")
            if not 0 <= manifest["root_state_id"] < manifest["states"]:
                raise ValueError("packed graph root state mismatch")
            strings_size = (path / "strings.bin").stat().st_size
            with (path / "positions.bin").open("rb") as position_stream, (
                path / "states.bin"
            ).open("rb") as state_stream, (path / "edges.bin").open("rb") as edge_stream:
                position_bytes = mmap.mmap(
                    position_stream.fileno(), 0, access=mmap.ACCESS_READ
                )
                state_bytes = mmap.mmap(state_stream.fileno(), 0, access=mmap.ACCESS_READ)
                edge_bytes = (
                    mmap.mmap(edge_stream.fileno(), 0, access=mmap.ACCESS_READ)
                    if manifest["edges"]
                    else None
                )
                try:
                    next_edge_id = 0
                    for position_id in range(manifest["positions"]):
                        string_start, string_length, game_start, game_count = (
                            GRAPH_POSITION.unpack_from(
                                position_bytes, position_id * GRAPH_POSITION.size
                            )
                        )
                        if string_start + string_length > strings_size:
                            raise ValueError(
                                f"packed position string mismatch: {position_id}"
                            )
                        if game_start + game_count > membership_count:
                            raise ValueError(
                                f"packed position membership mismatch: {position_id}"
                            )
                        if game_count > manifest["games"]:
                            raise ValueError(
                                f"packed position support mismatch: {position_id}"
                            )
                    for state_id in range(manifest["states"]):
                        state = GRAPH_STATE.unpack_from(
                            state_bytes, state_id * GRAPH_STATE.size
                        )
                        (
                            position_id,
                            edge_start,
                            edge_count,
                            game_start,
                            game_count,
                            ending_start,
                            ending_count,
                            _wins,
                            _draws,
                            _losses,
                            side,
                            castling_mask,
                            ep_square,
                        ) = state
                        if position_id >= manifest["positions"]:
                            raise ValueError(f"packed state position mismatch: {state_id}")
                        if edge_start + edge_count > manifest["edges"]:
                            raise ValueError(f"packed state edge range mismatch: {state_id}")
                        if edge_count:
                            if edge_start != next_edge_id:
                                raise ValueError(
                                    f"packed state edge ownership mismatch: {state_id}"
                                )
                            next_edge_id += edge_count
                        if game_start + game_count > membership_count:
                            raise ValueError(
                                f"packed state membership mismatch: {state_id}"
                            )
                        if ending_start + ending_count > membership_count:
                            raise ValueError(
                                f"packed state ending mismatch: {state_id}"
                            )
                        if ending_count > game_count:
                            raise ValueError(
                                f"packed state ending support mismatch: {state_id}"
                            )
                        if _wins + _draws + _losses != game_count:
                            raise ValueError(
                                f"packed state outcome count mismatch: {state_id}"
                            )
                        if side not in (0, 1) or castling_mask > 15:
                            raise ValueError(f"packed state context mismatch: {state_id}")
                        if ep_square != 255 and ep_square > 63:
                            raise ValueError(f"packed state en-passant mismatch: {state_id}")
                        for edge_id in range(edge_start, edge_start + edge_count):
                            edge = GRAPH_EDGE.unpack_from(
                                edge_bytes, edge_id * GRAPH_EDGE.size
                            )
                            child_position_id, child_state_id = edge[:2]
                            label_start, label_length = edge[3:5]
                            edge_game_start, edge_game_count = edge[5:7]
                            if child_position_id >= manifest["positions"]:
                                raise ValueError(
                                    f"packed edge child position mismatch: {edge_id}"
                                )
                            if child_state_id >= manifest["states"]:
                                raise ValueError(
                                    f"packed edge child state mismatch: {edge_id}"
                                )
                            child_state = GRAPH_STATE.unpack_from(
                                state_bytes, child_state_id * GRAPH_STATE.size
                            )
                            if child_state[0] != child_position_id:
                                raise ValueError(
                                    f"packed edge child identity mismatch: {edge_id}"
                                )
                            if label_start + label_length > strings_size:
                                raise ValueError(
                                    f"packed edge label mismatch: {edge_id}"
                                )
                            if edge_game_start + edge_game_count > membership_count:
                                raise ValueError(
                                    f"packed edge membership mismatch: {edge_id}"
                                )
                            if sum(edge[7:10]) != edge_game_count:
                                raise ValueError(
                                    f"packed edge outcome count mismatch: {edge_id}"
                                )
                    if next_edge_id != manifest["edges"]:
                        raise ValueError("packed graph has unowned edges")
                    root_state = GRAPH_STATE.unpack_from(
                        state_bytes, manifest["root_state_id"] * GRAPH_STATE.size
                    )
                    if root_state[0] != manifest["root_node_id"]:
                        raise ValueError("packed graph root node/state mismatch")
                finally:
                    if edge_bytes is not None:
                        edge_bytes.close()
                    state_bytes.close()
                    position_bytes.close()
            if phases is not None:
                phases["structural_validation"] = {
                    "edges": manifest["edges"],
                    "nodes": manifest["positions"],
                    "states": manifest["states"],
                    "scaling": "position_state_and_edge_records",
                    "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
                }
            return PublishedVersion(
                path.resolve(), manifest["build_id"], "packed-position-graph"
            )

        if (path / "nodes.bin").stat().st_size != manifest["nodes"] * NODE.size:
            raise ValueError("packed node record size mismatch")
        if (path / "edges.bin").stat().st_size != manifest["edges"] * EDGE.size:
            raise ValueError("packed edge record size mismatch")
        ending_count = (path / "endings.bin").stat().st_size // 4
        with (path / "nodes.bin").open("rb") as node_stream, (
            path / "edges.bin"
        ).open("rb") as edge_stream:
            node_bytes = mmap.mmap(node_stream.fileno(), 0, access=mmap.ACCESS_READ)
            edge_bytes = (
                mmap.mmap(edge_stream.fileno(), 0, access=mmap.ACCESS_READ)
                if manifest["edges"]
                else None
            )
            try:
                for node_id in range(manifest["nodes"]):
                    node = NODE.unpack_from(node_bytes, node_id * NODE.size)
                    start, end = node[2], node[3]
                    edge_start, edge_count = node[4], node[5]
                    ending_start, node_ending_count = node[6], node[7]
                    terminal = node[8]
                    if not 0 <= start < end <= manifest["games"]:
                        raise ValueError(f"packed node interval mismatch: {node_id}")
                    if edge_start + edge_count > manifest["edges"]:
                        raise ValueError(f"packed edge range mismatch: {node_id}")
                    if ending_start + node_ending_count > ending_count:
                        raise ValueError(f"packed ending range mismatch: {node_id}")
                    if terminal >= 0 and not start <= terminal < end:
                        raise ValueError(f"packed terminal interval mismatch: {node_id}")
                    for edge_index in range(edge_start, edge_start + edge_count):
                        _token, child = EDGE.unpack_from(
                            edge_bytes, edge_index * EDGE.size
                        )
                        if child >= manifest["nodes"]:
                            raise ValueError(f"packed child id mismatch: {node_id}")
                root = NODE.unpack_from(node_bytes, 0)
                if root[2:4] != (0, manifest["games"]):
                    raise ValueError("packed root interval mismatch")
            finally:
                if edge_bytes is not None:
                    edge_bytes.close()
                node_bytes.close()
        if phases is not None:
            phases["structural_validation"] = {
                "edges": manifest["edges"],
                "nodes": manifest["nodes"],
                "scaling": "node_and_edge_records",
                "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
            }
        return PublishedVersion(
            path.resolve(), manifest["build_id"], f"packed-{manifest['postings']}"
        )
    raise ValueError(f"unsupported index artifact: {path}")


def validate_artifact(path):
    return _validate_artifact(path)


def validate_artifact_profiled(path):
    """Validate a packed artifact and return low-cardinality phase metrics."""
    phases = {}
    version = _validate_artifact(path, phases)
    return version, phases


def write_runtime_attestation(
    artifact,
    destination,
    *,
    validated,
    transport_manifest_id=None,
):
    """Record a small runtime boundary after the caller completes full validation.

    The attestation deliberately lives outside the immutable artifact directory so
    the artifact's exact component allowlist remains unchanged.  Runtime startup
    trusts this build-produced statement, hashes only the small artifact manifest,
    and verifies component sizes before opening memory maps.
    """
    artifact = Path(artifact).resolve()
    destination = Path(destination)
    if validated.artifact != artifact:
        raise ValueError("runtime attestation does not match validated artifact")
    manifest_path = artifact / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("build_id") != validated.build_id:
        raise ValueError("runtime attestation build id mismatch")
    if transport_manifest_id is not None and not _is_sha256(transport_manifest_id):
        raise ValueError("runtime attestation transport manifest id mismatch")
    components = manifest.get("files")
    if not isinstance(components, dict) or not components:
        raise ValueError("runtime attestation requires artifact components")
    body = {
        "artifact_name": artifact.name,
        "build_id": validated.build_id,
        "components": components,
        "dataset_version": manifest.get("dataset_version", validated.build_id),
        "format": RUNTIME_ATTESTATION_FORMAT,
        "format_version": manifest.get("format_version"),
        "manifest": {
            "bytes": len(manifest_bytes),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        },
        "transport_manifest_id": transport_manifest_id,
    }
    payload = dict(body)
    payload["attestation_id"] = hashlib.sha256(_canonical_json(body)).hexdigest()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return payload


def _validate_runtime_structure(path, manifest):
    """Check constant-size structural boundaries attested by the build."""
    format_version = manifest.get("format_version")
    if format_version == "packed-position-graph-v2":
        _membership_count, _dictionaries, _username_count, username_size = (
            _validate_position_graph_v2_envelope(path, manifest)
        )
        offsets_path = path / "username_offsets.bin"
        with offsets_path.open("rb") as stream:
            first_offset = UINT32.unpack(stream.read(UINT32.size))[0]
            stream.seek(-UINT32.size, os.SEEK_END)
            final_offset = UINT32.unpack(stream.read(UINT32.size))[0]
        if first_offset != 0 or final_offset != username_size:
            raise ValueError("packed graph username offset boundary mismatch")
        with (path / "states.bin").open("rb") as stream:
            stream.seek(manifest["root_state_id"] * GRAPH_STATE_V2.size)
            root_state = GRAPH_STATE_V2.unpack(stream.read(GRAPH_STATE_V2.size))
        if root_state[0] != manifest["root_node_id"]:
            raise ValueError("packed graph root node/state mismatch")
        return PublishedVersion(
            path.resolve(), manifest["build_id"], "packed-position-graph"
        )

    if format_version == "packed-position-graph-v1":
        if min(
            manifest.get("games", 0),
            manifest.get("positions", 0),
            manifest.get("states", 0),
        ) < 1:
            raise ValueError("packed graph requires games, positions, and states")
        for field, record, count, filename in (
            ("position_record_bytes", GRAPH_POSITION, manifest["positions"], "positions.bin"),
            ("state_record_bytes", GRAPH_STATE, manifest["states"], "states.bin"),
            ("edge_record_bytes", GRAPH_EDGE, manifest["edges"], "edges.bin"),
        ):
            if manifest.get(field) != record.size:
                raise ValueError(f"packed {field.replace('_', ' ')} mismatch")
            if (path / filename).stat().st_size != count * record.size:
                raise ValueError(f"packed {filename} record size mismatch")
        if (path / "memberships.bin").stat().st_size % UINT32.size:
            raise ValueError("packed graph membership record size mismatch")
        if (path / "game_offsets.bin").stat().st_size != (
            manifest["games"] + 1
        ) * UINT64.size:
            raise ValueError("packed graph game offset count mismatch")
        if not 0 <= manifest["root_node_id"] < manifest["positions"]:
            raise ValueError("packed graph root position mismatch")
        if not 0 <= manifest["root_state_id"] < manifest["states"]:
            raise ValueError("packed graph root state mismatch")
        with (path / "states.bin").open("rb") as stream:
            stream.seek(manifest["root_state_id"] * GRAPH_STATE.size)
            root_state = GRAPH_STATE.unpack(stream.read(GRAPH_STATE.size))
        if root_state[0] != manifest["root_node_id"]:
            raise ValueError("packed graph root node/state mismatch")
        return PublishedVersion(
            path.resolve(), manifest["build_id"], "packed-position-graph"
        )

    postings = manifest.get("postings")
    if format_version not in {
        "packed-prefix-interval-v1",
        "packed-prefix-interval-v2",
    } or postings not in {"sorted", "bitmap"}:
        raise ValueError("runtime attestation requires a packed opening artifact")
    if min(manifest.get("games", 0), manifest.get("nodes", 0)) < 1:
        raise ValueError("packed index requires games and nodes")
    if manifest.get("node_record_bytes") != NODE.size:
        raise ValueError("packed node record size mismatch")
    if manifest.get("edge_record_bytes") != EDGE.size:
        raise ValueError("packed edge record size mismatch")
    if (path / "nodes.bin").stat().st_size != manifest["nodes"] * NODE.size:
        raise ValueError("packed node record size mismatch")
    if (path / "edges.bin").stat().st_size != manifest["edges"] * EDGE.size:
        raise ValueError("packed edge record size mismatch")
    with (path / "nodes.bin").open("rb") as stream:
        root = NODE.unpack(stream.read(NODE.size))
    if root[2:4] != (0, manifest["games"]):
        raise ValueError("packed root interval mismatch")
    return PublishedVersion(path.resolve(), manifest["build_id"], f"packed-{postings}")


def validate_runtime_artifact_profiled(path, attestation_path):
    """Validate a build-attested immutable artifact without corpus-sized scans."""
    path = Path(path).resolve()
    attestation_path = Path(attestation_path)
    phases = {}

    started = time.perf_counter_ns()
    attestation = json.loads(attestation_path.read_text())
    expected_keys = {
        "artifact_name",
        "attestation_id",
        "build_id",
        "components",
        "dataset_version",
        "format",
        "format_version",
        "manifest",
        "transport_manifest_id",
    }
    if set(attestation) != expected_keys:
        raise ValueError("runtime attestation shape mismatch")
    if attestation.get("format") != RUNTIME_ATTESTATION_FORMAT:
        raise ValueError("runtime attestation format mismatch")
    transport_manifest_id = attestation.get("transport_manifest_id")
    if transport_manifest_id is not None and not _is_sha256(transport_manifest_id):
        raise ValueError("runtime attestation transport manifest id mismatch")
    body = {key: value for key, value in attestation.items() if key != "attestation_id"}
    if attestation.get("attestation_id") != hashlib.sha256(
        _canonical_json(body)
    ).hexdigest():
        raise ValueError("runtime attestation id mismatch")
    if attestation.get("artifact_name") != path.name:
        raise ValueError("runtime attestation artifact mismatch")
    phases["attestation_parse"] = {
        "bytes": attestation_path.stat().st_size,
        "scaling": "constant",
        "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
    }

    started = time.perf_counter_ns()
    manifest_path = path / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    expected_manifest = attestation.get("manifest")
    if not isinstance(expected_manifest, dict) or set(expected_manifest) != {
        "bytes",
        "sha256",
    }:
        raise ValueError("runtime attestation manifest shape mismatch")
    if len(manifest_bytes) != expected_manifest.get("bytes") or hashlib.sha256(
        manifest_bytes
    ).hexdigest() != expected_manifest.get("sha256"):
        raise ValueError("runtime attestation manifest mismatch")
    manifest = json.loads(manifest_bytes)
    if (
        manifest.get("build_id") != attestation.get("build_id")
        or manifest.get("dataset_version", manifest.get("build_id"))
        != attestation.get("dataset_version")
        or manifest.get("format_version") != attestation.get("format_version")
        or manifest.get("files") != attestation.get("components")
    ):
        raise ValueError("runtime attestation metadata mismatch")
    phases["manifest_attestation"] = {
        "bytes": len(manifest_bytes),
        "scaling": "manifest_bytes",
        "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
    }

    started = time.perf_counter_ns()
    components = manifest.get("files")
    if (
        not isinstance(components, dict)
        or not components
        or not all(_safe_component_name(name) for name in components)
    ):
        raise ValueError("runtime artifact component allowlist mismatch")
    actual_files = {
        candidate.name for candidate in path.iterdir() if candidate.is_file()
    }
    if actual_files != {*components, "manifest.json"}:
        raise ValueError("runtime artifact component allowlist mismatch")
    for name, expected in components.items():
        if (
            not isinstance(expected, dict)
            or set(expected) != {"bytes", "sha256"}
            or not isinstance(expected.get("bytes"), int)
            or expected["bytes"] < 0
            or not _is_sha256(expected.get("sha256"))
            or (path / name).stat().st_size != expected["bytes"]
        ):
            raise ValueError(f"runtime artifact component mismatch: {name}")
    phases["component_stat"] = {
        "files": len(components),
        "scaling": "file_count",
        "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
    }

    started = time.perf_counter_ns()
    version = _validate_runtime_structure(path, manifest)
    phases["structural_envelope"] = {
        "scaling": "constant",
        "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
    }
    return version, phases


def publish_version(artifact, pointer):
    """Validate a retained version, then atomically replace only the pointer."""
    version = validate_artifact(artifact)
    pointer = Path(pointer)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "artifact": str(version.artifact),
            "build_id": version.build_id,
            "format": version.format,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=pointer.parent, prefix=f".{pointer.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer)
        directory_fd = os.open(pointer.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return version


def current_version(pointer):
    payload = json.loads(Path(pointer).read_text())
    return PublishedVersion(
        artifact=Path(payload["artifact"]),
        build_id=payload["build_id"],
        format=payload["format"],
    )


def remove_version(pointer):
    """Remove only the active publication pointer, retaining every artifact."""
    pointer = Path(pointer)
    try:
        pointer.unlink()
    except FileNotFoundError:
        return False
    directory_fd = os.open(pointer.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return True
