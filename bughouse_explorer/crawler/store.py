"""SQLite persistence boundary for crawl state and raw Bughouse games."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import uuid as uuidlib

from .domain import (
    BUGHOUSE_START_MONTH,
    RATING_THRESHOLD,
    eligibility_cutoff,
    is_qualifying_observation,
    normalize_username,
    select_partner_samples,
)
from .migrations import connect
from .records import normalize_callback_game


@dataclass(frozen=True)
class Job:
    id: int
    type: str
    payload: dict
    attempts: int
    max_attempts: int
    run_id: str | None = None


class CrawlerStore:
    def __init__(self, database_path, *, clock=time.time):
        self.database_path = database_path
        self._clock = clock

    def _connection(self):
        return connect(self.database_path)

    def _now(self):
        return int(self._clock())

    @staticmethod
    def _numeric_id(url):
        match = re.search(r"/(\d+)(?:/)?$", url or "")
        return int(match.group(1)) if match else None

    @staticmethod
    def _content_hash(payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _json(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def _ensure_player(self, conn, display_username, source):
        username = normalize_username(display_username)
        now = self._now()
        conn.execute(
            """
            INSERT INTO players
                (username, display_username, discovery_source,
                 discovered_at, last_seen_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (username) DO UPDATE SET
                display_username = excluded.display_username,
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
            """,
            (username, display_username.strip(), source, now, now, now),
        )
        return dict(
            conn.execute(
                "SELECT id, username FROM players WHERE username = ?", (username,)
            ).fetchone()
        )

    def _enqueue(
        self, conn, job_key, job_type, payload, *, max_attempts=5, run_id=None, available_at=None
    ):
        now = self._now()
        conn.execute(
            """
            INSERT INTO crawl_jobs
                (run_id, job_key, type, payload, max_attempts,
                 available_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (job_key) DO NOTHING
            """,
            (
                run_id,
                job_key,
                job_type,
                self._json(payload),
                max_attempts,
                now if available_at is None else int(available_at),
                now,
                now,
            ),
        )

    def seed_usernames(self, usernames):
        """Idempotently register seeds and queue their archive qualification scans."""
        conn = self._connection()
        try:
            with conn:
                for display in usernames:
                    username = normalize_username(display)
                    if not username:
                        continue
                    self._ensure_player(conn, display, "seed")
                    conn.execute(
                        "UPDATE players SET is_seed = 1, updated_at = ? WHERE username = ?",
                        (self._now(), username),
                    )
                    self._enqueue(
                        conn,
                        f"seed:archive:{username}",
                        "archive_list",
                        {"username": username, "mode": "qualify"},
                    )
        finally:
            conn.close()

    def start_run(self, run_type, config=None):
        run_id = str(uuidlib.uuid4())
        now = self._now()
        conn = self._connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO crawl_runs
                        (id, run_type, config, started_at, heartbeat_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, run_type, self._json(config or {}), now, now),
                )
        finally:
            conn.close()
        return run_id

    def heartbeat(self, run_id):
        conn = self._connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE crawl_runs SET heartbeat_at = ? WHERE id = ?",
                    (self._now(), run_id),
                )
        finally:
            conn.close()

    def resume_run(self, run_id):
        conn = self._connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE crawl_runs SET status = 'running', ended_at = NULL,
                        last_error = NULL, heartbeat_at = ? WHERE id = ?
                    """,
                    (self._now(), run_id),
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"unknown crawl run: {run_id}")
                row = conn.execute(
                    """
                    SELECT id, run_type, status, config, counters, started_at,
                           heartbeat_at, ended_at, last_error
                    FROM crawl_runs WHERE id = ?
                    """,
                    (run_id,),
                ).fetchone()
                result = dict(row)
                result["config"] = json.loads(result["config"])
                result["counters"] = json.loads(result["counters"])
                return result
        finally:
            conn.close()

    def assign_job_to_run(self, job_id, run_id):
        if not run_id:
            return
        conn = self._connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE crawl_jobs SET run_id = ?, updated_at = ? WHERE id = ?",
                    (run_id, self._now(), job_id),
                )
        finally:
            conn.close()

    def bump_run_counters(self, run_id, **increments):
        if not run_id or not increments:
            return
        conn = self._connection()
        try:
            with conn:
                row = conn.execute(
                    "SELECT counters FROM crawl_runs WHERE id = ?", (run_id,)
                ).fetchone()
                if not row:
                    return
                counters = json.loads(row["counters"])
                for key, amount in increments.items():
                    counters[key] = counters.get(key, 0) + amount
                conn.execute(
                    "UPDATE crawl_runs SET counters = ?, heartbeat_at = ? WHERE id = ?",
                    (self._json(counters), self._now(), run_id),
                )
        finally:
            conn.close()

    def record_http_event(self, run_id, report):
        """Persist HTTP retry diagnostics and their aggregate run counters."""
        if not run_id:
            return
        event = report["event"]
        status = report.get("status")
        increments = {}
        if event == "http_retry":
            increments["http_retries"] = 1
        elif event == "http_recovered":
            increments["http_recoveries"] = 1
        elif event == "http_slow":
            increments["http_slow_responses"] = 1
        elif event == "http_exhausted":
            increments["http_exhausted"] = 1
        if status == 429:
            increments["http_429s"] = 1
        elif status is not None and 500 <= int(status) < 600:
            increments["http_5xxs"] = 1
        error_type = str(report.get("error_type") or "").lower()
        if "timeout" in error_type:
            increments["http_timeouts"] = 1
        elif error_type:
            increments["http_network_errors"] = 1

        conn = self._connection()
        try:
            with conn:
                row = conn.execute(
                    "SELECT counters FROM crawl_runs WHERE id = ?", (run_id,)
                ).fetchone()
                if not row:
                    return
                counters = json.loads(row["counters"])
                for key, amount in increments.items():
                    counters[key] = counters.get(key, 0) + amount
                conn.execute(
                    "UPDATE crawl_runs SET counters = ?, heartbeat_at = ? WHERE id = ?",
                    (self._json(counters), self._now(), run_id),
                )
                level = (
                    "error" if event == "http_exhausted"
                    else "warning" if event in ("http_retry", "http_slow")
                    else "info"
                )
                conn.execute(
                    """
                    INSERT INTO crawl_events
                        (run_id, job_id, level, event, details, created_at)
                    VALUES (?, NULL, ?, ?, ?, ?)
                    """,
                    (run_id, level, event, self._json(report), self._now()),
                )
        finally:
            conn.close()

    def finish_run(self, run_id, status="complete", error=None):
        conn = self._connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE crawl_runs
                    SET status = ?, ended_at = ?, heartbeat_at = ?, last_error = ?
                    WHERE id = ?
                    """,
                    (status, self._now(), self._now(), error, run_id),
                )
        finally:
            conn.close()

    def status(self):
        conn = self._connection()
        try:
            players = {state: 0 for state in ("candidate", "eligible", "dormant")}
            for row in conn.execute(
                "SELECT state, COUNT(*) AS count FROM players GROUP BY state"
            ):
                players[row["state"]] = row["count"]
            jobs = {
                state: 0
                for state in ("queued", "leased", "deferred", "complete", "failed")
            }
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count FROM crawl_jobs GROUP BY status"
            ):
                jobs[row["status"]] = row["count"]
            games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            partner_links = conn.execute(
                "SELECT COUNT(*) FROM games WHERE partner_uuid IS NOT NULL"
            ).fetchone()[0]
            fully_crawled = conn.execute(
                "SELECT COUNT(*) FROM players "
                "WHERE full_crawl_completed_at IS NOT NULL"
            ).fetchone()[0]
            retries = conn.execute(
                "SELECT COALESCE(SUM(MAX(attempts - 1, 0)), 0) FROM crawl_jobs"
            ).fetchone()[0]
            recent_completed = conn.execute(
                """
                SELECT COUNT(*) FROM crawl_events
                WHERE event = 'job_complete' AND created_at >= ?
                """,
                (self._now() - 300,),
            ).fetchone()[0]
            current_row = conn.execute(
                """
                SELECT id, type, payload, attempts, leased_by, leased_until
                FROM crawl_jobs WHERE status = 'leased'
                ORDER BY updated_at DESC LIMIT 1
                """
            ).fetchone()
            current = dict(current_row) if current_row else None
            if current:
                current["payload"] = json.loads(current["payload"])
            error_row = conn.execute(
                """
                SELECT event, details, created_at FROM crawl_events
                WHERE level = 'error' ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            latest_error = dict(error_row) if error_row else None
            if latest_error:
                latest_error["details"] = json.loads(latest_error["details"])
            run_row = conn.execute(
                """
                SELECT id, run_type, status, counters, started_at, heartbeat_at,
                       ended_at, last_error
                FROM crawl_runs ORDER BY started_at DESC LIMIT 1
                """
            ).fetchone()
            active_run = dict(run_row) if run_row else None
            if active_run:
                active_run["counters"] = json.loads(active_run["counters"])
                request_count = sum(
                    active_run["counters"].get(key, 0)
                    for key in ("public_requests", "callback_requests")
                )
                elapsed = max(
                    1,
                    (active_run["ended_at"] or self._now())
                    - active_run["started_at"],
                )
                active_run["request_rate_per_second"] = request_count / elapsed
            return {
                "players": players,
                "fully_crawled_players": fully_crawled,
                "jobs": jobs,
                "remaining_jobs": jobs["queued"] + jobs["leased"] + jobs["deferred"],
                "retries": retries,
                "recent_jobs_per_hour": recent_completed * 12,
                "games": games,
                "partner_links": partner_links,
                "current": current,
                "latest_error": latest_error,
                "run": active_run,
            }
        finally:
            conn.close()

    def fully_crawled_player_count(self):
        conn = self._connection()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM players "
                "WHERE full_crawl_completed_at IS NOT NULL"
            ).fetchone()[0]
        finally:
            conn.close()

    def lease_job(self, worker_id, *, lease_seconds=300):
        """Atomically lease the next available job and reclaim expired leases."""
        now = self._now()
        conn = self._connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            expired_leases = list(
                conn.execute(
                    """
                    SELECT id, type, payload, attempts FROM crawl_jobs
                    WHERE status = 'leased' AND leased_until < ?
                      AND attempts >= max_attempts
                    """,
                    (now,),
                )
            )
            conn.execute(
                """
                UPDATE crawl_jobs
                SET status = 'queued', attempts = 0, available_at = ?,
                    leased_by = NULL, leased_until = NULL,
                    last_error = 'lease expired; retry budget reset', updated_at = ?
                WHERE status = 'leased' AND leased_until < ?
                  AND attempts >= max_attempts
                """,
                (now, now, now),
            )
            for expired in expired_leases:
                self._set_month_job_status(
                    conn,
                    expired,
                    "queued",
                    "lease expired; retry budget reset",
                    attempts=0,
                )
                self._event(
                    conn,
                    expired["id"],
                    "warning",
                    "lease_retry_budget_reset",
                    {},
                )
            exhausted = list(
                conn.execute(
                    """
                    SELECT id, type, payload, attempts FROM crawl_jobs
                    WHERE attempts >= max_attempts
                      AND status IN ('queued', 'deferred')
                    """
                )
            )
            conn.execute(
                """
                UPDATE crawl_jobs
                SET status = 'failed', last_error = 'retry budget exhausted',
                    updated_at = ?
                WHERE attempts >= max_attempts
                  AND status IN ('queued', 'deferred')
                """,
                (now,),
            )
            for failed in exhausted:
                self._set_month_job_status(
                    conn, failed, "failed", "retry budget exhausted"
                )
            row = conn.execute(
                """
                SELECT id, type, payload, attempts, max_attempts, run_id
                FROM crawl_jobs
                WHERE attempts < max_attempts
                  AND ((status IN ('queued', 'deferred') AND available_at <= ?)
                       OR (status = 'leased' AND leased_until < ?))
                ORDER BY
                    CASE
                        WHEN type = 'month'
                         AND json_extract(payload, '$.mode') IN ('full', 'monthly')
                            THEN 0
                        WHEN type = 'archive_list'
                         AND json_extract(payload, '$.mode') = 'full'
                            THEN 1
                        WHEN type = 'partner_probe' THEN 2
                        ELSE 3
                    END,
                    available_at, id
                LIMIT 1
                """,
                (now, now),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                """
                UPDATE crawl_jobs
                SET status = 'leased', attempts = attempts + 1,
                    leased_by = ?, leased_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (worker_id, now + lease_seconds, now, row["id"]),
            )
            self._set_month_job_status(
                conn, row, "leased", attempts=row["attempts"] + 1
            )
            conn.commit()
            return Job(
                id=row["id"],
                type=row["type"],
                payload=json.loads(row["payload"]),
                attempts=row["attempts"] + 1,
                max_attempts=row["max_attempts"],
                run_id=row["run_id"],
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def complete_job(self, job_id, details=None):
        now = self._now()
        conn = self._connection()
        try:
            with conn:
                job = conn.execute(
                    "SELECT id, type, payload, attempts FROM crawl_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                conn.execute(
                    """
                    UPDATE crawl_jobs
                    SET status = 'complete', leased_by = NULL, leased_until = NULL,
                        completed_at = ?, updated_at = ?, last_error = NULL
                    WHERE id = ?
                    """,
                    (now, now, job_id),
                )
                self._set_month_job_status(conn, job, "complete")
                if details:
                    self._event(conn, job_id, "info", "job_complete", details)
        finally:
            conn.close()

    def defer_job(
        self,
        job_id,
        error,
        *,
        delay_seconds,
        preserve_after_exhaustion=False,
    ):
        now = self._now()
        conn = self._connection()
        try:
            with conn:
                job = conn.execute(
                    """
                    SELECT id, type, payload, attempts, max_attempts
                    FROM crawl_jobs WHERE id = ?
                    """,
                    (job_id,),
                ).fetchone()
                exhausted = bool(
                    job and job["attempts"] >= job["max_attempts"]
                )
                final_status = (
                    "failed" if exhausted and not preserve_after_exhaustion
                    else "deferred"
                )
                max_attempts = (
                    job["max_attempts"] + 5
                    if exhausted and preserve_after_exhaustion
                    else job["max_attempts"]
                )
                conn.execute(
                    """
                    UPDATE crawl_jobs
                    SET status = ?, max_attempts = ?,
                        available_at = ?, leased_by = NULL, leased_until = NULL,
                        last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        final_status,
                        max_attempts,
                        now + delay_seconds,
                        str(error),
                        now,
                        job_id,
                    ),
                )
                self._set_month_job_status(
                    conn, job, final_status, str(error)
                )
                self._event(
                    conn, job_id, "error", f"job_{final_status}",
                    {"error": str(error)},
                )
                return final_status
        finally:
            conn.close()

    def fail_job(self, job_id, error):
        now = self._now()
        conn = self._connection()
        try:
            with conn:
                job = conn.execute(
                    "SELECT id, type, payload, attempts FROM crawl_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                conn.execute(
                    """
                    UPDATE crawl_jobs
                    SET status = 'failed', leased_by = NULL, leased_until = NULL,
                        last_error = ?, updated_at = ? WHERE id = ?
                    """,
                    (str(error), now, job_id),
                )
                self._set_month_job_status(conn, job, "failed", str(error))
                self._event(conn, job_id, "error", "job_failed", {"error": str(error)})
        finally:
            conn.close()

    def _set_month_job_status(
        self, conn, job, status, error=None, *, attempts=None
    ):
        if not job or job["type"] != "month":
            return
        payload = json.loads(job["payload"])
        conn.execute(
            """
            UPDATE player_months
            SET status = ?, attempts = ?, last_error = ?
            WHERE player_id = (SELECT id FROM players WHERE username = ?)
              AND year = ? AND month = ?
            """,
            (
                status,
                job["attempts"] if attempts is None else attempts,
                error,
                normalize_username(payload["username"]),
                int(payload["year"]),
                int(payload["month"]),
            ),
        )

    def _event(self, conn, job_id, level, event, details):
        run = conn.execute(
            "SELECT run_id FROM crawl_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO crawl_events
                (run_id, job_id, level, event, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run["run_id"] if run else None,
                job_id,
                level,
                event,
                self._json(details),
                self._now(),
            ),
        )

    def _observe_public_participant(
        self, conn, game_uuid, color, participant, end_time, run_started_at,
        run_id=None,
    ):
        player = self._ensure_player(conn, participant["username"], "public_game")
        rating = participant.get("rating")
        result = participant.get("result")
        conn.execute(
            """
            INSERT INTO game_participants
                (game_uuid, color, player_id, rating, result, rating_source)
            VALUES (?, ?, ?, ?, ?, 'public')
            ON CONFLICT (game_uuid, color) DO UPDATE SET
                player_id = excluded.player_id, rating = excluded.rating,
                result = excluded.result, rating_source = 'public'
            """,
            (game_uuid, color, player["id"], rating, result),
        )
        if is_qualifying_observation(rating, end_time, run_started_at):
            self._qualify_player(
                conn, player, rating, game_uuid, end_time, run_id=run_id
            )

    def _qualify_player(
        self, conn, player, rating, game_uuid, end_time, *, run_id=None
    ):
        now = self._now()
        previous = conn.execute(
            "SELECT state FROM players WHERE id = ?", (player["id"],)
        ).fetchone()
        conn.execute(
            """
            UPDATE players
            SET state = 'eligible', qualifying_rating = ?,
                qualifying_game_uuid = ?, qualifying_at = ?, updated_at = ?
            WHERE id = ? AND (qualifying_at IS NULL OR qualifying_at <= ?)
            """,
            (rating, game_uuid, end_time, now, player["id"], end_time),
        )
        self._enqueue(
            conn,
            (
                f"reactivate:archive:{player['username']}:{game_uuid}"
                if previous and previous["state"] == "dormant"
                else f"full:archive:{player['username']}"
            ),
            "archive_list",
            {"username": player["username"], "mode": "full"},
            run_id=run_id,
        )

    def save_public_month(
        self,
        username,
        year,
        month,
        games,
        *,
        run_started_at,
        etag=None,
        last_modified=None,
        sampler_version=1,
        run_id=None,
    ):
        """Atomically store one public archive month and enqueue discovered work."""
        bughouse = []
        malformed_games = 0
        for game in games:
            if not isinstance(game, dict) or game.get("rules") != "bughouse":
                continue
            if not game.get("uuid"):
                malformed_games += 1
                continue
            bughouse.append(game)
        owner = normalize_username(username)
        now = self._now()
        conn = self._connection()
        try:
            with conn:
                owner_row = self._ensure_player(conn, username, "archive_owner")
                for game in bughouse:
                    game_uuid = game["uuid"]
                    end_time = game.get("end_time")
                    conn.execute(
                        """
                        INSERT INTO games
                            (uuid, numeric_id, end_time, time_control, time_class,
                             rated, rules, tcn, initial_setup, fen, url, source,
                             raw_payload, content_hash, first_seen_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'bughouse', ?, ?, ?, ?, 'public',
                                ?, ?, ?, ?)
                        ON CONFLICT (uuid) DO UPDATE SET
                            numeric_id = COALESCE(excluded.numeric_id, games.numeric_id),
                            end_time = excluded.end_time,
                            time_control = excluded.time_control,
                            time_class = excluded.time_class,
                            rated = excluded.rated, tcn = excluded.tcn,
                            initial_setup = excluded.initial_setup, fen = excluded.fen,
                            url = excluded.url, source = 'public',
                            raw_payload = excluded.raw_payload,
                            content_hash = excluded.content_hash,
                            updated_at = excluded.updated_at
                        """,
                        (
                            game_uuid,
                            self._numeric_id(game.get("url")),
                            end_time,
                            game.get("time_control"),
                            game.get("time_class"),
                            None if game.get("rated") is None else int(game["rated"]),
                            game.get("tcn"),
                            game.get("initial_setup"),
                            game.get("fen"),
                            game.get("url"),
                            self._json(game),
                            self._content_hash(game),
                            now,
                            now,
                        ),
                    )
                    for color in ("white", "black"):
                        participant = game.get(color)
                        if participant and participant.get("username"):
                            self._observe_public_participant(
                                conn, game_uuid, color, participant,
                                end_time, run_started_at, run_id,
                            )

                samples = select_partner_samples(
                    bughouse, owner, year, month, sampler_version
                )
                for game in samples:
                    numeric_id = self._numeric_id(game.get("url"))
                    reference = str(numeric_id) if numeric_id is not None else game["uuid"]
                    self._enqueue(
                        conn,
                        f"partner:{game['uuid']}",
                        "partner_probe",
                        {
                            "board_uuid": game["uuid"],
                            "reference": reference,
                            "username": owner,
                            "year": year,
                            "month": month,
                            "sampler_version": sampler_version,
                        },
                        max_attempts=4,
                        run_id=run_id,
                    )

                conn.execute(
                    """
                    INSERT INTO player_months
                        (player_id, year, month, status, etag, last_modified,
                         archive_game_count, bughouse_game_count, sampler_version,
                         fetched_at)
                    VALUES (?, ?, ?, 'complete', ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (player_id, year, month) DO UPDATE SET
                        status = 'complete', etag = excluded.etag,
                        last_modified = excluded.last_modified,
                        archive_game_count = excluded.archive_game_count,
                        bughouse_game_count = excluded.bughouse_game_count,
                        sampler_version = excluded.sampler_version,
                        fetched_at = excluded.fetched_at, last_error = NULL
                    """,
                    (
                        owner_row["id"], year, month, etag, last_modified,
                        len(games), len(bughouse), sampler_version, now,
                    ),
                )
                completed_month = f"{year:04d}-{month:02d}"
                conn.execute(
                    """
                    UPDATE players
                    SET latest_month_completed = CASE
                            WHEN latest_month_completed IS NULL
                              OR latest_month_completed < ? THEN ?
                            ELSE latest_month_completed END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (completed_month, completed_month, now, owner_row["id"]),
                )
        finally:
            conn.close()
        result = {
            "archive_games": len(games),
            "bughouse_games": len(bughouse),
            "probes": len(samples),
        }
        if malformed_games:
            result["malformed_games"] = malformed_games
        return result

    def month_cache(self, username, year, month):
        conn = self._connection()
        try:
            row = conn.execute(
                """
                SELECT pm.etag, pm.last_modified, pm.status,
                       pm.attempts, pm.last_error
                FROM player_months pm JOIN players p ON p.id = pm.player_id
                WHERE p.username = ? AND pm.year = ? AND pm.month = ?
                """,
                (normalize_username(username), year, month),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def mark_month_not_modified(self, username, year, month):
        conn = self._connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE player_months SET status = 'complete', fetched_at = ?, last_error = NULL
                    WHERE player_id = (SELECT id FROM players WHERE username = ?)
                      AND year = ? AND month = ?
                    """,
                    (self._now(), normalize_username(username), year, month),
                )
                completed_month = f"{year:04d}-{month:02d}"
                conn.execute(
                    """
                    UPDATE players
                    SET latest_month_completed = CASE
                            WHEN latest_month_completed IS NULL
                              OR latest_month_completed < ? THEN ?
                            ELSE latest_month_completed END,
                        updated_at = ?
                    WHERE username = ?
                    """,
                    (
                        completed_month,
                        completed_month,
                        self._now(),
                        normalize_username(username),
                    ),
                )
        finally:
            conn.close()

    def schedule_archive_months(
        self, username, months, *, mode, run_started_at, run_id=None
    ):
        """Queue either the one-year qualification window or a full lifetime archive."""
        normalized = normalize_username(username)
        selected = [
            archive_month
            for archive_month in sorted(set(months))
            if archive_month >= BUGHOUSE_START_MONTH
        ]
        if mode == "qualify":
            cutoff = datetime.fromtimestamp(
                eligibility_cutoff(run_started_at), tz=timezone.utc
            )
            selected = [m for m in selected if m >= (cutoff.year, cutoff.month)]
            selected.reverse()
        conn = self._connection()
        try:
            with conn:
                player = self._ensure_player(conn, username, "archive_owner")
                for year, month in selected:
                    conn.execute(
                        """
                        INSERT INTO player_months (player_id, year, month, status)
                        VALUES (?, ?, ?, 'queued')
                        ON CONFLICT (player_id, year, month) DO NOTHING
                        """,
                        (player["id"], year, month),
                    )
                    self._enqueue(
                        conn,
                        f"month:{normalized}:{year:04d}-{month:02d}",
                        "month",
                        {
                            "username": normalized,
                            "year": year,
                            "month": month,
                            "mode": mode,
                        },
                        run_id=run_id,
                    )
        finally:
            conn.close()
        return selected

    def discard_pre_bughouse_month_work(self):
        """Remove unfinished legacy work for months before Bughouse existed."""
        start_year, start_month = BUGHOUSE_START_MONTH
        conn = self._connection()
        try:
            with conn:
                jobs = conn.execute(
                    """
                    DELETE FROM crawl_jobs
                    WHERE type = 'month' AND status <> 'complete'
                      AND (
                        CAST(json_extract(payload, '$.year') AS INTEGER) < ?
                        OR (
                          CAST(json_extract(payload, '$.year') AS INTEGER) = ?
                          AND CAST(json_extract(payload, '$.month') AS INTEGER) < ?
                        )
                      )
                    """,
                    (start_year, start_year, start_month),
                ).rowcount
                player_months = conn.execute(
                    """
                    DELETE FROM player_months
                    WHERE status <> 'complete'
                      AND (year < ? OR (year = ? AND month < ?))
                    """,
                    (start_year, start_year, start_month),
                ).rowcount
                return {"jobs": jobs, "player_months": player_months}
        finally:
            conn.close()

    def mark_full_crawl_completed_if_done(self, username):
        normalized = normalize_username(username)
        conn = self._connection()
        try:
            with conn:
                pending = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM player_months pm JOIN players p ON p.id = pm.player_id
                    WHERE p.username = ? AND pm.status <> 'complete'
                    """,
                    (normalized,),
                ).fetchone()[0]
                if pending == 0:
                    conn.execute(
                        """
                        UPDATE players SET full_crawl_completed_at = ?, updated_at = ?
                        WHERE username = ? AND state = 'eligible'
                        """,
                        (self._now(), self._now(), normalized),
                    )
                    return True
                return False
        finally:
            conn.close()

    def reevaluate_dormancy(self, run_started_at):
        """Pause players whose newest qualifying observation left the rolling window."""
        cutoff = eligibility_cutoff(run_started_at)
        conn = self._connection()
        try:
            with conn:
                eligible_before = {
                    row["id"]
                    for row in conn.execute(
                        "SELECT id FROM players WHERE state = 'eligible'"
                    )
                }
                conn.execute(
                    """
                    UPDATE players
                    SET state = CASE WHEN EXISTS (
                            SELECT 1
                            FROM game_participants gp
                            JOIN games g ON g.uuid = gp.game_uuid
                            WHERE gp.player_id = players.id
                              AND gp.rating_source IN ('public', 'callback_pgn')
                              AND gp.rating >= ? AND g.end_time >= ?
                        ) THEN 'eligible' ELSE 'dormant' END,
                        qualifying_rating = (
                            SELECT gp.rating
                            FROM game_participants gp
                            JOIN games g ON g.uuid = gp.game_uuid
                            WHERE gp.player_id = players.id
                              AND gp.rating_source IN ('public', 'callback_pgn')
                              AND gp.rating >= ? AND g.end_time >= ?
                            ORDER BY g.end_time DESC, gp.rating DESC, gp.game_uuid
                            LIMIT 1
                        ),
                        qualifying_game_uuid = (
                            SELECT gp.game_uuid
                            FROM game_participants gp
                            JOIN games g ON g.uuid = gp.game_uuid
                            WHERE gp.player_id = players.id
                              AND gp.rating_source IN ('public', 'callback_pgn')
                              AND gp.rating >= ? AND g.end_time >= ?
                            ORDER BY g.end_time DESC, gp.rating DESC, gp.game_uuid
                            LIMIT 1
                        ),
                        qualifying_at = (
                            SELECT g.end_time
                            FROM game_participants gp
                            JOIN games g ON g.uuid = gp.game_uuid
                            WHERE gp.player_id = players.id
                              AND gp.rating_source IN ('public', 'callback_pgn')
                              AND gp.rating >= ? AND g.end_time >= ?
                            ORDER BY g.end_time DESC, gp.rating DESC, gp.game_uuid
                            LIMIT 1
                        ),
                        updated_at = ?
                    WHERE state IN ('eligible', 'dormant')
                    """,
                    (
                        RATING_THRESHOLD,
                        cutoff,
                        RATING_THRESHOLD,
                        cutoff,
                        RATING_THRESHOLD,
                        cutoff,
                        RATING_THRESHOLD,
                        cutoff,
                        self._now(),
                    ),
                )
                dormant = conn.execute(
                    "SELECT id FROM players WHERE state = 'dormant'"
                ).fetchall()
                dormant_ids = {row["id"] for row in dormant}
                conn.execute(
                    """
                    DELETE FROM crawl_jobs
                    WHERE status <> 'complete'
                      AND type IN ('archive_list', 'month')
                      AND json_extract(payload, '$.username') IN (
                        SELECT username FROM players WHERE state = 'dormant'
                      )
                    """
                )
                conn.execute(
                    """
                    DELETE FROM player_months
                    WHERE status <> 'complete'
                      AND player_id IN (
                        SELECT id FROM players WHERE state = 'dormant'
                      )
                    """
                )
                return len(eligible_before & dormant_ids)
        finally:
            conn.close()

    def queue_current_month_refresh(self, run_started_at, *, run_id=None):
        """Requeue the still-changing UTC calendar month for active players."""
        if run_started_at.tzinfo is None:
            run_started_at = run_started_at.replace(tzinfo=timezone.utc)
        current = run_started_at.astimezone(timezone.utc)
        return self.queue_monthly_refresh(
            current.year, current.month, run_id=run_id
        )

    def queue_monthly_refresh(self, year, month, *, run_id=None):
        """Queue a calendar month for every active eligible player."""
        if (year, month) < BUGHOUSE_START_MONTH:
            return []
        conn = self._connection()
        try:
            with conn:
                rows = list(
                    conn.execute(
                        "SELECT id, username FROM players WHERE state = 'eligible' "
                        "ORDER BY username"
                    )
                )
                for player in rows:
                    conn.execute(
                        """
                        INSERT INTO player_months (player_id, year, month, status)
                        VALUES (?, ?, ?, 'queued')
                        ON CONFLICT (player_id, year, month) DO UPDATE SET
                            status = 'queued', last_error = NULL
                        """,
                        (player["id"], year, month),
                    )
                    now = self._now()
                    payload = self._json(
                        {
                            "username": player["username"],
                            "year": year,
                            "month": month,
                            "mode": "monthly",
                        }
                    )
                    conn.execute(
                        """
                        INSERT INTO crawl_jobs
                            (run_id, job_key, type, payload, max_attempts,
                             available_at, created_at, updated_at)
                        VALUES (?, ?, 'month', ?, 5, ?, ?, ?)
                        ON CONFLICT (job_key) DO UPDATE SET
                            run_id = excluded.run_id, payload = excluded.payload,
                            status = 'queued', attempts = 0,
                            available_at = excluded.available_at,
                            leased_by = NULL, leased_until = NULL,
                            last_error = NULL, completed_at = NULL,
                            updated_at = excluded.updated_at
                        WHERE crawl_jobs.status <> 'leased'
                        """,
                        (
                            run_id,
                            f"refresh:{year:04d}-{month:02d}:{player['username']}",
                            payload,
                            now,
                            now,
                            now,
                        ),
                    )
                return [row["username"] for row in rows]
        finally:
            conn.close()

    def save_callback_game(self, payload, *, run_started_at, run_id=None):
        """Store one callback board and resolve its reciprocal partner when possible."""
        record = normalize_callback_game(payload)
        game_uuid = record["uuid"]
        now = self._now()
        conn = self._connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO games
                        (uuid, numeric_id, partner_reference, end_time, time_control,
                         time_class, rated, rules, tcn, initial_setup, fen, url,
                         source, raw_payload, content_hash, first_seen_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'bughouse', ?, ?, ?, ?,
                            'callback', ?, ?, ?, ?)
                    ON CONFLICT (uuid) DO UPDATE SET
                        numeric_id = COALESCE(games.numeric_id, excluded.numeric_id),
                        partner_reference = COALESCE(excluded.partner_reference,
                                                     games.partner_reference),
                        end_time = COALESCE(games.end_time, excluded.end_time),
                        time_control = COALESCE(games.time_control, excluded.time_control),
                        tcn = COALESCE(games.tcn, excluded.tcn),
                        initial_setup = COALESCE(games.initial_setup, excluded.initial_setup),
                        fen = COALESCE(games.fen, excluded.fen),
                        url = COALESCE(games.url, excluded.url),
                        raw_payload = CASE WHEN games.source = 'public'
                                           THEN games.raw_payload ELSE excluded.raw_payload END,
                        content_hash = CASE WHEN games.source = 'public'
                                            THEN games.content_hash ELSE excluded.content_hash END,
                        updated_at = excluded.updated_at
                    """,
                    (
                        game_uuid,
                        record["numeric_id"],
                        record["partner_reference"],
                        record["end_time"],
                        record["time_control"],
                        record["time_class"],
                        None if record["rated"] is None else int(record["rated"]),
                        record["tcn"],
                        record["initial_setup"],
                        record["fen"],
                        record["url"],
                        self._json(record["raw_payload"]),
                        self._content_hash(record["raw_payload"]),
                        now,
                        now,
                    ),
                )
                for color, participant in record["participants"].items():
                    player = self._ensure_player(
                        conn, participant["username"], "callback_game"
                    )
                    conn.execute(
                        """
                        INSERT INTO game_participants
                            (game_uuid, color, player_id, rating, result, rating_source)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT (game_uuid, color) DO UPDATE SET
                            player_id = excluded.player_id, rating = excluded.rating,
                            result = excluded.result,
                            rating_source = excluded.rating_source
                        WHERE game_participants.rating_source <> 'public'
                        """,
                        (
                            game_uuid, color, player["id"], participant["rating"],
                            participant["result"], participant["rating_source"],
                        ),
                    )
                    if (
                        participant["rating_source"] == "callback_pgn"
                        and is_qualifying_observation(
                            participant["rating"], record["end_time"], run_started_at
                        )
                    ):
                        self._qualify_player(
                            conn, player, participant["rating"],
                            game_uuid, record["end_time"], run_id=run_id,
                        )

                reference = record["partner_reference"]
                if reference:
                    partner = conn.execute(
                        """
                        SELECT uuid, numeric_id FROM games
                        WHERE uuid = ? OR CAST(numeric_id AS TEXT) = ? LIMIT 1
                        """,
                        (reference, reference),
                    ).fetchone()
                    if partner and partner["uuid"] != game_uuid:
                        conn.execute(
                            "UPDATE games SET partner_uuid = ?, updated_at = ? WHERE uuid = ?",
                            (partner["uuid"], now, game_uuid),
                        )
                        identifiers = [game_uuid]
                        if record["numeric_id"] is not None:
                            identifiers.append(str(record["numeric_id"]))
                        placeholders = ",".join("?" * len(identifiers))
                        conn.execute(
                            f"""
                            UPDATE games SET partner_uuid = ?, updated_at = ?
                            WHERE uuid = ? AND partner_reference IN ({placeholders})
                            """,
                            (game_uuid, now, partner["uuid"], *identifiers),
                        )
        finally:
            conn.close()
        return record

    def has_game_reference(self, reference):
        conn = self._connection()
        try:
            return bool(
                conn.execute(
                    "SELECT 1 FROM games WHERE uuid = ? OR CAST(numeric_id AS TEXT) = ?",
                    (str(reference), str(reference)),
                ).fetchone()
            )
        finally:
            conn.close()

    def get_game(self, game_uuid):
        conn = self._connection()
        try:
            row = conn.execute("SELECT * FROM games WHERE uuid = ?", (game_uuid,)).fetchone()
            if not row:
                return None
            game = dict(row)
            game["raw_payload"] = json.loads(game["raw_payload"])
            participants = {}
            for participant in conn.execute(
                """
                SELECT gp.color, p.username, gp.rating, gp.result
                FROM game_participants gp JOIN players p ON p.id = gp.player_id
                WHERE gp.game_uuid = ?
                """,
                (game_uuid,),
            ):
                participants[participant["color"]] = {
                    "username": participant["username"],
                    "rating": participant["rating"],
                    "result": participant["result"],
                }
            game["participants"] = participants
            return game
        finally:
            conn.close()
