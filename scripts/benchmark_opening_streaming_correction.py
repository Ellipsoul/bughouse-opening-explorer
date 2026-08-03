#!/usr/bin/env python3
"""Rebuild one representative correction, publish it, then roll back."""

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import time

from bughouse_explorer.opening.adapter import CrawlerSnapshotAdapter, SnapshotSelection
from bughouse_explorer.opening.publication import current_version, publish_version, validate_artifact
from bughouse_explorer.opening.streaming import build_streaming_packed_index


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("original_artifact", type=Path)
    parser.add_argument("corrected_artifact", type=Path)
    parser.add_argument("pointer", type=Path)
    parser.add_argument("--temporary-directory", type=Path, required=True)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--sample-modulus", type=int, required=True)
    parser.add_argument("--game-uuid", required=True)
    args = parser.parse_args()
    snapshot = args.snapshot.resolve()
    observed = _sha256(snapshot)
    if observed != args.snapshot_sha256.casefold():
        parser.error(f"snapshot SHA-256 mismatch: {observed}")
    corrected_count = 0

    def corrected_outcomes():
        nonlocal corrected_count
        for outcome in CrawlerSnapshotAdapter(snapshot).iter_outcomes(
            SnapshotSelection(args.sample_modulus, 0)
        ):
            if outcome.game is not None and outcome.game.uuid == args.game_uuid:
                corrected_count += 1
                yield replace(
                    outcome,
                    game=replace(
                        outcome.game,
                        content_hash=f"representative-correction:{outcome.game.content_hash}",
                    ),
                )
            else:
                yield outcome

    fingerprint = (
        f"sha256:{observed};rowid-mod-{args.sample_modulus}-0;"
        f"corrected={args.game_uuid}"
    )
    started = time.perf_counter()
    report = build_streaming_packed_index(
        corrected_outcomes(),
        args.corrected_artifact,
        source_fingerprint=fingerprint,
        temporary_directory=args.temporary_directory,
    )
    rebuild_seconds = time.perf_counter() - started
    if corrected_count != 1:
        raise ValueError(f"expected one corrected game, observed {corrected_count}")
    validate_artifact(args.corrected_artifact)
    original = publish_version(args.original_artifact, args.pointer)
    started = time.perf_counter()
    corrected = publish_version(args.corrected_artifact, args.pointer)
    publication_seconds = time.perf_counter() - started
    started = time.perf_counter()
    publish_version(args.original_artifact, args.pointer)
    rollback_seconds = time.perf_counter() - started
    payload = {
        "corrected_build_id": corrected.build_id,
        "corrected_game_uuid": args.game_uuid,
        "original_build_id": original.build_id,
        "publication_seconds": publication_seconds,
        "rebuild": asdict(report),
        "rebuild_seconds": rebuild_seconds,
        "rollback_build_id": current_version(args.pointer).build_id,
        "rollback_seconds": rollback_seconds,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
