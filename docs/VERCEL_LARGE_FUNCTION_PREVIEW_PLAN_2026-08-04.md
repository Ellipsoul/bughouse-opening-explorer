# Vercel Large Function preview plan — 4 August 2026

## Decision

The next slice is an isolated, protected Vercel Large Function preview of the
already validated full opening-tree artifact. It is a transport,
materialization, and hosted-behavior experiment. It is not authorization to
upload the artifact, create paid storage, change Production configuration, or
promote a deployment.

The preferred transport is a deterministic, journalled, checksum-verified
chunk upload into a new immutable deployment. This avoids treating the 2.525 GB
artifact—or its 1.892 GB `games.bin` component—as one opaque, failure-prone
upload. A controlled interrupted-upload rehearsal must prove that only an
incomplete chunk is retransmitted before the full artifact is allowed to leave
the workstation.

The representative artifact remains the correctness, performance, rollback,
and removal oracle throughout this slice. Production continues to use it until
hosted full-scale evidence and costs have been presented and a separate
promotion approval has been obtained.

## Current checkpoint

- The full accepted-game tree contains 6,516,478 games and 2,524,966,683
  component bytes.
- Full artifacts A and B are component-identical. A is the only candidate that
  may be staged; B remains untouched as the rollback/reproducibility oracle.
- Dataset version:
  `1e876810b96364e4bf9f23d49fb509a843783253`.
- The source fingerprint is the restored snapshot SHA-256
  `04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`.
- Full local reader readiness is approximately 5.96 seconds and peak RSS is
  approximately 522 MB.
- Local service, browser, terminal, player-filter, concurrency, correction,
  rollback, and removal checks passed under the existing query and response
  budgets.
- Vercel Large Functions currently supports uncompressed Node, Python, and
  container Function packages up to 5 GB on Fluid Compute. The feature is a
  public beta.
- The separate opening service project was created after the automatic
  Large Functions enrolment cutoff and was last observed with Fluid Compute
  enabled. Both facts must be rechecked immediately before any upload.
- The frontend player-filter fix is merged on `bughouse-chess` `main` and is
  live. The full artifact has not been uploaded.

The complete build, phase, checksum, and validation evidence is in
[`FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md`](FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md).

## Immutable artifact identity

Candidate directory:

```text
artifacts/opening/full-post-qualification-20260802-v2-a
```

Only the following files may enter the staging manifest:

| Component | Bytes | SHA-256 |
| --- | ---: | --- |
| `edges.bin` | 69,751,332 | `33867afed4a8060b7febafdb2515f0dda90315bc2f77bf0a6241d94325761da3` |
| `endings.bin` | 470,456 | `870ed3e5092d1746baa198e32092aa2f56a224b0b587f221c84e6aeb97a29b88` |
| `game_offsets.bin` | 52,131,832 | `d506bee7d360bc10adc6757b4137f8e17d2828d80b68eeaae09bb9951f9b0ca0` |
| `games.bin` | 1,892,357,989 | `33898a7dd13e34ac8c1c7dfb37551a3452d528e735fe3f1bd3d53f44e9e6aea7` |
| `nodes.bin` | 418,508,028 | `212846f6806a58801d62f34522c0b4b602e2e65c7e05ceb9439057aabb2fda84` |
| `postings.bin` | 78,197,736 | `594ecc0b982ef68e453ce1a88156dd5134ea9d834a6618556f3f8717a53d34c9` |
| `postings.json` | 13,549,310 | `0128cfc462db5c11e9494c0963563fdde64c74b6762f3050a594f61cb2c6e993` |

`manifest.json` must also be included and validated. Its recorded SHA-256 is
`024e80a02738fee59974434cee22300a20b2ae3c2c5245f906c712cbc223cf3d`.

The staging allowlist must reject the restored SQLite snapshot, compressed
backup, `data/`, raw API payloads, artifact B, unrelated artifacts, credentials,
and any separately exported username corpus.

## Why an ordinary upload is insufficient

