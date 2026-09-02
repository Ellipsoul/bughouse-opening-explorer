from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.position_graph_packed import build_packed_position_graph
from bughouse_explorer.opening.startup import measure_first_load
from bughouse_explorer.opening.streaming import build_streaming_packed_index
from opening_fixtures import corpus


def test_first_load_measurement_separates_bounded_requests_from_reader_readiness(tmp_path):
    artifact = tmp_path / "artifact"
    outcomes = (
        AdapterOutcome(source_rowid=index, game=opening_game)
        for index, opening_game in enumerate(corpus(), 1)
    )
    report = build_streaming_packed_index(
        outcomes,
        artifact,
        source_fingerprint="startup-fixture-v1",
        temporary_directory=tmp_path / "temporary",
    )

    measurement = measure_first_load(artifact)

    assert measurement["dataset_version"] == report.build_id
    assert measurement["startup"]["phases"]["component_checksum"]["scaling"] == "artifact_bytes"
    assert measurement["requests"]["first_metadata"]["scaling"] == "constant"
    assert measurement["requests"]["first_neighborhood"]["scaling"] == "request_budget_bounded"
    assert measurement["requests"]["warm_metadata"]["encoded_bytes"] > 0
    assert measurement["requests"]["warm_neighborhood"]["returned_nodes"] <= 500
    assert measurement["requests"]["warm_neighborhood"]["encoded_bytes"] <= 256 * 1024
    assert measurement["process"]["mapped_virtual_bytes"] > 0
    assert measurement["process"]["minor_page_faults"] >= 0
    assert measurement["process"]["major_page_faults"] >= 0
    assert measurement["process"]["peak_rss_bytes"] > 0


def test_first_load_measurement_uses_the_graph_root_state(tmp_path):
    artifact = tmp_path / "graph"
    build_id = build_packed_position_graph(
        corpus(), artifact, source_fingerprint="startup-graph-v1"
    )

    measurement = measure_first_load(artifact)

    assert measurement["dataset_version"] == build_id
    assert measurement["requests"]["first_neighborhood"]["returned_nodes"] > 0
    assert measurement["requests"]["warm_neighborhood"]["encoded_bytes"] <= 256 * 1024
