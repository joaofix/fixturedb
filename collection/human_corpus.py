"""
Human corpus collection for between-group comparison.

Collects human-generated fixtures from the same agent-enabled repositories
used for the agent corpus. Commits are scanned in the same temporal window as
the agent dataset, and only non-AI commits that fully add a fixture are kept.
"""

import argparse
import csv
import json
import logging
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any, Set
from collections import defaultdict

from pydriller import Repository

from .cli_utils import (
    add_language_arg,
    add_output_db_arg,
    add_repos_per_language_arg,
    add_repo_dir_arg,
    add_test_commits_csv_arg,
    add_workers_arg,
)
from .config import (
    CLONES_DIR,
    DATA_DIR,
    AGENT_CORPUS_START_DATE,
    HUMAN_CORPUS_CUTOFF_DATE,
    LANGUAGE_CONFIGS,
    EXTRACT_WORKERS,
    COLLECTION_OUTPUT_TAG,
)
from .db import (
    db_session,
    initialise_db,
    mark_global_checkpoint,
    is_global_checkpoint_completed,
    upsert_repository,
    insert_test_commit,
    insert_human_inter_fixture,
    insert_human_inter_fixtures_bulk,
    insert_human_within_fixture,
)
from .agent_corpus import clone_repo_for_commit_scan
from .clone_manager import clone_with_function
from .fixture_extractor import AgentFixtureExtractor
from .test_commit_utils import write_test_commits_csv
from .agent_commit_detector import Tier1RepositoryScanner
from .test_commit_filter import build_pre2021_candidate_pool
from .agent_patterns import AGENT_SIGNATURES, PAPER_AGENT_CONFIG_PATTERNS, PAPER_AGENT_REPOSITORY_LANGUAGES
from .corpus_utils import (
    BaseCorpusStats,
    compute_repo_metadata,
    construct_repo_dict,
    generate_corpus_summary,
    persist_repository_and_fixtures,
)
from .sampling import stratified_sample_by_language
from .utils import (
    _stable_repo_id,
    _normalize_language_filters,
    build_repo_row,
    _date_only,
)
from .logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Dataset C loader
# ---------------------------------------------------------------------------


def load_dataset_c_repos(csv_path: Path) -> list[dict]:
    """Load repos from a Dataset C CSV file.

    Works with both the combined ``dataset_c_sample.csv`` and per-language
    ``dataset_c_{lang}.csv`` files. Returns a list of dicts with keys:
    *full_name*, *language*, *clone_url*.
    """
    repos: list[dict] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = (row.get("repo_name") or "").strip()
            if not name or "/" not in name:
                continue
            repos.append({
                "full_name": name,
                "language": (row.get("language") or "").strip().lower(),
                "clone_url": (row.get("clone_url") or f"https://github.com/{name}.git").strip(),
            })
    logger.info("Loaded %d Dataset C repos from %s", len(repos), csv_path)
    return repos


def _human_fixtures_root(override: Path | None = None) -> Path:
    if override is not None:
        return override
    return Path(__file__).resolve().parents[1] / "fixtures-from-humans" / COLLECTION_OUTPUT_TAG


def _human_fixture_csv_path(language: str, collection_kind: str, override: Path | None = None) -> Path:
    subdir = "same-repo" if collection_kind == "within" else "cross-repo"
    return _human_fixtures_root(override) / subdir / f"{language}_human_fixtures.csv"


def _warn_stale_human_fixture_csvs(fixtures_output_dir: Path | None = None) -> None:
    """Log a warning if stale human fixture CSVs exist from a previous run."""
    root = _human_fixtures_root(fixtures_output_dir)
    same_repo_dir = root / "same-repo"
    if same_repo_dir.exists() and same_repo_dir.is_dir():
        existing = list(same_repo_dir.glob("*_human_fixtures.csv"))
        if existing:
            logger.warning(
                "[Human Corpus] Found %d existing human fixture CSV(s) in %s "
                "from a previous run. These will be overwritten with fresh data.",
                len(existing),
                same_repo_dir,
            )
            for p in sorted(existing):
                logger.warning("[Human Corpus]   %s (%d bytes)", p.name, p.stat().st_size)


def _load_inter_checkpoint(inter_checkpoint: Path) -> tuple[set[str], dict]:
    """Load inter-repo resume state from disk."""
    completed: set[str] = set()
    counts_local = {"repos_persisted": 0, "fixtures_persisted": 0}
    if inter_checkpoint.exists():
        try:
            with inter_checkpoint.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            completed.update(data.get("completed_repos", []))
            counts_local.update(data.get("counts", {}))
        except Exception:
            logger.debug("Failed to load inter checkpoint %s", inter_checkpoint)
    return completed, counts_local


def _save_inter_checkpoint(
    inter_checkpoint: Path, completed: set[str], counts_local: dict
) -> None:
    """Persist inter-repo resume state to disk."""
    try:
        inter_checkpoint.parent.mkdir(parents=True, exist_ok=True)
        with inter_checkpoint.open("w", encoding="utf-8") as fh:
            json.dump(
                {"completed_repos": sorted(completed), "counts": counts_local},
                fh,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        logger.debug("Failed to save inter checkpoint %s", inter_checkpoint)


def _write_inter_progress(
    inter_progress_file: Path, completed: set[str], counts_local: dict
) -> None:
    """Write a small progress snapshot for the inter-repo collector."""
    try:
        inter_progress_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "repos_persisted": counts_local.get("repos_persisted", 0),
            "fixtures_persisted": counts_local.get("fixtures_persisted", 0),
            "completed_repos_count": len(completed),
        }
        with inter_progress_file.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        logger.debug("Failed to write inter progress %s", inter_progress_file)


