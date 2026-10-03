# September opening candidate — local release packet

Status: the full-corpus parity, local browser matrix, offline transport and local
Function package are validated. Final checks passed: backend 310 after pre-commit review, frontend
541 unit / 159 component / 36 E2E, TypeScript/ESLint, production build and both
diff checks. This packet is not an upload or deployment approval. See the
[result record](OPENING_INCREMENTAL_RESULT_2026-10-03.md).

## Fixed identities and rollback

- Sole candidate: `full-position-graph-through-202609-20261003-r1-v2-a`.
- Immutable full oracle B and incremental comparison outputs remain local.
- Service project: `prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP`,
  `bughouse-opening-explorer-service`.
- Team: `team_kjpopfvj3bLNk74leLtqEgAD`, scope `aronteh-projects`.
- Canonical alias: `bughouse-opening-explorer-service.vercel.app`.
- Current known-good deployment: `dpl_AHb8E3hcTUBcv2m3VcD4ePcymjdA`,
  `bughouse-opening-explorer-service-2e4nbxohq-aronteh-projects.vercel.app`.
- Older retained fallback: `dpl_4TFjHYbjsrxVPFza8SnHwdhSJkJP`.
- Public proxy: `https://bughouse.aronteh.com/api/opening-explorer/api/meta`.
- Current public dataset: August `68a97678c3df093d243473e0844b373d669ac335`,
  6,747,980 games, packed position graph v2.

These were checked read-only on 3 October. Recheck alias and scoped environment
identities immediately before any separately approved mutation. Preserve the
August local artifacts and both recorded deployments.

## Hosting configuration checked

CLI 62.2.0, Hobby team, Fluid Compute enabled, `iad1`, basic build machine,
no Secure Compute connection or Static IP configuration returned by the project
API. Service deployment protection is `all_except_custom_domains`. Production
service-token keys exist on both service and frontend; secret values were not
exported. The frontend timeout override is Sensitive and its value remains
unverified; the checked source default is 45,000 ms and maximum is 60,000 ms.

