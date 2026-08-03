#!/usr/bin/env python3
"""Run the Vercel Function compatibility probe without starting a service."""

import argparse
from pathlib import Path

from bughouse_explorer.opening.function_probe import (
    FunctionCompatibilityProbe,
    report_json,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--concurrent-reads", type=int, default=16)
    parser.add_argument("--scratch-directory", type=Path, default=Path("/tmp"))
    args = parser.parse_args()
    with FunctionCompatibilityProbe(
        args.artifact,
        scratch_directory=args.scratch_directory,
    ) as probe:
        print(report_json(probe, concurrent_reads=args.concurrent_reads))


if __name__ == "__main__":
    main()
