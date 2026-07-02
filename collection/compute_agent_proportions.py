#!/usr/bin/env python3
"""Compute domain category proportions from Dataset A agent fixture repos.

Reads the agent fixture repository list and joins with the domain classification
data to compute per-language and global category proportions. Outputs a JSON file
used by ``sample_proportional_repos.py`` for Dataset C sampling.

Usage:
    python -m collection.compute_agent_proportions
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from .config import CLASSIFY_OUTPUT_DIR, ROOT_DIR
from .logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

AGENT_REPOS_DIR = ROOT_DIR / "fixtures-from-agents" / "repos"
OUTPUT_PATH = ROOT_DIR / "fixtures-from-agents" / "category_proportions.json"


def _load_classification_map(classified_dir: Path) -> dict[str, str]:
    """Build a mapping from repo_name → domain from the classified CSVs."""
    mapping: dict[str, str] = {}
    for csv_path in sorted(classified_dir.glob("*.csv")):
        with open(csv_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name = (row.get("name") or "").strip()
                domain = (row.get("domain") or "").strip().lower()
                if name and domain:
                    mapping[name] = domain
    return mapping


def _load_agent_repos(repos_dir: Path) -> dict[str, list[str]]:
    """Load Dataset A repo names grouped by language.

    Returns:
        {language: [repo_name, ...]}
    """
    by_lang: dict[str, list[str]] = defaultdict(list)
    for csv_path in sorted(repos_dir.glob("*_agent_fixture_repos.csv")):
        # Extract language from filename: "python_agent_fixture_repos.csv" → "python"
        lang = csv_path.stem.split("_")[0]
        with open(csv_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name = (row.get("repo_name") or "").strip()
                if name:
                    by_lang[lang].append(name)
    return dict(by_lang)


def compute_proportions(
    agent_repos_dir: Path = AGENT_REPOS_DIR,
    classified_dir: Path = CLASSIFY_OUTPUT_DIR,
) -> dict:
    """Compute per-language and global category proportions.

    Returns a dict suitable for JSON serialization.
    """
    classification = _load_classification_map(classified_dir)
    agent_by_lang = _load_agent_repos(agent_repos_dir)

    per_language: dict[str, dict] = {}
    global_counts: dict[str, int] = defaultdict(int)
    global_total = 0

    for lang in sorted(agent_by_lang):
        repos = agent_by_lang[lang]
        domain_counts: dict[str, int] = defaultdict(int)
        unknown = 0

        for repo in repos:
            domain = classification.get(repo)
            if domain:
                domain_counts[domain] += 1
                global_counts[domain] += 1
                global_total += 1
            else:
                unknown += 1
                logger.warning("No classification for agent repo: %s", repo)

        total = len(repos)
        proportions = {
            d: round(c / total, 4) for d, c in sorted(domain_counts.items(), key=lambda x: -x[1])
        }

        per_language[lang] = {
            "total_repos": total,
            "classified": total - unknown,
            "unknown": unknown,
            "domain_counts": dict(sorted(domain_counts.items(), key=lambda x: -x[1])),
            "proportions": proportions,
        }

        logger.info(
            "%s: %d repos → %s",
            lang,
            total,
            "  ".join(f"{d}:{p:.1%}" for d, p in proportions.items()),
        )

    global_proportions = {
        d: round(c / global_total, 4)
        for d, c in sorted(global_counts.items(), key=lambda x: -x[1])
    }

    logger.info(
        "Global: %d repos → %s",
        global_total,
        "  ".join(f"{d}:{p:.1%}" for d, p in global_proportions.items()),
    )

    return {
        "global": {
            "total_repos": global_total,
            "domain_counts": dict(sorted(global_counts.items(), key=lambda x: -x[1])),
            "proportions": global_proportions,
        },
        "per_language": per_language,
    }


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger.info("Computing category proportions from Dataset A …")

    result = compute_proportions()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    logger.info("Written to %s", OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())