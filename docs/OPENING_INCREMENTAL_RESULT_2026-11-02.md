# October-only incremental opening update — 2026-11-02

## Outcome

The current local update is complete under the explicitly revised `incremental-integrity-v1` policy. The validated incremental v2 export is the routine release candidate. All November games are excluded. No additional crawl, retained-data deletion, commit, push, upload or deployment occurred during the workflow revision. Production was not reverified or changed.

- Candidate: `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/artifacts/opening/incremental-position-graph-through-202610-20261101-october-only-r3-v2`.
- Dataset: `dbcc296735e87541e82e1f2cdac06a5c17e61174`; 7,019,712 accepted games.
- Positions/states/edges: 15,967,147 / 16,598,349 / 18,390,359.
- Candidate bytes including manifest: 3,526,334,311.
- Source: `snapshots/monthly-20261101-october-only-r3/crawler-through-2026-10.db`.
- Source SHA-256: `52473c926d78eb2aaa78dd5efc6f319b694c91708842103baace7fdb96109a2a`.
- Exclusive cutoff: `end_time < 1793491200` (2026-11-01 00:00:00 UTC). Source has 8,835,204 boards, no null timestamps, and zero November-or-later boards.
- Insights were already published and reconciled: 1,170 players; dataset `cc434b13a480d4c93c87871084e98eb666c55f5a`. See `MONTHLY_DATA_AND_PLAYER_INSIGHTS_RESULT_2026-11-01.md`.

## Supervisor transition and intentional cancellations

The old supervisor (PID 4534) was first frozen while its incremental export (PID 20738) continued. Its stored entrypoints were disabled, a replacement supervisor was started to adopt that export, then the old supervisor and only the full-reference builders (4925/4926) were terminated. The replacement has no full-reference launch/wait paths and does not interpret their intentional cancellation as update failure. Partial reference scratch and all original logs remain intact.

- Intentionally cancelled: full A and full B builds, their repacks, full A/B comparisons, and full-versus-incremental v1/v2 parity.
- Retained: checked October source, September parent, completed October checkpoint and support/owner proof, in-flight export, all completed insights/tests and exact rollback files.
- Prior host restart recovery remains recorded in `HOST_RESTART_RECOVERY.md`; it is not a new data failure. No old supervisor should be restarted.

## Executed replacement acceptance gate

| Check | Result |
| --- | --- |
| Source checksum, SQLite quick/FK, cutoff, crawler closure/domain audit | Passed |
| Parent linkage and parent/child checksum, policy/engine/source identity | Passed |
| Durable completion, no pending WAL, support/owner verification | Passed; reused completed invariant stage with verified unchanged bytes |
| Full change and threshold witness reconciliation | Passed |
| Artifact components, format/structure/source fingerprint and accepted count | Passed |
| v1-to-v2 semantic conversion | All 7,019,712 game metadata records, 10,000 sampled states, 3 filtered roots passed |
| Backend regression/recovery and rejection tests | 327 passed |
| Exact-name transport/stage/runtime boundaries | Red-to-green: candidate allowed; unapproved full references/near matches rejected; existing rollback entries preserved |
| Frontend unit/component/type/lint/production build | Retained passed results: 573 unit, 161 component, types/lint/build |
| Local HTTP oracle | 17 cases passed with equal body, status and ETag |
| Graph behavior/performance and attested startup | Passed; 20 startup repetitions |
| Desktop/mobile browser | Passed at 1440, 320 and 390 px |

Parent checksum: `bb2fb092fe8ac7d8c9cd17f0abf31f382055fae1a0e24a9aa0dfbe9df4ac7dd0`. Child checksum: `a5b7c35015fca00c210271cd7be747fd32e5cd74e20f78a90a9d8714fe11e469`. Child is 71,690,526,720 bytes and is the next routine parent. Its completion proof includes positive support, accepted singleton owners, shared counts and XOR membership accumulators, replay of touched singleton owners, root counts, valid membership ownership and two player postings per accepted game. No pinned adapter/engine/exporter implementation was changed.

## Complete delta reconciliation

