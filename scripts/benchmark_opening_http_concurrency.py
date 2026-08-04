#!/usr/bin/env python3
"""Measure bounded HTTP concurrency for an already-running opening service."""

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def request_once(url, barrier):
    barrier.wait()
    started = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        body = error.read()
        status = error.code
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return {"bytes": len(body), "elapsed_ms": elapsed_ms, "status": status}


def wave(url, concurrency):
    barrier = __import__("threading").Barrier(concurrency)
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(
            executor.map(lambda _index: request_once(url, barrier), range(concurrency))
        )
    elapsed = [result["elapsed_ms"] for result in results]
    statuses = {}
    for result in results:
        statuses[str(result["status"])] = statuses.get(str(result["status"]), 0) + 1
    return {
        "concurrency": concurrency,
        "latency_ms": {
            "max": max(elapsed),
            "mean": statistics.fmean(elapsed),
            "p50": percentile(elapsed, 0.50),
            "p95": percentile(elapsed, 0.95),
            "p99": percentile(elapsed, 0.99),
        },
        "response_bytes": sorted({result["bytes"] for result in results}),
        "statuses": statuses,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("dataset_version")
    parser.add_argument("--levels", default="1,8,32,64")
    parser.add_argument("--waves", type=int, default=3)
    args = parser.parse_args()
    query = urllib.parse.urlencode(
        {
            "dataset_version": args.dataset_version,
            "target_forward_depth": 5,
            "max_nodes": 500,
            "max_encoded_bytes": 262144,
        }
    )
    url = f"{args.base_url.rstrip('/')}/api/nodes/0/neighborhood?{query}"
    levels = [int(value) for value in args.levels.split(",")]
    payload = {
        "dataset_version": args.dataset_version,
        "target": url,
        "waves": [
            wave(url, concurrency)
            for concurrency in levels
            for _iteration in range(args.waves)
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
