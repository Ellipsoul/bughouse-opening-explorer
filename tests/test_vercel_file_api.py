import json

import pytest

from bughouse_explorer.opening.vercel_file_api import VercelFileApi


class _Response:
    def __init__(self, status, payload=b"{}"):
        self.status = status
        self._payload = payload

    def read(self):
        return self._payload


class _Connection:
    def __init__(self, response):
        self.response = response
        self.requests = []
        self.headers = []
        self.sent = bytearray()

    def putrequest(self, method, path):
        self.requests.append((method, path, None))

    def putheader(self, key, value):
        self.headers.append((key.lower(), str(value)))

    def endheaders(self):
        pass

    def send(self, payload):
        self.sent.extend(payload)

    def request(self, method, path, body, headers):
        self.requests.append((method, path, (body, headers)))

    def getresponse(self):
        return self.response

    def close(self):
        pass


def test_file_api_streams_a_digest_addressed_file_without_exposing_the_token(tmp_path):
    source = tmp_path / "part.bin"
    source.write_bytes(b"abcdef")
    connection = _Connection(_Response(200))
    connection_arguments = []

    def connection_factory(host, *args, **kwargs):
        connection_arguments.append((host, args, kwargs))
        return connection

    client = VercelFileApi(
        "server-only-token",
        "team-id",
        connection_factory=connection_factory,
    )
    record = {
        "bytes": 6,
        "path": "transport/dataset/payload.bin/part-00000000.bin",
        "sha1": "1f8ac10f23c5b5bc1167bda84b833e5c057a77d2",
        "sha256": "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1c5c6dcd93c4721ba1",
    }

    acknowledged = client.upload_file(source, record)

    assert acknowledged == record["sha1"]
    assert connection.requests == [("POST", "/v2/files?teamId=team-id", None)]
    assert ("x-now-digest", record["sha1"]) in connection.headers
    assert ("content-length", "6") in connection.headers
    assert bytes(connection.sent) == b"abcdef"
    assert "server-only-token" not in repr(connection.requests)
    assert connection_arguments == [("api.vercel.com", (), {"timeout": 300})]


def test_file_api_creates_an_unaliased_preview_from_exact_file_references():
    response = {"id": "dpl_preview", "target": None, "url": "preview.vercel.app"}
    connection = _Connection(_Response(200, json.dumps(response).encode()))
    client = VercelFileApi(
        "server-only-token",
        "team-id",
        connection_factory=lambda _host, timeout: connection,
    )
    manifest = {
        "files": [
            {
                "bytes": 6,
                "path": "transport/part.bin",
                "sha1": "1f8ac10f23c5b5bc1167bda84b833e5c057a77d2",
            }
        ]
    }

    deployment = client.create_preview(
        manifest,
        project="prj_service",
        name="bughouse-opening-explorer-service",
        metadata={"actor": "transport-rehearsal"},
        environment={"OPENING_EXPLORER_SERVICE_TOKEN": "server-only-service-token"},
        build_environment={"VERCEL_SUPPORT_LARGE_FUNCTIONS": "1"},
    )

    _method, path, request = connection.requests[0]
    body = json.loads(request[0])
    assert path == "/v13/deployments?teamId=team-id"
    assert body["autoAssignCustomDomains"] is False
    assert body["env"] == {
        "OPENING_EXPLORER_SERVICE_TOKEN": "server-only-service-token"
    }
    assert body["build"] == {"env": {"VERCEL_SUPPORT_LARGE_FUNCTIONS": "1"}}
    assert "target" not in body
    assert "projectSettings" not in body
    assert "source" not in body
    assert body["project"] == "prj_service"
    assert body["files"] == [
        {
            "file": "transport/part.bin",
            "sha": manifest["files"][0]["sha1"],
            "size": 6,
        }
    ]
    assert deployment == response


def test_file_api_can_target_production_only_when_explicitly_requested():
    response = {"id": "dpl_production", "target": "production"}
    connection = _Connection(_Response(200, json.dumps(response).encode()))
    client = VercelFileApi(
        "server-only-token",
        "team-id",
        connection_factory=lambda _host, timeout: connection,
    )
    manifest = {
        "files": [
            {
                "bytes": 6,
                "path": "transport/part.bin",
                "sha1": "1f8ac10f23c5b5bc1167bda84b833e5c057a77d2",
            }
        ]
    }

    deployment = client.create_preview(
        manifest,
        project="prj_service",
        name="bughouse-opening-explorer-service",
        target="production",
        auto_assign_custom_domains=True,
    )

    body = json.loads(connection.requests[0][2][0])
    assert body["target"] == "production"
    assert body["autoAssignCustomDomains"] is True
    assert deployment == response


def test_file_api_rejects_a_pulled_sensitive_placeholder_before_deployment():
    client = VercelFileApi("server-only-token", "team-id")

    with pytest.raises(ValueError, match="redaction placeholder"):
        client.create_preview(
            {"files": []},
            project="prj_service",
            name="bughouse-opening-explorer-service",
            environment={"OPENING_EXPLORER_SERVICE_TOKEN": "(Sensitive)"},
        )


def test_file_api_rejects_a_pulled_redaction_placeholder_from_build_environment():
    client = VercelFileApi("server-only-token", "team-id")

    with pytest.raises(ValueError, match="redaction placeholder"):
        client.create_preview(
            {"files": []},
            project="prj_service",
            name="bughouse-opening-explorer-service",
            build_environment={"PRIVATE_BUILD_TOKEN": "[REDACTED]"},
        )
