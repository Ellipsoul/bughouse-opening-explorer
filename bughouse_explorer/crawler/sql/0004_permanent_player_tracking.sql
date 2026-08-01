ALTER TABLE players ADD COLUMN tracking_started_at INTEGER;

UPDATE players
SET tracking_started_at = COALESCE(qualifying_at, discovered_at)
WHERE state = 'eligible';

CREATE INDEX idx_players_permanent_tracking
    ON players(tracking_started_at)
    WHERE tracking_started_at IS NOT NULL;
