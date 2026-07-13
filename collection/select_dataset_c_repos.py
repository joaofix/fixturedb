#!/usr/bin/env python3
"""Select Dataset C repos: created within a fixed window, no sampling.

Replaces sample_proportional_repos.py's role. Filters github-search-raw/
to repos created between DATASET_C_MIN_CREATED_DATE and
HUMAN_CORPUS_CUTOFF_DATE and writes every qualifying repo straight to
datasets/c/repos/{lang}_repo.csv (plus a combined all.csv) -- no domain
classification, no stratification, no per-language cap. The date window
itself is what bounds fixture-age risk and candidate volume; a proportional
sample on top of it is no longer needed. See
internal-docs/methodology-improvements/dataset-c-repo-selection.md for why.

The actual repo quality floor (commit count, test file count) is enforced
later in dataset_c.py, measured from each repo's real git history as of
the cutoff commit -- not from GitHub's live metadata, which only reflects
today's popularity, not the repo's state at the time. See that module's
_process_repo() docstring.

Usage:
    python -m collection discover-repos --dataset c
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import paths
from .config import DATASET_C_MIN_CREATED_DATE, HUMAN_CORPUS_CUTOFF_DATE
from .csv_adapter import get_adapter
from .logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

OUTPUT_DIR = paths.stage_dir("c", "repos")

_OUTPUT_FIELDNAMES = [
    "repo_name",
    "language",
    "clone_url",
    "github_id",
    "created_at",
    "topics",
    "stars",
]


def select_repos(
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    min_created: str = DATASET_C_MIN_CREATED_DATE,
    cutoff_date: str = HUMAN_CORPUS_CUTOFF_DATE,
) -> list[dict]:
    """Return every repo in raw_dir created within [min_created, cutoff_date].

    No sampling, no per-language cap, no domain classification -- the date
    window is the only filter applied here.

    github_id is carried through from the raw CSV's own "id" column
    (SEART/GitHub's real numeric repo ID) -- this is the uniqueness key
    the repositories table's github_id UNIQUE constraint relies on.
    Discarding it (as this function used to) means every repo defaults to
    github_id=0 downstream and collides on that constraint, silently
    collapsing an entire collection run's repos into a single DB row. See
    internal-docs/methodology-improvements/dataset-c-repo-selection.md.
    """
    selected: list[dict] = []
    for csv_path in sorted(raw_dir.glob("*.csv.gz"), key=lambda p: p.name):
        file_lang = csv_path.stem.split(".")[0].lower()
        with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name = (row.get("name") or row.get("full_name") or "").strip()
                if not name or "/" not in name:
                    continue

                created = (row.get("createdAt") or row.get("created_at") or "").strip()[:10]
                if not created or created < min_created or created > cutoff_date:
                    continue

                raw_id = (row.get("id") or "").strip()
                try:
                    github_id = int(raw_id)
                except ValueError:
                    github_id = None
                if github_id is None:
                    continue

                lang = (
                    (row.get("mainLanguage") or row.get("language") or file_lang)
                    .strip()
                    .lower()
                )
                # SEART exports topics as a ';'-separated string, not JSON --
                # convert here so classify_domain() (which expects a JSON
                # array string) can actually read it. Same fix as Dataset A's
                # agent_repository_counter.py.
                topics_raw = (row.get("topics") or "").strip()
                topics_json = json.dumps([t for t in topics_raw.split(";") if t])
                stars = row.get("stargazers") or row.get("watchers") or 0
                try:
                    stars = int(float(stars))
                except (TypeError, ValueError):
                    stars = 0
                selected.append(
                    {
                        "repo_name": name,
                        "language": lang,
                        "clone_url": f"https://github.com/{name}.git",
                        "github_id": github_id,
                        "created_at": created,
                        "topics": topics_json,
                        "stars": stars,
                    }
                )

    return selected


def write_per_language_files(selected: list[dict], output_dir: Path) -> dict[str, int]:
    """Write one CSV per language in output_dir (`{lang}_repo.csv`), plus a
    combined file (`all.csv`).

    Returns a dict of {language: row_count}.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for r in selected:
        by_lang[r["language"]].append(r)

    adapter = get_adapter()
    counts: dict[str, int] = {}
    for lang in sorted(by_lang):
        path = output_dir / f"{lang}_repo.csv"
        adapter.write_dicts(path, by_lang[lang], _OUTPUT_FIELDNAMES)
        counts[lang] = len(by_lang[lang])
        logger.info("  %s: %d repos -> %s", lang, counts[lang], path.name)

    adapter.write_dicts(output_dir / "all.csv", selected, _OUTPUT_FIELDNAMES)

    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: select Dataset C repos created within the fixed window."""
    configure_logging()

    logger.info(
        "Selecting repos created between %s and %s (no sampling)",
        DATASET_C_MIN_CREATED_DATE,
        HUMAN_CORPUS_CUTOFF_DATE,
    )

    selected = select_repos()
    counts = write_per_language_files(selected, OUTPUT_DIR)

    logger.info("Selected %d repos total", len(selected))
    for lang in sorted(counts):
        logger.info("  %s: %d", lang, counts[lang])
    logger.info("Written to %s/", OUTPUT_DIR)

    return 0


if __name__ == "__main__":
    sys.exit(main())
