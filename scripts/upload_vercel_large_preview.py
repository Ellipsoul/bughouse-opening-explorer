#!/usr/bin/env python3
"""Approval-gated upload and optional creation of an unaliased Vercel Preview."""

import argparse
import json
import os
from pathlib import Path

from bughouse_explorer.opening.vercel_file_api import VercelFileApi
from bughouse_explorer.opening.vercel_transport import (
    reuse_staged_source_acknowledgements,
    upload_staged_source_files,
    validate_staged_source_files,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", type=Path)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--estimated-upload-mbps", type=float, default=25.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-manifest-id")
    parser.add_argument("--create-preview", action="store_true")
    parser.add_argument(
        "--target", choices=("preview", "production"), default="preview"
    )
    parser.add_argument(
        "--runtime-env-key",
        action="append",
        default=[],
        help="copy this named process variable into the deployment runtime",
    )
    parser.add_argument(
        "--build-env-key",
        action="append",
        default=[],
        help="copy this named process variable into the deployment build",
    )
    parser.add_argument("--interrupt-path")
    parser.add_argument("--interrupt-after-bytes", type=int)
    parser.add_argument("--reuse-acknowledgements-from-stage", type=Path)
    parser.add_argument("--reuse-acknowledgements-from-journal", type=Path)
    args = parser.parse_args()
    if bool(args.reuse_acknowledgements_from_stage) != bool(
        args.reuse_acknowledgements_from_journal
    ):
        parser.error("both acknowledgement reuse arguments are required together")
    if args.target == "production" and not args.create_preview:
        parser.error("--target production requires --create-preview")
    manifest = json.loads((args.stage / "bundle-manifest.json").read_text())
    validate_staged_source_files(manifest, args.stage)
    expected_seconds = manifest["total_bytes"] * 8 / (
        args.estimated_upload_mbps * 1_000_000
    )
    preflight = {
        "cleanup": {
            "deployment": "delete only the recorded disposable Preview after approval",
            "credentials": "no new credential is created by this script",
            "source_digest_retention": "undocumented; support answer required",
        },
        "create_preview": args.create_preview,
        "deployment_target": args.target if args.create_preview else None,
        "estimated_upload_mbps": args.estimated_upload_mbps,
        "estimated_upload_seconds_excluding_retries_and_build": expected_seconds,
        "execute": args.execute,
        "file_count": len(manifest["files"]),
        "files": manifest["files"],
        "manifest_id": manifest["manifest_id"],
        "mutations": [
            "upload missing content-addressed source files",
            "create one unaliased Preview" if args.create_preview else "no deployment",
        ],
        "deployment_environment_keys": sorted(set(args.runtime_env_key)),
        "deployment_build_environment_keys": sorted(set(args.build_env_key)),
        "project_id": args.project_id,
        "project_name": args.project_name,
        "rollback": "Production and the retained representative deployment are untouched",
        "reuse_acknowledgements_from": (
            {
                "journal": str(args.reuse_acknowledgements_from_journal),
                "stage": str(args.reuse_acknowledgements_from_stage),
            }
            if args.reuse_acknowledgements_from_stage
            else None
        ),
        "team_id": args.team_id,
        "total_bytes": manifest["total_bytes"],
    }
    if not args.execute:
        print(json.dumps(preflight, indent=2, sort_keys=True))
        return
    if args.confirm_manifest_id != manifest["manifest_id"]:
        parser.error("--execute requires the exact --confirm-manifest-id")
    token = os.environ.get("VERCEL_TOKEN")
    if not token:
        parser.error("VERCEL_TOKEN must be provided server-side for --execute")
    environment = {}
    build_environment = {}
    for key, destination in (
        *((key, environment) for key in args.runtime_env_key),
        *((key, build_environment) for key in args.build_env_key),
    ):
        value = os.environ.get(key)
        if value is None:
            parser.error(f"deployment environment variable is missing: {key}")
        destination[key] = value
    client = VercelFileApi(
        token,
        args.team_id,
        interrupt_path=args.interrupt_path,
        interrupt_after_bytes=args.interrupt_after_bytes,
    )
    reused_acknowledgements = None
    if args.reuse_acknowledgements_from_stage and not args.journal.exists():
        previous_manifest = json.loads(
            (
                args.reuse_acknowledgements_from_stage / "bundle-manifest.json"
            ).read_text()
        )
        reused_acknowledgements = reuse_staged_source_acknowledgements(
            previous_manifest,
            args.reuse_acknowledgements_from_journal,
            manifest,
            args.journal,
        )
    upload = upload_staged_source_files(
        manifest,
        args.stage,
        args.journal,
        client.upload_file,
    )
    result = {
        "preflight": preflight,
        "reused_acknowledgements": reused_acknowledgements,
        "upload": upload,
    }
    if args.create_preview:
        result["deployment"] = client.create_preview(
            manifest,
            project=args.project_id,
            name=args.project_name,
            metadata={
                "actor": "codex-transport",
                "transportManifest": manifest["transport_manifest_id"],
            },
            environment=environment,
            build_environment=build_environment,
            target="production" if args.target == "production" else None,
            auto_assign_custom_domains=args.target == "production",
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
