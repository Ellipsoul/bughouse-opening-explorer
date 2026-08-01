ALTER TABLE players ADD COLUMN full_archive_list_fetched_at INTEGER;
ALTER TABLE players ADD COLUMN archive_unavailable_at INTEGER;
ALTER TABLE players ADD COLUMN archive_unavailable_error TEXT;

ALTER TABLE player_months ADD COLUMN unavailable_at INTEGER;
ALTER TABLE player_months ADD COLUMN unavailable_error TEXT;

ALTER TABLE crawl_jobs ADD COLUMN terminal_outcome TEXT;
ALTER TABLE crawl_jobs ADD COLUMN terminal_at INTEGER;

CREATE TABLE player_archive_month_manifest (
    player_id    INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    observed_at  INTEGER NOT NULL,
    run_id       TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
    PRIMARY KEY (player_id, year, month)
);
