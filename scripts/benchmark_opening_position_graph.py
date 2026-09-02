#!/usr/bin/env python3
"""Benchmark and smoke-check one transposition-aware opening graph artifact."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time

from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.service import OpeningReadService


def _stable_hash(response):
    payload = json.loads(json.dumps(response))
    payload["instrumentation"]["elapsed_microseconds"] = 0
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _summary(values):
    ordered = sorted(values)
    return {
        "maximum_ms": max(ordered),
        "median_ms": statistics.median(ordered),
        "minimum_ms": min(ordered),
        "p95_ms": ordered[int((len(ordered) - 1) * 0.95)],
    }


def _timed_neighborhood(service, *, node_id, state_id, query_filter=None):
    started = time.perf_counter_ns()
    response = service.neighborhood(
        dataset_version=service.dataset_version,
        anchor_node_id=node_id,
        anchor_state_id=state_id,
        query_filter=query_filter,
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    encoded_bytes = len(
        json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
    )
    return response, elapsed_ms, encoded_bytes


def _popular_player(service, seat):
    prefix = f"{seat}\0"
    key = max(
        (key for key in service.index.posting_index if key.startswith(prefix)),
        key=lambda value: (service.index.posting_index[value]["count"], value),
    )
    return key.split("\0", 1)[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be between 1 and 100")
    if args.result and args.result.exists():
        raise FileExistsError(args.result)

    with OpeningReadService(args.artifact) as service:
        if not service.graph_mode:
            parser.error("artifact must use packed-position-graph-v1")
        metadata = service.metadata()
        root_node_id = metadata["root_node_id"]
        root_state_id = metadata["root_state_id"]
        filters = {
            "unfiltered": None,
            "popular_white": QueryFilter(
                white_username=_popular_player(service, "white")
            ),
            "popular_black": QueryFilter(
                black_username=_popular_player(service, "black")
            ),
        }
        cases = {}
        root_response = None
        for name, query_filter in filters.items():
            timings = []
            hashes = []
            encoded_bytes = []
            for _repeat in range(args.repeats):
                response, elapsed_ms, size = _timed_neighborhood(
                    service,
                    node_id=root_node_id,
                    state_id=root_state_id,
                    query_filter=query_filter,
                )
                if name == "unfiltered":
                    root_response = response
                timings.append(elapsed_ms)
                hashes.append(_stable_hash(response))
                encoded_bytes.append(size)
            cases[name] = {
                "deterministic": len(set(hashes)) == 1,
                "encoded_bytes": sorted(set(encoded_bytes)),
                "latency": _summary(timings),
                "returned_edges": len(response["edges"]),
                "returned_nodes": len(response["nodes"]),
                "returned_states": len(response["states"]),
            }

        trace = []
        node_id = root_node_id
        state_id = root_state_id
        seen_states = {state_id}
        for _ply in range(8):
            response = service.neighborhood(
                dataset_version=service.dataset_version,
                anchor_node_id=node_id,
                anchor_state_id=state_id,
                target_forward_depth=1,
                max_nodes=4_000,
                max_encoded_bytes=512 * 1024,
            )
            outgoing = [
                edge
                for edge in response["edges"]
                if edge["parent_state_id"] == state_id
            ]
            if not outgoing:
                break
            edge = max(
                outgoing,
                key=lambda value: (
                    response["edge_overlays"][str(value["id"])]["support"],
                    value["move_label"],
                    -value["id"],
                ),
            )
            trace.append(
                {
                    "edge_id": edge["id"],
                    "move_label": edge["move_label"],
                    "node_id": edge["child_id"],
                    "state_id": edge["child_state_id"],
                    "support": response["edge_overlays"][str(edge["id"])][
                        "support"
                    ],
                }
            )
            node_id = edge["child_id"]
            state_id = edge["child_state_id"]
            if state_id in seen_states:
                break
            seen_states.add(state_id)

        support_one_edge = next(
            (
                edge
                for edge in root_response["edges"]
                if root_response["edge_overlays"][str(edge["id"])]["support"] == 1
            ),
            None,
        )
        source_example = None
        if support_one_edge is not None:
            source_example = service.edge_game_examples(
                dataset_version=service.dataset_version,
                edge_id=support_one_edge["id"],
                limit=1,
            )
            if source_example["total_matching"] != 1:
                raise ValueError("support-one edge did not return exactly one source game")

        payload = {
            "artifact": str(args.artifact.resolve()),
            "cases": cases,
            "dataset_version": service.dataset_version,
            "format_version": metadata["format_version"],
            "mainline": trace,
            "replay_policy": metadata["replay_policy"],
            "root_node_id": root_node_id,
            "root_state_id": root_state_id,
            "source_edge_checked": support_one_edge is not None,
            "startup": service.startup_profile,
            "terminal_policy": metadata["terminal_policy"],
        }

    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.result:
        args.result.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
