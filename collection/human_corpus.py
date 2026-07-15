"""
Builds Dataset B: human-authored fixtures, within-repo matched control.

Collects human-generated fixtures from the same agent-enabled repositories
used for the agent corpus. Commits are scanned in the same temporal window as
the agent dataset, and only non-AI commits that fully add a fixture are kept.
Entry point: `python -m collection extract-fixtures --dataset b`. See
agent_corpus.py (Dataset A) and dataset_c.py (Dataset C, the cross-repo
baseline) for the other two datasets. Repository selection lives in
human_corpus_repo_selection.py, kept separate since it's pure CSV/DB
querying with no fixture-extraction logic of its own.
"""

import csv
import json
import shutil
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydriller import Repository
from tqdm import tqdm

from . import paths
from .clone_primitives import clone_repo_for_commit_scan
from .config import (
    AGENT_CORPUS_START_DATE,
    CLONES_DIR,
    COLLECTION_OUTPUT_TAG,
    EXTRACT_WORKERS,
)
from .corpus_utils import (
    BaseCorpusStats,
    compute_repo_metadata,
    construct_repo_dict,
    persist_repository_and_fixtures,
)
from .db import (
    db_session,
    initialise_db,
    insert_test_commit,
    is_global_checkpoint_completed,
    mark_global_checkpoint,
    upsert_repository,
)
from .ephemeral_clone import clone_with_function
from .fixture_extractor import AgentFixtureExtractor
from .human_corpus_repo_selection import select_human_corpus_repositories
from .logging_utils import get_logger
from .test_commit_utils import write_test_commits_csv
from .tiered_agent_corpus_scanner import Tier1RepositoryScanner

logger = get_logger(__name__)


def _human_fixtures_dir(dataset: str, override: Path | None = None) -> Path:
    """Fixture output dir for `dataset` ('b' or 'c'), default datasets/{dataset}/fixtures."""
    if override is not None:
        return override
    return paths.stage_dir(dataset, "fixtures") / COLLECTION_OUTPUT_TAG


def _human_fixture_csv_path(
    language: str, dataset: str, override: Path | None = None
) -> Path:
    return _human_fixtures_dir(dataset, override) / f"{language}_fixtures.csv"


def _warn_stale_human_fixture_csvs(
    dataset: str, fixtures_output_dir: Path | None = None
) -> None:
    """Log a warning if stale human fixture CSVs exist from a previous run."""
    root = _human_fixtures_dir(dataset, fixtures_output_dir)
    if root.exists() and root.is_dir():
        existing = list(root.glob("*_fixtures.csv"))
        if existing:
            logger.warning(
                "[Human Corpus] Found %d existing human fixture CSV(s) in %s "
                "from a previous run. These will be overwritten with fresh data.",
                len(existing),
                root,
            )
            for p in sorted(existing):
                logger.warning(
                    "[Human Corpus]   %s (%d bytes)", p.name, p.stat().st_size
                )


@dataclass
class HumanCorpusStats(BaseCorpusStats):
    """Statistics for human corpus collection (inherits from base)."""

    pass


