"""Deterministic, checksum-verified transport for immutable opening artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time

from .publication import validate_artifact


DEFAULT_CHUNK_SIZE = 64 * 1024 * 1024
COMPACT_POSITION_GRAPH_ARTIFACT_NAME = "full-position-graph-through-202608-v2"
AUTHORIZED_TRANSPORT_ARTIFACT_NAMES = frozenset(
    {
        "representative-mod71-v2-a",
        "full-post-qualification-20260802-v2-a",
        COMPACT_POSITION_GRAPH_ARTIFACT_NAME,
    }
)


def _canonical_json(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _safe_component_name(name):
    candidate = PurePosixPath(name)
    return (
        candidate.as_posix() == name
        and not candidate.is_absolute()
        and len(candidate.parts) == 1
        and name not in {"", ".", ".."}
    )


def create_transport_manifest(
    artifact,
    *,
    chunk_size=DEFAULT_CHUNK_SIZE,
    authorized_artifact_names=AUTHORIZED_TRANSPORT_ARTIFACT_NAMES,
):
    """Describe an authorized artifact as stable, content-addressed chunks."""
    artifact = Path(artifact)
    if artifact.name not in authorized_artifact_names:
        raise ValueError(f"artifact is not transport-authorized: {artifact.name}")
    if not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    source_manifest_path = artifact / "manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text())
    declared = source_manifest.get("files")
    if not isinstance(declared, dict):
        raise ValueError("artifact manifest files must be an object")
    if not all(_safe_component_name(name) for name in declared):
        raise ValueError("artifact manifest contains an unsafe component path")

    included = sorted([*declared, "manifest.json"])
    actual = sorted(
        path.relative_to(artifact).as_posix()
        for path in artifact.iterdir()
        if path.is_file()
    )
    if actual != included:
        raise ValueError("artifact directory does not match the component allowlist")

    dataset_version = source_manifest.get("dataset_version")
    if not isinstance(dataset_version, str) or not dataset_version:
        raise ValueError("artifact manifest has no dataset_version")

    components = []
    for name in included:
        source = artifact / name
        size = source.stat().st_size
        component_sha256 = hashlib.sha256()
        parts = []
        with source.open("rb") as stream:
            offset = 0
            part_number = 0
            while True:
                payload = stream.read(chunk_size)
                if not payload and (offset or size):
                    break
                sha256 = hashlib.sha256(payload).hexdigest()
                sha1 = hashlib.sha1(payload).hexdigest()
                component_sha256.update(payload)
                parts.append(
                    {
                        "bytes": len(payload),
                        "offset": offset,
                        "part": part_number,
                        "path": (
                            f"transport/{dataset_version}/{name}/"
                            f"part-{part_number:08d}.bin"
                        ),
                        "sha1": sha1,
                        "sha256": sha256,
                    }
                )
                offset += len(payload)
                part_number += 1
                if offset == size:
                    break
        digest = component_sha256.hexdigest()
        if name != "manifest.json":
            expected = declared[name]
            if size != expected.get("bytes"):
                raise ValueError(f"artifact component size mismatch: {name}")
            if digest != expected.get("sha256"):
                raise ValueError(f"artifact component hash mismatch: {name}")
        components.append(
            {"bytes": size, "path": name, "sha256": digest, "parts": parts}
        )

    source_bytes = sum(component["bytes"] for component in components)
    manifest = {
        "artifact_name": artifact.name,
        "chunk_size": chunk_size,
        "components": components,
        "dataset_version": dataset_version,
        "format": "vercel-digest-chunks-v1",
        "source_bytes": source_bytes,
        "temporary_bytes": source_bytes * 2,
    }
    manifest["manifest_id"] = hashlib.sha256(_canonical_json(manifest)).hexdigest()
    return manifest


def validate_transport_manifest(manifest):
    """Fail closed unless a manifest is canonical, contiguous, and self-consistent."""
    if not isinstance(manifest, dict) or manifest.get("format") != "vercel-digest-chunks-v1":
        raise ValueError("unsupported transport manifest")
    claimed_id = manifest.get("manifest_id")
    body = {key: value for key, value in manifest.items() if key != "manifest_id"}
    actual_id = hashlib.sha256(_canonical_json(body)).hexdigest()
    if claimed_id != actual_id:
        raise ValueError("transport manifest id mismatch")
    chunk_size = manifest.get("chunk_size")
    if not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("invalid transport chunk size")
    dataset_version = manifest.get("dataset_version")
    if not isinstance(dataset_version, str) or not dataset_version:
        raise ValueError("invalid transport dataset version")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("transport manifest has no components")
    component_paths = [component.get("path") for component in components]
    if component_paths != sorted(set(component_paths)):
        raise ValueError("transport components are duplicated or reordered")
    if "manifest.json" not in component_paths:
        raise ValueError("transport manifest omits artifact manifest.json")

    all_part_paths = []
    source_bytes = 0
    for component in components:
        name = component.get("path")
        if not isinstance(name, str) or not _safe_component_name(name):
            raise ValueError("unsafe transport component path")
        size = component.get("bytes")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"invalid transport component size: {name}")
        parts = component.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"transport component has no parts: {name}")
        offset = 0
        for expected_part, part in enumerate(parts):
            expected_path = (
                f"transport/{dataset_version}/{name}/part-{expected_part:08d}.bin"
            )
            part_size = part.get("bytes")
            if part.get("part") != expected_part or part.get("offset") != offset:
                raise ValueError(f"transport parts are duplicated or reordered: {name}")
            if part.get("path") != expected_path:
                raise ValueError(f"unexpected transport part path: {name}")
            if not isinstance(part_size, int) or part_size < 0 or part_size > chunk_size:
                raise ValueError(f"invalid transport part size: {name}")
            if part_size == 0 and not (size == 0 and len(parts) == 1):
                raise ValueError(f"unexpected empty transport part: {name}")
            if expected_part < len(parts) - 1 and part_size != chunk_size:
                raise ValueError(f"short non-final transport part: {name}")
            for algorithm, length in (("sha1", 40), ("sha256", 64)):
                digest = part.get(algorithm)
                if not isinstance(digest, str) or len(digest) != length:
                    raise ValueError(f"invalid {algorithm} for transport part: {name}")
                try:
                    int(digest, 16)
                except ValueError as error:
                    raise ValueError(
                        f"invalid {algorithm} for transport part: {name}"
                    ) from error
            offset += part_size
            all_part_paths.append(expected_path)
        if offset != size:
            raise ValueError(f"transport component size mismatch: {name}")
        source_bytes += size
    if len(all_part_paths) != len(set(all_part_paths)):
        raise ValueError("transport part paths are duplicated")
    if manifest.get("source_bytes") != source_bytes:
        raise ValueError("transport source byte total mismatch")
    if manifest.get("temporary_bytes") != source_bytes * 2:
        raise ValueError("transport temporary byte total mismatch")
    return manifest


def write_transport_chunks(artifact, manifest, destination):
    """Write every manifest part to a new, external staging directory."""
    validate_transport_manifest(manifest)
    artifact = Path(artifact)
    destination = Path(destination)
    if artifact.name != manifest["artifact_name"]:
        raise ValueError("transport artifact name mismatch")
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    try:
        for component in manifest["components"]:
            source = artifact / component["path"]
            with source.open("rb") as stream:
                component_sha256 = hashlib.sha256()
                for part in component["parts"]:
                    payload = stream.read(part["bytes"])
                    component_sha256.update(payload)
                    if len(payload) != part["bytes"]:
                        raise ValueError(f"source became truncated: {component['path']}")
                    if hashlib.sha256(payload).hexdigest() != part["sha256"]:
                        raise ValueError(f"source chunk hash mismatch: {part['path']}")
                    if hashlib.sha1(payload).hexdigest() != part["sha1"]:
                        raise ValueError(f"source chunk digest mismatch: {part['path']}")
                    target = destination / part["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as output:
                        output.write(payload)
                        output.flush()
                        os.fsync(output.fileno())
                if stream.read(1):
                    raise ValueError(f"source became oversized: {component['path']}")
                if component_sha256.hexdigest() != component["sha256"]:
                    raise ValueError(f"source component hash mismatch: {component['path']}")
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination


def reconstruct_transport(
    manifest,
    chunks,
    destination,
    *,
    validate_artifact_structure=True,
):
    """Reconstruct a new artifact only after every chunk passes exact validation."""
    validate_transport_manifest(manifest)
    chunks = Path(chunks)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    expected_paths = {
        part["path"]
        for component in manifest["components"]
        for part in component["parts"]
    }
    actual_paths = {
        path.relative_to(chunks).as_posix()
        for path in (chunks / "transport").rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        raise ValueError("transport chunk set is missing or contains unexpected files")

    destination.mkdir(parents=True)
    try:
        for component in manifest["components"]:
            target = destination / component["path"]
            sha256 = hashlib.sha256()
            with target.open("xb") as output:
                for part in component["parts"]:
                    chunk = chunks / part["path"]
                    if chunk.stat().st_size != part["bytes"]:
                        raise ValueError(f"transport chunk size mismatch: {part['path']}")
                    payload = chunk.read_bytes()
                    if hashlib.sha256(payload).hexdigest() != part["sha256"]:
                        raise ValueError(f"transport chunk hash mismatch: {part['path']}")
                    if hashlib.sha1(payload).hexdigest() != part["sha1"]:
                        raise ValueError(f"transport chunk digest mismatch: {part['path']}")
                    output.write(payload)
                    sha256.update(payload)
                output.flush()
                os.fsync(output.fileno())
            if target.stat().st_size != component["bytes"]:
                raise ValueError(f"reconstructed component size mismatch: {component['path']}")
            if sha256.hexdigest() != component["sha256"]:
                raise ValueError(f"reconstructed component hash mismatch: {component['path']}")
        if validate_artifact_structure:
            validate_artifact(destination)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination


class _UploadJournal:
    def __init__(self, path, manifest_id, parts):
        self.path = Path(path)
        self.manifest_id = manifest_id
        self.parts = {part["path"]: part for part in parts}
        self.acknowledged = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._append(
                {
                    "format": "vercel-upload-journal-v1",
                    "manifest_id": manifest_id,
                    "type": "header",
                }
            )
        self._load()

    def _load(self):
        payload = self.path.read_bytes()
        if payload and not payload.endswith(b"\n"):
            complete = payload.rfind(b"\n") + 1
            with self.path.open("r+b") as stream:
                stream.truncate(complete)
                stream.flush()
                os.fsync(stream.fileno())
            payload = payload[:complete]
        records = []
        for line_number, line in enumerate(payload.splitlines(), 1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"corrupt upload journal line {line_number}") from error
        if not records:
            self._append(
                {
                    "format": "vercel-upload-journal-v1",
                    "manifest_id": self.manifest_id,
                    "type": "header",
                }
            )
            records = [json.loads(self.path.read_text().splitlines()[0])]
        header = records[0]
        if (
            header.get("type") != "header"
            or header.get("format") != "vercel-upload-journal-v1"
            or header.get("manifest_id") != self.manifest_id
        ):
            raise ValueError("upload journal belongs to a different manifest")
        for record in records[1:]:
            if record.get("type") != "ack":
                raise ValueError("invalid upload journal record")
            path = record.get("path")
            part = self.parts.get(path)
            if part is None or record.get("sha1") != part["sha1"]:
                raise ValueError("upload journal acknowledges an unknown chunk")
            existing = self.acknowledged.get(path)
            if existing is not None and existing != record["sha1"]:
                raise ValueError("upload journal has conflicting acknowledgements")
            self.acknowledged[path] = record["sha1"]

    def _append(self, record):
        payload = _canonical_json(record) + b"\n"
        descriptor = os.open(
            self.path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError("short upload journal write")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def acknowledge(self, part, remote_digest):
        if remote_digest != part["sha1"]:
            raise ValueError("remote acknowledgement digest mismatch")
        if part["path"] in self.acknowledged:
            return False
        self._append(
            {
                "bytes": part["bytes"],
                "path": part["path"],
                "sha1": remote_digest,
                "type": "ack",
            }
        )
        self.acknowledged[part["path"]] = remote_digest
        return True


def _validate_chunk_file(path, part):
    if path.stat().st_size != part["bytes"]:
        raise ValueError(f"transport chunk size mismatch: {part['path']}")
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha1.update(block)
            sha256.update(block)
    if sha1.hexdigest() != part["sha1"] or sha256.hexdigest() != part["sha256"]:
        raise ValueError(f"transport chunk hash mismatch: {part['path']}")


def upload_transport_chunks(
    manifest,
    chunks,
    journal_path,
    uploader,
    *,
    max_attempts=5,
    base_delay=1.0,
    sleep=time.sleep,
):
    """Upload unacknowledged chunks with bounded retry and durable acknowledgements."""
    validate_transport_manifest(manifest)
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")
    if base_delay < 0:
        raise ValueError("base_delay must be non-negative")
    chunks = Path(chunks)
    all_parts = [
        part
        for component in manifest["components"]
        for part in component["parts"]
    ]
    journal = _UploadJournal(journal_path, manifest["manifest_id"], all_parts)
    summary = {
        "bytes_reused": 0,
        "bytes_uploaded": 0,
        "chunks_reused": 0,
        "chunks_uploaded": 0,
        "manifest_id": manifest["manifest_id"],
        "retries": 0,
    }
    for component in manifest["components"]:
        for part in component["parts"]:
            if part["path"] in journal.acknowledged:
                summary["chunks_reused"] += 1
                summary["bytes_reused"] += part["bytes"]
                continue
            path = chunks / part["path"]
            _validate_chunk_file(path, part)
            for attempt in range(1, max_attempts + 1):
                try:
                    remote_digest = uploader(path, part)
                    journal.acknowledge(part, remote_digest)
                    summary["chunks_uploaded"] += 1
                    summary["bytes_uploaded"] += part["bytes"]
                    break
                except Exception as error:
                    if attempt == max_attempts:
                        raise RuntimeError(
                            f"upload attempts exhausted: {part['path']}"
                        ) from error
                    summary["retries"] += 1
                    sleep(base_delay * (2 ** (attempt - 1)))
    return summary


def validate_staged_source_manifest(manifest):
    """Validate the exact small-file/chunk source set submitted to Vercel."""
    if not isinstance(manifest, dict) or manifest.get("format") != "vercel-staged-source-v1":
        raise ValueError("unsupported staged source manifest")
    claimed_id = manifest.get("manifest_id")
    body = {key: value for key, value in manifest.items() if key != "manifest_id"}
    if claimed_id != hashlib.sha256(_canonical_json(body)).hexdigest():
        raise ValueError("staged source manifest id mismatch")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("staged source manifest has no files")
    paths = [record.get("path") for record in files]
    if paths != sorted(set(paths)):
        raise ValueError("staged source paths are duplicated or reordered")
    total = 0
    for record in files:
        path = record.get("path")
        candidate = PurePosixPath(path) if isinstance(path, str) else None
        if (
            candidate is None
            or candidate.is_absolute()
            or candidate.as_posix() != path
            or ".." in candidate.parts
        ):
            raise ValueError("unsafe staged source path")
        size = record.get("bytes")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"invalid staged source size: {path}")
        for algorithm, length in (("sha1", 40), ("sha256", 64)):
            digest = record.get(algorithm)
            if not isinstance(digest, str) or len(digest) != length:
                raise ValueError(f"invalid staged source {algorithm}: {path}")
            try:
                int(digest, 16)
            except ValueError as error:
                raise ValueError(f"invalid staged source {algorithm}: {path}") from error
        total += size
    if manifest.get("total_bytes") != total:
        raise ValueError("staged source byte total mismatch")
    return manifest


def validate_staged_source_files(manifest, stage):
    """Verify the complete staged upload set and every source-file digest."""
    validate_staged_source_manifest(manifest)
    stage = Path(stage)
    expected = {record["path"] for record in manifest["files"]}
    actual = {
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() and path.name != "bundle-manifest.json"
    }
    if actual != expected:
        raise ValueError("staged source set does not match its manifest")
    for record in manifest["files"]:
        _validate_chunk_file(stage / record["path"], record)
    return manifest


def reuse_staged_source_acknowledgements(
    previous_manifest,
    previous_journal_path,
    manifest,
    journal_path,
):
    """Seed a new journal only with remotely acknowledged byte-identical files."""
    validate_staged_source_manifest(previous_manifest)
    validate_staged_source_manifest(manifest)
    journal_path = Path(journal_path)
    if journal_path.exists():
        raise FileExistsError(journal_path)
    previous_parts = previous_manifest["files"]
    previous_journal = _UploadJournal(
        previous_journal_path,
        previous_manifest["manifest_id"],
        previous_parts,
    )
    journal = _UploadJournal(journal_path, manifest["manifest_id"], manifest["files"])
    previous_by_path = {record["path"]: record for record in previous_parts}
    reused_bytes = 0
    reused_files = 0
    identity_keys = ("bytes", "path", "sha1", "sha256")
    for record in manifest["files"]:
        previous = previous_by_path.get(record["path"])
        if previous is None or record["path"] not in previous_journal.acknowledged:
            continue
        if any(previous[key] != record[key] for key in identity_keys):
            continue
        journal.acknowledge(record, previous_journal.acknowledged[record["path"]])
        reused_bytes += record["bytes"]
        reused_files += 1
    return {"bytes_reused": reused_bytes, "files_reused": reused_files}


def upload_staged_source_files(
    manifest,
    stage,
    journal_path,
    uploader,
    *,
    max_attempts=5,
    base_delay=1.0,
    sleep=time.sleep,
):
    """Journal and upload every exact source file needed for a Preview build."""
    validate_staged_source_files(manifest, stage)
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")
    stage = Path(stage)
    parts = [
        {
            "bytes": record["bytes"],
            "path": record["path"],
            "sha1": record["sha1"],
            "sha256": record["sha256"],
        }
        for record in manifest["files"]
    ]
    journal = _UploadJournal(journal_path, manifest["manifest_id"], parts)
    summary = {
        "bytes_reused": 0,
        "bytes_uploaded": 0,
        "chunks_reused": 0,
        "chunks_uploaded": 0,
        "manifest_id": manifest["manifest_id"],
        "retries": 0,
    }
    for part in parts:
        if part["path"] in journal.acknowledged:
            summary["chunks_reused"] += 1
            summary["bytes_reused"] += part["bytes"]
            continue
        source = stage / part["path"]
        for attempt in range(1, max_attempts + 1):
            try:
                remote_digest = uploader(source, part)
                journal.acknowledge(part, remote_digest)
                summary["chunks_uploaded"] += 1
                summary["bytes_uploaded"] += part["bytes"]
                break
            except Exception as error:
                if attempt == max_attempts:
                    raise RuntimeError(
                        f"upload attempts exhausted: {part['path']}"
                    ) from error
                summary["retries"] += 1
                sleep(base_delay * (2 ** (attempt - 1)))
    return summary
