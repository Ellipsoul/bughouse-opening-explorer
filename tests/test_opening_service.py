import asyncio
from unittest.mock import patch

from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.publication import (
    validate_artifact,
    write_runtime_attestation,
)
import pytest

from bughouse_explorer.opening.service import (
    BudgetExceeded,
    InvalidNodeId,
    OpeningReadService,
    StaleDatasetVersion,
    create_opening_service,
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


def _request(app, path, *, headers=(), query=""):
    messages = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    async def run():
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
                "query_string": query.encode(),
                "root_path": "",
                "headers": [(name.lower().encode(), value.encode()) for name, value in headers],
                "client": ("127.0.0.1", 12345),
                "server": ("service.example", 443),
            },
            receive,
            send,
        )

    asyncio.run(run())
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    response_headers = {
        name.decode().lower(): value.decode()
        for name, value in start["headers"]
    }
    return start["status"], response_headers, body


def test_http_boundary_separates_health_from_authenticated_readiness(tmp_path):
    artifact, report = _artifact(tmp_path)
    app = create_opening_service(artifact, bearer_token="preview-secret")

    health_status, health_headers, health_body = _request(app, "/healthz")
    unauthorized_status, _, _ = _request(app, "/readyz")
    ready_status, ready_headers, ready_body = _request(
        app,
        "/readyz",
        headers=(("authorization", "Bearer preview-secret"),),
    )

    assert health_status == 200
    assert health_headers["cache-control"] == "no-store"
    assert b'"status":"alive"' in health_body
    assert unauthorized_status == 401
    assert ready_status == 200
    assert ready_headers["cache-control"] == "private, no-cache"
    assert report.build_id.encode() in ready_body
    assert b'"status":"ready"' in ready_body


def test_http_boundary_emits_deterministic_validator_and_honors_if_none_match(tmp_path):
    artifact, _report = _artifact(tmp_path)
    app = create_opening_service(artifact, bearer_token="preview-secret")
    authorization = ("authorization", "Bearer preview-secret")

    status, headers, first_body = _request(
        app,
        "/api/meta",
        headers=(authorization,),
    )
    not_modified, second_headers, second_body = _request(
        app,
        "/api/meta",
        headers=(authorization, ("if-none-match", headers["etag"])),
    )

    assert status == 200
    assert headers["cache-control"] == "private, no-cache"
    assert headers["etag"].startswith('"')
    assert first_body
    assert not_modified == 304
    assert second_headers["etag"] == headers["etag"]
    assert second_body == b""


def test_http_neighborhood_body_and_validator_exclude_runtime_timing(tmp_path):
    artifact, report = _artifact(tmp_path)
    app = create_opening_service(artifact)
    query = f"dataset_version={report.build_id}&max_nodes=20&max_encoded_bytes=32000"

    first_status, first_headers, first_body = _request(
        app, "/api/nodes/0/neighborhood", query=query
    )
    second_status, second_headers, second_body = _request(
        app, "/api/nodes/0/neighborhood", query=query
    )

    assert first_status == second_status == 200
    assert first_headers["etag"] == second_headers["etag"]
    assert first_body == second_body
    assert first_headers["server-timing"] != ""


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


def test_fresh_reader_reports_separate_startup_phases_and_scaling_scopes(tmp_path):
    artifact, _report = _artifact(tmp_path)

    with OpeningReadService(artifact) as service:
        profile = service.startup_profile

    assert list(profile["phases"]) == [
        "manifest_parse",
        "component_stat",
        "component_checksum",
        "structural_validation",
        "posting_directory_parse",
        "mmap_construction",
    ]
    assert profile["phases"]["manifest_parse"]["scaling"] == "constant"
    assert profile["phases"]["component_stat"]["scaling"] == "file_count"
    assert profile["phases"]["component_checksum"]["scaling"] == "artifact_bytes"
    assert profile["phases"]["structural_validation"]["scaling"] == "node_and_edge_records"
    assert profile["phases"]["posting_directory_parse"]["scaling"] == "posting_directory_bytes"
    assert profile["phases"]["mmap_construction"]["scaling"] == "mapped_file_count"
    assert profile["phases"]["component_checksum"]["bytes"] == sum(
        record["bytes"] for record in service.index.manifest["files"].values()
    )
    assert profile["phases"]["structural_validation"]["nodes"] == service.index.manifest["nodes"]
    assert profile["phases"]["structural_validation"]["edges"] == service.index.manifest["edges"]
    assert profile["phases"]["posting_directory_parse"]["records"] == len(service.index.posting_index)
    assert profile["phases"]["mmap_construction"]["files"] == 6
    assert all(phase["wall_ms"] >= 0 for phase in profile["phases"].values())
    assert profile["total_wall_ms"] >= sum(
        phase["wall_ms"] for phase in profile["phases"].values()
    )


def test_attested_reader_skips_full_artifact_validation_at_runtime(tmp_path):
    artifact, _report = _artifact(tmp_path)
    attestation = tmp_path / "opening-artifact-attestation.json"
    write_runtime_attestation(
        artifact,
        attestation,
        validated=validate_artifact(artifact),
    )

    with patch(
        "bughouse_explorer.opening.service.validate_artifact_profiled",
        side_effect=AssertionError("full validation belongs in the build"),
    ), OpeningReadService(artifact, runtime_attestation=attestation) as service:
        profile = service.startup_profile

    assert "component_checksum" not in profile["phases"]
    assert "structural_validation" not in profile["phases"]
    assert profile["phases"]["component_stat"]["scaling"] == "file_count"


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
