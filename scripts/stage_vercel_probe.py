#!/usr/bin/env python3
"""Stage only the authorized representative and minimal Function probe."""

import argparse
import json
from pathlib import Path

from bughouse_explorer.opening.vercel_stage import stage_probe_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = stage_probe_bundle(root, args.artifact, args.destination)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
