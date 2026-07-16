"""
Agent commit counter

For each repository marked `has_agent_config` in the selected `*_repo.csv` input directory,
this script clones the repository using the shared commit-scan clone helper,
scans the git history for agent commits using the shared collection logic, and writes
one CSV per language containing one row per detected agent commit.

Output per-language CSV columns (one row per agent commit):
- `repo_name` — owner/repo
- `commit_sha` — full commit SHA
- `commit_url` — GitHub web URL for the specific commit
- `agent_type` — detected agent type token (e.g., copilot, claude) if available
- `commit_date` — commit date (ISO 8601)
- `author_name` — commit author name
- `author_email` — commit author email
- `language` — repo language (from the QC CSV)
- `clone_url` — repository clone URL
- `processed_at` — when this row was written (ISO 8601 UTC)

This script skips commits already written in existing per-language CSVs so it can be resumed.
Temporary clones are deleted in a `finally` block immediately after each repo is processed.
It only reads repositories marked `has_agent_config` in the repo-counter CSV output.
By default the clone is blob-limited so large file contents are not downloaded; commit history remains complete.
"""

import concurrent.futures
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

import os

from collection import paths
from collection.agent_corpus import get_agent_commits
from collection.agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES
from collection.cli_utils import add_output_dir_arg, add_since_arg, add_workers_arg
from collection.csv_adapter import get_adapter
from collection.ephemeral_clone import temp_clone_commit_history

# Defaults, resolved through the central path registry (collection.paths).
# Not created at import time -- `run()` creates `output_dir` once it knows
# the real value, so importing this module for a toy run never touches the
# real datasets/ tree.
GITHUB_SEARCH_AGENT_DIR = paths.stage_dir("a", "repos")
OUTPUT_DIR = paths.stage_dir("a", "commits")

from collection.logging_utils import get_logger

logger = get_logger(__name__)


def read_config_positive_rows(input_dir: Path = GITHUB_SEARCH_AGENT_DIR) -> list[dict]:
    """Load repo rows flagged `has_agent_config` from `*_repo.csv` files in `input_dir`."""
    rows = []
    repo_csv_paths = sorted(
        input_dir.glob("*_repo.csv"), key=lambda path: path.name
    )

    for fp in repo_csv_paths:
        with fp.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                language = (
                    (r.get("language") or r.get("source_language") or "")
                    .strip()
                    .lower()
                )
                if language not in PAPER_AGENT_REPOSITORY_LANGUAGES:
                    continue
                if str(r.get("has_agent_config") or "").strip() in (
                    "1",
                    "True",
                    "true",
                ):
                    rows.append(r)
    return rows


def load_seen_commits_for_language(lang: str, output_dir: Path = OUTPUT_DIR) -> set:
    """Return commit SHAs already written to *lang*'s output CSV, for resuming."""
    csv_path = output_dir / f"{lang.lower()}_commit.csv"
    seen = set()
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for r in reader:
                    sha = (r.get("commit_sha") or "").strip()
                    if sha:
                        seen.add(sha)
        except Exception:
            pass
    return seen


def write_commit_rows(rows: list[dict], output_dir: Path = OUTPUT_DIR) -> None:
    """Append *rows* to their per-language output CSV and write a JSON checkpoint."""
    # rows may contain multiple languages; group by language
    by_lang: dict[str, list[dict]] = {}
    for r in rows:
        lang = (r.get("language") or "unknown").lower()
        by_lang.setdefault(lang, []).append(r)

    for lang, items in by_lang.items():
        csv_path = output_dir / f"{lang}_commit.csv"
        fieldnames = [
            "repo_name",
            "commit_sha",
            "commit_url",
            "agent_type",
            "commit_date",
            "author_name",
            "author_email",
            "language",
            "clone_url",
            "processed_at",
        ]
        logger.debug(
            "Writing %d commit rows for language=%s to %s", len(items), lang, csv_path
        )
        # Append rows and fsync to make progress durable for checkpoints
        try:
            get_adapter().append_dicts(csv_path, items, fieldnames, fsync=True)
        except OSError:
            # Best-effort durability; failures shouldn't abort the whole run
            logger.exception("Failed to fsync %s", csv_path)

        # Write a small JSON checkpoint to record progress and allow fast inspection
        try:
            checkpoint = {
                "language": lang,
                "rows_written": len(items),
                "last_written_at": datetime.now(timezone.utc).isoformat(),
            }
            cp_path = output_dir / f"{lang}_commit.checkpoint.json"
            with cp_path.open("w", encoding="utf-8") as cfh:
                json.dump(checkpoint, cfh)
                cfh.flush()
                try:
                    os.fsync(cfh.fileno())
                except Exception:
                    logger.exception("Failed to fsync checkpoint %s", cp_path)
        except Exception:
            logger.exception("Failed to write checkpoint for language=%s", lang)


