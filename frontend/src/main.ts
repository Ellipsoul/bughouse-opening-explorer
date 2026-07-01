import { Chessground } from "chessground";
import { Api } from "chessground/api";
import { Key } from "chessground/types";

import {
  positionMoves, positionGames, meta, usernames, lookupPosition,
  Filters, START_FEN, MoveRow,
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
const rootNode = (): Node => ({ id: rootId, fen: START_FEN, san: null, ply: 0 });

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

// Jump straight to a pasted FEN: look up its position id and, on a hit, start a fresh line there
// (same reset-then-render shape as reset()). A FEN not in the dataset leaves the board untouched.
// Submitted on Enter or blur. lastFen holds the last *successfully* jumped-to FEN, so the blur that
// follows an Enter submit is a no-op, but a failed lookup can be retried with the same text.
let lastFen = "";
async function goToFen(): Promise<void> {
  const input = $("fen-input") as HTMLInputElement;
  const error = $("fen-error");
  const raw = input.value.trim();
  if (!raw || raw === lastFen) return;
  let hit: { id: number; fen: string } | null;
  try {
    hit = await lookupPosition(raw);
  } catch (err) {
    console.error(err);
    // A fetch TypeError means the server is unreachable; anything else is an error status it returned.
    error.textContent =
      err instanceof TypeError
        ? "Couldn't reach the server — is it running (and restarted)?"
        : "Lookup failed (server error).";
    error.hidden = false;
    return;
  }
  if (!hit) {
    error.textContent = "Position not in the dataset.";
    error.hidden = false;
    return;
  }
  error.hidden = true;
  lastFen = raw;
  input.blur(); // drop focus so the text caret stops blinking in the field
  // Seed move numbering from the FEN: side-to-move (from the resolved position) + the fullmove
  // counter in the pasted input give the position's real ply, even though its moves are unknown.
  // A FEN without a fullmove field falls back to move 1 (nothing better is recoverable).
  const side = hit.fen.split(" ")[1];
  const fullmove = Number.parseInt(raw.split(/\s+/)[5] ?? "1", 10) || 1;
  const ply = (fullmove - 1) * 2 + (side === "b" ? 1 : 0);
  path = [{ id: hit.id, fen: hit.fen, san: null, ply }];
  cursor = 0;
  render();
}

// True if the event target is an editable field, so letter shortcuts don't fire while typing.
function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
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
  const fenEl = $("fen-input") as HTMLInputElement;
  // Keep the FEN on a single line by shrinking the font until it fits the field's width.
  const MAX_FONT = 12;
  const MIN_FONT = 6;
  const fitFont = () => {
    fenEl.style.fontSize = `${MAX_FONT}px`;
    let size = MAX_FONT;
    while (size > MIN_FONT && fenEl.scrollWidth > fenEl.clientWidth) {
      size -= 0.5;
      fenEl.style.fontSize = `${size}px`;
    }
  };
  fenEl.addEventListener("input", () => {
    // Strip the crazyhouse/bughouse pocket ([] and its contents) from the field automatically.
    const cleaned = fenEl.value.replace(/\[.*?\]/g, "");
    if (cleaned !== fenEl.value) fenEl.value = cleaned;
    fitFont();
  });
  fenEl.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter") {
      e.preventDefault();
      goToFen();
    }
  });
  fenEl.addEventListener("blur", goToFen);
  window.addEventListener("resize", fitFont);
  fitFont(); // size correctly on load
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") back();
    else if (e.key === "ArrowRight") forward();
    // Letter shortcuts: ignore while typing in a text field (e.g. the username filter).
    else if (e.key === "f" && !isTyping(e.target)) flip();
    else if (e.key === "r" && !isTyping(e.target)) reset();
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
