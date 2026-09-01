# Piece Drop Heat Maps: semantic specification (2026-08-09)

## Question and user value

**Piece Drop Heat Maps** asks where each permanently tracked player places
pawns, knights, bishops, rooks, and queens. The five distributions expose
recurring attacking, defensive, and coordination patterns without claiming
that a common square is objectively good or bad.

The stable insight ID is `piece-drop-heatmaps`.

## Semantic contract

| Property | Definition |
| --- | --- |
| Grain | One stored/exported row per permanently tracked player, containing White and Black channels for five piece-type-by-square distributions. The browser derives one cohort aggregate from those rows. |
| Cohort | Every snapshot player whose `tracking_started_at IS NOT NULL`, matched by normalized username. The cohort size is never hard-coded. |
| Eligible games | Games accepted by `opening-adapter-v2-short-non-checkmate`: supported public/callback source, Bughouse rules, standard initial setup, valid participant shape and decodable TCN, within the safety limit, and not a short non-checkmate. |
| Game denominator | Combined uses common `analyzed_games`: eligible games whose complete replay succeeds, deduplicated when the same account occupies both seats. White-only and Black-only use colour-specific analyzed appearances. Each denominator includes successfully replayed games in which the player made no drop. A zero-game player remains present with zero counts. |
| Aggregate denominator | The initial **All tracked players** row displays the dataset-level `analyzed_games` count in Combined, White-only, and Black-only modes. It never sums player game counts because one game can represent multiple tracked players. |
| Counted event | A TCN move decoded as a drop of pawn, knight, bishop, rook, or queen onto an empty board square. Ordinary moves and captures are not drops. The event is counted only after the entire game passes replay validation. |
| Stored coordinates | White and Black channels retain exact source squares. White-only and Black-only both use the ordinary White-facing board orientation, with rank 8 at the top and rank 1 at the bottom. Black-only is not normalized or rotated. |
| Combined normalization | White destinations retain their source square. Black destinations preserve the file and map the rank to `9 - rank`. Thus both players' own back ranks appear at rank 1 while kingside and queenside files keep their chess meaning. |
| Attribution | Attribute each drop to the normalized player occupying the moving seat. If one normalized account occupies both seats, the game counts once in `analyzed_games`, while valid drops from both seats are combined after applying each seat's colour normalization. |
| Aggregate attribution | Sum `players[].dropsByColor` over every permanently tracked player, independently by colour, piece type, and square. Do not include drops by untracked participants. Combined then rank-reflects the summed Black channel before adding White. |
| Percentage denominator | For one player or the derived cohort aggregate, active colour mode, and piece type, `drops_on_square / sum(drops_on_all_64_squares_for_that_piece_and_mode)`. A piece type with no drops has 0% on every square. Percentages are derived at presentation time and are not stored or exported. |
| Malformed replay | Atomic exclusion. An `undefined` fragment, invalid token, missing/wrong-side source piece, occupied drop, self-capture, or other structural replay failure contributes no material, king height, drop counts, or evidence. Eligible and replay-excluded counts remain auditable. |
| Selection order | Search suggestions match username and display name. Selected players appear in the order they were added, enabling deliberate side-by-side comparison without implying a ranking. |
| Heat scale | Each board is normalized independently: the player's most-used square for that piece and active colour mode receives maximum intensity, other occupied squares scale by their proportion relative to that maximum, and zero-count squares retain only the checkerboard tone. Exact count and percentage remain available in the square label. This keeps sparse and diffuse distributions legible; colour intensity is not a cross-piece volume comparison. |

Rank-only normalization is intentional. Keeping raw squares would vertically
blur the same attacking idea across White and Black games. Rotating Black by
180 degrees would also exchange the chess meanings of the `a` and `h` files,
turning queenside patterns into kingside patterns. Preserving the file while
normalizing direction avoids both distortions.

## Stored and exported fields

The versioned SQLite artifact stores:

- common build provenance and player game denominators;
- a distinct `drop_heatmap_analyzer_version` in the build record;
- `player_drop_color_game_counts(player_id, player_color, eligible_games,
  analyzed_games, replay_excluded_games)`, exactly two rows per player;
- `player_drop_squares(player_id, player_color, piece_type, square, drops)`,
  with one exact non-negative integer row for every player, colour, piece type,
  and square;
- a colour-specific operator view exposing exact source squares, colour
  denominators, piece totals, and ratios; and
