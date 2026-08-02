# Documentation map

Read these documents in this order when resuming work:

1. [`HANDOFF_2026-08-01.md`](HANDOFF_2026-08-01.md) — current state, stable
   decisions, operational boundaries, and the next-session entrypoint.
2. [`BACKUP_RECOVERY.md`](BACKUP_RECOVERY.md) — recovery contract, checked
   snapshot procedure, Zstandard boundary, restore drill, and accepted threat
   model.
3. [`BACKUP_RECOVERY_SLICE_PROMPT.md`](BACKUP_RECOVERY_SLICE_PROMPT.md) —
   historical copy-ready prompt for the completed recovery-hygiene session.
   The checked designated-directory backup and read-back restore are complete.
4. [`PLATFORM_ARCHITECTURE.md`](PLATFORM_ARCHITECTURE.md) — durable raw-to-index,
   API, publication, client-bandwidth, and failure-isolation architecture.
5. [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) — measured opening-index,
   read-API, prefetch, hosting, and deferred storage research plan.
6. [`CRAWLER.md`](CRAWLER.md) — canonical crawler architecture and policy.
7. [`CRAWL_RUN_FULL_ANALYSIS.md`](CRAWL_RUN_FULL_ANALYSIS.md) — final closure,
   database integrity, game-shape audit, move coverage, and bounded anomalies.
8. [`QUALIFICATION_CORRECTION_IMPACT_2026-08-01.md`](QUALIFICATION_CORRECTION_IMPACT_2026-08-01.md)
   — per-player read-only impact evidence and the bounded reconciliation plan.
9. [`CRAWL_RUN_250_ANALYSIS.md`](CRAWL_RUN_250_ANALYSIS.md) — historical checkpoint
   completion, reconciliation findings, and the pre-full-crawl baseline.
10. [`CRAWL_RUN_100_ANALYSIS.md`](CRAWL_RUN_100_ANALYSIS.md) — historical
   measurements and the evidence that led to sampler version 2. Treat its
   point-in-time queue tables as historical rather than current status.

The live crawler database is intentionally excluded from Git. Always query it
for current counts instead of copying figures from a dated report.