Vercel deployments are immutable. The deployment API accepts files by digest,
then creates a deployment from filename, digest, and size references. This
gives a strong content-addressed integrity boundary and ensures that a failed
candidate cannot alter the current deployment.

However, the documented Hobby CLI source-file limit is 100 MB, while
`games.bin` is 1.892 GB and `nodes.bin` is 418.5 MB. The deployment
documentation does not promise resumable byte-range transfer within one source
file. `vercel deploy --archive=tgz` is also unsuitable: it removes file-level
upload caching and makes a connection interruption affect a large opaque
archive.

Vercel Blob has explicit multipart retry semantics and is the fallback
transport, not the default runtime architecture. Blob storage/materialization
would exceed the current Hobby included storage, add transfer and operation
costs, and still require a credible build-time path into the immutable Function
package. Runtime whole-artifact materialization is incompatible with the
current mmap reader and available Function scratch assumptions.

Official references must be refreshed on the execution date:

- [Large Functions announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3)
- [Function package troubleshooting and eligibility](https://vercel.com/kb/guide/troubleshooting-function-250mb-limit)
- [Vercel limits](https://vercel.com/docs/limits)
- [Deployment workflow](https://vercel.com/docs/deployments/overview)
- [Digest-addressed deployment files](https://vercel.com/kb/guide/how-do-i-generate-an-sha-for-uploading-a-file-to-the-vercel-api)
- [Staged CLI deployment](https://vercel.com/docs/cli/deploying-from-cli)
- [Vercel Blob multipart uploads](https://vercel.com/docs/vercel-blob)

## Proposed transport protocol

### Deterministic chunks

- Split each component larger than 64 MiB into fixed 64-MiB transport chunks.
- Use stable paths derived from dataset version, component name, and zero-padded
  part number.
- Record original component size and SHA-256, chunk offset, chunk size,
  chunk SHA-256, and the digest required by the Vercel file API.
- Never overwrite a staged name. A changed byte creates a different immutable
  version or fails validation.
- Store no secret or machine-specific absolute path in the manifest.

### Journal and retry

- Maintain a local append-safe upload journal outside the artifact directory.
- Mark a chunk complete only after Vercel acknowledges its digest.
- On retry, query or resubmit by digest so acknowledged chunks are reused.
- Use bounded retry with exponential backoff and an explicit final failure.
- Never infer completion from bytes written to the network; use the remote
  acknowledgement and final deployment manifest.

### Reconstruction

- Reconstruct components in a remote build-only staging directory.
- Verify each reconstructed component's exact byte count and SHA-256.
- Validate `manifest.json` and run the existing complete structural validator.
- Include only reconstructed components and the existing service boundary in
  the final Function package; transport chunks must not be traced into it.
- Fail the build closed on a missing, duplicated, reordered, oversized, or
  mismatched chunk.
- Measure remote temporary bytes. Confirm sufficient build disk for source
  chunks, reconstructed output, packaging overhead, and recovery headroom
  before the full transfer.

## Workstream A — transport proof with small data

Use TDD to implement the transport manifest, splitting, reconstruction, and
validation boundary. Tests must cover:

- deterministic manifests and part ordering;
- empty, final-short, exactly-one-part, and multi-part inputs;
- missing, duplicated, reordered, truncated, oversized, and corrupt chunks;
- wrong component size and SHA-256;
- journal restart and idempotent retry;
- allowlist rejection of snapshots, backups, artifact B, and unrelated files;
- complete reconstruction of the representative artifact; and
- byte-identical validation against the retained representative oracle.

Run a no-upload dry run that prints the exact included paths, component and
chunk counts, source bytes, expected reconstructed bytes, and maximum temporary
bytes.

## Workstream B — interruption rehearsal

Use a protected disposable Preview target and the representative artifact or a
similarly bounded fixture. This work changes Vercel state and therefore needs
explicit approval before it begins.

1. Upload enough chunks to establish observable progress.
2. Interrupt the client during a chunk upload.
3. Restart from the journal.
4. Prove acknowledged chunks were not retransmitted and only the incomplete
   chunk was retried.
5. Reconstruct and validate the exact original SHA-256.
6. Remove the disposable deployment and scoped credentials after recording the
   evidence.

If resumption/reuse is not demonstrated, stop. Do not upload the full artifact.
Escalate to Vercel support or present the Blob multipart fallback, including
current cost and cleanup implications.

## Workstream C — final preflight and approval

Immediately before a full upload:

- confirm both repositories are on the intended clean commits;
- revalidate artifact A and compare artifact B without modifying either;
- rerun free-disk, memory, file-descriptor, and local temporary-headroom checks;
- refresh Vercel Large Functions, CLI file, build duration/disk, memory,
  region, concurrency, transfer, storage, and pricing documentation;
- read-only inspect the service project, plan, Fluid Compute state, regions,
  current representative deployment, protection, and environment scoping;
- estimate source, build, Function, Blob-fallback, and removal costs;
- present the exact mutations, upload bytes, expected duration, costs, rollback,
  and deletion commands; and
- obtain explicit approval for the full protected Preview upload and any
  required configuration or paid resource.

Approval for a Preview upload does not authorize Production promotion.

## Workstream D — protected full Preview

After approval, stage exactly artifact A through the proven transport into the
separate opening-service project. Do not change the frontend Production origin,
custom domain, or representative deployment.

Record CLI/API versions, project and team IDs, environment, region, start/end
time, bytes attempted/reused/retried, build phase times, final Function package
size, deployment ID/URL, protection state, and platform usage.

The deployment is acceptable only if the dashboard identifies the intended
Large Function path, readiness validates every artifact checksum, metadata
reports the full dataset version/count, and the service remains protected.

## Workstream E — hosted validation and decision

Run the same representative and full local query corpus without relaxing
limits:

- cold deployment readiness and first request;
- warm metadata, root, deep, and direct-link neighborhoods;
- White and Black player filters and invalid/stale filters;
- support-one branches, endings, drops, terminal/source-game behavior;
- 1/8/32/64 concurrency and bounded overload behavior;
- ETags, cancellation, timeouts, response/node/byte caps, and corrupt input;
- browser navigation, Back/Forward, autocomplete, invalid-player UI, and the
  existing two-board viewer;
- correction through a new immutable Preview deployment;
- rollback to the retained representative; and
- bounded removal with no artifact or credential residue.

Compare hosted cold/warm timings, RSS, CPU, errors, transfer, invocation and
memory usage, and observed cost with the local result. Present the evidence and
recommend one of: retain representative, continue the protected experiment,
promote the full artifact, use paid external container control, or revisit the
reader/storage architecture.

No Production promotion occurs in this slice without a new, explicit approval.
If later approved, use a production-target deployment with domain assignment
disabled, validate it, and promote the immutable deployment only after all
checks pass. Rollback must restore the known representative deployment/origin.

## Required durable evidence

- dated official-limit and cost snapshot;
- exact dry-run allowlist and chunk manifest summary;
- TDD and interruption-recovery evidence;
- local and remote temporary-write/headroom measurements;
- upload journal summary with retries and reused bytes;
- final Function contents, size, checksums, deployment ID, and protection state;
- hosted benchmark and semantic comparison;
- correction, rollback, removal, and credential-cleanup evidence; and
- a clear Production recommendation with separately approval-gated costs.

Never commit the artifact, transport chunks, upload journal, credentials,
deployment protection bypass, raw snapshot, or raw username corpus.

## Definition of done

This slice is complete when the transport is demonstrably interruption-safe at
chunk granularity; the full artifact is either validated in a protected Preview
under the existing budgets or stopped at an evidence-backed gate; all costs and
mutations are recorded; rollback and removal are demonstrated; Production and
the representative oracle remain safe; and no live database, crawler request,
browser artifact transfer, unapproved cost, or unrelated viewer regression has
occurred.
