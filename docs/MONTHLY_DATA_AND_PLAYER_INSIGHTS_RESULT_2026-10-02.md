# Monthly data and Player Insights result — 2026-10-02

## Outcome

The September 2026 data refresh completed on 2 October. The existing monthly runner refreshed September and mutable October, permanently enrolled 56 players through the reachable Bughouse network, completed their available lifetime histories, and reached clean crawler closure. A new checked immutable snapshot supplied one shared build of all four registered projections, covering all five implemented UI modes. Double exports were byte-identical and the complete validated set was published to local `bughouse-chess/app/data`.

No commit, push, deployment, or packed Opening Explorer rebuild/release was performed. Previous snapshots, artifacts, and historical result documents remain intact.

## Preflight and retained baseline

- Both working trees were clean before starting. Backend revision: `3c032ff93e89557817cd78b058c0531e3dd30c19`; frontend revision: `517cf13eaecffa1fe9c7ccd463eba4e6c1afba7c`.
- Applicable instructions were checked in both repositories and their ancestor directories; no `AGENTS.md` was present. The documentation map, monthly runbook, latest dated monthly result, crawler/handoff/roadmap, and Player Insights development guide supplied the operational contract.
- Available disk space: 774 GiB before acquisition; 759 GiB after snapshot creation. Existing source data was about 15 GiB; retained snapshots about 29 GiB before this run. Capacity comfortably covered the new 16.07 GB source snapshot and 26.17 MB derived artifact.
- The persisted latest run was the completed August-period refresh. Closure was ready, with zero pending/failed jobs. There was no September-period active/interrupted run or existing monthly output. A fresh label `20261002` was used.
- The live frontend registry contains Net Material, Net Material per Game, Average King Height, Piece Drop Heat Maps, and Material Game Highs. Its four static imports match `PLAYER_INSIGHT_PROJECTIONS`; the two material modes share one projection.
- Exact previous projection bytes and checksums are retained under `artifacts/insights/operations-20261002/rollback-projections/`, alongside `preflight.json`, `before-status.json`, and the acquisition log.

Invocation:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_monthly_refresh.py \
  --year 2026 --month 9 --run-label 20261002 \
  --frontend-data-dir ../bughouse/bughouse-chess/app/data --publish
