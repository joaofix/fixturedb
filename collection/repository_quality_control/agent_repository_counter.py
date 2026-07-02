"""
Preliminary repository counter (previously agent_repo_preliminar_quality_control.py)

Scans `github-search-raw` result files, shallow-clones each candidate, detects whether
an agent configuration file exists in the latest tree, and writes per-language
CSV rows with the repository metadata and `has_agent_config` flag.
"""

import concurrent.futures
import csv
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from collection.agent_corpus import scan_cloned_repo_for_agent_configs
from collection.agent_patterns import (
    PAPER_AGENT_REPOSITORY_LANGUAGES,
)
from collection.clone_manager import temp_clone_commit_history
from collection.config import EXCLUSION_KEYWORDS
from collection.logging_utils import get_logger
from collection.utils import _normalize_language_filters

logger = get_logger(__name__)

GITHUB_SEARCH_RAW_DIR = PROJECT_ROOT / "github-search-raw"
OUTPUT_DIR = PROJECT_ROOT / "github-search-agent" / "agent_repositories"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def csv_path_for_language(language: str) -> Path:
    lang = (language or "unknown").lower()
    return OUTPUT_DIR / f"{lang}_agent_repo.csv"


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


def _collect_result_files(
    results_dir: Path, allowed_languages: Optional[list[str]] = None
) -> list[Path]:
    """Pick one raw input file per language, preferring compressed CSV exports."""
    preferred_order = [".csv.gz", ".csv", ".json.gz", ".json", ".txt", ".list"]
    files_by_base: dict[str, list[Path]] = {}
    allowed = {lang.lower() for lang in (allowed_languages or []) if lang}

    if not results_dir.exists() or not results_dir.is_dir():
        return []

    for f in sorted(results_dir.iterdir()):
        if f.is_dir() or f.name == "details.txt":
            continue

        base = f.name
        for suffix in (".csv.gz", ".json.gz"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        else:
            base = f.stem

        files_by_base.setdefault(base, []).append(f)

    chosen_files = []
    for _base, flist in files_by_base.items():
        pick = None
        for pref in preferred_order:
            for f in flist:
                if f.name.endswith(pref):
                    if allowed:
                        language = _language_from_raw_filename(f.name)
                        if language and language not in allowed:
                            continue
                    pick = f
                    break
            if pick:
                break
        if not pick:
            pick = flist[0]
            if allowed:
                language = _language_from_raw_filename(pick.name)
                if language and language not in allowed:
                    continue
        chosen_files.append(pick)

    return chosen_files


def _read_repos_from_files(
    files: list[Path], allowed_languages: Optional[list[str]] = None
) -> List[dict]:
    """Read repositories from SEART result files (CSV/JSON)."""
    repos: list[dict] = []
    allowed = {lang.lower() for lang in (allowed_languages or []) if lang}

    for f in files:
        source_language = _language_from_results_filename(f.name)
        if not source_language:
            source_language = _language_from_raw_filename(f.name)
        if allowed and source_language and source_language not in allowed:
            continue
        if source_language and source_language not in PAPER_AGENT_REPOSITORY_LANGUAGES:
            continue
        try:
            if f.name.endswith(".csv.gz"):
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


def _language_from_results_filename(file_name: str) -> str:
    if "-results." not in file_name:
        return ""
    return file_name.split("-results.", 1)[0].strip().lower()


def _language_from_raw_filename(file_name: str) -> str:
    if file_name.endswith(".csv.gz"):
        return file_name[:-7].strip().lower()
    if file_name.endswith(".csv"):
        return file_name[:-4].strip().lower()
    if file_name.endswith(".json.gz"):
        return file_name[:-8].strip().lower()
    if file_name.endswith(".json"):
        return file_name[:-5].strip().lower()
    return ""


def read_repo_list(
    languages: Optional[list[str]] = None, language: Optional[str] = None
) -> List[dict]:
    """Read candidate repos from github-search-raw."""
    selected_languages = _normalize_language_filters(languages, language)
    files_raw = _collect_result_files(GITHUB_SEARCH_RAW_DIR, selected_languages)
    repos = _read_repos_from_files(files_raw, selected_languages)
    if selected_languages:
        logger.info(
            "Loaded %d repo candidates from %s for languages=%s",
            len(repos),
            GITHUB_SEARCH_RAW_DIR,
            ",".join(selected_languages),
        )
    else:
        logger.info(
            "Loaded %d repo candidates from %s", len(repos), GITHUB_SEARCH_RAW_DIR
        )
    return repos


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
        has_agent_config = False
        qc_reason = ""

        with temp_clone_commit_history(
            clone_url, full_name, prefix="agent-repos-", timeout=60
        ) as repo_path:
            try:
                if repo_path and repo_path.exists():
                    has_agent_config = scan_cloned_repo_for_agent_configs(repo_path)
                    if not has_agent_config:
                        qc_reason = "no_agent_config"
                else:
                    qc_reason = "clone_failed_or_missing"
            except Exception:
                qc_reason = "clone_failed_or_missing"

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


def run(
    limit: int = 0,
    since: str = "2025-01-01",
    workers: int = 8,
    languages: Optional[list[str]] = None,
    language: Optional[str] = None,
) -> int:
    repos = read_repo_list(languages=languages, language=language)
    if not repos:
        print("No repos found in github-search-raw.")
        return 0
    limit = int(limit or 0)

    to_process = []
    for entry in repos:
        if limit and len(to_process) >= limit:
            break
        to_process.append(entry)

    if not to_process:
        print("No repos to process.")
        return 0

    write_lock = threading.Lock()

    def write_row(row: dict) -> None:
        csv_path = csv_path_for_language(row.get("language") or "unknown")
        with write_lock:
            file_exists = csv_path.exists()
            with csv_path.open("a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
                fh.flush()

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

    global GITHUB_SEARCH_RAW_DIR, OUTPUT_DIR

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
        "--since", type=str, default="2025-01-01", help="Since date for agent commits"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of worker threads for parallel processing",
    )
    parser.add_argument(
        "--language",
        choices=sorted(PAPER_AGENT_REPOSITORY_LANGUAGES),
        help="Limit processing to a single language",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=sorted(PAPER_AGENT_REPOSITORY_LANGUAGES),
        help="Limit processing to one or more languages",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=GITHUB_SEARCH_RAW_DIR,
        help="Directory containing github-search-raw result files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory where *_agent_repo.csv files are stored",
    )
    args = parser.parse_args()

    GITHUB_SEARCH_RAW_DIR = Path(args.source_dir)
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    selected_languages = []
    if args.language:
        selected_languages.append(args.language)
    if args.languages:
        selected_languages.extend(args.languages)

    raise SystemExit(
        run(
            limit=args.limit,
            since=args.since,
            workers=args.workers,
            languages=selected_languages or None,
        )
    )


if __name__ == "__main__":
    # Configure logging via collection.logging_utils.configure_logging()
    from collection.logging_utils import configure_logging

    configure_logging()
    main()
