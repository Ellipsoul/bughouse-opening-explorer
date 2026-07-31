"""Single-worker orchestration for the durable crawler queue."""

from __future__ import annotations

from datetime import datetime, timezone

from .http import (
    CallbackNotFound,
    DeferredHttpError,
    PermanentHttpError,
    PlayerNotFound,
)


class CrawlWorker:
    def __init__(
        self,
        store,
        client,
        *,
        run_started_at=None,
        sampler_version=1,
        worker_id="crawler",
        run_id=None,
    ):
        self.store = store
        self.client = client
        self.run_started_at = run_started_at or datetime.now(timezone.utc)
        self.sampler_version = sampler_version
        self.worker_id = worker_id
        self.run_id = run_id

    def run_until_idle(self, max_jobs=None):
        result = {"processed": 0, "completed": 0, "deferred": 0, "failed": 0}
        while max_jobs is None or result["processed"] < max_jobs:
            job = self.store.lease_job(self.worker_id)
            if job is None:
                break
            self.store.assign_job_to_run(job.id, self.run_id)
            self.store.heartbeat(self.run_id) if self.run_id else None
            result["processed"] += 1
            try:
                details = self._process(job)
            except CallbackNotFound as exc:
                status = self.store.defer_job(job.id, exc, delay_seconds=86_400)
                result[status] += 1
            except DeferredHttpError as exc:
                status = self.store.defer_job(
                    job.id,
                    exc,
                    delay_seconds=60,
                    preserve_after_exhaustion=True,
                )
                result[status] += 1
            except (PlayerNotFound, PermanentHttpError, ValueError) as exc:
                self.store.fail_job(job.id, exc)
                result["failed"] += 1
            except Exception as exc:
                self.store.fail_job(job.id, exc)
                result["failed"] += 1
            else:
                self.store.complete_job(job.id, details)
                result["completed"] += 1
        return result

    def _process(self, job):
        if job.type == "archive_list":
            return self._archive_list(job)
        if job.type == "month":
            return self._month(job)
        if job.type == "partner_probe":
            return self._partner_probe(job)
        raise ValueError(f"unknown crawl job type: {job.type}")

    def _archive_list(self, job):
        username = job.payload["username"]
        mode = job.payload["mode"]
        months = self.client.get_archives(username)
        self.store.bump_run_counters(self.run_id, public_requests=1)
        scheduled = self.store.schedule_archive_months(
            username,
            months,
            mode=mode,
            run_started_at=self.run_started_at,
            run_id=self.run_id or job.run_id,
        )
        if mode == "full":
            self.store.mark_full_crawl_completed_if_done(username)
        return {"username": username, "mode": mode, "months": len(scheduled)}

    def _month(self, job):
        username = job.payload["username"]
        year = int(job.payload["year"])
        month = int(job.payload["month"])
        cache = self.store.month_cache(username, year, month) or {}
        response = self.client.get_month(
            username,
            year,
            month,
            etag=cache.get("etag"),
            last_modified=cache.get("last_modified"),
        )
        self.store.bump_run_counters(self.run_id, public_requests=1)
        if response.not_modified:
            self.store.mark_month_not_modified(username, year, month)
            summary = {"archive_games": 0, "bughouse_games": 0, "probes": 0,
                       "not_modified": True}
        else:
            summary = self.store.save_public_month(
                username,
                year,
                month,
                (response.data or {}).get("games", []),
                run_started_at=self.run_started_at,
                etag=response.etag,
                last_modified=response.last_modified,
                sampler_version=self.sampler_version,
                run_id=self.run_id or job.run_id,
            )
        if job.payload.get("mode") == "full":
            self.store.mark_full_crawl_completed_if_done(username)
        return {"username": username, "year": year, "month": month, **summary}

    def _partner_probe(self, job):
        first_payload = self.client.get_callback(job.payload["reference"])
        self.store.bump_run_counters(self.run_id, callback_requests=1)
        first = self.store.save_callback_game(
            first_payload,
            run_started_at=self.run_started_at,
            run_id=self.run_id or job.run_id,
        )
        partner = first.get("partner_reference")
        fetched_partner = False
        if partner and not self.store.has_game_reference(partner):
            partner_payload = self.client.get_callback(partner)
            self.store.bump_run_counters(self.run_id, callback_requests=1)
            self.store.save_callback_game(
                partner_payload,
                run_started_at=self.run_started_at,
                run_id=self.run_id or job.run_id,
            )
            fetched_partner = True
        return {
            "board_uuid": first["uuid"],
            "partner_reference": partner,
            "fetched_partner": fetched_partner,
        }
