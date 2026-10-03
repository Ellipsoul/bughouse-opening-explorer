# Incremental opening migration — implementation and evidence

Status: **validated local release candidate complete**. The actual
August-to-September update matches both independent full builds byte-for-byte, and the
local release gates passed. Production remains August. See the
[operator runbook](OPENING_INCREMENTAL_RUNBOOK.md), and
[concrete release packet](OPENING_INCREMENTAL_RELEASE_PACKET_2026-10-03.md).

## Implemented behavior

The durable builder retains a normalized UUID/revision ledger, stable internal
game keys (including deletion tombstones), complete distinct-placement support,
singleton owners, materialized position/state/edge/ending memberships, and player
postings. Update generations preserve their parent and pin source and semantic/
engine identities. Discovery, update, repair, verification and export are separate
stages with recoverable transaction cursors and manifest-last completion.

The support/owner design uses exact counts plus the XOR of contributing keys.
Count-one rows therefore identify their sole owner after final-batch additions,
removals and unchanged-count replacements, without retaining every hidden posting.
Shared accumulators are verified against materialized memberships, and affected
singleton owners are independently replayed for ownership verification.

Canonical export regenerates target-order ordinals, public IDs, offsets, postings
and dictionaries. Serving remains `packed-position-graph-v2`. The independent full
builder never reads an incremental checkpoint. Its fact schema and exporter were
factored without changing any byte in the retained representative output.

## Inputs and source integrity

| Source | Bytes | SHA-256 | Stored boards |
| --- | ---: | --- | ---: |
| August | 15,695,740,928 | `262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228` | 8,487,878 |
| September target | 16,067,272,704 | `241f5e8dc353d42c751382223c386fa8fc495b8b792ada52920006695f2404eb` | 8,684,730 |

Both complete immutable snapshots passed quick_check and zero foreign-key checks.
The target passed the latest completed run's qualification/cohort/closure audit.
Historical backfills and partial October remain included. No live crawler access
or acquisition was performed.

## Representative proof

The 8,187-game August mod823 full build after refactoring matches every retained
component and manifest byte. Its incremental bootstrap/export also matches.
The actual snapshot-to-snapshot mod823 update reaches 8,364 accepted games and
matches the independent target full build byte-for-byte, including manifest.
It replayed 177 new games for placement support and queued 110 promotion owners.
These figures are sample evidence, not the complete affected-game count.

Sample checkpoint bytes: August 73,957,376; September 75,526,144. Sample target
phases: ingestion 2.842 s, support 0.329 s, repair 0.558 s, verification 0.191 s,
and complete export 1.024 s. These precede additional owner-audit checks and are
not a full monthly benchmark.

Behavior fixtures cover metadata changes without raw-hash changes, source order,
move/result/rating/name/source corrections, admission changes, promotion/demotion,
hidden ownership, unchanged-count replacement, transposition bridges, cycles,
repetitions, real endings, orphan exclusion, malformed-game atomic exclusion,
split/reordered updates, tombstones, no-op retry, parent preservation, source/policy
mismatch, corrupt support owners/spills, stage interruption, seed-table resume,
and export interruption with a fresh retry output.

Recovery review additionally proved atomic rollback between old-revision
subtraction and replacement support, and inside materialized frontier replacement.
A busy final SQLite checkpoint cannot publish completion, and a nonempty WAL or
inconsistent completion metadata fails verification. Revision history is keyed by
generation identity plus source, so revisiting an earlier source checksum retains
the immediately preceding move revision instead of colliding with older history.

The retained full August staging was independently re-exported in 1,048.997 s.
Both 6,447,934,175-byte v1 directories then passed a separate exact component and
manifest-byte parity check in 45.880 s. This validates seed reuse; complete hidden
support/ownership discovery is still part of the bootstrap and is not replaced
by this proof.

## Tooling and application gates

