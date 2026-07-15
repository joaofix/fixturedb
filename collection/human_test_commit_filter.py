"""Filtering to human-authored test commits: pre-2021 baseline (Dataset C)
and post-2025 within-repo control (Dataset B).

Split out of test_commit_filter.py, which now holds only the agent-side
(Dataset A) filtering path. Entry point for Dataset B:
`python -m collection filter-test-commits --dataset b`.
"""

from __future__ import annotations

import csv
import functools
import gzip
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from . import paths
from .config import (
    AGENT_CORPUS_START_DATE,
    CLONES_DIR,
    HUMAN_CORPUS_CUTOFF_DATE,
    LANGUAGE_CONFIGS,
)
from .csv_adapter import get_adapter
from .ephemeral_clone import temp_clone_commit_history
from .logging_utils import get_logger
from .test_commit_resume_state import (
    _load_test_commit_resume_state,
    _save_test_commit_resume_state,
)
from .test_commit_utils import write_test_commits_csv
from .tiered_agent_corpus_scanner import Tier1RepositoryScanner

logger = get_logger(__name__)

_DISAGREEMENT_FIELDNAMES = [
    "repo_name",
    "language",
    "commit_sha",
    "commit_date",
    "dataset_a_agent_type",
    "dataset_b_role",
    "dataset_b_agent_type",
    "reason",
]


def _load_dataset_a_commit_lookup(commits_dir: Path) -> dict[str, dict[str, str]]:
    """Build {repo_name: {commit_sha: agent_type}} from Dataset A's already-classified
    commits (datasets/a/commits/*.csv), to cross-check Dataset B's fresh classification
    against a known-good oracle -- see docs/architecture/agent-detection.md and this
    function's caller for why this is a correctness safety net, not a speed optimization.

    Missing/unreadable source is not fatal: Dataset B's own collection must never be
    blocked by this cross-check, so a warning is logged and an empty lookup returned
    (the cross-check then silently finds nothing to compare against).
    """
    lookup: dict[str, dict[str, str]] = defaultdict(dict)
    csv_paths = sorted(Path(commits_dir).glob("*_commit.csv"))
    if not csv_paths:
        logger.warning(
            "[human-test-commits] No Dataset A commit CSVs found under %s; "
            "skipping the Dataset A cross-check (Dataset B collection continues normally)",
            commits_dir,
        )
        return {}

    for csv_path in csv_paths:
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    repo_name = (row.get("repo_name") or "").strip()
                    commit_sha = (row.get("commit_sha") or "").strip()
                    agent_type = (row.get("agent_type") or "").strip()
                    if repo_name and commit_sha and agent_type:
                        lookup[repo_name][commit_sha] = agent_type
        except Exception as exc:
            logger.warning(
                "[human-test-commits] Failed to read %s for the Dataset A "
                "cross-check: %s (continuing without it for this file)",
                csv_path,
                exc,
            )

    return dict(lookup)


def _check_against_dataset_a(
    repo_name: str,
    language: str,
    commit,
    dataset_a_lookup: dict[str, dict[str, str]],
) -> dict | None:
    """Compare one freshly-scanned commit's role against Dataset A's already-validated
    classification for the same (repo_name, commit_sha), if Dataset A examined it.

    Returns a disagreement row dict, or None when there's nothing worth flagging --
    including the common case of a human-classified commit Dataset A never saw (new
    repo activity since Dataset A's snapshot, not a disagreement).
    """
    dataset_a_agent_type = dataset_a_lookup.get(repo_name, {}).get(commit.commit_sha)

    if dataset_a_agent_type is not None:
        if commit.agent_type == dataset_a_agent_type:
            return None
        return {
            "repo_name": repo_name,
            "language": language,
            "commit_sha": commit.commit_sha,
            "commit_date": commit.commit_date,
            "dataset_a_agent_type": dataset_a_agent_type,
            "dataset_b_role": commit.commit_role,
            "dataset_b_agent_type": commit.agent_type or "",
            "reason": "mismatch",
        }

    if commit.commit_role == "agent":
        return {
            "repo_name": repo_name,
            "language": language,
            "commit_sha": commit.commit_sha,
            "commit_date": commit.commit_date,
            "dataset_a_agent_type": "",
            "dataset_b_role": commit.commit_role,
            "dataset_b_agent_type": commit.agent_type or "",
            "reason": "dataset_a_missing",
        }

    return None


