from pathlib import Path

from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.streaming import build_streaming_packed_index
from bughouse_explorer.opening.vercel_stage import (
    AUTHORIZED_ARTIFACT_NAME,
    stage_probe_bundle,
    stage_service_bundle,
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
    assert (destination / "vercel.json").exists()
    assert (destination / "requirements.txt").read_text() == "fastapi==0.141.1\n"
