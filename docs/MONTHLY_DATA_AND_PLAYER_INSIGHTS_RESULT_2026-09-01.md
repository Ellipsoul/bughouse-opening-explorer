# Monthly data and Player Insights result — 2026-09-01

## Outcome

The September monthly refresh completed successfully. The crawler refreshed the
permanent Chess.com cohort through the completed August period plus the mutable
September partial month, recursively enrolled 68 newly qualifying players,
reached durable closure, and produced a checked immutable source snapshot. All
four registered Player Insights were rebuilt from that snapshot in one source
pass, exported twice deterministically, and atomically published to the local
`bughouse-chess/app/data` build inputs.

No commit, push, upload, promotion, or deployment was performed.

## Crawler acquisition

Run id: `c9071974-7528-4932-962d-7450e506801e`

- Run type: `monthly`
- Started: 2026-09-01 17:28:34 UTC
- Ended: 2026-09-01 18:20:40 UTC
- Duration: 52 minutes 6 seconds
- Jobs processed: 4,149
- Jobs completed: 4,137
- Run-terminal jobs: 12
- Jobs remaining/failed/deferred: 0 / 0 / 0
- Public requests: 4,039
- Callback requests: 137
- Run-scoped HTTP retries, 429s, recoveries, timeouts, network errors, 5xx
  responses, slow responses, and exhausted requests: all 0
- Final terminal ledger: 18 unavailable months, 1 unavailable archive, 0
  unresolved partner probes
- Closure: ready; zero active runs and zero permanently tracked players without
  a completed or terminal archive outcome

The older `latest_error` field still points to a resolved 2026-08-01 DNS error
for `111michael`; it did not recur during this run and is not the current run's
`last_error` (which is null).

### Corpus delta

| Measure | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Stored game boards | 8,195,984 | 8,487,878 | +291,894 |
| Participant rows | 16,391,968 | 16,975,756 | +583,788 |
| Known players | 247,274 | 253,981 | +6,707 |
| Permanently tracked players | 1,013 | 1,081 | +68 |
| Fully crawled players | 1,013 | 1,081 | +68 |
| Candidate players | 245,108 | 251,768 | +6,660 |
| Currently eligible players | 1,013 | 1,014 | +1 |
| Currently dormant players | 1,153 | 1,199 | +46 |
| Complete job rows | 53,140 | 56,285 | +3,145 |

Permanent tracking remains monotonic: current eligibility/dormancy is a
classification, not a collection-retention rule.

### Newly enrolled permanent players

Every enrollment below came from a timestamped `public_game` rating of at least
2000 inside the run's rolling one-year eligibility window. Tracking began
between 17:31:16 and 18:10:00 UTC; recursive lifetime backfills and bounded
partner probes then completed before snapshotting.

| Username | Qualifying rating | Username | Qualifying rating |
| --- | ---: | --- | ---: |
| `bamb00knight` | 2190 | `brendgame` | 2006 |
| `dercostechnology` | 2656 | `down-the-t` | 2256 |
| `east-of-edens` | 2109 | `esquie-33` | 2202 |
| `slider-out-wide` | 2313 | `sokmate` | 2244 |
| `chienbinhvietnam` | 2005 | `vladislav_voitovich` | 2517 |
| `criticalapproach` | 2324 | `dreamsing` | 2273 |
| `fire_moth` | 2018 | `sherendev` | 2051 |
| `vectorveld` | 2245 | `vectorveld314` | 2227 |
| `esfsjc` | 2057 | `nohethto` | 2244 |
| `crocodileyu` | 2503 | `esken` | 2027 |
| `jmg_1108` | 2140 | `john0128` | 2000 |
| `jszeq` | 2005 | `totsamyiparen64` | 2020 |
| `yabooger` | 2002 | `dezzphantom` | 2006 |
| `streamfm` | 2000 | `tactictic` | 2081 |
| `xxundefeatedchampionxx` | 2373 | `a1t19` | 2060 |
| `happy77177` | 2000 | `knightduta` | 2264 |
| `4lifez` | 2090 | `marcustrieschess` | 2157 |
| `phuzer` | 2213 | `sunjagraf` | 2066 |
| `strongerbishop` | 2000 | `user580810382` | 2069 |
| `purple-straw` | 2090 | `natall-com` | 2075 |
| `pointsdotcom` | 2000 | `muted-hamster` | 2000 |
| `yshyne` | 2160 | `boggedhouse` | 2108 |
| `cmmauricio` | 2003 | `kittysaysroar` | 2153 |
| `liiogical` | 2071 | `noordst` | 2002 |
| `megyn-kelly` | 2045 | `haba788` | 2018 |
| `aioriasagitario` | 2007 | `e4isamistake` | 2000 |
| `son_of_bugzilla` | 2001 | `rambo-william-john` | 2016 |
| `mattydperrine` | 2306 | `jkidjr22` | 3049 |
| `anitakusevic19` | 2144 | `qqcanadaum` | 2002 |
| `jostim` | 2009 | `loving_vincent` | 2145 |
| `user583944864` | 2008 | `yoboiisback123456` | 2002 |
| `filip_opheim` | 2002 | `kat71013` | 2001 |
| `lyricl` | 2003 | `nocapflex` | 2327 |
| `lordsguscio` | 2153 | `joeysmithhh` | 2002 |

## Immutable source snapshot

Path: `snapshots/monthly-20260901/crawler-through-2026-08.db`