def _write_disagreements_csv(disagreements: list[dict], output_path: Path) -> None:
    adapter = get_adapter()
    adapter.write_dicts(output_path, disagreements, _DISAGREEMENT_FIELDNAMES)


def _load_pre2021_raw_repo_rows(
    raw_search_dir: Path, language: str | None = None
) -> list[dict]:
    """Load pre-2021 repository search rows from github-search-raw CSV.gz files."""
    cutoff_date = HUMAN_CORPUS_CUTOFF_DATE
    language_filter = (language or "").strip().lower() or None
    repo_rows: list[dict] = []

    for csv_path in sorted(Path(raw_search_dir).glob("*.csv.gz"), key=lambda p: p.name):
        try:
            with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    repo_name = (row.get("name") or row.get("full_name") or "").strip()
                    lang = (
                        (row.get("mainLanguage") or row.get("language") or "")
                        .strip()
                        .lower()
                    )
                    created_at = (
                        row.get("createdAt") or row.get("created_at") or ""
                    ).strip()
                    is_fork = (
                        str(row.get("isFork") or row.get("fork") or "").strip().lower()
                    )
                    if not repo_name or "/" not in repo_name:
                        continue
                    if language_filter and lang != language_filter:
                        continue
                    if lang and lang not in LANGUAGE_CONFIGS:
                        continue
                    if is_fork in {"1", "true", "yes"}:
                        continue
                    if created_at and created_at[:10] > cutoff_date:
                        continue
                    repo_rows.append(
                        {
                            "repo_name": repo_name,
                            "full_name": repo_name,
                            "language": lang or language_filter or "unknown",
                            "clone_url": (
                                row.get("clone_url")
                                or f"https://github.com/{repo_name}.git"
                            ).strip(),
                            "created_at": created_at,
                        }
                    )
        except Exception as exc:
            logger.debug("Failed to read raw search CSV %s: %s", csv_path, exc)

    return repo_rows


