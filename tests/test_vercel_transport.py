import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from bughouse_explorer.opening.vercel_transport import (
    create_transport_manifest,
    reconstruct_transport,
    reuse_staged_source_acknowledgements,
    upload_transport_chunks,
    upload_staged_source_files,
    validate_staged_source_files,
    write_transport_chunks,
)


def _write_artifact(root, name, files, dataset_version="dataset-v1"):
    artifact = root / name
    artifact.mkdir()
    records = {}
    for filename, payload in files.items():
        (artifact / filename).write_bytes(payload)
        records[filename] = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    (artifact / "manifest.json").write_text(
        json.dumps(
            {
                "build_id": dataset_version,
                "dataset_version": dataset_version,
                "files": records,
            },
            sort_keys=True,
        )
    )
    return artifact


def _resign(manifest):
    body = {key: value for key, value in manifest.items() if key != "manifest_id"}
    manifest["manifest_id"] = hashlib.sha256(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def test_transport_manifest_is_deterministic_with_exact_and_short_final_parts(tmp_path):
    artifact = _write_artifact(
        tmp_path,
        "fixture-a",
        {"beta.bin": b"abcdef", "alpha.bin": b"1234"},
    )

    first = create_transport_manifest(
        artifact,
        chunk_size=4,
        authorized_artifact_names={"fixture-a"},
    )
    second = create_transport_manifest(
        artifact,
        chunk_size=4,
        authorized_artifact_names={"fixture-a"},
    )

    assert first == second
    assert [component["path"] for component in first["components"]] == [
        "alpha.bin",
        "beta.bin",
        "manifest.json",
    ]
    beta = first["components"][1]
    assert [(part["offset"], part["bytes"]) for part in beta["parts"]] == [
        (0, 4),
        (4, 2),
    ]
    alpha = first["components"][0]
    assert [(part["offset"], part["bytes"]) for part in alpha["parts"]] == [
        (0, 4)
    ]


def test_transport_reconstructs_every_source_file_byte_for_byte(tmp_path):
    artifact = _write_artifact(
        tmp_path,
        "fixture-a",
        {"beta.bin": b"abcdef", "alpha.bin": b"1234"},
    )
    manifest = create_transport_manifest(
        artifact,
        chunk_size=4,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"

    write_transport_chunks(artifact, manifest, chunks)
    reconstructed = reconstruct_transport(
        manifest,
        chunks,
        tmp_path / "reconstructed",
        validate_artifact_structure=False,
    )

    assert {
        path.name: path.read_bytes() for path in reconstructed.iterdir()
    } == {path.name: path.read_bytes() for path in artifact.iterdir()}


def test_transport_round_trips_an_empty_component(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"empty.bin": b""})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=4,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)

    reconstructed = reconstruct_transport(
        manifest,
        chunks,
        tmp_path / "reconstructed",
        validate_artifact_structure=False,
    )

    assert (reconstructed / "empty.bin").read_bytes() == b""


@pytest.mark.parametrize(
    "mutation",
    ["missing", "unexpected", "truncated", "oversized", "corrupt"],
)
def test_reconstruction_rejects_invalid_chunk_sets_and_bytes(tmp_path, mutation):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=4,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)
    part = chunks / manifest["components"][0]["parts"][0]["path"]
    if mutation == "missing":
        part.unlink()
    elif mutation == "unexpected":
        shutil.copy2(part, chunks / "transport" / "duplicate.bin")
    elif mutation == "truncated":
        part.write_bytes(part.read_bytes()[:-1])
    elif mutation == "oversized":
        part.write_bytes(part.read_bytes() + b"x")
    else:
        payload = bytearray(part.read_bytes())
        payload[0] ^= 1
        part.write_bytes(payload)

    with pytest.raises(ValueError):
        reconstruct_transport(
            manifest,
            chunks,
            tmp_path / "reconstructed",
            validate_artifact_structure=False,
        )


@pytest.mark.parametrize("mutation", ["duplicate", "reordered"])
def test_reconstruction_rejects_duplicate_or_reordered_manifest_parts(
    tmp_path, mutation
):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=4,
        authorized_artifact_names={"fixture-a"},
    )
    invalid = copy.deepcopy(manifest)
    parts = invalid["components"][1]["parts"]
    if mutation == "duplicate":
        parts.append(copy.deepcopy(parts[-1]))
        invalid["components"][1]["bytes"] += parts[-1]["bytes"]
        invalid["source_bytes"] += parts[-1]["bytes"]
        invalid["temporary_bytes"] = invalid["source_bytes"] * 2
    else:
        parts.reverse()
    _resign(invalid)

    with pytest.raises(ValueError):
        reconstruct_transport(
            invalid,
            tmp_path / "unused-chunks",
            tmp_path / "reconstructed",
            validate_artifact_structure=False,
        )


