"""
Preliminary repository counter (previously agent_repo_preliminar_quality_control.py)

Scans `github-search` result files, shallow-clones each candidate, detects whether
an agent configuration file exists in the latest tree, and writes per-language
CSV rows with the repository metadata and `has_agent_config` flag.

Progress is saved atomically to `qc_progress.json` in the selected output directory so runs are resumable.
"""

import csv
import json
import logging
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
import concurrent.futures

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from collection.agent_corpus import scan_cloned_repo_for_agent_configs
from collection.config import EXCLUSION_KEYWORDS
from collection.agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES
from collection.temp_clone import cleanup_tempdir, clone_to_tempdir

logger = logging.getLogger(__name__)

GITHUB_SEARCH_DIR = PROJECT_ROOT / "github-search"
REPOSITORIES_SOURCE_500_DIR = GITHUB_SEARCH_DIR / "repositories-source-500-stars"
REPOSITORIES_SOURCE_100_DIR = GITHUB_SEARCH_DIR / "repositories-source-100-stars"
OUTPUT_DIR = GITHUB_SEARCH_DIR / "agent-activity-100-stars"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS_PATH = OUTPUT_DIR / "qc_progress.json"


def csv_path_for_language(language: str) -> Path:
    lang = (language or "unknown").lower()
    return OUTPUT_DIR / f"{lang}_agent_repo_qc.csv"


def _to_int(value: object) -> int:
    try:
        if value is None:
            return 0
        s = str(value).strip()
        if not s:
            return 0
        return int(float(s))
    except Exception:
        return 0


def _has_exclusion_keyword(text: str) -> bool:
    lowered = (text or "").casefold()
    return any(keyword.casefold() in lowered for keyword in EXCLUSION_KEYWORDS)


def _collect_result_files(results_dir: Path) -> list[Path]:
    """Pick one results file per language base, preferring CSV over JSON."""
    preferred_order = [
        "-results.csv.gz",
        "-results.csv",
        "-results.json.gz",
        "-results.json",
    ]
    files_by_base: dict[str, list[Path]] = {}

    if not results_dir.exists() or not results_dir.is_dir():
        return []

    for f in sorted(results_dir.iterdir()):
        if f.is_dir():
            continue
        if "-results." in f.name:
            base = f.name.split("-results.", 1)[0]
            files_by_base.setdefault(base, []).append(f)

    chosen_files = []
    for _base, flist in files_by_base.items():
        pick = None
        for pref in preferred_order:
            for f in flist:
                if f.name.endswith(pref):
                    pick = f
                    break
            if pick:
                break
        if not pick:
            pick = flist[0]
        chosen_files.append(pick)

    return chosen_files


def _read_repos_from_files(files: list[Path]) -> List[dict]:
    """Read repositories from SEART result files (CSV/JSON)."""
    repos: list[dict] = []

    for f in files:
        source_language = _language_from_results_filename(f.name)
        if source_language and source_language not in PAPER_AGENT_REPOSITORY_LANGUAGES:
            continue
        try:
            if f.name.endswith("-results.csv.gz"):
                import gzip

                with gzip.open(f, "rt", errors="ignore") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        name = (row.get("name") or row.get("full_name") or "").strip()
                        if not name or "/" not in name:
                            continue
                        description = (row.get("description") or "").strip()
                        if _has_exclusion_keyword(name) or _has_exclusion_keyword(
                            description
                        ):
                            continue
                        lang = (
                            row.get("mainLanguage")
                            or row.get("language")
                            or source_language
                            or ""
                        )
                        lang = (lang or "").lower()
                        if lang not in PAPER_AGENT_REPOSITORY_LANGUAGES:
                            continue
                        stars = row.get("stargazers") or row.get("watchers") or 0
                        contributors = row.get("contributors") or 0
                        repos.append(
                            {
                                "full_name": name,
                                "language": lang,
                                "source_language": source_language,
                                "clone_url": f"https://github.com/{name}.git",
                                "stars": _to_int(stars),
                                "num_contributors": _to_int(contributors),
                            }
                        )
            elif f.suffix in (".txt", ".list"):
                for line in f.read_text(errors="ignore").splitlines():
                    s = line.strip()
                    if s and "/" in s and not _has_exclusion_keyword(s):
                        if source_language not in PAPER_AGENT_REPOSITORY_LANGUAGES:
                            continue
                        repos.append(
                            {"full_name": s, "source_language": source_language}
                        )
            elif f.suffix == ".json" or f.name.endswith(".json.gz"):
                if f.suffix == ".gz" or f.name.endswith(".json.gz"):
                    import gzip

                    with gzip.open(f, "rt", errors="ignore") as fh:
                        data = json.load(fh)
                else:
                    data = json.loads(f.read_text(errors="ignore"))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, str) and "/" in item:
                            if _has_exclusion_keyword(item):
                                continue
                            if source_language not in PAPER_AGENT_REPOSITORY_LANGUAGES:
                                continue
                            repos.append(
                                {"full_name": item, "source_language": source_language}
                            )
                        elif isinstance(item, dict):
                            val = item.get("full_name") or item.get("name")
                            if val and "/" in val:
                                description = (item.get("description") or "").strip()
                                if _has_exclusion_keyword(
                                    val
                                ) or _has_exclusion_keyword(description):
                                    continue
                                if (
                                    source_language
                                    not in PAPER_AGENT_REPOSITORY_LANGUAGES
                                ):
                                    continue
                                repos.append(
                                    {
                                        "full_name": val,
                                        "source_language": source_language,
                                    }
                                )
                elif isinstance(data, dict) and "items" in data:
                    for item in data.get("items", []):
                        repo = item.get("repository") or item
                        if isinstance(repo, dict):
                            val = repo.get("full_name") or repo.get("name")
                            if val and "/" in val:
                                description = (repo.get("description") or "").strip()
                                if _has_exclusion_keyword(
                                    val
                                ) or _has_exclusion_keyword(description):
                                    continue
                                if (
                                    source_language
                                    not in PAPER_AGENT_REPOSITORY_LANGUAGES
                                ):
                                    continue
                                repos.append(
                                    {
                                        "full_name": val,
                                        "source_language": source_language,
                                    }
                                )
        except Exception:
            continue

    return repos


