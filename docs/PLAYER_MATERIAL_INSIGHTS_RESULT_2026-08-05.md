# Player material insights: full extraction result (2026-08-05)

## Outcome

The first full player-material insight artifact is complete. It was built
locally from the same immutable, checksummed post-qualification crawler
snapshot used by the full opening tree. The build did not read
`data/crawler.db`.

The derived artifact is:

- `artifacts/insights/full-post-qualification-20260802/material-insights.db`
- 249,856 bytes
- SHA-256
  `df0697ced99719bd93cef7b3a337f00856a1bc064138cde14f8d2970bdd9ec0a`
- dataset version `2b0f44c2a04fe721accfda7e98e35f56741e7dce`

The machine-readable build record is
`artifacts/insights/full-post-qualification-20260802/material-insights-build-result.json`.
Both files are ignored build artifacts rather than Git-tracked source files.
The builder and tests are the durable means of reproducing them; this document
retains their build identity and validation evidence.

## Full-build measurements

| Measure | Result |
| --- | ---: |
| Permanently tracked players | 1,013 |
| Adapter-accepted games | 6,516,478 |
| Successfully analyzed games | 6,516,457 |
| Atomically replay-excluded games | 21 |
| Adapter-accepted plies | 324,522,210 |
| Successfully analyzed plies | 324,520,761 |
| Build time | 578.516 seconds |
| Throughput | 11,264 accepted games/second |
| Peak resident memory | 51,707,904 bytes |

The adapter also excluded 1,063,593 `empty_tcn` games and 615,913
`short_non_checkmate` games under the existing
`opening-adapter-v2-short-non-checkmate` policy. Those games are outside the
material insight's eligible-game set, just as they are outside the full
opening-tree corpus.

## Cohort and denominator

The cohort is selected from the input snapshot rather than hard-coded:

```sql
SELECT ... FROM players
WHERE tracking_started_at IS NOT NULL;
```

Consequently, a future snapshot containing additional permanently tracked
players will include them in its next insight database automatically. The
current snapshot contains 1,013 such players. Four have no adapter-accepted
games and are deliberately retained with zero counts.

For each player:

- `eligible_games` counts adapter-accepted games in which that player appears;
- `analyzed_games` counts those games whose complete TCN replay succeeded;
- `replay_excluded_games` counts eligible games excluded atomically due to a
  replay anomaly;
- `eligible_games = analyzed_games + replay_excluded_games`.

Per-game material averages use `analyzed_games`, because no partial capture
counts from an excluded game are retained.

## Capture semantics

The analyzer replays every accepted two-character TCN token in order and
records captures for both seats. Its tested rules are:

- an ordinary captured piece uses its board type;
- an en-passant capture counts as a pawn;
- a promoted piece remains a pawn for capture accounting, even after moving;
- a dropped piece uses its full dropped type;
- a drop itself is not a capture;
- kings are never material-counted;
- a game with an invalid token or structural replay failure contributes no
  capture counts at all.

TCN decoding preserves the canonical alphabet's first-occurrence behavior.
This matters because the alphabet contains `+` twice: the first occurrence is
the bishop-drop code. A regression test locks that behavior down.

## The `undefined` data-quality edge

The full pass confirmed the independently observed edge case. Exactly 21
adapter-accepted games contain a literal `undefined` fragment in their TCN.
Every one is recorded in `material_anomalies` with reason
`undefined_tcn_fragment`; no other replay-anomaly reason occurred in the full
build.

These games are excluded atomically. Even if a valid prefix contains captures,
none of those prefix captures are included. The affected player's eligible
count remains visible, and their replay-excluded count increases, so the
omission is auditable rather than silent.

## SQLite contract

The database is a standalone, read-only publication candidate with these
relations:

- `insight_builds`: snapshot identity, policy versions, and corpus totals;
- `players`: the permanently tracked cohort copied from the snapshot;
- `player_game_counts`: eligible, analyzed, and replay-excluded denominators;
- `player_material`: one row per player and piece type, with `pieces_won` and
  `pieces_lost` for pawn, knight, bishop, rook, and queen;
- `material_anomalies`: the exact source game and stable exclusion reason;
- `adapter_skips`: source games outside the accepted corpus, grouped by reason;
- `material_piece_values`: exact half-point integer values for the Bughouse and
  Standard presets;
