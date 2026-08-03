"""Vercel Function configuration for the bounded opening read service."""

import os
from pathlib import Path

from .service import create_opening_service
from .vercel_stage import AUTHORIZED_ARTIFACT_NAME


def _positive_int(environ, name, default):
    raw = environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def create_vercel_app(*, environ=None, project_root=None, factory=create_opening_service):
    """Create the hosted app from server-only settings and a fixed artifact path."""
    environ = os.environ if environ is None else environ
    token = environ.get("OPENING_EXPLORER_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("OPENING_EXPLORER_SERVICE_TOKEN is required")
    max_concurrency = _positive_int(
        environ, "OPENING_EXPLORER_MAX_CONCURRENCY", 8
    )
    wait_ms = _positive_int(
        environ, "OPENING_EXPLORER_CONCURRENCY_WAIT_MS", 50
    )
    root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
    artifact = (root / "artifacts" / "opening" / AUTHORIZED_ARTIFACT_NAME).resolve()
    return factory(
        artifact,
        allowed_origins=(),
        bearer_token=token,
        max_concurrency=max_concurrency,
        concurrency_wait_seconds=wait_ms / 1_000,
    )
