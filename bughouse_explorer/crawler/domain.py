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
    return numeric_rating >= threshold and numeric_end_time >= eligibility_cutoff(
        run_started_at
    )


def _sample_key(game, username, year, month, sampler_version):
    value = (
        f"{sampler_version}|{username.lower()}|{year:04d}|{month:02d}|{game['uuid']}"
    )
    return hashlib.blake2b(value.encode(), digest_size=16).digest()


def _pick(games, username, year, month, sampler_version):
    return min(
        games,
        key=lambda game: _sample_key(game, username, year, month, sampler_version),
    )


def select_partner_samples(games, username, year, month, sampler_version=1):
    """Return deterministic callback probes for one player-month."""
    ordered = sorted(games, key=lambda game: (game.get("end_time") or 0, game["uuid"]))
    if len(ordered) <= 4:
        return ordered
    if len(ordered) <= 20:
        split = len(ordered) // 2
        strata = (ordered[:split], ordered[split:])
        return [_pick(s, username, year, month, sampler_version) for s in strata]
    return [_pick(ordered, username, year, month, sampler_version)]
