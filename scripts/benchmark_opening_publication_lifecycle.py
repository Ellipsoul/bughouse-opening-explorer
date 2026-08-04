#!/usr/bin/env python3
"""Measure local candidate switch, rollback, and pointer-only removal."""

import argparse
import hashlib
import json
from pathlib import Path
import time

from bughouse_explorer.opening.publication import publish_version, remove_version


def component_hashes(artifact):
    hashes = {}
    for path in sorted(Path(artifact).iterdir()):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
            hashes[path.name] = digest.hexdigest()
    return hashes


def timed_publish(artifact, pointer):
    started = time.perf_counter()
    version = publish_version(artifact, pointer)
    return version, time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("oracle", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("pointer", type=Path)
    args = parser.parse_args()
    before = {
        "oracle": component_hashes(args.oracle),
        "candidate": component_hashes(args.candidate),
    }
    oracle, oracle_seconds = timed_publish(args.oracle, args.pointer)
    candidate, candidate_seconds = timed_publish(args.candidate, args.pointer)
    rollback, rollback_seconds = timed_publish(args.oracle, args.pointer)
    removal_started = time.perf_counter()
    removed = remove_version(args.pointer)
    removal_seconds = time.perf_counter() - removal_started
    after = {
        "oracle": component_hashes(args.oracle),
        "candidate": component_hashes(args.candidate),
    }
    print(
        json.dumps(
            {
                "artifact_hashes_unchanged": after == before,
                "candidate_build_id": candidate.build_id,
                "candidate_publish_seconds": candidate_seconds,
                "oracle_build_id": oracle.build_id,
                "oracle_publish_seconds": oracle_seconds,
                "pointer_exists_after_removal": args.pointer.exists(),
                "removal_seconds": removal_seconds,
                "removed": removed,
                "rollback_build_id": rollback.build_id,
                "rollback_seconds": rollback_seconds,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
