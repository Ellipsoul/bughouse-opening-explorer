#!/usr/bin/env python3
"""Require byte-identical validated graph artifacts, including manifest bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from bughouse_explorer.opening.publication import validate_artifact


def verify(artifacts):
    started = time.monotonic()
    records = []
    for artifact in map(Path, artifacts):
        validated = validate_artifact(artifact)
        manifest_bytes = (artifact / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        # validate_artifact has recomputed every declared component digest.
        components = {
            **manifest["files"],
            "manifest.json": {
                "bytes": len(manifest_bytes),
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            },
        }
        actual = {path.name for path in artifact.iterdir() if path.is_file()}
        if actual != set(components):
            raise ValueError(f"artifact file set differs from its manifest: {artifact}")
        records.append(
            {
                "artifact": str(artifact.resolve()),
                "build_id": validated.build_id,
                "format": manifest["format_version"],
                "components": components,
                "total_bytes": sum(value["bytes"] for value in components.values()),
            }
        )
    equal = all(
        record["components"] == records[0]["components"] for record in records[1:]
    )
    return {
        "exact_all_component_and_manifest_bytes": equal,
        "artifacts": records,
        "validation_seconds": time.monotonic() - started,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path, nargs="+")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if len(args.artifacts) < 2:
        parser.error("at least two artifacts are required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = verify(args.artifacts)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(payload)
    print(payload, end="")
    if not report["exact_all_component_and_manifest_bytes"]:
        raise SystemExit("validated artifacts differ; see parity report")