Exact September A-name allowlists were added in transport, stage and runtime;
B/comparison names remain rejected and rollback names remain allowed. The HTTP
oracle discovers manifest roots and real graph state/edge witnesses. Startup and
publication lifecycle compatibility were tested. Recovery uses the explicit run's
window. The runbook's stale 30-second proxy statement was corrected to the source
45-second default; the maximum remains 60 seconds, with no application limit change.

Frontend baseline verification passed 540 unit, 159 component and 36 E2E tests,
TypeScript/ESLint and production build. Browser verification subsequently found
and fixed async board sizing and mobile ancestor scrolling; the final revision
has 541 passing unit tests and passed TypeScript/ESLint. Final component/E2E/build
results are recorded in the completion section. The initial sandbox font-fetch
failure was environmental and the network-enabled build passed.

The new startup option measures the existing build-attested runtime separately
from full checksum/structural validation; its fixture confirms file-count/constant
validation phases without a corpus scan. The offline filesystem receiver fixture
proves interrupted receipt, retry, journal reuse and exact reconstruction. Full-size
candidate measurements are below. Latest broad backend run: 308 passed in
12.57 seconds, including repeated-source revision history, unchanged-ledger
preservation during promotion repair and a genuine internal-ending HTTP witness.

## Complete August checkpoint proof

The completed August checkpoint contains 6,747,980 accepted games and 234,533,343
complete distinct placements, including 5,985,342 shared placements. Its SQLite
file is 69,306,163,200 bytes, SHA-256
`eae3a11d27757e921b361cdd692349cbb326aa5aa272e9c9a49023d4db29267e`.
The complete support B-tree occupies 8,028,999,680 bytes. Both source-revision
tables occupy 14,115,221,504 bytes each; this first version keeps explicit raw and
normalized revisions to support auditable correction/recovery.

Recorded resumed bootstrap phases were ingestion 877.402 s, complete support
discovery 3,393.073 s, validated materialized-seed copy/index work 6,765.060 s,
and checkpoint verification 1,515.293 s. The resumed command took 12,972.691 s
and reached 2,504,327,168 bytes native peak RSS. Generation wall time including
the initial controlled interruption and setup was 14,306.626 s.

The completed checkpoint's canonical v1 export took 3,223.549 s and passed strict
component and manifest-byte parity against the retained 6,447,934,175-byte August
artifact. This proves the complete parent, beyond the earlier seed validation.

During the actual September repair, finalization was found to scan every ledger
key and replace all incoming revisions. It now writes only the complete changed
key set, leaving promotion-only owners' source records intact. A trigger-backed
regression test reproduced the old behavior and passed with the change. The owned
writer was stopped at committed repair cursor 8,684,000 and the same child resumed
with the same source and schema; original logs remain. The interrupted attempt's time is retained in the original process log; total
generation wall time below includes it, while the repair-tail time does not.

## Complete September temporal generation

The child of the proven August checkpoint completed with 6,899,477 accepted games,
239,539,511 complete placements and 6,115,542 shared placements. Only the 151,497
new accepted games required support replay. Its 70,723,231,744-byte SQLite file has
SHA-256 `bb2fb092fe8ac7d8c9cd17f0abf31f382055fae1a0e24a9aa0dfbe9df4ac7dd0`.
Recorded exclusions are 1,128,912 empty TCN, 656,320 short non-checkmate and 21
position replay errors; there are no deletion tombstones for this batch.

Ingestion took 1,578.005 s, support changes 1,070.163 s and full checkpoint
verification 1,387.094 s. The recorded 32.456 s repair timing covers only the
resumed tail after the controlled interruption. Total generation wall time was
9,032.706 s, including the earlier repair attempt and interruption. The resumed
CLI took 1,829.679 s and reached 650,215,424 bytes native peak RSS. These are
concurrent migration measurements, not an isolated next-month benchmark.

The independent complete delta audit took 567.035 s and passed every expected
source assertion. It enumerates 279,532 changed UUID records and 121,588 promoted
placements. Of 76,490 repaired old owners, **57,909 gained longer frontiers** and
18,581 retained the same frontier; **673 newly reached their true ending**. The
analysis's 46,971 extensions / 291 endings were lower bounds, superseded by this
complete replay-backed enumeration. There were no demotions in this batch.

