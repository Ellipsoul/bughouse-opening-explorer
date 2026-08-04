"""Create an auditable minimal Vercel probe bundle from explicit inputs."""

import hashlib
import json
from pathlib import Path
import shutil

from .publication import validate_artifact
from .vercel_transport import validate_transport_manifest


AUTHORIZED_ARTIFACT_NAME = "representative-mod71-v2-a"
PROBE_SOURCE_FILES = (
    "api/compatibility_probe.py",
    "bughouse_explorer/__init__.py",
    "bughouse_explorer/tcn.py",
    "bughouse_explorer/opening/__init__.py",
    "bughouse_explorer/opening/adapter.py",
    "bughouse_explorer/opening/function_probe.py",
    "bughouse_explorer/opening/model.py",
    "bughouse_explorer/opening/packed.py",
    "bughouse_explorer/opening/publication.py",
    "bughouse_explorer/opening/trie.py",
    "vercel.probe.json",
)
SERVICE_SOURCE_FILES = (
    "api/opening_service.py",
    "bughouse_explorer/__init__.py",
    "bughouse_explorer/tcn.py",
    "bughouse_explorer/opening/__init__.py",
    "bughouse_explorer/opening/adapter.py",
    "bughouse_explorer/opening/model.py",
    "bughouse_explorer/opening/packed.py",
    "bughouse_explorer/opening/publication.py",
    "bughouse_explorer/opening/service.py",
    "bughouse_explorer/opening/trie.py",
    "bughouse_explorer/opening/vercel_hosted.py",
    "bughouse_explorer/opening/vercel_stage.py",
    "vercel.service.json",
)
LARGE_PREVIEW_SOURCE_FILES = tuple(
    path for path in SERVICE_SOURCE_FILES if path != "vercel.service.json"
) + (
    "bughouse_explorer/opening/vercel_transport.py",
    "scripts/materialize_vercel_transport.py",
)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha1_sha256(path):
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha1.update(chunk)
            sha256.update(chunk)
    return sha1.hexdigest(), sha256.hexdigest()


