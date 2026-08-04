#!/usr/bin/env python3
"""Stage an allowlisted chunk source tree for a Vercel remote build."""

import argparse
import json
from pathlib import Path

from bughouse_explorer.opening.vercel_stage import stage_large_preview_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("transport_manifest", type=Path)
    parser.add_argument("chunks", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    try:
        args.destination.resolve().relative_to(repository)
    except ValueError:
        pass
    else:
        parser.error("the generated upload stage must be outside the repository")
    transport_manifest = json.loads(args.transport_manifest.read_text())
    result = stage_large_preview_bundle(
        repository,
        transport_manifest,
        args.chunks,
        args.destination,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
