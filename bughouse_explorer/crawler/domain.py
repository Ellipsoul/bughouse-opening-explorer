"""Pure crawler policies shared by the worker and tests."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


RATING_THRESHOLD = 2000
ELIGIBILITY_WINDOW_YEARS = 1
BUGHOUSE_START_MONTH = (2016, 1)


def normalize_username(username):
    """Return the case-insensitive identity used by the crawler."""
    return username.strip().lower()


def eligibility_cutoff(run_started_at):
    """Return the Unix timestamp at the run's eligibility-window boundary."""
    if run_started_at.tzinfo is None:
        run_started_at = run_started_at.replace(tzinfo=timezone.utc)
    try:
        cutoff = run_started_at.replace(
            year=run_started_at.year - ELIGIBILITY_WINDOW_YEARS
        )
    except ValueError:  # 29 February -> 28 February in a non-leap cutoff year.
        cutoff = run_started_at.replace(
            year=run_started_at.year - ELIGIBILITY_WINDOW_YEARS, day=28
        )
    return int(cutoff.timestamp())


def eligibility_window(run_started_at):
    """Return the inclusive Unix-timestamp bounds for one fixed evaluation."""
    if run_started_at.tzinfo is None:
        run_started_at = run_started_at.replace(tzinfo=timezone.utc)
    return eligibility_cutoff(run_started_at), int(run_started_at.timestamp())


def is_qualifying_observation(
    rating, end_time, run_started_at, threshold=RATING_THRESHOLD
):
    """Whether a timestamped post-game rating qualifies a player for a full crawl."""
    if rating is None or end_time is None:
        return False
    try:
        numeric_rating = int(rating)
        numeric_end_time = int(end_time)
    except (TypeError, ValueError):
        return False
    lower_bound, upper_bound = eligibility_window(run_started_at)
    return (
        numeric_rating >= threshold
        and lower_bound <= numeric_end_time <= upper_bound
    )


def select_partner_year_sample(games, username, year, sampler_version=2):
    """Choose one deterministic board from an already-filtered player-year."""
    if not games:
        return None
    prefix = f"{sampler_version}|{username.lower()}|{year:04d}|"
    return min(
        games,
        key=lambda game: hashlib.blake2b(
            f"{prefix}{game['uuid']}".encode(), digest_size=16
        ).digest(),
    )
