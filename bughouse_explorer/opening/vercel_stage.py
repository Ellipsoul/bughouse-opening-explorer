"""Create an auditable minimal Vercel probe bundle from explicit inputs."""

import hashlib
import json
from pathlib import Path
import shutil

from .publication import validate_artifact


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


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
