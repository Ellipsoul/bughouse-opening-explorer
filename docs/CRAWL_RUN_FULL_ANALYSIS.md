# Full player crawl and data-quality analysis

Bootstrap run `8210df08-c748-4de7-9eea-ccc8740caa8a` reached durable
seed-reachable closure on 1 August 2026. This report records the final crawl
state and a read-only audit of `data/crawler.db` before any derived opening
index is built.

The crawler database is intentionally excluded from Git. These figures are a
dated evidence snapshot, not a replacement for querying the live database.

The two qualification anomalies recorded below were corrected after this
historical audit. See
[`QUALIFICATION_CORRECTION_IMPACT_2026-08-01.md`](QUALIFICATION_CORRECTION_IMPACT_2026-08-01.md)
and [`HANDOFF_2026-08-01.md`](HANDOFF_2026-08-01.md) for the read-only impact
evidence, bounded reconciliation, and current cohort counts.

## Executive summary

- The run is `complete`: all durable jobs are complete, with no queued, leased,
  deferred, or unresolved failed work.
- The final database contains 8,195,984 canonical Bughouse boards and exactly
  16,391,968 participant rows.
- The 1,015 eligible players have a final outcome: 1,014 completed lifetime
  crawls and one explicitly unavailable archive.
- SQLite `PRAGMA quick_check` returned `ok`; a complete foreign-key scan found
  zero violations.
- Every board has exactly one white and one black participant. Public records
  reproduce their raw Chess.com JSON with zero normalized-field mismatches.
- 7,132,391 boards (87.02%) contain usable TCN moves, comprising 325,470,732
  encoded plies. A complete syntax scan found no malformed TCN strings.
- The remaining 1,063,593 boards have an empty move list in the source data.
  They remain valid raw game records but cannot contribute moves to an opening
  index.
- The database is a sound raw-data foundation. The audit found two eligibility
  edge cases, 250 older completions without the new manifest provenance, six
  explicitly unavailable month endpoints, and a small set of faithfully stored
  upstream anomalies. These are bounded and documented below.

Coverage still means transitive closure from the approved seeds. Chess.com has
no global Bughouse feed, so this result cannot prove that a disconnected player
population does not exist.

## Run outcome

| Metric | Value |
| --- | ---: |
| Run id | `8210df08-c748-4de7-9eea-ccc8740caa8a` |
| Started (UTC) | 2026-07-31 19:40:45 |
| Ended (UTC) | 2026-08-01 17:51:29 |
| Start-to-end interval, including pauses | 22 h 10 m 44 s |
| Run status | `complete` |
| Completed durable jobs | 52,890 |
| Queued / leased / deferred / failed jobs | 0 / 0 / 0 / 0 |
| Fully crawled players | 1,014 |
| Terminal archive-unavailable players | 1 |
| Public / callback requests | 52,175 / 2,232 |
| HTTP 5xx / network errors | 11 / 7 |
| HTTP retries / recoveries | 18 / 10 |
| Slow successful responses | 2 |
| Canonical boards | 8,195,984 |
| Participant rows | 16,391,968 |
| Database bytes | 15,145,734,144 (about 14.1 GiB) |

The run was deliberately stopped and resumed at bounded checkpoints, so the
start-to-end interval is not continuous worker runtime. Explicit resume kept
the original lower eligibility cutoff of `2025-07-31 19:40:45 UTC`.

The historical `job_failed` events comprise six public month 404s. Migration
0003 and reconciliation converted those into audited terminal outcomes, so no
failed work remains unresolved at closure.

## Growth after the 250-player launch checkpoint

The checked pre-launch backup
`data/crawler-ready-for-full-crawl-20260801.db` provides the comparison point.

| Metric | Pre-launch | Final | Change |
| --- | ---: | ---: | ---: |
| Canonical boards | 7,343,178 | 8,195,984 | +852,806 |
| Public boards | 7,343,169 | 8,195,423 | +852,254 |
| Callback-only boards | 9 | 561 | +552 |
| Participant rows | 14,686,356 | 16,391,968 | +1,705,612 |
| Discovered players | 227,021 | 247,274 | +20,253 |
| Eligible players | 1,006 | 1,015 | +9 |
| Completed lifetime crawls | 250 | 1,014 | +764 |
| Resolved partner links | 121 | 2,232 | +2,111 |

Across 49,269 completed player-month ledger rows, the crawler observed
10,377,847 Bughouse board occurrences. UUID upserts reduced those overlapping
archive observations to 8,195,984 canonical records, collapsing approximately
21% of the occurrences. This is the expected shape when two qualified players
appear in the same games and their archives overlap.

## Database integrity and canonical game shape

The audit opened SQLite with `mode=ro`, `immutable=1`, and `query_only=ON`.
It performed no writes.

