"""Dataset C: pre-2022 human fixtures extracted from a stratified sample snapshot."""

import csv
import json
import logging
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from collection.fixture_extractor import AgentFixtureExtractor, extract_fixtures
from collection.agent_commit_detector import _is_test_file_path
from collection.clone_manager import clone_with_function
from collection.agent_corpus import clone_repo_for_commit_scan
from collection.config import (
    HUMAN_CORPUS_CUTOFF_DATE,
)
from collection.corpus_utils import construct_repo_dict, persist_repository_and_fixtures
from collection.sampling import stratified_sample_by_language
from collection.db import db_session, initialise_db
from collection.logging_utils import get_logger

logger = get_logger(__name__)


def load_repo_cutoffs(csv_path: Path) -> Dict[str, Dict[str, str]]:
    """Load dataset_c_repo_cutoffs.csv mapping repo_name -> cutoff metadata."""
    cutoffs: Dict[str, Dict[str, str]] = {}
    if not csv_path.exists():
        logger.warning("Cutoff CSV not found: %s", csv_path)
        return cutoffs
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            repo_name = (row.get("repo_name") or "").strip()
            if not repo_name:
                continue
            cutoffs[repo_name] = {
                "language": (row.get("language") or "unknown").strip().lower(),
                "cutoff_commit_sha": (row.get("cutoff_commit_sha") or "").strip(),
                "cutoff_commit_date": (row.get("cutoff_commit_date") or "").strip(),
                "clone_url": (row.get("clone_url") or "").strip(),
            }
    logger.info("Loaded %d repo cutoffs from %s", len(cutoffs), csv_path)
    return cutoffs


def find_cutoff_commit(repo_path: Path, cutoff_date: str = HUMAN_CORPUS_CUTOFF_DATE) -> Optional[Dict[str, str]]:
    """Find the last commit before cutoff_date in the repo."""
    try:
        from pydriller import Repository

        repo = Repository(str(repo_path))
        best = None
        for commit in repo.traverse_commits():
            commit_date_val = commit.author_date.date().isoformat()
            if commit_date_val <= cutoff_date:
                if best is None or commit_date_val > best["date"]:
                    best = {
                        "sha": commit.hash,
                        "date": commit_date_val,
                    }
        return best
    except Exception as exc:
        logger.debug("Failed to find cutoff commit in %s: %s", repo_path, exc)
        return None


def find_test_files_at_commit(repo_path: Path, language: Optional[str] = None) -> List[str]:
    """Find all test files in the repo at the current checkout."""
    test_files: List[str] = []
    for file_path in sorted(repo_path.rglob("*")):
        if not file_path.is_file():
            continue
        rel_path = str(file_path.relative_to(repo_path))
        if not _is_test_file_path(rel_path, language=language):
            continue
        test_files.append(rel_path)
    return test_files


def _load_dataset_c_checkpoint(checkpoint_path: Path) -> Tuple[Set[str], Dict[str, int]]:
    completed_repos: Set[str] = set()
    counts: Dict[str, int] = {
        "repos_persisted": 0,
        "fixtures_persisted": 0,
    }
    if checkpoint_path.exists():
        try:
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            completed_repos.update(
                str(r).strip()
                for r in data.get("completed_repos", [])
                if str(r or "").strip()
            )
            counts.update(data.get("counts", {}))
        except Exception:
            pass
    return completed_repos, counts


def _save_dataset_c_checkpoint(checkpoint_path: Path, completed_repos: Set[str], counts: Dict[str, int]) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "completed_repos": sorted(completed_repos),
        "counts": counts,
    }
    with checkpoint_path.open("w", encoding="utf-8") as fh:
        json.dump(checkpoint, fh, ensure_ascii=False, indent=2)
        fh.flush()


def _write_dataset_c_progress(progress_path: Path, completed_repos: Set[str], counts: Dict[str, int]) -> None:
    progress = {
        "repos_persisted": counts.get("repos_persisted", 0),
        "fixtures_persisted": counts.get("fixtures_persisted", 0),
        "completed_repos_count": len(completed_repos),
    }
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("w", encoding="utf-8") as fh:
        json.dump(progress, fh, ensure_ascii=False, indent=2)
        fh.flush()


