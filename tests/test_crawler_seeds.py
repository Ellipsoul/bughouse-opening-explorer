from bughouse_explorer.crawler.seeds import load_initial_seeds


def test_approved_seed_manifest_is_case_insensitively_unique():
    seeds = load_initial_seeds()

    assert len(seeds) == 35
    assert "larso" in [seed.lower() for seed in seeds]
    assert len({seed.lower() for seed in seeds}) == len(seeds)
