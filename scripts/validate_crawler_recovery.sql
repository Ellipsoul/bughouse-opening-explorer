-- Read-only crawler recovery validation for the fixed bootstrap policy window.
-- Run against a closed snapshot or restore via an immutable read-only URI:
--   sqlite3 'file:/absolute/path/to/crawler.db?mode=ro&immutable=1' \
--     ".read scripts/validate_crawler_recovery.sql"
--
-- The fixed window below belongs to bootstrap run
-- 8210df08-c748-4de7-9eea-ccc8740caa8a. Update the policy assertions when a
-- future authoritative snapshot intentionally uses a different evaluation
-- window.

.bail on
PRAGMA query_only = ON;
.mode list
.separator |

SELECT 'quick_check', group_concat(quick_check, ',') FROM pragma_quick_check;
SELECT 'foreign_key_violations', COUNT(*) FROM pragma_foreign_key_check;
SELECT 'schema_migrations', group_concat(version, ',')
FROM (SELECT version FROM crawler_schema_migrations ORDER BY version);
SELECT 'games', COUNT(*) FROM games;
SELECT 'game_participants', COUNT(*) FROM game_participants;
SELECT 'players', COUNT(*) FROM players;
SELECT 'players_candidate', COUNT(*) FROM players WHERE state = 'candidate';
SELECT 'players_dormant', COUNT(*) FROM players WHERE state = 'dormant';
SELECT 'players_eligible', COUNT(*) FROM players WHERE state = 'eligible';
SELECT 'permanently_tracked_players', COUNT(*)
FROM players WHERE tracking_started_at IS NOT NULL;
SELECT 'completed_crawls', COUNT(*)
FROM players WHERE full_crawl_completed_at IS NOT NULL;
SELECT 'terminal_unavailable_archives', COUNT(*)
FROM players WHERE archive_unavailable_at IS NOT NULL;
SELECT 'terminal_unavailable_months', COUNT(*)
FROM player_months WHERE unavailable_at IS NOT NULL;
SELECT 'terminal_unresolved_probes', COUNT(*)
FROM crawl_jobs WHERE terminal_outcome = 'probe_unresolved';
SELECT 'crawl_jobs', COUNT(*) FROM crawl_jobs;
SELECT 'jobs_complete', COUNT(*) FROM crawl_jobs WHERE status = 'complete';
SELECT 'jobs_queued', COUNT(*) FROM crawl_jobs WHERE status = 'queued';
SELECT 'jobs_leased', COUNT(*) FROM crawl_jobs WHERE status = 'leased';
SELECT 'jobs_deferred', COUNT(*) FROM crawl_jobs WHERE status = 'deferred';
SELECT 'jobs_failed', COUNT(*) FROM crawl_jobs WHERE status = 'failed';
SELECT 'crawl_events', COUNT(*) FROM crawl_events;
SELECT 'active_runs', COUNT(*)
FROM crawl_runs WHERE status = 'running' OR ended_at IS NULL;

SELECT 'qualification_invariant_violations', COUNT(*)
FROM players p
LEFT JOIN games g ON g.uuid = p.qualifying_game_uuid
LEFT JOIN game_participants gp
  ON gp.game_uuid = p.qualifying_game_uuid
 AND gp.player_id = p.id
WHERE (
        p.state = 'eligible'
     OR p.qualifying_game_uuid IS NOT NULL
     OR p.qualifying_rating IS NOT NULL
     OR p.qualifying_at IS NOT NULL
) AND (
        p.qualifying_game_uuid IS NULL
     OR p.qualifying_rating IS NULL
     OR p.qualifying_at IS NULL
     OR gp.player_id IS NULL
     OR gp.rating IS NOT p.qualifying_rating
     OR gp.rating_source NOT IN ('public', 'callback_pgn')
     OR g.end_time IS NOT p.qualifying_at
);

SELECT 'eligible_without_valid_fixed_window_observation', COUNT(*)
FROM players p
WHERE p.state = 'eligible'
  AND NOT EXISTS (
      SELECT 1
      FROM game_participants gp
      JOIN games g ON g.uuid = gp.game_uuid
      WHERE gp.player_id = p.id
        AND gp.rating_source IN ('public', 'callback_pgn')
        AND gp.rating >= 2000
        AND g.end_time BETWEEN
            CAST(strftime('%s', '2025-07-31 19:40:45') AS INTEGER)
            AND CAST(strftime('%s', '2026-07-31 19:40:45') AS INTEGER)
  );

SELECT 'eligible_pointer_fixed_window_violations', COUNT(*)
FROM players
WHERE state = 'eligible'
  AND (
      qualifying_rating < 2000
      OR qualifying_at < CAST(strftime('%s', '2025-07-31 19:40:45') AS INTEGER)
      OR qualifying_at > CAST(strftime('%s', '2026-07-31 19:40:45') AS INTEGER)
  );

SELECT 'closure_remaining_jobs', COUNT(*)
FROM crawl_jobs WHERE status IN ('queued', 'leased', 'deferred');
SELECT 'closure_failed_jobs', COUNT(*)
FROM crawl_jobs WHERE status = 'failed';
SELECT 'closure_tracked_without_outcome', COUNT(*)
FROM players
WHERE tracking_started_at IS NOT NULL
  AND full_crawl_completed_at IS NULL
  AND archive_unavailable_at IS NULL;
SELECT 'closure_eligible_without_outcome', COUNT(*)
FROM players
WHERE state = 'eligible'
  AND full_crawl_completed_at IS NULL
  AND archive_unavailable_at IS NULL;
SELECT 'closure_ready', CASE WHEN
    (SELECT COUNT(*) FROM crawl_jobs
     WHERE status IN ('queued', 'leased', 'deferred')) = 0
    AND (SELECT COUNT(*) FROM crawl_jobs WHERE status = 'failed') = 0
    AND (SELECT COUNT(*) FROM players
         WHERE tracking_started_at IS NOT NULL
           AND full_crawl_completed_at IS NULL
           AND archive_unavailable_at IS NULL) = 0
  THEN 1 ELSE 0 END;
