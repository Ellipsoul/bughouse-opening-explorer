"""Operator-approved initial crawl seeds."""

from pathlib import Path


INITIAL_SEEDS_PATH = Path(__file__).with_name("initial_seeds.txt")


def load_initial_seeds(path=INITIAL_SEEDS_PATH):
    seen = set()
    seeds = []
    for value in Path(path).read_text().split():
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        seeds.append(value)
    return seeds
