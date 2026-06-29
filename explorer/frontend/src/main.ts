import { Chessground } from "chessground";
import { Api } from "chessground/api";
import { Key } from "chessground/types";

import {
  positionMoves, positionGames, meta, usernames, Filters, START_FEN, MoveRow,
} from "./db";
import { renderMoves, renderMoveList, renderGames, Node } from "./explorer";
import { setupCombobox, ComboboxController } from "./combobox";

import "chessground/assets/chessground.base.css";
import "chessground/assets/chessground.brown.css";
import "chessground/assets/chessground.cburnett.css";
import "./styles.css";

// The start position's id, fetched from meta.root_id at startup (the DB has no fen->id index, so
// navigation is keyed by integer id; the root is the only node without a parent move to supply one).
let rootId = 0;
const rootNode = (): Node => ({ id: rootId, fen: START_FEN, san: null });

let path: Node[] = [rootNode()];
let cursor = 0;
let orientation: "white" | "black" = "white";
let cg: Api;
let currentMoves: MoveRow[] = [];

// Rating filter: show games whose mean rating is >= ratingMin. The floor means "any".
const RATING_MIN = 1000;
const RATING_MAX = 3000;
const RATING_STEP = 50;
let ratingMin = RATING_MIN;

// Min-games filter: hide continuations played in fewer than `minGames` games. This is a live query
// param (nothing is pruned from the DB by frequency), so dragging it just changes the threshold.
const MIN_GAMES_MIN = 1;
const MIN_GAMES_MAX = 10;
let minGames = 5;

// Username filter: empty = no filter. White/Black match the corresponding seat (both = a pairing).
let whiteFilter = "";
let blackFilter = "";
let whiteCombo: ComboboxController;
let blackCombo: ComboboxController;

// Clicking a player's name in the games panel commits it to that seat's combobox (which filters).
function pickPlayer(name: string, side: "white" | "black"): void {
  (side === "white" ? whiteCombo : blackCombo).set(name);
}

function currentFilters(): Filters {
  const white = whiteFilter.trim() || undefined;
  const black = blackFilter.trim() || undefined;
  // The min-games slider is the single source of truth in every case (including username filters):
  // to see a specific player's one-off lines, drag the slider down to 1.
  return { white, black, minGames };
}

const $ = (id: string) => document.getElementById(id)!;

function turnColor(fen: string): "white" | "black" {
  return fen.split(" ")[1] === "w" ? "white" : "black";
}

// Legal-ish destinations for dragging: only normal moves present in the data.
function dests(moves: MoveRow[]): Map<Key, Key[]> {
  const map = new Map<Key, Key[]>();
  for (const m of moves) {
    if (!m.from_sq) continue; // drops aren't draggable (no pocket)
    const list = map.get(m.from_sq as Key) ?? [];
    list.push(m.to_sq as Key);
    map.set(m.from_sq as Key, list);
  }
  return map;
}

function node(): Node {
  return path[cursor];
}

async function render(): Promise<void> {
  const n = node();
  const color = turnColor(n.fen);
  const filters = currentFilters();
  currentMoves = await positionMoves(n.id, ratingMin, filters);

  cg.set({
    fen: n.fen.split(" ")[0],
    orientation,
    turnColor: color,
    lastMove: n.lastMove as Key[] | undefined,
    movable: {
      free: false,
      color,
      dests: dests(currentMoves),
    },
  });

  renderMoves($("explorer"), currentMoves, navigateTo, minGames);
  renderMoveList($("movelist"), path, cursor, jumpTo);
  renderGames($("games"), await positionGames(n.id, ratingMin, filters), pickPlayer);
}

function navigateTo(m: MoveRow): void {
  // Truncate any forward history, then descend into the chosen move.
  path = path.slice(0, cursor + 1);
  const last = m.from_sq ? [m.from_sq, m.to_sq] : [m.to_sq];
  path.push({ id: m.child_id, fen: m.child_fen, san: m.san, lastMove: last });
  cursor = path.length - 1;
  render();
}

