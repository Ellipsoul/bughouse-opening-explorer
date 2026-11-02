# Monthly data and Player Insights result — 2026-11-01

## Acquisition and local publication

The completed acquisition was converted into a new October-only analysis snapshot at the user’s request. All boards ending on or after 1 November 2026 00:00 UTC were excluded from this snapshot; the original acquired source remains preserved. Qualification pointers were reconciled against retained games, excluding November-only qualification from the cohort. All four registered projections were rebuilt from a checked immutable snapshot, exported twice byte-identically, and published to local frontend files. This record is reconciled against the retained machine-readable result records. No deployment, commit, push, or external artifact upload occurred.

- Run: `07c49e93-c6b9-4e7e-94c6-7603d7f30fee`.
- Boards: 8,684,730 → 8,835,204.
- Permanently tracked players: 1,137 → 1,170; 33 new enrollments.
- Closure: zero remaining/failed jobs, active runs, or tracked players without an outcome.
- Snapshot: `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/snapshots/monthly-20261101-october-only-r3/crawler-through-2026-10.db`; SHA-256 `52473c926d78eb2aaa78dd5efc6f319b694c91708842103baace7fdb96109a2a`.
- Insight dataset: `cc434b13a480d4c93c87871084e98eb666c55f5a`.
- Accepted/analyzed/excluded games: 7,019,733 / 7,019,712 / 21.
- Independent reconciliation passed: exact cohort, source/analysis totals, per-player table counts, denominators, nonnegative material counts, bounded high ranks, projection metadata/privacy, and published bytes.

## Projection sizes and checksums

| Projection | Bytes | gzip bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `player-material-insights.json` | 223,633 | 60,427 | `8f0e83146228d302c147347daa42a9519dd01c5092016cf94defa6ff4150eb98` |
| `player-king-height-insights.json` | 875,320 | 152,968 | `de12ceba01d7e1905256d001bf7f635cf7599ca3f88dde8af21315ec9f84252a` |
| `player-drop-heatmap-insights.json` | 2,087,933 | 648,779 | `1d8039e77375f47f48abf6ca3fd380a562835a17d56ff24bc701271d66db3514` |
| `player-material-game-highs.json` | 2,543,982 | 445,266 | `bd39ff763de8f0f80f74d6f95eaf3d5347f0829bbfe212525397d8a1f7dac6de` |

## Verification

Backend preflight: 310 tests passed. Against the published October-only projections, 573 frontend unit tests and 161 component tests passed; TypeScript/ESLint, production build, and frontend diff checks also passed. Logs are retained under `artifacts/opening-incremental-20261101-october-only-r3/`. Desktop/mobile browser checks passed for all five modes at 1440, 320 and 390 pixels, with no horizontal overflow or invalid numeric output; search covered an empty result, newly enrolled `aldehani3`, zero-game `commando_droid`, and a long username. Sort reversal passed. Screenshots and driver logs are under frontend `output/playwright/monthly-20261101/`. The local production build showed the expected local Vercel Analytics 404 and CSS preload warnings, not an insight failure. Opening-tree evidence and the superseding routine policy are recorded separately in `OPENING_INCREMENTAL_RESULT_2026-11-02.md`.

## Reproduction and rollback

The complete original frontend projection set and checksums are retained in `artifacts/insights/operations-20261101-october-only-r3/rollback-projections/` and `preflight.json`. Acquisition log, independent reconciliation, enrollment and terminal ledgers are in that operations directory. Machine-readable snapshot and workflow results are under `snapshots/monthly-20261101-october-only-r3/` and `artifacts/insights/monthly-20261101-october-only-r3/`.

The opening-tree continuation uses `artifacts/opening-incremental-20261101-october-only-r3/`; it retains the September parent and the completed October child. Full-reference builds and dependent parity checks were intentionally cancelled by explicit user instruction after replacing their supervisor. The validated incremental export is the routine candidate; this is not deployment approval.
