# 250-player crawl and reconciliation analysis

Run `8210df08-c748-4de7-9eea-ccc8740caa8a` stopped cleanly at its configured
limit on 1 August 2026. This is the final bounded checkpoint before the
uncapped seed-reachable closure crawl.

## Checkpoint result

| Metric | Value |
| --- | ---: |
| Marked lifetime crawls | 250 |
| Canonical boards | 7,343,178 |
| Public / callback-only boards | 7,343,169 / 9 |
| Participant rows | 14,686,356 |
| Completed jobs before reconciliation | 33,340 |
| Public / callback requests | 33,245 / 121 |
| Database bytes | 13,557,141,504 |
| HTTP retries / recoveries | 16 / 9 |
| HTTP 429 responses | 0 |

The database passed `PRAGMA quick_check` and foreign-key validation. Every
board has exactly two participant rows, no malformed Bughouse record was
persisted, and all 424 sampler-v2 selections passed source, owner, year, cutoff,
and durable-job invariants. Those v2 probes remain queued, so scheduling—not
live v2 callback yield—was verified at this checkpoint.

From completion 100 through 250, 101 new full archive-list jobs were created:
a frontier ratio of `101 / 150 = 0.673`. This is below one but needs repeated
uncapped checkpoints before convergence can be claimed.

## August completion defect

On the August resume, a mutable August refresh row was queued for each eligible
player. For 335 players it remained pending when the last full-history month
finished, so the completion predicate correctly declined at that moment. Every
one of the 335 later finished its August maintenance job, but the monthly path
did not re-run lifetime completion.

The repair stores the exact full archive-list month manifest separately from
maintenance months. Reconciliation deliberately did not mark all 335 from
counts alone: 299 appeared complete, while 36 had fewer ledger rows than their
earlier archive-list count. All received a fresh authoritative archive-list
check.

## Terminal outcomes and reconciled queue

Five public month 404s and one full archive-list 404 are now explicit terminal
records with the original error and timestamp retained. After migration and
idempotent reconciliation:

| Queue/outcome | Count |
| --- | ---: |
| Queued full archive-list jobs | 786 |
| Queued full month jobs | 1 |
| Queued sampler-v2 probes | 424 |
| Failed / leased / deferred jobs | 0 / 0 / 0 |
| Terminal unavailable months | 5 |
| Terminal unavailable archives | 1 |

The closure audit remains intentionally incomplete while 1,211 durable jobs
and 755 eligible players without a final outcome remain.
