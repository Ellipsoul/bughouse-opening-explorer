import json

from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.packed import PackedIndex, build_packed_index
from bughouse_explorer.opening.publication import validate_artifact
from bughouse_explorer.opening.streaming import build_streaming_packed_index
from opening_fixtures import E4, E5, corpus


def _outcomes():
    return [
        AdapterOutcome(source_rowid=index, game=opening_game)
        for index, opening_game in enumerate(corpus(), 1)
    ] + [AdapterOutcome(source_rowid=99, skip_reason="short_non_checkmate")]


def test_streaming_writer_matches_the_packed_oracle_without_retaining_the_corpus(tmp_path):
    oracle = tmp_path / "oracle"
    streamed = tmp_path / "streamed"
    repeated = tmp_path / "repeated"
    build_packed_index(corpus(), oracle, source_fingerprint="fixture-v2")

    first = build_streaming_packed_index(
        iter(_outcomes()),
        streamed,
        source_fingerprint="fixture-v2",
        temporary_directory=tmp_path / "temporary-first",
    )
    second = build_streaming_packed_index(
        iter(_outcomes()),
        repeated,
        source_fingerprint="fixture-v2",
        temporary_directory=tmp_path / "temporary-second",
    )

    assert first.accepted_games == 7
    assert first.skipped == {"short_non_checkmate": 1}
    assert first.build_id == second.build_id
    assert validate_artifact(streamed).build_id == first.build_id
    first_manifest = json.loads((streamed / "manifest.json").read_text())
    second_manifest = json.loads((repeated / "manifest.json").read_text())
    oracle_manifest = json.loads((oracle / "manifest.json").read_text())
    assert first_manifest["game_metadata_codec"] == "zlib-json-v1"
    assert first_manifest["files"]["games.bin"]["bytes"] < oracle_manifest["files"]["games.jsonl"]["bytes"]
    assert first_manifest["files"] == second_manifest["files"]

    queries = [
        ((), None),
        ((E4,), None),
        ((E4, E5), None),
        ((), QueryFilter(white_username="alice")),
        ((E4,), QueryFilter(white_username="alice", black_username="xavier")),
    ]
    with PackedIndex(oracle) as expected, PackedIndex(streamed) as actual:
        for prefix, query_filter in queries:
            assert actual.query(prefix, query_filter) == expected.query(
                prefix, query_filter
            )
