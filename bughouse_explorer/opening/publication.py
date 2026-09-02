"""Validated atomic publication pointer for immutable index versions."""

from dataclasses import dataclass
import json
import mmap
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from .packed import EDGE, NODE, UINT32, UINT64, _file_hash
from .position_graph_packed import (
    EDGE as GRAPH_EDGE,
    POSITION as GRAPH_POSITION,
    STATE as GRAPH_STATE,
)


@dataclass(frozen=True)
class PublishedVersion:
    artifact: Path
    build_id: str
    format: str


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