class HumanCorpusCollector:
    """Collect human-authored fixtures from agent-enabled repositories."""

    def __init__(
        self,
        corpus_db_path: Path | None = None,
        clones_dir: Path = CLONES_DIR,
        output_db: Path | None = None,
        repo_qc_dir: Path | None = None,
        test_commits_csv: Path | None = None,
        fixtures_output_dir: Path | None = None,
    ):
        """
        Initialize human corpus collector.

        Args:
            corpus_db_path: Path to source corpus.db (default: db/corpus.db).
                Threaded through to Tier1RepositoryScanner/AgentFixtureExtractor,
                but stored and never read by either -- kept for API compatibility,
                not because anything here actually opens that DB.
            clones_dir: Directory for temporary clones
            output_db: Path to output database (default: db/b.db)
            repo_qc_dir: Directory containing *_repo.csv files (default: datasets/b/repos)
            test_commits_csv: Directory containing test-commit CSVs
            fixtures_output_dir: Override for fixture CSV output directory
        """
        self.corpus_db_path = (
            Path(corpus_db_path) if corpus_db_path else paths.corpus_db_path()
        )
        self.clones_dir = Path(clones_dir)
        self.output_db = Path(output_db) if output_db else paths.db_path("b")
        self.test_commits_csv = Path(test_commits_csv) if test_commits_csv else None
        self.fixtures_output_dir = (
            Path(fixtures_output_dir) if fixtures_output_dir else None
        )
        self.repo_qc_dir = (
            Path(repo_qc_dir) if repo_qc_dir else paths.stage_dir("b", "repos")
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

        logger.debug(f"[Human Corpus] Processing {repo_name}")

        if repo_path.exists() and (repo_path / ".git" / "shallow").exists():
            shutil.rmtree(repo_path, ignore_errors=True)

        # Clone inside a managed context to guarantee cleanup and respect disk guards.
        logger.debug(
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
                    "commits_accepted": 0,
                    "commits_rejected": 0,
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
                    "commits_accepted": 0,
                    "commits_rejected": 0,
                }

            scanner = Tier1RepositoryScanner(self.corpus_db_path)
            extractor = AgentFixtureExtractor(
                clones_dir=self.clones_dir,
                source_db=self.corpus_db_path,
                start_date=AGENT_CORPUS_START_DATE,
            )

            # Compute control variables using shared utility
            metadata = compute_repo_metadata(dict(repo), AGENT_CORPUS_START_DATE)
            domain = metadata["domain"]
            repo_age = metadata["repo_age_years"]
            scan_result = self._scan_and_extract(
                managed_repo_path, language_name, repo_name, scanner, extractor
            )
            test_commit_rows = scan_result[0]
            fixtures = scan_result[1]
            adoption_intensity = scan_result[2]
            commits_accepted = scan_result[3]
            commits_rejected = scan_result[4]

            return {
                "repo_name": repo_name,
                "language_name": language_name,
                "status": "ok",
                "skip_reason": None,
                "domain": domain,
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
                    repo_age_years=repo_age,
                    agent_adoption_intensity=adoption_intensity,
                ),
                "test_commit_rows": test_commit_rows,
                "fixtures": fixtures,
                "commits_accepted": commits_accepted,
                "commits_rejected": commits_rejected,
            }

    def _scan_and_extract(
        self,
        managed_repo_path: Path,
        language_name: str,
        repo_name: str,
        scanner: Tier1RepositoryScanner,
        extractor: AgentFixtureExtractor,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Any, int, int]:
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
            tuple: (test_commit_rows, fixtures, adoption_intensity, commits_accepted, commits_rejected)
                - test_commit_rows (list[dict]): Rows suitable for CSV/DB insertion
                  describing each human test commit discovered.
                - fixtures (list[dict]): Extracted fixture dictionaries filtered
                  to only include complete additions.
                - adoption_intensity (str | None): Agent adoption intensity category.
                - commits_accepted (int): Human test commits that passed the
                  commit-level purity gate (every touched test file was a
                  pure addition), regardless of fixture yield.
                - commits_rejected (int): Human test commits rejected by the
                  gate because some touched test file had a deletion, was
                  deleted, or was renamed.
        """
        commit_roles = scanner.scan_repo_commit_roles(
            managed_repo_path,
            start_date=AGENT_CORPUS_START_DATE,
            language=language_name,
            detect_test_files=True,
        )

        # Compute agent adoption intensity from the full commit role list
        total_commits = len(commit_roles)
        agent_commits_count = sum(
            1 for c in commit_roles if c.commit_role == "agent"
        )
        from .tiered_agent_corpus_scanner import compute_adoption_intensity

        adoption_intensity = compute_adoption_intensity(
            managed_repo_path,
            AGENT_CORPUS_START_DATE,
            agent_commit_count=agent_commits_count,
            total_commit_count=total_commits,
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
        commits_accepted = 0
        commits_rejected = 0
        if human_commits:
            logger.debug(
                f"[Human Corpus] {repo_name}: scanning {len(human_commits)} human commits"
            )
            purity_stats: Dict[str, int] = {}
            fixtures = extractor._extract_from_agent_commits(
                repo_name=repo_name, commits=human_commits, stats=purity_stats
            )
            fixtures = [
                fixture for fixture in fixtures if fixture.get("is_complete_addition")
            ]
            # Same commit-level purity gate agent_corpus.py reports via
            # fixture_repos.csv's rejected_mixed_test_diff/accepted columns --
            # mirrored here so Dataset B's acceptance rate is measurable too
            # (see internal-docs/REVIEWER_CRITIQUE_DETECTION_METHODOLOGY.md
            # gap #3: this was previously silently discarded).
            commits_rejected = purity_stats.get("commits_skipped_commit_level", 0)
            commits_accepted = purity_stats.get(
                "commits_proceeded", 0
            ) + purity_stats.get("commits_skipped_file_level", 0)
            # Persistence reads commit_kind for the between-group comparison
            # (between_group_comparison.py's WHERE f.commit_kind = 'human'),
            # but _extract_from_agent_commits doesn't set it -- same shared
            # extractor agent_corpus.py uses, tagged "agent" there. Tag here
            # so it isn't left at corpus_utils.py's "unknown" default.
            for fixture in fixtures:
                fixture["commit_kind"] = "human"

        return test_commit_rows, fixtures, adoption_intensity, commits_accepted, commits_rejected

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
            if existing and self.test_commits_csv is not None:
                out_dir = self.test_commits_csv
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
        _warn_stale_human_fixture_csvs("b", self.fixtures_output_dir)

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

        repo_ages: list[float] = []
        repo_contributors: list[int] = []
        language_progress: dict[str, dict] = {}
        progress_lock = threading.Lock()
        progress_file = self._human_progress_file()

        def log_progress(stop_flag_container: dict) -> None:
            """Log progress every 3 minutes."""
            while not stop_flag_container.get("stop_flag", False):
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

        stop_flag_container: dict = {"stop_flag": False}
        progress_thread = threading.Thread(
            target=log_progress, args=(stop_flag_container,), daemon=True
        )
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
            stop_flag_container["stop_flag"] = True
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
        lang_fixtures_collected = 0
        lang_commits_accepted = 0
        lang_commits_rejected = 0

        if workers <= 1:
            for repo in tqdm(
                lang_repos, desc=f"[Human Corpus] {current_lang}", unit="repo"
            ):
                lang_results.append(self._process_human_repository(repo))
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self._process_human_repository, repo): repo
                    for repo in lang_repos
                }
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc=f"[Human Corpus] {current_lang}",
                    unit="repo",
                ):
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
            repo_age = result["repo_age"]
            if repo_age is not None:
                repo_ages.append(repo_age)
            if result.get("num_contributors"):
                repo_contributors.append(result["num_contributors"])

            stats.domain_distribution[domain] = (
                stats.domain_distribution.get(domain, 0) + 1
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
            lang_commits_accepted += result.get("commits_accepted", 0)
            lang_commits_rejected += result.get("commits_rejected", 0)

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
            for repo_data, fixtures_list in lang_all_fixtures:
                # Bucket by each fixture's OWN detected language, not the
                # repo's aggregate current_lang -- a repo's SEART-assigned
                # language is a single tag for the whole repo, but a
                # multi-language repo (e.g. a Java backend with a JS
                # frontend) can have human commits touching test files in
                # more than one language. Same fix as agent_corpus.py's
                # _persist_repo_agent_commit_stats().
                fixtures_by_language: dict[str, list[dict]] = {}
                for fx in fixtures_list:
                    fx_lang = (fx.get("language") or current_lang).strip().lower()
                    fixtures_by_language.setdefault(fx_lang, []).append(fx)

                fixture_count = 0
                for fx_lang, fx_group in fixtures_by_language.items():
                    fixtures_out_path = _human_fixture_csv_path(
                        fx_lang, "b", self.fixtures_output_dir
                    )
                    fixture_count += persist_repository_and_fixtures(
                        self.output_db,
                        repo_data,
                        fx_group,
                        out_path=fixtures_out_path,
                        handle_mocks=True,
                    )
                with progress_lock:
                    stats.fixtures_collected += fixture_count
                    lang_fixtures_collected += fixture_count
                    if stats.repos_by_language[current_lang] > 0:
                        language_progress[current_lang]["avg_fixtures_per_repo"] = (
                            lang_fixtures_collected
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

            # Commit-level purity-gate outcome for this language -- one row,
            # written unconditionally (not gated on only_write_test_commits)
            # since it's cheap and always available once repos have been
            # scanned. This is what makes Dataset B's purity acceptance rate
            # auditable after the fact (see collection/dataset_summary.py);
            # previously this data was computed in memory and discarded.
            purity_out_dir = Path(self.test_commits_csv)
            purity_out_dir.mkdir(parents=True, exist_ok=True)
            purity_out_path = purity_out_dir / f"{current_lang}_purity_stats.csv"
            with purity_out_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh, fieldnames=["language", "commits_accepted", "commits_rejected"]
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "language": current_lang,
                        "commits_accepted": lang_commits_accepted,
                        "commits_rejected": lang_commits_rejected,
                    }
                )

        with db_session(self.output_db) as conn:
            mark_global_checkpoint(conn, f"human_within_complete:{current_lang}")

