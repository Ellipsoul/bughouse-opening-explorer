# Average King Height: semantic specification (2026-08-06)

## Question and user value

**Average King Height** asks how far a player's king advances from its own back
rank during a game. It is a playful, imperfect proxy for how much king exposure
a player tolerates. The distribution is the primary evidence; the average is a
compact sorting statistic, not a claim about intent or playing strength.

The stable insight ID is `average-king-height`.

## Semantic contract

| Property | Definition |
| --- | --- |
| Grain | One row per permanently tracked player, with one bucket contribution per analyzed source game. |
| Cohort | Every snapshot player whose `tracking_started_at IS NOT NULL`, matched by normalized username. The cohort size is never hard-coded. |
| Eligible games | Games accepted by `opening-adapter-v2-short-non-checkmate`: supported public/callback source, Bughouse rules, standard initial setup, valid participant shape and decodable TCN, within the safety limit, and not a short non-checkmate. |
| Denominator | `analyzed_games`: eligible games whose complete replay succeeds. A zero-game player remains present with eight zero buckets and a null average. |
| White height | The greatest numeric rank ever occupied by White's original king, including the starting rank. |
| Black height | The greatest value of `9 - numeric rank` ever occupied by Black's original king, including the starting rank. |
| Range | Integer 1 through 8. A king that never leaves its back rank scores 1; reaching the opponent's back rank scores 8. Returning toward home never reduces the game's maximum. |
| Attribution | Attribute White's height to the normalized White player and Black's height to the normalized Black player. If one normalized account occupies both seats, the source game contributes once at the greater of its two seat heights. |
| Malformed replay | Atomic exclusion. An `undefined` fragment, invalid token, missing/wrong-side source piece, occupied drop, self-capture, or other structural replay failure contributes no material, height bucket, or score-8 evidence. The eligible and replay-excluded counts remain auditable. |
| Average | `sum(height * games_at_height) / analyzed_games`; null when the denominator is zero. No rounding is stored. |
| Sort | The default is average height ascending. Average height and touchdown count are separate metric toggles; activating the current metric reverses its direction, while selecting the other metric starts descending. Null averages remain after analyzed players in either average direction. Touchdown ties use normalized username. |
| Score-8 evidence | One sparse derived row per tracked player and analyzed game whose attributed height is 8. Store player ID, internal game UUID/content hash, public Chess.com URL, end time, and attributed color. |

The score-8 list deliberately uses the highest seat value for a same-account
game, matching the one-player-game grain. Its color is `white`, `black`, or
`both` when both kings reach height 8.

## Stored and exported fields

The versioned SQLite artifact stores:

- common build provenance and denominators;
- `player_king_height(player_id, height, games)`, exactly eight rows per player;
- `king_height_eight_games(player_id, game_uuid, content_hash, game_url,
  end_time, player_color)`; and
- `player_king_height_scores`, an exact view exposing the weighted sum and
  nullable average.

The browser projection exports only:

- dataset version/checksum and relevant policy versions;
- username, display name, and analyzed-game denominator;
- eight integer bucket counts in height order 1 through 8; and
- public Chess.com URL, end time, and color for score-8 games.

It does not export TCN, internal game UUIDs/content hashes, anomaly evidence,
or SQLite. The public URLs are the narrow, user-requested exception to the
usual no-game-identifier publication default.

## UI shape

The insight uses a feature-owned searchable, paginated leaderboard rather than
the material table. Each row/card contains:

- player and active-sort rank;
- average height and analyzed-game count;
- an eight-bucket probability chart on a common 0–100% scale; and
- a compact, expandable list of every public score-8 game, called a
  **touchdown** in the user interface; each stored source URL is converted to
  the corresponding Relay Bughouse analysis URL and opens in a new tab.

The default order is average height ascending. Compact **Average King Height**
and **Touchdowns** sort controls each reverse when activated again. Every chart
has an accessible textual summary, zero-game players show an em dash rather
than `NaN`, and core controls wrap at narrow viewports. A non-negative integer
minimum-games filter defaults to 1000.
Desktop rows reserve a fixed-height scrolling touchdown area, while mobile
cards may expand naturally. On small mobile displays, the page-level and
insight-level explanatory paragraphs are hidden so controls and data arrive
earlier; both remain visible from the `sm` breakpoint upward.

## Acceptance examples

1. Neither king leaves its back rank: both players contribute to bucket 1.
2. White reaches rank 5: White contributes to bucket 5.
3. Black reaches rank 6: Black contributes to bucket `9 - 6 = 3`.
4. A king reaches height 5 and later returns home: the game remains in bucket 5.
5. A score-8 replay produces one sparse source-game record whose UI link opens
   that game in Relay's Bughouse analysis board.
6. A valid prefix reaches height 8 but a later token is malformed: the entire
   game contributes no bucket and no score-8 link.
7. A permanently tracked player with no analyzed games has eight zero buckets
   and a null average.

## Shared-pass decision

King height shares the material analyzer's source pass because the cohort,
adapter eligibility, complete-TCN replay, atomic failure boundary, and player
denominators are identical. The replay computes both kings' maxima in game-local
state and merges them only after success. This avoids a second multi-million-
game replay without coupling different semantics or failure policies.
