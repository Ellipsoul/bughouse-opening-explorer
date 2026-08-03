#!/usr/bin/env python3
"""Measure an exact-prefix trie from an immutable crawler snapshot."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time

from bughouse_explorer.opening.adapter import (
    ADAPTER_POLICY_VERSION,
    InclusionPolicy,
    STANDARD_INITIAL_SETUP,
)
from bughouse_explorer.opening.shape import measure_sorted_token_lines


def _token_lines(rows, progress_every):
    for count, (tcn, uuid) in enumerate(rows, 1):
        if progress_every and count % progress_every == 0:
            print(f"measured {count:,} sorted games", file=sys.stderr, flush=True)
        yield tuple(tcn[offset : offset + 2] for offset in range(0, len(tcn), 2)), uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--progress-every", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    uri = f"file:{args.snapshot.resolve()}?mode=ro&immutable=1"
    started = time.perf_counter()
    with sqlite3.connect(uri, uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA cache_size=-262144")
        policy = InclusionPolicy()
        rows = connection.execute(
            """
            SELECT tcn, uuid
            FROM games AS g
            LEFT JOIN game_participants AS white
              ON white.game_uuid = g.uuid AND white.color = 'white'
            LEFT JOIN game_participants AS black
              ON black.game_uuid = g.uuid AND black.color = 'black'
            WHERE tcn IS NOT NULL
              AND tcn <> ''
              AND rules = 'bughouse'
              AND initial_setup = ?
              AND source IN ('public', 'callback')
              AND length(tcn) / 2 <= ?
              AND (
                length(tcn) / 2 > ?
                OR white.result = 'checkmated'
                OR black.result = 'checkmated'
              )
            ORDER BY tcn, uuid
            """,
            (
                STANDARD_INITIAL_SETUP,
                policy.max_plies,
                policy.max_short_non_checkmate_plies,
            ),
        )
        shape = measure_sorted_token_lines(
            _token_lines(rows, args.progress_every)
        )
        short_non_checkmate = connection.execute(
            """
            SELECT COUNT(*)
            FROM games AS g
            LEFT JOIN game_participants AS white
              ON white.game_uuid = g.uuid AND white.color = 'white'
            LEFT JOIN game_participants AS black
              ON black.game_uuid = g.uuid AND black.color = 'black'
            WHERE g.tcn IS NOT NULL AND g.tcn <> ''
              AND g.rules = 'bughouse' AND g.initial_setup = ?
              AND g.source IN ('public', 'callback')
              AND length(g.tcn) / 2 <= ?
              AND length(g.tcn) / 2 <= ?
              AND COALESCE(white.result, '') <> 'checkmated'
              AND COALESCE(black.result, '') <> 'checkmated'
            """,
            (
                STANDARD_INITIAL_SETUP,
                policy.max_plies,
                policy.max_short_non_checkmate_plies,
            ),
        ).fetchone()[0]
    elapsed = time.perf_counter() - started
    usage = resource.getrusage(resource.RUSAGE_SELF)
    payload = asdict(shape)
    payload.update(
        {
            "accepted_games": shape.games,
            "adapter_policy": ADAPTER_POLICY_VERSION,
            "elapsed_seconds": elapsed,
            "games_per_second": shape.games / elapsed,
            "plies_per_second": shape.plies / elapsed,
            "peak_rss_bytes": usage.ru_maxrss,
            "snapshot": str(args.snapshot.resolve()),
            "skipped": {"short_non_checkmate": short_non_checkmate},
        }
    )
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
