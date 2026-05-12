#!/usr/bin/env python3
"""
fixture-corpus -- corpus collection pipeline CLI

IMPORTANT: Pre-scraped repositories from SEART-GHS must be available in github-search/ folder.
Download CSV files from https://seart-ghs.si.usi.ch/ before running the pipeline.

Commands
--------
  init          Initialise the SQLite database
  load          Load repos from SEART-GHS CSV files into DB
  clone         Clone repos in 'discovered' status
  extract       Extract fixtures from repos in 'cloned' status
  run           Run the full pipeline end-to-end (load -> clone -> extract -> classify -> categorize)
  toy           Build toy dataset (10 repos/language) for validation
  stats         Print current corpus statistics

Examples
--------
  # Full pipeline for Python only, 50 repos
  python pipeline.py run --language python --max 50

  # Build toy dataset for testing recent changes
  python pipeline.py toy
  python pipeline.py toy --language python

  # Load phase only, all languages
  python pipeline.py search --max 200

  # Check what we have so far
  python pipeline.py stats
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from collection.config import (
    LANGUAGE_CONFIGS,
    CLONE_BATCH_SIZE,
    MAX_COLLECTION_ITERATIONS,
)
from collection.db import (
    initialise_db,
    db_is_initialised,
    db_session,
    get_corpus_stats,
    get_analyzed_count_by_language,
    get_analyzed_count_for_language,
)
from collection.github_search_loader import load_repos_for_language, load_all_languages
from collection.cloner import clone_pending_repos, cleanup_stale_clones
from collection.extractor import extract_all_cloned
from collection.classifier import classify_all
from collection.fixture_classifier import categorize_all
from collection.exporter import export_dataset
from collection.validator import generate_sample, compute_metrics

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/pipeline.log"),
    ],
)
logger = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize the SQLite database schema."""
    initialise_db()
    logger.info("✓ Database initialised.")


def cmd_load(args: argparse.Namespace) -> None:
    """Load pre-scraped repositories from SEART-GHS CSV files.

    Loads all repos from CSV that pass basic quality filters (archived, forks,
    keywords, minimum commits/stars). The 500-per-language target is enforced
    at the clone/analyze phase, not here.
    """
    language = args.language

    if language:
        if language not in LANGUAGE_CONFIGS:
            print(
                f"Unknown language '{language}'. "
                f"Choose from: {list(LANGUAGE_CONFIGS)}"
            )
            sys.exit(1)
        count = load_repos_for_language(language)
        print(f"✓ {count} repos loaded for {language}")
    else:
        print(f"Loading all languages (all repos passing basic quality filters)...")
        results = load_all_languages()
        for lang, count in results.items():
            print(f"  {lang:12s}: {count} repos")


def cmd_cleanup(args: argparse.Namespace) -> None:
    """Remove stale clone directories from interrupted runs."""
    counts = cleanup_stale_clones(dry_run=dry_run)
    verb = "Would remove" if dry_run else "Removed"
    print(f"✓ Cleanup done.")
    print(f"  {verb} {counts['removed']} stale clone(s)")
    print(f"  {verb} {counts['orphaned']} orphaned clone(s)")
    print(f"  Kept {counts['kept']} valid clone(s) (awaiting extraction)")


def cmd_cleanup_toy(args: argparse.Namespace) -> None:
    """Remove all extracted repos beyond the first 50 per language."""

    print("╔════════════════════════════════════════════════╗")
    print("║  Cleaning up database to keep only TOY dataset ║")
    print("╚════════════════════════════════════════════════╝")

    summary = cleanup_to_toy_dataset()

    print(f"\n── Cleanup Summary ────────────────────────────")
    print(f"  Repos removed:     {summary['repos_removed']}")
    print(f"  Fixtures removed:  {summary['fixtures_removed']}")
    print(f"  Mock usages removed: {summary['mocks_removed']}")

    if summary["per_language"]:
        print(f"\n── Per Language ───────────────────────────────")
        for lang, counts in sorted(summary["per_language"].items()):
            print(
                f"  {lang:12s}: kept {counts['kept']:3d}, removed {counts['removed']:3d}"
            )

    print(f"\n✓ Cleanup complete. Database now contains only toy dataset.")


