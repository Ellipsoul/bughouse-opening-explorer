#!/usr/bin/env python3
"""Create or dry-run the deterministic 64-MiB artifact transport."""

import argparse
import json
import os
from pathlib import Path

from bughouse_explorer.opening.vercel_transport import (
    DEFAULT_CHUNK_SIZE,
    create_transport_manifest,
    write_transport_chunks,
)


def _outside_repository(path, repository):
    try:
        path.resolve().relative_to(repository.resolve())
    except ValueError:
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--chunk-directory", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    manifest = create_transport_manifest(args.artifact, chunk_size=args.chunk_size)
    parts = [
        part
        for component in manifest["components"]
        for part in component["parts"]
    ]
    report = {
        "artifact": args.artifact.as_posix(),
        "artifact_name": manifest["artifact_name"],
        "chunk_bytes": sum(part["bytes"] for part in parts),
        "chunk_count": len(parts),
        "components": manifest["components"],
        "dataset_version": manifest["dataset_version"],
        "excluded": [
            "data/**",
            "snapshots/**",
            "**/*.db",
            "**/*.sqlite",
            "**/*.zst",
            "artifacts/opening/full-post-qualification-20260802-v2-b/**",
            "all unrelated artifacts, credentials, raw payloads, and username exports",
        ],
        "local_incremental_temporary_bytes": manifest["source_bytes"] * 2,
        "local_peak_bytes_including_retained_source": manifest["source_bytes"] * 3,
        "manifest_id": manifest["manifest_id"],
        "reconstructed_bytes": manifest["source_bytes"],
        "remote_input_plus_reconstruction_bytes": manifest["temporary_bytes"],
        "source_bytes": manifest["source_bytes"],
        "write_requested": args.write,
    }
    if args.write:
        if args.chunk_directory is None or args.manifest_output is None:
            parser.error("--write requires --chunk-directory and --manifest-output")
        if not _outside_repository(args.chunk_directory, repository):
            parser.error("transport chunks must be outside the repository")
        if not _outside_repository(args.manifest_output, repository):
            parser.error("transport manifest must be outside the repository")
        if args.manifest_output.exists():
            raise FileExistsError(args.manifest_output)
        write_transport_chunks(args.artifact, manifest, args.chunk_directory)
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest_output.open("x") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        report["chunk_directory"] = args.chunk_directory.as_posix()
        report["manifest_output"] = args.manifest_output.as_posix()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