def _collect_human_test_commits_from_repo_rows(
    repo_rows: list[dict],
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
    process_fn=None,
    dataset_a_commits_dir: Path | None = None,
) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in repo_rows:
        repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
        if repo_name:
            grouped[repo_name].append(row)
    test_commit_rows_by_language: dict[str, list[dict]] = defaultdict(list)
    disagreements: list[dict] = []
    (
        existing_rows_by_lang,
        seen_commit_shas_by_language,
        completed_repos,
        counts,
    ) = _load_test_commit_resume_state(Path(output_dir), role="human")

    repos_processed = counts.get("repos_processed", 0)
    commits_scanned = counts.get("commits_scanned", 0)
    repos_with_test_commits = counts.get("repos_with_test_commits", 0)
    workers = max(1, int(workers or 1))

    # Default to the 2025+ variant for Dataset 2 (agent-enabled repos, post-2025)
    if process_fn is None:
        process_fn = _process_repo_human_test_commits_2025

    if process_fn is _process_repo_human_test_commits_2025:
        dataset_a_lookup = _load_dataset_a_commit_lookup(
            Path(dataset_a_commits_dir)
            if dataset_a_commits_dir
            else paths.stage_dir("a", "commits")
        )
        if dataset_a_lookup:
            logger.info(
                "[human-test-commits] Loaded Dataset A cross-check oracle: %d repo(s) "
                "with known commit classifications",
                len(dataset_a_lookup),
            )
        process_fn = functools.partial(process_fn, dataset_a_lookup=dataset_a_lookup)

    # Filter out repos already completed in checkpoint
    repos_to_process = {
        repo_name: repo_rows_for_name
        for repo_name, repo_rows_for_name in grouped.items()
        if repo_name not in completed_repos
    }

    total_repos = len(repos_to_process)

    logger.info(
        "[human-test-commits] Loaded %d repo rows across %d repos (to process=%d)",
        sum(len(v) for v in grouped.values()),
        len(grouped),
        total_repos,
    )
    if completed_repos:
        logger.info(
            "[human-test-commits] Resuming from checkpoint: %d repos already completed, %d repo(s) skipped",
            len(completed_repos),
            len(grouped) - len(repos_to_process),
        )
    logger.info("[human-test-commits] Filtering with %d worker(s)", workers)

    def persist_progress() -> None:
        counts.update(
            {
                "repos_processed": repos_processed,
                "commits_scanned": commits_scanned,
                "repos_with_test_commits": repos_with_test_commits,
                "test_commits_found": sum(
                    len(language_rows)
                    for language_rows in test_commit_rows_by_language.values()
                ),
            }
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        for language, language_rows in sorted(test_commit_rows_by_language.items()):
            write_test_commits_csv(
                language_rows, output_dir / f"{language}_human_test_commit.csv"
            )
        if disagreements:
            _write_disagreements_csv(
                disagreements, output_dir / "commit_role_disagreements.csv"
            )
        _save_test_commit_resume_state(
            output_dir, counts, completed_repos, role="human"
        )

    if workers == 1:
        with tqdm(total=total_repos, desc="[human-test-commits]", unit="repo") as pbar:
            for repo_name, repo_rows_for_name in repos_to_process.items():
                (
                    language,
                    repo_test_commits,
                    repo_count,
                    repo_commits_scanned,
                    repo_disagreements,
                ) = process_fn(repo_rows_for_name[0])
                repos_processed += repo_count
                commits_scanned += repo_commits_scanned
                disagreements.extend(repo_disagreements)
                new_rows = []
                lang_seen = seen_commit_shas_by_language.setdefault(language, set())
                for row in repo_test_commits:
                    commit_sha = (row.get("commit_sha") or "").strip()
                    if commit_sha and commit_sha not in lang_seen:
                        lang_seen.add(commit_sha)
                        new_rows.append(row)
                if new_rows:
                    repos_with_test_commits += 1
                    test_commit_rows_by_language[language].extend(new_rows)
                completed_repos.add(repo_name)
                persist_progress()
                pbar.set_postfix(commits=commits_scanned, test_commits=sum(
                    len(v) for v in test_commit_rows_by_language.values()
                ))
                pbar.update(1)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(process_fn, repo_rows_for_name[0]): repo_name
                for repo_name, repo_rows_for_name in repos_to_process.items()
            }
            try:
                with tqdm(total=total_repos, desc="[human-test-commits]", unit="repo") as pbar:
                    for future in as_completed(futures):
                        (
                            language,
                            repo_test_commits,
                            repo_count,
                            repo_commits_scanned,
                            repo_disagreements,
                        ) = future.result()
                        repos_processed += repo_count
                        commits_scanned += repo_commits_scanned
                        disagreements.extend(repo_disagreements)
                        new_rows = []
                        lang_seen = seen_commit_shas_by_language.setdefault(language, set())
                        for row in repo_test_commits:
                            commit_sha = (row.get("commit_sha") or "").strip()
                            if commit_sha and commit_sha not in lang_seen:
                                lang_seen.add(commit_sha)
                                new_rows.append(row)
                        if new_rows:
                            repos_with_test_commits += 1
                            test_commit_rows_by_language[language].extend(new_rows)
                        repo_name = futures.get(future, None)
                        if repo_name:
                            completed_repos.add(repo_name)
                        persist_progress()
                        pbar.set_postfix(commits=commits_scanned, test_commits=sum(
                            len(v) for v in test_commit_rows_by_language.values()
                        ))
                        pbar.update(1)
            except KeyboardInterrupt:
                logger.warning(
                    "[human-test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs..."
                )
                for fut in futures:
                    fut.cancel()
                persist_progress()
                raise

    output_files: dict[str, str] = {}
    total_test_commits = 0
    for language, language_rows in sorted(test_commit_rows_by_language.items()):
        output_path = output_dir / f"{language}_human_test_commit.csv"
        write_test_commits_csv(language_rows, output_path)
        output_files[language] = str(output_path)
        total_test_commits += len(language_rows)

    disagreements_path: str | None = None
    if disagreements:
        out_path = output_dir / "commit_role_disagreements.csv"
        _write_disagreements_csv(disagreements, out_path)
        disagreements_path = str(out_path)

    disagreement_summary = (
        f", {len(disagreements)} Dataset A disagreement(s) logged to {disagreements_path}"
        if disagreements
        else ""
    )
    logger.info(
        "[human-test-commits] Finished: %d repos processed, %d commits scanned, "
        "%d human test commits found%s",
        repos_processed,
        commits_scanned,
        total_test_commits,
        disagreement_summary,
    )
    counts.update(
        {
            "repos_processed": repos_processed,
            "commits_scanned": commits_scanned,
            "repos_with_test_commits": repos_with_test_commits,
            "test_commits_found": total_test_commits,
        }
    )
    _save_test_commit_resume_state(output_dir, counts, completed_repos, role="human")
    return {
        "repos_processed": repos_processed,
        "commits_scanned": commits_scanned,
        "repos_with_test_commits": repos_with_test_commits,
        "test_commits_found": total_test_commits,
        "output_files": output_files,
        "output_dir": str(output_dir),
        "disagreements_found": len(disagreements),
        "disagreements_file": disagreements_path,
    }