Source additions reconcile to 196,852 UUIDs: 151,497 accepted, 27,806 empty TCN and
17,549 short non-checkmate. There are 82,680 changed existing raw revisions,
including 64,166 accepted metadata corrections, with zero existing move/admission
changes and zero deleted UUIDs. All 21 prior replay-error identities and errors
are unchanged. Accepted metadata changes include 32,126 White-name fields, 32,198
Black-name fields, four White-result fields, two Black-result fields, six source
fields and six provenance fields. Field counts overlap within games; they are
not additive game counts. Every changed accepted revision also has a changed
content hash; no rating correction was observed.
The result/source/provenance corrections concern the same six accepted games.

Full witnesses are retained under
`artifacts/opening-incremental-20261003-r1/complete-delta/`: `report.json`,
`source-changes.jsonl`, `threshold-placements.jsonl`, and `threshold-games.jsonl`.
The report SHA-256 is
`484f4bb30b6bad7ba45ab3f4b457afe6da267060f4f3d0d1cd7dba01ed7a4fd0`;
`complete-delta-evidence.json` records all four witness hashes, sizes and JSONL
row counts.
The completed canonical September export took 2,190.078 s and its v2 repack
took 99.722 s. Both formats match both independent full references, including
exact manifest serialization. Export retained 3,850,399,744 temporary bytes.
September support occupies 8,028,999,680 B-tree bytes; ledger, incoming and prior
revision tables occupy 14,434,918,400, 14,434,283,520 and 316,547,072 bytes.
The update is not a scan-only benchmark: full checkpoint verification, export,
repack and independent parity are all included in the evidence.

## Independent full references

Both complete September references passed artifact validation and their v1
manifests/components match. Their dataset/build identity is
`137962bc5eace0f0c5ce4e50c2889d459a66087e`, with root position 9,867,991 and
state 7,439,655. Each contains 6,899,477 games, 15,690,069 positions, 16,310,295
states, 18,071,251 edges and 369,587,351 memberships. The v1 artifact is
6,593,699,820 bytes including its manifest. Exclusions and shared-placement count
match the completed temporal child.

| Independent build | Full build seconds | Validation seconds | Native peak RSS bytes | Retained temporary bytes |
| --- | ---: | ---: | ---: | ---: |
| A, sole candidate | 25,455.982 | 23.184 | 2,544,484,352 | 22,924,001,464 |
| B, immutable oracle | 25,095.670 | 23.206 | 2,541,944,832 | 22,924,128,440 |

Evidence: `full-a-result.json`, `full-b-result.json`, and `full-v1-parity.json`
under the dated operations directory. These builds consumed the immutable target
independently and did not read a generation checkpoint. A/B v2 repacks took
105.456 / 105.721 s. Strict three-way v1 / v2 byte validation took 67.782 /
36.031 s. Final source and completed-checkpoint hashes remained unchanged for
both generations after export (`final-byte-parity-and-bookends.json`).

## Read-only hosting preflight

As checked on 3 October, the existing team is Hobby, service Fluid Compute is true,
region is `iad1`, and deployment protection remains enabled. Cached CLI 62.2.0
matches the published npm version. Service/front-end secret keys exist in Production
scope; their values were not exported or used. The Production timeout override is
Sensitive, so its actual value is not verified by these key/scope checks.

The service alias currently points to `dpl_AHb8E3hcTUBcv2m3VcD4ePcymjdA` (READY).
The earlier `dpl_4TFjHYbjsrxVPFza8SnHwdhSJkJP` is also retained and READY.
Public metadata, read through the Vercel connector at
`/api/opening-explorer/api/meta`, still reports the August v2 dataset
`68a97678c3df093d243473e0844b373d669ac335`, 6,747,980 games, root node 9,651,009
and state 7,275,645. Initial local TLS/receive failures and a wrong-path request
were corrected; neither was evidence of a production data failure.

