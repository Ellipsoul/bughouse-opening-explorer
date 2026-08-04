# Vercel Large Function transport and preflight result — 4 August 2026

> Historical preflight: the gates recorded below were subsequently resolved
> and the full artifact was deployed. See
> [`VERCEL_LARGE_FUNCTION_PRODUCTION_RESULT_2026-08-04.md`](VERCEL_LARGE_FUNCTION_PRODUCTION_RESULT_2026-08-04.md)
> for the authoritative upload, Production, validation, cost, cleanup, and
> rollback result. This document preserves the evidence available before the
> first external upload.

## Decision

The deterministic transport, local reconstruction, upload journal, retry, and
Vercel build-materialization boundaries are implemented and tested. Artifact A
was split into 44 deterministic 64-MiB-or-smaller source chunks, reconstructed
byte-for-byte, checksum-verified, and accepted by the complete artifact
validator. No full build was rerun.

The slice is stopped before the first external upload. Two Vercel behaviors
remain undocumented or inconsistent with the current local tooling:

1. Vercel documents remote Large Functions up to 5 GB, but Vercel CLI 54.12.2
   with bundled `@vercel/python` 6.44.1 rejects the measured 2,423.77-MiB full
   Python bundle at the old 500-MB local packaging boundary. Setting the
   documented `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` in the disposable local
   Preview environment and process environment did not change that result.
2. Vercel documents deployment deletion, but not the retention or explicit
   deletion semantics of content-addressed source files previously submitted
   to `/v2/files`.

The representative rehearsal must not upload until Vercel support answers the
source-retention question. The full artifact must not upload until support also
confirms that this post-enrolment Hobby project will use the 5-GB Python Large
Functions path despite the local-builder result.

No Vercel deployment, source file, environment variable, project setting,
Blob store, paid resource, alias, domain, or Production origin was created or
changed. Production still returns representative dataset
`e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03` through the frontend proxy. Direct
access to the representative service deployment still redirects to Vercel
Authentication.

## Repository and live-state reconciliation

Both repositories began clean and matched their remote `main` branches:

| Repository | Local and `origin/main` commit | Result |
| --- | --- | --- |
| `bughouse-opening-explorer` | `ba5c0d3` | transport work is local and uncommitted |
| `bughouse-chess` | `64238a6` | unchanged and still clean |

Read-only Vercel inspection found:

- team `aronteh-projects`, Hobby plan;
- opening-service project
  `prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP`, created 3 August 2026;
- Fluid Compute enabled, default Function region `iad1`;
- Vercel Authentication protection set to all deployments except custom
  domains;
- retained representative Production deployment
  `dpl_EFQgMysFNBRqQRqZctoMYtp8Pvar`, with a 32.37-MB recorded Function;
- frontend project `prj_UZ9keRku6D5IQXQk48VQZtX8htBl`, with its Production
  deployment still at commit `64238a6`; and
- frontend Production proxy metadata still reporting 91,911 representative
  games, not the full dataset.

Artifact A and immutable oracle B both passed complete structural validation
at build and dataset version
`1e876810b96364e4bf9f23d49fb509a843783253`. Their eight included files remain
component-identical. The live crawler database was not opened, served, or
modified.

## Refreshed official limits and costs

These sources were refreshed on 4 August 2026. Documented guarantees are kept
separate from local observations and inferences.