The current [Large Functions announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3)
describes a 5-GB public beta for Node/Python on Fluid Compute, with
`VERCEL_SUPPORT_LARGE_FUNCTIONS=1` opt-in for existing projects and exclusions
for Secure Compute/Static IPs. [Build resources](https://vercel.com/docs/builds)
describes 23 GB standard build disk. The exact candidate measurements are below.
Local success is not a hosted capacity or latency measurement.

The checked Hobby plan includes 4 active CPU-hours, 360 provisioned GB-hours and
one million Function invocations per month. Waiting on I/O is excluded from active
CPU, while provisioned memory is counted during requests. These are account
allowances, not a promise that this candidate has unused quota available.
[Function usage and pricing](https://vercel.com/docs/functions/usage-and-pricing).
Hobby's default Function allocation is 2 GB / 1 vCPU; Fluid Compute's maximum
duration is 300 seconds. The bounded frontend proxy still times out sooner.
[Function memory](https://vercel.com/docs/functions/configuring-functions/memory),
[Fluid Compute](https://vercel.com/docs/fluid-compute).

Hobby also includes 6,000 build minutes and 100 GB Fast Data Transfer; the standard
build machine has 8 GB RAM / 23 GB disk, with one concurrent build and a limit of
100 deployments per day. Exhausting Hobby usage can pause service until the
allowance resets; paid overage or a plan upgrade is not authorized by this packet.
Current account-wide remaining allowances have not been measured and must be
checked before an approved upload/build. Local timings on the M3 Max are not
predictions for that smaller hosted machine.
[Hobby limits](https://vercel.com/docs/plans/hobby),
[Platform limits](https://vercel.com/docs/limits),
[Plans](https://vercel.com/docs/plans).

## Local artifacts and evidence

All paths below are local and retained. The backend working directory is
`/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer`.

| Identity / measurement | Validated value |
| --- | --- |
| Dataset/build | `137962bc5eace0f0c5ce4e50c2889d459a66087e` |
| Accepted games | 6,899,477 |
| Root node / state | 9,867,991 / 7,439,655 |
| A artifact including manifest | 3,463,810,827 bytes |
| Transport manifest | `1915d692eab62479d3b4bd8ab6b74c5531da6bd2965afa83d0b3d92e07ef5399` |
| Transport | 61 original-byte chunks, 3,463,810,827 bytes |
| Source-stage manifest | `07c628824fcb2d79c348aa004177a78e9e4af79fe21c58bb5907145f5c4c7390` |
| Source-stage bytes | 3,464,044,423 |
| Local raw Function package | 3,480,735,015 bytes |
| Headroom below 5 GB | 1,519,264,985 bytes |
| Retained local build tree | 6,989,110,473 bytes |
| Headroom below 23 GB | 16,010,889,527 bytes |
| Local runtime attestation | `f50ec95c859ae254b43a66f20cb60d728594c8b5f06d2c1ed0a89b3b561372a1` |

Artifact:
`/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/artifacts/opening/full-position-graph-through-202609-20261003-r1-v2-a`.
Exact stage:
`/private/tmp/opening-release-20261003-r1-49hgvnfv/rehearsal/stage`.
Local package copy:
`/private/tmp/opening-local-package-20261003-r1-y0amapde/build`.
Reserved future remote journal:
`/private/tmp/opening-release-20261003-r1-49hgvnfv/remote-upload-journal.json`.
That journal does not exist yet; do not copy the local receiver journal into it.

Full A/B/incremental v1 and v2 match all component and manifest bytes. The source
and both checkpoints were rehashed unchanged after export. The complete metadata
comparison, direct/proxy oracle, bounded concurrency, cancellation, desktop Chrome
and mobile WebKit matrix passed. At 32/64 simultaneous requests the unchanged
admission limit intentionally produces bounded 503 `concurrency_limit` responses;
recovery succeeds. The browser downloaded no packed/database/postings files and
sent no Authorization header. Local dummy Firebase analytics/App Check warnings
were retained separately from the successful opening responses.

The local receiver retained an incomplete 32-MiB receipt, resumed with one 64-MiB
chunk reused, survived a transient retry, reconstructed exactly, and transferred
zero bytes on completed retry. This is offline filesystem evidence, not a remote
upload or remote interruption rehearsal. Follow the main runbook's remote rehearsal
gate only after its applicable approval; no disposable remote resources are
authorized by this packet.

`vercel build --target preview` ran only in the copied local stage with dummy
credentials and process-scoped flags. CLI 62.2.0 selected Python 3.12 / x86_64 and
enabled Large Functions beta. Package measurement includes every `filePathMap`
destination plus wrappers/config, and verified all artifact hashes. Transport,
databases and dotenv files are excluded. The initial directory-only measurement
was superseded by `local-package-measurement-r2.json` in the dated operations
directory. Local build took 21.624 s; hosted build duration and transient disk/RAM
remain unmeasured. At an assumed 25 Mbps, source bytes alone imply about 18.5
minutes upload, excluding retries, overhead and the hosted build; bandwidth is
not measured. Fresh local attested startup median/p95 was 115.525/124.752 ms,
with warm OS caches; no hosted cold-start guarantee is implied.

Complete checksums, gzip reference sizes and detailed timings are in the linked
result; current plan limits and remaining-account-allowance caveats are above.

## Approval 1: upload and protected Preview

Present the completed identities and measurements above before requesting this
approval. No upload, remote interruption rehearsal, Preview creation, project
configuration mutation or paid resource is included in local preparation.

Use the exact stage and manifest ID from the local preflight. Supply a real,
separately approved short-lived Preview service credential through a mode-0600
server-side file/process environment. Never use a Sensitive redaction placeholder.
Set the non-secret process configuration:

```bash
export OPENING_EXPLORER_ARTIFACT_NAME=full-position-graph-through-202609-20261003-r1-v2-a
export VERCEL_SUPPORT_LARGE_FUNCTIONS=1
```

This exact no-execution preflight was run locally and saved as
`artifacts/opening-incremental-20261003-r1/validated-upload-preflight.json`:

```bash
PYTHONPATH=. .venv/bin/python scripts/upload_vercel_large_preview.py \
  /private/tmp/opening-release-20261003-r1-49hgvnfv/rehearsal/stage \
  /private/tmp/opening-release-20261003-r1-49hgvnfv/remote-upload-journal.json \
  --team-id team_kjpopfvj3bLNk74leLtqEgAD \
  --project-id prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP \
  --project-name bughouse-opening-explorer-service \
  --runtime-env-key OPENING_EXPLORER_SERVICE_TOKEN \
  --runtime-env-key OPENING_EXPLORER_ARTIFACT_NAME \
  --build-env-key OPENING_EXPLORER_ARTIFACT_NAME \
  --build-env-key VERCEL_SUPPORT_LARGE_FUNCTIONS
```

After explicit applicable upload/Preview approval, repeat that exact command with
these additional arguments (not run during local preparation):

```text
--create-preview --target preview
--confirm-manifest-id 07c628824fcb2d79c348aa004177a78e9e4af79fe21c58bb5907145f5c4c7390
--execute
```

Supply `VERCEL_TOKEN` and the real short-lived `OPENING_EXPLORER_SERVICE_TOKEN`
through the approved server-side secret source, never command arguments, Git,
reports or `NEXT_PUBLIC_*`. Recheck stage identity before execution. Reuse only
the same remote journal on interruption; each acknowledged source file must
match path, bytes and both digests. A local journal is not a remote receipt.

Automatic approval review earlier rejected even a no-execution preflight carrying
`--create-preview`; the allowed local preflight omitted that flag. No external
operation was attempted to bypass the rejection. The flag is reserved here for
the separately approved release step.

Record uploaded/reused bytes, immutable Preview ID, reconstruction/attestation,
Large Functions enablement, actual Function size and build headroom. Then repeat
the graph HTTP oracle and 1/8/32/64 concurrency matrix on the protected Preview.
No local filesystem-receiver measurement will be described as an upload test.
The graph oracle accepts actual server-only token files:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_hosted_opening_oracle.py \
  artifacts/opening/full-position-graph-through-202609-20261003-r1-v2-a \
  https://<new-protected-preview-host> \
  <mode-0600-preview-service-token-file> <mode-0600-protection-bypass-file> \
  --report artifacts/opening-incremental-20261003-r1/approved-preview-oracle.json
```

The host and credential-file paths cannot be filled before an approved Preview
exists. Record its immutable ID before proceeding. For concurrency, use the same
server-side Authorization and protection-bypass headers with
`benchmark_opening_http_concurrency.py`'s request adapter, or an approved local
authenticated proxy. Its bare CLI has no credential arguments; do not accidentally
benchmark the protection page. The public proxy command after approved cutover is:

```bash
PYTHONPATH=. .venv/bin/python scripts/benchmark_opening_http_concurrency.py \
  https://bughouse.aronteh.com/api/opening-explorer \
  137962bc5eace0f0c5ce4e50c2889d459a66087e \
  --node-id 9867991 --state-id 7439655 --levels 1,8,32,64 --waves 3
```

## Approval 2: Production configuration and cutover

After successful protected Preview verification, present its immutable deployment
ID and hosted results. This second approval covers updating only the service's
Production-scoped non-secret artifact selector and Large Functions flag, then
promoting the validated Preview. Preserve Vercel's existing Sensitive Production
service credential. The frontend and service credentials must remain aligned.

CLI 62.2.0 supports the following commands (not executed during preparation):

```bash
npx --yes vercel@62.2.0 env update OPENING_EXPLORER_ARTIFACT_NAME production \
  --project prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP --scope aronteh-projects \
  --value full-position-graph-through-202609-20261003-r1-v2-a --yes
npx --yes vercel@62.2.0 env update VERCEL_SUPPORT_LARGE_FUNCTIONS production \
  --project prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP --scope aronteh-projects \
  --value 1 --yes
npx --yes vercel@62.2.0 promote <validated-preview-deployment-id> --scope aronteh-projects
```

Promoting a Preview creates a new Production deployment, as confirmed by the
[current CLI documentation](https://vercel.com/docs/cli/promote). Require independent remote
reconstruction, validation, attestation and packaging with Production settings.
Record its new ID, warm `/healthz`, verify the public proxy's exact new dataset,
then repeat the bounded root/deep/filter/ending/drop/game/ETag checks.

The exact rollback alias command is:

```bash
npx --yes vercel@62.2.0 alias set dpl_AHb8E3hcTUBcv2m3VcD4ePcymjdA \
  bughouse-opening-explorer-service.vercel.app --scope aronteh-projects
```

Verify public metadata returns August `68a97678c3df093d243473e0844b373d669ac335`.
If rollback is needed after changing Production configuration, separately restore
the artifact selector to `full-position-graph-through-202608-v2` before any later
rebuild of that version; an alias move does not revert project environment values:

```bash
npx --yes vercel@62.2.0 env update OPENING_EXPLORER_ARTIFACT_NAME production \
  --project prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP --scope aronteh-projects \
  --value full-position-graph-through-202608-v2 --yes
```

The two bounded frontend layout fixes are local changes for review and commit.
They require a separately authorized frontend release if they are to become live;
the backend artifact cutover does not deploy them. Current frontend rollback is
`dpl_Bo84JDKmwBjEg2jcBW4sAtNBy1j6` on project
`prj_UZ9keRku6D5IQXQk48VQZtX8htBl`; recheck that identity at any later release.

No cleanup deletion, commit or push is included in either approval. Retained
snapshots, checkpoints, source artifacts and rollback deployments remain intact.
