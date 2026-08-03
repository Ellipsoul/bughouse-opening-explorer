import pytest

from bughouse_explorer.opening.model import QueryFilter
from scripts.benchmark_hosted_opening_service import (
    _percentiles,
    _query_path,
    _reader_duration,
    _request,
)


def test_hosted_benchmark_uses_nearest_rank_percentiles():
    values = list(range(1, 21))

    assert _percentiles(values) == {
        "p50_ms": 10,
        "p95_ms": 19,
        "p99_ms": 20,
    }


def test_hosted_benchmark_parses_reader_timing_and_encodes_filters():
    path = _query_path(
        7,
        query_filter=QueryFilter(
            white_username="name with space",
            black_username="other+name",
        ),
    )

    assert "white=name+with+space" in path
    assert "black=other%2Bname" in path
    assert _reader_duration("edge;dur=2.0, reader;dur=1.125") == 1.125


def test_hosted_benchmark_failure_does_not_log_filter_values():
    class Response:
        status_code = 403

    class Session:
        def get(self, *_args, **_kwargs):
            return Response()

    with pytest.raises(RuntimeError) as error:
        _request(
            Session(),
            "https://example.test",
            "/api/nodes/0/neighborhood?white=private-player",
            None,
        )

    assert str(error.value) == "hosted benchmark request failed with HTTP 403"
    assert "private-player" not in str(error.value)