| Boundary | Current documented value | Consequence |
| --- | --- | --- |
| Large Function package | Node and Python packages up to 5 GB on Fluid Compute; public beta; new projects automatically enrolled | The approximately 2.54-GB full package is nominally eligible, subject to the support gate below. [Official announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3) |
| Existing-project opt-in | `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`, scopeable to Preview | The project post-dates automatic enrolment. Do not add the variable unless Vercel says it is required and the mutation is separately approved. [Official announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3) |
| Restrictions | Fluid Compute required; Secure Compute and Static IPs unsupported | Current project has Fluid enabled and neither excluded feature was observed. [Official announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3) |
| CLI source file | Hobby 100 MB; Pro 1 GB | Fixed 64-MiB chunks remain below the Hobby per-file limit. [Vercel limits](https://vercel.com/docs/limits) |
| Remote build | 45-minute maximum, 23-GB build disk; Hobby standard build memory is documented as 8 GB | Chunk input plus reconstruction needs 5,049,937,098 bytes before packaging, leaving substantial nominal disk headroom. [Builds](https://vercel.com/docs/builds) and [limits](https://vercel.com/docs/limits) |
| Fluid Hobby Function | 2 GB / 1 vCPU, 300-second maximum duration, 1,024 shared file descriptors | Recorded local 522-MB peak RSS fits memory. The generated Function uses a 300-second cap. [Function limits](https://vercel.com/docs/functions/limitations) |
| Request or response body | 4.5 MB | Existing 256-KiB default and 512-KiB hard response caps remain unchanged. [Function limits](https://vercel.com/docs/functions/limitations) |
| Region | `iad1` is explicitly configured | Matches the inspected project and representative deployment. [Regions](https://vercel.com/docs/functions/configuring-functions/region) |
| Hobby Fluid usage | 4 active CPU-hours, 360 GB-hours provisioned memory, and 1 million invocations included; no Hobby on-demand rate | The rehearsal has no separately documented dollar charge if it remains within the team's limits, but it consumes the shared allowances and Hobby can pause rather than bill overage. [Fluid pricing](https://vercel.com/docs/functions/usage-and-pricing) |

Vercel does not publish a separate price for digest source upload or a single
Hobby Preview build. Therefore the exact documented incremental bill for the
preferred rehearsal is **$0 within Hobby allowances**, not a guarantee of zero
resource consumption or uninterrupted availability.

### Blob fallback

Blob is not currently usable for this artifact on Hobby: Hobby includes 1 GB
of storage and blocks access after the limit rather than charging overage. A
full 2.525-GB store therefore requires an approved Pro upgrade or another paid
provider. Current Pro starts at **$20/month** with one deploying seat and $20
of usage credit. Current Blob rates are $0.023/GB-month storage, $5 per million
advanced operations, and $0.05/GB downloaded after plan allowances.

Using the same 44 parts across eight component uploads would count 60 advanced
operations: eight starts, 44 parts, and eight completions. The full artifact's
storage above the 1-GB headline allowance is 1.525 GB, or approximately
**$0.035/month** at $0.023/GB-month before proration, normally inside Pro's
credit. Multipart retries only failed parts; deletion is free. Provisioning a
store, upgrading the plan, and uploading remain unapproved. See
[Blob pricing](https://vercel.com/docs/vercel-blob/usage-and-pricing),
[multipart behavior](https://vercel.com/docs/vercel-blob), and
[Pro pricing](https://vercel.com/docs/plans/pro-plan).

## Deterministic transport identity

The transport includes the seven packed components and `manifest.json`.
Component bytes are 2,524,966,683; including the 1,866-byte artifact manifest,
the transported artifact is **2,524,968,549 bytes**.

| Component | Bytes | Parts |
| --- | ---: | ---: |
| `edges.bin` | 69,751,332 | 2 |
| `endings.bin` | 470,456 | 1 |
| `game_offsets.bin` | 52,131,832 | 1 |
| `games.bin` | 1,892,357,989 | 29 |
| `manifest.json` | 1,866 | 1 |
| `nodes.bin` | 418,508,028 | 7 |
| `postings.bin` | 78,197,736 | 2 |
| `postings.json` | 13,549,310 | 1 |

- chunk size: 67,108,864 bytes;
- chunk count: 44;
- transport manifest:
  `7707808909de37e964bed117d21eb5484fd898cbdf7d5af12b471c1db54d6622`;
- final staged-source manifest:
  `f88e99444da9f86fb91d62cfb92e3282445cb9edb530aa6790c447070a6b8d1a`;
- staged Vercel source: 64 files and **2,525,091,423 bytes**;
- local chunk plus reconstruction space: 5,049,937,098 bytes;
- local peak including retained source: 7,574,905,647 bytes;
- observed free disk before the full Vercel build rehearsal: more than 919 GB;
- local open-file limit: 1,048,575.

The full offline rehearsal wrote every chunk, reconstructed all eight files,
ran the complete structural validator, and produced no `diff -rq` difference
from artifact A. Artifact B was compared read-only and never staged.

The final dry-run upload command re-hashed all 64 staged inputs and returned
without creating a journal or opening a network connection. Its raw transfer
duration, excluding retries and build, is:

| Sustained upstream | Raw duration |
| ---: | ---: |
| 10 Mbit/s | 2,020.073 s / 33.67 min |
| 25 Mbit/s | 808.029 s / 13.47 min |
| 50 Mbit/s | 404.015 s / 6.73 min |
| 100 Mbit/s | 202.007 s / 3.37 min |

## Implementation and TDD evidence

The repository now contains:

- `bughouse_explorer/opening/vercel_transport.py`: canonical manifests,
  allowlisting, split/reconstruct validation, append-safe journal, bounded
  retry, and exact staged-input validation;
- `bughouse_explorer/opening/vercel_file_api.py`: streaming `/v2/files`
  uploads, explicit simulated mid-file interruption, and unaliased Preview
  creation;
- `bughouse_explorer/opening/vercel_stage.py`: deterministic minimal source
  staging, build-time materialization, and Function include/exclude controls;
- `scripts/prepare_vercel_transport.py`,
  `scripts/materialize_vercel_transport.py`,
  `scripts/stage_vercel_large_preview.py`, and
  `scripts/upload_vercel_large_preview.py`; and
- focused tests in `tests/test_vercel_transport.py`,
  `tests/test_vercel_file_api.py`, and `tests/test_vercel_stage.py`.

Red/green tests cover deterministic ordering, exact and short final parts,
empty inputs, missing/extra/duplicate/reordered/truncated/oversized/corrupt
chunks, wrong source size/hash, wrong component hash, artifact-B and unrelated
artifact rejection, snapshot/backup rejection, journal restart, torn-tail
recovery, idempotent retry, reused acknowledgements, wrong remote digest,
staged-input missing/extra/corrupt rejection, streaming API requests, unaliased
Preview construction, and byte-exact representative reconstruction.

The complete Python suite passes: **164 tests**.

## Vercel materialization observations

The final representative rehearsal source is 28 files and 36,894,853 bytes,
with staged-source manifest
`8c065213e76d6392b2da81a53ce8108b2826509b67f32b85f0cf02d683df9b14`.
A representative stage passed the Vercel local builder after the build command
was changed to a standard Python Function project build:

1. reconstruct and fully validate during `buildCommand`;
2. package `api/index.py` as Python 3.12;
3. trace all eight reconstructed artifact files; and
4. trace zero `transport/**` files, `transport-manifest.json` files, or
   materializer scripts into the final Function.

That representative local Function contained 959 unique traced files and
53,333,117 bytes, including all 36,784,493 representative artifact bytes.

The exact full stage also reconstructed and fully validated before packaging.
The local builder then measured **2,423.77 MiB** and rejected it at its 500-MB
Lambda ephemeral-storage path. Repeating with the documented Large Functions
variable in both the disposable process and disposable local Preview env file
produced the same failure. This is local-tool evidence, not proof that Vercel's
remote 5-GB beta will fail, but it prevents assuming the remote path is ready.

## Mandatory Vercel support questions

Obtain a written answer to all of the following before upload:

1. For a Hobby project created 3 August 2026 with Fluid Compute enabled, will
   an API-created Preview using Python 3.12 accept a measured 2,423.77-MiB
   package under the June 2026 5-GB Large Functions beta?
2. Is any project or Preview environment mutation required for automatic
   enrolment, and if so, exactly which setting? Why does CLI 54.12.2 with
   `@vercel/python` 6.44.1 still enforce the 500-MB local path even when
   `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` is present?
3. Does the remote builder preserve the documented 23-GB disk and 45-minute
   limits for a Large Python Function while source chunks and 2.525 GB of
   reconstructed output coexist?
4. After deleting an API-created Preview, what happens to digest-addressed
   source objects uploaded through `/v2/files`? State the retention period,
   team scoping, and any supported immediate-deletion endpoint or procedure.
5. Is a repeated `POST /v2/files` with the same SHA-1 and size guaranteed to
   reuse an acknowledged source object without retransmitting its body after a
   client interruption?

Do not infer answers from ordinary immutable-deployment behavior.

## Rehearsal approval gate, prepared but not yet open

Once support answers the retention/reuse questions, present this exact
disposable rehearsal for explicit approval:

- target: unaliased, Vercel-Authentication-protected Preview in opening-service
  project `prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP`, team
  `team_kjpopfvj3bLNk74leLtqEgAD`, region `iad1`;
- source: representative A only, 28 files, 36,894,641 bytes, 8 transport
  chunks;
- expected raw transfer at 25 Mbit/s: 11.806 seconds, excluding build and
  retries;
- interruption target:
  `transport/e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03/games.bin/part-00000000.bin`,
  after 8,388,608 of its 26,687,930 bytes;
- expected journal state at interruption: 22 acknowledged files and 1,861,036
  reused bytes; the incomplete `games.bin` part has no acknowledgement and is
  retried from its beginning;
- mutations: upload missing digest-addressed files and create one unaliased
  Preview; no environment, project, alias, domain, frontend, or Production
  mutation;
- documented bill: $0 within current Hobby allowances; usage still counts;
- validation: reconstruct, checksum, complete artifact validation, service
  metadata, and representative oracle queries under unchanged limits;
- cleanup: delete only the recorded disposable deployment and remove only any
  separately approved temporary credential; no new credential is created by
  the script; and
- rollback: no operation is required because Production and the retained
  representative deployment never move.

Approval for this 36.9-MB rehearsal would not authorize the 2.525-GB upload.

## Verification summary

- opening repository: `python -m pytest -q` — 164 passed;
- final full staged-input dry run — 64/64 files re-hashed, no journal, no
  network;
- representative Vercel local build — passed materialization and chunk
  exclusion;
- full Vercel local build — reconstruction and structural validation passed,
  packaging stopped at the documented tooling mismatch;
- frontend opening-explorer unit slice — 33 passed;
- frontend TypeScript and ESLint — passed;
- frontend production build — passed after allowing the configured Google Font
  downloads;
- full frontend unit run — 467 passed and one unrelated existing
  `localStorage.clear()` failure under Node 26.5.0;
- live frontend metadata — representative dataset confirmed;
- direct service URL — protected by Vercel Authentication;
- no commit or push performed.

Production remains on the representative artifact. No full hosted benchmark,
correction, rollback, removal, or Production decision is claimed because the
required protected Preview does not yet exist.
