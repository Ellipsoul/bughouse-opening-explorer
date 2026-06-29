"""Thin, polite client for the chess.com Published-Data API.

Only two endpoints are needed:

* ``GET /pub/player/{username}/games/archives`` -> list of monthly archive URLs.
* ``GET /pub/player/{username}/games/{YYYY}/{MM}`` -> all games for that month.

Requests are serial and carry a descriptive User-Agent (chess.com asks for one). 429 is
retried honoring ``Retry-After``; transient 5xx use capped exponential backoff. 404 raises
a clear :class:`PlayerNotFound`.
"""

import time

import requests

BASE = "https://api.chess.com/pub"
USER_AGENT = "bughouse-downloader/0.1 (https://github.com/Oh-My-Lands/bughouse-opening-toolkit)"


class ApiError(RuntimeError):
    pass


class PlayerNotFound(ApiError):
    pass


class ChessComClient:
    def __init__(self, user_agent=USER_AGENT, max_retries=5, sleep=time.sleep):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self.max_retries = max_retries
        self._sleep = sleep

    def _get(self, url):
        delay = 1.0
        for attempt in range(self.max_retries):
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                raise PlayerNotFound(f"Not found: {url}")
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", delay))
                self._sleep(wait)
                delay = min(delay * 2, 60)
                continue
            if 500 <= resp.status_code < 600:
                self._sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise ApiError(f"HTTP {resp.status_code} for {url}")
        raise ApiError(f"Giving up after {self.max_retries} retries: {url}")

    def get_archive_months(self, username):
        """Return [(year, month), ...] sorted ascending for the player's archives."""
        data = self._get(f"{BASE}/player/{username.lower()}/games/archives")
        months = []
        for url in data.get("archives", []):
            year, month = url.rstrip("/").split("/")[-2:]
            months.append((int(year), int(month)))
        return sorted(months)

    def get_month_games(self, username, year, month):
        """Return the raw list of game records for one month."""
        url = f"{BASE}/player/{username.lower()}/games/{year:04d}/{month:02d}"
        return self._get(url).get("games", [])
