from pathlib import Path

import pytest

from bughouse_explorer.opening.vercel_hosted import create_vercel_app


def test_vercel_app_requires_a_server_only_bearer_token(tmp_path):
    with pytest.raises(RuntimeError, match="SERVICE_TOKEN"):
        create_vercel_app(
            environ={}, project_root=tmp_path, factory=lambda *_args, **_kwargs: None
        )


def test_vercel_app_uses_only_fixed_artifact_and_server_proxy_boundary(tmp_path):
    calls = []

    def factory(artifact, **options):
        calls.append((artifact, options))
        return "app"

    app = create_vercel_app(
        environ={
            "OPENING_EXPLORER_SERVICE_TOKEN": "server-secret",
            "OPENING_EXPLORER_MAX_CONCURRENCY": "7",
            "OPENING_EXPLORER_CONCURRENCY_WAIT_MS": "80",
        },
        project_root=tmp_path,
        factory=factory,
    )

    assert app == "app"
    assert calls == [
        (
            Path(tmp_path, "artifacts/opening/representative-mod71-v2-a").resolve(),
            {
                "allowed_origins": (),
                "bearer_token": "server-secret",
                "max_concurrency": 7,
                "concurrency_wait_seconds": 0.08,
            },
        )
    ]


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("OPENING_EXPLORER_MAX_CONCURRENCY", "0"),
        ("OPENING_EXPLORER_MAX_CONCURRENCY", "many"),
        ("OPENING_EXPLORER_CONCURRENCY_WAIT_MS", "0"),
        ("OPENING_EXPLORER_CONCURRENCY_WAIT_MS", "slow"),
    ),
)
def test_vercel_app_rejects_invalid_runtime_budgets(tmp_path, name, value):
    with pytest.raises(RuntimeError, match=name):
        create_vercel_app(
            environ={"OPENING_EXPLORER_SERVICE_TOKEN": "secret", name: value},
            project_root=tmp_path,
            factory=lambda *_args, **_kwargs: None,
        )
