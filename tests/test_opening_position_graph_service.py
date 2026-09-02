import pytest

from bughouse_explorer.opening.position_graph import build_position_graph
from bughouse_explorer.opening.position_graph_packed import build_packed_position_graph
from bughouse_explorer.opening.service import BudgetExceeded, OpeningReadService
from opening_fixtures import D4, E4, NF3, game, token


NF6 = token("g8", "f6")
NC3 = token("b1", "c3")
NC6 = token("b8", "c6")


def _artifact(tmp_path):
    first_order = (NF3, NF6, NC3, NC6)
    second_order = (NC3, NC6, NF3, NF6)
    games = [
        game("a", first_order + (E4,), white="alice", black="xavier"),
        game("b", second_order + (E4,), white="alice", black="yara"),
        game("c", second_order + (D4,), white="carol", black="xavier"),
    ]
    oracle = build_position_graph(games, source_fingerprint="service-graph")
    artifact = tmp_path / "artifact"
    build_packed_position_graph(
        games, artifact, source_fingerprint="service-graph"
    )
    return artifact, oracle


def test_graph_neighborhood_is_state_qualified_and_edge_scoped(tmp_path):
    artifact, oracle = _artifact(tmp_path)
    occurrence = oracle.trace((NF3, NF6, NC3, NC6))

    with OpeningReadService(artifact) as service:
        metadata = service.metadata()
        response = service.neighborhood(
            dataset_version=oracle.build_id,
            anchor_node_id=occurrence.position_id,
            anchor_state_id=occurrence.state_id,
            target_forward_depth=1,
            max_nodes=20,
            max_encoded_bytes=32_000,
        )

    assert metadata["root_state_id"] == oracle.root_state_id
    assert metadata["format_version"] == "packed-position-graph-v1"
    assert metadata["replay_policy"] == "strict-source-game-v1"
    assert response["anchor_node_id"] == occurrence.position_id
    assert response["anchor_state_id"] == occurrence.state_id
    assert "path" not in response
    assert len({node["id"] for node in response["nodes"]}) == len(response["nodes"])
    assert {
        (edge["move_token"], response["edge_overlays"][str(edge["id"])]["support"])
        for edge in response["edges"]
        if edge["parent_state_id"] == occurrence.state_id
    } == {(E4, 2), (D4, 1)}


def test_source_games_are_selected_from_the_traversed_edge_not_the_child_node(tmp_path):
    artifact, oracle = _artifact(tmp_path)
    occurrence = oracle.trace((NF3, NF6, NC3, NC6))

    with OpeningReadService(artifact) as service:
        response = service.neighborhood(
            dataset_version=oracle.build_id,
            anchor_node_id=occurrence.position_id,
            anchor_state_id=occurrence.state_id,
            target_forward_depth=1,
            max_nodes=20,
            max_encoded_bytes=32_000,
        )
        d4_edge = next(edge for edge in response["edges"] if edge["move_token"] == D4)
        examples = service.edge_game_examples(
            dataset_version=oracle.build_id,
            edge_id=d4_edge["id"],
            limit=6,
        )

    assert examples["edge_id"] == d4_edge["id"]
    assert examples["total_matching"] == 1
    assert [example["uuid"] for example in examples["games"]] == ["c"]


def test_graph_rejects_ambiguous_node_scoped_game_examples(tmp_path):
    artifact, oracle = _artifact(tmp_path)

    with OpeningReadService(artifact) as service, pytest.raises(
        ValueError, match="ambiguous"
    ):
        service.game_examples(
            dataset_version=oracle.build_id,
            node_id=oracle.root_position_id,
        )


def test_graph_rejects_an_anchor_move_list_that_exceeds_the_state_budget(tmp_path):
    artifact, oracle = _artifact(tmp_path)

    with OpeningReadService(artifact) as service, pytest.raises(
        BudgetExceeded, match="anchor's atomic graph neighborhood"
    ):
        service.neighborhood(
            dataset_version=oracle.build_id,
            anchor_node_id=oracle.root_position_id,
            anchor_state_id=oracle.root_state_id,
            target_forward_depth=1,
            max_nodes=1,
            max_encoded_bytes=32_000,
        )
