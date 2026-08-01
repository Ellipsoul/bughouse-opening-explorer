# 100-player crawl analysis

This report analyzes bootstrap run
`8210df08-c748-4de7-9eea-ccc8740caa8a`, which stopped on 31 July 2026 after
reaching its configured limit of 100 fully crawled players.

The figures are a snapshot of `data/crawler.db` immediately after the run. The
run deliberately stopped with reachable work remaining, so its database status
is `stopped`, not `complete` or globally idle.

## Executive summary

- The crawler reached exactly 100 fully crawled players in 9,626 seconds
  (2 h 40 m 26 s).
- It completed 10,222 durable jobs and recorded 10,126 public archive
  operations plus 121 callback operations.
- The whole run averaged 1.064 logical Chess.com operations per second.
- The last 25.3 minutes, after restarting with the 100 ms minimum interval,
  completed 1.193 jobs per second. The earlier 250 ms segment completed 1.037
  jobs per second, an observed improvement of about 15%.
- No HTTP 429 response was observed. There were five 5xx responses, one network
  error, six retries, three recorded recoveries, and one permanent archive 404.
- The database contains 3,511,571 unique Bughouse board UUIDs and occupies
  6,484,099,072 bytes (about 6.04 GiB).
- The 100 completed players are highly heterogeneous: the median has 19,276
  Bughouse board occurrences, the 90th percentile has 66,555, and the largest
  has 141,423.
- The crawl is nowhere near queue exhaustion. It knows about 931 currently
  eligible players, of whom 831 still need a full crawl, and has 23,268 jobs
  already queued.
- Completing only the currently known eligible population is estimated to need
  roughly another 24-30 hours on one worker once archive months and the partner
  probes they generate are both included.
- This is a lower bound for transitive closure. During the final 100 ms segment,
  21 completed players led to 33 newly created full-crawl jobs. The frontier was
  still growing faster than it was being retired, so the final reachable player
  count cannot yet be estimated tightly.

## Run outcome

| Metric | Value |
| --- | ---: |
| Started (UTC) | 2026-07-31 19:40:45 |
| Ended (UTC) | 2026-07-31 22:21:11 |
| Wall time | 9,626 s / 2.674 h |
| Fully crawled players | 100 |
| Completed jobs | 10,222 |
| Failed jobs | 1 |
| Queued jobs | 23,268 |
| Public archive operations | 10,126 |
| Callback operations | 121 |
| Average logical operation rate | 1.064/s |
| Unique board UUIDs | 3,511,571 |
| Database size | 6,484,099,072 bytes |

The single failed job was a public archive request for `dielie`, March 2018,
which returned HTTP 404. It did not terminate the crawl.

## Speed profile

The run changed configuration partway through. The initial process used the
250 ms minimum interval. At 21:55:55 UTC it was resumed with the 100 ms minimum
interval and the stricter eligibility policy.

| Segment | Wall time | Completed jobs | Jobs/s | Players completed | Players/h |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial 250 ms | 8,110 s | 8,411 | 1.037 | 79 | 35.1 |
| Restarted 100 ms | 1,516 s | 1,808 | 1.193 | 21 | 49.8 |

The 100 ms segment processed larger-than-average monthly payloads while still
finishing more jobs per second:

| Segment | Months fetched | Mean archive records/month | Mean Bughouse boards/month |
| --- | ---: | ---: | ---: |
| Initial 250 ms | 7,733 | 511.6 | 396.9 |
| Restarted 100 ms | 1,811 | 623.6 | 560.2 |

Unique-board ingestion rose from about 1.19 million boards/hour in the initial
segment to 1.97 million boards/hour in the restarted segment.

The final segment also demonstrates why the durable queue can appear almost
stationary during healthy progress:

| Final 25.3-minute queue flow | Jobs |
| --- | ---: |
| Completed | 1,808 |
| New partner probes created | 1,626 |
| New full archive-list jobs created | 33 |
| New monthly refresh jobs created | 7 |
| **Net jobs retired** | **142** |

That is only 337 net jobs retired/hour even though the worker completed about
4,293 jobs/hour. Most month work was being transformed into deterministic probe
work rather than disappearing from the queue. This is expected pipeline flow,
not a stall, but it makes queue length alone a poor progress indicator.

