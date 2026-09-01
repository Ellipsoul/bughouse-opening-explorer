# Material Game Highs: semantic specification (2026-08-12)

## Question and user value

**Material Game Highs** asks which three analyzed games contain each
permanently tracked player's greatest positive net material and greatest
negative net material. It applies the first two material insights' signed net
calculation at individual-game grain and highlights memorable single-game
extremes without implying that one exceptional game describes the player's
typical play.

The stable insight ID is `material-game-highs`.

## Semantic contract

| Property | Definition |
| --- | --- |
| Grain | One leaderboard row per permanently tracked player. Each row has up to three qualifying game references for each combination of piece-value preset (`bughouse` or `standard`) and direction (`won` or `lost`). |
| Cohort | Every snapshot player whose `tracking_started_at IS NOT NULL`, matched by normalized username. Future permanently tracked players appear automatically, including players with no qualifying games. |
| Eligible games | Games accepted by `opening-adapter-v2-short-non-checkmate`: supported public/callback source, Bughouse rules, standard initial setup, valid participant shape and decodable TCN, within the safety limit, and not a short non-checkmate. |
| Analyzed games | Eligible games whose complete TCN replay succeeds. This is the filterable game-count field shown for each player and matches the existing material denominator. A same-account player occupying both seats counts once. |
| Counted material | Per-game net is `material captured by the player - material captured by the opposing seat`, using the same signed calculation as Net Material and Net Material per Game. Ordinary captured pieces use their board type; en passant is a pawn; a captured promoted pawn counts as a pawn regardless of its promoted form; a dropped piece uses its full dropped type; drops are not captures; kings have no material value. |
| Attribution | For a tracked player in one seat, subtract the opposing seat's capture ledger from that player's capture ledger, piece by piece, then apply the selected preset. If one normalized account occupies both seats, combine both seats before calculating one game net, matching the existing lifetime material ledger and one-game denominator. Its two seat ledgers balance to zero, so such a game does not qualify for either signed extreme. Partner-board captures are not attributed to this one-board record. |
| Piece-value presets | Rank independently under Bughouse values (pawn 1.5, knight 3, bishop 3, rook 4, queen 7) and Standard values (pawn 1, knight 3, bishop 3, rook 5, queen 9). Values are represented exactly as integer half-points in extraction and SQLite. |
| Qualification | Under each preset, `won` keeps only strictly positive per-game nets and `lost` keeps only strictly negative per-game nets. The source record must also have a public Chess.com game URL. A player may therefore have zero, one, two, or three results in a direction. Net-zero games and unreferenceable records are not arbitrary filler evidence. |
| Top-three order | `won` orders the largest signed nets first; `lost` orders the most negative signed nets first. Ties use newer non-null `end_time`, then stable game UUID. Null end times sort after known times. This exact order chooses the retained three and makes repeated builds deterministic. |
| Player order | The active direction ranks players by the signed net of their first qualifying game under the active preset: descending for `won`, ascending for `lost`. Players without a qualifying game remain after ranked players. Remaining ties use normalized username ascending. Search, minimum analyzed games, and pagination do not recompute rank. |
| Final position | Store the completed one-board four-field FEN produced by the same successful replay. Display from the tracked seat's perspective; a same-account both-seat record uses White orientation. |
| Malformed replay | Atomic exclusion. An `undefined` fragment, invalid token, missing/wrong-side source piece, occupied drop, self-capture, or other structural replay failure contributes no lifetime aggregate and no game-high candidate. Eligible and replay-excluded counts remain auditable through the shared material tables. |
| Denominator | No ratio is calculated for this insight. `analyzed_games` is retained only as player context and a UI filter. Zero-game players remain present with empty result arrays. |

## Shared-pass and bounded-state decision

The completed lifetime material tables cannot recover per-game extremes because
they intentionally discard game boundaries. A separate SQL query over that
artifact would therefore be insufficient.

The efficient implementation extends the existing material replay pass. Once a
game has replayed successfully, its already-computed game-local capture
counters are subtracted into signed per-player nets and feed four bounded
top-three sets per tracked player:

