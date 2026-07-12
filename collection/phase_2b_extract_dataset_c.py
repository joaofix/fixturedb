"""Phase 2B: Extract Dataset C — human-authored fixtures from an independent
pre-2021 repo sample (the cross-repo baseline).

Reads the `dataset_c_*.csv` repo lists (see select_dataset_c_repos.py,
which selects every repo created within a fixed window -- no sampling) and
delegates to collection.dataset_c.collect_dataset_c_fixtures(), which
clones each repo, checks out its pinned pre-2021 cutoff commit, and
extracts every fixture from every test file at that snapshot (no
diff/purity gating, since this is a snapshot rather than a commit-by-commit
scan).

For Dataset B (the within-repo matched human control), see
phase_2_extract_human.py instead.

Output:
    - SQL inserts into fixturedb-human.db
    - JSON with extraction statistics
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .cli_utils import add_output_db_arg, add_workers_arg
from .dataset_c import collect_dataset_c_fixtures
from .human_corpus import load_dataset_c_repos
from .logging_utils import configure_logging, get_logger

configure_logging(fmt="%(message)s")

logger = get_logger(__name__)


def main():
    """Execute Phase 2B Dataset C collection."""

    parser = argparse.ArgumentParser(
        description="Collect Dataset C human fixtures from a pre-2021 repo sample"
    )
    project_root = Path(__file__).resolve().parents[1]
    add_output_db_arg(
        parser,
        project_root / "data" / "fixturedb-human.db",
        "Output database path",
    )
    parser.add_argument(
        "--clones-dir",
        type=Path,
        default=project_root / "clones",
        help="Directory with repository clones",
    )
    parser.add_argument(
        "--language",
        choices=["python", "javascript", "java", "typescript"],
        default=None,
        help="Process a single language (uses dataset_c_{lang}.csv); "
        "omit to process every dataset_c_*.csv found",
    )
    add_workers_arg(parser, default=4)
    args = parser.parse_args()

    clones_dir = args.clones_dir
    output_db = args.output_db
    dataset_c_dir = project_root / "fixtures-from-agents"
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats_file = output_dir / f"phase_2b_extraction_stats_{timestamp}.json"

    logger.info("=" * 70)
    logger.info("PHASE 2B: Collect Dataset C (Human Fixtures, Cross-Repo Baseline)")
    logger.info("=" * 70)
    logger.info(f"Target database: {output_db}")
    logger.info(f"Clones directory: {clones_dir}")
    logger.info(f"Dataset C repo samples: {dataset_c_dir}")
    logger.info(f"Statistics will be saved to: {stats_file}")
    logger.info("")

    # NOTE: No top-level database_has_rows guard here. Dataset C has its own
    # per-language checkpoint (dataset_c_checkpoint_<lang>.json) and per-repo
    # persistence checkpoints inside collect_dataset_c_fixtures. A blanket
    # skip-if-db-has-rows breaks multi-language workflows.

    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        logger.error("Repositories must be cloned before running Phase 2B")
        return 1

    per_lang_csv = (
        dataset_c_dir / f"dataset_c_{args.language}.csv" if args.language else None
    )
    combined_csv = dataset_c_dir / "dataset_c_sample.csv"
    available = sorted(dataset_c_dir.glob("dataset_c_*.csv"))

    if args.language:
        if not (per_lang_csv and per_lang_csv.exists()) and not combined_csv.exists():
            logger.error(
                f"No Dataset C repo sample found for language={args.language} "
                f"under {dataset_c_dir}"
            )
            return 1
    elif not available:
        logger.error(f"No dataset_c_*.csv repo samples found under {dataset_c_dir}")
        logger.error("Please run select_dataset_c_repos.py first")
        return 1

    logger.info("")

    try:
        logger.info("Starting Dataset C fixture collection...")

        cutoff_csv = dataset_c_dir / "dataset_c_repo_cutoffs.csv"
        if args.language:
            csv_path = (
                per_lang_csv if per_lang_csv and per_lang_csv.exists() else combined_csv
            )
            repos = load_dataset_c_repos(csv_path)
            logger.info(f"Loaded {len(repos)} repos from {csv_path}")
            stats, db_path = collect_dataset_c_fixtures(
                agent_repos=repos,
                clones_dir=clones_dir,
                output_db=output_db,
                cutoff_csv=cutoff_csv,
                workers=getattr(args, "workers", None) or 4,
                language=args.language,
            )
        else:
            logger.info(
                "Auto-detected %d language CSVs: %s",
                len(available),
                [p.name for p in available],
            )
            all_stats = {}
            for lang_csv in available:
                lang = lang_csv.stem.replace("dataset_c_", "")
                lang_repos = load_dataset_c_repos(lang_csv)
                logger.info(f"Processing language={lang} ({len(lang_repos)} repos)")
                lang_stats, db_path = collect_dataset_c_fixtures(
                    agent_repos=lang_repos,
                    clones_dir=clones_dir,
                    output_db=output_db,
                    cutoff_csv=cutoff_csv,
                    workers=getattr(args, "workers", None) or 4,
                    language=lang,
                )
                all_stats[lang] = lang_stats
            stats = {
                "repos_persisted": sum(
                    s.get("repos_persisted", 0) for s in all_stats.values()
                ),
                "fixtures_persisted": sum(
                    s.get("fixtures_persisted", 0) for s in all_stats.values()
                ),
                "completed_repos": sum(
                    s.get("completed_repos", 0) for s in all_stats.values()
                ),
            }

        logger.info("")
        logger.info("=" * 70)
        logger.info("EXTRACTION RESULTS SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Repositories persisted: {stats.get('repos_persisted', 0)}")
        logger.info(f"Total fixtures extracted: {stats.get('fixtures_persisted', 0)}")
        logger.info(f"Completed repos: {stats.get('completed_repos', 0)}")

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "phase": "Phase 2B - Dataset C Human Fixture Collection",
            "statistics": stats,
            "output_database": str(db_path),
        }

        with open(stats_file, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info("")
        logger.info(f"Statistics saved to: {stats_file}")
        logger.info("")
        logger.info("PHASE 2B COMPLETE")
        logger.info(
            "Next: Run phase_3_extract_agent.py (Dataset A) if not already done"
        )

        return 0

    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
