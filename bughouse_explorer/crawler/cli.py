"""Click commands for operating the standalone crawler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import time

import click

from .config import CrawlerConfig
from .http import ChessComCrawlerClient
from .migrations import apply_migrations
from .seeds import load_initial_seeds
from .store import CrawlerStore
from .worker import CrawlWorker


def _config(database_path):
    env = CrawlerConfig.from_env()
    return CrawlerConfig(
        database_path=database_path,
        user_agent=env.user_agent,
        min_interval_ms=env.min_interval_ms,
        sampler_version=env.sampler_version,
    )


def _store(database_path):
    apply_migrations(database_path)
    return CrawlerStore(database_path)


def _worker(store, config, *, run_started_at=None, run_id=None):
    client = ChessComCrawlerClient(
        user_agent=config.user_agent,
        min_interval_ms=config.min_interval_ms,
    )
    return CrawlWorker(
        store,
        client,
        run_started_at=run_started_at,
        sampler_version=config.sampler_version,
        worker_id="cli-worker",
        run_id=run_id,
    )


def _print_status(status, as_json=False):
    if as_json:
        click.echo(json.dumps(status, sort_keys=True, default=str))
        return
    players = status["players"]
    jobs = status["jobs"]
    click.echo(
        "Players: "
        f"{players['eligible']} eligible, {players['candidate']} candidate, "
        f"{players['dormant']} dormant"
    )
    click.echo(
        "Jobs: "
        f"{jobs['queued']} queued, {jobs['leased']} leased, "
        f"{jobs['deferred']} deferred, {jobs['failed']} failed, "
        f"{jobs['complete']} complete"
    )
    click.echo(
        f"Games: {status['games']} boards, {status['partner_links']} linked boards; "
        f"{status['fully_crawled_players']} players fully crawled"
    )
    click.echo(
        f"Progress: {status['remaining_jobs']} jobs remaining, "
        f"{status['retries']} retries, "
        f"{status['recent_jobs_per_hour']} jobs/hour recently"
    )
    if status["run"]:
        run = status["run"]
        counters = run["counters"]
        click.echo(
            f"Run: {run['id']} ({run['status']}), heartbeat {run['heartbeat_at']}; "
            f"{counters.get('public_requests', 0)} public and "
            f"{counters.get('callback_requests', 0)} callback requests, "
            f"{run['request_rate_per_second']:.2f} req/s"
        )
    if status["current"]:
        current = status["current"]
        click.echo(f"Current: {current['type']} {current['payload']}")
    if status["latest_error"]:
        click.echo(f"Latest error: {status['latest_error']['details']}")


@click.group()
@click.option(
    "--crawler-db",
    default=lambda: CrawlerConfig.from_env().database_path,
    show_default="data/crawler.db",
    help="Standalone SQLite crawler database.",
)
@click.pass_context
def crawl(ctx, crawler_db):
    """Crawl Chess.com Bughouse archives into a durable SQLite queue."""
    ctx.ensure_object(dict)
    ctx.obj["database_path"] = crawler_db


@crawl.command("migrate")
@click.pass_context
def migrate_command(ctx):
    """Apply pending crawler database migrations."""
    path = ctx.obj["database_path"]
    apply_migrations(path)
    click.echo(f"Crawler database ready: {path}")


@crawl.command("seed")
@click.argument("usernames", nargs=-1)
@click.pass_context
def seed_command(ctx, usernames):
    """Add seed USERNAMES; with no names, load the approved initial manifest."""
    path = ctx.obj["database_path"]
    store = _store(path)
    values = list(usernames) or load_initial_seeds()
    store.seed_usernames(values)
    click.echo(f"Seeded {len({value.lower() for value in values})} player(s) in {path}")


def _run(store, config, run_id, run_started_at, max_jobs):
    worker = _worker(
        store, config, run_started_at=run_started_at, run_id=run_id
    )
    try:
        result = worker.run_until_idle(max_jobs=max_jobs)
    except KeyboardInterrupt:
        store.finish_run(run_id, "stopped", "interrupted")
        raise click.Abort()
    status = store.status()
    unfinished = status["jobs"]["queued"] + status["jobs"]["leased"] + status["jobs"]["deferred"]
    store.finish_run(run_id, "stopped" if unfinished else "complete")
    click.echo(json.dumps(result, sort_keys=True))
    _print_status(store.status())


@crawl.command("bootstrap")
@click.option("--max-jobs", type=int, default=None, help="Stop after this many jobs.")
@click.option("--seed-initial/--no-seed-initial", default=True, show_default=True)
@click.pass_context
def bootstrap_command(ctx, max_jobs, seed_initial):
    """Run or continue the self-expanding full-history crawl."""
    path = ctx.obj["database_path"]
    config = _config(path)
    store = _store(path)
    if seed_initial:
        store.seed_usernames(load_initial_seeds())
    started = datetime.now(timezone.utc)
    run_id = store.start_run("bootstrap", {"sampler_version": config.sampler_version})
    _run(store, config, run_id, started, max_jobs)


@crawl.command("monthly")
@click.option("--year", type=int)
@click.option("--month", type=click.IntRange(1, 12))
@click.option("--max-jobs", type=int, default=None)
@click.pass_context
def monthly_command(ctx, year, month, max_jobs):
    """Refresh the previous month for every currently eligible player."""
    if (year is None) != (month is None):
        raise click.UsageError("--year and --month must be supplied together")
    started = datetime.now(timezone.utc)
    if year is None:
        previous = started.replace(day=1) - timedelta(days=1)
        year, month = previous.year, previous.month
    path = ctx.obj["database_path"]
    config = _config(path)
    store = _store(path)
    run_id = store.start_run("monthly", {"year": year, "month": month})
    dormant = store.reevaluate_dormancy(started)
    queued = store.queue_monthly_refresh(year, month, run_id=run_id)
    click.echo(f"Queued {len(queued)} player(s); marked {dormant} dormant")
    _run(store, config, run_id, started, max_jobs)


@crawl.command("resume")
@click.argument("run_id", required=False)
@click.option("--max-jobs", type=int, default=None)
@click.pass_context
def resume_command(ctx, run_id, max_jobs):
    """Resume the durable global queue after interruption or deferred retries."""
    path = ctx.obj["database_path"]
    config = _config(path)
    store = _store(path)
    if run_id is None:
        started = datetime.now(timezone.utc)
        run_id = store.start_run("bootstrap", {"resumed": True})
    else:
        run = store.resume_run(run_id)
        started = datetime.fromtimestamp(run["started_at"], tz=timezone.utc)
    _run(store, config, run_id, started, max_jobs)


@crawl.command("status")
@click.option("--watch", is_flag=True, help="Refresh every two seconds.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.pass_context
def status_command(ctx, watch, as_json):
    """Show persisted crawl progress without changing the queue."""
    store = _store(ctx.obj["database_path"])
    try:
        while True:
            _print_status(store.status(), as_json)
            if not watch:
                return
            time.sleep(2)
    except KeyboardInterrupt:
        return
