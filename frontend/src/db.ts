// Data layer: queries the local FastAPI server (/api/...). The SQLite database lives
// server-side, so the browser only fetches small JSON results — no whole-DB download.

export const START_FEN =
  "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -";

async function api<T>(
  path: string,
  params: Record<string, string | number | undefined> = {}
): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  const res = await fetch(`/api/${path}?${qs.toString()}`);
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

// Username/side filter: match the White seat, the Black seat, or both (an exact pairing).
export interface Filters {
  white?: string;
  black?: string;
  minGames?: number;
}

export interface MoveRow {
  move_id: string;
  san: string;
  from_sq: string | null;
  to_sq: string;
  drop_piece: string | null;
  child_id: number;
  child_fen: string;
  n: number;
  white_wins: number;
  black_wins: number;
  draws: number;
}

export interface GameRow {
  white_username: string;
  white_rating: number;
  black_username: string;
  black_rating: number;
  outcome: number; // 0 = white win, 1 = black win, 2 = draw
  url: string;
  time_control: string;
}

// Continuations from position `pid` at or above mean rating `ratingMin`, with optional username
// filter. Positions are keyed by integer id (not FEN) — the id comes from the parent move's child_id
// (or meta.root_id for the start position).
export function positionMoves(
  pid: number,
  ratingMin: number,
  filters: Filters = {}
): Promise<MoveRow[]> {
  return api<MoveRow[]>("moves", {
    pid, rmin: ratingMin,
    white: filters.white, black: filters.black, min_games: filters.minGames,
  });
}

// Top games through position `pid` at or above mean rating `ratingMin` and optional username filter.
export function positionGames(
  pid: number,
  ratingMin: number,
  filters: Filters = {},
  limit = 8
): Promise<GameRow[]> {
  return api<GameRow[]>("games", {
    pid, rmin: ratingMin, white: filters.white, black: filters.black, limit,
  });
}

// Resolve a FEN to its position node (id + the normalized 4-field FEN the server keys by), or null
// if that position isn't in the indexed data. A dedicated fetch (not the api() helper) so the
// expected 404 = "not found" case stays a null return instead of a thrown error.
export async function lookupPosition(
  fen: string
): Promise<{ id: number; fen: string } | null> {
  const res = await fetch(`/api/position?fen=${encodeURIComponent(fen)}`);
  if (res.status === 404 || res.status === 400) return null;
  if (!res.ok) throw new Error(`API position failed: ${res.status}`);
  return res.json() as Promise<{ id: number; fen: string }>;
}

export interface UserOption {
  name: string;
  count: number;
}

// Distinct usernames in the dataset with game counts, most-played first (for autocomplete).
export function usernames(): Promise<UserOption[]> {
  return api<UserOption[]>("usernames");
}

let cachedMeta: Record<string, string> = {};

export async function meta(): Promise<Record<string, string>> {
  cachedMeta = await api<Record<string, string>>("meta");
  return cachedMeta;
}

// Synchronous access to the last-fetched meta (populated once at startup via meta()).
export function metaCached(): Record<string, string> {
  return cachedMeta;
}
