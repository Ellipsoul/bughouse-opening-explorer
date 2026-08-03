#!/usr/bin/env python3
"""Measure correction handling as immutable full rebuild/publication/rollback."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import time

from bughouse_explorer.opening.adapter import CrawlerSnapshotAdapter, SnapshotSelection
from bughouse_explorer.opening.packed import build_packed_index
from bughouse_explorer.opening.publication import (
    current_version,
    publish_version,
    validate_artifact,
)
from bughouse_explorer.opening.relational import build_relational_index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("original_artifact", type=Path)
    parser.add_argument("corrected_artifact", type=Path)
    parser.add_argument("pointer", type=Path)
    parser.add_argument("--candidate", choices=("relational", "packed-sorted"), required=True)
    parser.add_argument("--sample-modulus", type=int, default=71)
    args = parser.parse_args()
    outcomes = CrawlerSnapshotAdapter(args.snapshot).iter_outcomes(
        SnapshotSelection(args.sample_modulus, 0)
    )
    games = [outcome.game for outcome in outcomes if outcome.game is not None]
    target_index = len(games) // 2
    donor_index = target_index + 1
    original = games[target_index]
    donor = games[donor_index]
    games[target_index] = replace(
        original,
        move_tokens=donor.move_tokens,
        content_hash=f"representative-correction:{original.content_hash}",
    )
    fingerprint = (
        "sha256:04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac;"
        f"rowid-mod-{args.sample_modulus}-0;corrected={original.uuid}"
    )
    started = time.perf_counter()
    if args.candidate == "relational":
        corrected_id = build_relational_index(
            games, args.corrected_artifact, source_fingerprint=fingerprint
        )
    else:
        corrected_id = build_packed_index(
            games,
            args.corrected_artifact,
            source_fingerprint=fingerprint,
            postings="sorted",
        )
    rebuild_seconds = time.perf_counter() - started
    validate_artifact(args.corrected_artifact)
    original_version = publish_version(args.original_artifact, args.pointer)
    started = time.perf_counter()
    publish_version(args.corrected_artifact, args.pointer)
    publication_seconds = time.perf_counter() - started
    started = time.perf_counter()
    publish_version(args.original_artifact, args.pointer)
    rollback_seconds = time.perf_counter() - started
    payload = {
        "candidate": args.candidate,
        "corrected_build_id": corrected_id,
        "corrected_game_uuid": original.uuid,
        "corrected_move_count_from": len(original.move_tokens),
        "corrected_move_count_to": len(donor.move_tokens),
        "games": len(games),
        "original_build_id": original_version.build_id,
        "publication_seconds": publication_seconds,
        "rebuild_seconds": rebuild_seconds,
        "rollback_build_id": current_version(args.pointer).build_id,
        "rollback_seconds": rollback_seconds,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