def cmd_clone(args: argparse.Namespace) -> None:
    """Clone pending discovered repositories."""
    # batch=N means "process at most N repos this run" (incremental mode)
    batch = getattr(args, "batch", None)
    summary = clone_pending_repos(
        language=args.language,
        batch_size=batch,
    )
    print(f"✓ Clone batch done: {summary}")


def cmd_extract(
    args: argparse.Namespace,
    target_analyzed: int | None = None,
    target_per_language: int | None = None,
    target_per_language_dict: dict[str, int] | None = None,
):
    """Extract fixtures from cloned repos, optionally stopping early when target is reached."""
    totals = extract_all_cloned(
        language=args.language,
        target_analyzed=target_analyzed,
        target_per_language=target_per_language,
        target_per_language_dict=target_per_language_dict,
    )
    early_stopped = totals.pop("early_stopped", False)
    print(f"✓ Extraction done: {totals} (early_stopped={early_stopped})")
    return early_stopped


def cmd_run(args: argparse.Namespace) -> None:
    """Run all collection phases sequentially: load → clone → extract → classify → categorize."""
    print("── Phase 0: Initialise ─────────────────────────────")
    if db_is_initialised():
        print("  Database already initialised — skipping.")
    else:
        cmd_init(args)

    print("\n── Phase 1: Load SEART-GHS repos ──────────────────")
    cmd_load(args)

    print("\n── Phase 2: Clone repositories ─────────────────────")
    # Override batch to None so ALL discovered repos are cloned, not just
    # the default batch of 50. The --batch flag on `run` is intentionally
    # removed — use `clone --batch N` for incremental operation instead.
    args.batch = None
    cmd_clone(args)

    print("\n── Phase 3: Extract fixtures ───────────────────────")
    cmd_extract(args)

    print("\n── Phase 4: Classify domains ───────────────────────")
    args.overwrite = False
    cmd_classify(args)

    print("\n── Phase 5: Categorize fixtures ────────────────────")
    args.overwrite = False
    cmd_categorize(args)

    print("\n── Done ─────────────────────────────────────────────")
    cmd_stats(args)


def cmd_collect_balanced(args: argparse.Namespace, targets: dict[str, int]) -> None:
    """
    Balanced iterative collection: Clones and extracts until all languages reach target.

    Repeats clone+extract cycles until each language has >=targets[lang] repos
    with successfully extracted fixtures, ensuring balanced representation across languages.

    Args:
        args: Command arguments
        targets: Dictionary mapping language names to target repo counts
    """
    from collection.db import get_analyzed_count_by_language

    max_iterations = MAX_COLLECTION_ITERATIONS  # Safety limit to prevent infinite loops
    iteration = 1

    while iteration <= max_iterations:
        print(f"\n{'='*70}")
        print(f"Balanced Collection - Iteration {iteration}/{max_iterations}")
        print(f"{'='*70}")

        # Check current extraction status per language
        with db_session() as conn:
            current_counts = get_analyzed_count_by_language(conn)

        # Determine which languages need more repos
        languages_below_target = {}
        for lang in LANGUAGE_CONFIGS.keys():
            current = current_counts.get(lang, 0)
            languages_below_target[lang] = current
            target = targets.get(lang, 0)
            status = "✓" if current >= target else "✗"
            print(f"  {status} {lang:12s}: {current:4d}/{target}")

        # Check if all languages reached target
        all_reached = all(
            current >= targets.get(lang, 0)
            for lang, current in languages_below_target.items()
        )

        if all_reached:
            print(f"\n✓ ALL LANGUAGES REACHED TARGET")
            break

        # Clone phase: Only clone for languages below target
        print(f"\n── Phase: Clone (iteration {iteration}) ─────────────────────")
        print(f"  Cloning ~100 repos per language (only for those below target)...")
        for lang in LANGUAGE_CONFIGS.keys():
            current = languages_below_target.get(lang, 0)
            target = targets.get(lang, 0)
            if current < target:
                args.language = lang
                args.batch = 100
                cmd_clone(args)
                print(f"    Cloning {lang} (currently {current}/{target})")
            else:
                print(f"    Skipping {lang} (already at {current}/{target})")
        args.language = None  # Reset for extraction

        # Extract phase: Stop when all languages reach target
        print(f"\n── Phase: Extract (iteration {iteration}) ────────────────────")
        print(f"  Extracting until all languages reach their targets...")
        cmd_extract(args, target_per_language_dict=targets)

        iteration += 1

    if iteration > max_iterations:
        print(
            f"\n⚠️  Max iterations ({max_iterations}) reached. Some languages may be below target."
        )
        print(f"  Current status:")
        with db_session() as conn:
            current_counts = get_analyzed_count_by_language(conn)
        for lang in LANGUAGE_CONFIGS.keys():
            current = current_counts.get(lang, 0)
            target = targets.get(lang, 0)
            print(f"    {lang:12s}: {current}/{target}")

    print(f"\n── Done ─────────────────────────────────────────────")
    cmd_stats(args)


