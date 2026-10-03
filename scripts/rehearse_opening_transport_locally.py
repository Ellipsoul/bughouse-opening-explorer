#!/usr/bin/env python3
"""Rehearse exact transport, interruption and retry using only local files.

The existing upload journal is exercised with a filesystem receiver. This module
has no HTTP client, hosting credentials, deployment or environment mutation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from bughouse_explorer.opening.vercel_stage import stage_large_preview_bundle
from bughouse_explorer.opening.vercel_transport import (
    create_transport_manifest,
    reconstruct_transport,
    upload_transport_chunks,
    validate_staged_source_files,
    write_transport_chunks,
)


def rehearse(artifact, output):
    artifact, output = Path(artifact).resolve(), Path(output).resolve()
    repository = Path(__file__).resolve().parents[1]
    if output.is_relative_to(repository):
        raise ValueError("transport rehearsal must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    phases = {}

    def timed(name, operation):
        start = time.monotonic()
        print(json.dumps({"stage": name, "event": "start"}), flush=True)
        result = operation()
        phases[name] = time.monotonic() - start
        return result

    manifest = timed("manifest", lambda: create_transport_manifest(artifact))
    repeated = timed("repeat_manifest", lambda: create_transport_manifest(artifact))
    if manifest != repeated:
        raise ValueError("transport manifests are not deterministic")
    (output / "transport-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    timed(
        "write_chunks",
        lambda: write_transport_chunks(artifact, manifest, output / "chunks"),
    )
    parts = [
        part for component in manifest["components"] for part in component["parts"]
    ]
    if len(parts) < 2:
        raise ValueError("interruption rehearsal requires two or more transport parts")
    receive_count = 0

    def receive(source, part):
        target = output / "local-receiver" / part["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1()
        with source.open("rb") as src, target.open("xb") as dst:
            for block in iter(lambda: src.read(8 * 1024 * 1024), b""):
                dst.write(block)
                digest.update(block)
            dst.flush()
            os.fsync(dst.fileno())
        return digest.hexdigest()

    def interrupted(source, part):
        nonlocal receive_count
        receive_count += 1
        if receive_count == 2:
            with (
                source.open("rb") as src,
                (output / "retained-interrupted-receipt.bin").open("xb") as dst,
            ):
                dst.write(src.read(max(1, part["bytes"] // 2)))
                dst.flush()
                os.fsync(dst.fileno())
            raise KeyboardInterrupt("controlled local receiver interruption")
        return receive(source, part)

    start = time.monotonic()
    try:
        upload_transport_chunks(
            manifest, output / "chunks", output / "local-only.journal", interrupted
        )
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("the expected interruption did not occur")
    phases["interrupted_receiver"] = time.monotonic() - start
    transient = True

    def resumed(source, part):
        nonlocal transient
        if transient:
            transient = False
            raise OSError("controlled transient local receiver failure")
        return receive(source, part)

    resumed_result = timed(
        "resume_receiver",
        lambda: upload_transport_chunks(
            manifest,
            output / "chunks",
            output / "local-only.journal",
            resumed,
            sleep=lambda _: None,
        ),
    )
    if resumed_result["chunks_reused"] != 1 or resumed_result["retries"] != 1:
        raise AssertionError(
            "resume did not reuse the acknowledged first part and retry once"
        )

    def unexpected(*_args):
        raise AssertionError(
            "a completed journal unexpectedly attempted another transfer"
        )

    noop = timed(
        "completed_journal_retry",
        lambda: upload_transport_chunks(
            manifest, output / "chunks", output / "local-only.journal", unexpected
        ),
    )
    if noop["chunks_uploaded"] or noop["chunks_reused"] != len(parts):
        raise AssertionError("completed retry was not an exact no-op")
    rebuilt = timed(
        "reconstruct_received_chunks",
        lambda: reconstruct_transport(
            manifest,
            output / "local-receiver",
            output / "reconstructed" / artifact.name,
        ),
    )
    if (rebuilt / "manifest.json").read_bytes() != (
        artifact / "manifest.json"
    ).read_bytes():
        raise AssertionError("reconstructed manifest bytes differ")
    stage = timed(
        "stage_source",
        lambda: stage_large_preview_bundle(
            repository, manifest, output / "chunks", output / "stage"
        ),
    )
    timed(
        "validate_stage", lambda: validate_staged_source_files(stage, output / "stage")
    )
    report = {
        "external_writes": False,
        "artifact": str(artifact),
        "output": str(output),
        "dataset_version": manifest["dataset_version"],
        "manifest_id": manifest["manifest_id"],
        "source_bytes": manifest["source_bytes"],
        "parts": len(parts),
        "stage_bytes": stage["total_bytes"],
        "stage_manifest_id": stage["manifest_id"],
        "phases_seconds": phases,
        "resume": resumed_result,
        "completed_retry": noop,
        "exact_reconstruction": True,
        "retained_partial_bytes": (output / "retained-interrupted-receipt.bin")
        .stat()
        .st_size,
        "free_bytes_after": shutil.disk_usage(output).free,
    }
    (output / "local-rehearsal.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(rehearse(args.artifact, args.output), indent=2, sort_keys=True))