def test_reconstruction_rejects_wrong_component_hash(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=4,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)
    invalid = copy.deepcopy(manifest)
    invalid["components"][1]["sha256"] = "0" * 64
    _resign(invalid)

    with pytest.raises(ValueError, match="reconstructed component hash mismatch"):
        reconstruct_transport(
            invalid,
            chunks,
            tmp_path / "reconstructed",
            validate_artifact_structure=False,
        )


def test_manifest_creation_rejects_wrong_source_size_or_hash(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    (artifact / "payload.bin").write_bytes(b"changed")

    with pytest.raises(ValueError, match="component (size|hash) mismatch"):
        create_transport_manifest(
            artifact,
            chunk_size=4,
            authorized_artifact_names={"fixture-a"},
        )


@pytest.mark.parametrize(
    "artifact_name",
    ["full-post-qualification-20260802-v2-b", "unrelated-artifact"],
)
def test_manifest_creation_rejects_artifact_b_and_unrelated_artifacts(
    tmp_path, artifact_name
):
    artifact = _write_artifact(tmp_path, artifact_name, {"payload.bin": b"abcdef"})

    with pytest.raises(ValueError, match="not transport-authorized"):
        create_transport_manifest(artifact, chunk_size=4)


def test_manifest_creation_rejects_extra_snapshot_or_backup_files(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    (artifact / "snapshot.db.zst").write_bytes(b"forbidden")

    with pytest.raises(ValueError, match="component allowlist"):
        create_transport_manifest(
            artifact,
            chunk_size=4,
            authorized_artifact_names={"fixture-a"},
        )


def test_upload_journal_reuses_acknowledged_chunks_after_interruption(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=1024,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)
    journal = tmp_path / "upload.journal"
    first_calls = []

    def interrupted_uploader(path, part):
        first_calls.append(part["path"])
        if len(first_calls) == 2:
            raise KeyboardInterrupt
        return part["sha1"]

    with pytest.raises(KeyboardInterrupt):
        upload_transport_chunks(
            manifest,
            chunks,
            journal,
            interrupted_uploader,
            sleep=lambda _seconds: None,
        )

    resumed_calls = []

    def resumed_uploader(path, part):
        resumed_calls.append(part["path"])
        return part["sha1"]

    summary = upload_transport_chunks(
        manifest,
        chunks,
        journal,
        resumed_uploader,
        sleep=lambda _seconds: None,
    )

    assert resumed_calls == first_calls[1:]
    assert summary["chunks_reused"] == 1
    assert summary["chunks_uploaded"] == 1
    assert summary["bytes_reused"] + summary["bytes_uploaded"] == manifest[
        "source_bytes"
    ]


def test_upload_retries_idempotently_then_reuses_every_acknowledged_chunk(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=1024,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)
    journal = tmp_path / "upload.journal"
    attempts = 0

    def flaky_uploader(path, part):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("interrupted")
        return part["sha1"]

    first = upload_transport_chunks(
        manifest,
        chunks,
        journal,
        flaky_uploader,
        base_delay=0,
        sleep=lambda _seconds: None,
    )
    second_calls = []
    second = upload_transport_chunks(
        manifest,
        chunks,
        journal,
        lambda path, part: second_calls.append(part["path"]),
        sleep=lambda _seconds: None,
    )

    assert first["retries"] == 1
    assert second_calls == []
    assert second["bytes_reused"] == manifest["source_bytes"]
    assert second["chunks_uploaded"] == 0


def test_upload_journal_recovers_an_incomplete_final_record(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=1024,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)
    journal = tmp_path / "upload.journal"
    upload_transport_chunks(
        manifest,
        chunks,
        journal,
        lambda path, part: part["sha1"],
        sleep=lambda _seconds: None,
    )
    with journal.open("ab") as stream:
        stream.write(b'{"type":"ack"')

    summary = upload_transport_chunks(
        manifest,
        chunks,
        journal,
        lambda path, part: pytest.fail("acknowledged chunk was retransmitted"),
        sleep=lambda _seconds: None,
    )

    assert journal.read_bytes().endswith(b"\n")
    assert summary["bytes_reused"] == manifest["source_bytes"]


def test_upload_rejects_an_acknowledgement_for_the_wrong_digest(tmp_path):
    artifact = _write_artifact(tmp_path, "fixture-a", {"payload.bin": b"abcdef"})
    manifest = create_transport_manifest(
        artifact,
        chunk_size=1024,
        authorized_artifact_names={"fixture-a"},
    )
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)

    with pytest.raises(RuntimeError, match="attempts exhausted"):
        upload_transport_chunks(
            manifest,
            chunks,
            tmp_path / "upload.journal",
            lambda path, part: "0" * 40,
            max_attempts=1,
            sleep=lambda _seconds: None,
        )


def test_staged_source_upload_is_journalled_and_idempotent(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "one.txt").write_bytes(b"one")
    (stage / "two.txt").write_bytes(b"two")
    records = []
    for path in sorted(stage.iterdir()):
        payload = path.read_bytes()
        records.append(
            {
                "bytes": len(payload),
                "path": path.name,
                "sha1": hashlib.sha1(payload).hexdigest(),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "files": records,
        "format": "vercel-staged-source-v1",
        "total_bytes": 6,
        "transport_manifest_id": "transport-id",
    }
    _resign(manifest)
    calls = []

    first = upload_staged_source_files(
        manifest,
        stage,
        tmp_path / "stage.upload-journal",
        lambda path, record: calls.append(record["path"]) or record["sha1"],
        sleep=lambda _seconds: None,
    )
    second = upload_staged_source_files(
        manifest,
        stage,
        tmp_path / "stage.upload-journal",
        lambda path, record: pytest.fail("staged source file was retransmitted"),
        sleep=lambda _seconds: None,
    )

    assert calls == ["one.txt", "two.txt"]
    assert first["bytes_uploaded"] == 6
    assert second["bytes_reused"] == 6


def test_staged_source_journal_reuses_only_byte_identical_files_across_manifests(
    tmp_path,
):
    def staged_manifest(stage):
        records = []
        for path in sorted(stage.iterdir()):
            payload = path.read_bytes()
            records.append(
                {
                    "bytes": len(payload),
                    "path": path.name,
                    "sha1": hashlib.sha1(payload).hexdigest(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        manifest = {
            "files": records,
            "format": "vercel-staged-source-v1",
            "total_bytes": sum(record["bytes"] for record in records),
            "transport_manifest_id": "transport-id",
        }
        _resign(manifest)
        return manifest

    old_stage = tmp_path / "old-stage"
    old_stage.mkdir()
    (old_stage / "large.bin").write_bytes(b"unchanged")
    (old_stage / "source.py").write_bytes(b"old")
    old_manifest = staged_manifest(old_stage)
    old_journal = tmp_path / "old.upload-journal"
    upload_staged_source_files(
        old_manifest,
        old_stage,
        old_journal,
        lambda _path, record: record["sha1"],
        sleep=lambda _seconds: None,
    )

    new_stage = tmp_path / "new-stage"
    new_stage.mkdir()
    (new_stage / "large.bin").write_bytes(b"unchanged")
    (new_stage / "source.py").write_bytes(b"new")
    new_manifest = staged_manifest(new_stage)
    new_journal = tmp_path / "new.upload-journal"

    reused = reuse_staged_source_acknowledgements(
        old_manifest,
        old_journal,
        new_manifest,
        new_journal,
    )
    uploaded = []
    summary = upload_staged_source_files(
        new_manifest,
        new_stage,
        new_journal,
        lambda _path, record: uploaded.append(record["path"]) or record["sha1"],
        sleep=lambda _seconds: None,
    )

    assert reused == {"bytes_reused": 9, "files_reused": 1}
    assert uploaded == ["source.py"]
    assert summary["bytes_reused"] == 9
    assert summary["bytes_uploaded"] == 3


@pytest.mark.parametrize("mutation", ["missing", "unexpected", "corrupt"])
def test_staged_source_input_validation_fails_closed(tmp_path, mutation):
    stage = tmp_path / "stage"
    stage.mkdir()
    source = stage / "one.txt"
    source.write_bytes(b"one")
    manifest = {
        "files": [
            {
                "bytes": 3,
                "path": "one.txt",
                "sha1": hashlib.sha1(b"one").hexdigest(),
                "sha256": hashlib.sha256(b"one").hexdigest(),
            }
        ],
        "format": "vercel-staged-source-v1",
        "total_bytes": 3,
        "transport_manifest_id": "transport-id",
    }
    _resign(manifest)
    if mutation == "missing":
        source.unlink()
    elif mutation == "unexpected":
        (stage / "extra.txt").write_bytes(b"extra")
    else:
        source.write_bytes(b"two")

    with pytest.raises(ValueError):
        validate_staged_source_files(manifest, stage)


def test_representative_artifact_reconstructs_byte_exactly(tmp_path):
    artifact = (
        Path(__file__).resolve().parents[1]
        / "artifacts/opening/representative-mod71-v2-a"
    )
    if not artifact.exists():
        pytest.skip("retained representative artifact is not present")
    manifest = create_transport_manifest(artifact, chunk_size=1024 * 1024)
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, manifest, chunks)

    reconstructed = reconstruct_transport(
        manifest,
        chunks,
        tmp_path / "reconstructed",
    )

    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in reconstructed.iterdir()
    } == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in artifact.iterdir()
    }
