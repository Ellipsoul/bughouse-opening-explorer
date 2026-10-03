#!/usr/bin/env python3
"""Compare a protected hosted reader byte-for-byte with the local artifact."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlencode

import requests
import uvicorn

from bughouse_explorer.opening.service import OpeningReadService, create_opening_service


def _query(node_id, dataset_version, operation="neighborhood", **parameters):
    query = {"dataset_version": dataset_version, **parameters}
    if operation == "neighborhood":
        query.setdefault("target_forward_depth", 5)
        query.setdefault("max_nodes", 500)
        query.setdefault("max_encoded_bytes", 256 * 1024)
    else:
        query.setdefault("limit", 6)
    return f"/api/nodes/{node_id}/{operation}?{urlencode(query)}"


def _private_cases(artifact, deep_node, internal_ending_node, drop_node):
    with OpeningReadService(artifact) as service:
        version = service.dataset_version
        postings = service.index.posting_index
        white = max(
            (key for key in postings if key.startswith("white\0")),
            key=lambda key: (postings[key]["count"], key),
        ).split("\0", 1)[1]
        black = max(
            (key for key in postings if key.startswith("black\0")),
            key=lambda key: (postings[key]["count"], key),
        ).split("\0", 1)[1]
        if service.graph_mode:
            return version, _graph_cases(service, white, black)
        first_game = service.index._game(0)
        if any(value is None for value in (deep_node, internal_ending_node, drop_node)):
            raise ValueError(
                "prefix rollback oracle requires explicit legacy node witnesses"
            )
    bounded = {
        "root": _query(0, version),
        "deep_direct": _query(deep_node, version),
        "internal_ending_neighborhood": _query(internal_ending_node, version),
        "white_filter": _query(0, version, white=white),
        "black_filter": _query(0, version, black=black),
        "exact_pair_filter": _query(
            0,
            version,
            white=first_game["white_username"],
            black=first_game["black_username"],
        ),
        "invalid_player_filter": _query(0, version, white="__missing_player__"),
        "internal_ending_games": _query(
            internal_ending_node, version, operation="games"
        ),
        "drop_terminal_games": _query(drop_node, version, operation="games"),
        "autocomplete": (
            "/api/players?"
            + urlencode(
                {
                    "dataset_version": version,
                    "prefix": white[: max(1, min(3, len(white)))],
                    "limit": 10,
                }
            )
        ),
        "stale_version": _query(0, "stale"),
        "invalid_node": _query(999_999_999, version),
        "hard_node_cap": _query(0, version, max_nodes=4_001),
        "hard_byte_cap": _query(0, version, max_encoded_bytes=512 * 1024 + 1),
    }
    return version, {"metadata": "/api/meta", **bounded}


def _graph_cases(service, white, black):
    """Discover actual state/edge witnesses; public IDs are never assumed stable."""
    index = service.index
    version = service.dataset_version
    root = index.root_state_id

    def neighborhood(state, **parameters):
        node = index.state_structure(state)["node_id"]
        return _query(node, version, state_id=state, **parameters)

    def games(edge):
        return f"/api/edges/{edge}/games?" + urlencode(
            {"dataset_version": version, "limit": 6}
        )

    state = root
    seen = {state}
    for _ in range(12):
        outgoing = index.outgoing_edges(state)
        if not outgoing:
            break
        edge = max(outgoing, key=lambda e: (e["_game_count"], -e["id"]))
        state = edge["child_state_id"]
        if state in seen:
            break
        seen.add(state)
    ending = None
    drop = None
    for edge_id in range(index.manifest["edges"]):
        edge = index._edge(edge_id)
        child = edge[1]
        if drop is None and "@" in index._string(edge[3], edge[4], encoding="utf-8"):
            drop = edge_id
        child_state = index.state_structure(child)
        if (
            ending is None
            and child_state["_ending_count"]
            and child_state["outgoing_count"]
        ):
            examples = service.edge_game_examples(
                dataset_version=version, edge_id=edge_id, limit=1
            )
            if examples["actual_ending_count"]:
                ending = (edge_id, child)
        if ending is not None and drop is not None:
            break
    if ending is None or drop is None:
        raise ValueError("graph oracle requires actual ending and drop witnesses")
    first = index.game(0)
    return {
        "metadata": "/api/meta",
        "root": neighborhood(root),
        "deep_direct": neighborhood(state),
        "internal_ending_neighborhood": neighborhood(ending[1]),
        "internal_ending_games": games(ending[0]),
        "drop_terminal_games": games(drop),
        "drop_neighborhood": neighborhood(index._edge(drop)[1]),
        "white_filter": neighborhood(root, white=white),
        "black_filter": neighborhood(root, black=black),
        "exact_pair_filter": neighborhood(
            root, white=first["white_username"], black=first["black_username"]
        ),
        "invalid_player_filter": neighborhood(root, white="__missing_player__"),
        "autocomplete": "/api/players?"
        + urlencode({"dataset_version": version, "prefix": white[:3], "limit": 10}),
        "stale_version": _query(index.root_position_id, "stale", state_id=root),
        "invalid_node": _query(999999999, version, state_id=root),
        "hard_node_cap": neighborhood(root, max_nodes=4001),
        "hard_byte_cap": neighborhood(root, max_encoded_bytes=512 * 1024 + 1),
    }


def _remote_request(session, base_url, path, headers):
    started = time.perf_counter_ns()
    try:
        response = session.get(
            f"{base_url.rstrip('/')}{path}", headers=headers, timeout=300
        )
    except requests.RequestException as error:
        raise RuntimeError("hosted oracle request failed") from error
    return response, (time.perf_counter_ns() - started) / 1_000_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("base_url")
    parser.add_argument("service_token_file", type=Path)
    parser.add_argument("protection_bypass_token_file", type=Path)
    parser.add_argument("--deep-node", type=int)
    parser.add_argument("--internal-ending-node", type=int)
    parser.add_argument("--drop-node", type=int)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    service_token = args.service_token_file.read_text().strip()
    bypass_token = args.protection_bypass_token_file.read_text().strip()
    if not service_token or not bypass_token:
        parser.error("token files must be non-empty")

    version, cases = _private_cases(
        args.artifact,
        args.deep_node,
        args.internal_ending_node,
        args.drop_node,
    )
    local_app = create_opening_service(args.artifact, bearer_token=service_token)
    local_headers = {"Authorization": f"Bearer {service_token}"}
    remote_headers = {
        **local_headers,
        "x-vercel-protection-bypass": bypass_token,
    }
    report = {
        "cases": {},
        "dataset_version": version,
        "filter_values_in_report": False,
    }
    failures = []
    local_root_etag = None
    remote_root_etag = None
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    local_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(
            local_app,
            host="127.0.0.1",
            log_level="critical",
            access_log=False,
        )
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    for _attempt in range(300):
        if server.started:
            break
        time.sleep(0.01)
    else:
        raise RuntimeError("local oracle server did not start")
    try:
        with requests.Session() as local, requests.Session() as remote:
            for name, path in cases.items():
                local_response, _local_elapsed = _remote_request(
                    local, local_url, path, local_headers
                )
                remote_response, elapsed_ms = _remote_request(
                    remote, args.base_url, path, remote_headers
                )
                body_equal = local_response.content == remote_response.content
                etag_equal = local_response.headers.get(
                    "etag"
                ) == remote_response.headers.get("etag")
                status_equal = local_response.status_code == remote_response.status_code
                report["cases"][name] = {
                    "body_bytes": len(remote_response.content),
                    "body_equal": body_equal,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "etag_equal": etag_equal,
                    "status": remote_response.status_code,
                    "status_equal": status_equal,
                }
                if name == "root":
                    local_root_etag = local_response.headers.get("etag")
                    remote_root_etag = remote_response.headers.get("etag")
                if not (body_equal and status_equal and etag_equal):
                    failures.append(name)

            root_path = cases["root"]
            local_not_modified, _local_elapsed = _remote_request(
                local,
                local_url,
                root_path,
                {**local_headers, "If-None-Match": local_root_etag},
            )
            remote_not_modified, elapsed_ms = _remote_request(
                remote,
                args.base_url,
                root_path,
                {**remote_headers, "If-None-Match": remote_root_etag},
            )
            not_modified_ok = (
                local_not_modified.status_code == remote_not_modified.status_code == 304
                and local_not_modified.content == remote_not_modified.content == b""
                and local_not_modified.headers.get("etag")
                == remote_not_modified.headers.get("etag")
            )
            report["cases"]["root_not_modified"] = {
                "body_bytes": len(remote_not_modified.content),
                "body_equal": local_not_modified.content == remote_not_modified.content,
                "elapsed_ms": round(elapsed_ms, 3),
                "etag_equal": (
                    local_not_modified.headers.get("etag")
                    == remote_not_modified.headers.get("etag")
                ),
                "status": remote_not_modified.status_code,
                "status_equal": not_modified_ok,
            }
            if not not_modified_ok:
                failures.append("root_not_modified")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()

    report["failures"] = failures
    canonical = json.dumps(report, separators=(",", ":"), sort_keys=True).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