- `player_material_scores`: a view deriving material won, lost, net, and
  per-analyzed-game averages for both presets.

The stored preset values are:

| Preset | Pawn | Knight | Bishop | Rook | Queen |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bughouse | 1.5 | 3 | 3 | 4 | 7 |
| Standard | 1 | 3 | 3 | 5 | 9 |

Per-piece net and average figures remain exact derivations:

```sql
SELECT
    p.username,
    m.piece_type,
    m.pieces_won,
    m.pieces_lost,
    m.pieces_won - m.pieces_lost AS net_pieces,
    1.0 * m.pieces_won / NULLIF(g.analyzed_games, 0)
        AS average_pieces_won_per_game,
    1.0 * m.pieces_lost / NULLIF(g.analyzed_games, 0)
        AS average_pieces_lost_per_game
FROM players AS p
JOIN player_game_counts AS g USING (player_id)
JOIN player_material AS m USING (player_id);
```

The top material winners under the Bughouse preset can be queried without
replaying any games:

```sql
SELECT username, analyzed_games, net_material
FROM player_material_scores
WHERE preset = 'bughouse'
ORDER BY net_material DESC, username
LIMIT 100;
```

## Build and refresh procedure

Always select a named immutable snapshot, validate it according to the monthly
snapshot workflow, and record its SHA-256. Never point the builder at the live
crawler database. Then create a new output path:

```sh
.venv/bin/python scripts/build_player_insights.py \
  snapshots/full-tree-input-20260804/restored-crawler-post-qualification-20260802.db \
  artifacts/insights/full-post-qualification-20260802/material-insights.db \
  --snapshot-sha256 04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac \
  --result artifacts/insights/full-post-qualification-20260802/material-insights-build-result.json
```

The command verifies the source checksum before scanning and refuses to
overwrite either an existing insight database or an existing result record.
Use a new versioned directory for every future snapshot. Only after checksum,
SQLite integrity, row-shape, and metric validation should a small static export
or the derived database become a website release input.

## Static website projection

The checked database now has a deterministic browser projection generated by
`scripts/export_player_insights.py`. For this dataset, it produced:

- frontend path:
  `bughouse-chess/app/data/player-material-insights.json`;
- 194,309 bytes uncompressed;
- approximately 53,917 bytes with gzip;
- SHA-256
  `a378fd7171d44640a763c272c763f621260e1eb0d97e051c9d5f7a6ca27c6af4`;
- 1,013 player records;
- dataset version `2b0f44c2a04fe721accfda7e98e35f56741e7dce`.

The export retains one metadata record, the fixed five-piece ordering, both
piece-value presets, and each player's denominators plus exact won/lost counts.
It is imported at Next.js build time, so `/player-insights` makes no runtime
insight API request.

After every future checked database build, update the frontend projection with:

```sh
.venv/bin/python scripts/export_player_insights.py \
  artifacts/insights/<snapshot>/material-insights.db \
  ../bughouse/bughouse-chess/app/data/player-material-insights.json \
  --database-sha256 <material-insights-db-sha256> \
  --replace
```

The exporter verifies the database checksum, rejects incomplete player/piece
rows, emits deterministic compact JSON, and atomically replaces the canonical
frontend file only when `--replace` is explicit.

## Validation evidence

The completed artifact passed:

- `PRAGMA quick_check` (`ok`);
- `PRAGMA foreign_key_check` (zero violations);
- 1,013 player rows and exactly five material rows per player;
- 2,026 score-view rows, one per player and preset;
- zero negative piece counts;
- zero game-count invariant violations;
- zero material-score arithmetic violations;
- output checksum agreement with the build-result JSON.

The extraction repository test suite passes with its full test set. Focused
coverage includes ordinary captures, en passant, promoted and dropped pieces,
the duplicated TCN `+` symbol, future cohort expansion, atomic invalid-game
exclusion, snapshot checksum verification, deterministic rebuilds, score
views, deterministic static export, row-shape rejection, checksum verification,
and atomic frontend replacement.

The static projection is consumed by the separate `/player-insights` route in
`bughouse-chess`. No Vercel resource, Production deployment, commit, or push was
performed as part of this local implementation.
