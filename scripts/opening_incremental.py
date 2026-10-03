#!/usr/bin/env python3
"""Explicit, checked-source bootstrap/update/resume/export/verify operations."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import resource
import sqlite3
import time

from bughouse_explorer.opening.adapter import (
    ADAPTER_POLICY_VERSION,
    CrawlerSnapshotAdapter,
    SnapshotSelection,
)
from bughouse_explorer.opening.incremental import Generation, Revision
from bughouse_explorer.opening.packed import _file_hash
from bughouse_explorer.opening.position_graph_streaming import (
    GRAPH_REPLAY_POLICY_VERSION,
)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "command", choices=["bootstrap", "update", "resume", "export", "verify"]
    )
    parser.add_argument("generation", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--snapshot-sha256")
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--validated-seed", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-modulus", type=int, default=1)
    parser.add_argument("--sample-remainder", type=int, default=0)
    parser.add_argument(
        "--interrupt-after",
        choices=["ingest", "support", "repair", "verify", "complete"],
    )
    args = parser.parse_args()
    started = time.monotonic()
    if args.command in ("export", "verify"):
        gen = Generation(args.generation)
        if args.command == "verify":
            result = gen.verify_complete()
        else:
            if not args.output:
                parser.error("export requires --output")
            result = asdict(gen.export(args.output))
    else:
        if not args.snapshot or not args.snapshot_sha256:
            parser.error("explicit snapshot and SHA-256 required")
        source = args.snapshot.resolve()
        if source.name == "crawler.db" and source.parent.name == "data":
            parser.error("live crawler source is prohibited")
        digest = _file_hash(source)
        if digest != args.snapshot_sha256:
            parser.error("snapshot SHA-256 mismatch")
        with sqlite3.connect(f"{source.as_uri()}?mode=ro&immutable=1", uri=True) as c:
            if (
                c.execute("PRAGMA quick_check").fetchall() != [("ok",)]
                or c.execute("PRAGMA foreign_key_check").fetchone()
            ):
                parser.error("snapshot integrity failure")
        selection = SnapshotSelection(args.sample_modulus, args.sample_remainder)
        fingerprint = (
            f"sha256:{digest};rowid-mod-{selection.rowid_modulus}-{selection.rowid_remainder};"
            f"policy={ADAPTER_POLICY_VERSION};graph=piece-placement-state-context-v1;replay={GRAPH_REPLAY_POLICY_VERSION}"
        )
        if args.command == "resume":
            gen = Generation.open(args.generation, source_fingerprint=fingerprint)
        else:
            if args.command == "update" and not args.parent:
                parser.error("update requires --parent")
            if args.command == "bootstrap" and args.parent:
                parser.error("bootstrap cannot use a parent")
            gen = Generation.create(
                args.generation,
                source_fingerprint=fingerprint,
                parent=Generation(args.parent) if args.parent else None,
            )
        if args.validated_seed:
            print(
                json.dumps({"stage": "validate_and_index_seed", "event": "start"}),
                flush=True,
            )
            gen.configure_seed(args.validated_seed)
        adapter = CrawlerSnapshotAdapter(source)

        def revisions():
            for row in adapter.iter_rows(selection):
                yield Revision.from_row(row, adapter)
            if _file_hash(source) != digest:
                raise ValueError("snapshot changed during source ingestion")

        gen.run(
            revisions(),
            interrupt_after=args.interrupt_after,
            progress=lambda value: print(json.dumps(value, sort_keys=True), flush=True),
        )
        result = gen.verify_complete()
    print(
        json.dumps(
            {
                "result": result,
                "seconds": time.monotonic() - started,
                "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
