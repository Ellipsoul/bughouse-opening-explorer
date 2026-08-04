"""Minimal streaming client for Vercel's digest-addressed deployment files API."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
from urllib.parse import quote


class SimulatedUploadInterruption(KeyboardInterrupt):
    """Raised only by an explicitly configured disposable rehearsal."""


_PULLED_SECRET_PLACEHOLDERS = {
    "(sensitive)",
    "[redacted]",
    "[sensitive]",
}


class VercelFileApi:
    def __init__(
        self,
        token,
        team_id,
        *,
        host="api.vercel.com",
        timeout=300,
        connection_factory=http.client.HTTPSConnection,
        interrupt_path=None,
        interrupt_after_bytes=None,
    ):
        if not token:
            raise ValueError("a server-only Vercel token is required")
        if not team_id:
            raise ValueError("a Vercel team id is required")
        if interrupt_path is not None and (
            not isinstance(interrupt_after_bytes, int) or interrupt_after_bytes <= 0
        ):
            raise ValueError("an interruption byte offset is required")
        self._token = token
        self.team_id = team_id
        self.host = host
        self.timeout = timeout
        self.connection_factory = connection_factory
        self.interrupt_path = interrupt_path
        self.interrupt_after_bytes = interrupt_after_bytes
        self._interrupted = False

    def _connection(self):
        return self.connection_factory(self.host, timeout=self.timeout)

    @property
    def _team_query(self):
        return f"teamId={quote(self.team_id, safe='')}"

    def upload_file(self, source, record):
        """Stream one complete file and return its digest only after HTTP 200."""
        source = Path(source)
        if source.stat().st_size != record["bytes"]:
            raise ValueError(f"upload file size mismatch: {record['path']}")
        connection = self._connection()
        try:
            connection.putrequest("POST", f"/v2/files?{self._team_query}")
            connection.putheader("Authorization", f"Bearer {self._token}")
            connection.putheader("Content-Type", "application/octet-stream")
            connection.putheader("Content-Length", record["bytes"])
            connection.putheader("x-now-digest", record["sha1"])
            connection.putheader("x-now-size", record["bytes"])
            connection.endheaders()
            sent = 0
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    connection.send(block)
                    sent += len(block)
                    if (
                        not self._interrupted
                        and record["path"] == self.interrupt_path
                        and sent >= self.interrupt_after_bytes
                    ):
                        self._interrupted = True
                        connection.close()
                        raise SimulatedUploadInterruption(
                            f"interrupted {record['path']} after {sent} bytes"
                        )
            response = connection.getresponse()
            payload = response.read()
            if response.status != 200:
                detail = payload.decode("utf-8", errors="replace")[:500]
                raise RuntimeError(
                    f"Vercel file upload failed with HTTP {response.status}: {detail}"
                )
            return record["sha1"]
        finally:
            connection.close()

    def create_preview(
        self,
        manifest,
        *,
        project,
        name,
        metadata=None,
        environment=None,
        build_environment=None,
        target=None,
        auto_assign_custom_domains=False,
    ):
        """Create a deployment from already acknowledged file digests."""
        if target not in {None, "production"}:
            raise ValueError("deployment target must be omitted or production")
        for boundary, values in (
            ("deployment", environment or {}),
            ("build", build_environment or {}),
        ):
            for key, value in values.items():
                if str(value).strip().lower() in _PULLED_SECRET_PLACEHOLDERS:
                    raise ValueError(
                        f"{boundary} environment contains a redaction placeholder: {key}"
                    )
        files = [
            {"file": record["path"], "sha": record["sha1"], "size": record["bytes"]}
            for record in manifest["files"]
        ]
        request = {
            "autoAssignCustomDomains": auto_assign_custom_domains,
            "files": files,
            "env": environment or {},
            "build": {"env": build_environment or {}},
            "meta": metadata or {},
            "name": name,
            "project": project,
        }
        if target is not None:
            request["target"] = target
        body = json.dumps(
            request,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        connection = self._connection()
        try:
            connection.request(
                "POST",
                f"/v13/deployments?{self._team_query}",
                body,
                {
                    "Authorization": f"Bearer {self._token}",
                    "Content-Length": str(len(body)),
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            payload = response.read()
            try:
                result = json.loads(payload or b"{}")
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    f"Vercel deployment returned invalid JSON (HTTP {response.status})"
                ) from error
            if response.status not in {200, 201} or "error" in result:
                error = result.get("error", result)
                raise RuntimeError(
                    f"Vercel Preview creation failed with HTTP {response.status}: {error}"
                )
            return result
        finally:
            connection.close()
