# Average King Height: full local result (2026-08-06)

## Outcome

Average King Height is implemented end to end in the authorized
`FULL_LOCAL_BUILD_AND_UI` scope. One checksum-verified immutable crawler
snapshot produced a versioned Player Insights SQLite artifact, deterministic
browser projection, and a feature-owned third insight in `bughouse-chess`.

No live crawler database was opened for mutation, and nothing was committed,
pushed, uploaded, previewed, or deployed.

The exact semantic contract is in
[`PLAYER_KING_HEIGHT_INSIGHT_SPEC_2026-08-06.md`](PLAYER_KING_HEIGHT_INSIGHT_SPEC_2026-08-06.md).
In short, each successfully replayed source game contributes one maximum king
height per tracked player: White uses the greatest rank reached, Black uses the
greatest `9 - rank`, and a normalized account occupying both seats contributes
once at its greater seat height. Heights are integers 1 through 8.

## Source and build

The build read this source immutably:

- snapshot: `snapshots/full-tree-input-20260804/restored-crawler-post-qualification-20260802.db`
- bytes: `15,146,962,944`
- SHA-256: `04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`
- SQLite `quick_check`: `ok`
- tracked-player cohort: `1,013`
- raw source games: `8,195,984`

Before the full pass, a deterministic modulus-71 representative pass accepted
`91,911` games and `4,573,999` plies in `9.901` seconds at approximately
`9,283` games/second with `27,705,344` bytes peak RSS. It observed 151
score-8 player-seat occurrences, which was sufficient to exercise sparse
evidence storage before the full scan.

The full shared material-and-height replay wrote:

- artifact: `artifacts/insights/full-post-qualification-20260802-king-height-v1/player-insights.db`
- artifact bytes: `1,769,472`
- artifact SHA-256: `f4027fda026469de08433ca92ba49c706e092c34f6d0c90c39b62d66cf0152e9`
- build result: `artifacts/insights/full-post-qualification-20260802-king-height-v1/player-insights-build-result.json`
- build-result bytes: `1,229`
- build-result SHA-256: `87d80409423adc60670c8b7947e67ab10c6fb18cc7691835995391adcbc77bca`
- dataset version: `30f02b1e7ef82f5c372f393c405309239c1499af`
- schema version: `2`
- adapter policy: `opening-adapter-v2-short-non-checkmate`
- material analyzer: `player-material-v1`
- king-height analyzer: `player-king-height-v1`
- elapsed: `577.735` seconds
- throughput: approximately `11,279` accepted games/second
- peak RSS: `59,342,848` bytes

The source pass reconciled as follows:

| Measure | Count |
| --- | ---: |
| Accepted games | 6,516,478 |
| Fully analyzed games | 6,516,457 |
| Replay-excluded games | 21 |
| Accepted plies | 324,522,210 |
| Fully analyzed plies | 324,520,761 |
| Skipped: empty TCN | 1,063,593 |
| Skipped: short non-checkmate | 615,913 |

All 21 replay exclusions were classified as `undefined_tcn_fragment`. Because
the two insights share the same complete-replay boundary, they contributed to
neither material nor king-height aggregates.

## Derived schema and validation

Schema version 2 adds:

- `player_king_height(player_id, height, games)`, with exactly eight rows for
  every tracked player;
- `king_height_eight_games(player_id, game_uuid, content_hash, game_url,
  end_time, player_color)`, retaining local evidence and public-link fields;
  and
- `player_king_height_scores`, an exact weighted-sum and nullable-average view.

The artifact passed these checks:

- SQLite `quick_check`: `ok`
- foreign-key violations: none
- tracked players: `1,013`
- king-height bucket rows: `8,104`
- attributed player-games: `8,435,811`
- negative counts: none
- bucket-sum versus analyzed-game mismatches: none
- zero-game cohort members: `4`, each with eight zero buckets and a null
  average
- score-8 evidence rows: `7,170`, across `650` players
- score-8 evidence versus bucket-8 mismatches: none
- invalid public URLs: none

The same pass preserved the original material result: player game counts,
piece counts, and anomaly rows were all exactly identical under bidirectional
SQLite `EXCEPT` checks against the first full material artifact.

## Corpus result

Across all attributed player-games, the distribution is:

| Height | Games | Probability |
| ---: | ---: | ---: |
| 1 | 4,926,867 | 58.4042% |
| 2 | 2,267,196 | 26.8759% |
| 3 | 762,763 | 9.0420% |
| 4 | 311,426 | 3.6917% |
| 5 | 124,480 | 1.4756% |
| 6 | 22,987 | 0.2725% |
| 7 | 12,922 | 0.1532% |
| 8 | 7,170 | 0.0850% |

The corpus-weighted average is `1.648139`.

The initial expectation that each player would have at most a few score-8
games does not hold for the most prolific accounts. `nochewycandy` has the
largest observed count, 128 touchdowns in 99,031 analyzed games (0.1293%), and
`outrunyou` has 126. The event is still very rare as a probability, but a long
lifetime produces enough examples that the UI must bound the expanded panel
instead of rendering an assumed handful inline.

## Browser projections

The new deterministic projection is:

- path: `bughouse-chess/app/data/player-king-height-insights.json`
- bytes: `791,817`
- gzip bytes: `141,656`
- SHA-256: `724f2dd2d464664915342768d6b985151fb9996cb6eaf22046c6cc2b1abf309c`
- players: `1,013`
- public score-8 links: `7,170`

