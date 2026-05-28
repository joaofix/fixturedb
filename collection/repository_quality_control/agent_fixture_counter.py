"""Extract per-language agent fixture rows from a QCed agent-commit dataset.

Input:
- One directory containing per-language commit CSVs, e.g.:
  - python_agent_commit.csv
  - java_agent_commit.csv
  - ...

Output:
- One CSV per language written to --output-dir:
  - python_agent_fixture.csv
  - java_agent_fixture.csv
  - ...

This script reuses the existing fixture extraction logic in
`collection.fixture_extractor.AgentFixtureExtractor` and the commit-level
metadata from the QCed commit CSVs.
"""

from __future__ import annotations

import csv
import logging
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from collection.agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES
from collection.fixture_extractor import AgentFixtureExtractor
from collection.temp_clone import cleanup_tempdir, clone_to_tempdir

logger = logging.getLogger(__name__)

DEFAULT_INPUT_DIR = PROJECT_ROOT / "github-search-agent"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "github-search-agent"
DEFAULT_CLONES_DIR = PROJECT_ROOT / "clones"
DEFAULT_CLONE_THRESHOLD = 12
DEFAULT_PROGRESS_EVERY = 50
DEFAULT_WORKERS = 6


def _collect_commit_files(input_dir: Path, commit_dataset: str = "agent") -> list[Path]:
    files = set()
    if commit_dataset == "test":
        patterns = ("*_agent_test_commit_qc.csv", "*_agent_test_commit.csv")
    else:
        patterns = ("*_agent_commit.csv", "*_agent_commit_qc.csv")

    for pattern in patterns:
        for p in input_dir.glob(pattern):
            if p.is_file():
                files.add(p)
    return sorted(files)


