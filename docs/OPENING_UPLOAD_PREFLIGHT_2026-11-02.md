# October-only opening-tree upload preflight — 2 November 2026

Historical preflight. Subsequent explicitly authorized direct Production release:
[3 November result](OPENING_PRODUCTION_RELEASE_2026-11-03.md). Pending statements
below describe the preflight date, not the current deployment status.

Scope: local preparation and read-only hosting inspection only. No files were uploaded,
no deployment or environment was created/changed, and Production remains untouched.
The user-authorized incremental-integrity-v1 acceptance remains the corpus gate;
independent full rebuild comparisons were intentionally cancelled, not passed.

## Candidate and transport

- Candidate: `artifacts/opening/incremental-position-graph-through-202610-20261101-october-only-r3-v2`.
- Dataset: `dbcc296735e87541e82e1f2cdac06a5c17e61174`; 7,019,712 games.
- Source cutoff: `end_time < 1793491200`; no November games. Source hash and lineage are in `docs/OPENING_INCREMENTAL_RESULT_2026-11-02.md`.
- Candidate including manifest: 3,526,334,311 bytes; 61 parts of at most 64 MiB.
- Transport manifest: `7fbc74f9beecd6f13b74f9689e2d27a3934a7abbee5ca44e5d66849e400945ad`.
- Stage: `/private/tmp/opening-release-20261102-r1/rehearsal/stage`.
- Stage manifest: `404d54eeca634d7ff0b9f89c3a4e2f40e6c9743cc26b15214f90149398b54b80`.
- Upload payload: 84 files, 3,526,568,287 bytes. Exact inventory checked; no databases, snapshots, credentials, repository history or unrelated artifacts.
- Dry-run transfer estimate: 1,128.5 seconds (18.8 minutes) at 25 Mbps, excluding retries and remote build/verification. This is an assumed connection speed, not a measurement.

The offline rehearsal passed repeated deterministic manifests, component hashes,
complete reconstruction validation, interruption after one acknowledged chunk,
one transient retry, reuse of the acknowledged chunk, and a completed journal
retry that transferred zero bytes and reused all 61 parts. Partial receipts and
all logs are retained. The local rehearsal journal must never be reused as a
remote upload journal.

Evidence: `artifacts/opening-upload-20261102-r1/` contains the dry-run,
component manifest, rehearsal result, connector inspection and package logs.
The full chunks, receiver and reconstruction remain under the temporary release
root above. Keep them until separately authorized cleanup.

## Live hosting observations and limitations

The connector confirmed team `team_kjpopfvj3bLNk74leLtqEgAD`, service project
`prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP`, region `iad1`, and deployment protection
`all_except_custom_domains`. The canonical service alias currently resolves to
READY Production deployment `dpl_44ZU71gqyfbXAp6R6PNmFRSdTLpL`, the retained
rollback target. Refresh this identity immediately before a later mutation.

Production `VERCEL_SUPPORT_LARGE_FUNCTIONS` is `1`. The staged configuration
sets `fluid: true`, region `iad1`, and the exact incremental artifact include
boundary plus runtime attestation. The service token is Sensitive and currently
Production-scoped; a protected Preview needs a real approved server-side
credential source, not a pulled redaction placeholder. No secret was decrypted
or exported. Frontend origin/timeout values are also Sensitive and remain
unverified; the source timeout default is 45 seconds with a 60-second maximum.

After the user authenticated, CLI 65.9.0 successfully rechecked the account:
Hobby plan, basic build machine, service Fluid Compute enabled, and no Secure
Compute connection or Static IP configuration returned. Both project IDs and
Production targets match the connector inspection. The earlier failed credential
checks remain retained as diagnostic history.

The exact staged-source local build passed in 173.2 seconds. The deployed
Function file map contains 525 mapped files plus its wrapper/config, totaling
**3,537,974,762 bytes**, with **1,462,025,238 bytes** below 5 GB. Every declared
artifact component was hash-verified in the package; transport parts and databases
are excluded. Build-tree disk consumption was 7,117,327,998 bytes, below the
conservative 23-GB budget. Use `local-package-measurement-r2.json`; the earlier
directory-only measurement omits externally mapped files and is superseded.
A first local build was interrupted while materializing silently; its files/logs
are retained, and a fresh copy completed successfully. No corpus was rebuilt.

Current [Function limits](https://vercel.com/docs/functions/limitations) document
5-GB Large Functions on Fluid Compute with Active CPU, including Python; Secure
Compute and Static IPs are excluded. [Hobby documentation](https://vercel.com/docs/plans/hobby)
lists 32-GB build disk, whereas older [build resource documentation](https://vercel.com/docs/builds)
lists 23 GB; the package check conservatively uses 23 GB. The authenticated `vercel usage --json` request returned billing data unavailable
for 1–2 November; this is not zero usage. Account allowance headroom remains
unverified. Content-addressed source retention is also undocumented and has not
been established by this preflight. No paid resources or upgrades are authorized.

## Remaining release sequence

Local package measurement and authenticated account configuration checks passed.
Confirm remaining account usage and the Preview credential source before release.
Then obtain separate authorization for the runbook's external rehearsal/upload
and protected Preview, verify its remote reconstruction, Large Functions logs,
HTTP oracle and frontend behavior, and obtain separate Production authorization.
This prepared stage does not itself grant any release permission. Production
promotion/rebuild and its checks remain a later operation.

The next upload is prepared but not executed. Use a fresh remote journal at
`/private/tmp/opening-release-20261102-r1/upload.journal`; it does not exist yet.
Do not use the local build copy or its dummy credential fixture as the upload
source. Use the unchanged validated stage and the exact stage manifest above.

Backend source commit: `39dfc7d996405ffc641ab03ced76c936a8ccc86e`.
Frontend source commit: `ee49640d96bbaf721a57bab19483d92b634ae5a0`.
Only this dated report was added to tracked-source scope; operational evidence
is under the ignored artifact directory. No commits or pushes were made.
