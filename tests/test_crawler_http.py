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
        return next(self.responses)


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
