#!/usr/bin/env python3
"""Validate monthly source recovery using its explicit recorded run identity."""
import argparse, json
from pathlib import Path
from bughouse_explorer.opening.snapshot_recovery import audit_snapshot
from bughouse_explorer.opening.packed import _file_hash

if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("--run-id", required=True)
    p.add_argument("--sha256", required=True)
    args = p.parse_args()
    if _file_hash(args.snapshot) != args.sha256:
        p.error("source SHA-256 mismatch")
    print(
        json.dumps(audit_snapshot(args.snapshot, args.run_id), indent=2, sort_keys=True)
    )
