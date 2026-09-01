# Material Game Highs result (2026-08-12)

## Outcome

Material Game Highs is complete locally across `bughouse-opening-explorer` and
`bughouse-chess`. It retains only each permanently tracked player's three
greatest positive and three greatest negative single-game **net** material
results under each of the Bughouse and Standard piece-value presets. It is
available through the new `material-game-highs` Player Insights tab in the
local production build.

The precise cohort, eligibility, attribution, malformed-data, storage,
publication, and UI contract is in
[`PLAYER_MATERIAL_GAME_HIGHS_INSIGHT_SPEC_2026-08-12.md`](PLAYER_MATERIAL_GAME_HIGHS_INSIGHT_SPEC_2026-08-12.md).
No live crawler database was opened or changed. Nothing was committed, pushed,
deployed, or published.

## Settled semantics

- One game's score is the signed net used by the existing two material views:
  material captured by the tracked player minus material captured by the
  opponent on that board.
- Strictly positive scores qualify for **Most won** and strictly negative
  scores qualify for **Most lost**. Net-zero games are not filler results.
- A captured promoted pawn counts as a pawn, regardless of its promoted role.
  En passant, dropped-piece captures, same-account seats, and malformed replay
  retain the existing material analyzer's tested behavior.
- Bughouse and Standard results are ranked and stored independently. The
  browser switches between precomputed top-three sets rather than rescoring a
  discarded game history.
- Equal scores use newer known end time, then stable game UUID. This order is
  deterministic both when choosing the retained three and when exporting them.
- A result must have a public Chess.com game URL because the insight presents
  each extreme as an inspectable game reference.

The existing lifetime material tables could not answer this question because
they intentionally discard game boundaries. The new analyzer instead reuses
the successful game-local capture ledgers and final replay position in the
shared source pass. It feeds four bounded top-three accumulators per player and
never retains or sorts a player's complete game history. The maximum additional
candidate state is `players x 2 presets x 2 directions x 3 games`.

## Implementation

The shared builder now records schema version 4 and analyzer version
`player-material-game-highs-v1`. Its feature-owned
`player_material_game_highs` table stores exact signed half-points, deterministic
rank, internal game identity, public URL, end time, player colour, and the
completed four-field FEN.

`export_material_game_highs` and
`scripts/export_material_game_highs.py` produce a deterministic browser-safe
projection containing only dataset metadata, player identity, analyzed-game
context, preset/direction arrays, URLs, dates, colours, final FENs, and signed
half-point values. Internal UUIDs, content hashes, raw TCN, anomaly evidence,
and discarded candidates remain local.

The Relay UI adds:

- a stable `?insight=material-game-highs` route value;
- Most won / Most lost and Bughouse / Standard switching;
- player search, non-negative minimum-games filtering, and 25/50/100-row
  pagination without recomputing global ranks;
- up to three equal final-position cards per player with signed score, date,
  colour, and a new-tab Relay link; and
- static, non-interactive boards using the analysis board's square palette and
  Wikipedia piece artwork. The pieces occupy 92% of a square, while the browser
  lazily loads the same 12 cacheable piece URLs already used by Relay.

Desktop keeps three expanding boards in one row. Phone layouts use 272-pixel
game cards in a player-row scroller; the leaderboard page itself remains
viewport-width.

## Representative benchmark

A temporary 250,000-row source sample produced 225,558 accepted games in
30.57 seconds, or 7,377.8 accepted games per second, with 131,104,768 bytes
peak RSS. It produced 6,955 retained rows across 725 players. Every
player/preset/direction group contained at most three rows. The temporary
sample and output stayed outside both worktrees.

## Full immutable extraction

Input:

- snapshot: `snapshots/full-tree-input-20260804/restored-crawler-post-qualification-20260802.db`
- snapshot SHA-256:
  `04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`
- cohort policy: `permanent-tracking-v1`
- adapter policy: `opening-adapter-v2-short-non-checkmate`

Output:

- artifact:
  `artifacts/insights/full-post-qualification-20260802-material-game-highs-v1/player-insights.db`
- artifact SHA-256:
  `59bb0542b43f1cefda2f381c44d8fb66300076cadcd2b8108cab9eb0a575cd90`
- artifact size: 23,351,296 bytes
- dataset version: `6d6869bc792e195644be7129ca5fb5571020aa63`
- schema version: 4
- build result:
  `artifacts/insights/full-post-qualification-20260802-material-game-highs-v1/player-insights-build-result.json`

