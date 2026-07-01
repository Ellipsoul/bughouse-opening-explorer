// Rendering of the explorer panels: the continuations table (with win-rate bars), the move-list
// breadcrumb, and the games panel.

import { MoveRow, GameRow, metaCached } from "./db";

export interface Node {
  id: number; // position id (query key); fen is kept for board rendering
  fen: string;
  san: string | null;
  lastMove?: string[];
  // Half-moves played before this position (0 for the game start). Only meaningful on the first node
  // of a line: after a FEN jump it seeds correct move numbering, since the FEN gives us the move
  // number and side-to-move even though the moves that reached it are unknown.
  ply?: number;
}

function pct(x: number, n: number): number {
  return n ? Math.round((100 * x) / n) : 0;
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
    el.innerHTML = `<p class="empty">No further continuations to show here. Moves played in fewer
      than ${minGames} games are hidden — lower the Min games filter to show them. Moves beyond
      ${depth} aren't recorded.</p>`;
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
  path: Node[],
  cursor: number,
  onJump: (index: number) => void
): void {
  el.innerHTML = "";
  // Number/colour each ply from its absolute half-move index (basePly + i) rather than the array
  // index, so a line that starts from a jumped FEN is numbered from that position's real move number
  // (e.g. "15... Nc6") instead of restarting at 1.
  const basePly = path[0]?.ply ?? 0;
  if (basePly > 0) {
    const hint = document.createElement("span");
    hint.className = "ply-hint";
    hint.textContent = "…";
    hint.title = "Line started from a pasted position — the earlier moves aren't known";
    el.appendChild(hint);
  }
  path.forEach((node, i) => {
    if (i === 0) return; // starting node has no move leading into it
    const p = basePly + i; // absolute half-move number of the move into this node
    const isWhite = p % 2 === 1;
    const moveNo = Math.ceil(p / 2);
    const span = document.createElement("span");
    span.className = "ply" + (i === cursor ? " current" : "");
    // White: "3. Nf3"; Black: bare "Nc6", except a Black move opening the line gets "3... Nc6".
    const prefix = isWhite ? `${moveNo}. ` : i === 1 ? `${moveNo}... ` : "";
    span.textContent = prefix + node.san;
    span.addEventListener("click", () => onJump(i));
    el.appendChild(span);
  });
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