Official documentation currently describes a 5-GB Large Functions public beta on
Fluid Compute, with existing-project opt-in and exclusions for Secure Compute and
Static IPs. [Large Functions announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3).
Build documentation describes 23 GB standard build disk.
[Build resources](https://vercel.com/docs/builds).
The actual new package was built locally with the checked CLI and measured
through its complete file map, as detailed below. Hosted performance and available
account quota remain separate release gates.

## Artifact bytes and exact checksums

The sole release candidate is
`artifacts/opening/full-position-graph-through-202609-20261003-r1-v2-a`.
The matching full B and incremental directories remain independent local evidence.
All six complete artifacts remain retained. The v2 candidate is **3,463,810,827
bytes including manifest**, versus August's 3,386,499,197 bytes. The v1 target is
6,593,699,820 bytes versus August's 6,447,934,175 bytes.

The following candidate hashes were validated against A, B and incremental output.
Gzip sizes are independent level-6 streams measured into a counting sink, with no
compressed release files. Their sum is **1,539,069,003 bytes**; it is neither the
raw transport size nor the Function package size. Compression took 126.610 s.

| Component | Raw bytes | Gzip-6 bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `edges.bin` | 487,923,777 | 241,592,853 | `5aa844441dc23b1a7b6cf83d219bf953bce38f5c9f29d8f0dda0e8c9d9bd708d` |
| `game_dictionaries.json` | 240 | 177 | `99bf90cef0b4bb9f39102e5c11138a3d02534f3572973f2ae92c7bc9c7850c10` |
| `games.bin` | 275,979,080 | 124,242,687 | `2f313d97960b717520d4b2b7ebc693f6d2b4c14b658663698d65b2d1945bde1b` |
| `manifest.json` | 2,707 | 1,187 | `da74d264a3e1ec8249d2ffbdf6dcfd9102cadfcdb266361ecac37771a8a15cf1` |
| `memberships.bin` | 986,932,992 | 603,585,161 | `ed74e00f48cccb22df57eff3a5f8eea3f6124500fb592a1998f9a00ed643a79d` |
| `positions.bin` | 203,970,897 | 85,695,574 | `3a48f6c59607d3cbde3141682397a7b69248251cbbf95082fe7d41634af20e2b` |
| `postings.bin` | 55,195,816 | 28,047,767 | `800991178366a3cc51c676930a6699476dfca366d9273b1de9ba6ed1717d4a92` |
| `postings.json` | 14,137,784 | 2,715,333 | `d7384d5e79c6fef4e90104d6873be7b21b964438fa1487085c51896b19b04cca` |
| `states.bin` | 554,550,030 | 224,157,282 | `791c0cc5562c95f39fcd7d7ff56efe188dbae572ab9ce0431c92b15b574800f4` |
| `strings.bin` | 882,376,673 | 227,599,752 | `de8c0c99322ac84f3ca3282a317bd5de4b409eb0dd17861fe16b355d27a69e89` |
| `username_offsets.bin` | 736,280 | 265,842 | `40dfcb705784669936a1910b12895e8f333387792dd8130bfdc15c767ec44fe6` |
| `usernames.bin` | 2,004,551 | 1,165,388 | `12e2fbe3272825bf7cd3df2898324d4986047fac3a1b70f18cc534a94b81de56` |

Complete v1 hashes and both exact manifest serializations are retained in
`three-way-byte-parity-v1.json`, `three-way-byte-parity-v2.json` and
`three-way-parity.json` in the operations directory. Public IDs are target-order
exports; stable checkpoint keys were not exposed. Every one of 6,899,477 game
metadata records, 10,000 sampled states and three filtered roots also passed v1/v2
semantic parity (`v1-v2-all-metadata.log`).

## Local service, lifecycle and performance

The exact A candidate passed the graph-aware 17-case HTTP oracle both directly
and through the actual Next.js proxy: metadata/root, meaningful deep state,
internal true ending, terminal game references, drops, White/Black/exact-pair
filters, missing player, autocomplete, stale version, invalid node, ETag and hard
node/byte limits. No mismatches were recorded. The original internal-ending
selector could choose a leaf; a failing behavior fixture exposed that and the
selector now requires an actual ending alongside an outgoing edge.

Twenty fresh processes were measured on macOS 27.0.1 / Apple M3 Max / 128 GiB RAM,
Python 3.13.7. OS file caches were not flushed and other migration work ran
concurrently. These are local measurements, not hosted cold-start guarantees.

| Measurement | Median | p95 |
| --- | ---: | ---: |
| Full-validation startup | 12,209.339 ms | 12,486.152 ms |
| Build-attested startup | 115.525 ms | 124.752 ms |
| Attested process launch through first result | 224.658 ms | 234.657 ms |
| Attested first root neighborhood | 31.124 ms | 31.853 ms |
| Attested warm root neighborhood | 28.694 ms | 29.383 ms |
| Unfiltered graph benchmark | 25.501 ms | 30.378 ms |
| Popular White filter | 2,425.136 ms | 2,457.350 ms |
| Popular Black filter | 2,434.620 ms | 2,483.930 ms |

Native startup RSS median/p95 was 239,566,848 / 240,353,280 bytes for attested
readers and 253,698,048 / 257,507,328 bytes with full validation. The graph benchmark
returned 245,583 unfiltered bytes, 253,424 White-filter bytes and 254,646 Black-filter
bytes, all deterministic and within the 262,144-byte default. Its unfiltered
response contained 408 nodes/states and 411 edges; filtered responses contained
445 nodes/states and 448 edges. Source edges were checked.

The unchanged admission limit accepted every request at concurrency 1 and 8.
Three 32-way waves accepted 9/11/9 and rejected 23/21/23; three 64-way waves
accepted 16/10/9 and rejected 48/54/55. Rejections are intentional bounded 503s,
not successful query results. A separate 64-way proof checked every rejected
response was `concurrency_limit`, `Retry-After: 1`, `Cache-Control: no-store`,
with a bounded body and a successful recovery request. No limit was raised.

The proxy's 100-ms test override returned bounded 503 in 103.197 ms; a 20-ms abort
returned in 22.365 ms and the recovery request succeeded. Normal operation used
the existing 45-second source default. Publication lifecycle testing switched a
local owned pointer August→A→August in 11.744/11.958/11.708 s, confirmed artifact
hashes unchanged, then removed only that disposable pointer. Retained artifacts
were not deleted.

Evidence: `candidate-http-oracle.json`, `candidate-proxy-http-oracle.json`,
`candidate-concurrency*.json`, `proxy-timeout-cancellation.json`, `startup.json`,
`candidate-attested-startup.json`, `graph-benchmark.json`, and `lifecycle.log`.

## Offline transport and local Function package

The fresh external rehearsal is
`/private/tmp/opening-release-20261003-r1-49hgvnfv/rehearsal`.
Its deterministic transport identity is
`1915d692eab62479d3b4bd8ab6b74c5531da6bd2965afa83d0b3d92e07ef5399`:
61 chunks, 3,463,810,827 original bytes. Stage identity is
`07c628824fcb2d79c348aa004177a78e9e4af79fe21c58bb5907145f5c4c7390`,
3,464,044,423 source bytes. Repeated manifest generation agreed exactly.

An interrupted local filesystem receipt retained a 33,554,432-byte partial.
Resume reused one complete 67,108,864-byte chunk, transferred 60 remaining chunks
(3,396,701,963 bytes), and survived one injected transient failure. A subsequent
retry reused all 61 chunks and transferred zero bytes. Reconstruction passed
exact component validation in 17.785 s. No remote upload occurred; the local
journal is not reusable as a remote acknowledgement.

CLI 62.2.0 built a copied stage locally in 21.624 s with dummy local credentials
and process-only Large Functions/artifact flags. The log selected Python 3.12,
`x86_64`, and enabled Large Functions beta. All 986 `filePathMap` destinations plus
the wrapper/config total **3,480,735,015 bytes**, leaving **1,519,264,985 bytes**
below a conservative 5,000,000,000-byte cap. The retained build tree occupies
6,989,110,473 bytes, leaving 16,010,889,527 below 23 GB. Native build RSS peaked
at 324,206,592 bytes. This measures the local output; hosted build transients and
actual remote package size still need verification after approval.

Every mapped artifact component was hash-checked. Transport chunks, databases and
dotenv files are excluded from the Function. The original directory-only package
measurement counted just wrappers and was superseded by
`local-package-measurement-r2.json`; Vercel 62 references external files through
the file map, so `du` of `index.func` alone is not the package size. The local
runtime attestation is
`f50ec95c859ae254b43a66f20cb60d728594c8b5f06d2c1ed0a89b3b561372a1`.

Build copy and log:
`/private/tmp/opening-local-package-20261003-r1-y0amapde/build` and `build.log`.
No project environment was changed. Remaining external release approvals and
exact candidate/rollback commands are in the linked release packet.

## Desktop/mobile browser proof and bounded UI repair

The exact A artifact was served locally behind the real Next.js proxy. Headed
Chrome used 1440×1000; WebKit 26.6 used an iPhone 15 at 393×659 CSS pixels.
The mobile root board occupies x=48, y=101, width=329, height=329 and is fully
visible on initial load. Screenshots were inspected, not merely generated.

Verified flows included both `Nf3 Nf6 Nc3 Nc6` and `Nc3 Nc6 Nf3 Nf6`, reaching
the identical state 9,587,892; keyboard Left/Right; direct 12-ply state 12,279,558;
the `P@f6` shared drop from state 22 to 1,940,411; and an unclickable real ending
at state 12,554,468 alongside its outgoing continuation. Direct anchors correctly
start a new local move list while showing the requested board position.

Actual renamed-player filters returned `firkintime` White/Black 26,279/26,482
and `zyoimmm22` 4,712/4,487. The retired `zyoim22` suggestion is absent; clear and
missing-player behavior passed. The old `ryantime` still has 35 White / 44 Black
historical games, so it was not incorrectly asserted absent. Stale August URL
anchors were ignored in favor of the September root; existing behavior rewrites
the URL on subsequent navigation rather than immediately at bootstrap. An initial
test expecting immediate normalization was corrected to the existing contract.

The actual `B@b4` source link for game 160842422747 opened the two-board viewer,
including littleplotkin/xshyne and their partner board. The test intercepted the
canonical link and redirected it locally without fetching the public host. The
existing server fixtures supplied games 160842422747/160842422749; no Chess.com
acquisition occurred. Advancing the viewer and the unchanged Player Insights page
also passed smoke verification; no projection file changed.

The browser evidence contains 385 desktop and 275 mobile opening responses,
with maximum bodies 261,185 and 259,890 bytes respectively. Every recorded opening
response succeeded with the candidate dataset; none downloaded packed binaries,
databases or full postings, or sent an Authorization header. The dummy Firebase
setup produced blocked analytics/installation fetch errors and an App Check
warning; these are preserved, so this is not a zero-console-error claim. A dev-only
HMR dependency warning while editing disappeared after reload.

Two bounded UI repairs were necessary: attach the board ResizeObserver after
async loading and size the mobile grid row explicitly; scroll only the selected
move's list rather than all ancestors. A failing async-sizing regression test
now passes, including resizing below the former 260-pixel minimum. The API,
dataset cache, credentials, application limits and Player Insights projections
were unchanged. React effect/listener cleanup was reviewed.

Evidence: `browser-validation.json`, with snapshots, network audit and reviewed
screenshots under the frontend's `output/playwright/opening-20261003-r1/`.

## Final repository checks and resource envelope

| Gate on the final implementation | Result |
| --- | --- |
| Complete backend pytest suite | 308 passed, 12.57 s |
| Incremental behavior/recovery subset | 31 passed |
| Frontend unit tests | 541 passed |
| Frontend component tests | 159 passed |
| Frontend E2E tests | 36 passed |
| TypeScript and ESLint | passed |
| Next.js production build | passed, including static generation |
| Both working trees `git diff --check` | passed |

Final frontend logs were copied into the dated operations directory as
`frontend-{unit,lint,component,e2e,build}-final.log`. The production build retains
existing Baseline-data-age and Node deprecation warnings. No dependency upgrade
was added to suppress them. The first sandbox build's font-fetch failure, first
local-loopback restriction, interrupted repair and corrected measurement/test
assumptions remain in their original logs; none was recast as a successful run.

Thirty-second owned-process samples observed a maximum combined RSS of
4,297,867,264 bytes within one monitor stream.
The streams cover different process sets; no synchronized cross-stream peak is
invented. Native full-build peaks were about 2.54 GB per process, reported above.
Host free space began at 808,108,351,488 bytes at monitor start,
reached a minimum of **539,643,875,328 bytes**
(502.6 GiB), and ended at
539,673,972,736 bytes. Host free space includes unrelated activity;
sampled RSS can miss short peaks. `resource-summary.json` retains every process's
sample window and peak, with native command measurements kept separate.

The full session progress log is retained locally as
`artifacts/opening-incremental-20261003-r1/OPENING_INCREMENTAL_PROGRESS_2026-10-03.md`;
it is historical execution evidence and is not required reading for monthly updates.

The operations root is
`/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/artifacts/opening-incremental-20261003-r1`.
Sources remain `snapshots/monthly-20260901/crawler-through-2026-08.db` and
`snapshots/monthly-20261002/crawler-through-2026-09.db`. Complete checkpoint paths
are `august/checkpoint.sqlite3` and `september/checkpoint.sqlite3` within that root,
with immutable completion records in each `complete.json`. Both use schema 1,
`opening-adapter-v2-short-non-checkmate`, `skip-unreplayable-source-game-v1` and
`last-shared-placement-plus-one-or-game-end-v1`; exact engine/adapter/exporter
implementation digests are pinned in those completion records.

The complete parent remains valid, and the completed September child is the
next-month parent. This run does not waive routine independent A/B release gates.
The local services, owned emulator/browser sessions and monitors were stopped
after verification. Snapshots, checkpoints, temporary recovery files, all oracles,
artifacts and previous analysis were retained. No live crawler was read, no
acquisition or Player Insights refresh was run, and no external upload, hosting
mutation, deployment, commit, push or retained-data deletion occurred. The changes
and the concrete release packet are ready for review and commit by the user.


## Pre-commit scope review — 3 October 2026

The recurring core (revision/support/owner store, shared admission/export helpers
and CLI) remains necessary. Snapshot audit, delta audit, parity, graph oracle,
attested startup and transport-retry tools are reusable monthly release checks.
Validated-seed import remains an optional bootstrap/recovery path, not a monthly
step. Exact candidate allowlists and retained rollback entries remain required.
The frontend sizing/scroll fixes are independent bug fixes suitable for a separate
commit; they are not a prerequisite for the backend data cutover.

Removed the temporary fallback for an unfinished pre-namespace bootstrap. New
incomplete generations require their recorded revision namespace; completed
August and September checkpoints still verify and completed retries are no-ops.
An audit regression was reproduced and fixed: a corrected previously malformed
owner must not replay its rejected old revision when a batch demotes placements.
The report now compares only accepted revisions. The actual September dataset
had no such admission correction, so its recorded result is unchanged.

Post-review backend verification: **310 tests passed in 10.53 s**. Both complete
checkpoint hashes remain unchanged, and all 17 service-source files still match
the validated external stage. Neither changed builder/report file is deployed
in that stage. The frontend source is unchanged from its verified 541/159/36-test
revision; those suites were not needlessly rerun for documentation cleanup.
Both diff checks passed. Review logs are retained in the local operations root.

The 599-line session log was moved intact into that ignored operations root.
The documentation map and runbook now lead with the routine monthly path and
mark the old analysis/handoff/prompt as historical. No artifacts or recovery data
were deleted, and no commits, uploads, environment changes or deployments ran.
