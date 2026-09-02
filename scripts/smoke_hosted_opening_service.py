#!/usr/bin/env python3
"""Verify the hosted opening boundary without printing its bearer token."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

import requests


EXPECTED_DATASET_VERSION = "e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03"


def request(base_url, path, *, token=None, etag=None, protection_bypass=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if etag is not None:
        headers["If-None-Match"] = etag
    if protection_bypass is not None:
        headers["x-vercel-protection-bypass"] = protection_bypass
    started = time.perf_counter_ns()
    response = requests.get(
        f"{base_url.rstrip('/')}{path}", headers=headers, timeout=300
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
    parser.add_argument(
        "--expected-dataset-version", default=EXPECTED_DATASET_VERSION
    )
    parser.add_argument(
        "--artifact-name", default="representative-mod71-v2-a"
    )
    parser.add_argument("--protection-bypass-token-file", type=Path)
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 64:
        parser.error("--concurrency must be between 1 and 64")
    token = args.token_file.read_text().strip()
    if not token:
        parser.error("token file is empty")
    protection_bypass = (
        args.protection_bypass_token_file.read_text().strip()
        if args.protection_bypass_token_file
        else None
    )
    if args.protection_bypass_token_file and not protection_bypass:
        parser.error("protection bypass token file is empty")

    unauthenticated_ready = request(
        args.base_url, "/readyz", protection_bypass=protection_bypass
    )
    readiness = request(
        args.base_url,
        "/readyz",
        token=token,
        protection_bypass=protection_bypass,
    )
    metadata = json.loads(readiness["body"])
    if metadata.get("dataset_version") != args.expected_dataset_version:
        raise SystemExit("hosted readiness returned the wrong dataset version")
    root_node_id = metadata.get("root_node_id", 0)
    root_state_parameter = (
        f"&state_id={metadata['root_state_id']}"
        if "root_state_id" in metadata
        else ""
    )
    meta = request(
        args.base_url,
        "/api/meta",
        token=token,
        protection_bypass=protection_bypass,
    )
    not_modified = request(
        args.base_url,
        "/api/meta",
        token=token,
        etag=meta["etag"],
        protection_bypass=protection_bypass,
    )
    root_path = (
        f"/api/nodes/{root_node_id}/neighborhood"
        f"?dataset_version={args.expected_dataset_version}"
        f"{root_state_parameter}"
        "&target_forward_depth=5&max_nodes=500&max_encoded_bytes=262144"
    )
    root = request(
        args.base_url,
        root_path,
        token=token,
        protection_bypass=protection_bypass,
    )
    stale = request(
        args.base_url,
        f"/api/nodes/{root_node_id}/neighborhood?dataset_version=stale"
        f"{root_state_parameter}&max_nodes=500"
        "&max_encoded_bytes=262144",
        token=token,
        protection_bypass=protection_bypass,
    )
    hidden = request(
        args.base_url,
        f"/artifacts/opening/{args.artifact_name}/manifest.json",
        token=token,
        protection_bypass=protection_bypass,
    )
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        concurrent = list(
            executor.map(
                lambda _index: request(
                    args.base_url,
                    root_path,
                    token=token,
                    protection_bypass=protection_bypass,
                ),
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
    allowed_concurrent_statuses = {200} if args.concurrency <= 8 else {200, 503}
    if (
        any(status not in allowed_concurrent_statuses for status in concurrent_statuses)
        or 200 not in concurrent_statuses
    ):
        failures["concurrency"] = concurrent_statuses
    report = {
        "concurrency": args.concurrency,
        "concurrent_elapsed_ms": sorted(
            round(response["elapsed_ms"], 3) for response in concurrent
        ),
        "concurrent_status_counts": {
            str(status): concurrent_statuses.count(status)
            for status in sorted(set(concurrent_statuses))
        },
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