- Bytes: 15,695,740,928 (14.62 GiB)
- SHA-256:
  `262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228`
- SQLite `quick_check`: `ok`
- Foreign-key violations: 0
- Games: 8,487,878
- Participant rows: 16,975,756
- Tracked/fully crawled players: 1,081 / 1,081
- Latest persisted run: the completed monthly run above

The snapshot was created with SQLite's online backup API only after crawler
closure, then reopened using immutable read-only semantics for integrity and
count checks. The live `data/crawler.db` was not used as the analysis input.

## Player Insights artifact

Path: `artifacts/insights/monthly-20260901/player-insights.db`

- Dataset version: `e5869e33c39039089b2ed07b680e2b81c0a9fbe5`
- Schema version: 4
- Bytes: 24,862,720 (23.71 MiB)
- SHA-256:
  `ee76e64e0d1d4025fe5ed790d72cbd72db67941850be803081173765898efbbd`
- SQLite `quick_check`: `ok`
- Foreign-key violations: 0
- Tracked players: 1,081
- Accepted games: 6,748,001 (+231,523 from the August artifact)
- Analyzed games: 6,747,980 (+231,523)
- Replay-excluded games: 21 (unchanged)
- Accepted/analyzed plies: 335,988,511 / 335,987,062
- Adapter skips: 1,101,106 empty TCN; 638,771 short non-checkmates
- Build time: 818.40 seconds
- Throughput: 8,245.36 accepted games/second
- Peak RSS: 209,240,064 bytes (199.55 MiB)

The reconciliation `6,748,001 = 6,747,980 + 21` holds. Every excluded replay
has a bounded anomaly record in SQLite and no raw TCN, internal game UUID,
content hash, or anomaly evidence crosses into the browser projections.

### Semantic row checks

| Table/contract | Rows | Violations |
| --- | ---: | ---: |
| Players | 1,081 | 0 |
| Material: 5 piece rows/player | 5,405 | 0 |
| King height: 8 heights/player | 8,648 | 0 |
| Drop squares: 2 colors × 5 pieces × 64 squares/player | 691,840 | 0 |
| Drop color ledgers: 2/player | 2,162 | 0 |
| Material game highs | 12,854 | 0 |
| Material anomaly evidence | 21 | — |

Additional checks found zero negative counts, zero per-color game
reconciliation errors, zero game-high groups above three records, and zero
game-high rank gaps. Game-high sign, rank, color, URL, and uniqueness contracts
are also enforced by the artifact schema.

## Browser projections

Each staged projection was independently exported twice and required to have
the same SHA-256 before the complete four-file set was atomically published.
All four declare the same source snapshot, dataset version, 1,081-player
cohort, 6,748,001 accepted games, 6,747,980 analyzed games, and 21 exclusions.

| Projection | Raw bytes | gzip -9 bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `player-material-insights.json` | 207,085 | 56,953 | `1994069225bdb97494a39d38a518cee48e9b95c2f560d90c9d49f4adf29aac2a` |
| `player-king-height-insights.json` | 832,605 | 145,922 | `0bcf5eb085ebb2a73020ce06cb913e0e9fb5052cbd8938adcbd87a6077f396c0` |
| `player-drop-heatmap-insights.json` | 1,939,993 | 609,730 | `231b2091ab2a77b874f42c53dd19e81fb67f28100241638c9af5a28a166d735e` |
| `player-material-game-highs.json` | 2,360,343 | 414,276 | `6af56f82bfc33b26d3bbae819af12101a677fc238bfa5b6decab08086a049d56` |

## Verification

- Backend: `PYTHONPATH=. .venv/bin/pytest -q` — 223 passed.
- Frontend unit: `npm run test:unit` — 516 passed across 64 files.
- Frontend component: `npm run test:component` — 151 passed across 17
  Cypress specs with local Firebase emulators.
- TypeScript/ESLint: `npm run lint` — passed.
- Production build: `npm run build` — passed; `/player-insights` statically
  prerendered. The sandboxed first attempt could not fetch configured Google
  Fonts; the permitted network retry succeeded.
- Browser: the production build was exercised with Playwright at desktop and
  390 × 844. All five modes rendered the new cohort and counts: Net Material,
  Net Material per Game, Average King Height, Piece Drop Heat Maps, and Material
  Game Highs. The narrow viewport had `scrollWidth = clientWidth = 390`.
- Browser console: no Player Insights feature/data errors. Local production
  emitted the expected undeployed Vercel Analytics 404/log, a report-only
  Google frame-ancestor message, and CSS preload warnings.

The initial frontend run correctly failed four tests that pinned August's exact
cohort/version/totals. Those tests now verify non-empty, internally consistent,
versioned projection contracts, so future monthly data refreshes do not require
manual fixture-constant edits. The full unit suite passed after this change.

## Reproduction, rollback, and release boundary

Machine-readable records:

- `snapshots/monthly-20260901/snapshot-result.json`
- `artifacts/insights/monthly-20260901/monthly-refresh-result.json`
- `artifacts/insights/monthly-20260901/monthly-workflow-result.json`

The canonical future procedure is
`docs/MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md`; the implementation entry
point is `scripts/run_monthly_refresh.py`. A retry must use a new immutable run
label. Rollback the website inputs as one complete four-projection set using
the previous Git revision; do not delete either immutable September artifact.
Deployment remains a separate, explicit authorization gate.
