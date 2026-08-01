CREATE TABLE IF NOT EXISTS partner_year_samples (
    player_id           INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    year                INTEGER NOT NULL,
    sampler_version     INTEGER NOT NULL,
    board_uuid          TEXT NOT NULL REFERENCES games(uuid) ON DELETE CASCADE,
    eligibility_cutoff  INTEGER NOT NULL,
    run_id              TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
    selected_at         INTEGER NOT NULL,
    PRIMARY KEY (player_id, year, sampler_version)
);

CREATE INDEX IF NOT EXISTS idx_partner_year_samples_board
    ON partner_year_samples(board_uuid);