def _process_repo_human_test_commits_pre2021(
    repo_row: dict,
    dataset_a_lookup: dict[str, dict[str, str]] | None = None,
) -> tuple[str, list[dict], int, int, list[dict]]:
    """Scan a repo for human test commits in the pre-2021 era (Dataset 3).

    Uses HUMAN_CORPUS_CUTOFF_DATE to find human-authored test commits
    from before the AI coding agent era. Always returns an empty disagreements
    list -- this corpus predates Dataset A's agent era entirely, so there's
    nothing in datasets/a/commits/*.csv that could ever overlap with it.
    `dataset_a_lookup` is accepted (and ignored) only so this function has the
    same signature as `_process_repo_human_test_commits_2025` for
    `_collect_human_test_commits_from_repo_rows`'s shared aggregation.
    """
    repo_name = (repo_row.get("repo_name") or repo_row.get("full_name") or "").strip()
    clone_url = (
        repo_row.get("clone_url") or f"https://github.com/{repo_name}.git"
    ).strip()
    language = (repo_row.get("language") or "unknown").strip().lower()

    logger.debug("[human-test-commits] Cloning %s (%s)", repo_name, language)
    with temp_clone_commit_history(
        clone_url, repo_name, prefix="human-test-commits-", timeout=300
    ) as repo_path:
        if repo_path is None:
            logger.warning(
                "Failed to clone %s while filtering human test commits", repo_name
            )
            return language, [], 1, 0, []

        test_commit_rows: list[dict] = []
        commits_scanned = 0
        scanner = Tier1RepositoryScanner(paths.corpus_db_path())
        commit_roles = scanner.scan_repo_commit_roles(
            repo_path,
            start_date=HUMAN_CORPUS_CUTOFF_DATE,
            language=language,
            detect_test_files=True,
        )
        for commit in commit_roles:
            commits_scanned += 1
            if commit.commit_role != "human" or not commit.is_test_commit:
                continue
            test_commit_rows.append(
                {
                    "repo_name": repo_name,
                    "language": language,
                    "commit_sha": commit.commit_sha,
                    "commit_role": "human",
                    "agent_type": commit.agent_type,
                    "commit_date": commit.commit_date,
                    "test_file_count": len(commit.test_files),
                    "test_file_paths": json.dumps(
                        commit.test_files, ensure_ascii=False
                    ),
                }
            )

    logger.info(
        "[human-test-commits] %s (%s): scanned %d commits, found %d human test commits",
        repo_name,
        language,
        commits_scanned,
        len(test_commit_rows),
    )
    return language, test_commit_rows, 1, commits_scanned, []


