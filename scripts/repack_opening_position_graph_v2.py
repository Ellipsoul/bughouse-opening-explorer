#!/usr/bin/env python3
"""Repack one immutable position-graph v1 artifact as compact v2."""

import argparse
import json
from pathlib import Path
import time

from bughouse_explorer.opening.position_graph_v2 import repack_position_graph_v2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="validated v1 artifact directory")
    parser.add_argument("output", type=Path, help="new, non-existent v2 directory")
    arguments = parser.parse_args()

    started = time.monotonic()
    print(
        f"Repacking {arguments.source} -> {arguments.output}",
        flush=True,
    )
    build_id = repack_position_graph_v2(arguments.source, arguments.output)
    manifest = json.loads((arguments.output / "manifest.json").read_text())
    source_bytes = sum(
        record["bytes"]
        for record in json.loads(
            (arguments.source / "manifest.json").read_text()
        )["files"].values()
    )
    output_bytes = sum(record["bytes"] for record in manifest["files"].values())
    print(
        json.dumps(
            {
                "build_id": build_id,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "format_version": manifest["format_version"],
                "output_bytes": output_bytes,
                "saved_bytes": source_bytes - output_bytes,
                "source_bytes": source_bytes,
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