| Measure | Count |
| --- | ---: |
| `added_accepted` | 120,235 |
| `added_empty_tcn` | 17,909 |
| `added_short_non_checkmate` | 12,330 |
| `added_uuid` | 150,474 |
| `deleted_uuid` | 0 |
| `existing_accepted_metadata_changed` | 12,184 |
| `existing_changed` | 15,275 |
| `existing_outcome_changed` | 0 |
| `existing_topology_changed` | 0 |
| `parent_source_rows` | 8,684,730 |
| `target_source_rows` | 8,835,204 |
| `newly_reached_true_endings` | 505 |
| `old_game_frontier_extensions` | 47,213 |
| `promotion_placements` | 99,438 |
| `repaired_owners` | 61,962 |
| `unchanged_frontiers` | 14,749 |

All 21 replay exclusions are unchanged from the parent. There are no source removals or existing topology/outcome changes in this month’s actual delta; regression fixtures exercise removals, corrections and recovery. The 3,176 November boards removed from the newly acquired analysis copy were not in the September parent, so they are not falsely counted as parent-to-child deletions. All changes and repaired owners have retained JSONL witnesses.

## Browser and service evidence

Player Insights: all five modes rendered at all three widths, without horizontal overflow or NaN/Infinity; empty/new/zero-game/long-name searches and sort reversal passed. Production-build insight verification recorded only the expected local Analytics 404 and CSS preload warnings.

Opening Explorer: the local development proxy rendered the exact incremental dataset; white/black player filtering, reset, root and four-ply navigation, game-link targets, transposition convergence, and deep-link reload passed. Both Nf3/Nf6/Nc3/Nc6 and Nc3/Nc6/Nf3/Nf6 converge on state 9757643 and node 9055481 (18,880 games). Ready-state screenshots have no loading placeholder or horizontal overflow. Production rejects insecure loopback upstreams by design; tree browser evidence is explicitly local development, not a hosted-production check.

The first transposition browser assertion raced the asynchronous URL update; the subsequent expected-state wait passed and the original diagnostic log is retained. Initial screenshots captured loading states; final `tree-*-ready.png` screenshots were captured only after data readiness. Neither initial attempt is presented as completed visual evidence.

Attested startup p50/p95: 108.09/120.51 ms across 20 fresh processes. These are local measurements, not hosted latency promises.

## Policy, assurance limits and remaining work

Canonical incremental and monthly release runbooks, documentation map, exact-name transport/stage/runtime rules, regression fixtures, and the follow-up were revised consistently. `scripts/run_opening_incremental_checks.py` is the reusable post-export orchestrator; it has no full-reference dependency. Small regression fixtures can still use an independently computed oracle; full-corpus rebuild comparisons are reserved for explicitly requested audits or relevant algorithm/policy migrations.

No independent full-corpus parity is claimed. The replacement gate checks lineage, durable invariants, complete delta accounting, exported bytes/structure and tested local behavior. Common-mode adapter, incremental-engine or exporter defects can still evade it. V1/v2 comparison validates format conversion of the same incremental facts, not independent reconstruction.

Remaining authorized local work: none after final diff review. Remaining local time estimate: complete. External upload/deployment is outside this request; any later release requires separate authority and its transport/hosting gates. Exact rollback names remain allowed; no wildcard was introduced.

## Evidence and rollback

Operations root: `artifacts/opening-incremental-20261101-october-only-r3/`. Key records: `incremental-acceptance.json`, `complete-delta/report.json` and JSONL witnesses, `incremental-acceptance-events.jsonl`, `acceptance-*.log`, `local-http-oracle.json`, `startup.json`, `graph-benchmark.json`, `intentional-full-build-cancellation.json`, and `final-local-result.json`. Source cutoff lineage is alongside the immutable snapshot. Browser scripts/logs/screenshots are in frontend `output/playwright/monthly-20261101/`.

Preserve the September parent/candidate and existing authorized rollback artifacts. Exact previous insights remain under `artifacts/insights/operations-20261101-october-only-r3/rollback-projections/`. No original acquisition, cancelled-build scratch, failed staging attempt or historical evidence was deleted.
