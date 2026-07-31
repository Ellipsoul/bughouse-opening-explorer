"""Polite synchronous HTTP boundary for the crawler."""

from __future__ import annotations

from dataclasses import dataclass
import random
import time

import requests


PUB_BASE = "https://api.chess.com/pub"
CALLBACK_BASE = "https://www.chess.com/callback/live/game"


@dataclass(frozen=True)
class FetchResult:
    data: dict | None
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class CrawlerHttpError(RuntimeError):
    """Base class for crawler HTTP failures."""


class DeferredHttpError(CrawlerHttpError):
    """A transient request exhausted its immediate retry budget."""


class PermanentHttpError(CrawlerHttpError):
    """A request failed in a way the job should not immediately retry."""


class PlayerNotFound(PermanentHttpError):
    pass


class CallbackNotFound(PermanentHttpError):
    pass


class ChessComCrawlerClient:
    def __init__(
        self,
        *,
        session=None,
        user_agent,
        min_interval_ms=250,
        max_retries=5,
        sleep=time.sleep,
        monotonic=time.monotonic,
        jitter=lambda: random.uniform(0, 0.1),
    ):
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )
        self.min_interval_ms = min_interval_ms
        self.max_retries = max_retries
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._last_completed = None

    def _pace(self):
        if self._last_completed is None or self.min_interval_ms <= 0:
            return
        elapsed = self._monotonic() - self._last_completed
        remaining = self.min_interval_ms / 1000 - elapsed
        if remaining > 0:
            self._sleep(remaining + self._jitter())

    def _get(self, url, *, headers=None, not_found_error=PermanentHttpError):
        delay = 1.0
        for attempt in range(self.max_retries):
            self._pace()
            try:
                response = self.session.get(url, timeout=30, headers=headers or {})
            except requests.RequestException as exc:
                self._last_completed = self._monotonic()
                if attempt + 1 == self.max_retries:
                    raise DeferredHttpError(f"request failed after retries: {url}") from exc
                self._sleep(delay)
                delay = min(delay * 2, 60)
                continue
            self._last_completed = self._monotonic()
            if response.status_code in (200, 304):
                return response
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt + 1 == self.max_retries:
                    raise DeferredHttpError(
                        f"HTTP {response.status_code} after retries: {url}"
                    )
                wait = float(response.headers.get("Retry-After", delay))
                self._sleep(wait)
                delay = min(delay * 2, 60)
                continue
            if response.status_code == 404:
                raise not_found_error(f"HTTP 404: {url}")
            raise PermanentHttpError(f"HTTP {response.status_code}: {url}")
        raise DeferredHttpError(f"request failed after retries: {url}")

    def get_month(self, username, year, month, *, etag=None, last_modified=None):
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        url = (
            f"{PUB_BASE}/player/{username.strip().lower()}/games/"
            f"{year:04d}/{month:02d}"
        )
        response = self._get(url, headers=headers)
        return FetchResult(
            data=None if response.status_code == 304 else response.json(),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            not_modified=response.status_code == 304,
        )

    def get_archives(self, username):
        normalized = username.strip().lower()
        url = f"{PUB_BASE}/player/{normalized}/games/archives"
        response = self._get(url, not_found_error=PlayerNotFound)
        months = []
        for archive_url in response.json().get("archives", []):
            year, month = archive_url.rstrip("/").split("/")[-2:]
            months.append((int(year), int(month)))
        return sorted(months)

    def get_callback(self, reference):
        response = self._get(
            f"{CALLBACK_BASE}/{reference}", not_found_error=CallbackNotFound
        )
        return response.json()
