import json

import pytest

from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.position_graph import build_position_graph
from bughouse_explorer.opening.position_graph_packed import (
    PackedPositionGraph,
    build_packed_position_graph,
)
from bughouse_explorer.opening.position_graph_streaming import (
    build_streaming_position_graph,
    build_two_pass_position_graph,
    discover_shared_positions,
)
from opening_fixtures import D4, D5, E4, E5, NF3, game, token


NF6 = token("g8", "f6")
NC3 = token("b1", "c3")
NC6 = token("b8", "c6")


def _outcomes(games):
    return tuple(
        AdapterOutcome(source_rowid=index, game=opening_game)
        for index, opening_game in enumerate(games, 1)
    )


def _trace(reader, move_tokens):
    state_id = reader.root_state_id
    for move_token in move_tokens:
        branch = next(
            branch
            for branch in reader.query_state(state_id).branches
            if branch.move_token == move_token
        )
        state_id = branch.child_state_id
    return reader.query_state(state_id)


def test_streaming_graph_matches_the_reference_packed_artifact(tmp_path):
    first_order = (NF3, NF6, NC3, NC6)
    second_order = (NC3, NC6, NF3, NF6)
    games = [
        game("a", first_order + (E4,), white="alice", black="xavier"),
        game("b", second_order + (E4,), white="alice", black="yara"),
        game("c", second_order + (D4,), white="carol", black="xavier"),
    ]
    outcomes = [
        AdapterOutcome(source_rowid=index, game=opening_game)
        for index, opening_game in enumerate(games, 1)
    ] + [AdapterOutcome(source_rowid=99, skip_reason="short_non_checkmate")]
    oracle_dir = tmp_path / "oracle"
    streamed_dir = tmp_path / "streamed"
    build_packed_position_graph(
        games, oracle_dir, source_fingerprint="streaming-graph"
    )

    report = build_streaming_position_graph(
        iter(outcomes),
        streamed_dir,
        source_fingerprint="streaming-graph",
        temporary_directory=tmp_path / "temporary",
    )
    graph = build_position_graph(games, source_fingerprint="streaming-graph")
    state_id = graph.trace(first_order).state_id

    assert report.accepted_games == 3
    assert report.skipped == {"short_non_checkmate": 1}
    assert report.build_id == graph.build_id
    with PackedPositionGraph(oracle_dir) as oracle, PackedPositionGraph(
        streamed_dir
    ) as streamed:
        for query_filter in (
            None,
            QueryFilter(white_username="alice"),
            QueryFilter(black_username="xavier"),
        ):
            assert streamed.query_state(state_id, query_filter) == oracle.query_state(
                state_id, query_filter
            )


def test_two_pass_graph_keeps_unique_bridges_to_a_shared_transposition(tmp_path):
    first_order = (NF3, NF6, NC3, NC6)
    second_order = (NC3, NC6, NF3, NF6)
    games = [
        game("a", first_order + (E4,)),
        game("b", second_order + (E4,)),
        game("c", second_order + (D4,)),
    ]
    outcomes = _outcomes(games)
    output = tmp_path / "graph"

    report = build_two_pass_position_graph(
        lambda: iter(outcomes),
        output,
        source_fingerprint="two-pass-transposition",
        temporary_directory=tmp_path / "temporary",
    )

    manifest = json.loads((output / "manifest.json").read_text())
    assert report.accepted_games == 3
    assert manifest["terminal_policy"] == (
        "last-shared-placement-plus-one-or-game-end-v1"
    )
    assert manifest["replay_policy"] == "skip-unreplayable-source-game-v1"
    assert manifest["shared_positions"] >= 2
    with PackedPositionGraph(output) as reader:
        first = _trace(reader, first_order)
        second = _trace(reader, second_order)
        assert first.position_id == second.position_id
        assert first.state_id == second.state_id
        assert first.state_support == second.state_support == 3
        assert {branch.move_token: branch.support for branch in first.branches} == {
            E4: 2,
            D4: 1,
        }


def test_two_pass_graph_drops_only_the_proven_dead_unique_tail(tmp_path):
    games = [
        game("a", (E4, E5, NF3)),
        game("b", (D4, D5, NC3)),
    ]
    outcomes = _outcomes(games)
    output = tmp_path / "graph"

    build_two_pass_position_graph(
        lambda: iter(outcomes),
        output,
        source_fingerprint="two-pass-dead-tail",
        temporary_directory=tmp_path / "temporary",
    )

    with PackedPositionGraph(output) as reader:
        root = reader.query_state(reader.root_state_id)
        assert {branch.move_token for branch in root.branches} == {E4, D4}
        for branch in root.branches:
            frontier = reader.query_state(branch.child_state_id)
            assert frontier.state_support == 1
            assert frontier.actual_ending_count == 0
            assert frontier.branches == ()
            assert frontier.sole_game_uuid in {"a", "b"}


def test_shared_position_discovery_counts_distinct_games_not_revisits(tmp_path):
    cycle = (NF3, NF6, token("f3", "g1"), token("f6", "g8"))
    games = [game("a", cycle), game("b", (E4,))]

    report = discover_shared_positions(
        iter(_outcomes(games)),
        tmp_path / "discovery",
        source_fingerprint="distinct-game-support",
        chunk_bytes=24,
    )

    assert report.accepted_games == 2
    # The root is revisited by game a, but is emitted once for that game and once
    # for game b, so it is the only shared placement.
    assert report.shared_positions == 1
    assert report.shared_positions_path.stat().st_size == 20


def test_two_pass_graph_rejects_a_changed_second_pass_before_manifest(tmp_path):
    first = _outcomes([game("a", (E4,)), game("b", (D4,))])
    second = _outcomes([game("a", (E4,)), game("changed", (D4,))])
    calls = iter((first, second))
    output = tmp_path / "graph"

    with pytest.raises(ValueError, match="content or order changed"):
        build_two_pass_position_graph(
            lambda: iter(next(calls)),
            output,
            source_fingerprint="changed-input",
            temporary_directory=tmp_path / "temporary",
        )

    assert not (output / "manifest.json").exists()


def test_two_pass_graph_excludes_unreplayable_source_games_in_both_passes(tmp_path):
    invalid = game("broken", (token("f2", "f3"), token("f2", "f4")))
    valid = game("valid", (E4,))
    outcomes = _outcomes([invalid, valid])
    output = tmp_path / "graph"

    report = build_two_pass_position_graph(
        lambda: iter(outcomes),
        output,
        source_fingerprint="unreplayable-source",
        temporary_directory=tmp_path / "temporary",
    )

    assert report.accepted_games == 1
    assert report.skipped == {"position_replay_error": 1}
    with PackedPositionGraph(output) as reader:
        assert reader.manifest["games"] == 1
        assert reader.game(0)["uuid"] == "valid"