A second export to a temporary path was byte-identical. The projection exports
the eight counts and only public Chess.com URL, end time, and player color for
touchdown games; internal UUIDs, content hashes, TCN, and anomaly evidence stay
local.

The material projection was regenerated from the shared artifact without
changing its counts:

- bytes: `194,309`
- gzip bytes: `53,916`
- SHA-256: `d7121d10f0004ef16bd80c6cc8c1552c63c621d4d5338780380f18f6970183e3`

## User interface

`/player-insights` now has a third, separate **Average King Height** chip. Its
projection is loaded only when that insight is selected, keeping the larger
791 KB JSON out of the initial material view.

Each player card shows:

- the active-sort rank, analyzed games, and nullable weighted average;
- an accessible eight-bucket probability chart on a shared 0–100% scale, from
  the player's own back rank to the opposite back rank; and
- an expandable, scroll-contained list of score-8 games with date and
  White/Black seat attribution, labelled as touchdowns; each link derives the
  game ID from the stored public source URL and opens Relay's Bughouse analysis
  board in a new tab.

The default metric is **Average King Height** ascending. The compact **Average
King Height** and **Touchdowns** controls each reverse direction when activated
again; selecting the other metric starts highest-first. Null averages remain
last in either average direction, touchdown ties use normalized username,
search and pagination work independently, and the chip controls wrap without
horizontal page overflow on a 390-pixel viewport. The minimum-games filter
defaults to 1000 and accepts only non-negative integers; blank means no minimum.
Desktop rows are approximately 20% shorter and reserve a fixed-height,
internally scrolling touchdown area so opening it produces no row-height shift.
Mobile cards retain their natural top-down expansion. Chart labels and
percentages use larger, higher-contrast text, and the height-8 end label is
**TOUCHDOWN**.

On small mobile displays, the general page description and the king-height
description are hidden, `Measured from each back rank` is removed at every
breakpoint, and the remaining header, insight navigation, search, sort, and
filter spacing is tightened without reducing the primary 44-pixel controls.

Production-build browser verification covered desktop and mobile layouts,
search, both directions for both sort metrics, the 128-link largest touchdown
list, and a 390-pixel overflow check. With the then-current 100-game filter, average
descending placed `aknod` first, touchdown descending placed `nochewycandy`
first with 128, and touchdown ascending placed zero-touchdown `02teen` first by
username tie-break. The local console contained only the expected unavailable
Vercel Web Analytics request and framework preload warnings; no application
error was observed.

The frontend refinement pass measured the desktop row at exactly 124 pixels
both before and after opening touchdowns. The largest list used a 52-pixel
client scrollport over 6,082 pixels of content. At 390 pixels, the page
`scrollWidth` equalled its 390-pixel viewport, and the same list used a
192-pixel mobile scrollport with natural card expansion. Fractional input
`100.5` left the then-current controlled minimum unchanged at `100`, and ranks were
recalculated inside the filtered cohort so its first visible player is `#1`.
After the mobile-density pass, the first player row began at 466.5 CSS pixels
in the 390-by-844 viewport, and the document width remained exactly 390 pixels.

A final link follow-up raised the default minimum to 1000 and routed touchdown
games through `https://bughouse.aronteh.com/?gameId=<GAME_ID>` in a new tab. A
production-build browser check confirmed the rendered `1000` value and a real
touchdown link's Relay URL, `_blank` target, and `noreferrer noopener` relation.
The opening explorer's support-one source-game rows use the same shared URL
builder and new-tab contract; four component scenarios cover its lifted child,
sole continuation, filtered refill, and packed-terminal paths.

## Automated verification

`bughouse-opening-explorer`:

```text
.venv/bin/python -m pytest -q
197 passed in 1.82s
```

`bughouse-chess`, using the repository's Node 22 runtime:

```text
Vitest: 57 files, 493 tests passed
npm run lint: passed (TypeScript and ESLint)
next build: passed; /player-insights generated statically
```

The backend tests cover directional rank normalization, a king returning
home, same-account two-seat attribution, zero denominators, score-8 evidence,
atomic malformed replay, schema/version provenance, export invariants,
determinism, and CLI behavior. Frontend tests cover arithmetic, null-last
sorting, search/pagination, charts, expansion, lazy data loading, the host
integration, and route isolation.

## Refresh procedure

Build a fresh immutable artifact from a named, checksum-verified snapshot:

```bash
.venv/bin/python scripts/build_player_insights.py \
  snapshots/<name>/restored-crawler.db \
  artifacts/insights/<new-name>/player-insights.db \
  --snapshot-sha256 <source-sha256>
```

After validating and recording the new artifact checksum, refresh both checked
frontend projections explicitly:

```bash
.venv/bin/python scripts/export_player_insights.py \
  artifacts/insights/<new-name>/player-insights.db \
  ../bughouse/bughouse-chess/app/data/player-material-insights.json \
  --database-sha256 <player-insights-db-sha256> \
  --replace

.venv/bin/python scripts/export_king_height_insights.py \
  artifacts/insights/<new-name>/player-insights.db \
  ../bughouse/bughouse-chess/app/data/player-king-height-insights.json \
  --database-sha256 <player-insights-db-sha256> \
  --replace
```

Then repeat SQLite reconciliation, deterministic second exports, both
repositories' automated checks, and production-build browser verification.
Publishing remains a separate explicit approval gate.

## Rollback

The change is additive. A frontend rollback can remove the Average King Height
chip, renderer, and checked king-height projection while leaving the original
material views intact. The prior material artifact and projection remain
independently reproducible. The source snapshot and live `data/crawler.db` were
not changed.
