import json

from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.position_graph import build_position_graph
from bughouse_explorer.opening.position_graph_packed import (
    PackedPositionGraph,
    _SelectedGames,
    build_packed_position_graph,
)
from opening_fixtures import D4, E4, NF3, game, token


NF6 = token("g8", "f6")
NC3 = token("b1", "c3")
NC6 = token("b8", "c6")


def _games():
    first_order = (NF3, NF6, NC3, NC6)
    second_order = (NC3, NC6, NF3, NF6)
    return [
        game("a", first_order + (E4,), white="alice", black="xavier"),
        game("b", second_order + (E4,), white="alice", black="yara"),
        game("c", second_order + (D4,), white="carol", black="xavier"),
    ]


def test_packed_graph_matches_reference_queries_and_declares_graph_semantics(tmp_path):
    games = _games()
    oracle = build_position_graph(games, source_fingerprint="graph-fixture")
    artifact = tmp_path / "artifact"

    build_id = build_packed_position_graph(
        games,
        artifact,
        source_fingerprint="graph-fixture",
    )
    manifest = json.loads((artifact / "manifest.json").read_text())

    assert build_id == oracle.build_id
    assert manifest["format_version"] == "packed-position-graph-v1"
    assert manifest["node_semantics"] == "piece-placement-v1"
    assert manifest["state_semantics"] == "side-castling-en-passant-v1"
    assert manifest["support_semantics"] == "distinct-game-membership-v1"
    assert manifest["terminal_policy"] == "full-replay-game-end-v1"
    assert manifest["replay_policy"] == "strict-source-game-v1"

    state_id = oracle.trace((NF3, NF6, NC3, NC6)).state_id
    queries = [
        None,
        QueryFilter(white_username="alice"),
        QueryFilter(black_username="xavier"),
        QueryFilter(white_username="alice", black_username="xavier"),
    ]
    with PackedPositionGraph(artifact) as packed:
        assert packed.root_position_id == oracle.root_position_id
        assert packed.root_state_id == oracle.root_state_id
        for query_filter in queries:
            assert packed.query_state(state_id, query_filter) == oracle.query_state(
                state_id, query_filter
            )


def test_filtered_intersection_scans_a_small_posting_instead_of_every_selected_game():
    class SmallPosting:
        count = 2

        def __init__(self):
            self.value_calls = 0

        def value(self, index):
            self.value_calls += 1
            return (3, 90)[index]

        def contains(self, _value):
            raise AssertionError("large selected set must not be scanned")

    posting = SmallPosting()
    selected = _SelectedGames(range(100))

    assert PackedPositionGraph._matches(posting, selected) == (3, 90)
    assert posting.value_calls == 2
