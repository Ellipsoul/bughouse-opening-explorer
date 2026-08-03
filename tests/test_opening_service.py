from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.model import QueryFilter
import pytest

from bughouse_explorer.opening.service import (
    BudgetExceeded,
    InvalidNodeId,
    OpeningReadService,
    StaleDatasetVersion,
)
from bughouse_explorer.opening.streaming import build_streaming_packed_index
from opening_fixtures import E4, E5, corpus


def _artifact(tmp_path):
    artifact = tmp_path / "artifact"
    outcomes = (
        AdapterOutcome(source_rowid=index, game=opening_game)
        for index, opening_game in enumerate(corpus(), 1)
    )
    report = build_streaming_packed_index(
        outcomes,
        artifact,
        source_fingerprint="service-fixture-v1",
        temporary_directory=tmp_path / "temporary",
    )
    return artifact, report


def test_service_reports_validated_versioned_dataset_metadata(tmp_path):
    artifact, report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        metadata = service.metadata()

    assert metadata == {
        "adapter_policy": "opening-adapter-v2-short-non-checkmate",
        "coverage": {
            "accepted_games": 7,
            "source_fingerprint": "service-fixture-v1",
        },
        "dataset_version": report.build_id,
        "format_version": "packed-prefix-interval-v2",
        "root_node_id": 0,
        "terminal_policy": "first-distinct-support-one-or-game-end-v1",
    }


def test_neighborhood_is_versioned_flat_budgeted_and_marks_every_frontier(tmp_path):
    artifact, report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        response = service.neighborhood(
            dataset_version=report.build_id,
            anchor_node_id=0,
            target_forward_depth=5,
            max_nodes=4,
            max_encoded_bytes=32_000,
        )

        try:
            service.neighborhood(
                dataset_version="stale-version",
                anchor_node_id=0,
            )
        except StaleDatasetVersion as error:
            assert error.expected == report.build_id
        else:
            raise AssertionError("stale dataset version was accepted")

    assert response["dataset_version"] == report.build_id
    assert response["anchor_node_id"] == 0
    assert response["path"] == [{"move_token": None, "node_id": 0}]
    assert 1 <= len(response["nodes"]) <= 4
    assert len({node["id"] for node in response["nodes"]}) == len(response["nodes"])
    root_children = {
        edge["child_id"] for edge in response["edges"] if edge["parent_id"] == 0
    }
    assert root_children
    assert root_children <= {node["id"] for node in response["nodes"]}
    assert response["frontiers"]
    assert all(frontier["node_id"] in {node["id"] for node in response["nodes"]} for frontier in response["frontiers"])
    assert response["instrumentation"]["returned_nodes"] == len(response["nodes"])
    assert response["instrumentation"]["encoded_bytes"] <= 32_000


def test_deeper_prefetch_expands_parent_move_lists_atomically(tmp_path):
    artifact, report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        response = service.neighborhood(
            dataset_version=report.build_id,
            anchor_node_id=0,
            target_forward_depth=5,
            max_nodes=5,
            max_encoded_bytes=32_000,
        )

    returned_children = {}
    for edge in response["edges"]:
        returned_children[edge["parent_id"]] = returned_children.get(edge["parent_id"], 0) + 1
    for node in response["nodes"]:
        if node["id"] == response["anchor_node_id"]:
            continue
        assert returned_children.get(node["id"], 0) in {0, node["child_count"]}


def test_filtered_support_one_is_not_reported_as_an_actual_root_ending(tmp_path):
    artifact, report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        response = service.neighborhood(
            dataset_version=report.build_id,
            anchor_node_id=0,
            query_filter=QueryFilter(
                white_username="  FRAN ", black_username="ZED"
            ),
            max_nodes=20,
            max_encoded_bytes=32_000,
        )

    root = response["overlays"]["0"]
    assert response["filter"] == {
        "black_username": "zed",
        "white_username": "fran",
    }
    assert root["support"] == 1
    assert root["sole_game_ordinal"] is not None
    assert root["actual_ending_count"] == 0


def test_game_examples_are_lazy_bounded_and_keep_actual_endings_explicit(tmp_path):
    artifact, report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        root = service.neighborhood(
            dataset_version=report.build_id,
            anchor_node_id=0,
            max_nodes=20,
            max_encoded_bytes=32_000,
        )
        e4 = next(edge["child_id"] for edge in root["edges"] if edge["move_token"] == E4)
        e4_view = service.neighborhood(
            dataset_version=report.build_id,
            anchor_node_id=e4,
            max_nodes=20,
            max_encoded_bytes=32_000,
        )
        e5 = next(edge["child_id"] for edge in e4_view["edges"] if edge["move_token"] == E5)
        games = service.game_examples(
            dataset_version=report.build_id,
            node_id=e5,
            limit=1,
        )

    assert games["dataset_version"] == report.build_id
    assert games["node_id"] == e5
    assert games["total_matching"] == 3
    assert games["actual_ending_count"] == 2
    assert len(games["games"]) == 1
    assert games["games"][0]["actual_ending"] is True
    assert games["games"][0]["url"].startswith("https://example.invalid/")
    assert "raw_payload" not in games["games"][0]


def test_player_search_is_prefix_based_versioned_and_strictly_limited(tmp_path):
    artifact, report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        result = service.search_players(
            dataset_version=report.build_id,
            prefix=" AL ",
            limit=1,
        )

    assert result == {
        "dataset_version": report.build_id,
        "limit": 1,
        "players": [
            {"black_games": 0, "username": "alice", "white_games": 3}
        ],
        "prefix": "al",
        "truncated": False,
    }


def test_service_rejects_invalid_nodes_filters_and_requests_beyond_hard_budgets(tmp_path):
    artifact, report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        with pytest.raises(InvalidNodeId):
            service.neighborhood(
                dataset_version=report.build_id,
                anchor_node_id=999_999,
            )
        with pytest.raises(BudgetExceeded):
            service.neighborhood(
                dataset_version=report.build_id,
                anchor_node_id=0,
                max_nodes=4_001,
            )
        with pytest.raises(ValueError, match="printable"):
            service.neighborhood(
                dataset_version=report.build_id,
                anchor_node_id=0,
                query_filter=QueryFilter(white_username="\x00bad"),
            )
