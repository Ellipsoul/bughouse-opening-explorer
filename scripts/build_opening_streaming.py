#!/usr/bin/env python3
"""Build one representative packed version from an explicit checked snapshot."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import time

from bughouse_explorer.opening.adapter import (
    ADAPTER_POLICY_VERSION,
    CrawlerSnapshotAdapter,
    SnapshotSelection,
)
from bughouse_explorer.opening.publication import validate_artifact
from bughouse_explorer.opening.streaming import build_streaming_packed_index


PRODUCTION_POLICY_GAMES = 6_516_478


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--temporary-directory", type=Path, required=True)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--sample-modulus", type=int, required=True)
    parser.add_argument("--sample-remainder", type=int, default=0)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    snapshot = args.snapshot.resolve()
    if not snapshot.is_file():
        parser.error("snapshot must be an explicit existing immutable SQLite file")
    observed_sha256 = _sha256(snapshot)
    if observed_sha256 != args.snapshot_sha256.casefold():
        parser.error(
            f"snapshot SHA-256 mismatch: expected {args.snapshot_sha256}, "
            f"observed {observed_sha256}"
        )
    selection = SnapshotSelection(args.sample_modulus, args.sample_remainder)
    source_fingerprint = (
        f"sha256:{observed_sha256};rowid-mod-{selection.rowid_modulus}-"
        f"{selection.rowid_remainder};policy={ADAPTER_POLICY_VERSION}"
    )

    before_blocks = resource.getrusage(resource.RUSAGE_SELF).ru_oublock
    started = time.perf_counter()
    report = build_streaming_packed_index(
        CrawlerSnapshotAdapter(snapshot).iter_outcomes(selection),
        args.output,
        source_fingerprint=source_fingerprint,
        temporary_directory=args.temporary_directory,
    )
    build_seconds = time.perf_counter() - started
    validation_started = time.perf_counter()
    validated = validate_artifact(args.output)
    validation_seconds = time.perf_counter() - validation_started
    after_blocks = resource.getrusage(resource.RUSAGE_SELF).ru_oublock
    logical_write_bytes = report.temporary_bytes + report.final_bytes
    physical_write_bytes = max(0, after_blocks - before_blocks) * 512
    manifest = json.loads((args.output / "manifest.json").read_text())
    usage = resource.getrusage(resource.RUSAGE_SELF)
    payload = {
        **asdict(report),
        "adapter_policy": ADAPTER_POLICY_VERSION,
        "build_seconds": build_seconds,
        "component_bytes": {
            name: record["bytes"] for name, record in manifest["files"].items()
        },
        "component_hashes": {
            name: record["sha256"] for name, record in manifest["files"].items()
        },
        "games_per_second": report.accepted_games / build_seconds,
        "logical_write_lower_bound_bytes": logical_write_bytes,
        "peak_rss_bytes": usage.ru_maxrss,
        "physical_write_bytes": physical_write_bytes,
        "physical_write_measurement_reliable": physical_write_bytes > 0,
        "projected_full_final_bytes": round(
            report.final_bytes * PRODUCTION_POLICY_GAMES / report.accepted_games
        ),
        "sample_modulus": selection.rowid_modulus,
        "sample_remainder": selection.rowid_remainder,
        "snapshot": str(snapshot),
        "snapshot_sha256": observed_sha256,
        "source_fingerprint": source_fingerprint,
        "validated_build_id": validated.build_id,
        "validation_seconds": validation_seconds,
        "write_measurement_note": (
            "ru_oublock * 512 is reported only when nonzero; logical temporary plus "
            "final bytes remain a lower bound, not a claim about physical amplification"
        ),
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.result:
        if args.result.exists():
            raise FileExistsError(args.result)
        args.result.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