def cmd_toy(args: argparse.Namespace) -> None:
    """
    Run pipeline on toy/validation dataset: Balanced extraction of repos per language.

    Uses iterative balanced collection to ensure all languages are represented equally.
    Continues cloning and extracting until each language reaches the target.

    Flow:
    1. Load all repos (if not already loaded)
    2. Iteratively: Clone batches and extract until all languages reach target
    3. Classify and categorize the extracted fixtures
    """
    from collection.config import LANGUAGE_CONFIGS

    # Build per-language targets from config
    toy_targets = {lang: config.toy_target for lang, config in LANGUAGE_CONFIGS.items()}
    total_toys = sum(toy_targets.values())

    print("╔════════════════════════════════════════════════════╗")
    print(f"║  TOY DATASET ({total_toys} extracted repos total)            ║")
    print("╚════════════════════════════════════════════════════╝")

    print("\n── Phase 0: Initialise ─────────────────────────────")
    if db_is_initialised():
        print("  Database already initialised — skipping.")
    else:
        cmd_init(args)

    print("\n── Phase 1: Load SEART-GHS repos ──────────────────")
    print("  (Loading all repos passing basic quality filters)")
    cmd_load(args)

    print("\n── Phase 2-3: Balanced Clone + Extract ────────────")
    print(f"  (Iteratively collecting until targets reached per language)")
    cmd_collect_balanced(args, targets=toy_targets)
    args.language = None  # Reset language filter

    print("\n── Phase 4: Classify domains ───────────────────────")
    args.overwrite = False
    cmd_classify(args)

    print("\n── Phase 5: Categorize fixtures ────────────────────")
    args.overwrite = False
    cmd_categorize(args)

    print("\n── Done ─────────────────────────────────────────────")
    cmd_stats(args)

    print("\n✓ TOY DATASET COMPLETE")
    print("  Ready for testing and validation of recent changes.")
    print("  To run tests: python -m pytest tests/")


def cmd_full(args: argparse.Namespace) -> None:
    """
    Run full pipeline: Balanced extraction of repos per language.

    Uses iterative balanced collection to ensure all languages are represented equally.
    Continues cloning and extracting until each language reaches its target.
    This produces the production-quality research corpus.

    Flow:
    1. Load all repos (if not already loaded)
    2. Iteratively: Clone batches and extract until all languages reach target
    3. Classify and categorize the extracted fixtures
    4. Export final corpus
    """
    from collection.config import LANGUAGE_CONFIGS

    # Build per-language targets from config
    full_targets = {
        lang: config.full_target for lang, config in LANGUAGE_CONFIGS.items()
    }
    total_full = sum(full_targets.values())

    print("╔════════════════════════════════════════════════════╗")
    print(f"║  FULL DATASET ({total_full} extracted repos total)           ║")
    print("╚════════════════════════════════════════════════════╝")

    print("\n── Phase 0: Initialise ─────────────────────────────")
    if db_is_initialised():
        print("  Database already initialised — skipping.")
    else:
        cmd_init(args)

    print("\n── Phase 1: Load SEART-GHS repos ──────────────────")
    print("  (Loading all repos passing basic quality filters)")
    cmd_load(args)

    print("\n── Phase 2-3: Balanced Clone + Extract ────────────")
    print(f"  (Iteratively collecting until targets reached per language)")
    cmd_collect_balanced(args, targets=full_targets)
    args.language = None  # Reset language filter

    print("\n── Phase 4: Classify domains ───────────────────────")
    args.overwrite = False
    cmd_classify(args)

    print("\n── Phase 5: Categorize fixtures ────────────────────")
    args.overwrite = False
    cmd_categorize(args)

    print("\n── Phase 6: Export corpus ──────────────────────────")
    cmd_export(args)

    print("\n── Done ─────────────────────────────────────────────")
    cmd_stats(args)

    print("\n✓ FULL DATASET COMPLETE")
    print(
        f"  Production corpus with {FULL_TARGET_REPOS_PER_LANGUAGE} repos/language ready for analysis."
    )


