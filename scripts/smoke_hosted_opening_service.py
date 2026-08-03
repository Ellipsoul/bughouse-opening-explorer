#!/usr/bin/env python3
"""Verify the hosted opening boundary without printing its bearer token."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

import requests


EXPECTED_DATASET_VERSION = "e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03"


def request(base_url, path, *, token=None, etag=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if etag is not None:
        headers["If-None-Match"] = etag
    started = time.perf_counter_ns()
    response = requests.get(
        f"{base_url.rstrip('/')}{path}", headers=headers, timeout=10
    )
    return {
        "body": response.content,
        "elapsed_ms": (time.perf_counter_ns() - started) / 1_000_000,
        "etag": response.headers.get("etag"),
        "status": response.status_code,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("token_file", type=Path)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 32:
        parser.error("--concurrency must be between 1 and 32")
    token = args.token_file.read_text().strip()
    if not token:
        parser.error("token file is empty")

    unauthenticated_ready = request(args.base_url, "/readyz")
    readiness = request(args.base_url, "/readyz", token=token)
    metadata = json.loads(readiness["body"])
    if metadata.get("dataset_version") != EXPECTED_DATASET_VERSION:
        raise SystemExit("hosted readiness returned the wrong dataset version")
    meta = request(args.base_url, "/api/meta", token=token)
    not_modified = request(
        args.base_url, "/api/meta", token=token, etag=meta["etag"]
    )
    root_path = (
        "/api/nodes/0/neighborhood"
        f"?dataset_version={EXPECTED_DATASET_VERSION}"
        "&target_forward_depth=5&max_nodes=500&max_encoded_bytes=262144"
    )
    root = request(args.base_url, root_path, token=token)
    stale = request(
        args.base_url,
        "/api/nodes/0/neighborhood?dataset_version=stale&max_nodes=500"
        "&max_encoded_bytes=262144",
        token=token,
    )
    hidden = request(
        args.base_url,
        "/artifacts/opening/representative-mod71-v2-a/manifest.json",
        token=token,
    )
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        concurrent = list(
            executor.map(
                lambda _index: request(args.base_url, root_path, token=token),
                range(args.concurrency),
            )
        )

    expected = {
        "unauthenticated_ready": (unauthenticated_ready["status"], 401),
        "readiness": (readiness["status"], 200),
        "meta": (meta["status"], 200),
        "not_modified": (not_modified["status"], 304),
        "root": (root["status"], 200),
        "stale": (stale["status"], 409),
        "hidden_artifact": (hidden["status"], 404),
    }
    failures = {
        name: {"actual": actual, "expected": wanted}
        for name, (actual, wanted) in expected.items()
        if actual != wanted
    }
    concurrent_statuses = [response["status"] for response in concurrent]
    if any(status != 200 for status in concurrent_statuses):
        failures["concurrency"] = concurrent_statuses
    report = {
        "concurrency": args.concurrency,
        "concurrent_elapsed_ms": sorted(
            round(response["elapsed_ms"], 3) for response in concurrent
        ),
        "dataset_version": metadata["dataset_version"],
        "failures": failures,
        "requests": {
            name: {
                "elapsed_ms": round(response["elapsed_ms"], 3),
                "status": response["status"],
            }
            for name, response in (
                ("unauthenticated_ready", unauthenticated_ready),
                ("readiness", readiness),
                ("meta", meta),
                ("not_modified", not_modified),
                ("root", root),
                ("stale", stale),
                ("hidden_artifact", hidden),
            )
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