def save_progress(progress: dict) -> None:
    try:
        PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = PROGRESS_PATH.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(progress, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, PROGRESS_PATH)
    except Exception:
        logger.debug("Failed to save progress")


def _rebuild_progress_from_csvs() -> dict:
    processed = {}
    for csv_path in OUTPUT_DIR.glob("*_agent_repo_qc.csv"):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    repo_name = (row.get("repo_name") or "").strip()
                    if not repo_name:
                        continue
                    processed[repo_name] = {
                        "language": (row.get("language") or "").strip() or "unknown",
                        "qc_reason": (row.get("qc_reason") or "").strip(),
                    }
        except Exception:
            continue
    return {"processed": processed}


def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        try:
            return json.loads(PROGRESS_PATH.read_text())
        except Exception:
            rebuilt = _rebuild_progress_from_csvs()
            save_progress(rebuilt)
            return rebuilt
    return {}


def _language_from_results_filename(file_name: str) -> str:
    if "-results." not in file_name:
        return ""
    return file_name.split("-results.", 1)[0].strip().lower()


def read_repo_list() -> List[dict]:
    """Read candidate repos from the refactored github-search directory.

    The 100-star candidate set is built as:
      1) all repositories from the 500-star source folder
      2) plus only the additional repositories from the 100-star source folder
         with 100 <= stars < 500

    This guarantees we leverage the existing 500-star search results while
    extending coverage only in the missing star range.
    """
    files_500 = _collect_result_files(REPOSITORIES_SOURCE_500_DIR)
    files_100 = _collect_result_files(REPOSITORIES_SOURCE_100_DIR)

    # Backward-compatibility for legacy flat layout under github-search/
    if not files_500 and not files_100:
        files_500 = _collect_result_files(GITHUB_SEARCH_DIR)

    repos_500 = _read_repos_from_files(files_500)
    repos_100 = _read_repos_from_files(files_100)

    by_name: dict[str, dict] = {}
    ordered: list[dict] = []

    # Keep all 500+ repos as baseline.
    for repo in repos_500:
        name = (repo.get("full_name") or "").strip()
        if not name or name in by_name:
            continue
        by_name[name] = repo
        ordered.append(repo)

    added_low_star = 0
    # Append only the missing 100-499 repos from the broader 100-star export.
    for repo in repos_100:
        name = (repo.get("full_name") or "").strip()
        if not name or name in by_name:
            continue
        stars = _to_int(repo.get("stars"))
        if stars < 100 or stars >= 500:
            continue
        by_name[name] = repo
        ordered.append(repo)
        added_low_star += 1

    logger.info(
        "Loaded repo candidates using merged star tiers: baseline_500=%d, added_100_499=%d, total=%d",
        len(repos_500),
        added_low_star,
        len(ordered),
    )
    return ordered


