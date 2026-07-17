import { Chessground } from "chessground";
import { Api } from "chessground/api";
import { Key } from "chessground/types";

import {
  positionMoves, positionGames, meta, usernames, lookupPosition,
  Filters, START_FEN, MoveRow,
} from "./db";
import {
  renderMoves, renderMoveList, renderGames, renderRepetitionTerminal, Node,
} from "./explorer";
import { setupCombobox, ComboboxController } from "./combobox";

import "chessground/assets/chessground.base.css";
import "chessground/assets/chessground.brown.css";
import "chessground/assets/chessground.cburnett.css";
import "./styles.css";

// The start position's id, fetched from meta.root_id at startup (the DB has no fen->id index, so
// navigation is keyed by integer id; the root is the only node without a parent move to supply one).
let rootId = 0;
const makeRoot = (id: number, fen: string, ply = 0): Node => ({
  id, fen, san: null, ply, parent: null, children: [],
});

// The variation tree: `root` anchors it, `current` is the position shown on the board. Moves
// explored are never discarded — diverging from a line adds a sibling branch instead.
let root: Node = makeRoot(rootId, START_FEN);
let current: Node = root;
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
// The comboboxes load in the background after first paint, so ignore clicks until they're ready.
function pickPlayer(name: string, side: "white" | "black"): void {
  const combo = side === "white" ? whiteCombo : blackCombo;
  combo?.set(name);
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

// How many times the current position has occurred in the line so far. Positions are keyed by
// FEN-without-move-counters (placement, side, castling, ep) — exactly chess's repetition identity —
// and each such key maps to one position id, so counting equal ids along the ancestor path counts
// repetitions. Three occurrences is a threefold repetition, which ends a chess.com bughouse game as
// a draw. Only ancestors count, so a repetition in one variation doesn't poison sibling lines.
function repetitionCount(): number {
  const id = current.id;
  let count = 0;
  for (let n: Node | null = current; n; n = n.parent) if (n.id === id) count++;
  return count;
}

// True when the current node sits on a variation somewhere (some ancestor isn't its parent's
// first child) — i.e. Promote would change the tree.
function onVariation(): boolean {
  for (let n = current; n.parent; n = n.parent) {
    if (n.parent.children[0] !== n) return true;
  }
  return false;
}

async function render(): Promise<void> {
  const n = current;
  const color = turnColor(n.fen);
  const filters = currentFilters();
  const reps = repetitionCount();
  const terminal = reps >= 3; // threefold repetition: the game would end here

  // No continuations past a terminal position, so nothing is draggable either.
  currentMoves = terminal ? [] : await positionMoves(n.id, ratingMin, filters);

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

  if (terminal) {
    renderRepetitionTerminal($("explorer"));
  } else {
    renderMoves($("explorer"), currentMoves, navigateTo, minGames);
  }
  renderMoveList($("movelist"), root, current, jumpTo, terminal);
  // The node-action buttons only apply where they'd do something: Delete needs a move to delete,
  // Promote needs the current line to actually be a variation.
  ($("delete-node") as HTMLButtonElement).disabled = !current.parent;
  ($("promote-node") as HTMLButtonElement).disabled = !onVariation();
  renderGames($("games"), await positionGames(n.id, ratingMin, filters), pickPlayer);
}

function navigateTo(m: MoveRow): void {
  // Descend into the chosen move without discarding anything: reuse the child if this move was
  // already explored (two distinct moves always yield distinct child positions, so matching by
  // child_id is sound); otherwise append it — the first move played from a position stays the
  // mainline, later divergences become variations.
  let child = current.children.find((c) => c.id === m.child_id);
  if (!child) {
    child = {
      id: m.child_id,
      fen: m.child_fen,
      san: m.san,
      lastMove: m.from_sq ? [m.from_sq, m.to_sq] : [m.to_sq],
      ply: current.ply + 1,
      parent: current,
      children: [],
    };
    current.children.push(child);
  }
  current.activeChild = child;
  current = child;
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

function jumpTo(target: Node): void {
  // Point each ancestor's activeChild down the jumped-to branch so Back/Forward retrace it.
  for (let n = target; n.parent; n = n.parent) n.parent.activeChild = n;
  current = target;
  render();
}

function back(): void {
  if (current.parent) {
    current = current.parent;
    render();
  }
}
function forward(): void {
  const next = current.activeChild ?? current.children[0];
  if (next) {
    current = next;
    render();
  }
}

// ArrowUp/ArrowDown at a branch point: switch the board to the previous/next sibling move.
function cycleSibling(dir: 1 | -1): void {
  const parent = current.parent;
  if (!parent || parent.children.length < 2) return;
  const i = parent.children.indexOf(current);
  const next =
    parent.children[(i + dir + parent.children.length) % parent.children.length];
  parent.activeChild = next;
  current = next;
  render();
}

// Make the current line the mainline: at every branch point on the way up, move this branch to
// the front of its parent's children (front = mainline in the renderer).
function promoteNode(): void {
  let changed = false;
  for (let n = current; n.parent; n = n.parent) {
    const siblings = n.parent.children;
    const i = siblings.indexOf(n);
    if (i > 0) {
      siblings.splice(i, 1);
      siblings.unshift(n);
      changed = true;
    }
    n.parent.activeChild = n;
  }
  if (changed) render();
}

// Remove the current move and everything after it, stepping back to the parent position.
function deleteNode(): void {
  const parent = current.parent;
  if (!parent) return; // the root has no move to delete
  parent.children.splice(parent.children.indexOf(current), 1);
  if (parent.activeChild === current) parent.activeChild = undefined;
  current = parent;
  render();
}

function reset(): void {
  // Drop the whole tree (not just jump to its root) so the move list empties out.
  root = makeRoot(rootId, START_FEN);
  current = root;
  render();
}
function flip(): void {
  orientation = orientation === "white" ? "black" : "white";
  render();
}

// Jump straight to a pasted FEN: look up its position id and, on a hit, start a fresh line there
// (same reset-then-render shape as reset()). A FEN not in the dataset leaves the board untouched.
// Submitted on Enter or blur. A successful jump calls input.blur(), which itself fires the blur
// handler; `jumping` suppresses exactly that self-inflicted re-entry (see the blur listener) so the
// lookup isn't run twice. Any FEN can always be (re)submitted — including one just tried and one
// that failed — so a bad paste never wedges the field.
let jumping = false;
async function goToFen(): Promise<void> {
  const input = $("fen-input") as HTMLInputElement;
  const error = $("fen-error");
  const raw = input.value.trim();
  if (!raw) return;
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
  jumping = true;
  input.blur(); // drop focus so the text caret stops blinking in the field
  jumping = false;
  // Seed move numbering from the FEN: side-to-move (from the resolved position) + the fullmove
  // counter in the pasted input give the position's real ply, even though its moves are unknown.
  // A FEN without a fullmove field falls back to move 1 (nothing better is recoverable).
  const side = hit.fen.split(" ")[1];
  const fullmove = Number.parseInt(raw.split(/\s+/)[5] ?? "1", 10) || 1;
  const ply = (fullmove - 1) * 2 + (side === "b" ? 1 : 0);
  root = makeRoot(hit.id, hit.fen, ply);
  current = root;
  render();
}

// True if the event target is an editable field, so letter shortcuts don't fire while typing.
function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT") return (el as HTMLInputElement).type !== "range"; // sliders aren't typing
  return tag === "TEXTAREA" || el.isContentEditable;
}

// Make a slider pointer-only: swallow every key except Tab so keyboard input (arrows, Home/End,
// PageUp/PageDown) never moves it. Arrow keys still bubble to the document handler for the board.
function makeCursorOnly(slider: HTMLInputElement): void {
  slider.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") e.preventDefault();
  });
}

