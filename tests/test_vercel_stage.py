from pathlib import Path
import json

import pytest

from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.publication import (
    RUNTIME_ATTESTATION_FILENAME,
    validate_runtime_artifact_profiled,
)
from bughouse_explorer.opening.streaming import build_streaming_packed_index
from bughouse_explorer.opening.vercel_stage import (
    AUTHORIZED_ARTIFACT_NAME,
    stage_large_preview_bundle,
    stage_probe_bundle,
    stage_service_bundle,
)
from bughouse_explorer.opening.vercel_transport import (
    create_transport_manifest,
    validate_staged_source_manifest,
    write_transport_chunks,
)
from opening_fixtures import corpus


def test_probe_stage_contains_only_explicit_source_and_authorized_artifact(tmp_path):
    artifact = tmp_path / AUTHORIZED_ARTIFACT_NAME
    report = build_streaming_packed_index(
        (
            AdapterOutcome(source_rowid=index, game=opening_game)
            for index, opening_game in enumerate(corpus(), 1)
        ),
        artifact,
        source_fingerprint="vercel-stage-fixture-v1",
        temporary_directory=tmp_path / "temporary",
    )
    source_root = Path(__file__).resolve().parents[1]
    destination = tmp_path / "stage"

    manifest = stage_probe_bundle(source_root, artifact, destination)
    staged = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}

    assert manifest["artifact_build_id"] == report.build_id
    assert "api/compatibility_probe.py" in staged
    assert f"artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}/manifest.json" in staged
    assert "bundle-manifest.json" in staged
    assert not any("crawler" in path or path.endswith((".db", ".zst")) for path in staged)


def test_service_stage_contains_only_api_inputs_and_authorized_artifact(tmp_path):
    artifact = tmp_path / AUTHORIZED_ARTIFACT_NAME
    report = build_streaming_packed_index(
        (
            AdapterOutcome(source_rowid=index, game=opening_game)
            for index, opening_game in enumerate(corpus(), 1)
        ),
        artifact,
        source_fingerprint="vercel-service-stage-fixture-v1",
        temporary_directory=tmp_path / "temporary",
    )
    source_root = Path(__file__).resolve().parents[1]
    destination = tmp_path / "stage"

    manifest = stage_service_bundle(source_root, artifact, destination)
    staged = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }

    assert manifest["artifact_build_id"] == report.build_id
    assert "api/opening_service.py" in staged
    assert "bughouse_explorer/opening/service.py" in staged
    assert "bughouse_explorer/opening/function_probe.py" not in staged
    assert "vercel.probe.json" not in staged
    assert "data/crawler.db" not in staged
    assert not any(path.endswith((".db", ".sqlite", ".zst")) for path in staged)
    assert f"artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}/manifest.json" in staged
    assert RUNTIME_ATTESTATION_FILENAME in staged
    assert (destination / "vercel.json").exists()
    assert (destination / "requirements.txt").read_text() == "fastapi==0.141.1\n"
    runtime_version, _phases = validate_runtime_artifact_profiled(
        destination / "artifacts" / "opening" / AUTHORIZED_ARTIFACT_NAME,
        destination / RUNTIME_ATTESTATION_FILENAME,
    )
    assert runtime_version.build_id == report.build_id


def test_large_preview_stage_contains_chunks_but_not_the_reconstructed_artifact(
    tmp_path,
):
    artifact = tmp_path / AUTHORIZED_ARTIFACT_NAME
    build_streaming_packed_index(
        (
            AdapterOutcome(source_rowid=index, game=opening_game)
            for index, opening_game in enumerate(corpus(), 1)
        ),
        artifact,
        source_fingerprint="vercel-transport-stage-fixture-v1",
        temporary_directory=tmp_path / "temporary",
    )
    transport_manifest = create_transport_manifest(artifact, chunk_size=1024)
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, transport_manifest, chunks)
    source_root = Path(__file__).resolve().parents[1]
    destination = tmp_path / "stage"

    staged_manifest = stage_large_preview_bundle(
        source_root,
        transport_manifest,
        chunks,
        destination,
    )
    validate_staged_source_manifest(staged_manifest)

    staged = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    config = json.loads((destination / "vercel.json").read_text())
    function = config["functions"]["api/index.py"]
    assert config["buildCommand"].startswith(
        "python -m scripts.materialize_vercel_transport "
    )
    assert config["buildCommand"].endswith(
        "--runtime-attestation opening-artifact-attestation.json"
    )
    assert "framework" not in config
    assert "api/index.py" in staged
    assert "api/opening_service.py" not in staged
    assert "public/.keep" in staged
    assert "transport-manifest.json" in staged
    assert any(path.startswith("transport/") for path in staged)
    assert not any(
        path.startswith(f"artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}/")
        for path in staged
    )
    assert "transport/**" in function["excludeFiles"]
    assert function["includeFiles"] == (
        "{"
        f"artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}/**,"
        "opening-artifact-attestation.json}"
    )
    assert "tool.vercel.scripts" not in (destination / "pyproject.toml").read_text()


def test_large_preview_stage_rejects_a_corrupt_upload_input_chunk(tmp_path):
    artifact = tmp_path / AUTHORIZED_ARTIFACT_NAME
    build_streaming_packed_index(
        (
            AdapterOutcome(source_rowid=index, game=opening_game)
            for index, opening_game in enumerate(corpus(), 1)
        ),
        artifact,
        source_fingerprint="vercel-transport-corrupt-stage-fixture-v1",
        temporary_directory=tmp_path / "temporary",
    )
    transport_manifest = create_transport_manifest(artifact, chunk_size=1024)
    chunks = tmp_path / "chunks"
    write_transport_chunks(artifact, transport_manifest, chunks)
    part = transport_manifest["components"][0]["parts"][0]
    chunk = chunks / part["path"]
    payload = bytearray(chunk.read_bytes())
    payload[0] ^= 1
    chunk.write_bytes(payload)

    with pytest.raises(ValueError, match="transport chunk hash mismatch"):
        stage_large_preview_bundle(
            Path(__file__).resolve().parents[1],
            transport_manifest,
            chunks,
            tmp_path / "stage",
        )