def stage_probe_bundle(source_root, artifact, destination):
    source_root = Path(source_root).resolve()
    artifact = Path(artifact).resolve()
    destination = Path(destination).resolve()
    if artifact.name != AUTHORIZED_ARTIFACT_NAME:
        raise ValueError(f"probe artifact must be {AUTHORIZED_ARTIFACT_NAME}")
    validated = validate_artifact(artifact)
    if validated.format != "packed-sorted":
        raise ValueError("probe artifact must use sorted packed postings")
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)

    for relative in PROBE_SOURCE_FILES:
        source = source_root / relative
        target_relative = "vercel.json" if relative == "vercel.probe.json" else relative
        target = destination / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    artifact_target = (
        destination / "artifacts" / "opening" / AUTHORIZED_ARTIFACT_NAME
    )
    shutil.copytree(artifact, artifact_target)
    (destination / ".python-version").write_text("3.12\n")
    (destination / "requirements.txt").write_text(
        "# Compatibility probe uses only Python's standard library.\n"
    )
    (destination / ".vercelignore").write_text(
        "/*\n"
        "!api\n!api/**\n"
        "!artifacts\n!artifacts/opening\n"
        f"!artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}\n"
        f"!artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}/**\n"
        "!bughouse_explorer\n!bughouse_explorer/**\n"
        "!.python-version\n!requirements.txt\n!vercel.json\n"
        "!bundle-manifest.json\n"
    )

    records = []
    for path in sorted(candidate for candidate in destination.rglob("*") if candidate.is_file()):
        relative = path.relative_to(destination).as_posix()
        if path.suffix in {".db", ".sqlite", ".zst"} or "crawler.db" in relative:
            raise ValueError(f"forbidden staged file: {relative}")
        records.append(
            {"bytes": path.stat().st_size, "path": relative, "sha256": _sha256(path)}
        )
    manifest = {
        "artifact_build_id": validated.build_id,
        "artifact_format": validated.format,
        "files": records,
        "total_bytes": sum(record["bytes"] for record in records),
    }
    (destination / "bundle-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def stage_service_bundle(source_root, artifact, destination):
    """Stage the authenticated API and only its fixed representative artifact."""
    source_root = Path(source_root).resolve()
    artifact = Path(artifact).resolve()
    destination = Path(destination).resolve()
    if artifact.name != AUTHORIZED_ARTIFACT_NAME:
        raise ValueError(f"service artifact must be {AUTHORIZED_ARTIFACT_NAME}")
    validated = validate_artifact(artifact)
    if validated.format != "packed-sorted":
        raise ValueError("service artifact must use sorted packed postings")
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)

    for relative in SERVICE_SOURCE_FILES:
        source = source_root / relative
        target_relative = "vercel.json" if relative == "vercel.service.json" else relative
        target = destination / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    artifact_target = destination / "artifacts" / "opening" / AUTHORIZED_ARTIFACT_NAME
    shutil.copytree(artifact, artifact_target)
    (destination / ".python-version").write_text("3.12\n")
    (destination / "requirements.txt").write_text("fastapi==0.141.1\n")
    (destination / ".vercelignore").write_text(
        "/*\n"
        "!api\n!api/**\n"
        "!artifacts\n!artifacts/opening\n"
        f"!artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}\n"
        f"!artifacts/opening/{AUTHORIZED_ARTIFACT_NAME}/**\n"
        "!bughouse_explorer\n!bughouse_explorer/**\n"
        "!.python-version\n!requirements.txt\n!vercel.json\n"
        "!bundle-manifest.json\n"
    )

    records = []
    for path in sorted(
        candidate for candidate in destination.rglob("*") if candidate.is_file()
    ):
        relative = path.relative_to(destination).as_posix()
        if path.suffix in {".db", ".sqlite", ".zst"} or "crawler.db" in relative:
            raise ValueError(f"forbidden staged file: {relative}")
        records.append(
            {"bytes": path.stat().st_size, "path": relative, "sha256": _sha256(path)}
        )
    manifest = {
        "artifact_build_id": validated.build_id,
        "artifact_format": validated.format,
        "files": records,
        "total_bytes": sum(record["bytes"] for record in records),
    }
    (destination / "bundle-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def stage_large_preview_bundle(
    source_root,
    transport_manifest,
    chunks,
    destination,
):
    """Stage only service source and deterministic chunks for remote materialization."""
    validate_transport_manifest(transport_manifest)
    source_root = Path(source_root).resolve()
    chunks = Path(chunks).resolve()
    destination = Path(destination).resolve()
    artifact_name = transport_manifest["artifact_name"]
    if artifact_name not in {
        AUTHORIZED_ARTIFACT_NAME,
        "full-post-qualification-20260802-v2-a",
    }:
        raise ValueError(f"large preview artifact is not authorized: {artifact_name}")
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    try:
        for relative in LARGE_PREVIEW_SOURCE_FILES:
            source = source_root / relative
            target_relative = (
                "api/index.py" if relative == "api/opening_service.py" else relative
            )
            target = destination / target_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        for component in transport_manifest["components"]:
            for part in component["parts"]:
                source = chunks / part["path"]
                if source.stat().st_size != part["bytes"]:
                    raise ValueError(f"transport chunk size mismatch: {part['path']}")
                sha1, sha256 = _sha1_sha256(source)
                if sha1 != part["sha1"] or sha256 != part["sha256"]:
                    raise ValueError(f"transport chunk hash mismatch: {part['path']}")
                target = destination / part["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        (destination / "transport-manifest.json").write_text(
            json.dumps(transport_manifest, indent=2, sort_keys=True) + "\n"
        )
        (destination / ".python-version").write_text("3.12\n")
        artifact_relative = f"artifacts/opening/{artifact_name}"
        (destination / "pyproject.toml").write_text(
            "[project]\n"
            'name = "bughouse-opening-preview"\n'
            'version = "0.0.0"\n'
            'requires-python = ">=3.12"\n'
            'dependencies = ["fastapi==0.141.1"]\n'
        )
        (destination / "public").mkdir()
        (destination / "public" / ".keep").write_text("")
        (destination / "vercel.json").write_text(
            json.dumps(
                {
                    "$schema": "https://openapi.vercel.sh/vercel.json",
                    "buildCommand": (
                        "python -m scripts.materialize_vercel_transport "
                        f"transport-manifest.json . {artifact_relative}"
                    ),
                    "fluid": True,
                    "functions": {
                        "api/index.py": {
                            "excludeFiles": (
                                "{transport/**,transport-manifest.json,"
                                "scripts/materialize_vercel_transport.py}"
                            ),
                            "includeFiles": f"{artifact_relative}/**",
                            "maxDuration": 300,
                        }
                    },
                    "regions": ["iad1"],
                    "rewrites": [
                        {"source": "/(.*)", "destination": "/api/index"}
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (destination / ".vercelignore").write_text(
            "/*\n"
            "!api\n!api/**\n"
            "!bughouse_explorer\n!bughouse_explorer/**\n"
            "!scripts\n!scripts/materialize_vercel_transport.py\n"
            "!transport\n!transport/**\n"
            "!public\n!public/**\n"
            "!.python-version\n!pyproject.toml\n!transport-manifest.json\n"
            "!vercel.json\n!bundle-manifest.json\n"
        )

        records = []
        for path in sorted(
            (candidate for candidate in destination.rglob("*") if candidate.is_file()),
            key=lambda candidate: candidate.relative_to(destination).as_posix(),
        ):
            relative = path.relative_to(destination).as_posix()
            if path.suffix in {".db", ".sqlite", ".zst"} or "crawler.db" in relative:
                raise ValueError(f"forbidden staged file: {relative}")
            sha1, sha256 = _sha1_sha256(path)
            records.append(
                {
                    "bytes": path.stat().st_size,
                    "path": relative,
                    "sha1": sha1,
                    "sha256": sha256,
                }
            )
        manifest = {
            "artifact_name": artifact_name,
            "dataset_version": transport_manifest["dataset_version"],
            "files": records,
            "format": "vercel-staged-source-v1",
            "total_bytes": sum(record["bytes"] for record in records),
            "transport_manifest_id": transport_manifest["manifest_id"],
        }
        manifest["manifest_id"] = hashlib.sha256(
            json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        (destination / "bundle-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
    except BaseException:
        shutil.rmtree(destination)
        raise
    return manifest