def _collect_inter_human_candidates(
    agent_repos: list[dict],
    clones_dir: Path,
    scanner: Tier1RepositoryScanner,
    extractor: AgentFixtureExtractor,
    candidate_map: dict[str, list[dict]],
) -> list[tuple[dict, dict]]:
    """Collect complete human fixture candidates from agent-enabled repositories."""
    candidates: list[tuple[dict, dict]] = []

    for repo in agent_repos:
        repo_name = repo["full_name"]
        repo_path = clones_dir / repo_name.replace("/", "__")

        if repo_path.exists() and (repo_path / ".git" / "shallow").exists():
            shutil.rmtree(repo_path, ignore_errors=True)

        with clone_with_function(
            clone_repo_for_commit_scan,
            repo.get("clone_url", ""),
            repo_path,
        ) as managed_repo_path:
            if managed_repo_path is None:
                logger.debug("[Human Inter] clone failed for %s; skipping", repo_name)
                continue

            human_commits = {}
            if candidate_map and repo_name in candidate_map:
                for row in candidate_map[repo_name]:
                    sha = (row.get("commit_sha") or "").strip()
                    date = (row.get("commit_date") or "").strip()
                    if sha and date and date <= HUMAN_CORPUS_CUTOFF_DATE:
                        human_commits[sha] = "human"
            else:
                try:
                    commit_roles = scanner.scan_repo_commit_roles(
                        managed_repo_path,
                        start_date="1970-01-01",
                        language=repo.get("language"),
                        detect_test_files=True,
                    )
                except Exception as e:
                    logger.debug("[Human Inter] scan failed for %s: %s", repo_name, e)
                    continue

                human_commits = {
                    c.commit_sha: "human"
                    for c in commit_roles
                    if c.commit_role == "human"
                    and getattr(c, "is_test_commit", False)
                    and (c.commit_date or "") <= HUMAN_CORPUS_CUTOFF_DATE
                }

            if not human_commits:
                continue

            fixtures = extractor._extract_from_agent_commits(
                repo_name=repo_name, commits=human_commits
            )
            fixtures = [f for f in fixtures if f.get("is_complete_addition")]
            if not fixtures:
                continue

            for fixture in fixtures:
                fixture["repo_full_name"] = repo_name
                fixture["language"] = repo.get("language")
                candidates.append((repo, fixture))

    return candidates


@dataclass
class HumanCorpusStats(BaseCorpusStats):
    """Statistics for human corpus collection (inherits from base)."""

    pass


