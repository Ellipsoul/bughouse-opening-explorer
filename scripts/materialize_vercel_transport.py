#!/usr/bin/env python3
"""Reconstruct and fully validate a staged opening artifact during a build."""

import argparse
import json
from pathlib import Path
import shutil

from bughouse_explorer.opening.vercel_transport import reconstruct_transport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("chunks", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--minimum-free-headroom-bytes", type=int)
    parser.add_argument("--runtime-attestation", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    required_free = (
        args.minimum_free_headroom_bytes
        if args.minimum_free_headroom_bytes is not None
        else manifest["source_bytes"] * 2
    )
    free_before = shutil.disk_usage(args.chunks).free
    if free_before < required_free:
        raise SystemExit(
            f"insufficient materialization headroom: {free_before} < {required_free}"
        )
    artifact = reconstruct_transport(
        manifest,
        args.chunks,
        args.destination,
        runtime_attestation=args.runtime_attestation,
    )
    runtime_attestation = (
        json.loads(args.runtime_attestation.read_text())
        if args.runtime_attestation is not None
        else None
    )
    print(
        json.dumps(
            {
                "artifact": artifact.as_posix(),
                "dataset_version": manifest["dataset_version"],
                "free_bytes_before": free_before,
                "minimum_free_headroom_bytes": required_free,
                "reconstructed_bytes": manifest["source_bytes"],
                **(
                    {
                        "runtime_attestation": args.runtime_attestation.as_posix(),
                        "runtime_attestation_id": runtime_attestation[
                            "attestation_id"
                        ],
                    }
                    if runtime_attestation is not None
                    else {}
                ),
                "status": "validated",
                "transport_manifest_id": manifest["manifest_id"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
