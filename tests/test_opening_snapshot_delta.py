import importlib.util
from pathlib import Path
import sqlite3

import pytest

from bughouse_explorer.opening.adapter import STANDARD_INITIAL_SETUP
from opening_fixtures import E4, E5, NF3, token


spec = importlib.util.spec_from_file_location(
    "snapshot_delta", Path(__file__).parents[1] / "scripts/analyze_opening_snapshot_delta.py"
)
delta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delta)


def snapshot(path, rows, *, username="alice"):
    with sqlite3.connect(path) as connection:
        connection.executescript(delta.SUBSET_SCHEMA)
        connection.executemany("INSERT INTO players VALUES (?, ?)", [(1, username), (2, "bob")])
        for uuid, options in rows.items():
            connection.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                uuid, options.get("tcn", E4 + E5), "bughouse", STANDARD_INITIAL_SETUP,
                "public", 1790000000, "180", 1, "https://www.chess.com/game/live/1",
                options.get("hash", "hash"),
            ))
            connection.executemany("INSERT INTO game_participants VALUES (?, ?, ?, ?, ?)", [
                (uuid, "white", 1, options.get("rating", 2100), options.get("white_result", "win")),
                (uuid, "black", 2, 2000, options.get("result", "checkmated")),
            ])


def quiet(*args, **kwargs):
    pass


def test_delta_covers_additions_deletions_and_corrections_outside_raw_hash(tmp_path):
    before, after = tmp_path / "before.db", tmp_path / "after.db"
    old = {"unchanged": {}, "deleted": {}, "rating": {}, "moves": {}, "hash": {}, "admission": {}}
    new = {
        "unchanged": {}, "rating": {"rating": 2200}, "moves": {"tcn": E4},
        "hash": {"hash": "new"}, "admission": {"result": "resigned"},
        "added": {}, "empty": {"tcn": ""},
    }
    snapshot(before, old)
    snapshot(after, new)
    result = delta.analyze(before, after, tmp_path / "output", progress=quiet)
    assert result["counts"]["new_boards"] == 2
    assert result["counts"]["deleted_boards"] == 1
    assert result["counts"]["existing_participant_candidate_boards"] == 2
    assert result["classifications"]["existing_accepted_metadata_changed"] == 1
    assert result["classifications"]["existing_accepted_moves_changed"] == 1
    assert result["classifications"]["existing_accepted_content_hash_only"] == 1
    assert result["classifications"]["existing_accepted_to_short_non_checkmate"] == 1
    assert result["classifications"]["deleted_adapter_accepted"] == 1
    assert result["classifications"]["added_adapter_accepted"] == 1
    assert result["new_adapter_skips"] == {"empty_tcn": 1}
    assert result["existing_accepted_field_changes"]["white_rating"] == 1
    assert result["existing_accepted_field_changes"]["move_tokens"] == 1


def test_username_changes_are_found_without_game_or_participant_hash_changes(tmp_path):
    before, after = tmp_path / "before.db", tmp_path / "after.db"
    snapshot(before, {"game": {}})
    snapshot(after, {"game": {}}, username="renamed")
    result = delta.analyze(before, after, tmp_path / "output", progress=quiet)
    assert result["classifications"]["existing_accepted_metadata_changed"] == 1
    assert result["distinct_username_replacement_pairs"] == 1
    assert result["counts"]["unchanged_boards"] == 0
    assert result["snapshot_sha256"]["before"] == delta.sha256(before)
    assert result["snapshot_sha256"]["after"] == delta.sha256(after)


def test_checksums_and_fresh_outputs_are_required(tmp_path):
    before, after = tmp_path / "before.db", tmp_path / "after.db"
    snapshot(before, {})
    snapshot(after, {})
    with pytest.raises(ValueError, match="checksum mismatch"):
        delta.analyze(before, after, tmp_path / "bad-hash", expected_before="0" * 64, progress=quiet)
    with pytest.raises(FileExistsError):
        delta.analyze(before, after, tmp_path / "bad-hash", progress=quiet)


def test_result_bucket_correction_is_found_without_replaying_moves(tmp_path):
    before, after = tmp_path / "before.db", tmp_path / "after.db"
    moves = "".join((
        E4, E5, NF3, token("b8", "c6"), token("f1", "c4"),
        token("g8", "f6"), token("d2", "d4"), token("e5", "d4"),
    ))
    snapshot(before, {"game": {"tcn": moves, "result": "resigned"}})
    snapshot(after, {"game": {
        "tcn": moves, "white_result": "agreed", "result": "agreed",
    }})
    result = delta.analyze(before, after, tmp_path / "output", progress=quiet)
    assert result["existing_result_bucket_changes"] == {"win -> draw": 1}
    assert result["classifications"]["existing_accepted_metadata_changed"] == 1
    assert result["game_field_changes"]["existing_tcn_changed"] == 0


def test_live_crawler_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="never data/crawler.db"):
        delta.analyze(tmp_path / "data/crawler.db", tmp_path / "other.db", tmp_path / "output", progress=quiet)
