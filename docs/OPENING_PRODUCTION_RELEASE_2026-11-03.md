# October-only opening-tree Production release — 3 November 2026

The user explicitly authorized direct Production upload and skipped Preview for
this release. This supersedes the Preview sequencing in the monthly release
runbook for this operation only. No Git commit/push, new crawl, November games,
deletion or paid resource upgrade is included.

Prepared candidate and preflight: [2 November report](OPENING_UPLOAD_PREFLIGHT_2026-11-02.md).
Acceptance: [incremental result](OPENING_INCREMENTAL_RESULT_2026-11-02.md).

Dataset `dbcc296735e87541e82e1f2cdac06a5c17e61174`, 7,019,712 games, analysis
cutoff `end_time < 1793491200`. Exact stage manifest:
`404d54eeca634d7ff0b9f89c3a4e2f40e6c9743cc26b15214f90149398b54b80`.
The service project is `prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP`, team
`team_kjpopfvj3bLNk74leLtqEgAD`. The prior READY Production deployment
`dpl_44ZU71gqyfbXAp6R6PNmFRSdTLpL` is retained for rollback.

Status: **READY and public API verified**. Production deployment
`dpl_FtPiXcRpz5sBKFbzHZAqGDEDuyrL` owns both service Production aliases. Evidence is in
`artifacts/opening-production-20261103-r1/`, with the resumable remote journal at
`/private/tmp/opening-release-20261102-r1/upload.journal`.

The initial access token was expired: all five attempts at the first five-byte
file were rejected with HTTP 403 before acknowledgement. An authenticated CLI
request refreshed the session; the second run resumed the exact journal.
Credentials remain local/in memory and are not printed or embedded in the source.
Production inherits its existing service secret; only the exact artifact name
and Large Functions build opt-in are supplied as non-secret overrides.

The source and Function-package validation are local evidence. No independent
full rebuild parity was performed, per the revised policy. Account quota and
content-addressed source retention remain preflight limitations. A direct
Production release exposes traffic before the live checks; the retained rollback
remains available. No Preview was created.

The user requested no browser checks and will inspect the live UI personally.
A baseline browser opened before that instruction was closed immediately; no
post-deployment browser verification is claimed. Deployment logs and public API
oracle checks remain in scope.


## Completed release evidence

All 84 files / 3,526,568,287 bytes were acknowledged. The successful upload run
had zero retries; the earlier expired-token failure is retained separately.
Remote CLI 65.4.0 / Python 3.12 reconstructed all 3,526,334,311 artifact bytes,
reported complete validation and emitted attestation
`01d0dc62e1d411712f4905288ce65ed46aca61475bd4f6bf285f98a8547afb18`, matching the
local build. Logs explicitly enabled Large Functions and completed deployment.
No project-level environment variable was changed: the deployment overrides
select the October artifact, and the existing Production secret is inherited.
Future deployments must also explicitly select their candidate; the project-level
artifact default was not promoted by this release.

The public frontend metadata reports the exact October source fingerprint,
dataset `dbcc296735e87541e82e1f2cdac06a5c17e61174`, 7,019,712 games, root node
10,042,268 and root state 7,571,232. All 17 public-proxy oracle cases passed:
metadata, root/deep/ending/drop responses, white/black/pair/missing-player filters,
autocomplete, source games, stale/invalid IDs, hard caps and conditional GET.
Decoded response bytes and status codes match the local artifact. Validators
carry the same SHA-256 digest; the public proxy may prefix them with `W/`.
Each side's conditional request returns empty-body 304 with the matching digest.

The first strict direct-service-style oracle failed exact ETag comparison only;
all data bodies/statuses matched. An identity-encoding retry still encountered
weak validators, while gzip header evidence confirmed CDN weakening. Those
reports are retained, not relabelled passes. The final report explicitly tests
the public-proxy contract and preserves raw validator values:
`artifacts/opening-production-20261103-r1/public-proxy-oracle.json`.
It is not a protected-runtime concurrency benchmark or browser test.

The user reports that the UI is loaded and ready. Agent browser checks were
stopped at the user's request. Production is ready for the user's own UI review.
No rollback, deletion, commit or push was performed. The machine-readable
closeout is `artifacts/opening-production-20261103-r1/final-production-result.json`.

Operational lessons and remaining automation work are recorded in the
[cycle review](MONTHLY_UPDATE_REVIEW_2026-11-03.md).