def _process_repo(
    repo: Dict[str, Any],
    cutoffs: Dict[str, Dict[str, str]],
    extractor: AgentFixtureExtractor,
    clones_dir: Path,
) -> Tuple[bool, List[Tuple[Dict[str, Any], Dict[str, Any]]]]:
    """Process a single repo for Dataset C snapshot extraction.

    Returns:
        (success, list of (repo, fixture) tuples)
    """
    repo_name = repo["full_name"]
    repo_path = clones_dir / repo_name.replace("/", "__")
    language = (repo.get("language") or "unknown").strip().lower()
    clone_url = (
        repo.get("clone_url")
        or cutoffs.get(repo_name, {}).get("clone_url")
        or f"https://github.com/{repo_name}.git"
    ).strip()

    # Determine target path before clone so managed_path can be used directly
    actual_repo_path = repo_path

    with clone_with_function(clone_repo_for_commit_scan, clone_url, repo_path) as managed_path:
        if managed_path is None:
            logger.warning("[Dataset C] Clone failed for %s", repo_name)
            return False, []

        actual_repo_path = managed_path if managed_path is not None else repo_path

        cutoff = cutoffs.get(repo_name)
        if cutoff and cutoff.get("cutoff_commit_sha"):
            cutoff_sha = cutoff["cutoff_commit_sha"]
            cutoff_date_val = cutoff["cutoff_commit_date"]
        else:
            cutoff_info = find_cutoff_commit(actual_repo_path)
            if not cutoff_info:
                logger.warning("[Dataset C] No cutoff commit found for %s", repo_name)
                return False, []
            cutoff_sha = cutoff_info["sha"]
            cutoff_date_val = cutoff_info["date"]

        try:
            subprocess.run(
                ["git", "-C", str(actual_repo_path), "checkout", cutoff_sha, "--force"],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except Exception as exc:
            logger.warning(
                "[Dataset C] Checkout failed for %s @ %s: %s",
                repo_name,
                cutoff_sha[:8],
                exc,
            )
            return False, []

        test_files = find_test_files_at_commit(
            actual_repo_path, language if language != "unknown" else None
        )
        if not test_files:
            logger.debug(
                "[Dataset C] No test files in %s at cutoff %s",
                repo_name,
                cutoff_sha[:8],
            )
            return True, []

        logger.info(
            "[Dataset C] %s: %d test files at cutoff %s",
            repo_name,
            len(test_files),
            cutoff_sha[:8],
        )

        repo_fixtures: List[Dict[str, Any]] = []
        for test_file in test_files:
            try:
                file_fixtures = extractor._extract_from_snapshot_file(
                    repo_path=actual_repo_path,
                    file_path=test_file,
                    language=language,
                    cutoff_commit_sha=cutoff_sha,
                    cutoff_commit_date=cutoff_date_val,
                )
                repo_fixtures.extend(file_fixtures)
            except Exception as exc:
                logger.debug(
                    "[Dataset C] Failed to extract %s in %s: %s",
                    test_file,
                    repo_name,
                    exc,
                )

        if repo_fixtures:
            logger.info(
                "[Dataset C] %s: %d fixtures extracted",
                repo_name,
                len(repo_fixtures),
            )
            return True, [
                (repo, {**fixture, "repo_full_name": repo_name, "language": language})
                for fixture in repo_fixtures
            ]
        return True, []


def collect_dataset_c_fixtures(
    agent_repos: List[Dict[str, Any]],
    clones_dir: Path,
    output_db: Path,
    cutoff_csv: Optional[Path] = None,
    workers: int = 4,
    seed: int = 42,
    targets: Optional[Dict[str, int]] = None,
) -> Tuple[Dict[str, int], Path]:
    """Extract human_pre2022 fixtures from a stratified repo sample via snapshot extraction.

    For each repo:
    1. Clone repo if not already present
    2. Determine cutoff commit (last commit before 2022-01-01)
    3. Checkout cutoff commit
    4. Find all test files
    5. Extract ALL fixtures from each test file (no diff filter, no pure-addition gate)
    6. Tag each fixture with agent_type='human_pre2022' and cutoff commit metadata
    7. Persist sampled fixtures to DB
    """
    workers = max(1, int(workers or 1))
    initialise_db(output_db)

    cutoffs: Dict[str, Dict[str, str]] = {}
    if cutoff_csv:
        cutoffs = load_repo_cutoffs(cutoff_csv)

    checkpoint_path = output_db.parent / "dataset_c_checkpoint.json"
    progress_path = output_db.parent / f"{output_db.stem}_dataset_c_progress.json"

    completed_repos, counts = _load_dataset_c_checkpoint(checkpoint_path)
    pending_repos = [r for r in agent_repos if r.get("full_name") not in completed_repos]
    if completed_repos:
        logger.info(
            "[Dataset C] Skipping %d already-persisted repos (%d remaining)",
            len(completed_repos),
            len(pending_repos),
        )

    if not pending_repos:
        logger.info("[Dataset C] All repos already completed")
        return counts, output_db

    logger.info(
        "[Dataset C] Processing %d repos (%d already done)",
        len(pending_repos),
        len(completed_repos),
    )

    if targets is None:
        targets = {}
        with db_session(output_db) as conn:
            cur = conn.execute("""
                SELECT r.language, COUNT(f.id) as c
                FROM fixtures f
                JOIN repositories r ON f.repo_id = r.id
                WHERE f.commit_kind = 'agent'
                GROUP BY r.language
            """)
            for row in cur.fetchall():
                lang = (row[0] or "unknown").lower()
                targets[lang] = int(row[1])
    else:
        targets = dict(targets)

    candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    extractor = AgentFixtureExtractor(
        clones_dir=clones_dir,
        source_db=None,
        start_date="1970-01-01",
    )

    successful_repos: Set[str] = set()

    if workers <= 1:
        for repo in pending_repos:
            success, results = _process_repo(repo, cutoffs, extractor, clones_dir)
            if success:
                successful_repos.add(repo["full_name"])
                candidates.extend(results)
    else:
        def _submit(repo):
            return _process_repo(repo, cutoffs, extractor, clones_dir)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_submit, repo): repo for repo in pending_repos}
            try:
                for future in as_completed(futures):
                    success, results = future.result()
                    if success:
                        successful_repos.add(futures[future]["full_name"])
                        candidates.extend(results)
            except KeyboardInterrupt:
                logger.warning("[Dataset C] Interrupted; saving progress...")
                for fut in futures:
                    fut.cancel()
                _save_dataset_c_checkpoint(checkpoint_path, completed_repos, counts)
                _write_dataset_c_progress(progress_path, completed_repos, counts)
                raise

    completed_repos.update(successful_repos)
    _save_dataset_c_checkpoint(checkpoint_path, completed_repos, counts)
    _write_dataset_c_progress(progress_path, completed_repos, counts)

    flat_candidates = [dict(fixture) for _, fixture in candidates]
    selected = stratified_sample_by_language(flat_candidates, targets, seed=seed)

    repo_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for fixture in selected:
        repo_groups[fixture.get("repo_full_name")].append(fixture)

    for repo_full, fixtures_list in repo_groups.items():
        repo_data = construct_repo_dict(
            full_name=repo_full,
            language=fixtures_list[0].get("language") if fixtures_list else "unknown",
            stars=0,
            forks=0,
        )
        try:
            from collection.human_corpus import _human_fixture_csv_path

            fixture_out_path = _human_fixture_csv_path(
                repo_data["language"], "inter", output_db.parent
            )
            persist_repository_and_fixtures(
                output_db,
                repo_data,
                fixtures_list,
                out_path=fixture_out_path,
                handle_mocks=True,
            )
            counts["repos_persisted"] = counts.get("repos_persisted", 0) + 1
            counts["fixtures_persisted"] = counts.get(
                "fixtures_persisted", 0
            ) + len(fixtures_list)
        except Exception as exc:
            logger.debug("[Dataset C] Failed to persist %s: %s", repo_full, exc)

    totals: Dict[str, int] = {
        "repos_persisted": counts.get("repos_persisted", 0),
        "fixtures_persisted": counts.get("fixtures_persisted", 0),
        "completed_repos": len(completed_repos),
    }
    logger.info(
        "[Dataset C] Complete: %d repos, %d fixtures",
        len(completed_repos),
        counts.get("fixtures_persisted", 0),
    )
    return totals, output_db