This is useful operational evidence, but it is not a controlled A/B test. The
second segment also used different queue priority, consisted entirely of month
jobs, covered a different player mix, and ran for only 25 minutes. The safest
conclusion is that 100 ms improved throughput without producing observable rate
limiting; the exact percentage attributable to pacing alone remains uncertain.

Only about 0.1 seconds of an average 0.84-second job cycle is now deliberate
pacing. Chess.com response time, JSON parsing, and SQLite ingestion dominate the
remaining wall time. Removing the delay entirely therefore cannot produce a
tenfold improvement.

## HTTP health

| Observation | Count |
| --- | ---: |
| HTTP 429 | 0 |
| HTTP 5xx | 5 |
| Network errors | 1 |
| Retries | 6 |
| Recoveries | 3 |
| Permanent failed jobs | 1 |

Six retries across roughly 10,247 logical operations is about 0.06%. There is
no evidence in this run that Chess.com rate-limited the single-worker crawler.
The occasional long request is more consistent with server/network latency than
throttling.

## Data accumulated

### Player states

| State | Full crawl complete | Players |
| --- | --- | ---: |
| Eligible | Yes | 100 |
| Eligible | No | 831 |
| Dormant | No | 1,204 |
| Candidate | No | 119,964 |

There are 122,099 distinct player identities in total. Most are historical or
below-threshold opponents found inside the large public archives; discovering
an identity does not cause its archive to be fetched unless qualifying evidence
is observed.

### Recent observed rating distribution

Among players for whom the database has an authoritative rating observation in
the final one-year eligibility window:

| Maximum observed rating | Players |
| --- | ---: |
| 2000+ | 931 |
| 1950-1999 | 203 |
| 1900-1949 | 229 |
| 1800-1899 | 650 |
| 1600-1799 | 1,991 |
| Below 1600 | 21,503 |

The 931 observations at 2000+ correspond exactly to the current eligible
population, which is a useful eligibility-integrity check. The 203 players in
the 1950-1999 band are the clearest near-threshold source of future promotions,
but players can also be discovered or re-encountered with ratings not yet in the
database.

### Game de-duplication

Completed player-month records contain 4,021,136 Bughouse board occurrences,
while the canonical `games` table contains 3,511,571 unique UUIDs. At this
snapshot, 509,565 repeated occurrences (12.7%) were collapsed by UUID rather
than stored as duplicate games.

Of the canonical boards:

- 3,511,558 are authoritative public-archive records;
- 13 remain callback-only records;
- participant rows comprise 7,023,116 public observations and 26 timestamped
  callback-PGN observations.

The 96 completed probe jobs made 121 callback operations. They left only 13
callback-only boards and discovered 11 identities first seen via callback; none
of those 11 is currently eligible. This small initial sample suggests that many
sampled partner boards are eventually encountered in public player histories,
but 7,919 queued probes remain too large a backlog to generalize confidently.

### SQLite storage profile

| Object | MiB | Share |
| --- | ---: | ---: |
| `games` | 4,638.8 | 75.0% |
| `game_participants` | 496.4 | 8.0% |
| Participant primary-key index | 384.9 | 6.2% |
| Player-to-game index | 362.5 | 5.9% |
| Games UUID index | 169.8 | 2.7% |

The database currently uses about 1,846 bytes per canonical board, including
participants, indexes, players, jobs, and events. A practical capacity-planning
rule is therefore approximately 1.8-2.0 GB per additional million unique
boards. Raw game payloads in `games` are the dominant cost.

There are roughly 45,000 known or likely-to-be-scheduled full-history month
fetches left for the current eligible population. If future months resemble the
median completed month, the database would finish near 20 GB; if they resemble
the game-heavy final segment, it could approach 45-50 GB. A central planning
allowance of roughly 35-40 GB for the currently known 931-player population is
reasonable, but this range is much less certain than the time estimate because
future board overlap can substantially improve de-duplication.

Do not extrapolate `6 GB / 100 completed players` directly. The existing 6 GB
already includes recent qualification scans for hundreds of unfinished and
dormant players, while later full histories will overlap more heavily.

## Workload distribution

### Fully crawled players

