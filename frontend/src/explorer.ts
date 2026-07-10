// Rendering of the explorer panels: the continuations table (with win-rate bars), the move-list
// breadcrumb, and the games panel.

import { MoveRow, GameRow, metaCached } from "./db";

// One position in the variation tree. The tree is parent-linked; children[0] is the mainline
// continuation and later children are variations (the first move played from a position stays
// the mainline; later divergences become sidelines).
export interface Node {
  id: number; // position id (query key); fen is kept for board rendering
  fen: string;
  san: string | null; // null only at the root (no move leads into it)
  lastMove?: string[];
  // Absolute half-move index of the move into this node (child.ply = parent.ply + 1). The root
  // carries the base ply: 0 for the game start, or the real ply after a FEN jump — the FEN gives
  // the move number and side-to-move even though the moves that reached it are unknown.
  ply: number;
  parent: Node | null;
  children: Node[];
  activeChild?: Node; // last child navigated into, so Forward retraces the path just taken
}

function pct(x: number, n: number): number {
  return n ? Math.round((100 * x) / n) : 0;
}

// Shown in place of the continuations once the current line has repeated a position three times:
// chess.com ends bughouse games by repetition, so the line is terminal here and forward moves are
// suppressed (the board's drag targets are cleared by the caller). Back/Reset/jump still work.
export function renderRepetitionTerminal(el: HTMLElement): void {
  el.innerHTML = `
    <div class="terminal">
      <span class="terminal-badge">½–½</span>
      <div class="terminal-body">
        <strong>Draw by threefold repetition</strong>
      </div>
    </div>`;
}

export function renderMoves(
  el: HTMLElement,
  moves: MoveRow[],
  onPick: (m: MoveRow) => void,
  minGames: number
): void {
  el.innerHTML = "";
  if (!moves.length) {
    const m = metaCached();
    const depth = m.max_ply
      ? `move ${Math.floor(Number(m.max_ply) / 2)}`
      : "the indexed depth";
    const empty = document.createElement("p");
    empty.className = "empty";
    // At minGames 1 the filter hides nothing, so don't suggest lowering it.
    const filterNote =
      minGames > 1
        ? `Moves played in fewer than ${minGames} games are hidden — lower the Min games
      filter to show them. `
        : "";
    empty.textContent = `No further continuations to show here. ${filterNote}Moves beyond
      ${depth} aren't recorded.`;
    el.appendChild(empty);
    return;
  }
  const totalOverall = moves.reduce((s, m) => s + m.n, 0);
  for (const m of moves) {
    const pw = pct(m.white_wins, m.n);
    const pd = pct(m.draws, m.n);
    const pb = pct(m.black_wins, m.n);
    // Only label a segment when it is wide enough to fit the text (skips thin draw slivers).
    const label = (p: number) => (p >= 12 ? `${p}%` : "");
    const row = document.createElement("div");
    row.className = "move-row";
    row.innerHTML = `
      <div class="move-san">${m.san}</div>
      <div class="move-count">
        <div class="games">${m.n.toLocaleString()}</div>
        <div class="share">${pct(m.n, totalOverall)}%</div>
      </div>
      <div class="winbar" title="White ${pw}% · Draw ${pd}% · Black ${pb}%">
        <span class="w" style="width:${pw}%">${label(pw)}</span>
        <span class="d" style="width:${pd}%">${label(pd)}</span>
        <span class="b" style="width:${pb}%">${label(pb)}</span>
      </div>
    `;
    row.addEventListener("click", () => onPick(m));
    el.appendChild(row);
  }
}

