from pathlib import Path

from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.function_probe import FunctionCompatibilityProbe
from bughouse_explorer.opening.streaming import build_streaming_packed_index
from opening_fixtures import corpus


def _artifact(tmp_path):
    artifact = tmp_path / "artifact"
    report = build_streaming_packed_index(
        (
            AdapterOutcome(source_rowid=index, game=opening_game)
            for index, opening_game in enumerate(corpus(), 1)
        ),
        artifact,
        source_fingerprint="function-probe-fixture-v1",
        temporary_directory=tmp_path / "temporary",
    )
    return artifact, report


def test_function_probe_validates_and_reuses_memory_mapped_random_access(tmp_path):
    artifact, report = _artifact(tmp_path)

    with FunctionCompatibilityProbe(
        artifact,
        scratch_directory=tmp_path / "scratch",
        bundle_directory=tmp_path / "bundle",
    ) as probe:
        first = probe.run(concurrent_reads=4)
        second = probe.run(concurrent_reads=4)

    assert first["artifact"]["dataset_version"] == report.build_id
    assert first["artifact"]["format_version"] == "packed-prefix-interval-v2"
    assert first["artifact"]["checksum_validated"] is True
    assert first["mmap"]["concurrent_reads"] == 4
    assert first["mmap"]["failures"] == 0
    assert first["scratch"]["round_trip_validated"] is True
    assert second["instance"]["id"] == first["instance"]["id"]
    assert second["instance"]["invocation_count"] == 2
    assert second["instance"]["reader_reused"] is True


def test_bundle_write_probe_tolerates_read_only_cleanup(monkeypatch, tmp_path):
    artifact, _report = _artifact(tmp_path)

    with FunctionCompatibilityProbe(
        artifact,
        scratch_directory=tmp_path / "scratch",
        bundle_directory=tmp_path / "bundle",
    ) as probe:
        monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(30, "Read-only file system")))
        monkeypatch.setattr(Path, "unlink", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(30, "Read-only file system")))

        assert probe._bundle_write_probe() is False
