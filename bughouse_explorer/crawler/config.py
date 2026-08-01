"""Environment-backed crawler configuration."""

from dataclasses import dataclass
import os


DEFAULT_USER_AGENT = (
    "bughouse-explorer-crawler/0.1 "
    "(https://github.com/Ellipsoul/bughouse-opening-explorer; "
    "mailto:aronteh.chess@gmail.com)"
)


@dataclass(frozen=True)
class CrawlerConfig:
    database_path: str = "data/crawler.db"
    user_agent: str = DEFAULT_USER_AGENT
    min_interval_ms: int = 100
    sampler_version: int = 2
    max_consecutive_errors: int = 5

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        return cls(
            database_path=env.get("BUGHOUSE_CRAWLER_DB", "data/crawler.db"),
            user_agent=env.get("CHESSCOM_USER_AGENT", DEFAULT_USER_AGENT),
            min_interval_ms=int(env.get("CHESSCOM_MIN_INTERVAL_MS", "100")),
            sampler_version=int(env.get("BUGHOUSE_SAMPLER_VERSION", "2")),
            max_consecutive_errors=max(
                1, int(env.get("BUGHOUSE_MAX_CONSECUTIVE_ERRORS", "5"))
            ),
        )
