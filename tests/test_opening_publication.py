import hashlib
from dataclasses import replace
import pytest

from bughouse_explorer.opening.packed import build_packed_index
from bughouse_explorer.opening.publication import current_version, publish_version
from bughouse_explorer.opening.relational import build_relational_index
from opening_fixtures import D4, D5, NF3, corpus


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
