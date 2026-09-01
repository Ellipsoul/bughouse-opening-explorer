# Piece Drop Heat Maps: full result (2026-08-09)

## Outcome

Piece Drop Heat Maps is complete as the third feature-owned Player Insight.
The shared local extraction now stores exact White and Black drop-square
channels for pawn, knight, bishop, rook, and queen. The checked web projection
supports White-only, Black-only, and rank-normalized Combined views, plus an
unlimited searchable player comparison.

The compressed projection is practical for static publication: the 1,013-player
JSON is 1,822,069 bytes raw and 573,871 bytes with `gzip -9`. It is isolated in
the heat-map insight's lazy-loaded chunk and therefore does not enlarge the
initial material view. No runtime Player Insights API was introduced.

The exact semantic contract is
[`PLAYER_DROP_HEATMAP_INSIGHT_SPEC_2026-08-09.md`](PLAYER_DROP_HEATMAP_INSIGHT_SPEC_2026-08-09.md).

## Source and build identity

The build read this immutable snapshot, never the live `data/crawler.db`:

- snapshot:
  `snapshots/full-tree-input-20260804/restored-crawler-post-qualification-20260802.db`;
- snapshot SHA-256:
  `04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`;
- cohort policy: `permanent-tracking-v1`;
- adapter policy: `opening-adapter-v2-short-non-checkmate`;
- material analyzer: `player-material-v1`;
- king-height analyzer: `player-king-height-v1`;
- drop analyzer: `player-drop-heatmap-v1`;
- schema version: `3`; and
- dataset version: `2133356ea2a468c93ef084d65b7ec760b3c0b4a2`.

The output is:

- SQLite:
  `artifacts/insights/full-post-qualification-20260802-drop-heatmap-v1/player-insights.db`;
- size: 19,357,696 bytes;
- SHA-256:
  `d23c07e08ba445c38ff82f49797cc5485e6a6b395bc92b8fad2b4d84c49625a8`;
- build result:
  `artifacts/insights/full-post-qualification-20260802-drop-heatmap-v1/player-insights-build-result.json`;
- build-result SHA-256:
  `d1d29af7e7fb48f406e5d787a338a102274a73969bfb949c7379272875f4a2e8`.

The checksum-verified full scan completed in 650.50 seconds at 10,017.62
accepted games per second with peak RSS of 195,379,200 bytes. A preceding
250,000-source-outcome representative run accepted 225,558 games in 25.45
seconds at 8,863.7 accepted games per second with 109,035,520 bytes peak RSS.

## Corpus reconciliation

The complete run produced:

- 1,013 permanently tracked players;
- 6,516,478 accepted games and 324,522,210 accepted plies;
- 6,516,457 completely analyzed games and 324,520,761 analyzed plies;
- 21 atomically replay-excluded games, all classified
  `undefined_tcn_fragment`;
- 1,063,593 `empty_tcn` adapter skips; and
- 615,913 `short_non_checkmate` adapter skips.

The colour-specific analyzed appearances were 4,225,546 as White and 4,210,265
as Black. They are deliberately not required to sum to the common game
denominator: a game can contain two tracked players, and one normalized account
occupying both seats is deduplicated only in the common denominator.

The artifact contains exactly:

- 1,013 player rows;
- 2,026 colour-denominator rows;
- 648,320 raw drop rows (`1,013 x 2 x 5 x 64`);
- 648,320 colour-view rows; and
- 324,160 combined-view rows (`1,013 x 5 x 64`).

There were no negative counts, missing squares, colour-denominator violations,
or common-denominator violations. `PRAGMA quick_check` returned `ok` and
foreign-key validation returned zero rows.

The material and king-height projections were preserved exactly apart from the
new dataset identity: bidirectional `EXCEPT` comparisons against the preceding
king-height artifact returned zero rows for player game counts, player material,
player king height, score-8 evidence, and anomaly tables.

## Drop distribution

The full cohort made 48,454,388 attributed drops:

| Piece | Drops | Share |
| --- | ---: | ---: |
| Pawn | 17,225,640 | 35.55% |
| Bishop | 13,196,636 | 27.24% |
| Knight | 12,872,197 | 26.57% |
| Queen | 2,619,459 | 5.41% |
| Rook | 2,540,456 | 5.24% |

By source colour and piece:

| Piece | White | Black |
| --- | ---: | ---: |
| Pawn | 8,597,982 | 8,627,658 |
| Knight | 6,288,986 | 6,583,211 |
| Bishop | 6,853,330 | 6,343,306 |
| Rook | 1,210,859 | 1,329,597 |
| Queen | 1,262,795 | 1,356,664 |

Across the rank-normalized Combined corpus, the most-used square was `h6` for
pawns (1,391,123), `e5` for knights (1,204,953), `g3` for bishops (759,072),
`g3` for rooks (173,252), and `f7` for queens (149,941). These are descriptive
corpus totals, not claims that those squares are objectively best.

The most represented players by common analyzed games are:

| Player | Games | Drops |
| --- | ---: | ---: |
| outrunyou | 123,302 | 823,173 |
| nochewycandy | 99,031 | 615,305 |
| biggerbishop | 86,603 | 523,977 |
| chuckmoulton | 84,729 | 415,509 |
| Dielie | 82,106 | 486,535 |

## Static projection

