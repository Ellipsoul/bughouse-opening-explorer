CREATE TABLE IF NOT EXISTS players (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    username                 TEXT NOT NULL UNIQUE,
    display_username         TEXT NOT NULL,
    state                    TEXT NOT NULL DEFAULT 'candidate'
                             CHECK (state IN ('candidate', 'eligible', 'dormant')),
    is_seed                  INTEGER NOT NULL DEFAULT 0,
    discovery_source         TEXT NOT NULL,
    discovered_at            INTEGER NOT NULL,
    last_seen_at             INTEGER,
    qualifying_rating        INTEGER,
    qualifying_game_uuid     TEXT,
    qualifying_at            INTEGER,
    full_crawl_completed_at  INTEGER,
    latest_month_completed   TEXT,
    updated_at               INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    uuid                 TEXT PRIMARY KEY,
    numeric_id           INTEGER UNIQUE,
    partner_reference    TEXT,
    partner_uuid         TEXT,
    end_time             INTEGER,
    time_control         TEXT,
    time_class           TEXT,
    rated                INTEGER,
    rules                TEXT NOT NULL DEFAULT 'bughouse',
    tcn                  TEXT,
    initial_setup        TEXT,
    fen                  TEXT,
    url                  TEXT,
    source               TEXT NOT NULL CHECK (source IN ('public', 'callback')),
    raw_payload          TEXT NOT NULL,
    content_hash         TEXT NOT NULL,
    first_seen_at        INTEGER NOT NULL,
    updated_at           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crawler_games_end_time ON games(end_time);
CREATE INDEX IF NOT EXISTS idx_crawler_games_partner_uuid
    ON games(partner_uuid) WHERE partner_uuid IS NOT NULL;

CREATE TABLE IF NOT EXISTS game_participants (
    game_uuid     TEXT NOT NULL REFERENCES games(uuid) ON DELETE CASCADE,
    color         TEXT NOT NULL CHECK (color IN ('white', 'black')),
    player_id     INTEGER NOT NULL REFERENCES players(id),
    rating        INTEGER,
    result        TEXT,
    rating_source TEXT NOT NULL CHECK (rating_source IN ('public', 'callback_pgn', 'callback_profile')),
    PRIMARY KEY (game_uuid, color)
);
CREATE INDEX IF NOT EXISTS idx_crawler_participants_player
    ON game_participants(player_id, game_uuid);

CREATE TABLE IF NOT EXISTS player_months (
    player_id            INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    year                 INTEGER NOT NULL CHECK (year >= 2000),
    month                INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    status               TEXT NOT NULL DEFAULT 'queued'
                         CHECK (status IN ('queued', 'leased', 'complete', 'deferred', 'failed')),
    etag                 TEXT,
    last_modified        TEXT,
    archive_game_count   INTEGER,
    bughouse_game_count  INTEGER,
    attempts             INTEGER NOT NULL DEFAULT 0,
    sampler_version      INTEGER,
    fetched_at           INTEGER,
    last_error           TEXT,
    PRIMARY KEY (player_id, year, month)
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id            TEXT PRIMARY KEY,
    run_type      TEXT NOT NULL CHECK (run_type IN ('bootstrap', 'monthly')),
    status        TEXT NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'complete', 'failed', 'stopped')),
    config        TEXT NOT NULL DEFAULT '{}',
    counters      TEXT NOT NULL DEFAULT '{}',
    started_at    INTEGER NOT NULL,
    heartbeat_at  INTEGER NOT NULL,
    ended_at      INTEGER,
    last_error    TEXT
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
    job_key         TEXT NOT NULL UNIQUE,
    type            TEXT NOT NULL CHECK (type IN ('archive_list', 'month', 'partner_probe')),
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'leased', 'deferred', 'complete', 'failed')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,
    available_at    INTEGER NOT NULL,
    leased_by       TEXT,
    leased_until    INTEGER,
    last_error      TEXT,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    completed_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_crawler_jobs_available
    ON crawl_jobs(status, available_at, id);

CREATE TABLE IF NOT EXISTS crawl_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT REFERENCES crawl_runs(id) ON DELETE CASCADE,
    job_id      INTEGER REFERENCES crawl_jobs(id) ON DELETE SET NULL,
    level       TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error')),
    event       TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '{}',
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crawler_events_created
    ON crawl_events(created_at DESC);