| Percentile | Completed archive months | Bughouse board occurrences |
| --- | ---: | ---: |
| P10 | 10 | 4,141 |
| P25 | 21 | 9,460 |
| P50 | 70 | 19,276 |
| P75 | 99 | 36,005 |
| P90 | 118 | 66,555 |

The mean completed history is 64.6 months and 27,460 Bughouse board
occurrences. The mean is above the board-count median because a small number of
very prolific players dominate volume.

The largest completed histories by Bughouse board occurrence are:

| Player | Months | Bughouse boards |
| --- | ---: | ---: |
| `hopefulwin` | 118 | 141,423 |
| `biggerbishop` | 119 | 99,724 |
| `chickencrossroad` | 123 | 84,830 |
| `vampyreslayer` | 121 | 84,019 |
| `111michael` | 109 | 72,455 |

The first 100 are biased toward established, highly connected players. Later
players may have shorter and lighter histories, so a simple linear projection
from their game counts is likely to overestimate storage and parsing work.

### Monthly payloads

| Percentile | All archive records | Bughouse boards |
| --- | ---: | ---: |
| P50 | 324 | 171 |
| P90 | 1,283 | 1,172 |
| P99 | 2,932 | 2,850 |
| Maximum | 5,000 | 4,998 |

Monthly request count is therefore a good first-order time predictor, but a poor
predictor of ingestion volume: the largest months contain over fifteen times as
many records as the median.

## Remaining queue

| Job type | Queued |
| --- | ---: |
| Full archive-list fetch | 496 |
| Month fetch | 14,853 |
| Partner probe | 7,919 |
| **Total** | **23,268** |

Of the queued month jobs, 13,949 are full-history months and 904 are
current-month refreshes. Archive lists have already been fetched for roughly
341 unfinished eligible players; those players currently average about 50
known archive months, with 41 still queued. Roughly 490 other eligible players
are still waiting for their full archive list, so their older month jobs have
not yet been added to the visible queue.

This is why `23,268 / current jobs per second` understates remaining time. It
omits:

1. older month jobs that the 496 archive-list fetches will create;
2. partner-probe jobs that every newly completed month can create; and
3. full-history work for additional players promoted during those fetches.

The final segment's measured job-creation rate reinforces this point: 1,808
completions produced 1,666 new jobs and reduced the visible queue by only 142.
The rate will change by phase. Month-heavy phases generate probe debt, while a
probe-heavy phase should retire jobs faster unless it promotes many new
eligible players.

### Why the queue often grows by exactly one

The status value is a count of durable jobs, not a fully expanded count of
future HTTP requests. Job expansion is intentionally lazy:

| Completed job or observation | Immediate fan-out |
| --- | --- |
| Player receives qualifying evidence | One `archive_list` job |
| `archive_list` completes | One `month` job for each available archive month |
| `month` completes | Zero to four sampled `partner_probe` jobs, plus archive-list jobs for any newly qualifying players |
| `partner_probe` completes | Zero to four archive-list jobs for newly qualifying board players |

The adaptive sampling rule makes a one-job increase especially common. A month
with more than 20 Bughouse boards selects exactly one representative board, so
it normally enqueues one partner probe. Months with 5-20 boards select two, and
months with 1-4 boards select all of them. Global board-UUID job keys suppress a
probe that was already enqueued through another player's archive.

The current month job remains leased while its ingestion transaction adds the
new probe jobs. It is marked complete in a second transaction. A status poll can
therefore briefly observe the newly added probe while still counting the leased
month. After completion, a high-volume month commonly has a net queue change of
zero: one month job retired and one probe job added.

New-player fan-out is also two-stage. Qualification adds only one archive-list
job because the crawler does not know which months exist until it calls the
player's archive-list endpoint. When that job eventually executes, it can add
dozens or over one hundred month jobs at once.

This distinction was visible in the final 25-minute segment: 1,808 completed
month jobs created 1,626 partner probes but only 33 new full archive-list jobs.
Most single-job queue growth was partner sampling, not player discovery.

## Reassessing partner-probe density

A live snapshot during the follow-on 250-player run showed that the monthly
sampling policy had accumulated 9,143 queued partner probes owned by 184
players. Those jobs covered only 1,076 distinct player/year combinations, or
an average of 8.5 probes for each represented player-year.