The deterministic browser projection is
`bughouse-chess/app/data/player-drop-heatmap-insights.json`:

- schema version: `1`;
- players: 1,013;
- raw size: 1,822,069 bytes;
- `gzip -9` size: 573,871 bytes;
- SHA-256:
  `2af62cca78fec201c5932219c120b2d1892b2408889c116bb7ba8de2f41fad83`;
- fixed channel shape: `2 colours x 5 pieces x 64 squares` per player; and
- repeated export: byte-identical.

The export retains raw White and Black integer counts and their separate game
denominators. Combined counts and percentages are deterministic frontend
derivations; Black ranks map to `9 - rank` and files are preserved.

The material and king-height projections were regenerated from the same
artifact so all three share the new dataset identity. Their payload data was
unchanged apart from that identity:

- material: 194,309 bytes, SHA-256
  `966e4717efddfe4847cb961d05dc4677af164206d27049c3963881ad2ed65ee8`;
- king height: 791,817 bytes, SHA-256
  `db0d54e63de1a5091f3b5ad3d603a208aa26bec9a9fed6085c8e327a612d1c0d`.

## Web experience

The fourth Player Insights chip uses a custom semantic CSS checkerboard rather
than a chess interaction or charting dependency. Each piece has its own colour
family; square intensity is normalized within that player, mode, and piece.
Every non-zero square displays its exact count and share, while every square
also has an accessible count-and-percentage name and hover label.

With no selected players, one **All tracked players** row places the five
cohort-wide piece boards side by side. The browser derives it from the existing
static projection by summing every `players[].dropsByColor` channel by colour,
piece, and square. It does not include untracked seats or sum player game
counts; the header uses the dataset-level analyzed-game count.

The searchable multi-select uses suggestions, removable chips, and no arbitrary
selection limit. Once players are selected, the comparison transposes the
layout: five piece columns sit side by side and selected players stack
top-to-bottom inside each column. On narrow screens, that comparison scrolls
horizontally inside its region while the page itself remains viewport-width.

The mode control provides:

- **Combined** — White source squares plus rank-reflected Black squares;
- **White** — exact White source squares and White analyzed appearances; and
- **Black** — exact, unnormalized Black source squares and Black analyzed
  appearances, drawn from White's perspective with rank 8 at the top.

Changing mode updates game counts, distributions, and percentages, and
the desktop orientation explanation. That secondary explanation is hidden on
mobile to conserve filter space.

The revised boards have a 252-pixel minimum width, exactly 75% larger than the
first 144-pixel pass. Five-column grids divide additional available width among
the boards on larger screens; smaller containers scroll horizontally. The
cohort identity and dataset game count share a compact header above the
aggregate row, and the repeated “Count and share of this piece's drops” copy
remains omitted.

The insight can be shared directly at
`/player-insights?insight=piece-drop-heatmaps`. All four Player Insights chips
use their stable IDs as query values, and switching chips updates the address
without discarding unrelated parameters or triggering another data load.

## Verification

Completed verification:

- opening-explorer suite: 206 tests passed;
- bughouse-chess unit suite: 504 tests passed across 60 files;
- bughouse-chess component suite: 151 tests passed across 17 specifications;
- TypeScript and ESLint: passed;
- optimized Next.js production build: passed;
- desktop browser: the permanent-cohort aggregate was visually inspected at
  1,440 x 1,000; its piece totals matched the tracked-player static projection;
- mobile browser: the raw Black view, cohort header, player-selection
  transition, comparison, and return to the aggregate were inspected at 390 x
  844;
- mobile document width: 390 px scroll width and 390 px client width;
- intended comparison scroller: 1,408 px content inside a 332 px client region;
  and
- local console: no feature errors; only the expected undeployed Vercel
  Analytics 404 and preload notices.

## Refresh procedure

From `bughouse-opening-explorer`, choose a fresh output directory and use the
recorded snapshot checksum:

```bash
.venv/bin/python scripts/build_player_insights.py \
  snapshots/<snapshot>.db \
  artifacts/insights/<version>/player-insights.db \
  --snapshot-sha256 <snapshot-sha256>

.venv/bin/python scripts/export_player_insights.py \
  artifacts/insights/<version>/player-insights.db \
  ../bughouse/bughouse-chess/app/data/player-material-insights.json \
  --database-sha256 <player-insights-db-sha256> \
  --replace

.venv/bin/python scripts/export_king_height_insights.py \
  artifacts/insights/<version>/player-insights.db \
  ../bughouse/bughouse-chess/app/data/player-king-height-insights.json \
  --database-sha256 <player-insights-db-sha256> \
  --replace

.venv/bin/python scripts/export_drop_heatmap_insights.py \
  artifacts/insights/<version>/player-insights.db \
  ../bughouse/bughouse-chess/app/data/player-drop-heatmap-insights.json \
  --database-sha256 <player-insights-db-sha256> \
  --replace
```

Review all projection metadata and checksums, then repeat backend tests,
frontend tests, lint, production build, and responsive browser checks.

## Rollback

The live crawler was not read or changed. No deployment was performed. To roll
back this local/publication candidate, revert the checked frontend projection,
heat-map components and registry entry, and the regenerated material and
king-height projections together. Retain the immutable SQLite artifact and
result record so the build can still be reproduced or compared.
