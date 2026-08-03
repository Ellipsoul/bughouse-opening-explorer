#!/usr/bin/env python3
"""Benchmark bounded read strategies against one deterministic packed artifact."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import resource
import statistics
import time
import zlib

from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.service import OpeningReadService


def _percentiles(values):
    ordered = sorted(values)
    return {
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[int((len(ordered) - 1) * 0.95)],
        "p99_ms": ordered[int((len(ordered) - 1) * 0.99)],
    }


def _encoded(response):
    payload = json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
    return len(payload), len(zlib.compress(payload, level=6))


def _stable_hash(response):
    payload = json.loads(json.dumps(response))
    payload["instrumentation"].pop("elapsed_microseconds", None)
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _best_child(response, parent):
    edges = [edge for edge in response["edges"] if edge["parent_id"] == parent]
    return max(
        edges,
        key=lambda edge: (
            response["overlays"][str(edge["child_id"])]["support"],
            edge["move_token"],
        ),
    )["child_id"]


def _mainline(service, version, length=6):
    node = 0
    path = [node]
    for _ in range(length):
        response = service.neighborhood(
            dataset_version=version,
            anchor_node_id=node,
            target_forward_depth=1,
            max_nodes=4_000,
            max_encoded_bytes=512 * 1024,
        )
        children = [edge for edge in response["edges"] if edge["parent_id"] == node]
        if not children:
            break
        node = _best_child(response, node)
        path.append(node)
    return path


def _simulate(service, version, path, *, target_depth, max_nodes, max_bytes, force_each=False):
    nodes = set()
    edges = defaultdict(set)
    requests = response_bytes = compressed_bytes = 0
    returned = 0
    for index, node_id in enumerate(path):
        next_id = path[index + 1] if index + 1 < len(path) else None
        needs_request = force_each or node_id not in nodes or (
            next_id is not None and next_id not in edges[node_id]
        )
        if needs_request:
            response = service.neighborhood(
                dataset_version=version,
                anchor_node_id=node_id,
                target_forward_depth=target_depth,
                max_nodes=max_nodes,
                max_encoded_bytes=max_bytes,
            )
            requests += 1
            encoded, compressed = _encoded(response)
            response_bytes += encoded
            compressed_bytes += compressed
            returned += len(response["nodes"])
            nodes.update(node["id"] for node in response["nodes"])
            for edge in response["edges"]:
                edges[edge["parent_id"]].add(edge["child_id"])
    return {
        "compressed_response_bytes": compressed_bytes,
        "requests": requests,
        "returned_nodes": returned,
        "unique_cached_nodes": len(nodes),
        "unused_prefetched_nodes": len(nodes - set(path)),
        "uncompressed_response_bytes": response_bytes,
    }


def _simulate_browser_policy(service, version, path, *, target_depth, max_nodes, max_bytes):
    nodes = {}
    edges = defaultdict(set)
    frontiers = set()
    foreground_requests = prefetch_requests = 0
    response_bytes = compressed_bytes = returned = 0

    def request(node_id, kind):
        nonlocal foreground_requests, prefetch_requests
        nonlocal response_bytes, compressed_bytes, returned
        response = service.neighborhood(
            dataset_version=version,
            anchor_node_id=node_id,
            target_forward_depth=target_depth,
            max_nodes=max_nodes,
            max_encoded_bytes=max_bytes,
        )
        if kind == "foreground":
            foreground_requests += 1
        else:
            prefetch_requests += 1
        encoded, compressed = _encoded(response)
        response_bytes += encoded
        compressed_bytes += compressed
        returned += len(response["nodes"])
        returned_ids = {node["id"] for node in response["nodes"]}
        nodes.update({node["id"]: node for node in response["nodes"]})
        frontiers.difference_update(returned_ids)
        frontiers.update(frontier["node_id"] for frontier in response["frontiers"])
        for edge in response["edges"]:
            edges[edge["parent_id"]].add(edge["child_id"])

    request(path[0], "foreground")
    for node_id in path:
        if node_id not in nodes:
            request(node_id, "foreground")
        cached_children = sum(child_id in nodes for child_id in edges[node_id])
        if nodes[node_id]["child_count"] and cached_children == 0:
            request(node_id, "foreground")
        elif node_id in frontiers:
            request(node_id, "prefetch")

    return {
        "compressed_response_bytes": compressed_bytes,
        "foreground_requests": foreground_requests,
        "prefetch_requests": prefetch_requests,
        "requests": foreground_requests + prefetch_requests,
        "returned_nodes": returned,
        "unique_cached_nodes": len(nodes),
        "unused_prefetched_nodes": len(set(nodes) - set(path)),
        "uncompressed_response_bytes": response_bytes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    startup_started = time.perf_counter()
    with OpeningReadService(args.artifact) as service:
        startup_ms = (time.perf_counter() - startup_started) * 1_000
        rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        version = service.dataset_version
        mainline = _mainline(service, version)

        posting_records = service.index.posting_index
        white = max(
            (key for key in posting_records if key.startswith("white\0")),
            key=lambda key: (posting_records[key]["count"], key),
        ).split("\0", 1)[1]
        black = max(
            (key for key in posting_records if key.startswith("black\0")),
            key=lambda key: (posting_records[key]["count"], key),
        ).split("\0", 1)[1]
        first_game = service.index._game(0)
        filters = {
            "unfiltered": None,
            "player_as_white": QueryFilter(white_username=white),
            "player_as_black": QueryFilter(black_username=black),
            "exact_pair": QueryFilter(
                white_username=first_game["white_username"],
                black_username=first_game["black_username"],
            ),
        }
        latency = {}
        response_sizes = {}
        determinism = {}
        for name, query_filter in filters.items():
            timings = []
            hashes = []
            for _ in range(args.repeats):
                started = time.perf_counter_ns()
                response = service.neighborhood(
                    dataset_version=version,
                    anchor_node_id=0,
                    query_filter=query_filter,
                )
                timings.append((time.perf_counter_ns() - started) / 1_000_000)
                hashes.append(_stable_hash(response))
            latency[name] = _percentiles(timings)
            encoded, compressed = _encoded(response)
            response_sizes[name] = {
                "compressed_bytes": compressed,
                "encoded_bytes": encoded,
                "frontiers": len(response["frontiers"]),
                "nodes": len(response["nodes"]),
            }
            determinism[name] = len(set(hashes)) == 1

        strategies = {
            "one_node_request_per_move": _simulate(
                service,
                version,
                mainline,
                target_depth=0,
                max_nodes=4_000,
                max_bytes=512 * 1024,
                force_each=True,
            ),
            "fixed_depth_1": _simulate(
                service, version, mainline, target_depth=1, max_nodes=4_000, max_bytes=512 * 1024
            ),
            "fixed_depth_3": _simulate(
                service, version, mainline, target_depth=3, max_nodes=4_000, max_bytes=512 * 1024
            ),
            "fixed_depth_5": _simulate(
                service, version, mainline, target_depth=5, max_nodes=4_000, max_bytes=512 * 1024
            ),
            "adaptive_depth_5": _simulate(
                service, version, mainline, target_depth=5, max_nodes=500, max_bytes=256 * 1024
            ),
            "browser_complete_move_lists_adaptive_depth_5": _simulate_browser_policy(
                service, version, mainline, target_depth=5, max_nodes=500, max_bytes=256 * 1024
            ),
        }
        internal_ending = next(
            node_id
            for node_id in range(service.index.manifest["nodes"])
            if (node := service.index._node(node_id))[5] and node[7]
        )
        drop_node = next(
            child_id
            for node_id in range(service.index.manifest["nodes"])
            for token, child_id in service.index._children(service.index._node(node_id))
            if token[0] in "&-*+="
            and service.index._node(child_id)[1] <= 6
            and service.index._node(child_id)[7]
            and any(
                game["white_result"] == "checkmated"
                or game["black_result"] == "checkmated"
                for game in service.game_examples(
                    dataset_version=version, node_id=child_id, limit=3
                )["games"]
            )
        )
        internal_games = service.game_examples(
            dataset_version=version, node_id=internal_ending, limit=3
        )
        drop_games = service.game_examples(
            dataset_version=version, node_id=drop_node, limit=3
        )
        edge_cases = {
            "internal_actual_ending": {
                "actual_ending_count": internal_games["actual_ending_count"],
                "node_id": internal_ending,
                "returned_examples": len(internal_games["games"]),
                "total_matching": internal_games["total_matching"],
            },
            "retained_short_checkmate_with_drop": {
                "actual_ending_count": drop_games["actual_ending_count"],
                "has_checkmate": any(
                    game["white_result"] == "checkmated"
                    or game["black_result"] == "checkmated"
                    for game in drop_games["games"]
                ),
                "path": service.neighborhood(
                    dataset_version=version,
                    anchor_node_id=drop_node,
                    target_forward_depth=1,
                    max_nodes=100,
                    max_encoded_bytes=64 * 1024,
                )["path"],
                "returned_examples": len(drop_games["games"]),
                "total_matching": drop_games["total_matching"],
            },
        }
        filter_change = service.neighborhood(
            dataset_version=version,
            anchor_node_id=mainline[min(3, len(mainline) - 1)],
            query_filter=filters["player_as_white"],
        )

    payload = {
        "artifact": str(args.artifact.resolve()),
        "dataset_version": version,
        "deterministic_responses": determinism,
        "edge_cases": edge_cases,
        "filter_change_cached_structural_nodes": len(filter_change["nodes"]),
        "latency": latency,
        "mainline_node_ids": mainline,
        "response_sizes": response_sizes,
        "service_incremental_peak_rss_bytes": max(0, rss_after - rss_before),
        "service_startup_ms": startup_ms,
        "strategies": strategies,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.result:
        if args.result.exists():
            raise FileExistsError(args.result)
        args.result.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
