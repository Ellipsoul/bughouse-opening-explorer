import hashlib
from dataclasses import replace
from unittest.mock import patch
import pytest

from bughouse_explorer.opening.packed import build_packed_index
from bughouse_explorer.opening.position_graph_packed import build_packed_position_graph
from bughouse_explorer.opening.position_graph_v2 import repack_position_graph_v2
from bughouse_explorer.opening.publication import (
    current_version,
    publish_version,
    remove_version,
    validate_artifact,
    validate_runtime_artifact_profiled,
    write_runtime_attestation,
)
from bughouse_explorer.opening.relational import build_relational_index
from opening_fixtures import D4, D5, NF3, corpus, game


def _sha256(path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_relational_rebuild_is_byte_deterministic(tmp_path):
    first = tmp_path / "first.sqlite3"
    second = tmp_path / "second.sqlite3"

    first_id = build_relational_index(corpus(), first, source_fingerprint="fixture-v1")
    second_id = build_relational_index(corpus(), second, source_fingerprint="fixture-v1")

    assert second_id == first_id
    assert _sha256(second) == _sha256(first)


def test_packed_rebuild_is_component_deterministic(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_id = build_packed_index(
        corpus(), first, source_fingerprint="fixture-v1", postings="sorted"
    )
    second_id = build_packed_index(
        corpus(), second, source_fingerprint="fixture-v1", postings="sorted"
    )

    assert second_id == first_id
    assert {
        path.name: _sha256(path) for path in first.iterdir() if path.is_file()
    } == {
        path.name: _sha256(path) for path in second.iterdir() if path.is_file()
    }


def test_corrected_rebuild_can_publish_and_roll_back_without_replacing_versions(tmp_path):
    version_one = tmp_path / "v1.sqlite3"
    version_two = tmp_path / "v2.sqlite3"
    pointer = tmp_path / "current.json"
    original = corpus()
    corrected = [
        replace(
            game,
            move_tokens=(D4, D5, NF3),
            content_hash="corrected-hash-c",
        )
        if game.uuid == "c"
        else game
        for game in original
    ]
    first_id = build_relational_index(
        original, version_one, source_fingerprint="fixture-v1"
    )
    second_id = build_relational_index(
        corrected, version_two, source_fingerprint="fixture-v2"
    )

    publish_version(version_one, pointer)
    assert current_version(pointer).build_id == first_id
    publish_version(version_two, pointer)
    assert current_version(pointer).build_id == second_id
    publish_version(version_one, pointer)

    assert current_version(pointer).build_id == first_id
    assert version_one.exists() and version_two.exists()


def test_removal_deletes_only_the_publication_pointer(tmp_path):
    artifact = tmp_path / "packed-v1"
    pointer = tmp_path / "current.json"
    build_packed_index(
        corpus(), artifact, source_fingerprint="fixture-v1", postings="sorted"
    )
    component_hashes = {
        path.name: _sha256(path) for path in artifact.iterdir() if path.is_file()
    }
    publish_version(artifact, pointer)

    assert remove_version(pointer) is True
    assert remove_version(pointer) is False
    assert not pointer.exists()
    assert {
        path.name: _sha256(path) for path in artifact.iterdir() if path.is_file()
    } == component_hashes


def test_packed_publication_rejects_a_corrupted_candidate(tmp_path):
    artifact = tmp_path / "packed-v1"
    pointer = tmp_path / "current.json"
    build_id = build_packed_index(
        corpus(), artifact, source_fingerprint="fixture-v1", postings="sorted"
    )

    publish_version(artifact, pointer)
    assert current_version(pointer).build_id == build_id
    with (artifact / "edges.bin").open("ab") as stream:
        stream.write(b"corruption")

    with pytest.raises(ValueError, match="hash|size"):
        publish_version(artifact, pointer)


def test_runtime_attestation_uses_only_manifest_and_file_count_scaled_checks(tmp_path):
    source = tmp_path / "graph-v1"
    artifact = tmp_path / "graph-v2"
    build_packed_position_graph(
        [
            replace(
                game("a", (D4, D5, NF3)),
                uuid="00000000-0000-4000-8000-00000000000a",
                url="https://www.chess.com/game/live/1001",
            )
        ],
        source,
        source_fingerprint="runtime-attestation-fixture-v1",
    )
    repack_position_graph_v2(source, artifact)
    validated = validate_artifact(artifact)
    attestation = tmp_path / "opening-artifact-attestation.json"
    write_runtime_attestation(
        artifact,
        attestation,
        validated=validated,
        transport_manifest_id="a" * 64,
    )

    with patch(
        "bughouse_explorer.opening.publication._file_hash",
        side_effect=AssertionError("runtime validation must not hash large components"),
    ):
        runtime_version, phases = validate_runtime_artifact_profiled(
            artifact,
            attestation,
        )

    assert runtime_version == validated
    assert list(phases) == [
        "attestation_parse",
        "manifest_attestation",
        "component_stat",
        "structural_envelope",
    ]
    assert phases["manifest_attestation"]["scaling"] == "manifest_bytes"
    assert phases["component_stat"]["scaling"] == "file_count"
    assert phases["structural_envelope"]["scaling"] == "constant"


def test_runtime_attestation_rejects_a_changed_artifact_manifest(tmp_path):
    artifact = tmp_path / "packed-v1"
    build_packed_index(
        corpus(), artifact, source_fingerprint="attested-manifest-v1", postings="sorted"
    )
    attestation = tmp_path / "opening-artifact-attestation.json"
    write_runtime_attestation(
        artifact,
        attestation,
        validated=validate_artifact(artifact),
    )
    (artifact / "manifest.json").write_text(
        (artifact / "manifest.json").read_text() + "\n"
    )

    with pytest.raises(ValueError, match="attestation manifest mismatch"):
        validate_runtime_artifact_profiled(artifact, attestation)


def test_runtime_attestation_rejects_a_changed_component_size(tmp_path):
    artifact = tmp_path / "packed-v1"
    build_packed_index(
        corpus(), artifact, source_fingerprint="attested-size-v1", postings="sorted"
    )
    attestation = tmp_path / "opening-artifact-attestation.json"
    write_runtime_attestation(
        artifact,
        attestation,
        validated=validate_artifact(artifact),
    )
    with (artifact / "edges.bin").open("ab") as stream:
        stream.write(b"corruption")

    with pytest.raises(ValueError, match="component mismatch: edges.bin"):
        validate_runtime_artifact_profiled(artifact, attestation)