// Dragging a piece: resolve to a data move (queen-preferred for promotions).
function onBoardMove(orig: Key, dest: Key): void {
  const candidates = currentMoves.filter(
    (m) => m.from_sq === orig && m.to_sq === dest
  );
  if (!candidates.length) return;
  const queen = candidates.find((m) => m.move_id.endsWith("q"));
  navigateTo(queen ?? candidates[0]);
}

function jumpTo(index: number): void {
  cursor = index;
  render();
}

function back(): void {
  if (cursor > 0) {
    cursor--;
    render();
  }
}
function forward(): void {
  if (cursor < path.length - 1) {
    cursor++;
    render();
  }
}
function reset(): void {
  // Clear the line entirely (not just jump to its start) so the move breadcrumb empties out.
  path = [rootNode()];
  cursor = 0;
  render();
}
function flip(): void {
  orientation = orientation === "white" ? "black" : "white";
  render();
}

// Wire the minimum-rating slider and its live readout. Also fetch meta once so renderMoves's
// empty-state message (max_ply / min_games) has data to show.
async function setupRatingFilter(): Promise<void> {
  const m = await meta();
  rootId = Number(m.root_id);
  path = [rootNode()]; // now that rootId is known, give the start node its real position id
  const slider = $("rating-min") as HTMLInputElement;
  const readout = $("rating-readout");
  slider.min = String(RATING_MIN);
  slider.max = String(RATING_MAX);
  slider.step = String(RATING_STEP);
  slider.value = String(ratingMin);
  const updateReadout = () => {
    readout.textContent = `Mean rating ≥ ${ratingMin}`;
  };
  updateReadout();
  // `input` fires on every step while dragging; update the readout live but debounce the query.
  let timer: number | undefined;
  slider.addEventListener("input", () => {
    ratingMin = Number(slider.value);
    updateReadout();
    clearTimeout(timer);
    timer = window.setTimeout(render, 150);
  });
}

// Wire the min-games slider and its live readout (mirrors setupRatingFilter).
function setupMinGamesFilter(): void {
  const slider = $("min-games") as HTMLInputElement;
  const readout = $("min-games-readout");
  slider.min = String(MIN_GAMES_MIN);
  slider.max = String(MIN_GAMES_MAX);
  slider.value = String(minGames);
  const updateReadout = () => {
    readout.textContent = `Min games ${minGames}`;
  };
  updateReadout();
  let timer: number | undefined;
  slider.addEventListener("input", () => {
    minGames = Number(slider.value);
    updateReadout();
    clearTimeout(timer);
    timer = window.setTimeout(render, 150);
  });
}

// Build the White/Black typeahead comboboxes from the username list (fetched once).
async function setupUsernameFilter(): Promise<void> {
  const options = await usernames();
  whiteCombo = setupCombobox($("white-combobox"), options, (v) => {
    whiteFilter = v;
    render();
  });
  blackCombo = setupCombobox($("black-combobox"), options, (v) => {
    blackFilter = v;
    render();
  });
}

async function main(): Promise<void> {
  cg = Chessground($("board"), {
    fen: START_FEN.split(" ")[0],
    orientation: "white",
    highlight: { lastMove: true },
    animation: { enabled: true, duration: 150 },
    movable: { free: false, showDests: true, events: { after: onBoardMove } },
    draggable: { showGhost: true },
  });

  $("back").addEventListener("click", back);
  $("forward").addEventListener("click", forward);
  $("reset").addEventListener("click", reset);
  $("flip").addEventListener("click", flip);
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") back();
    else if (e.key === "ArrowRight") forward();
  });

  try {
    await setupRatingFilter();
    setupMinGamesFilter();
    await setupUsernameFilter();
    await render();
  } catch (err) {
    $("loading").textContent =
      "Can't reach the explorer server — start it with `bughouse-explorer-serve`.";
    console.error(err);
    return;
  }
  $("loading").style.display = "none";
}

main();
