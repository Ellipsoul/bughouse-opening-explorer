import sqlite3
from datetime import datetime, timezone
import pytest
from bughouse_explorer.opening.snapshot_recovery import audit_connection


def source():
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
      CREATE TABLE crawl_runs(id TEXT,status TEXT,started_at INTEGER,ended_at INTEGER);
      CREATE TABLE crawl_jobs(status TEXT);
      CREATE TABLE players(id INTEGER,state TEXT,tracking_started_at INTEGER,
        full_crawl_completed_at INTEGER,archive_unavailable_at INTEGER,
        qualifying_game_uuid TEXT,qualifying_rating INTEGER,qualifying_at INTEGER);
      CREATE TABLE games(uuid TEXT,end_time INTEGER);
      CREATE TABLE game_participants(game_uuid TEXT,player_id INTEGER,rating INTEGER,rating_source TEXT);
    """
    )
    now = int(datetime(2026, 10, 2, tzinfo=timezone.utc).timestamp())
    c.execute(
        "INSERT INTO crawl_runs VALUES (?,?,?,?)", ("monthly", "complete", now, now + 1)
    )
    c.execute("INSERT INTO players VALUES (1,'eligible',1,1,NULL,'g',2200,?)", (now,))
    c.execute("INSERT INTO games VALUES ('g',?)", (now,))
    c.execute("INSERT INTO game_participants VALUES ('g',1,2200,'public')")
    return c


def test_run_specific_window_accepts_october_evidence_and_rejects_stale_pointer():
    c = source()
    report = audit_connection(c, "monthly")
    assert not any(report["violations"].values())
    c.execute("UPDATE players SET qualifying_at=1")
    with pytest.raises(ValueError, match="invariant"):
        audit_connection(c, "monthly")


def test_active_run_or_unclosed_cohort_is_rejected():
    c = source()
    c.execute("UPDATE crawl_runs SET status='running'")
    with pytest.raises(ValueError, match="completed"):
        audit_connection(c, "monthly")
    c = source()
    c.execute("UPDATE players SET full_crawl_completed_at=NULL")
    with pytest.raises(ValueError, match="invariant"):
        audit_connection(c, "monthly")
