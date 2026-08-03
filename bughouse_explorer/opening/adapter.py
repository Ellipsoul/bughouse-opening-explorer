"""Format-neutral records read from an immutable crawler snapshot."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from bughouse_explorer.tcn import decode_tcn


STANDARD_INITIAL_SETUP = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
)
ADAPTER_POLICY_VERSION = "opening-adapter-v2-short-non-checkmate"


@dataclass(frozen=True)
class InclusionPolicy:
    max_plies: int = 2_048
    max_short_non_checkmate_plies: int = 6
    accepted_sources: frozenset[str] = frozenset({"public", "callback"})


@dataclass(frozen=True)
class SnapshotSelection:
    rowid_modulus: int
    rowid_remainder: int = 0

    def __post_init__(self):
        if self.rowid_modulus <= 0:
            raise ValueError("rowid_modulus must be positive")
        if not 0 <= self.rowid_remainder < self.rowid_modulus:
            raise ValueError("rowid_remainder must be inside the modulus")


@dataclass(frozen=True)
class OpeningGame:
    uuid: str
    move_tokens: tuple[str, ...]
    white_username: str
    black_username: str
    white_rating: int | None
    black_rating: int | None
    white_result: str | None
    black_result: str | None
    end_time: int | None
    time_control: str | None
    rated: bool
    url: str | None
    source: str
    content_hash: str
    provenance_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterOutcome:
    source_rowid: int
    game: OpeningGame | None = None
    skip_reason: str | None = None


class CrawlerSnapshotAdapter:
    """Expose crawler rows as storage-independent opening-game outcomes."""

    def __init__(self, path: str | Path, policy: InclusionPolicy | None = None):
        self.path = Path(path).resolve()
        self.policy = policy or InclusionPolicy()

    def iter_outcomes(self, selection: SnapshotSelection | None = None):
        uri = f"file:{self.path}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            where = ""
            parameters = ()
            if selection is not None:
                where = "WHERE (g.rowid % ?) = ?"
                parameters = (
                    selection.rowid_modulus,
                    selection.rowid_remainder,
                )
            rows = connection.execute(
                f"""
                SELECT
                    g.rowid AS source_rowid,
                    g.uuid,
                    g.tcn,
                    g.rules,
                    g.initial_setup,
                    g.end_time,
                    g.time_control,
                    g.rated,
                    g.url,
                    g.source,
                    g.content_hash,
                    white_player.username AS white_username,
                    white.rating AS white_rating,
                    white.result AS white_result,
                    black_player.username AS black_username,
                    black.rating AS black_rating,
                    black.result AS black_result
                FROM games AS g
                LEFT JOIN game_participants AS white
                  ON white.game_uuid = g.uuid AND white.color = 'white'
                LEFT JOIN players AS white_player ON white_player.id = white.player_id
                LEFT JOIN game_participants AS black
                  ON black.game_uuid = g.uuid AND black.color = 'black'
                LEFT JOIN players AS black_player ON black_player.id = black.player_id
                {where}
                ORDER BY g.rowid
                """,
                parameters,
            )
            for row in rows:
                tcn = row["tcn"] or ""
                reason = self._skip_reason(row, tcn)
                if reason is not None:
                    yield AdapterOutcome(
                        source_rowid=row["source_rowid"], skip_reason=reason
                    )
                    continue
                provenance_flags = []
                if row["source"] == "callback":
                    provenance_flags.append("callback_source")
                if row["white_username"] == row["black_username"]:
                    provenance_flags.append("same_account")
                ratings = (row["white_rating"], row["black_rating"])
                if any(rating == 0 for rating in ratings):
                    provenance_flags.append("rating_zero")
                if any(rating is not None and rating > 4_000 for rating in ratings):
                    provenance_flags.append("rating_over_4000")
                yield AdapterOutcome(
                    source_rowid=row["source_rowid"],
                    game=OpeningGame(
                        uuid=row["uuid"],
                        move_tokens=tuple(
                            tcn[offset : offset + 2]
                            for offset in range(0, len(tcn), 2)
                        ),
                        white_username=row["white_username"],
                        black_username=row["black_username"],
                        white_rating=row["white_rating"],
                        black_rating=row["black_rating"],
                        white_result=row["white_result"],
                        black_result=row["black_result"],
                        end_time=row["end_time"],
                        time_control=row["time_control"],
                        rated=bool(row["rated"]),
                        url=row["url"],
                        source=row["source"],
                        content_hash=row["content_hash"],
                        provenance_flags=tuple(provenance_flags),
                    ),
                )

    def _skip_reason(self, row: sqlite3.Row, tcn: str) -> str | None:
        if not tcn:
            return "empty_tcn"
        if row["source"] not in self.policy.accepted_sources:
            return "unsupported_source"
        if row["rules"] != "bughouse":
            return "non_bughouse_rules"
        if row["initial_setup"] != STANDARD_INITIAL_SETUP:
            return "nonstandard_initial_setup"
        if row["white_username"] is None or row["black_username"] is None:
            return "participant_shape"
        if len(tcn) // 2 > self.policy.max_plies:
            return "safety_limit"
        try:
            decode_tcn(tcn)
        except (IndexError, ValueError):
            return "decode_error"
        if (
            len(tcn) // 2 <= self.policy.max_short_non_checkmate_plies
            and row["white_result"] != "checkmated"
            and row["black_result"] != "checkmated"
        ):
            return "short_non_checkmate"
        return None