def _process_single(entry: dict, since: str) -> Optional[dict]:
    full_name = entry.get("full_name")
    try:
        lang = (
            (entry.get("language") or entry.get("source_language") or "unknown")
            .strip()
            .lower()
        )
        meta = {
            "language": lang,
            "stars": int(entry.get("stars") or entry.get("stargazers") or 0),
            "clone_url": entry.get("clone_url")
            or f"https://github.com/{full_name}.git",
            "num_contributors": int(entry.get("num_contributors") or 0),
        }
        print(f"Processing {full_name} (lang={lang})")

        clone_url = meta.get("clone_url")
        repo_path = None
        temp_root = None
        if clone_url:
            clone_args = [
                "--depth=1",
                "--filter=blob:none",
                "--single-branch",
                "--no-tags",
            ]
            repo_path, temp_root = clone_to_tempdir(
                full_name,
                clone_url,
                clone_args,
                timeout=60,
                prefix="agent-qc-",
            )

        has_agent_config = False
        qc_reason = ""

        try:
            if repo_path and repo_path.exists():
                has_agent_config = scan_cloned_repo_for_agent_configs(repo_path)
                if not has_agent_config:
                    qc_reason = "no_agent_config"
            else:
                qc_reason = "clone_failed_or_missing"
        finally:
            cleanup_tempdir(temp_root)

        row = {
            "repo_name": full_name,
            "has_agent_config": int(bool(has_agent_config)),
            "language": meta.get("language"),
            "stars": meta.get("stars"),
            "clone_url": meta.get("clone_url"),
            "num_contributors": meta.get("num_contributors"),
            "qc_reason": qc_reason,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        return row
    except Exception as e:
        logger.debug(f"Error processing {full_name}: {e}")
        return None


def run(limit: int = 0, since: str = "2023-06-01", workers: int = 8) -> int:
    repos = read_repo_list()
    if not repos:
        print(
            "No repos found in github-search source folders (repositories-source-500-stars / repositories-source-100-stars)."
        )
        return 0
    limit = int(limit or 0)
    progress = load_progress()

    to_process = []
    seen_global = set(progress.get("processed", {}).keys())
    for entry in repos:
        if limit and len(to_process) >= limit:
            break
        full_name = entry.get("full_name")
        if full_name in seen_global:
            continue
        to_process.append(entry)

    if not to_process:
        print("No new repos to process (all skipped by progress).")
        return 0

    csv_headers_written = set()

    def write_row(row: dict) -> None:
        csv_path = csv_path_for_language(row.get("language") or "unknown")
        if csv_path not in csv_headers_written:
            if not csv_path.exists():
                with csv_path.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(
                        fh,
                        fieldnames=[
                            "repo_name",
                            "has_agent_config",
                            "language",
                            "stars",
                            "clone_url",
                            "num_contributors",
                            "qc_reason",
                            "processed_at",
                        ],
                    )
                    writer.writeheader()
            csv_headers_written.add(csv_path)

        with csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            writer.writerow(row)
            fh.flush()

        processed = progress.get("processed", {})
        processed[row["repo_name"]] = {
            "language": row.get("language"),
            "qc_reason": row.get("qc_reason", ""),
        }
        progress["processed"] = processed
        progress["last"] = {"repo": row["repo_name"]}
        save_progress(progress)

    workers = max(1, int(workers or 1))
    if workers == 1:
        count = 0
        for entry in to_process:
            res = _process_single(entry, since)
            if res:
                write_row(res)
                count += 1
        print(f"Processed {count} repos; CSVs stored in {OUTPUT_DIR}")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_process_single, entry, since) for entry in to_process]
            count = 0
            for fut in concurrent.futures.as_completed(futures):
                r = fut.result()
                if r:
                    write_row(r)
                    count += 1
        print(
            f"Processed {count} repos with {workers} workers; CSVs stored in {OUTPUT_DIR}"
        )
    return 0


def main():
    import argparse

    global REPOSITORIES_SOURCE_500_DIR, REPOSITORIES_SOURCE_100_DIR, OUTPUT_DIR, PROGRESS_PATH

    parser = argparse.ArgumentParser(
        description="Preliminary QC of agent candidate repos"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of repos to process (0 = all)",
    )
    parser.add_argument(
        "--since", type=str, default="2023-06-01", help="Since date for agent commits"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of worker threads for parallel processing",
    )
    parser.add_argument(
        "--source-500-dir",
        type=Path,
        default=REPOSITORIES_SOURCE_500_DIR,
        help="Directory containing 500-star SEART source files",
    )
    parser.add_argument(
        "--source-100-dir",
        type=Path,
        default=REPOSITORIES_SOURCE_100_DIR,
        help="Directory containing 100-star SEART source files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory where *_agent_repo_qc.csv and qc_progress.json are stored",
    )
    args = parser.parse_args()

    REPOSITORIES_SOURCE_500_DIR = Path(args.source_500_dir)
    REPOSITORIES_SOURCE_100_DIR = Path(args.source_100_dir)
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH = OUTPUT_DIR / "qc_progress.json"

    raise SystemExit(run(limit=args.limit, since=args.since, workers=args.workers))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