def process_repo_for_commits(row: dict, since: str) -> tuple[list[dict], int]:
    """Temp-clone the repo in *row* and return (agent commits, total commits
    examined) since *since*. The total counts every commit the scan looked
    at in the date window -- agent, human, and bot alike -- not just the
    agent-matched ones returned in the first element."""
    full_name = (row.get("repo_name") or "").strip()
    clone_url = row.get("clone_url") or f"https://github.com/{full_name}.git"
    lang = (row.get("language") or "unknown").strip().lower()
    if not full_name:
        return [], 0
    clone_args = [
        "--filter=blob:limit=10m",
        "--single-branch",
        "--no-tags",
        "--no-checkout",
    ]
    logger.debug("Cloning %s (lang=%s) args=%s", full_name, lang, clone_args)
    out_rows = []
    with temp_clone_commit_history(
        clone_url, full_name, prefix="agent-commits-", timeout=300
    ) as repo_path:
        if repo_path is None:
            logger.warning("Clone failed for %s (clone_url=%s)", full_name, clone_url)
            return [], 0

        if repo_path and repo_path.exists():
            commits, total_examined = get_agent_commits(repo_path, since)
            logger.debug(
                "Found %d candidate agent commits in %s (of %d examined)",
                len(commits),
                full_name,
                total_examined,
            )
            for c in commits:
                commit_sha = c.get("commit_sha")
                out_rows.append(
                    {
                        "repo_name": full_name,
                        "commit_sha": commit_sha,
                        "commit_url": (
                            f"https://github.com/{full_name}/commit/{commit_sha}"
                            if full_name and commit_sha
                            else ""
                        ),
                        "agent_type": c.get("agent_type"),
                        "commit_date": c.get("commit_date"),
                        "author_name": c.get("author_name", ""),
                        "author_email": c.get("author_email", ""),
                        "language": lang,
                        "clone_url": clone_url,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
        else:
            return out_rows, 0

    return out_rows, total_examined


def write_commit_scan_totals(
    commits_scanned_by_lang: dict[str, int], output_dir: Path = OUTPUT_DIR
) -> None:
    """Write the per-language "total commits examined" summary as a
    human-readable summary.md sibling to the per-language commit CSVs --
    counts agent, human, and bot commits alike, not just the agent-attributed
    rows already present in those CSVs. Plain markdown rather than JSON: this
    number only ever needs to be read by a person (filling in or checking the
    paper's results table), not parsed by another pipeline stage. Overwritten
    on every call, safe to refresh mid-run for visibility into a killed/
    still-running collection."""
    summary_path = output_dir / "summary.md"
    lines = [
        "# Dataset A -- commit scan summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        '"Total commits scanned" counts every commit examined in the '
        "collection window (agent, human, and bot alike) -- not just the "
        "agent-attributed rows already present in the per-language commit "
        "CSVs in this directory.",
        "",
        "| Language | Total commits scanned |",
        "|---|---:|",
    ]
    for lang, total in sorted(commits_scanned_by_lang.items()):
        lines.append(f"| {lang} | {total:,} |")
    lines.append("")
    try:
        summary_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        logger.exception("Failed to write %s", summary_path)


def run(
    since: str = "2025-01-01",
    workers: int = 4,
    input_dir: Path = GITHUB_SEARCH_AGENT_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> int:
    """Scan all config-positive repos for agent commits and write per-language CSVs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = read_config_positive_rows(input_dir)
    logger.info("Found %d config-positive repos", len(candidates))
    if not candidates:
        print(f"No config-positive repos found in {input_dir}")
        return 0

    # Deduplicate by repo_name, keep first occurrence
    seen = set()
    unique = []
    for r in candidates:
        name = (r.get("repo_name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(r)

    logger.info("%d unique repos to process after deduplication", len(unique))

    # Preload per-language seen commit SHAs for resume-safety
    lang_seen = {}
    for r in unique:
        lang = (r.get("language") or "unknown").strip().lower()
        if lang not in lang_seen:
            lang_seen[lang] = load_seen_commits_for_language(lang, output_dir)

    workers = max(1, int(workers or 1))
    processed_count = 0
    commits_found = 0
    commits_scanned_by_lang: dict[str, int] = defaultdict(int)
    logger.info("Starting processing with %d workers", workers)
    if workers == 1:
        with tqdm(total=len(unique), desc="discover-commits", unit="repo") as pbar:
            for r in unique:
                lang = (r.get("language") or "unknown").strip().lower()
                logger.debug(
                    "Processing (sync) %s (lang=%s)", (r.get("repo_name") or ""), lang
                )
                rows, total_examined = process_repo_for_commits(r, since)
                commits_scanned_by_lang[lang] += total_examined
                # filter out seen shas
                new_rows = [
                    rr
                    for rr in rows
                    if rr.get("commit_sha") not in lang_seen.get(lang, set())
                ]
                if new_rows:
                    write_commit_rows(new_rows, output_dir)
                    # update seen set
                    lang_seen.setdefault(lang, set()).update(
                        [rr.get("commit_sha") for rr in new_rows if rr.get("commit_sha")]
                    )
                    commits_found += len(new_rows)
                    logger.debug(
                        "Wrote %d new commit rows for %s",
                        len(new_rows),
                        (r.get("repo_name") or ""),
                    )
                processed_count += 1
                pbar.set_postfix(commits=commits_found)
                pbar.update(1)
                if processed_count % 50 == 0:
                    write_commit_scan_totals(commits_scanned_by_lang, output_dir)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(process_repo_for_commits, r, since): r for r in unique}
            logger.info("Submitted %d tasks to executor", len(futures))
            with tqdm(total=len(futures), desc="discover-commits", unit="repo") as pbar:
                for fut in concurrent.futures.as_completed(futures):
                    src = futures[fut]
                    lang = (src.get("language") or "unknown").strip().lower()
                    try:
                        rows, total_examined = fut.result()
                    except Exception as e:
                        logger.exception(
                            "Error processing %s: %s", src.get("repo_name"), e
                        )
                        pbar.update(1)
                        continue
                    commits_scanned_by_lang[lang] += total_examined
                    new_rows = [
                        rr
                        for rr in rows
                        if rr.get("commit_sha") not in lang_seen.get(lang, set())
                    ]
                    if new_rows:
                        write_commit_rows(new_rows, output_dir)
                        lang_seen.setdefault(lang, set()).update(
                            [
                                rr.get("commit_sha")
                                for rr in new_rows
                                if rr.get("commit_sha")
                            ]
                        )
                        commits_found += len(new_rows)
                        logger.debug(
                            "Wrote %d new commit rows for %s",
                            len(new_rows),
                            src.get("repo_name"),
                        )
                    processed_count += 1
                    pbar.set_postfix(commits=commits_found)
                    pbar.update(1)
                    if processed_count % 50 == 0:
                        write_commit_scan_totals(commits_scanned_by_lang, output_dir)

    write_commit_scan_totals(commits_scanned_by_lang, output_dir)
    print(
        f"Processed {processed_count} config-positive repos; per-language commit CSVs "
        f"stored in {output_dir}; commit scan totals: {dict(commits_scanned_by_lang)}"
    )
    return 0


def main():
    """CLI entrypoint: scan config-positive repos and write agent-commit CSVs."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Full-history agent-commit counter for config-positive repos"
    )
    add_since_arg(parser, help_text="Since date for agent commits")
    add_workers_arg(parser, default=4, help_text="Parallel workers")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=GITHUB_SEARCH_AGENT_DIR,
        help="Directory containing *_repo.csv files",
    )
    add_output_dir_arg(
        parser,
        default=OUTPUT_DIR,
        help_text="Directory to write *_commit.csv files",
    )
    args = parser.parse_args()

    raise SystemExit(
        run(
            since=args.since,
            workers=args.workers,
            input_dir=Path(args.input_dir),
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    from collection.logging_utils import configure_logging

    configure_logging()
    main()
