"""
Agent commit counter

For each repository marked `has_agent_config` in the selected `*_agent_repo.csv` input directory,
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

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import concurrent.futures

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from collection.agent_corpus import get_agent_commits
from collection.agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES
from collection.clone_manager import temp_clone_commit_history
import os
import json

GITHUB_SEARCH_AGENT_DIR = PROJECT_ROOT / "github-search-agent" / "agent_repositories"
# Default output dir for agent commit CSVs (per-language)
OUTPUT_DIR = PROJECT_ROOT / "github-search-agent" / "agent_commits"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def read_config_positive_rows() -> list[dict]:
    rows = []
    repo_csv_paths = sorted(
        GITHUB_SEARCH_AGENT_DIR.glob("*_agent_repo.csv"), key=lambda path: path.name
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


def load_seen_commits_for_language(lang: str) -> set:
    csv_path = OUTPUT_DIR / f"{lang.lower()}_agent_commit.csv"
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


def write_commit_rows(rows: list[dict]) -> None:
    # rows may contain multiple languages; group by language
    by_lang = {}
    for r in rows:
        lang = (r.get("language") or "unknown").lower()
        by_lang.setdefault(lang, []).append(r)

    for lang, items in by_lang.items():
        csv_path = OUTPUT_DIR / f"{lang}_agent_commit.csv"
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
        logger.info(
            "Writing %d commit rows for language=%s to %s", len(items), lang, csv_path
        )
        # Ensure header exists
        if not csv_path.exists():
            with csv_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()

        # Append rows and fsync to make progress durable for checkpoints
        with csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            for it in items:
                writer.writerow({k: it.get(k, "") for k in fieldnames})
            try:
                fh.flush()
                os.fsync(fh.fileno())
            except Exception:
                # Best-effort durability; failures shouldn't abort the whole run
                logger.exception("Failed to fsync %s", csv_path)

        # Write a small JSON checkpoint to record progress and allow fast inspection
        try:
            checkpoint = {
                "language": lang,
                "rows_written": len(items),
                "last_written_at": datetime.now(timezone.utc).isoformat(),
            }
            cp_path = OUTPUT_DIR / f"{lang}_agent_commit.checkpoint.json"
            with cp_path.open("w", encoding="utf-8") as cfh:
                json.dump(checkpoint, cfh)
                cfh.flush()
                try:
                    os.fsync(cfh.fileno())
                except Exception:
                    logger.exception("Failed to fsync checkpoint %s", cp_path)
        except Exception:
            logger.exception("Failed to write checkpoint for language=%s", lang)


def process_repo_for_commits(row: dict, since: str) -> list[dict]:
    full_name = (row.get("repo_name") or "").strip()
    clone_url = row.get("clone_url") or f"https://github.com/{full_name}.git"
    lang = (row.get("language") or "unknown").strip().lower()
    if not full_name:
        return []
    clone_args = [
        "--filter=blob:limit=10m",
        "--single-branch",
        "--no-tags",
        "--no-checkout",
    ]
    logger.info("Cloning %s (lang=%s) args=%s", full_name, lang, clone_args)
    out_rows = []
    with temp_clone_commit_history(clone_url, full_name, prefix="agent-commit-qc-", timeout=300) as repo_path:
        if repo_path is None:
            logger.warning("Clone failed for %s (clone_url=%s)", full_name, clone_url)
            return []

        if repo_path and repo_path.exists():
            commits = get_agent_commits(repo_path, since)
            logger.info(
                "Found %d candidate agent commits in %s", len(commits), full_name
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

    return out_rows


def run(since: str = "2025-01-01", workers: int = 4) -> int:
    candidates = read_config_positive_rows()
    logger.info("Found %d config-positive repos", len(candidates))
    if not candidates:
        print(f"No config-positive repos found in {GITHUB_SEARCH_AGENT_DIR}")
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
            lang_seen[lang] = load_seen_commits_for_language(lang)

    workers = max(1, int(workers or 1))
    processed_count = 0
    logger.info("Starting processing with %d workers", workers)
    if workers == 1:
        for r in unique:
            lang = (r.get("language") or "unknown").strip().lower()
            logger.info(
                "Processing (sync) %s (lang=%s)", (r.get("repo_name") or ""), lang
            )
            rows = process_repo_for_commits(r, since)
            # filter out seen shas
            new_rows = [
                rr
                for rr in rows
                if rr.get("commit_sha") not in lang_seen.get(lang, set())
            ]
            if new_rows:
                write_commit_rows(new_rows)
                # update seen set
                lang_seen.setdefault(lang, set()).update(
                    [rr.get("commit_sha") for rr in new_rows if rr.get("commit_sha")]
                )
                logger.info(
                    "Wrote %d new commit rows for %s",
                    len(new_rows),
                    (r.get("repo_name") or ""),
                )
            processed_count += 1
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(process_repo_for_commits, r, since): r for r in unique}
            logger.info("Submitted %d tasks to executor", len(futures))
            for fut in concurrent.futures.as_completed(futures):
                src = futures[fut]
                lang = (src.get("language") or "unknown").strip().lower()
                try:
                    rows = fut.result()
                except Exception as e:
                    logger.exception("Error processing %s: %s", src.get("repo_name"), e)
                    continue
                new_rows = [
                    rr
                    for rr in rows
                    if rr.get("commit_sha") not in lang_seen.get(lang, set())
                ]
                if new_rows:
                    write_commit_rows(new_rows)
                    lang_seen.setdefault(lang, set()).update(
                        [
                            rr.get("commit_sha")
                            for rr in new_rows
                            if rr.get("commit_sha")
                        ]
                    )
                    logger.info(
                        "Wrote %d new commit rows for %s",
                        len(new_rows),
                        src.get("repo_name"),
                    )
                processed_count += 1

    print(
        f"Processed {processed_count} config-positive repos; per-language commit CSVs stored in {OUTPUT_DIR}"
    )
    return 0


def main():
    import argparse

    global GITHUB_SEARCH_AGENT_DIR, OUTPUT_DIR

    parser = argparse.ArgumentParser(
        description="Full-history agent-commit counter for config-positive repos"
    )
    parser.add_argument(
        "--since", type=str, default="2025-01-01", help="Since date for agent commits"
    )
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=GITHUB_SEARCH_AGENT_DIR,
        help="Directory containing *_agent_repo.csv files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory to write *_agent_commit_qc.csv files",
    )
    args = parser.parse_args()

    GITHUB_SEARCH_AGENT_DIR = Path(args.input_dir)
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raise SystemExit(run(since=args.since, workers=args.workers))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
