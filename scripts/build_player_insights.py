#!/usr/bin/env python3
"""Build the versioned player-insights SQLite database from a checked snapshot."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

from bughouse_explorer.insights.material import build_material_insights


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a new immutable player-insights database from an explicit "
            "checksummed crawler snapshot."
        )
    )
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--progress-interval", type=int, default=100_000)
    args = parser.parse_args()

    snapshot = args.snapshot.resolve()
    output = args.output.resolve()
    if not snapshot.is_file():
        parser.error("snapshot must be an explicit existing immutable SQLite file")
    if args.progress_interval <= 0:
        parser.error("progress interval must be positive")
    expected_sha256 = args.snapshot_sha256.casefold()
    observed_sha256 = _sha256(snapshot)
    if observed_sha256 != expected_sha256:
        parser.error(
            f"snapshot SHA-256 mismatch: expected {expected_sha256}, "
            f"observed {observed_sha256}"
        )
    if output.exists():
        parser.error("output already exists; insight artifacts are immutable")
    if args.result is not None and args.result.exists():
        parser.error("result already exists")

    def report_progress(payload: dict) -> None:
        print(json.dumps({"event": "progress", **payload}, sort_keys=True), file=sys.stderr, flush=True)

    started = time.perf_counter()
    report = build_material_insights(
        snapshot,
        output,
        snapshot_sha256=observed_sha256,
        progress=report_progress,
        progress_interval=args.progress_interval,
    )
    build_seconds = time.perf_counter() - started
    payload = {
        **asdict(report),
        "build_seconds": build_seconds,
        "games_per_second": report.accepted_games / build_seconds,
        "output": str(output),
        "output_bytes": output.stat().st_size,
        "output_sha256": _sha256(output),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "snapshot": str(snapshot),
        "snapshot_sha256": observed_sha256,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.result is not None:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
