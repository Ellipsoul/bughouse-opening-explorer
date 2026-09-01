#!/usr/bin/env python3
"""Export checked per-game material highs as deterministic static JSON."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from bughouse_explorer.insights.export import export_material_game_highs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export one immutable material game-high insight for the web client."
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--database-sha256", required=True)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="atomically replace an existing checked frontend artifact",
    )
    args = parser.parse_args()

    database = args.database.resolve()
    output = args.output.resolve()
    if not database.is_file():
        parser.error("database must be an existing SQLite insight artifact")
    expected_sha256 = args.database_sha256.casefold()
    observed_sha256 = _sha256(database)
    if observed_sha256 != expected_sha256:
        parser.error(
            f"database SHA-256 mismatch: expected {expected_sha256}, "
            f"observed {observed_sha256}"
        )
    if output.exists() and not args.replace:
        parser.error("output already exists")

    report = export_material_game_highs(database, output, replace=args.replace)
    payload = {
        **asdict(report),
        "database": str(database),
        "database_sha256": observed_sha256,
        "output": str(output),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
