# Documentation map

Read these documents in this order when resuming work:

1. [`CRAWL_RUN_FULL_ANALYSIS.md`](CRAWL_RUN_FULL_ANALYSIS.md) — final closure,
   database integrity, game-shape audit, move coverage, and bounded anomalies.
2. [`HANDOFF_2026-08-01.md`](HANDOFF_2026-08-01.md) — current state, stable
   decisions, operational boundaries, and the next-session entrypoint.
3. [`CRAWLER.md`](CRAWLER.md) — canonical crawler architecture and policy.
4. [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) — lossless-storage,
   opening-index, read-API, prefetch, hosting, and viewer-integration research
   plan.
5. [`CRAWL_RUN_250_ANALYSIS.md`](CRAWL_RUN_250_ANALYSIS.md) — historical checkpoint
   completion, reconciliation findings, and the pre-full-crawl baseline.
6. [`CRAWL_RUN_100_ANALYSIS.md`](CRAWL_RUN_100_ANALYSIS.md) — historical
   measurements and the evidence that led to sampler version 2. Treat its
   point-in-time queue tables as historical rather than current status.

The live crawler database is intentionally excluded from Git. Always query it
for current counts instead of copying figures from a dated report.