def select_human_corpus_repositories(
    repo_qc_dir: Path,
    repos_per_language: Optional[int] = None,
    language: Optional[str] = None,
    require_fixture_repo_list: bool = False,
) -> list[dict]:
    """
    Select agent-enabled repositories for human corpus collection.

    Queries the repo-QC CSV exports for repositories with agent config files.

    Args:
        repo_qc_dir: Directory containing *_agent_repo.csv files
        repos_per_language: Optional per-language cap. None means include all rows.
        language: Optional filter to single language
        require_fixture_repo_list: If True, require repositories to come only from
            *_agent_fixture_repos.csv files and fail otherwise.

    Returns:
        List of repository dicts with required metadata
    """
    # Backwards-compatible behaviour: if a SQLite corpus DB path is provided,
    # query the `repositories` table for pre-2021 repos. Otherwise fall back to
    # reading repo-QC CSV exports in `repo_qc_dir`.
    repo_path = Path(repo_qc_dir)
    selected: list[dict] = []

    if repo_path.exists() and repo_path.is_file():
        # Treat as corpus DB
        import sqlite3

        conn = sqlite3.connect(str(repo_path))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, github_id, full_name, language, stars, forks, description,
                   topics, created_at, pushed_at, clone_url, status, num_contributors, num_test_files
            FROM repositories
            WHERE created_at >= ? AND status IN ('analysed', 'cloned')
            ORDER BY language ASC, created_at ASC
            """,
            (AGENT_CORPUS_START_DATE,),  # Use agent temporal window (post-2025)
        )
        rows = cur.fetchall()
        conn.close()

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            (
                _id,
                github_id,
                full_name,
                lang,
                stars,
                forks,
                description,
                topics,
                created_at,
                pushed_at,
                clone_url,
                status,
                num_contributors,
                num_test_files,
            ) = row

            lang = (lang or "unknown").strip().lower()
            if language and lang != language:
                continue
            if lang not in LANGUAGE_CONFIGS:
                continue

            repo_row = {
                "id": _id,
                "github_id": github_id,
                "full_name": full_name,
                "language": lang,
                "stars": stars,
                "forks": forks,
                "description": description or "",
                "topics": topics or "[]",
                "created_at": created_at or "",
                "pushed_at": pushed_at or "",
                "clone_url": clone_url or f"https://github.com/{full_name}.git",
                "num_contributors": num_contributors or 0,
                "status": status,
            }
            grouped.setdefault(lang, [])
            grouped[lang].append(repo_row)

        for lang in [language] if language else list(LANGUAGE_CONFIGS.keys()):
            if not lang:
                continue
            lang_repos = grouped.get(lang, [])
            selected.extend(
                lang_repos
                if repos_per_language is None
                else lang_repos[:repos_per_language]
            )

        return selected

    # Fallback: read repo-QC CSVs
    grouped: dict[str, list[dict]] = {}
    # First preference: per-language agent fixture repo lists produced by
    # the agent extraction step. These files list repositories that actually
    # yielded agent fixtures and should be used as the canonical selection.
    project_root = Path(__file__).resolve().parents[1]
    # Prefer fixture lists in the provided repo_qc_dir (backwards compatible
    # with earlier behavior), then fall back to the project-level fixtures
    # directory used by centralized runs.
    # Prefer fixture lists in the provided repo_qc_dir (backwards compatible
    # with earlier behavior), but also fall back to the project-level
    # `fixtures-from-agents` so shared fixture lists remain discoverable even
    # when the caller points repo_qc_dir at a different CSV directory.
    candidate_dirs = []
    try:
        local_fixture_dir = Path(repo_qc_dir) / "fixtures-from-agents"
        if local_fixture_dir.exists() and local_fixture_dir.is_dir():
            candidate_dirs.append(local_fixture_dir)
        elif require_fixture_repo_list:
            # When strict mode is on and the repo_qc_dir doesn't have its own
            # fixtures-from-agents/ subdirectory, fall back to the project-level
            # fixture lists (fixtures-from-agents/repos/).
            project_fixture_dir = project_root / "fixtures-from-agents"
            if project_fixture_dir.exists() and project_fixture_dir.is_dir():
                logger.info(
                    "[Human Corpus] No local fixture-repo lists at %s; "
                    "falling back to project-level %s",
                    local_fixture_dir,
                    project_fixture_dir,
                )
                candidate_dirs.append(project_fixture_dir)
    except Exception:
        # If resolution fails for any reason, do not add the project-level fallback
        pass
    for fixture_list_dir in candidate_dirs:
        if fixture_list_dir.exists() and fixture_list_dir.is_dir():
            for search_dir in [fixture_list_dir, fixture_list_dir / "repos"]:
                if not search_dir.is_dir():
                    continue
                for fpath in sorted(search_dir.glob("*_agent_fixture_repos.csv")):
                    with fpath.open("r", encoding="utf-8", newline="") as fh:
                        reader = csv.DictReader(fh)
                        for row in reader:
                            repo_name = (
                                row.get("repo_name") or row.get("full_name") or ""
                            ).strip()
                            lang = (row.get("language") or "unknown").strip().lower()
                            if not repo_name or "/" not in repo_name:
                                continue
                            if language and lang != language:
                                continue
                            repo_row = build_repo_row(
                                repo_name,
                                lang,
                            )
                            grouped.setdefault(lang, [])
                            if repo_name not in {r["full_name"] for r in grouped[lang]}:
                                grouped[lang].append(repo_row)

    # If we found fixture-list repos, return those (respecting per-language cap)
    if grouped:
        for lang in [language] if language else list(LANGUAGE_CONFIGS.keys()):
            if not lang:
                continue
            lang_repos = grouped.get(lang, [])
            selected.extend(
                lang_repos
                if repos_per_language is None
                else lang_repos[:repos_per_language]
            )
        return selected

    if require_fixture_repo_list:
        raise ValueError(
            "Strict within-mode requires *_agent_fixture_repos.csv under "
            f"{Path(repo_qc_dir) / 'fixtures-from-agents'}"
        )
    # New fallback: accept per-language human test-commit CSVs produced earlier
    # e.g., python_human_test_commit.csv. These contain `repo_name` and
    # `language` columns and can be used to select repositories directly.
    # Increase CSV field size limit to handle very large `test_file_paths` fields
    try:
        csv.field_size_limit(10**7)
    except Exception:
        pass

    for csv_path in sorted(Path(repo_qc_dir).glob("*_human_test_commit.csv")):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name:
                    continue
                if language and lang != language:
                    continue
                repo_row = build_repo_row(
                    repo_name,
                    lang,
                )
                grouped.setdefault(lang, [])
                if repo_name not in {r["full_name"] for r in grouped[lang]}:
                    grouped[lang].append(repo_row)

    # Prefer agent test-commit CSVs (if present) which indicate positive
    # detection of agent activity in test files. If such files exist under
    # the `tests_commits` subdirectory of `repo_qc_dir`, use those repo
    # names as the canonical selection. Otherwise fall back to repo QC CSVs.
    # CSVs as before.
    tests_commits_dir = Path(repo_qc_dir) / "tests_commits"

    agent_test_repos: set[str] = set()
    if tests_commits_dir.exists() and tests_commits_dir.is_dir():
        for tpath in sorted(tests_commits_dir.glob("*_agent_test_commit.csv")):
            with tpath.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    repo_name = (
                        row.get("repo_name") or row.get("full_name") or ""
                    ).strip()
                    lang = (row.get("language") or "unknown").strip().lower()
                    if not repo_name or "/" not in repo_name:
                        continue
                    if language and lang != language:
                        continue
                    agent_test_repos.add((repo_name, lang))

    repo_csv_paths = sorted(
        Path(repo_qc_dir).glob("*_agent_repo.csv"), key=lambda path: path.name
    )

    for csv_path in repo_csv_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if str(row.get("has_agent_config") or "").strip().lower() not in {
                    "1",
                    "true",
                }:
                    continue

                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name:
                    continue
                if language and lang != language:
                    continue

                # If agent test-commit selection exists, restrict to that set
                if agent_test_repos and (repo_name, lang) not in agent_test_repos:
                    continue

                repo_row = build_repo_row(
                    repo_name,
                    lang,
                    stars=row.get("stars") or 0,
                    clone_url=row.get("clone_url"),
                    num_contributors=row.get("num_contributors") or 0,
                )
                grouped.setdefault(lang, [])
                if repo_name not in {r["full_name"] for r in grouped[lang]}:
                    grouped[lang].append(repo_row)

    for lang in [language] if language else list(LANGUAGE_CONFIGS.keys()):
        if not lang:
            continue
        lang_repos = grouped.get(lang, [])
        selected.extend(
            lang_repos
            if repos_per_language is None
            else lang_repos[:repos_per_language]
        )

    return selected


class HumanCorpusCollector:
    """Collect human-authored fixtures from agent-enabled repositories."""

    def __init__(
        self,
        corpus_db_path: Path,
        clones_dir: Path = CLONES_DIR,
        output_db: Path | None = None,
        repo_qc_dir: Path | None = None,
        test_commits_csv: Path | None = None,
        fixtures_output_dir: Path | None = None,
    ):
        """
        Initialize human corpus collector.

        Args:
            corpus_db_path: Path to source corpus.db (kept for metadata lookups)
            clones_dir: Directory for temporary clones
            output_db: Path to output database (default: data/between-group.db)
            repo_qc_dir: Directory containing *_agent_repo.csv files
            test_commits_csv: Directory containing test-commit CSVs
            fixtures_output_dir: Override for fixture CSV output directory
        """
        self.corpus_db_path = Path(corpus_db_path)
        self.clones_dir = Path(clones_dir)
        self.output_db = (
            Path(output_db) if output_db else (DATA_DIR / "between-group.db")
        )
        self.test_commits_csv = Path(test_commits_csv) if test_commits_csv else None
        self.fixtures_output_dir = (
            Path(fixtures_output_dir) if fixtures_output_dir else None
        )
        project_root = Path(__file__).resolve().parents[1]
        self.repo_qc_dir = (
            Path(repo_qc_dir)
            if repo_qc_dir
            else (project_root / "github-search-agent" / "agent_repositories")
        )

    def _validate_quality_filters(
        self, repo_path: Path, language: str, repo_name: str
    ) -> tuple[bool, Optional[str]]:
        since_date = datetime.fromisoformat(AGENT_CORPUS_START_DATE)
        try:
            num_commits = sum(
                1
                for _ in Repository(str(repo_path), since=since_date).traverse_commits()
            )
        except Exception as e:
            logger.debug(f"Failed to count commits for {repo_name}: {e}")
            return False, "commit_count_failed"

        if num_commits == 0:
            return False, "no_commits_in_agent_window"

        return True, None

    def _process_human_repository(self, repo: dict) -> dict:
        """Process one repository end-to-end up to, but not including, DB writes."""
        repo_name = repo["full_name"]
        language_name = repo["language"]
        repo_path = self.clones_dir / repo_name.replace("/", "__")

        logger.info(f"[Human Corpus] Processing {repo_name}")

        if repo_path.exists() and (repo_path / ".git" / "shallow").exists():
            shutil.rmtree(repo_path, ignore_errors=True)

        # Clone inside a managed context to guarantee cleanup and respect disk guards.
        logger.info(
            f"[Human Corpus] Cloning {repo_name} with full history for commit scan..."
        )
        with clone_with_function(
            clone_repo_for_commit_scan, repo.get("clone_url", ""), repo_path
        ) as managed_repo_path:
            if managed_repo_path is None:
                return {
                    "repo_name": repo_name,
                    "language_name": language_name,
                    "status": "clone_failed",
                    "skip_reason": "clone_failed",
                    "test_commit_rows": [],
                    "fixtures": [],
                }

            passes_qc, skip_reason = self._validate_quality_filters(
                managed_repo_path, language_name, repo_name
            )
            if not passes_qc:
                return {
                    "repo_name": repo_name,
                    "language_name": language_name,
                    "status": "qc_failed",
                    "skip_reason": skip_reason or "commit_count_failed",
                    "test_commit_rows": [],
                    "fixtures": [],
                }

            scanner = Tier1RepositoryScanner(self.corpus_db_path)
            extractor = AgentFixtureExtractor(
                clones_dir=self.clones_dir,
                source_db=self.corpus_db_path,
                start_date=AGENT_CORPUS_START_DATE,
            )

            # Compute control variables using shared utility
            metadata = compute_repo_metadata(repo, AGENT_CORPUS_START_DATE)
            domain = metadata["domain"]
            star_tier = metadata["star_tier"]
            repo_age = metadata["repo_age_years"]
            test_commit_rows, fixtures = self._scan_and_extract(
                managed_repo_path, language_name, repo_name, scanner, extractor
            )

            return {
                "repo_name": repo_name,
                "language_name": language_name,
                "status": "ok",
                "skip_reason": None,
                "domain": domain,
                "star_tier": star_tier,
                "repo_age": repo_age,
                "num_contributors": repo.get("num_contributors", 0),
                "repo_data": construct_repo_dict(
                    full_name=repo_name,
                    language=language_name,
                    stars=repo.get("stars", 0),
                    forks=repo.get("forks", 0),
                    description=repo.get("description", "") or "",
                    topics=repo.get("topics", "[]") or "[]",
                    created_at=repo.get("created_at", ""),
                    pushed_at=repo.get("pushed_at", ""),
                    clone_url=repo.get("clone_url", ""),
                    github_id=repo.get("github_id"),
                    num_contributors=repo.get("num_contributors", 0),
                    domain=domain,
                    star_tier=star_tier,
                    repo_age_years=repo_age,
                ),
                "test_commit_rows": test_commit_rows,
                "fixtures": fixtures,
            }

    def _scan_and_extract(
        self,
        managed_repo_path: Path,
        language_name: str,
        repo_name: str,
        scanner: Tier1RepositoryScanner,
        extractor: AgentFixtureExtractor,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Scan commit roles for a repository and extract complete human fixtures.

        This helper runs the provided `scanner` to obtain commit role objects,
        filters those commits to human test commits, and then invokes the
        `extractor` to extract fixtures from the matching commits. Only
        fixtures marked as `is_complete_addition` are returned.

        Args:
            managed_repo_path (Path): Path to the checked-out repository.
            language_name (str): Repository language (e.g., 'python').
            repo_name (str): GitHub repository full name (owner/name).
            scanner (Tier1RepositoryScanner-like): Object exposing
                `scan_repo_commit_roles(repo_path, start_date, language, detect_test_files)`.
            extractor (AgentFixtureExtractor-like): Object exposing
                `_extract_from_agent_commits(repo_name, commits)`.

        Returns:
            tuple: (test_commit_rows, fixtures)
                - test_commit_rows (list[dict]): Rows suitable for CSV/DB insertion
                  describing each human test commit discovered.
                - fixtures (list[dict]): Extracted fixture dictionaries filtered
                  to only include complete additions.
        """
        commit_roles = scanner.scan_repo_commit_roles(
            managed_repo_path,
            start_date=AGENT_CORPUS_START_DATE,
            language=language_name,
            detect_test_files=True,
        )

        test_commit_rows = [
            {
                "repo_name": repo_name,
                "commit_sha": commit.commit_sha,
                "commit_role": commit.commit_role,
                "agent_type": commit.agent_type,
                "commit_date": commit.commit_date,
                "language": language_name,
                "test_file_count": len(commit.test_files),
                "test_file_paths": json.dumps(commit.test_files, ensure_ascii=False),
            }
            for commit in commit_roles
            if commit.commit_role == "human" and commit.is_test_commit
        ]

        human_commits = {
            commit.commit_sha: "human"
            for commit in commit_roles
            if commit.commit_role == "human" and commit.is_test_commit
        }

        fixtures = []
        if human_commits:
            logger.info(
                f"[Human Corpus] {repo_name}: scanning {len(human_commits)} human commits"
            )
            fixtures = extractor._extract_from_agent_commits(
                repo_name=repo_name, commits=human_commits
            )
            fixtures = [
                fixture for fixture in fixtures if fixture.get("is_complete_addition")
            ]

        return test_commit_rows, fixtures

    def run(
        self,
        repos_per_language: Optional[int] = None,
        language: Optional[str] = None,
        only_write_test_commits: bool = False,
        workers: Optional[int] = None,
        seed: int = 42,
    ) -> tuple[HumanCorpusStats, Path]:
        """
        Collect human corpus with sequential language processing and progress tracking.

        Safe checkpoint: After all repos for a language are processed, CSV is written
        before moving to the next language.

        Args:
            repos_per_language: Optional per-language cap. None means include all rows.
            language: Optional filter to single language
            workers: Optional number of parallel workers. None uses the configured default.
            seed: Random seed (for reproducibility)

        Returns:
            (stats, output_db_path)
        """
        _ = seed  # Kept for reproducibility hooks
        initialise_db(self.output_db)

        workers = max(1, int(workers or EXTRACT_WORKERS))

        stats = HumanCorpusStats()
        all_test_commit_rows: list[dict] = []
        test_commit_rows_by_language: dict[str, list[dict]] = defaultdict(list)

        # If running in write-only mode and the repo_qc_dir already contains
        # per-language human test-commit CSVs, copy them to the output and exit.
        if only_write_test_commits:
            existing = list(Path(self.repo_qc_dir).glob("*_human_test_commit.csv"))
            if existing:
                out_dir = Path(self.test_commits_csv)
                # If input and output are the same directory, nothing to do.
                if out_dir.resolve() == Path(self.repo_qc_dir).resolve():
                    logger.info(
                        f"Input and output directory are the same ({out_dir}); skipping copy"
                    )
                    return stats, self.output_db
                out_dir.mkdir(parents=True, exist_ok=True)
                for p in sorted(existing):
                    shutil.copy(p, out_dir / p.name)
                logger.info(
                    f"Copied {len(existing)} human test-commit CSVs to {out_dir}"
                )
                return stats, self.output_db

        selected_repos = select_human_corpus_repositories(
            self.repo_qc_dir,
            repos_per_language,
            language,
            require_fixture_repo_list=True,
        )

        # Warn if stale fixture CSVs exist from a previous run
        _warn_stale_human_fixture_csvs(self.fixtures_output_dir)

        within_all_step = "human_within_complete:all"

        def within_step(lang_name: str) -> str:
            return f"human_within_complete:{lang_name}"

        logger.info(
            f"[Human Corpus] Selected {len(selected_repos)} agent-enabled repositories"
        )
        logger.info(f"[Human Corpus] Using {workers} worker(s)")

        # Group repos by language for sequential processing
        repos_by_language: dict[str, list[dict]] = defaultdict(list)
        for repo in selected_repos:
            lang = repo.get("language", "unknown").lower()
            repos_by_language[lang].append(repo)

        completed_languages: set[str] = set()
        with db_session(self.output_db) as conn:
            if is_global_checkpoint_completed(conn, within_all_step):
                logger.info(
                    "[Human Corpus] Completion checkpoint found; skipping within collection"
                )
                return stats, self.output_db

            for lang in repos_by_language:
                if is_global_checkpoint_completed(conn, within_step(lang)):
                    completed_languages.add(lang)

        if language and language.lower() in completed_languages:
            logger.info(
                f"[Human Corpus] Completion checkpoint found for {language}; skipping within collection"
            )
            return stats, self.output_db

        repos_by_language = {
            lang: repos
            for lang, repos in repos_by_language.items()
            if lang not in completed_languages
        }

        if not repos_by_language:
            with db_session(self.output_db) as conn:
                mark_global_checkpoint(conn, within_all_step)
            logger.info(
                "[Human Corpus] All selected languages already completed; skipping within collection"
            )
            return stats, self.output_db

        logger.info(
            f"[Human Corpus] Languages to process: {', '.join(sorted(repos_by_language.keys()))}"
        )
        for lang, repos in sorted(repos_by_language.items()):
            logger.info(f"[Human Corpus]   {lang}: {len(repos)} repositories")

        repo_ages = []
        repo_contributors = []
        language_progress: dict[str, dict] = {}
        progress_lock = threading.Lock()
        progress_file = self._human_progress_file()

        def log_progress():
            """Log progress every 3 minutes."""
            while not hasattr(log_progress, "stop_flag") or not log_progress.stop_flag:
                with progress_lock:
                    completed_total = stats.repos_scanned
                    fixtures_total = stats.fixtures_collected
                    logger.info(
                        f"[Human Corpus Progress] {completed_total} repos scanned, "
                        f"{stats.repos_passed_qc} passed QC, {fixtures_total} fixtures collected"
                    )
                    for lang in sorted(language_progress.keys()):
                        total_repos = language_progress[lang]["total_repos"]
                        completed = language_progress[lang]["completed"]
                        pct = (completed / total_repos * 100) if total_repos > 0 else 0
                        avg_fixtures = language_progress[lang]["avg_fixtures_per_repo"]
                        logger.info(
                            f"  {lang}: {completed}/{total_repos} ({pct:.1f}%) "
                            f"~{avg_fixtures:.0f} fixtures/repo"
                        )
                try:
                    self._write_human_progress_snapshot(
                        progress_file, stats, language_progress
                    )
                except Exception:
                    logger.debug("Failed to write progress snapshot")
                time.sleep(180)

        log_progress.stop_flag = False
        progress_thread = threading.Thread(target=log_progress, daemon=True)
        progress_thread.start()

        try:
            for lang_idx, (current_lang, lang_repos) in enumerate(
                sorted(repos_by_language.items()), 1
            ):
                logger.info(
                    f"[Human Corpus] Processing language {lang_idx}/{len(repos_by_language)}: {current_lang} ({len(lang_repos)} repos)"
                )
                language_progress[current_lang] = {
                    "total_repos": len(lang_repos),
                    "completed": 0,
                    "avg_fixtures_per_repo": 0,
                }
                self._process_human_within_language(
                    current_lang=current_lang,
                    lang_repos=lang_repos,
                    workers=workers,
                    only_write_test_commits=only_write_test_commits,
                    stats=stats,
                    progress_lock=progress_lock,
                    language_progress=language_progress,
                    repo_ages=repo_ages,
                    repo_contributors=repo_contributors,
                    all_test_commit_rows=all_test_commit_rows,
                    test_commit_rows_by_language=test_commit_rows_by_language,
                    progress_file=progress_file,
                )

        finally:
            # Stop progress logging thread
            log_progress.stop_flag = True
            progress_thread.join(timeout=5)

        # Compute means
        if repo_ages:
            stats.mean_repo_age_years = sum(repo_ages) / len(repo_ages)
        if repo_contributors:
            stats.mean_contributors = sum(repo_contributors) / len(repo_contributors)

        if self.test_commits_csv:
            # When an explicit file path is requested, write the combined rows.
            if not (only_write_test_commits or self.test_commits_csv.suffix == ""):
                out_dir = Path(self.test_commits_csv)
                write_test_commits_csv(all_test_commit_rows, self.test_commits_csv)

        # Generate summary
        self._generate_summary(stats)

        with db_session(self.output_db) as conn:
            if all(
                is_global_checkpoint_completed(conn, within_step(lang))
                for lang in repos_by_language
            ):
                mark_global_checkpoint(conn, within_all_step)

        try:
            self._write_human_progress_snapshot(progress_file, stats, language_progress)
        except Exception:
            logger.debug("Failed to write final progress file")

        return stats, self.output_db

    def collect_inter_human(
        self,
        agent_repos: list[dict],
        targets: Optional[dict] = None,
        workers: Optional[int] = None,
        seed: int = 42,
        raw_commits_dir: Optional[Path] = None,
    ) -> tuple[HumanCorpusStats, Path]:
        """
        Collect inter-repository human fixtures to match agent per-language totals.

        This builds a pre-2021 candidate pool from agent-enabled repos, extracts
        fixtures from human commits dated on-or-before `HUMAN_CORPUS_CUTOFF_DATE`,
        runs a stratified sampler, and persists the sampled rows into
        `human_inter_fixtures`.

        Fallback strategies (expand pool / reduce targets) are intentionally
        not implemented here.
        """
        workers = max(1, int(workers or EXTRACT_WORKERS))
        initialise_db(self.output_db)

        stats = HumanCorpusStats()
        candidates: list[dict] = []

        # Checkpoint / progress paths for inter-run resumability
        inter_checkpoint = Path(self.output_db).parent / "human_inter_checkpoint.json"
        inter_progress_file = (
            Path(self.output_db).parent
            / f"{Path(self.output_db).stem}_human_inter_progress.json"
        )

        logger.info(
            "[Human Inter] Building candidate pool from %d repos", len(agent_repos)
        )
        candidates = self._build_inter_candidates(agent_repos, raw_commits_dir)

        # Compute targets if not provided: count agent fixtures per language
        if targets is None:
            targets = {}
            with db_session(self.output_db) as conn:
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

        # Flatten candidate fixtures into plain dicts with language and repo_id placeholder
        flat_candidates = []
        for repo, f in candidates:
            # include repo metadata and fixture
            flat = dict(f)
            flat["repo_full_name"] = repo["full_name"]
            flat["language"] = repo.get("language")
            flat_candidates.append(flat)

        # Run stratified sampler
        selected = stratified_sample_by_language(flat_candidates, targets, seed=seed)

        # Persist selected fixtures into DB in batches per repository to reduce repeated upserts
        # Then insert all human_inter_fixtures inside a single DB transaction to minimize locking.
        from collections import defaultdict

        repo_groups: dict[str, list[dict]] = defaultdict(list)
        for fixture in selected:
            repo_groups[fixture.get("repo_full_name")].append(fixture)

        counts_local, completed_repos, inserted = self._persist_and_insert_inter(
            selected, inter_checkpoint, inter_progress_file, seed=seed
        )
        stats.fixtures_collected += int(inserted or 0)

        # Generate summary for the inter sample
        self._generate_summary(stats)
        return stats, self.output_db

    def _generate_summary(self, stats: HumanCorpusStats) -> None:
        """Generate and save human corpus summary."""
        generate_corpus_summary(
            stats=stats,
            corpus_name="human",
            output_db=self.output_db,
            temporal_scope=f"since {AGENT_CORPUS_START_DATE}",
            extra_metadata={
                "dataset_temporal_window": AGENT_CORPUS_START_DATE,
            },
            output_dir=self.output_db.parent,
        )

    def _build_inter_candidates(
        self, agent_repos: List[Dict[str, Any]], raw_commits_dir: Optional[Path]
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Construct the pre-2021 candidate pool of human fixtures from agent repos.

        Args:
            agent_repos: list of repository metadata dicts.
            raw_commits_dir: optional path to pre-2021 raw commit CSV exports.

        Returns:
            List of (repo_dict, fixture_dict) candidate pairs.
        """
        logger.info(
            "[Human Inter] Building candidate pool from %d repos", len(agent_repos)
        )
        scanner = Tier1RepositoryScanner(self.corpus_db_path)
        extractor = AgentFixtureExtractor(
            clones_dir=self.clones_dir,
            source_db=self.corpus_db_path,
            start_date="1970-01-01",
        )

        candidate_map = {}
        if raw_commits_dir:
            try:
                candidate_map = build_pre2021_candidate_pool(
                    raw_commits_dir, cutoff_date=HUMAN_CORPUS_CUTOFF_DATE
                )
                logger.info(
                    f"[Human Inter] Loaded pre-2021 candidate pool with {len(candidate_map)} repos from {raw_commits_dir}"
                )
            except Exception as e:
                logger.debug(
                    f"Failed to build candidate pool from {raw_commits_dir}: {e}"
                )

        return _collect_inter_human_candidates(
            agent_repos, self.clones_dir, scanner, extractor, candidate_map
        )

    def _persist_and_insert_inter(
        self,
        selected: List[Dict[str, Any]],
        inter_checkpoint: Path,
        inter_progress_file: Path,
        seed: int = 42,
    ) -> Tuple[Dict[str, int], Set[str], int]:
        """Persist per-repo CSVs for selected fixtures and perform coordinated DB insert.

        Returns:
            counts_local: mapping of counters (repos_persisted, fixtures_persisted)
            completed_repos: set of repo full-names successfully persisted
            inserted_count: number of rows inserted into `human_inter_fixtures`
        """
        from collections import defaultdict

        repo_groups: dict[str, list[dict]] = defaultdict(list)
        for fixture in selected:
            repo_groups[fixture.get("repo_full_name")].append(fixture)

        completed_repos, counts_local = _load_inter_checkpoint(inter_checkpoint)
        for repo_full, fixtures_list in repo_groups.items():
            if repo_full in completed_repos:
                logger.debug(
                    "[Human Inter] Skipping already persisted repo %s", repo_full
                )
                continue
            repo_data = construct_repo_dict(
                full_name=repo_full,
                language=(
                    fixtures_list[0].get("language") if fixtures_list else "unknown"
                ),
                stars=0,
                forks=0,
            )
            try:
                fixtures_out_path = _human_fixture_csv_path(
                    repo_data["language"], "inter", self.fixtures_output_dir
                )
                fixture_count = persist_repository_and_fixtures(
                    self.output_db,
                    repo_data,
                    fixtures_list,
                    out_path=fixtures_out_path,
                    handle_mocks=True,
                )
                counts_local["repos_persisted"] = (
                    counts_local.get("repos_persisted", 0) + 1
                )
                counts_local["fixtures_persisted"] = counts_local.get(
                    "fixtures_persisted", 0
                ) + int(fixture_count or 0)
                completed_repos.add(repo_full)
                _save_inter_checkpoint(inter_checkpoint, completed_repos, counts_local)
                _write_inter_progress(
                    inter_progress_file, completed_repos, counts_local
                )
            except Exception as e:
                logger.debug(
                    f"[Human Inter] failed to persist fixtures for {repo_full}: {e}"
                )
                continue

        # Perform coordinated insert and return inserted count
        inserted = 0
        try:
            from .db import insert_human_inter_fixtures_coordinated

            inserted = insert_human_inter_fixtures_coordinated(
                self.output_db, selected, seed=seed, batch_size=1000
            )
        except Exception as e:
            logger.debug(f"[Human Inter] coordinated bulk insert failed: {e}")
        finally:
            _save_inter_checkpoint(inter_checkpoint, completed_repos, counts_local)
            _write_inter_progress(inter_progress_file, completed_repos, counts_local)

        return counts_local, completed_repos, int(inserted or 0)

    def _human_progress_file(self) -> Path:
        """Return the progress snapshot path for within-repo collection."""
        return (
            Path(self.output_db).parent
            / f"{Path(self.output_db).stem}_human_progress.json"
        )

    def _write_human_progress_snapshot(
        self,
        progress_file: Path,
        stats: HumanCorpusStats,
        language_progress: dict[str, dict],
    ) -> None:
        """Write a JSON progress snapshot for the human within-repo collector."""
        data = {
            "repos_scanned": stats.repos_scanned,
            "repos_passed_qc": stats.repos_passed_qc,
            "fixtures_collected": stats.fixtures_collected,
            "test_commits_found": stats.test_commits_found,
            "per_language": {
                lang: {
                    "total_repos": info.get("total_repos", 0),
                    "completed": info.get("completed", 0),
                    "avg_fixtures_per_repo": info.get("avg_fixtures_per_repo", 0),
                }
                for lang, info in language_progress.items()
            },
        }
        try:
            progress_file.parent.mkdir(parents=True, exist_ok=True)
            with progress_file.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            logger.debug("Failed to write progress file %s", progress_file)

    def _process_human_within_language(
        self,
        current_lang: str,
        lang_repos: list[dict],
        workers: int,
        only_write_test_commits: bool,
        stats: HumanCorpusStats,
        progress_lock: threading.Lock,
        language_progress: dict[str, dict],
        repo_ages: list,
        repo_contributors: list,
        all_test_commit_rows: list[dict],
        test_commit_rows_by_language: dict[str, list[dict]],
        progress_file: Path,
    ) -> None:
        """Process one language worth of repositories and persist its outputs."""
        lang_results = []
        lang_all_fixtures = []
        lang_test_commit_rows = []

        if workers <= 1:
            for repo in lang_repos:
                lang_results.append(self._process_human_repository(repo))
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self._process_human_repository, repo): repo
                    for repo in lang_repos
                }
                for future in as_completed(futures):
                    lang_results.append(future.result())

        for result in lang_results:
            with progress_lock:
                stats.repos_scanned += 1
                language_progress[current_lang]["completed"] += 1

            repo_name = result["repo_name"]

            if result["status"] != "ok":
                stats.record_skip(result.get("skip_reason") or "unknown")
                logger.debug(
                    f"[Human Corpus] Skip {repo_name}: {result.get('skip_reason')}"
                )
                continue

            stats.repos_passed_qc += 1

            domain = result["domain"]
            star_tier = result["star_tier"]
            repo_age = result["repo_age"]
            if repo_age is not None:
                repo_ages.append(repo_age)
            if result.get("num_contributors"):
                repo_contributors.append(result["num_contributors"])

            stats.domain_distribution[domain] = (
                stats.domain_distribution.get(domain, 0) + 1
            )
            stats.star_tier_distribution[star_tier] = (
                stats.star_tier_distribution.get(star_tier, 0) + 1
            )

            repo_data = result["repo_data"]
            test_commit_rows = result["test_commit_rows"]
            fixtures = result["fixtures"]

            with db_session(self.output_db) as conn:
                repo_row, _ = upsert_repository(conn, repo_data)
                for test_commit in test_commit_rows:
                    test_commit["repo_id"] = repo_row
                    insert_test_commit(conn, test_commit)

            lang_test_commit_rows.extend(test_commit_rows)
            test_commit_rows_by_language[current_lang].extend(test_commit_rows)
            all_test_commit_rows.extend(test_commit_rows)
            stats.test_commits_found += len(test_commit_rows)

            if fixtures:
                lang_all_fixtures.append((repo_data, fixtures))
                stats.repos_by_language[current_lang] = (
                    stats.repos_by_language.get(current_lang, 0) + 1
                )
            else:
                logger.debug(
                    f"[Human Corpus] No complete human fixtures found in {repo_name}"
                )
                stats.repos_by_language[current_lang] = (
                    stats.repos_by_language.get(current_lang, 0) + 1
                )

            repo_path = self.clones_dir / repo_name.replace("/", "__")
            if repo_path.exists():
                shutil.rmtree(repo_path, ignore_errors=True)
                logger.debug(f"[Human Corpus] Cleaned up clone: {repo_name}")

        if lang_all_fixtures:
            logger.info(
                f"[Human Corpus] Writing {len(lang_all_fixtures)} repositories' fixtures to CSV for {current_lang}"
            )
            fixtures_out_path = _human_fixture_csv_path(current_lang, "within", self.fixtures_output_dir)
            for repo_data, fixtures_list in lang_all_fixtures:
                fixture_count = persist_repository_and_fixtures(
                    self.output_db,
                    repo_data,
                    fixtures_list,
                    out_path=fixtures_out_path,
                    handle_mocks=True,
                )
                with progress_lock:
                    stats.fixtures_collected += fixture_count
                    if stats.repos_by_language[current_lang] > 0:
                        language_progress[current_lang]["avg_fixtures_per_repo"] = (
                            stats.fixtures_collected
                            / stats.repos_by_language[current_lang]
                        )

            logger.info(
                f"[Human Corpus] Checkpoint complete for {current_lang}: "
                f"{stats.fixtures_collected} total fixtures collected"
            )
            self._write_human_progress_snapshot(progress_file, stats, language_progress)

        if self.test_commits_csv:
            if only_write_test_commits or self.test_commits_csv.suffix == "":
                out_dir = Path(self.test_commits_csv)
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{current_lang}_human_test_commit.csv"
                write_test_commits_csv(lang_test_commit_rows, out_path)
                self._write_human_progress_snapshot(
                    progress_file, stats, language_progress
                )

        with db_session(self.output_db) as conn:
            mark_global_checkpoint(conn, f"human_within_complete:{current_lang}")


def main(args):
    """CLI entry point for human corpus collection."""
    collector = HumanCorpusCollector(
        corpus_db_path=args.corpus_db,
        output_db=args.output_db,
        repo_qc_dir=args.repo_qc_dir,
    )
    stats, db_path = collector.run(
        repos_per_language=args.repos_per_language,
        language=args.language,
        only_write_test_commits=args.only_write_test_commits,
        workers=args.workers,
    )
    logger.info(
        f"Human corpus collection complete: {stats.fixtures_collected} fixtures in {db_path}"
    )


if __name__ == "__main__":
    # Ensure logging is configured for CLI runs so INFO progress messages are visible
    from collection.logging_utils import configure_logging

    configure_logging()
    parser = argparse.ArgumentParser(
        description="Collect human corpus from agent-enabled repositories"
    )
    parser.add_argument(
        "--corpus-db",
        type=Path,
        default=DATA_DIR / "corpus.db",
        help="Path to source corpus.db",
    )
    add_output_db_arg(
        parser,
        None,
        "Path to output between-group.db (default: data/between-group.db)",
    )
    add_repos_per_language_arg(parser, None)
    add_language_arg(parser, LANGUAGE_CONFIGS.keys())
    add_test_commits_csv_arg(
        parser,
        "Directory path to write per-language human test-commit CSVs and exit",
    )
    parser.add_argument(
        "--only-write-test-commits",
        action="store_true",
        help="If set, write per-language human test-commit CSVs and skip fixture extraction",
    )
    add_workers_arg(
        parser,
        EXTRACT_WORKERS,
        "Number of concurrent worker threads for repo processing",
    )
    add_repo_dir_arg(
        parser,
        None,
        "Directory containing repo-QC CSVs or per-language human test-commit CSVs (overrides default)",
    )
    args = parser.parse_args()
    # If user provided a test-commits path, wire it into the collector and run in write-only mode
    if args.test_commits_csv:
        args.test_commits_csv = Path(args.test_commits_csv)
        collector = HumanCorpusCollector(
            corpus_db_path=args.corpus_db,
            output_db=args.output_db,
            test_commits_csv=args.test_commits_csv,
            repo_qc_dir=args.repo_qc_dir,
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            language=args.language,
            only_write_test_commits=True,
            workers=args.workers,
        )
        logger.info(f"Wrote human test-commit CSVs to {args.test_commits_csv}")
    else:
        # Build collector with optional repo_qc_dir and run normally
        collector = HumanCorpusCollector(
            corpus_db_path=args.corpus_db,
            output_db=args.output_db,
            repo_qc_dir=args.repo_qc_dir,
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            language=args.language,
            only_write_test_commits=False,
            workers=args.workers,
        )
        logger.info(
            f"Human corpus collection complete: {stats.fixtures_collected} fixtures in {db_path}"
        )