- Bughouse positive net;
- Bughouse negative net;
- Standard positive net; and
- Standard negative net.

Each set retains at most three game candidates. No player game history is
stored or sorted, and no second full snapshot scan or replay pass is needed.
The additional state is bounded by `tracked players x 2 presets x 2 directions
x 3 games`.

## Stored fields

The versioned SQLite artifact stores a feature-owned
`player_material_game_highs` table with:

- `player_id`;
- `preset` (`bughouse` or `standard`);
- `direction` (`won` or `lost`);
- one-based `rank` from 1 through 3;
- exact signed `net_material_x2`;
- internal `game_uuid` and `content_hash` for provenance;
- public `game_url`;
- nullable `end_time`;
- `player_color` (`white`, `black`, or `both`); and
- final four-field `position_fen`.

The primary key is `(player_id, preset, direction, rank)`. Additional
uniqueness prevents one game appearing twice for the same player, preset, and
direction. SQLite checks enforce the fixed domains, direction/sign agreement,
non-zero scores, and valid rank range. Build provenance records a distinct game-high analyzer version and
increments the output schema version.

## Browser projection

The deterministic static projection exports only:

- dataset identity and relevant policy/analyzer versions;
- username, display name, and analyzed-game count;
- fixed preset and direction ordering; and
- for each retained public game: URL, end time, player colour, final FEN, and
  exact half-point score.

It does not export raw TCN, content hashes, internal UUIDs, anomaly evidence,
SQLite, lifetime piece ledgers, or discarded game candidates. Games without a
valid public Chess.com URL do not qualify for this reference-oriented insight;
the exporter validates every retained URL and contiguous rank sequence.

## UI shape

The insight is a feature-owned filterable leaderboard at
`/player-insights?insight=material-game-highs`.

- A two-way control toggles **Most won** and **Most lost**. The first view is
  Most won.
- The existing Bughouse/Standard preference selects the corresponding stored
  top-three set; the browser does not rescore discarded games.
- Player search, a non-negative minimum analyzed-games filter, and 25/50/100
  row pagination keep large leaderboards usable. The minimum defaults to zero
  so the permanent cohort is not silently hidden.
- Rank describes the full active player ordering before search, filtering, and
  pagination.
- Each desktop row has a compact player cell followed by three equal game-card
  columns. Each card contains the signed net score, final board, date, and a
  Relay analysis link derived from the stored Chess.com URL.
- On narrow screens, player identity remains above an internally horizontally
  scrollable three-card strip. Boards stay legible and the page itself remains
  viewport-width.
- Empty direction arrays render an explicit “No qualifying game” state rather
  than zero-score evidence.

Every final board is a static semantic grid using the same square palette and
Wikipedia piece artwork as Relay's analysis board. It has an accessible
position label and no move, drag, drop, annotation, or canvas behavior. Piece
images use the analysis board's existing 12 cacheable URLs and browser-native
lazy loading; the insight does not instantiate an interactive chessboard for
each game.

## Acceptance examples

1. White captures a pawn and loses no material: White gets net `+1.5` under
   Bughouse and `+1` under Standard; Black gets the corresponding negative net
   candidate. Both final positions are the same FEN, with opposite display
   orientations.
2. Four qualifying games have nets +7, +5, +3, and +1 Bughouse points for one player:
   only 7, 5, and 3 are stored. No full history or fourth reference remains.
3. A game where the player captures a queen but loses a rook has net +3 under
   Bughouse and +4 under Standard. Preset-specific values can therefore change
   the retained order; each preset keeps its own exact top three.
4. Two games tie on material: the newer known `end_time` ranks first; an equal
   or null-time tie is resolved by stable game UUID.
5. A tracked player has analyzed games but never finishes one with positive net
   material: their won array is empty, while their lost array may still contain
   up to three negative-net games.
6. A valid capture prefix followed by malformed TCN contributes no candidate in
   either direction or preset.
7. A same-account player occupies both seats: both seat ledgers combine to net
   zero, so the game appears in neither direction.
8. A future permanently tracked player appears with their analyzed-game count
   and empty arrays when no positive material game qualifies.
