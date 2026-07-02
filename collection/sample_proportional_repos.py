#!/usr/bin/env python3
"""Sample pre-2021 repositories proportionally to Dataset A's category distribution.

Reads the category proportions computed by ``compute_agent_proportions.py`` and
samples repositories from ``github-search-raw/`` that were created before the
human corpus cutoff date. Sampling is stratified by language and domain to match
Dataset A's proportions.

Usage:
    python -m collection.sample_proportional_repos [--target N] [--seed SEED]
"""

from __future__ import annotations

import csv
import gzip
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from .config import (
    CLASSIFY_INPUT_DIR,
    CLASSIFY_OUTPUT_DIR,
    DATASET_C_SAMPLING_SEED,
    HUMAN_CORPUS_CUTOFF_DATE,
    ROOT_DIR,
)
from .logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

PROPORTIONS_PATH = ROOT_DIR / "fixtures-from-agents" / "category_proportions.json"
OUTPUT_DIR = ROOT_DIR / "fixtures-from-agents"
OUTPUT_COMBINED_PATH = OUTPUT_DIR / "dataset_c_sample.csv"

# Default: ~100 repos per language (400 total), with 20% over-sample → ~480
DEFAULT_TARGET_PER_LANGUAGE = 100
OVER_SAMPLE_FACTOR = 1.2

_OUTPUT_FIELDNAMES = ["repo_name", "language", "domain", "clone_url"]


