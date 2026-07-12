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

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from collection import paths
from collection.agent_corpus import scan_cloned_repo_for_agent_configs
from collection.agent_patterns import (
    PAPER_AGENT_REPOSITORY_LANGUAGES,
)
from collection.cli_utils import add_output_dir_arg, add_since_arg, add_workers_arg
from collection.config import EXCLUSION_KEYWORDS
from collection.csv_adapter import get_adapter
from collection.ephemeral_clone import temp_clone_commit_history
from collection.logging_utils import get_logger
from collection.utils import _normalize_language_filters

logger = get_logger(__name__)

# Defaults, resolved through the central path registry (collection.paths) so
# `discover-repos --dataset a` and this module's standalone CLI agree on
# where repo-discovery output lives. Not created at import time -- `run()`
# creates `output_dir` once it knows the real value, so importing this module
# for a toy run (root=TOY_ROOT) never touches the real datasets/ tree.
GITHUB_SEARCH_RAW_DIR = paths.RAW_SEARCH_DIR
OUTPUT_DIR = paths.stage_dir("a", "repos")


def csv_path_for_language(language: str, output_dir: Path = OUTPUT_DIR) -> Path:
    """Return the per-language output CSV path under `output_dir`."""
    lang = (language or "unknown").lower()
    return output_dir / f"{lang}_repo.csv"


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
    languages: Optional[list[str]] = None,
    language: Optional[str] = None,
    raw_dir: Path = GITHUB_SEARCH_RAW_DIR,
) -> List[dict]:
    """Read candidate repos from `raw_dir` (default: github-search-raw)."""
    selected_languages = _normalize_language_filters(languages, language)
    files_raw = _collect_result_files(raw_dir, selected_languages)
    repos = _read_repos_from_files(files_raw, selected_languages)
    if selected_languages:
        logger.info(
            "Loaded %d repo candidates from %s for languages=%s",
            len(repos),
            raw_dir,
            ",".join(selected_languages),
        )
    else:
        logger.info("Loaded %d repo candidates from %s", len(repos), raw_dir)
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
        logger.debug("Processing %s (lang=%s)", full_name, lang)

        raw_clone_url = meta.get("clone_url") or f"https://github.com/{full_name}.git"
        clone_url = str(raw_clone_url).strip()
        matched_config_file: Optional[str] = None
        qc_reason = ""

        with temp_clone_commit_history(
            clone_url, str(full_name), prefix="agent-repos-", timeout=60
        ) as repo_path:
            try:
                if repo_path and repo_path.exists():
                    matched_config_file = scan_cloned_repo_for_agent_configs(repo_path)
                    if not matched_config_file:
                        qc_reason = "no_agent_config"
                else:
                    qc_reason = "clone_failed_or_missing"
            except Exception:
                qc_reason = "clone_failed_or_missing"

        row = {
            "repo_name": full_name,
            "has_agent_config": int(bool(matched_config_file)),
            "language": meta.get("language"),
            "stars": meta.get("stars"),
            "clone_url": meta.get("clone_url"),
            "num_contributors": meta.get("num_contributors"),
            "qc_reason": qc_reason,
            "matched_config_file": matched_config_file or "",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            # 1 = discovered directly from github-search-raw (this scan); 2 =
            # discovered via Tier-2 SEART matching (see __main__.py's
            # _merge_tier2_repos_into_csv). Always present, both writers use
            # the same column set/order, so append_dicts()'s "only write the
            # header if the file doesn't already exist" behavior can't leave
            # a subset of rows misaligned with the header.
            "discovery_tier": 1,
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
    source_dir: Path = GITHUB_SEARCH_RAW_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> int:
    """Detect agent config files across candidate repos and write per-language CSVs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    repos = read_repo_list(languages=languages, language=language, raw_dir=source_dir)
    if not repos:
        print(f"No repos found in {source_dir}.")
        return 0
    limit = int(limit or 0)

    to_process: list[dict] = []
    for entry in repos:
        if limit and len(to_process) >= limit:
            break
        to_process.append(entry)

    if not to_process:
        print("No repos to process.")
        return 0

    write_lock = threading.Lock()

    def write_row(row: dict) -> None:
        csv_path = csv_path_for_language(row.get("language") or "unknown", output_dir)
        with write_lock:
            get_adapter().append_dicts(csv_path, [row], list(row.keys()))

    workers = max(1, int(workers or 1))
    if workers == 1:
        count = 0
        with tqdm(total=len(to_process), desc="discover-repos", unit="repo") as pbar:
            for entry in to_process:
                res = _process_single(entry, since)
                if res:
                    write_row(res)
                    count += 1
                pbar.set_postfix(agent_config=count)
                pbar.update(1)
        print(f"Processed {count} repos; CSVs stored in {output_dir}")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_process_single, entry, since) for entry in to_process]
            count = 0
            with tqdm(total=len(futures), desc="discover-repos", unit="repo") as pbar:
                for fut in concurrent.futures.as_completed(futures):
                    r = fut.result()
                    if r:
                        write_row(r)
                        count += 1
                    pbar.set_postfix(agent_config=count)
                    pbar.update(1)
        print(
            f"Processed {count} repos with {workers} workers; CSVs stored in {output_dir}"
        )
    return 0


def main():
    """CLI entrypoint: run the preliminary agent-config repository counter."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Preliminary QC of agent candidate repos"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of repos to process (0 = all)",
    )
    add_since_arg(parser, help_text="Since date for agent commits")
    add_workers_arg(
        parser, default=8, help_text="Number of worker threads for parallel processing"
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
    add_output_dir_arg(
        parser,
        default=OUTPUT_DIR,
        help_text="Directory where *_repo.csv files are stored",
    )
    args = parser.parse_args()

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
            source_dir=Path(args.source_dir),
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    # Configure logging via collection.logging_utils.configure_logging()
    from collection.logging_utils import configure_logging

    configure_logging()
    main()