```

## Acquisition, terminal outcomes, and coverage

- Run: `b9303035-71b8-4413-86da-b5658a35e5c2` (`monthly`, configuration `{"month": 9, "year": 2026}`).
- Started: 2026-10-02 18:58:40 UTC; ended: 2026-10-02 19:47:39 UTC; duration: 2,939 seconds (48 minutes 59 seconds).
- Worker outcomes: 4,029 processed; 4,013 completed; 16 terminal; zero failed/deferred. These are executed-job outcomes, not the net change in durable completed rows, since monthly jobs are requeued.
- Public requests: 3,939; callback requests: 93. One callback request encountered a proxy/network disconnection, retried once, and recovered. One slow response was recorded. Zero 429s, timeouts, 5xx responses, or exhausted requests; the circuit breaker did not trip; run `last_error` is null.
- Final closure: zero queued, leased, deferred, failed, or active work; zero tracked players without completed/terminal archive outcomes. Final terminal ledger: 34 unavailable months (+16), one historical unavailable archive (unchanged), zero unresolved probes.
- The global `latest_error` still refers to the resolved 1 August DNS incident. It is historical, not a failure in this run.
- All 1,081 baseline permanent players have a completed or terminal September outcome. The final tracked cohort includes 1,010 currently eligible and 127 dormant players; dormancy does not end collection. All 1,137 tracked players have completed lifetime outcomes.
- Six pre-existing September-unavailable endpoints were retained as terminal and were not fetched again: 1,075 September jobs and 1,081 mutable-October jobs were initially queued. New qualifiers received available lifetime archives back to January 2016 and deterministic bounded partner probes. Collection/discovery continued recursively until closure.
- Newly enrolled `cephulac` had no September month in the authoritative archive manifest. A separate post-closure read-only verification of `/pub/player/cephulac/games/2026/09` returned HTTP 200 with zero archive/Bughouse games. This one verification request is additional to the persisted crawler request counters. Its observed September participation remains available through opponents’ archives. The checked snapshot was not modified.
- Coverage remains the transitive qualifying population reachable from the existing seeds/cohort, not a claim of global Chess.com coverage.

### Corpus deltas

| Measure | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Stored boards | 8,487,878 | 8,684,730 | +196,852 |
| Participant rows | 16,975,756 | 17,369,460 | +393,704 |
| Known players | 253,981 | 257,337 | +3,356 |
| Permanently tracked players | 1,081 | 1,137 | +56 |
| Fully crawled players | 1,081 | 1,137 | +56 |
| Candidate players | 251,768 | 255,076 | +3,308 |
| Eligible players | 1,014 | 1,010 | -4 |
| Dormant players | 1,199 | 1,251 | +52 |
| Completed durable job rows | 56,285 | 59,307 | +3,022 |

### New permanent enrollments

All 56 new enrollments have completed lifetime outcomes. The table reports the snapshot’s latest qualifying rating, which can supersede the original enrolling observation. The full timestamped enrollment ledger is retained in `artifacts/insights/operations-20261002/reconciliation.json`. Prior tracked identities are a strict subset of the new cohort.

| Username | Qualifying rating | Username | Qualifying rating |
| --- | ---: | --- | ---: |
| `0gzpanda` | 2093 | `abstract_idea` | 2001 |
| `agw2016` | 2007 | `ai387` | 2090 |
| `amaslidan` | 2151 | `anti-stupid` | 2052 |
| `b2147483647` | 2026 | `blackmamba4345` | 2615 |
| `buglund` | 2004 | `bungle_bug` | 2236 |
| `cephulac` | 2164 | `chessintuition0906` | 2009 |
| `chessmadara` | 2222 | `dan-biizerian` | 2151 |
| `desirousprism75` | 2010 | `develop-fast` | 2003 |
| `dropanite` | 2001 | `dylighted-catan` | 2047 |
| `dyslexism` | 2207 | `ejtang` | 2004 |
| `fastestbugplayer` | 2001 | `firkintime` | 2005 |
| `gmbrewchess` | 2072 | `gptastra` | 2504 |
| `gptsol` | 2504 | `grandmaster1369` | 2268 |
| `hoanghdang2009` | 2035 | `hollygolden` | 2002 |
| `ivsagg` | 2010 | `khiggins89` | 2315 |
| `linhchessvn04` | 2010 | `lupta_robin` | 2006 |
| `orange_ghost` | 2404 | `patzerseesacheckpatzergiv` | 2086 |
| `phyomnicus` | 2092 | `playa_alt` | 2003 |
| `playfastandsafenoob` | 2002 | `rayman333` | 2014 |
| `rbeh` | 2007 | `rl-1` | 2037 |
| `serg175` | 2000 | `shadowking71` | 2428 |
| `speedyshadowater` | 2005 | `the_undefeated_one_2017` | 2002 |
| `throh` | 2001 | `tititularcharacter` | 2443 |
| `tomrany` | 2027 | `toulisp` | 2001 |
| `vjfaker` | 2269 | `wesleywang1` | 2022 |
| `xiight` | 2501 | `yeilowsubmarine` | 2113 |
| `ymflb8hj43890rfjiwo93i` | 2015 | `zhuu96` | 2157 |
| `zoltanbolt_04` | 2202 | `zyoimmm22` | 2231 |

### New terminal-unavailable months

| Username | Month |
| --- | --- |
| `aka_regulus` | 2026-09 |
| `aka_regulus` | 2026-10 |
| `chuckmoultonakalibtard` | 2026-10 |
| `commando_droid` | 2026-09 |
| `commando_droid` | 2026-10 |
| `mudr-zlo` | 2026-10 |
| `panefsky_fics` | 2026-10 |
| `ryantime` | 2026-09 |
| `ryantime` | 2026-10 |
| `skymaomao` | 2026-10 |
| `slowfeasus` | 2026-10 |
| `truce-baldazzi` | 2026-10 |
| `walmart-12teen` | 2026-09 |
| `walmart-12teen` | 2026-10 |
| `zyoim22` | 2026-09 |
| `zyoim22` | 2026-10 |

## Immutable source and derived identities

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `snapshots/monthly-20261002/crawler-through-2026-09.db` | 16,067,272,704 | `241f5e8dc353d42c751382223c386fa8fc495b8b792ada52920006695f2404eb` |
| `artifacts/insights/monthly-20261002/player-insights.db` | 26,169,344 | `49d8a14e8adfe782d9501b029f305eed964071f296ed12186429e32867c0dfd2` |

Both databases passed SQLite `quick_check` and zero-violation foreign-key checks. The source was created using SQLite online backup after closure and opened read-only/immutable for analysis. The live crawler was not the analyzer input. The independent post-build audit verified the derived foreign-key check again before review.

- Dataset: `c41ea52519972b543a3cfbed54dd063c0d685b5a`; schema: 4; cohort: `permanent-tracking-v1`.
- Adapter: `opening-adapter-v2-short-non-checkmate`. Analyzer versions remain `player-material-v1`, `player-king-height-v1`, `player-drop-heatmap-v1`, and `player-material-game-highs-v1`.
- Accepted games: 6,899,498 (+151,497); analyzed: 6,899,477 (+151,497); excluded: 21 (unchanged). Accepted = analyzed + excluded.
- Accepted/analyzed plies: 343,356,605 / 343,355,156.
- Adapter skips: 1,128,912 empty TCN and 656,320 short non-checkmates. Source boards = accepted + both skip categories.
- All 21 anomaly identities and reasons match the previous artifact; exclusion policy is unchanged and no partial replay contributions are retained.
- Shared build: 810.18 seconds, 8516.04 accepted games/second, peak RSS 221,790,208 bytes.

### Semantic reconciliation

| Table | Rows |
| --- | ---: |
| `material_anomalies` | 21 |
| `player_drop_color_game_counts` | 2,274 |
| `player_drop_squares` | 727,680 |
| `player_game_counts` | 1,137 |
| `player_king_height` | 9,096 |
| `player_material` | 5,685 |
| `player_material_game_highs` | 13,476 |
| `players` | 1,137 |

Verified exact cohort identity, five material rows, eight height buckets, 640 color/piece/square rows, and two color denominator rows per player. Zero negative material counts; zero player/color denominator or king-height-total mismatches; zero game-high groups above three records or rank gaps. The schema enforces signs, rank, color, public URLs, and uniqueness. All exported schema/cohort/adapter/analyzer/dataset/source versions reconcile with the derived build record.

## Deterministic browser projections

Each export ran twice from the same artifact and matched by SHA-256. Independent checks confirmed identical staged/published bytes, exact player identity sets, and shared metadata. Deterministic gzip sizes were measured with `gzip -9 -n`. No raw TCN, SQLite, internal UUID, content hash, or anomaly evidence is present in the projection fields.

| Projection | Raw bytes | gzip -9 -n bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `player-material-insights.json` | 217,427 | 59,354 | `6a3d712b77e781d724d594d780b43f7d37d6a53fbc88d56a5790ef8332bec874` |
| `player-king-height-insights.json` | 858,039 | 150,342 | `198b54247d845466213f8de186cc36f30252bf4c36de4705f748720a30ae891b` |
| `player-drop-heatmap-insights.json` | 2,032,360 | 633,948 | `bb37dc060a9936c8d9c9c30bb9c1720bdeb528c1aacbd7816a71ae807c24539c` |
| `player-material-game-highs.json` | 2,475,103 | 433,944 | `ac87765c18d001c50ec1e84e75bcd13e329ecf108f45bc4d84add159d75c4438` |

## Verification and bounded workflow repair

- Backend suite: 255 passed, including the new integrity-gate regression test. The initial 254-test suite passed before the repair.
- Frontend unit suite against the published data: 540 passed across 68 files.
- Frontend component suite against the published data: 159 passed across 18 Cypress specs with owned local Firebase emulators. The baseline component suite also passed.
- TypeScript/ESLint: passed. Production build: passed; `/player-insights` is statically prerendered. Both repositories passed `git diff --check`.
- Local production browser: all five modes rendered at 1440 × 1000, 320 × 844, and 390 × 844 with no horizontal overflow. The 320/390 phone checks also exercised empty search, new `0gzpanda`, long `patzerseesacheckpatzergiv`, and zero-game `commando_droid` with null/emdash behavior and no NaN/Infinity.
- Desktop interactions passed material/king-height sort reversal, pagination, empty search, new enrollment, long username, zero/null behavior, inclusive minimum-games boundaries at 673/674 for `0gzpanda`, drop comparison with a zero-game player, all drop color channels, game-high won/lost direction and pagination. Public numeric game links, `_blank`, and `noopener` attributes were validated. Destinations were inspected; this is local insight verification, not a Production analysis-route verification.
- Browser requests contained no database download; projection privacy was checked independently. The sole console error was the expected local `/_vercel/insights/script.js` 404; CSS preload warnings were also present. No Player Insights data/rendering errors occurred.
- Screenshots are retained in `bughouse-chess/output/playwright/monthly-20261002/` (desktop and both phone widths), with browser logs copied into the local operations directory.
- Bounded repair: `build_player_insights_artifact` computed foreign-key violations but previously did not reject them. A deliberately orphaned fixture reproduced the erroneous successful export. The gate now raises before exporter invocation/result publication, and the regression confirms the partial database is retained for diagnosis. No analyzer or policy outputs changed. The already running workflow had loaded the earlier code; its actual derived database was independently checked and had zero violations.
- The runbook now explains the multi-minute initial eligibility reconciliation, preserving explicit period/label during resume finalization, baseline/rollback retention, and the corrected integrity gate. Current README counts and sizes were updated from actual artifacts; historical result documents were preserved.

## Reproduction and rollback

Machine-readable records:

- `snapshots/monthly-20261002/snapshot-result.json`
- `artifacts/insights/monthly-20261002/monthly-refresh-result.json`
- `artifacts/insights/monthly-20261002/monthly-workflow-result.json`
- `artifacts/insights/operations-20261002/reconciliation.json`
- `artifacts/insights/operations-20261002/before-status.json` and `after-status.json`
- `artifacts/insights/operations-20261002/workflow.log`

Rollback the complete four-file frontend projection set to revision `517cf13eaecffa1fe9c7ccd463eba4e6c1afba7c` or the exact saved files in `artifacts/insights/operations-20261002/rollback-projections/`. Its checksum manifest is in `preflight.json`. Rebuild the frontend after restoration; any deployment is a separate authorized operation. Keep both this snapshot/artifact and `monthly-20260901` for reproduction and comparison.

The crawler contains the newly acquired source truth; projection rollback does not undo acquisition. A retry creates a fresh immutable label (for example `20261002-r2`) and uses explicit `--year 2026 --month 9 --skip-crawl` after verifying the same completed run. Never overwrite a checked snapshot or analyze the live crawler. The packed Opening Explorer retains its separately recorded source/release and is outside this operation.

Operational guidance: [`MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md`](MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md).