Measured run:

| Measurement | Result |
| --- | ---: |
| Permanently tracked players | 1,013 |
| Accepted games | 6,516,478 |
| Successfully analyzed games | 6,516,457 |
| Replay-excluded games | 21 |
| Accepted plies | 324,522,210 |
| Analyzed plies | 324,520,761 |
| Elapsed time | 776.23 seconds |
| Throughput | 8,395.08 accepted games/second |
| Peak RSS | 192,970,752 bytes |

All 21 replay exclusions were the already bounded
`undefined_tcn_fragment` anomaly. They contributed neither partial lifetime
material nor game-high candidates.

## Artifact and compatibility validation

- SQLite `quick_check`: `ok`.
- Foreign-key violations: 0.
- Retained game-high rows: 12,075, comprising 6,042 won and 6,033 lost rows.
- Players with at least one retained reference: 1,009 of 1,013.
- Maximum rows per player/preset/direction group: 3.
- Direction/sign or rank violations: 0.
- Invalid public URLs: 0.
- Non-contiguous rank groups: 0.
- Bidirectional `EXCEPT` comparisons against the preceding full drop-heatmap
  artifact found zero differences in players, game counts, lifetime material,
  king height, king-height evidence, drop counts, drop squares, and anomaly
  rows.

## Static projection

The checked projection is
`bughouse-chess/app/data/player-material-game-highs.json`.

- players: 1,013
- retained game references: 12,075
- raw size: 2,216,498 bytes
- deterministic `gzip -9 -n` size: 389,022 bytes
- SHA-256:
  `7a2a42352103100a1b6d3135c521d0e949f8d8fd721ece4b68f0fdb0307d621d`
- repeated export: byte-identical

The three earlier projections were regenerated from the same schema-4 artifact
so every tab shares dataset identity. Their SHA-256 values are:

- material: `538c8584c4ba68b2ed4ca98f183f096162c6a2508b59ede01db57f8b5053407a`
- king height: `368aa8fcdc7ec2f981082d74fe96c1c423a8e7e0e1dac4b9a93ca5bf141789a1`
- drop heat maps: `cd6e9d9eb5dd0c3ddfbe088890b37a676150a2108ff8108c8e801d54698e8b83`

## Verification

Backend:

- full Python suite: 214 passed;
- focused extraction/export suite: 44 passed before the full build; and
- fixture coverage includes signed net rather than gross captures, independent
  presets, bounded retention, deterministic ties, atomic malformed replay, and
  captured-promoted-pawn scoring.

Frontend:

- full Vitest suite: 64 files and 513 tests passed;
- Cypress component suite: 17 specs and 151 tests passed;
- TypeScript and ESLint: passed;
- optimized Next.js production build: passed, including static prerender of
  `/player-insights`;
- desktop browser check: 2,560 x 1,440, with three readable analysis-style
  boards in each row;
- phone browser check: 390 x 844, with document client and scroll widths both
  390 pixels and the first row's 293-pixel viewport containing an 840-pixel
  internal game-card strip; and
- browser console: no feature exception. The local-only Vercel Analytics 404
  and Next.js CSS-preload warning remain unrelated to this insight.

## Refresh procedure

For a future named immutable snapshot, choose a new output directory and run:

```bash
.venv/bin/python scripts/build_player_insights.py \
  snapshots/<snapshot>.db \
  artifacts/insights/<version>/player-insights.db \
  --snapshot-sha256 <snapshot-sha256> \
  --result artifacts/insights/<version>/player-insights-build-result.json

.venv/bin/python scripts/export_material_game_highs.py \
  artifacts/insights/<version>/player-insights.db \
  ../bughouse/bughouse-chess/app/data/player-material-game-highs.json \
  --database-sha256 <player-insights-db-sha256> \
  --replace
```

Export the lifetime material, king-height, and drop-heatmap projections from
the same verified artifact as documented in the Relay README. Then re-run
SQLite validation, deterministic export comparison, both repositories' tests,
lint, production build, and wide/phone browser checks. Never substitute or
mutate `data/crawler.db`.

## Rollback

The checked JSON and frontend component are the publication switch. Rollback
means reverting the Material Game Highs projection and frontend tab, then
rebuilding before any separately authorized deployment. The immutable schema-4
artifact and result record can remain local for reproduction and comparison;
the earlier schema-3 artifact was not changed.
