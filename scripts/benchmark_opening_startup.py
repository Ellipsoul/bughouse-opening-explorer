#!/usr/bin/env python3
"""Benchmark fresh-process reader startup and sequential first-load requests."""

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time


def _percentiles(values):
    ordered = sorted(values)
    return {
        "p50": statistics.median(ordered),
        "p95": ordered[int((len(ordered) - 1) * 0.95)],
        "p99": ordered[int((len(ordered) - 1) * 0.99)],
    }


def _child(artifact):
    process_started = time.perf_counter_ns()
    import_started = time.perf_counter_ns()
    from bughouse_explorer.opening.startup import measure_first_load
    import_ms = (time.perf_counter_ns() - import_started) / 1_000_000
    measurement = measure_first_load(artifact)
    measurement["process"]["import_ms"] = import_ms
    measurement["process"]["script_to_result_ms"] = (
        time.perf_counter_ns() - process_started
    ) / 1_000_000
    return measurement


def _summarize(samples):
    first = samples[0]
    return {
        "process": {
            key: _percentiles([sample["process"][key] for sample in samples])
            for key in ("cpu_ms", "import_ms", "script_to_result_ms", "peak_rss_bytes")
        },
        "requests": {
            name: {
                "wall_ms": _percentiles(
                    [sample["requests"][name]["wall_ms"] for sample in samples]
                ),
                "scaling": first["requests"][name]["scaling"],
            }
            for name in first["requests"]
        },
        "startup": {
            "total_wall_ms": _percentiles(
                [sample["startup"]["total_wall_ms"] for sample in samples]
            ),
            "phases": {
                name: {
                    "wall_ms": _percentiles(
                        [sample["startup"]["phases"][name]["wall_ms"] for sample in samples]
                    ),
                    "scaling": phase["scaling"],
                }
                for name, phase in first["startup"]["phases"].items()
            },
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        print(json.dumps(_child(args.artifact), separators=(",", ":"), sort_keys=True))
        return
    if args.repeats < 1:
        parser.error("--repeats must be positive")

    samples = []
    for _ in range(args.repeats):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(args.artifact), "--child"],
            check=True,
            capture_output=True,
            text=True,
        )
        samples.append(json.loads(completed.stdout))

    payload = {
        "artifact_component_bytes": samples[0]["startup"]["phases"]["component_checksum"]["bytes"],
        "dataset_version": samples[0]["dataset_version"],
        "fresh_process_repetitions": len(samples),
        "samples": samples,
        "summary": _summarize(samples),
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.result:
        if args.result.exists():
            raise FileExistsError(args.result)
        args.result.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