Replacing monthly sampling with at most one deterministic probe per player and
calendar year would reduce that existing backlog to an upper bound of 1,076
jobs: an 88.2% reduction. The true total could be smaller because the existing
global board-UUID de-duplication would still apply when two annual samples
select the same board.

The one-year eligibility window permits a stronger reduction. A historical
callback board older than the run's eligibility cutoff cannot qualify either
of its players, and the crawler does not launch an archive qualification scan
merely because an old callback introduced a username. Because callback partner
boards are retained for discovery rather than opening-tree completeness, old
probes have little actionable value. Only 1,712 of the 9,143 queued probes were
inside the active one-year window, representing 338 distinct player/year
combinations across 180 players. Keeping one probe for each of those recent
player-years would reduce the full queued backlog by approximately 96.3%. At
the observed 1.26 callback requests per completed probe, this snapshot
represents roughly 11,000 avoidable callback requests in the already-visible
queue alone.

The observed discovery yield also supports a sparser policy:

- 96 completed partner-probe jobs made 121 callback requests;
- 25 probes, or 26%, needed a second request to fetch a partner board that was
  not already stored;
- callback data introduced 11 previously unseen player identities;
- all 11 callback-first players remain candidates, and none has qualified at
  the 2,000 threshold;
- all currently eligible non-seed players were first discovered through public
  archive boards.

The callback sample is still small: its 96 completed probes came from five
players and 13 player-years. Its zero eligible discoveries should therefore
not be read as proof that partner probes have no coverage value.

The stronger structural result comes from the public-board opponent graph. At
the same snapshot, all 945 eligible players belonged to a single connected
component using only public archive records, with 64,369 distinct
eligible-to-eligible opponent pairs. This validates the working hypothesis that
the high-rated Bughouse population is heavily connected through opponents.
It cannot prove that no unknown, disconnected group exists whose members occur
only as partners on the boards reached so far, because public archives expose
only the two players on the archived board.

The recommended compromise is therefore one deterministic probe per eligible
player per calendar year, restricted to games inside the rolling eligibility
window. It retains a low-cost safeguard against partner-only components while
removing nearly all monthly and stale historical callback debt. The initial
full crawl will normally sample at most two partial calendar years because a
one-year window can straddle New Year. Samples can be chosen after all relevant
archive months have been committed, using the lowest BLAKE2 hash of
`sampler-version | username | year | board-uuid`. For the current partial year,
the crawler should choose and persist at most one year-to-date sample when the
player's initial full crawl completes, then keep that choice fixed as later
monthly refreshes append games. The persisted sample prevents a lower-hash game
arriving later from creating a second probe for the same player-year.

The policy should use a new sampler version and retain completed version-1
probes for audit. Once the current capped run stops, queued version-1 monthly
probes can be discarded and rebuilt from the raw public games as annual probes;
no authoritative game data would be lost. The active worker prioritizes full
month and archive-list jobs ahead of partner probes, so it can continue the
current capped run while this policy is designed without spending materially
more time consuming the old probe backlog.

### Version-2 queue conversion

The 250-player run was gracefully stopped on 1 August 2026 and the proposed
policy was applied using the original run's `2025-07-31 19:40:45 UTC`
eligibility cutoff. A rehearsal on a consistent SQLite backup and the live
conversion produced identical selections:

- 9,304 unfinished version-1 monthly probe jobs removed;
- all 96 completed legacy probes and their callback data retained;
- 202 version-2 annual samples created for 105 fully crawled eligible players;
- 202 globally unique callback jobs queued;
- no selected board outside the eligibility window;
- no duplicate player/year/version sample and no orphaned sample; and
- all 4,115,152 raw game rows preserved.

This is a 97.8% reduction in the unfinished probe queue at the conversion
point. Incomplete eligible players receive their recent annual samples only
after their remaining lifetime archive months finish, so the queue grows by at
most two samples per newly completed player rather than roughly one sample per
completed month.

## Forecast model

For the first 100 completed histories under the original version-1 sampler:

- mean months per full player: 64.6;
- probe jobs created per completed month: approximately 0.84;
- callback operations per completed probe: approximately 1.26.

