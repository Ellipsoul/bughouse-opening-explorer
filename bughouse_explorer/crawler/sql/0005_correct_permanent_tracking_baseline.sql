UPDATE players
SET tracking_started_at = NULL
WHERE state = 'dormant'
  AND tracking_started_at IS NOT NULL
  AND tracking_started_at <= (
      SELECT applied_at
      FROM crawler_schema_migrations
      WHERE version = '0004_permanent_player_tracking.sql'
  );