- a combined operator view reflecting only Black ranks and using the common
  deduplicated analyzed-game denominator.

The browser projection exports only:

- dataset version/checksum and relevant policy versions;
- fixed piece order `pawn`, `knight`, `bishop`, `rook`, `queen`;
- fixed square order `a1` through `h1`, then `a2` through `h8`;
- username, display name, and analyzed-game denominator; and
- White and Black analyzed-game denominators; and
- two colour channels, each containing five arrays of 64 exact integer counts
  in the fixed square order.

It does not export TCN, game URLs or IDs, internal hashes, replay anomalies,
SQLite, precomputed percentages, heat colours, or per-game evidence.

The browser derives **All tracked players** directly from this unchanged static
projection by summing every exported player colour channel. The derivation adds
no stored field, schema version, extraction pass, or projection bytes.

## UI shape

The insight has two related views. With no explicit player selection, it shows
one feature-owned **All tracked players** row representing the permanent
cohort. The row contains:

- display name and the number of analyzed games represented;
- five compact, consistently oriented checkerboards in piece order;
- a piece icon/name and total drop count above each board;
- a proportion-based overlay whose strongest square is immediately visible;
- exact count and percentage in sufficiently large squares; and
- the same exact values in an accessible square name and native hover label at
  every viewport.

The five-board strip stays in one horizontal row. Each board has a 252-pixel
minimum width—75% larger than the first 144-pixel implementation—and all five
columns share additional available width on larger screens. Narrow screens keep
the cohort identity above a horizontally scrollable board strip rather than
shrinking squares below legibility. There is no player browse list or
pagination.

A searchable multi-select replaces the cohort aggregate with a comparison view
as soon as the first player is selected. It uses removable player chips and a
keyboard-accessible suggestion list, without an arbitrary selection limit. The
comparison transposes the board layout:
the five piece types form side-by-side columns and the selected players stack
top-to-bottom within each piece column. This makes like-for-like boards easy to
scan. The columns scroll horizontally on narrow screens, while selected chips
wrap above them.

A three-way segmented control selects **Combined**, **White**, or **Black**.
Combined is the default and rank-normalizes Black. White and Black retain their
exact source square labels and both are drawn from White's perspective, with
rank 8 at the top. Changing mode updates counts, percentages, and game
denominators in either the aggregate or comparison view. The orientation
explanation beside the mode control is omitted on mobile to preserve space. The
projection is imported only by the lazy-loaded heat-map insight so it does not
enlarge the initial material view.

The checkerboard and heat overlay use a local CSS grid. No chess interaction,
move legality, canvas, or general charting dependency is needed for this static
64-cell visualization.

The host page exposes the stable share URL
`/player-insights?insight=piece-drop-heatmaps`. Selecting another Player
Insights chip replaces only the `insight` query value, retaining unrelated
parameters and fragments. Unknown values fall back to Net Material; query
selection does not introduce a runtime data API or dynamic server render.

## Acceptance examples

1. White drops a knight on `e6`: White-only `knight/e6` increases by one and
   Combined `knight/e6` increases by one.
2. Black drops a knight on `e3`: Black-only raw `knight/e3` increases by one;
   Combined `knight/e6` increases by one because the file is preserved and
   rank 3 maps to rank 6.
3. Black drops a rook on `a2`: Black-only retains `a2`; Combined contributes to
   normalized `a7`, not `h7`.
4. A tracked account occupying both seats drops a pawn once from each seat:
   Combined `analyzed_games` increases once, both colour-specific appearances
   increase once, and both normalized squares increase.
5. A player with three queen drops on `d5` and one on `e6` has square
   percentages 75% and 25%; all other queen squares are 0%.
6. A successfully replayed game with no drops increases `analyzed_games` but
   leaves every drop count unchanged.
7. A valid prefix contains drops but a later token is malformed: the entire
   game contributes no drop counts.
8. A future permanently tracked player appears automatically with zero counts
   when the snapshot contains no analyzed games for that player.

## Shared-pass decision

Drop heat maps share the material and King Height replay pass because the
cohort, adapter eligibility, complete-TCN replay, atomic failure boundary, and
player game denominators are identical. The replay records each side's drops
in game-local counters and merges them only after complete success. This adds
bounded state of `tracked players x five piece types x 64 squares` and avoids a
second scan of more than six million games without weakening any insight's
semantics.