A high-volume completed player previously implied approximately:

```text
1 archive-list request
+ 64.6 monthly requests
+ (64.6 * 0.84 * 1.26) callback requests
= about 134 Chess.com operations
```

Version 2 replaces the per-month callback term with at most two recent annual
samples. Using 1.5 samples per completed player as a planning average gives:

```text
1 archive-list request
+ 64.6 monthly requests
+ (1.5 * 1.26) callback requests
= about 67.5 Chess.com operations
```

At 1.06-1.19 operations/second, that is approximately 57-63 fully closed
players/hour once the queue reaches steady state. A lighter future cohort
averaging 50 archive months would cost roughly 53 operations/player and close
at approximately 72-81 players/hour.

### Currently known eligible population

The earlier 24-30 hour estimate for all known eligible players included both
the visible version-1 callback backlog and callback debt that unfinished months
would continue to generate. It is superseded by the annual policy. The
250-player continuation should be profiled before publishing a replacement
whole-population forecast because its current queue already contains partially
completed histories from the prior policy.

### Reachable transitive population

The final population remains the main uncertainty. During the final 100 ms
segment:

- 21 players completed;
- 21,924 previously unseen identities were recorded;
- 33 new full-history archive jobs were created; and
- 1,666 total durable jobs were created.

The full-crawl frontier therefore grew by about 1.57 players for every player
completed during that short segment. That rate is volatile and must eventually
fall as identities overlap and the connected population saturates, but it is
currently above the break-even value of one. A finite closure time cannot be
extrapolated from the first 100 players alone.

Useful planning scenarios at an effective closure rate of 32-41 players/hour
are:

| Eventual reachable eligible players | Approximate remaining single-worker time |
| --- | ---: |
| 1,000 | 22-28 hours |
| 2,000 | 46-59 hours |
| 5,000 | 5.0-6.4 days |
| 10,000 | 10-13 days |

These are scenario calculations, not confidence intervals. Each additional
1,000 reachable eligible players adds roughly 24-31 hours at the observed
single-worker rate.

The current evidence makes **multiple days** more plausible than “a few more
hours” for true transitive closure, but it does not yet distinguish reliably
between a roughly 2,000-player and 5,000-player reachable population. Another
bounded run should measure whether newly eligible players per completion falls
below one.

## Recommended next profiling run

Resume from 100 to either 250 or 500 fully crawled players without changing
request policy. Record a snapshot every 25 completed players containing:

- fully crawled and currently eligible players;
- queued jobs by type and mode;
- newly created full-history jobs since the previous snapshot;
- completed public months and partner probes;
- logical and physical HTTP attempts;
- unique games and database bytes;
- wall time and response-size distribution.

The key convergence metric is:

```text
new eligible full-crawl jobs / newly completed full crawls
```

When that ratio stays below one and trends downward over several checkpoints,
the remaining closure time can be estimated as a shrinking queue. While it is
above one, any point estimate for the final population is structurally
unstable.

## Measurement limitations

This database supports accurate wall-clock, completion-rate, queue, response
size, and aggregate retry analysis. It does not currently retain a timing row
for every normal HTTP response. Consequently, this report cannot calculate:

- median, P90, or P99 request latency;
- the exact time split between Chess.com response wait, JSON parsing, and
  SQLite commit work;
- response-byte throughput; or
- historical queue size at arbitrary timestamps without an external snapshot.

The run's aggregate timing still bounds the upside from further pacing changes.
The 100 ms segment averaged about 0.84 seconds per completed month job, of which
only 0.10 seconds was mandatory delay. Even if all other costs stayed fixed,
removing that delay could improve throughput by only about another 14%.

For future profiling, persist aggregate latency histograms and periodic queue
snapshots rather than one event row per successful request. That would expose
P50/P90/P99 latency without materially increasing the already large database.

## Overnight continuation to 250 players

At 22:50:41 UTC on 31 July 2026, the durable run was resumed with
`--max-players 250`. This cap is the total fully crawled count, so this
continuation can add at most 150 completed players beyond the first checkpoint.

Initial safety checks found:

- exactly one crawler worker;
- approximately 91 MiB resident memory;
- 915 GiB free on the database volume;
- AC power selected by macOS; and
- an active `caffeinate` assertion preventing idle system sleep.