def _process_repo_human_test_commits_2025(
    repo_row: dict,
    dataset_a_lookup: dict[str, dict[str, str]] | None = None,
) -> tuple[str, list[dict], int, int, list[dict]]:
    """Scan a repo for human test commits in the post-2025 era (Dataset 2).

    Uses AGENT_CORPUS_START_DATE to find human-authored test commits
    from the same temporal window as the agent dataset, in agent-enabled repos.

    `dataset_a_lookup` (repo_name -> {commit_sha: agent_type}, from Dataset A's
    already-validated datasets/a/commits/*.csv) is an optional cross-check
    oracle: every commit this scan examines is compared against it, and any
    disagreement is recorded (not raised) -- see
    `_check_against_dataset_a`. This never blocks or alters Dataset B's own
    collection; it's a correctness safety net reviewed after the run.
    """
    repo_name = (repo_row.get("repo_name") or repo_row.get("full_name") or "").strip()
    clone_url = (
        repo_row.get("clone_url") or f"https://github.com/{repo_name}.git"
    ).strip()
    language = (repo_row.get("language") or "unknown").strip().lower()
    dataset_a_lookup = dataset_a_lookup or {}

    logger.debug("[human-test-commits] Cloning %s (%s)", repo_name, language)
    with temp_clone_commit_history(
        clone_url, repo_name, prefix="human-test-commits-", timeout=300
    ) as repo_path:
        if repo_path is None:
            logger.warning(
                "Failed to clone %s while filtering human test commits", repo_name
            )
            return language, [], 1, 0, []

        test_commit_rows: list[dict] = []
        disagreements: list[dict] = []
        commits_scanned = 0
        scanner = Tier1RepositoryScanner(paths.corpus_db_path())
        commit_roles = scanner.scan_repo_commit_roles(
            repo_path,
            start_date=AGENT_CORPUS_START_DATE,
            language=language,
            detect_test_files=True,
        )
        for commit in commit_roles:
            commits_scanned += 1
            disagreement = _check_against_dataset_a(
                repo_name, language, commit, dataset_a_lookup
            )
            if disagreement:
                disagreements.append(disagreement)
            if commit.commit_role != "human" or not commit.is_test_commit:
                continue
            test_commit_rows.append(
                {
                    "repo_name": repo_name,
                    "language": language,
                    "commit_sha": commit.commit_sha,
                    "commit_role": "human",
                    "agent_type": commit.agent_type,
                    "commit_date": commit.commit_date,
                    "test_file_count": len(commit.test_files),
                    "test_file_paths": json.dumps(
                        commit.test_files, ensure_ascii=False
                    ),
                }
            )

    disagreement_suffix = (
        f", {len(disagreements)} Dataset A disagreement(s)" if disagreements else ""
    )
    logger.info(
        "[human-test-commits] %s (%s): scanned %d commits, found %d human test commits%s",
        repo_name,
        language,
        commits_scanned,
        len(test_commit_rows),
        disagreement_suffix,
    )
    return language, test_commit_rows, 1, commits_scanned, disagreements


# Backwards-compatible alias: the old name now points to the pre-2021 variant
# (Dataset 3). Dataset 2 callers should use _process_repo_human_test_commits_2025.
_process_repo_human_test_commits = _process_repo_human_test_commits_pre2021


def collect_human_test_commits(
    repo_qc_dir: Path,
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
    language: str | None = None,
    dataset_a_commits_dir: Path | None = None,
) -> dict:
    """Filter agent-config repositories to human-authored commits that touch test files.

    Args:
        language: Optional language filter (e.g. 'python')
        dataset_a_commits_dir: Where to load the Dataset A cross-check oracle from
            (default: datasets/a/commits/, see _load_dataset_a_commit_lookup). Mainly
            for tests -- a real `--dataset b` run should just use the default.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    language_filter = (language or "").strip().lower() or None
    for csv_path in sorted(
        Path(repo_qc_dir).glob("*_repo.csv"), key=lambda path: path.name
    ):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("has_agent_config") or "").strip().lower() not in {
                    "1",
                    "true",
                }:
                    continue
                row_lang = (row.get("language") or "").strip().lower() or None
                if language_filter and row_lang and row_lang != language_filter:
                    continue
                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                if repo_name:
                    grouped[repo_name].append(row)

    repo_rows = [rows[0] for rows in grouped.values()]
    logger.info(
        "[human-test-commits] Loaded %d repo rows across %d repos from %s",
        sum(len(v) for v in grouped.values()),
        len(grouped),
        repo_qc_dir,
    )
    return _collect_human_test_commits_from_repo_rows(
        repo_rows,
        Path(output_dir),
        clones_dir=clones_dir,
        workers=workers,
        process_fn=_process_repo_human_test_commits_2025,
        dataset_a_commits_dir=dataset_a_commits_dir,
    )


def collect_human_test_commits_from_raw_search(
    raw_search_dir: Path,
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
    language: str | None = None,
) -> dict:
    """Filter github-search-raw repository search results to pre-2021 human test commits."""
    repo_rows = _load_pre2021_raw_repo_rows(raw_search_dir, language=language)
    logger.info(
        "[human-test-commits] Loaded %d pre-2021 repositories from raw search results in %s",
        len(repo_rows),
        raw_search_dir,
    )
    return _collect_human_test_commits_from_repo_rows(
        repo_rows,
        Path(output_dir),
        clones_dir=clones_dir,
        workers=workers,
        process_fn=_process_repo_human_test_commits_pre2021,
    )
