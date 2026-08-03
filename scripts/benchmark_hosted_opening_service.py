#!/usr/bin/env python3
"""Benchmark the hosted representative reader without emitting filter values."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode

import requests

from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.service import OpeningReadService


EXPECTED_DATASET_VERSION = "e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03"
MAINLINE_NODE_IDS = [0, 61223, 96218, 114287, 121291, 122739, 123280]


def _percentiles(values):
    ordered = sorted(values)

    def nearest_rank(percentile):
        return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]

    return {
        "p50_ms": round(nearest_rank(0.50), 3),
        "p95_ms": round(nearest_rank(0.95), 3),
        "p99_ms": round(nearest_rank(0.99), 3),
    }


def _reader_duration(header):
    for metric in (header or "").split(","):
        name, *parameters = metric.strip().split(";")
        if name != "reader":
            continue
        for parameter in parameters:
            if parameter.startswith("dur="):
                return float(parameter.removeprefix("dur="))
    return None


def _query_path(node_id, *, game_examples=False, query_filter=None):
    parameters = {"dataset_version": EXPECTED_DATASET_VERSION}
    if game_examples:
        parameters["limit"] = 6
        operation = "games"
    else:
        parameters.update(
            target_forward_depth=5,
            max_nodes=500,
            max_encoded_bytes=256 * 1024,
        )
        operation = "neighborhood"
    if query_filter and query_filter.white_username is not None:
        parameters["white"] = query_filter.white_username
    if query_filter and query_filter.black_username is not None:
        parameters["black"] = query_filter.black_username
    return f"/api/nodes/{node_id}/{operation}?{urlencode(parameters)}"


def _filters(artifact):
    with OpeningReadService(artifact) as service:
        if service.dataset_version != EXPECTED_DATASET_VERSION:
            raise RuntimeError("benchmark artifact is not the authorized dataset version")
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
    return {
        "player_as_white": QueryFilter(white_username=white),
        "player_as_black": QueryFilter(black_username=black),
        "exact_pair": QueryFilter(
            white_username=first_game["white_username"],
            black_username=first_game["black_username"],
        ),
    }


def _request(session, base_url, path, token):
    headers = {"accept": "application/json", "accept-encoding": "gzip"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    started = time.perf_counter_ns()
    response = session.get(
        f"{base_url.rstrip('/')}{path}", headers=headers, timeout=10
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    if not 200 <= response.status_code < 300:
        raise RuntimeError(
            f"hosted benchmark request failed with HTTP {response.status_code}"
        )
    return {
        "body_bytes": len(response.content),
        "elapsed_ms": elapsed_ms,
        "etag": response.headers.get("etag"),
        "reader_ms": _reader_duration(response.headers.get("server-timing")),
        "status": response.status_code,
    }


def _benchmark_case(session, base_url, token, path, repeats):
    samples = [_request(session, base_url, path, token) for _ in range(repeats)]
    reader_values = [sample["reader_ms"] for sample in samples if sample["reader_ms"] is not None]
    return {
        "body_bytes": samples[-1]["body_bytes"],
        "deterministic_etag": len({sample["etag"] for sample in samples}) == 1,
        "end_to_end": _percentiles([sample["elapsed_ms"] for sample in samples]),
        "reader": _percentiles(reader_values) if reader_values else None,
        "requests": len(samples),
        "statuses": sorted({sample["status"] for sample in samples}),
    }


def _trace(session, base_url, token):
    started = time.perf_counter_ns()
    responses = [
        _request(session, base_url, _query_path(node_id), token)
        for node_id in MAINLINE_NODE_IDS
    ]
    return {
        "body_bytes": sum(response["body_bytes"] for response in responses),
        "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
        "node_ids": MAINLINE_NODE_IDS,
        "requests": len(responses),
        "statuses": [response["status"] for response in responses],
    }


def _benchmark_boundary(base_url, token, cases, repeats):
    with requests.Session() as session:
        cold = _request(session, base_url, cases["root_unfiltered"], token)
        measured = {
            name: _benchmark_case(session, base_url, token, path, repeats)
            for name, path in cases.items()
        }
        trace_cold = _trace(session, base_url, token)
        trace_warm = _trace(session, base_url, token)
    return {
        "cold_root": {
            "body_bytes": cold["body_bytes"],
            "elapsed_ms": round(cold["elapsed_ms"], 3),
            "reader_ms": cold["reader_ms"],
            "status": cold["status"],
        },
        "cases": measured,
        "popular_seven_position_trace": {
            "first": trace_cold,
            "second": trace_warm,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("service_base_url")
    parser.add_argument("proxy_base_url")
    parser.add_argument("token_file", type=Path)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument(
        "--skip-proxy",
        action="store_true",
        help="Benchmark only the authenticated service when the proxy requires a browser checkpoint.",
    )
    args = parser.parse_args()
    if not 2 <= args.repeats <= 100:
        parser.error("--repeats must be between 2 and 100")
    if args.result.exists():
        raise FileExistsError(args.result)
    token = args.token_file.read_text().strip()
    if not token:
        parser.error("token file is empty")

    filters = _filters(args.artifact)
    cases = {
        "root_unfiltered": _query_path(0),
        "deep_mainline": _query_path(MAINLINE_NODE_IDS[-1]),
        "player_as_white": _query_path(0, query_filter=filters["player_as_white"]),
        "player_as_black": _query_path(0, query_filter=filters["player_as_black"]),
        "exact_pair": _query_path(0, query_filter=filters["exact_pair"]),
        "internal_actual_ending": _query_path(1907, game_examples=True),
        "retained_drop_checkmate": _query_path(13983, game_examples=True),
    }
    payload = {
        "artifact_component_bytes": 36_782_672,
        "dataset_version": EXPECTED_DATASET_VERSION,
        "filter_values_in_report": False,
        "proxy": (
            {"status": "skipped; measure with a real browser"}
            if args.skip_proxy
            else _benchmark_boundary(args.proxy_base_url, None, cases, args.repeats)
        ),
        "repeats_per_case": args.repeats,
        "service": _benchmark_boundary(args.service_base_url, token, cases, args.repeats),
        "sha256": {},
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    payload["sha256"]["report_without_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    args.result.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