// Wire the minimum-rating slider and its live readout. Also fetch meta once so renderMoves's
// empty-state message (max_ply / min_games) has data to show.
async function setupRatingFilter(): Promise<void> {
  const m = await meta();
  rootId = Number(m.root_id);
  root = makeRoot(rootId, START_FEN); // now that rootId is known, give the root its real position id
  current = root;
  const slider = $("rating-min") as HTMLInputElement;
  const readout = $("rating-readout");
  slider.min = String(RATING_MIN);
  slider.max = String(RATING_MAX);
  slider.step = String(RATING_STEP);
  slider.value = String(ratingMin);
  makeCursorOnly(slider);
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
  makeCursorOnly(slider);
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
  $("promote-node").addEventListener("click", promoteNode);
  $("delete-node").addEventListener("click", deleteNode);
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
    // Strip the crazyhouse/bughouse pocket from the field automatically, whether bracketed
    // ([...] and its contents) or a ninth /-delimited holdings segment after the 8 ranks.
    let cleaned = fenEl.value.replace(/\[.*?\]/g, "");
    cleaned = cleaned.replace(/^(\S+)/, (placement) => placement.split("/").slice(0, 8).join("/"));
    if (cleaned !== fenEl.value) fenEl.value = cleaned;
    fitFont();
  });
  fenEl.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter") {
      e.preventDefault();
      goToFen();
    }
  });
  fenEl.addEventListener("blur", () => {
    if (!jumping) goToFen(); // skip the blur our own input.blur() fires after a successful jump
  });
  window.addEventListener("resize", () => {
    fitFont();
    cg?.redrawAll(); // the board is responsive now; recompute its bounds when the viewport changes
  });
  fitFont(); // size correctly on load
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") back();
    else if (e.key === "ArrowRight") forward();
    // Up/Down cycle sibling variations at a branch point — but not while a text field has focus
    // (the username comboboxes use those keys for their menus), and without scrolling the page.
    else if (e.key === "ArrowUp" && !isTyping(e.target)) {
      e.preventDefault();
      cycleSibling(-1);
    } else if (e.key === "ArrowDown" && !isTyping(e.target)) {
      e.preventDefault();
      cycleSibling(1);
    }
    // Letter shortcuts: ignore while typing in a text field (e.g. the username filter).
    else if (e.key === "f" && !isTyping(e.target)) flip();
    else if (e.key === "r" && !isTyping(e.target)) reset();
  });

  try {
    await setupRatingFilter();
    setupMinGamesFilter();
    await render();
  } catch (err) {
    $("loading").textContent =
      "Can't reach the explorer server — start it with `bughouse-explorer-serve`.";
    console.error(err);
    return;
  }
  $("loading").style.display = "none";

  // The username typeahead isn't needed for first paint and its list is large (tens of thousands of
  // names), so load it in the background rather than blocking the board/moves on it. Until it
  // resolves the seat comboboxes are simply inert; whiteFilter/blackFilter default to "".
  setupUsernameFilter().catch((err) => console.error("username filter failed to load:", err));
}

main();