def _load_proportions(path: Path) -> dict:
    """Load the category proportions JSON."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_pre_cutoff_repos(
    raw_dir: Path, cutoff_date: str
) -> dict[str, dict[str, list[dict]]]:
    """Load repos from github-search-raw created before *cutoff_date*.

    Returns:
        {language: {domain: [repo_dict, ...]}}
    """
    by_lang_domain: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for csv_path in sorted(raw_dir.glob("*.csv.gz"), key=lambda p: p.name):
        file_lang = csv_path.stem.split(".")[0].lower()

        with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name = (row.get("name") or row.get("full_name") or "").strip()
                if not name or "/" not in name:
                    continue

                created_at = (row.get("createdAt") or row.get("created_at") or "").strip()
                if not created_at or created_at[:10] > cutoff_date:
                    continue

                # We need the domain from the classification data — but we don't
                # have it here. We'll join later. For now, store the raw repo.
                lang = (
                    row.get("mainLanguage") or row.get("language") or file_lang
                ).strip().lower()
                # SEART CSVs don't have a clone_url column — construct it from name
                clone_url = f"https://github.com/{name}.git"

                by_lang_domain[lang]["__all__"].append({
                    "repo_name": name,
                    "language": lang,
                    "clone_url": clone_url,
                })

    return {k: dict(v) for k, v in by_lang_domain.items()}


def _load_classification_map(classified_dir: Path) -> dict[str, str]:
    """Build repo_name → domain mapping from classified CSVs."""
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


def _assign_domains(
    by_lang: dict[str, dict[str, list[dict]]],
    classification: dict[str, str],
) -> dict[str, dict[str, list[dict]]]:
    """Assign domains to pre-cutoff repos and group by (language, domain)."""
    result: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for lang, buckets in by_lang.items():
        for repo in buckets.get("__all__", []):
            domain = classification.get(repo["repo_name"], "other")
            result[lang][domain].append(repo)

    return {k: dict(v) for k, v in result.items()}


def sample_proportional(
    proportions_path: Path = PROPORTIONS_PATH,
    raw_dir: Path = CLASSIFY_INPUT_DIR,
    classified_dir: Path = CLASSIFY_OUTPUT_DIR,
    target_per_language: int = DEFAULT_TARGET_PER_LANGUAGE,
    seed: int = DATASET_C_SAMPLING_SEED,
) -> list[dict]:
    """Sample repos proportionally to Dataset A's category distribution.

    Args:
        proportions_path: Path to category_proportions.json
        raw_dir: Path to github-search-raw/
        classified_dir: Path to classified repository CSVs
        target_per_language: Target repos per language (before over-sample)
        seed: Random seed for reproducibility (default: DATASET_C_SAMPLING_SEED from config)

    Returns:
        List of sampled repo dicts with keys: repo_name, language, domain, clone_url
    """
    rnd = random.Random(seed)

    proportions = _load_proportions(proportions_path)
    per_lang_props = proportions["per_language"]

    # Load pre-cutoff repos and assign domains
    raw_by_lang = _load_pre_cutoff_repos(raw_dir, HUMAN_CORPUS_CUTOFF_DATE)
    classification = _load_classification_map(classified_dir)
    by_lang_domain = _assign_domains(raw_by_lang, classification)

    sampled: list[dict] = []
    effective_target = int(target_per_language * OVER_SAMPLE_FACTOR)

    for lang in sorted(per_lang_props):
        lang_info = per_lang_props[lang]
        lang_props = lang_info["proportions"]
        available = by_lang_domain.get(lang, {})

        logger.info("--- %s (target: %d, over-sampled: %d) ---", lang, target_per_language, effective_target)

        for domain, proportion in lang_props.items():
            pool = available.get(domain, [])
            n_wanted = max(1, round(effective_target * proportion))
            n_actual = min(n_wanted, len(pool))

            if n_actual < n_wanted:
                logger.warning(
                    "  %s: wanted %d, only %d available",
                    domain, n_wanted, n_actual,
                )

            chosen = rnd.sample(pool, n_actual) if n_actual > 0 else []
            for repo in chosen:
                repo["domain"] = domain
            sampled.extend(chosen)

            logger.info("  %s: %d/%d (proportion: %.1%%)", domain, n_actual, len(pool), proportion)

    # Shuffle so output isn't grouped by language/domain
    rnd.shuffle(sampled)

    return sampled


def write_per_language_files(sampled: list[dict], output_dir: Path) -> dict[str, int]:
    """Write one CSV per language in *output_dir*, plus a combined file.

    Returns a dict of {language: row_count}.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for r in sampled:
        by_lang[r["language"]].append(r)

    counts: dict[str, int] = {}
    for lang in sorted(by_lang):
        path = output_dir / f"dataset_c_{lang}.csv"
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_OUTPUT_FIELDNAMES)
            writer.writeheader()
            for repo in by_lang[lang]:
                writer.writerow(repo)
        counts[lang] = len(by_lang[lang])
        logger.info("  %s: %d repos → %s", lang, counts[lang], path.name)

    # Combined file
    with open(output_dir / "dataset_c_sample.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_OUTPUT_FIELDNAMES)
        writer.writeheader()
        for repo in sampled:
            writer.writerow(repo)

    return counts


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Sample pre-2021 repos proportionally to Dataset A categories"
    )
    parser.add_argument(
        "--target",
        type=int,
        default=DEFAULT_TARGET_PER_LANGUAGE,
        help="Target repos per language (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DATASET_C_SAMPLING_SEED,
        help="Random seed (default: %(default)s, from DATASET_C_SAMPLING_SEED in config)",
    )
    args = parser.parse_args(argv)

    configure_logging()

    if not PROPORTIONS_PATH.exists():
        logger.error(
            "Proportions file not found: %s. Run compute_agent_proportions first.",
            PROPORTIONS_PATH,
        )
        return 1

    logger.info("Sampling repos proportionally …")
    logger.info("Target per language: %d (×%.1f over-sample = %d)",
                 args.target, OVER_SAMPLE_FACTOR, int(args.target * OVER_SAMPLE_FACTOR))
    logger.info("Cutoff date: %s", HUMAN_CORPUS_CUTOFF_DATE)

    sampled = sample_proportional(
        target_per_language=args.target,
        seed=args.seed,
    )

    counts = write_per_language_files(sampled, OUTPUT_DIR)

    # Summary
    by_domain: dict[str, int] = defaultdict(int)
    for r in sampled:
        by_domain[r["domain"]] += 1

    logger.info("Sampled %d repos total", len(sampled))
    for lang in sorted(counts):
        logger.info("  %s: %d", lang, counts[lang])
    logger.info("Domains: %s", "  ".join(f"{d}:{c}" for d, c in sorted(by_domain.items(), key=lambda x: -x[1])))
    logger.info("Written to %s/", OUTPUT_DIR)

    return 0


if __name__ == "__main__":
    sys.exit(main())