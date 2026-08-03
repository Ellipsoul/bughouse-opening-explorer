"""Standalone Vercel Function entrypoint for the packed-reader compatibility gate."""

from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bughouse_explorer.opening.function_probe import (
    FunctionCompatibilityProbe,
    report_json,
)


ARTIFACT = Path(
    os.environ.get(
        "OPENING_EXPLORER_ARTIFACT_PATH",
        "artifacts/opening/representative-mod71-v2-a",
    )
)
PROBE = FunctionCompatibilityProbe(ARTIFACT)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/compatibility_probe", "/"}:
            self.send_error(404)
            return
        try:
            reads = int(parse_qs(parsed.query).get("concurrent_reads", ["16"])[0])
            payload = report_json(PROBE, concurrent_reads=reads).encode()
        except (TypeError, ValueError) as error:
            payload = json.dumps(
                {"code": "invalid_request", "detail": str(error)},
                separators=(",", ":"),
            ).encode()
            self.send_response(422)
        else:
            self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "private, no-store")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        # Do not emit request URLs or query values from this compatibility probe.
        return
