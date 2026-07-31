from bughouse_explorer.crawler.config import CrawlerConfig


def test_crawler_config_reads_sqlite_and_request_policy_from_environment():
    config = CrawlerConfig.from_env(
        {
            "BUGHOUSE_CRAWLER_DB": "/tmp/crawler.db",
            "CHESSCOM_USER_AGENT": "crawler (owner@example.com)",
            "CHESSCOM_MIN_INTERVAL_MS": "400",
            "BUGHOUSE_SAMPLER_VERSION": "2",
        }
    )

    assert config.database_path == "/tmp/crawler.db"
    assert config.user_agent == "crawler (owner@example.com)"
    assert config.min_interval_ms == 400
    assert config.sampler_version == 2