def _date_only(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return value[:10]


def _load_agent_commit_dataset(
    input_dir: Path,
    language: str | None = None,
    since: str = "2025-01-01",
    commit_dataset: str = "agent",
) -> dict[str, dict]:
    """Load QCed agent commits grouped by repository."""
    grouped: dict[str, dict] = {}
    language_filter = (language or "").strip().lower() or None
    files = _collect_commit_files(input_dir, commit_dataset=commit_dataset)

    rows_seen = 0
    rows_kept = 0
    skipped_invalid = 0
    skipped_language = 0
    skipped_since = 0

    logger.info(
        "Loading commit dataset from %s (files=%d, language_filter=%s, since=%s, commit_dataset=%s)",
        input_dir,
        len(files),
        language_filter or "<none>",
        since or "<none>",
        commit_dataset,
    )

    for csv_path in files:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            file_rows = 0
            for row in reader:
                rows_seen += 1
                file_rows += 1
                repo_name = (row.get("repo_name") or "").strip()
                commit_sha = (row.get("commit_sha") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name or not commit_sha:
                    skipped_invalid += 1
                    continue
                if lang not in PAPER_AGENT_REPOSITORY_LANGUAGES:
                    skipped_language += 1
                    continue
                if language_filter and lang != language_filter:
                    skipped_language += 1
                    continue

                commit_date = _date_only(row.get("commit_date") or "")
                if since and commit_date and commit_date < since:
                    skipped_since += 1
                    continue

                clone_url = (
                    row.get("clone_url") or f"https://github.com/{repo_name}.git"
                ).strip()
                commit_url = (
                    row.get("commit_url")
                    or f"https://github.com/{repo_name}/commit/{commit_sha}"
                ).strip()
                agent_type = (row.get("agent_type") or "unknown").strip().lower()

                entry = grouped.setdefault(
                    repo_name,
                    {
                        "repo_name": repo_name,
                        "language": lang,
                        "clone_url": clone_url,
                        "commits": {},
                    },
                )
                if commit_sha not in entry["commits"]:
                    entry["commits"][commit_sha] = {
                        "agent_type": agent_type,
                        "commit_date": row.get("commit_date") or "",
                        "commit_url": commit_url,
                    }
                    rows_kept += 1

            logger.info("Read %d rows from %s", file_rows, csv_path.name)

    logger.info(
        "Loaded %d repositories and %d unique commits (rows_seen=%d, skipped_invalid=%d, skipped_language=%d, skipped_since=%d)",
        len(grouped),
        rows_kept,
        rows_seen,
        skipped_invalid,
        skipped_language,
        skipped_since,
    )
    return grouped


def _repo_local_path(clones_dir: Path, repo_name: str) -> Path:
    slash = clones_dir / repo_name
    underscore = clones_dir / repo_name.replace("/", "__")
    if slash.exists():
        return slash
    if underscore.exists():
        return underscore
    return underscore


def _run_git(repo_path: Path, args: list[str], timeout: int = 60) -> bool:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def _has_commit(repo_path: Path, commit_sha: str) -> bool:
    return _run_git(
        repo_path, ["cat-file", "-e", f"{commit_sha}^{{commit}}"], timeout=20
    )


def _fetch_commit(repo_path: Path, commit_sha: str, timeout: int = 120) -> bool:
    return _run_git(
        repo_path,
        ["fetch", "--depth=1", "--filter=blob:none", "origin", commit_sha],
        timeout=timeout,
    )


def _ensure_commits_present(
    repo_path: Path, clone_url: str, commit_shas: list[str]
) -> bool:
    """Ensure each target commit exists locally, fetching by SHA only when missing."""
    if not (repo_path / ".git").exists():
        return False

    # Add origin if the local repo has no remote set.
    if not _run_git(repo_path, ["remote", "get-url", "origin"], timeout=20):
        _run_git(repo_path, ["remote", "add", "origin", clone_url], timeout=20)

    all_present = True
    fetched = 0
    already_present = 0
    for sha in commit_shas:
        if _has_commit(repo_path, sha):
            already_present += 1
            continue
        if not _fetch_commit(repo_path, sha):
            all_present = False
        else:
            fetched += 1

    logger.info(
        "Commit availability in %s: requested=%d already_present=%d fetched=%d success=%s",
        repo_path,
        len(commit_shas),
        already_present,
        fetched,
        all_present,
    )
    return all_present


def _create_commit_targeted_temp_repo(
    repo_name: str, clone_url: str, commit_shas: list[str]
) -> tuple[Path | None, Path | None]:
    """Create a temporary repo and fetch only requested commit SHAs."""
    owner, name = repo_name.split("/", 1)
    temp_root = Path(tempfile.mkdtemp(prefix="agent-fixture-qc-"))
    repo_path = temp_root / f"{owner}__{name}"

    try:
        repo_path.mkdir(parents=True, exist_ok=True)
        if not _run_git(repo_path, ["init", "-q"], timeout=20):
            raise RuntimeError("git init failed")
        if not _run_git(repo_path, ["remote", "add", "origin", clone_url], timeout=20):
            raise RuntimeError("git remote add failed")

        fetched_any = False
        fetched_count = 0
        for sha in commit_shas:
            if _fetch_commit(repo_path, sha, timeout=180):
                fetched_any = True
                fetched_count += 1

        if fetched_any:
            logger.info(
                "Created SHA-targeted temp repo for %s: fetched=%d/%d",
                repo_name,
                fetched_count,
                len(commit_shas),
            )
            return repo_path, temp_root
    except Exception:
        pass

    logger.warning("Failed to create SHA-targeted temp repo for %s", repo_name)
    shutil.rmtree(temp_root, ignore_errors=True)
    return None, None


def _extract_rows_for_repo(
    repo_info: dict,
    extractor: AgentFixtureExtractor,
    include_partial: bool,
) -> list[dict]:
    repo_name = repo_info["repo_name"]
    commits_meta = repo_info["commits"]
    commits_for_extractor = {
        sha: meta["agent_type"] for sha, meta in commits_meta.items()
    }

    fixtures = extractor._extract_from_agent_commits(
        repo_name=repo_name, commits=commits_for_extractor
    )
    out_rows: list[dict] = []

    for fx in fixtures:
        is_complete = bool(fx.get("is_complete_addition"))
        if not include_partial and not is_complete:
            continue

        commit_sha = fx.get("commit_sha") or ""
        meta = commits_meta.get(commit_sha, {})
        mocks = fx.get("mocks", [])
        mock_identifiers = sorted(
            {
                (m.get("target_identifier") or "").strip()
                for m in mocks
                if (m.get("target_identifier") or "").strip()
            }
        )

        out_rows.append(
            {
                "repo_name": repo_name,
                "commit_sha": commit_sha,
                "commit_url": meta.get("commit_url")
                or f"https://github.com/{repo_name}/commit/{commit_sha}",
                "agent_type": fx.get("agent_type")
                or meta.get("agent_type")
                or "unknown",
                "commit_date": meta.get("commit_date") or "",
                "language": fx.get("language")
                or repo_info.get("language")
                or "unknown",
                "clone_url": repo_info.get("clone_url")
                or f"https://github.com/{repo_name}.git",
                "file_path": fx.get("file_path") or "",
                "fixture_name": fx.get("name") or "",
                "fixture_type": fx.get("fixture_type") or "",
                "framework": fx.get("framework") or "",
                "scope": fx.get("scope") or "",
                "loc": fx.get("loc") or 0,
                "start_line": fx.get("start_line") or 0,
                "end_line": fx.get("end_line") or 0,
                "is_complete_addition": int(is_complete),
                "num_mocks": len(mocks),
                "mock_identifiers": ";".join(mock_identifiers),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return out_rows


def _write_language_csvs(output_dir: Path, rows: list[dict]) -> None:
    fieldnames = [
        "repo_name",
        "commit_sha",
        "commit_url",
        "agent_type",
        "commit_date",
        "language",
        "clone_url",
        "file_path",
        "fixture_name",
        "fixture_type",
        "framework",
        "scope",
        "loc",
        "start_line",
        "end_line",
        "is_complete_addition",
        "num_mocks",
        "mock_identifiers",
        "processed_at",
    ]

    by_language: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        lang = (row.get("language") or "unknown").strip().lower()
        by_language[lang].append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    for lang, lang_rows in sorted(by_language.items()):
        path = output_dir / f"{lang}_agent_fixture.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(lang_rows)
        logger.info("Wrote %d fixture rows to %s", len(lang_rows), path)


def _process_single_repo(
    repo_name: str,
    repo_info: dict,
    clones_dir: Path,
    since: str,
    include_partial: bool,
    strategy: str,
    clone_threshold: int,
) -> dict:
    local_repo_path = _repo_local_path(clones_dir, repo_name)
    temp_root = None
    clone_url = repo_info.get("clone_url") or f"https://github.com/{repo_name}.git"
    commit_shas = list(repo_info.get("commits", {}).keys())

    selected_strategy = strategy
    if selected_strategy == "auto":
        selected_strategy = "clone" if len(commit_shas) > clone_threshold else "sha"

    logger.info(
        "Repo %s: commits=%d selected_strategy=%s (requested=%s threshold=%d)",
        repo_name,
        len(commit_shas),
        selected_strategy,
        strategy,
        clone_threshold,
    )

    used_local_clone = False
    if local_repo_path.exists() and (local_repo_path / ".git").exists():
        used_local_clone = True
        logger.info(
            "Repo %s: using existing local clone at %s", repo_name, local_repo_path
        )
        _ensure_commits_present(local_repo_path, clone_url, commit_shas)
    else:
        if selected_strategy == "sha":
            # Fast path: fetch only requested SHAs into a temp repo.
            local_repo_path, temp_root = _create_commit_targeted_temp_repo(
                repo_name,
                clone_url,
                commit_shas,
            )

            # Fallback: broader temporary clone if SHA-targeted fetch failed.
            if local_repo_path is None or temp_root is None:
                logger.info(
                    "Repo %s: SHA strategy failed, falling back to clone strategy",
                    repo_name,
                )
                clone_args = ["--filter=blob:limit=10m", "--no-tags"]
                local_repo_path, temp_root = clone_to_tempdir(
                    repo_name,
                    clone_url,
                    clone_args,
                    timeout=300,
                    prefix="agent-fixture-qc-",
                )
                if local_repo_path is None or temp_root is None:
                    logger.warning("Skipping %s: clone/fetch failed", repo_name)
                    return {
                        "repo_name": repo_name,
                        "strategy": selected_strategy,
                        "rows": [],
                        "skipped": True,
                        "local_clone_reuse": used_local_clone,
                    }
                _ensure_commits_present(local_repo_path, clone_url, commit_shas)
        else:
            # Clone strategy: one broader clone for this repo and reuse locally for all target commits.
            clone_args = ["--filter=blob:limit=10m", "--no-tags"]
            local_repo_path, temp_root = clone_to_tempdir(
                repo_name,
                clone_url,
                clone_args,
                timeout=300,
                prefix="agent-fixture-qc-",
            )
            if local_repo_path is None or temp_root is None:
                logger.warning("Skipping %s: clone failed", repo_name)
                return {
                    "repo_name": repo_name,
                    "strategy": selected_strategy,
                    "rows": [],
                    "skipped": True,
                    "local_clone_reuse": used_local_clone,
                }
            _ensure_commits_present(local_repo_path, clone_url, commit_shas)

    extractor = AgentFixtureExtractor(
        clones_dir=local_repo_path.parent, start_date=since
    )
    try:
        repo_rows = _extract_rows_for_repo(
            repo_info=repo_info,
            extractor=extractor,
            include_partial=include_partial,
        )
        logger.info("%s -> %d extracted fixture rows", repo_name, len(repo_rows))
        return {
            "repo_name": repo_name,
            "strategy": selected_strategy,
            "rows": repo_rows,
            "skipped": False,
            "local_clone_reuse": used_local_clone,
        }
    finally:
        cleanup_tempdir(temp_root)


def run(
    input_dir: Path,
    output_dir: Path,
    clones_dir: Path,
    since: str,
    language: str | None,
    include_partial: bool,
    strategy: str,
    clone_threshold: int,
    progress_every: int,
    workers: int,
    commit_dataset: str,
) -> int:
    logger.info(
        "Starting fixture extraction (input=%s output=%s clones=%s strategy=%s clone_threshold=%d since=%s language=%s include_partial=%s workers=%d)",
        input_dir,
        output_dir,
        clones_dir,
        strategy,
        clone_threshold,
        since,
        language or "<all>",
        include_partial,
        workers,
    )
    repos = _load_agent_commit_dataset(
        input_dir=input_dir,
        language=language,
        since=since,
        commit_dataset=commit_dataset,
    )
    if not repos:
        print(f"No agent commits found in {input_dir}")
        return 0

    rows: list[dict] = []
    processed_repos = 0
    skipped_repos = 0
    strategy_counts = {"sha": 0, "clone": 0}
    local_clone_reuse_count = 0
    total_repos = len(repos)
    started_at = time.time()

    def _log_progress(force: bool = False) -> None:
        done = processed_repos + skipped_repos
        if done == 0:
            return
        if not force and progress_every > 0 and done % progress_every != 0:
            return

        elapsed = max(time.time() - started_at, 0.001)
        rate = done / elapsed
        remaining = max(total_repos - done, 0)
        eta_seconds = remaining / rate if rate > 0 else 0.0
        logger.info(
            "Progress: %d/%d repos (processed=%d skipped=%d fixtures=%d, rate=%.2f repos/s, eta=%.1fs)",
            done,
            total_repos,
            processed_repos,
            skipped_repos,
            len(rows),
            rate,
            eta_seconds,
        )

    repo_items = sorted(repos.items())

    def _consume_result(result: dict) -> None:
        nonlocal processed_repos, skipped_repos, local_clone_reuse_count
        selected_strategy = (result.get("strategy") or "sha").strip().lower()
        if selected_strategy not in strategy_counts:
            selected_strategy = "sha"
        strategy_counts[selected_strategy] += 1

        if result.get("local_clone_reuse"):
            local_clone_reuse_count += 1

        if result.get("skipped"):
            skipped_repos += 1
        else:
            processed_repos += 1
            rows.extend(result.get("rows") or [])
        _log_progress()

    if workers <= 1:
        for repo_name, repo_info in repo_items:
            result = _process_single_repo(
                repo_name=repo_name,
                repo_info=repo_info,
                clones_dir=clones_dir,
                since=since,
                include_partial=include_partial,
                strategy=strategy,
                clone_threshold=clone_threshold,
            )
            _consume_result(result)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_repo = {
                executor.submit(
                    _process_single_repo,
                    repo_name,
                    repo_info,
                    clones_dir,
                    since,
                    include_partial,
                    strategy,
                    clone_threshold,
                ): repo_name
                for repo_name, repo_info in repo_items
            }
            for future in as_completed(future_to_repo):
                repo_name = future_to_repo[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.exception(
                        "Skipping %s due to unexpected worker error: %s", repo_name, exc
                    )
                    _consume_result(
                        {
                            "repo_name": repo_name,
                            "strategy": "sha",
                            "rows": [],
                            "skipped": True,
                            "local_clone_reuse": False,
                        }
                    )
                    continue
                _consume_result(result)

    if not rows:
        logger.info(
            "Completed with no fixture rows (processed_repos=%d skipped_repos=%d local_clone_reuse=%d strategy_counts=%s)",
            processed_repos,
            skipped_repos,
            local_clone_reuse_count,
            strategy_counts,
        )
        print("No fixture rows extracted from the provided agent commit dataset")
        return 0

    _write_language_csvs(output_dir, rows)
    logger.info(
        "Completed extraction (fixture_rows=%d processed_repos=%d skipped_repos=%d local_clone_reuse=%d strategy_counts=%s)",
        len(rows),
        processed_repos,
        skipped_repos,
        local_clone_reuse_count,
        strategy_counts,
    )
    _log_progress(force=True)
    print(
        f"Extracted {len(rows)} fixture rows into per-language CSVs under {output_dir}"
    )
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract per-language agent fixture CSVs from agent commit CSV inputs"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing *_agent_commit.csv files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for output *_agent_fixture.csv files",
    )
    parser.add_argument(
        "--clones-dir",
        type=Path,
        default=DEFAULT_CLONES_DIR,
        help="Directory with local clones (missing repos are fetched by commit SHA into temp repos)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default="2025-01-01",
        help="Only process commits on/after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--language",
        choices=sorted(PAPER_AGENT_REPOSITORY_LANGUAGES),
        default=None,
        help="Optional language filter",
    )
    parser.add_argument(
        "--include-partial",
        action="store_true",
        help="Include fixtures that are not complete additions",
    )
    parser.add_argument(
        "--strategy",
        choices=["auto", "sha", "clone"],
        default="auto",
        help="Repo acquisition strategy: auto (default), sha (fetch target commits only), or clone",
    )
    parser.add_argument(
        "--clone-threshold",
        type=int,
        default=DEFAULT_CLONE_THRESHOLD,
        help="In auto mode, repos with commit count greater than this use clone strategy",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=DEFAULT_PROGRESS_EVERY,
        help="Emit a progress summary log every N repositories (set 0 to disable periodic heartbeats)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Number of repositories to process concurrently (set 1 for sequential execution)",
    )
    parser.add_argument(
        "--commit-dataset",
        choices=["agent", "test"],
        default="test",
        help="Which commit dataset to extract fixtures from (default: test)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    return run(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        clones_dir=Path(args.clones_dir),
        since=args.since,
        language=args.language,
        include_partial=args.include_partial,
        strategy=args.strategy,
        clone_threshold=max(1, int(args.clone_threshold or DEFAULT_CLONE_THRESHOLD)),
        progress_every=max(0, int(args.progress_every)),
        workers=max(1, int(args.workers or DEFAULT_WORKERS)),
        commit_dataset=args.commit_dataset,
    )


if __name__ == "__main__":
    raise SystemExit(main())
