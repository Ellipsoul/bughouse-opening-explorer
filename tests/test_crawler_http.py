import requests

from bughouse_explorer.crawler.http import ChessComCrawlerClient


class Response:
    def __init__(self, status_code, data=None, headers=None):
        self.status_code = status_code
        self._data = data or {}
        self.headers = headers or {}

    def json(self):
        return self._data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = next(self.responses)
        if isinstance(result, BaseException):
            raise result
        return result


def test_month_fetch_uses_validators_and_reports_not_modified():
    session = Session([Response(304, headers={"ETag": "new-tag"})])
    client = ChessComCrawlerClient(
        session=session,
        user_agent="crawler-test (test@example.com)",
        min_interval_ms=0,
    )

    result = client.get_month(
        "Larso", 2026, 7, etag="old-tag", last_modified="yesterday"
    )

    assert result.not_modified
    assert result.etag == "new-tag"
    assert session.calls == [
        (
            "https://api.chess.com/pub/player/larso/games/2026/07",
            {
                "timeout": 30,
                "headers": {
                    "If-None-Match": "old-tag",
                    "If-Modified-Since": "yesterday",
                },
            },
        )
    ]


def test_transient_failures_honor_retry_after_then_return_games():
    session = Session(
        [
            Response(429, headers={"Retry-After": "0.5"}),
            Response(200, {"games": [{"uuid": "one"}]}),
        ]
    )
    sleeps = []
    client = ChessComCrawlerClient(
        session=session,
        user_agent="crawler-test (test@example.com)",
        min_interval_ms=0,
        sleep=sleeps.append,
        jitter=lambda: 0,
    )

    result = client.get_month("larso", 2026, 7)

    assert result.data == {"games": [{"uuid": "one"}]}
    assert sleeps == [0.5]
    assert len(session.calls) == 2


def test_rate_limit_retry_and_recovery_are_observable():
    session = Session(
        [
            Response(429, headers={"Retry-After": "2"}),
            Response(200, {"games": []}),
        ]
    )
    events = []
    client = ChessComCrawlerClient(
        session=session,
        user_agent="crawler-test (test@example.com)",
        min_interval_ms=0,
        sleep=lambda _seconds: None,
        jitter=lambda: 0,
        observer=events.append,
    )

    client.get_month("larso", 2026, 7)

    assert events[0]["event"] == "http_retry"
    assert events[0]["status"] == 429
    assert events[0]["attempt"] == 1
    assert events[0]["retry_in_seconds"] == 2
    assert events[0]["retry_after"] == "2"
    assert events[1]["event"] == "http_recovered"
    assert events[1]["status"] == 200
    assert events[1]["attempts"] == 2


def test_server_errors_use_exponential_backoff_before_recovery():
    session = Session([Response(503), Response(502), Response(200, {"games": []})])
    sleeps = []
    events = []
    client = ChessComCrawlerClient(
        session=session,
        user_agent="crawler-test (test@example.com)",
        min_interval_ms=0,
        sleep=sleeps.append,
        jitter=lambda: 0,
        observer=events.append,
    )

    client.get_month("larso", 2026, 7)

    assert sleeps == [1.0, 2.0]
    assert [event.get("status") for event in events] == [503, 502, 200]
    assert events[-1]["event"] == "http_recovered"
    assert events[-1]["attempts"] == 3


def test_network_timeout_retry_is_observable():
    session = Session(
        [requests.ReadTimeout("response stalled"), Response(200, {"games": []})]
    )
    events = []
    client = ChessComCrawlerClient(
        session=session,
        user_agent="crawler-test (test@example.com)",
        min_interval_ms=0,
        sleep=lambda _seconds: None,
        jitter=lambda: 0,
        observer=events.append,
    )

    client.get_month("larso", 2026, 7)

    assert events[0]["event"] == "http_retry"
    assert events[0]["status"] is None
    assert events[0]["error_type"] == "ReadTimeout"
    assert events[0]["retry_in_seconds"] == 1.0
    assert events[1]["event"] == "http_recovered"


def test_slow_successful_response_is_observable_without_a_retry():
    session = Session([Response(200, {"games": []})])
    events = []
    clock = iter([0.0, 0.0, 12.0])
    client = ChessComCrawlerClient(
        session=session,
        user_agent="crawler-test (test@example.com)",
        min_interval_ms=0,
        monotonic=lambda: next(clock),
        observer=events.append,
        slow_response_seconds=10,
    )

    client.get_month("larso", 2026, 7)

    assert events == [
        {
            "event": "http_slow",
            "url": "https://api.chess.com/pub/player/larso/games/2026/07",
            "status": 200,
            "attempts": 1,
            "elapsed_ms": 12_000,
        }
    ]


def test_callback_accepts_uuid_partner_references():
    payload = {
        "game": {
            "id": 178381671803,
            "uuid": "d90dc0b9-7fd3-11f1-ac4d-6cfe54652c60",
            "partnerGameId": "d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60",
        }
    }
    session = Session([Response(200, payload)])
    client = ChessComCrawlerClient(
        session=session,
        user_agent="crawler-test (test@example.com)",
        min_interval_ms=0,
    )

    assert client.get_callback(payload["game"]["uuid"]) == payload
    assert session.calls[0][0].endswith(payload["game"]["uuid"])