At the final segment's observed completion rate, the continuation should reach
250 in roughly 3-5 hours. The range allows for player-volume skew and occasional
retries.

| Failure mode | Overnight consequence | Existing protection | Residual risk |
| --- | --- | --- | --- |
| Power loss or forced termination | Current request/job interrupted | WAL transactions, UUID/job idempotency, expiring lease | Low data risk; crawl needs manual restart |
| Laptop sleep or reboot | Crawl pauses or exits | `tmux` plus current `caffeinate` assertion | No automatic restart after reboot or process crash |
| Disk exhaustion | SQLite write fails and worker exits | 250-player cap and 915 GiB free | Negligible for this bounded run |
| Isolated 429, 5xx, or network error | Request delayed or job deferred | Serial client, timeout, Retry-After, exponential retry, durable queue | Low based on the first run |
| Sustained API failure | Repeated per-job retry cycles across the queue | Per-request backoff and eventual deferral | Moderate: there is no global circuit breaker |
| Successful HTTP response with changed/malformed schema | Many jobs could be marked failed while worker continues | Per-job exception isolation and visible failed counter | Moderate completeness risk; no mass-failure threshold |
| Callback endpoint schema change | Probe jobs fail without losing public archives | Callback failures do not roll back archive ingestion | Low during this cap because full month work has higher priority |
| Hardware/database loss | Loss of an irreplaceable local dataset | SQLite durability only | Low probability, high impact without a separate backup |

The two material unattended-operation gaps are therefore not ordinary request
failure or SQLite corruption. They are:

1. **No global failure circuit breaker.** A sustained API or schema problem can
   affect many jobs before the queue becomes idle.
2. **No process supervisor or automatic restart.** `tmux` survives terminal
   disconnection, but not reboot or an unhandled process-level failure.

For a single bounded night, the run is reasonably safe because the API showed
no 429s, disk headroom is ample, and the operation is capped. Before a multi-day
closure run, add a circuit breaker (for example, stop after a short-window burst
of failed/exhausted jobs), run under systemd or another supervisor, and take an
online SQLite backup to separate storage.

## Representative queries

Run summary:

```sql
SELECT id, status,
       datetime(started_at, 'unixepoch') AS started_utc,
       datetime(ended_at, 'unixepoch') AS ended_utc,
       ended_at - started_at AS elapsed_seconds,
       counters
FROM crawl_runs
WHERE id = '8210df08-c748-4de7-9eea-ccc8740caa8a';
```

Player state and completion:

```sql
SELECT state,
       CASE WHEN full_crawl_completed_at IS NULL
            THEN 'not_full' ELSE 'full' END AS crawl_state,
       COUNT(*) AS players
FROM players
GROUP BY state, crawl_state;
```

Queue composition:

```sql
SELECT type, status, COUNT(*) AS jobs, SUM(attempts) AS attempts
FROM crawl_jobs
GROUP BY type, status
ORDER BY type, status;
```

Storage profile:

```sql
SELECT name,
       ROUND(SUM(pgsize) / 1024.0 / 1024.0, 1) AS mib
FROM dbstat
GROUP BY name
ORDER BY SUM(pgsize) DESC;
```

Recent maximum observed rating bands should always filter rating provenance:

```sql
WITH recent AS (
    SELECT gp.player_id, MAX(gp.rating) AS max_rating
    FROM game_participants gp
    JOIN games g ON g.uuid = gp.game_uuid
    WHERE gp.rating_source IN ('public', 'callback_pgn')
      AND g.end_time >= CAST(strftime('%s', '2026-07-31 22:21:11',
                                      '-1 year') AS INTEGER)
    GROUP BY gp.player_id
)
SELECT CASE
           WHEN max_rating >= 2000 THEN '2000+'
           WHEN max_rating >= 1950 THEN '1950-1999'
           WHEN max_rating >= 1900 THEN '1900-1949'
           WHEN max_rating >= 1800 THEN '1800-1899'
           WHEN max_rating >= 1600 THEN '1600-1799'
           ELSE 'below 1600'
       END AS rating_band,
       COUNT(*) AS players
FROM recent
GROUP BY rating_band;
```
