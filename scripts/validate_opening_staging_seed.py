#!/usr/bin/env python3
"""Validate retained materialized staging against every immutable v1 component."""
import argparse, json, time
from pathlib import Path
from bughouse_explorer.opening.incremental import validate_materialized_seed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("staging", type=Path)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    record = validate_materialized_seed(args.staging, args.artifact, args.output)
    print(
        json.dumps(
            {"record": record, "seconds": time.monotonic() - started},
            indent=2,
            sort_keys=True,
        )
    )