export function renderMoveList(
  el: HTMLElement,
  root: Node,
  current: Node,
  onJump: (node: Node) => void,
  drawByRepetition = false
): void {
  // Append one move's span, numbered from its absolute ply: White always gets "3. Nf3"; Black is
  // bare "Nc6" mid-line but gets "3... Nc6" when it opens a line or resumes after a variation
  // block. The ½–½ badge sits right after the current move when it completes a threefold.
  const appendMove = (
    container: HTMLElement,
    node: Node,
    needsNumber: boolean
  ): void => {
    const isWhite = node.ply % 2 === 1;
    const moveNo = Math.ceil(node.ply / 2);
    const span = document.createElement("span");
    span.className = "ply" + (node === current ? " current" : "");
    const prefix = isWhite ? `${moveNo}. ` : needsNumber ? `${moveNo}... ` : "";
    span.textContent = prefix + node.san;
    span.addEventListener("click", () => onJump(node));
    container.appendChild(span);
    if (drawByRepetition && node === current) {
      const badge = document.createElement("span");
      badge.className = "ply-draw";
      badge.textContent = "½–½";
      badge.title = "Draw by threefold repetition";
      container.appendChild(badge);
    }
  };

  const paren = (text: "(" | ")"): HTMLElement => {
    const span = document.createElement("span");
    span.className = "paren";
    span.textContent = text;
    return span;
  };

  // Render the line starting at `first`: its moves flow inline; at each branch point the
  // alternatives are emitted as parenthesized, indented blocks (recursively — nested blocks
  // indent further via CSS), then the line continues below them.
  const renderLine = (
    container: HTMLElement,
    first: Node,
    isLineStart: boolean
  ): void => {
    let n = first;
    let needsNumber = isLineStart;
    for (;;) {
      appendMove(container, n, needsNumber);
      needsNumber = false;
      // Branch point: this mainline move has alternatives — render each as a variation block.
      // (A variation node skips this; its own siblings were already rendered by its parent line.)
      const siblings = n.parent!.children;
      if (siblings.length > 1 && siblings[0] === n) {
        for (let i = 1; i < siblings.length; i++) {
          const block = document.createElement("div");
          block.className = "variation";
          block.appendChild(paren("("));
          renderLine(block, siblings[i], true);
          block.appendChild(paren(")"));
          container.appendChild(block);
        }
        needsNumber = true; // a Black move resuming after a block re-states its move number
      }
      if (!n.children.length) break;
      n = n.children[0];
    }
  };

  el.innerHTML = "";
  if (root.ply > 0) {
    const hint = document.createElement("span");
    hint.className = "ply-hint";
    hint.textContent = "…";
    hint.title = "Line started from a pasted position — the earlier moves aren't known";
    el.appendChild(hint);
  }
  if (root.children.length) renderLine(el, root.children[0], true);
}

function resultBadge(g: GameRow): string {
  if (g.outcome === 0) return "1–0"; // white win
  if (g.outcome === 1) return "0–1"; // black win
  return "½–½"; // draw
}

function playerButton(
  name: string,
  rating: number,
  side: "white" | "black",
  onPick: (name: string, side: "white" | "black") => void
): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.className = "player";
  btn.title = `Filter ${side} = ${name}`;
  btn.innerHTML = `<span class="pname"></span> <small>${rating}</small>`;
  btn.querySelector(".pname")!.textContent = name; // avoid HTML injection from usernames
  btn.addEventListener("click", () => onPick(name, side));
  return btn;
}

export function renderGames(
  el: HTMLElement,
  games: GameRow[],
  onPickPlayer: (name: string, side: "white" | "black") => void
): void {
  el.innerHTML = "";
  if (!games.length) {
    el.innerHTML = `<p class="empty">—</p>`;
    return;
  }
  for (const g of games) {
    const row = document.createElement("div");
    row.className = "game-row";

    const players = document.createElement("span");
    players.className = "players";
    players.append(
      playerButton(g.white_username, g.white_rating, "white", onPickPlayer),
      document.createTextNode(" vs "),
      playerButton(g.black_username, g.black_rating, "black", onPickPlayer)
    );

    const link = document.createElement("a");
    link.className = "result";
    link.href = g.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = `${resultBadge(g)} ↗`;

    row.append(players, link);
    el.appendChild(row);
  }
}
