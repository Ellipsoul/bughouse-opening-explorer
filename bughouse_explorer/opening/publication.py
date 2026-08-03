"""Validated atomic publication pointer for immutable index versions."""

from dataclasses import dataclass
import json
import mmap
import os
from pathlib import Path
import sqlite3
import tempfile

from .packed import EDGE, NODE, _file_hash


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


def validate_artifact(path):
    path = Path(path)
    if path.is_file():
        return _validate_relational(path)
    if path.is_dir() and (path / "manifest.json").is_file():
        manifest = json.loads((path / "manifest.json").read_text())
        for name, expected in manifest["files"].items():
            candidate = path / name
            if candidate.stat().st_size != expected["bytes"]:
                raise ValueError(f"packed size mismatch: {name}")
            if _file_hash(candidate) != expected["sha256"]:
                raise ValueError(f"packed hash mismatch: {name}")
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
        return PublishedVersion(
            path.resolve(), manifest["build_id"], f"packed-{manifest['postings']}"
        )
    raise ValueError(f"unsupported index artifact: {path}")


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