| Check | Result |
| --- | ---: |
| `PRAGMA quick_check` | `ok` |
| Foreign-key violations | 0 |
| Participant rows minus twice the board count | 0 |
| Non-Bughouse records | 0 |
| Missing or malformed UUIDs | 0 |
| Invalid raw JSON documents | 0 |
| Invalid content-hash lengths | 0 |
| Missing URLs | 0 |
| Missing end timestamps | 0 |
| Boards before the supported Bughouse period | 0 |
| Boards timestamped after run completion | 0 |

A `games` row is one board, not an entire two-board Bughouse match. Each board
has a canonical Chess.com UUID and two participant rows, one for each color.
The earliest stored board ended at `2016-09-08 00:11:55 UTC`; the latest ended
at `2026-08-01 12:33:20 UTC`.

All 8,195,423 public boards were compared to their retained raw payloads. The
stored UUID, end time, time control, time class, rated flag, rules, TCN, initial
setup, FEN, URL, and derived numeric id had zero mismatches. The normalized
username, rating, result, and rating source for both participant colors also
had zero mismatches.

Every board uses the same standard initial setup. The source-provided `fen`
field contains 6,489,696 distinct position strings, which is plausible for the
large and varied game corpus.

## Move-data suitability

| Metric | Value |
| --- | ---: |
| Boards with non-empty TCN | 7,132,391 |
| Share of all boards with moves | 87.02% |
| Encoded plies | 325,470,732 |
| Mean plies among boards with moves | 45.63 |
| Encoded drops | 72,259,548 |
| Encoded promotions | 1,864,988 |
| Boards with empty TCN | 1,063,593 |

The complete TCN corpus, rather than a sample, was streamed through a syntax
validator. All non-empty strings:

- have an even character count;
- use only the expected Chess.com TCN alphabet;
- use valid origin and destination markers; and
- contain no invalid drop or promotion encodings.

A second test selected 89,101 boards distributed by SQLite row id and replayed
up to the first 40 plies of each with the current decoder and board engine. It
replayed 2,997,411 plies with zero exceptions.

Chess.com supplied an empty TCN for 1,063,508 public boards and 85 callback
boards. It supplied no alternative PGN or callback move list for those rows.
Their result pairs are dominated by resignation, partner-board loss, and
abandonment. These rows should stay in raw storage and metadata analyses, but a
derived opening index must skip them and disclose its 87.02% move-data coverage.

## Population and workload shape

| Player state | Players | Players appearing in boards | Participant rows |
| --- | ---: | ---: | ---: |
| Candidate | 245,106 | 245,106 | 4,654,425 |
| Dormant | 1,153 | 1,153 | 1,357,695 |
| Eligible | 1,015 | 1,014 | 10,379,848 |
| **Total** | **247,274** | **247,273** | **16,391,968** |

The one non-participating identity is the archive-unavailable account described
under eligibility anomalies.

Player activity is strongly right-skewed:

| Participation level | Players |
| --- | ---: |
| Exactly one board | 116,100 |
| At least 10 boards | 35,360 |
| At least 100 boards | 7,825 |
| At least 1,000 boards | 1,684 |
| At least 10,000 boards | 319 |

The mean is 66.3 boards per participating player. The largest histories are
much bigger: `outrunyou` appears in 150,242 boards, `hopefulwin` in 141,437,
and `jarlcarlander` in 112,155. Almost every canonical board touches at least
one currently eligible player, which is consistent with building the dataset
as the union of qualified-player archives rather than from a global feed.

Annual board counts rise plausibly with Chess.com Bughouse activity and the
incomplete current year:

| Year | Boards | Empty TCN |
| --- | ---: | ---: |
| 2016 | 102,126 | 26,010 |
| 2017 | 211,031 | 29,731 |
| 2018 | 399,056 | 49,352 |
| 2019 | 686,310 | 83,985 |
| 2020 | 830,454 | 99,366 |
| 2021 | 855,433 | 114,296 |
| 2022 | 881,907 | 117,599 |
| 2023 | 910,841 | 112,861 |
| 2024 | 1,121,354 | 140,828 |
| 2025 | 1,421,612 | 171,721 |
| 2026 through 1 August | 775,860 | 117,844 |

August 2026 is deliberately a partial mutable-month snapshot: it contains
1,696 boards through the initial full-crawl refresh and must be refreshed by
normal monthly maintenance.

## Partner-board structure and sampler audit

The final database contains 2,232 directed `partner_uuid` links, all of which
resolve to an existing board. There are no self-links or dangling targets.

| Relationship | Directed links | Unique board pairs |
| --- | ---: | ---: |
| Reciprocal public/callback | 1,122 | 561 |
| Reciprocal public/public | 40 | 20 |
| One-way public/public | 1,070 | 1,070 |
| **Total** | **2,232** | **1,651** |

