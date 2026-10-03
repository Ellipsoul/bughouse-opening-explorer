from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import importlib.util

from bughouse_explorer.opening.position_graph_packed import build_packed_position_graph
from bughouse_explorer.opening.service import OpeningReadService
from bughouse_explorer.opening.startup import measure_first_load
from opening_fixtures import corpus

spec = importlib.util.spec_from_file_location(
    "hosted_oracle",
    Path(__file__).resolve().parents[1] / "scripts/validate_hosted_opening_oracle.py",
)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def test_oracle_uses_manifest_roots_state_pairs_and_edge_games(tmp_path):
    artifact = tmp_path / "graph"
    build_packed_position_graph(corpus(), artifact, source_fingerprint="oracle")
    version, cases = oracle._private_cases(artifact, None, None, None)
    with OpeningReadService(artifact) as service:
        meta = service.metadata()
        root = urlsplit(cases["root"])
        query = parse_qs(root.query)
        assert root.path == f"/api/nodes/{meta['root_node_id']}/neighborhood"
        assert query["state_id"] == [str(meta["root_state_id"])]
        for name in (
            "deep_direct",
            "internal_ending_neighborhood",
            "drop_neighborhood",
        ):
            split = urlsplit(cases[name])
            qs = parse_qs(split.query)
            response = service.neighborhood(
                dataset_version=version,
                anchor_node_id=int(split.path.split("/")[3]),
                anchor_state_id=int(qs["state_id"][0]),
            )
            if name == "internal_ending_neighborhood":
                assert (
                    service.index.state_structure(int(qs["state_id"][0]))[
                        "outgoing_count"
                    ]
                    > 0
                )
                assert (
                    response["state_overlays"][qs["state_id"][0]]["actual_ending_count"]
                    > 0
                )
        assert cases["drop_terminal_games"].startswith("/api/edges/")
        assert cases["internal_ending_games"].startswith("/api/edges/")
    measured = measure_first_load(artifact)
    assert measured["dataset_version"] == version


def test_existing_lifecycle_tool_preserves_graph_artifacts(tmp_path):
    import subprocess, sys, json

    a = tmp_path / "a"
    b = tmp_path / "b"
    build_packed_position_graph(corpus(), a, source_fingerprint="a")
    build_packed_position_graph(corpus()[:-1], b, source_fingerprint="b")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_opening_publication_lifecycle.py",
            str(a),
            str(b),
            str(tmp_path / "pointer.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["artifact_hashes_unchanged"]
    assert report["rollback_build_id"] == report["oracle_build_id"]
    assert not report["pointer_exists_after_removal"]


def test_parity_gate_includes_exact_manifest_serialization(tmp_path):
    import json, runpy, shutil

    verify = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/verify_opening_artifact_parity.py")
    )["verify"]
    a = tmp_path / "a"
    b = tmp_path / "b"
    build_packed_position_graph(corpus(), a, source_fingerprint="manifest-parity")
    shutil.copytree(a, b)
    assert verify([a, b])["exact_all_component_and_manifest_bytes"]
    manifest = json.loads((b / "manifest.json").read_text())
    (b / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
    assert not verify([a, b])["exact_all_component_and_manifest_bytes"]