def cmd_classify(args: argparse.Namespace) -> None:
    """Classify repository domains (web/cli/data/infra/library/other)."""
    counts = classify_all(overwrite=args.overwrite)
    print(f"✓ Domain classification done: {counts}")


def cmd_categorize(args: argparse.Namespace) -> None:
    """Categorize detected fixtures into types and patterns."""
    counts = categorize_all(overwrite=args.overwrite)
    print(f"✓ Fixture categorization done: {counts}")


def cmd_export(args: argparse.Namespace) -> None:
    """Export collected dataset as a versioned ZIP archive."""
    zip_path = export_dataset(
        version=args.version,
        include_raw_source=args.include_source,
    )
    print(f"✓ Dataset exported to: {zip_path}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Run quality checks on extracted fixtures."""
    if args.compute:
        from pathlib import Path

        results = compute_metrics(Path(args.compute))
        if results:
            print("✓ Metrics computed. See output above.")
    else:
        out = generate_sample(n_per_language=args.sample)
        if out:
            print(f"✓ Sample written to: {out}")


def cmd_stats(args: argparse.Namespace) -> None:
    """Print current corpus statistics."""
    with db_session() as conn:
        stats = get_corpus_stats(conn)

    col_w = 22
    print(f"\n{'Corpus statistics':─<45}")
    status_keys = [
        "repos_discovered",
        "repos_cloned",
        "repos_analysed",
        "repos_skipped",
        "repos_error",
    ]
    for k in status_keys:
        label = k.replace("_", " ").capitalize()
        print(f"  {label:<{col_w}} {stats.get(k, 0):>8,}")
    print()
    for k in ("test_files", "fixtures", "mock_usages"):
        label = k.replace("_", " ").capitalize()
        print(f"  {label:<{col_w}} {stats.get(k, 0):>8,}")
    print()


def cmd_quantitative_eda(args: argparse.Namespace) -> None:
    """Generate quantitative exploratory data analysis plots."""
    """Generate quantitative EDA plots suitable for ICSME Data Showcase track."""
    import subprocess
    from pathlib import Path

    eda_script = Path(__file__).parent / "eda" / "quantitative_eda.py"
    cmd = [
        sys.executable,
        str(eda_script),
        "--db",
        args.db,
        "--out",
        args.out,
    ]
    if args.show:
        cmd.append("--show")

    result = subprocess.run(cmd, cwd=str(Path(__file__).parent))
    sys.exit(result.returncode)


def cmd_qualitative_eda(args: argparse.Namespace) -> None:
    """Generate qualitative exploratory data analysis plots."""
    """Generate qualitative EDA plots for internal analysis only."""
    import subprocess
    from pathlib import Path

    eda_script = Path(__file__).parent / "eda" / "qualitative_eda.py"
    cmd = [
        sys.executable,
        str(eda_script),
        "--db",
        args.db,
        "--out",
        args.out,
    ]
    if args.show:
        cmd.append("--show")

    result = subprocess.run(cmd, cwd=str(Path(__file__).parent))
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fixture corpus collection pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    sub.add_parser("init", help="Initialise the database")

    # load
    p_load = sub.add_parser("load", help="Load repos from SEART-GHS CSV files")
    p_load.add_argument(
        "--language",
        choices=list(LANGUAGE_CONFIGS),
        help="Limit to one language (default: all)",
    )

    # clone
    p_clone = sub.add_parser("clone", help="Clone discovered repos")
    p_clone.add_argument("--language", choices=list(LANGUAGE_CONFIGS))
    p_clone.add_argument(
        "--batch",
        type=int,
        default=CLONE_BATCH_SIZE,
        help="Max repos to clone in this run",
    )

    # extract
    p_extract = sub.add_parser("extract", help="Extract fixtures from cloned repos")
    p_extract.add_argument("--language", choices=list(LANGUAGE_CONFIGS))

    # run
    p_run = sub.add_parser("run", help="Run full pipeline end-to-end")
    p_run.add_argument(
        "--language", choices=list(LANGUAGE_CONFIGS), help="Limit to one language"
    )
    p_run.add_argument(
        "--max", type=int, default=None, help="Max repos per language to load"
    )

    # toy
    p_toy = sub.add_parser(
        "toy", help="Build toy dataset (10 repos per language) for quick validation"
    )
    p_toy.add_argument(
        "--language",
        choices=list(LANGUAGE_CONFIGS),
        help="Limit to one language (default: all languages)",
    )

    # full
    p_full = sub.add_parser(
        "full",
        help="Build full production dataset (500 repos per language) with balanced collection",
    )
    p_full.add_argument(
        "--language",
        choices=list(LANGUAGE_CONFIGS),
        help="Limit to one language (default: all languages)",
    )

    # collect

    # cleanup
    p_cleanup = sub.add_parser(
        "cleanup", help="Remove stale clone directories from interrupted runs"
    )
    p_cleanup.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything",
    )

    # cleanup-toy
    p_cleanup_toy = sub.add_parser(
        "cleanup-toy",
        help="Remove extracted repos beyond first 50 per language (keep toy dataset only)",
    )

    # classify
    p_classify = sub.add_parser("classify", help="Label repo domains (web/cli/data/…)")
    p_classify.add_argument(
        "--overwrite", action="store_true", help="Re-classify already-labelled repos"
    )

    # categorize
    p_categorize = sub.add_parser(
        "categorize",
        help="Categorize fixtures by usage pattern (data_builder/service_setup/…)",
    )
    p_categorize.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-categorize already-categorized fixtures",
    )

    # export
    p_export = sub.add_parser("export", help="Export dataset for Zenodo deposit")
    p_export.add_argument(
        "--version", default="1.0", help="Version string (default: 1.0)"
    )
    p_export.add_argument(
        "--include-source",
        action="store_true",
        help="Include raw_source column in fixtures CSV",
    )

    # validate
    p_validate = sub.add_parser(
        "validate", help="Sample fixtures for manual precision/recall validation"
    )
    p_validate.add_argument(
        "--sample",
        type=int,
        default=50,
        help="Fixtures to sample per language (default: 50)",
    )
    p_validate.add_argument(
        "--compute",
        metavar="CSV",
        help="Path to a completed validation CSV — compute metrics",
    )

    # stats
    sub.add_parser("stats", help="Print corpus statistics")

    # quantitative_eda
    p_quant_eda = sub.add_parser(
        "quantitative-eda",
        help="Generate quantitative EDA plots (ICSME Data Showcase track)",
    )
    p_quant_eda.add_argument(
        "--db",
        default="data/corpus.db",
        help="Path to database (default: data/corpus.db)",
    )
    p_quant_eda.add_argument(
        "--out",
        default="output/eda/quantitative",
        help="Base output directory for plots",
    )
    p_quant_eda.add_argument(
        "--show",
        action="store_true",
        help="Display plots interactively instead of saving",
    )

    # qualitative_eda
    p_qual_eda = sub.add_parser(
        "qualitative-eda",
        help="Generate qualitative EDA plots (internal analysis only)",
    )
    p_qual_eda.add_argument(
        "--db",
        default="data/corpus.db",
        help="Path to database (default: data/corpus.db)",
    )
    p_qual_eda.add_argument(
        "--out",
        default="output/eda/qualitative",
        help="Base output directory for plots",
    )
    p_qual_eda.add_argument(
        "--show",
        action="store_true",
        help="Display plots interactively instead of saving",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMAND_MAP = {
    "init": cmd_init,
    "load": cmd_load,
    "clone": cmd_clone,
    "extract": cmd_extract,
    "cleanup": cmd_cleanup,
    "cleanup-toy": cmd_cleanup_toy,
    "classify": cmd_classify,
    "categorize": cmd_categorize,
    "export": cmd_export,
    "validate": cmd_validate,
    "run": cmd_run,
    "toy": cmd_toy,
    "full": cmd_full,
    "stats": cmd_stats,
    "quantitative-eda": cmd_quantitative_eda,
    "qualitative-eda": cmd_qualitative_eda,
}

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    COMMAND_MAP[args.command](args)