The one-way links faithfully reproduce public records where the source names a
partner board but the target has no reverse reference. Derived match grouping
should therefore treat a resolved partner relationship as undirected instead
of requiring reciprocity.

Sampler version 2 persisted 1,557 deterministic annual selections: 781 for
2025 and 776 for 2026. All selections passed the following invariants:

- the sample owner participates in the selected board;
- the stored sample year matches the board timestamp;
- the board is not older than the persisted eligibility cutoff; and
- a completed durable partner-probe job exists for the selected board.

The 1,653 completed probe jobs consist of these 1,557 version-2 samples plus 96
completed probes retained from sampler version 1.

## Known completeness gaps

### Terminal archive outcome

`thanithailand2024` has an explicit terminal archive-list 404:

```text
https://api.chess.com/pub/player/thanithailand2024/games/archives
```

The account is eligible in the current data but has no stored board
participation. This is also an eligibility-evidence anomaly, described below.
The closure audit correctly treats this as an unavailable archive rather than
claiming a completed lifetime crawl.

### Terminal month outcomes

Six public month endpoints returned HTTP 404 and are stored as terminal
`month_unavailable` outcomes:

| Player | Month | Boards recovered through other players |
| --- | --- | ---: |
| `akewjon` | 2025-07 | 23 |
| `crosky` | 2016-09 | 86 |
| `dielie` | 2018-03 | 350 |
| `flubs` | 2018-02 | 6 |
| `thanithailand2024` | 2026-07 | 0 |
| `thanithailand2024` | 2026-08 | 0 |

Games for the first four slices were encountered through opponents' archives,
but those months cannot be certified complete. Their presence reduces the
practical hole; it does not make the unavailable owner endpoint authoritative.

### Pre-migration completion provenance

The first 250 lifetime completions predate migration 0003. They have:

- a completed archive-list job;
- at least one completed player-month row; and
- no unresolved month ledger row.

They do not have `full_archive_list_fetched_at` or rows in
`player_archive_month_manifest`, because those provenance structures did not
yet exist. The later 764 completions all use the authoritative manifest and
have no unresolved manifest month.

This is an auditability gap, not evidence that those 250 histories are
incomplete. If uniform provenance becomes a hard requirement, a later
read-before-write reconciliation can refresh their archive lists and populate
manifests without deleting stored games.

## Eligibility anomalies

### Misattributed qualification: `thanithailand2024`

The account is marked eligible at rating 2024 with qualifying game
`67e713ba-9130-11f0-970f-a0369feff220`, dated 14 September 2025. However, that
board's actual participants are `coerced` at 2013 and `anhhungcodoc` at 2024.
`thanithailand2024` does not participate in that board—or any stored board.

The qualifying pointer therefore borrowed another participant's rating. This
affects one player classification and the reported eligible count, but it does
not corrupt the referenced board or its participant records. The account's
archive is independently unavailable with HTTP 404.

### Missing upper evaluation bound: `esquie-33`

The run began at `2026-07-31 19:40:45 UTC`. `esquie-33` first reached the
inclusive threshold of 2000 at `19:50:39 UTC`, ten minutes after that fixed
evaluation timestamp. Earlier stored ratings are below 2000.

Explicit resume preserves the lower cutoff but the current eligibility helper
does not enforce `end_time <= run_started_at`. Under a strict window anchored
to the original evaluation instant, this player is one extra inclusion. The
effect is conservative over-collection—the player's history is present—not
missing raw game data.

## Faithfully retained upstream anomalies

The following values are unusual but match the retained Chess.com JSON exactly:

- 53 public boards between 25 January and 19 February 2025 name the same
  account as both white and black, across 23 accounts.
- 131 participant observations across 20 accounts have ratings above 4000.
  The maximum is 7933, from the account `Bug10K` in March 2020.
- 188 participant observations across seven accounts have a rating of zero.

These rows should remain losslessly stored. Derived products can define and
document their own quality filters rather than rewriting the raw evidence.

## Audit conclusion

The full crawl achieved truthful durable closure and produced a coherent raw
dataset. The physical database, relational structure, normalization, UUID
de-duplication, participant cardinality, move encoding, partner resolution,
and deterministic sampler all passed their audits.

Before building production derived data, the recommended follow-up work is:

1. correct the qualification-owner attribution path exposed by
   `thanithailand2024`;
2. enforce both lower and upper bounds for a fixed eligibility window;
3. decide whether to backfill authoritative manifests for the 250 legacy
   completions;
4. encode the six terminal month gaps and 87.02% move-data coverage into
   derived-data provenance; and
5. define explicit downstream policies for empty TCN, self-opponent boards,
   implausible ratings, and one-way partner links.

None of those findings requires discarding or re-crawling the healthy canonical
game corpus.
