"""
Builds Dataset A: agent-authored fixtures for the between-group comparison.

Collects fixtures from agent-authored commits (Tier 1: co-authored-by trailers
only) detected from repositories with agent configuration files. Entry point:
phase_3_extract_agent.py. See human_corpus.py (Dataset B) and dataset_c.py
(Dataset C) for the other two datasets.
"""

import argparse
import csv
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from tqdm import tqdm

from collection.logging_utils import get_logger

from .agent_patterns import (
    PAPER_AGENT_CONFIG_PATTERNS,
    PAPER_AGENT_REPOSITORY_LANGUAGES,
    repo_contains_patterns,
)
from .clone_primitives import _output_requests_credentials
from .config import (
    AGENT_CORPUS_START_DATE,
    CLONES_DIR,
    COLLECTION_OUTPUT_TAG,
    DATA_DIR,
    LANGUAGE_CONFIGS,
    MIN_COMMITS,
)
from .corpus_utils import (
    BaseCorpusStats,
    compute_repo_metadata,
    construct_repo_dict,
    generate_corpus_summary,
    persist_repository_and_fixtures,
)
from .csv_adapter import get_adapter
from .db import (
    db_session,
    initialise_db,
    insert_test_commit,
    is_global_checkpoint_completed,
    mark_global_checkpoint,
    update_agent_commit_stats,
    upsert_repository,
)
from .ephemeral_clone import clone_with_function
from .fixture_extractor import AgentFixtureExtractor
from .test_commit_utils import collect_test_files_for_commit, write_test_commits_csv
from .utils import _normalize_language_filters, build_repo_row

logger = get_logger(__name__)


@dataclass
class AgentCorpusStats(BaseCorpusStats):
    """Statistics for agent corpus collection (inherits from base)."""

    repos_with_agent_config: int = 0
    agent_commits_found: int = 0
    agent_types_distribution: Dict[str, int] = field(default_factory=dict)


def get_agent_commits(repo_path: Path, start_date: str) -> list[dict]:
    """
    Get commits with agent metadata after start_date.

    Args:
        repo_path: Path to repository
        start_date: ISO date string

    Returns:
        List of dicts with commit_sha, agent_type, commit_date
    """
    try:
        from .tiered_agent_corpus_scanner import Tier1RepositoryScanner

        project_root = Path(__file__).resolve().parents[1]
        scanner = Tier1RepositoryScanner(project_root / "data" / "corpus.db")
        commits = scanner.scan_repo_for_agent_commits(repo_path, start_date=start_date)
        return [
            {
                "commit_sha": commit.commit_sha,
                "agent_type": commit.agent_type,
                "commit_date": commit.commit_date,
                "author_name": commit.author_name,
                "author_email": commit.author_email,
            }
            for commit in commits
        ]
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Failed to get agent commits for {repo_path}: {e}")
        return []


def _load_qc_repo_rows(
    repo_qc_dir: Path,
    languages: Optional[list[str]] = None,
    language: Optional[str] = None,
    repos_per_language: Optional[int] = None,
) -> list[dict]:
    """Load config-positive repositories from the repo-QC CSVs."""
    selected_languages = _normalize_language_filters(languages, language)
    allowed_languages = set(selected_languages or [])
    grouped: dict[str, list[dict]] = {}

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

                repo_name = (row.get("repo_name") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name:
                    continue
                if lang not in PAPER_AGENT_REPOSITORY_LANGUAGES:
                    continue
                if allowed_languages and lang not in allowed_languages:
                    continue

                repo_row = build_repo_row(
                    repo_name,
                    lang,
                    stars=row.get("stars") or 0,
                    clone_url=row.get("clone_url") or "",
                    num_contributors=row.get("num_contributors") or 0,
                )
                grouped.setdefault(lang, [])
                if repo_name not in {r["full_name"] for r in grouped[lang]}:
                    grouped[lang].append(repo_row)

    ordered: list[dict] = []
    language_order = selected_languages or sorted(grouped.keys())
    for lang in language_order:
        if lang:
            ordered.extend(grouped.get(lang, [])[:repos_per_language])

    return ordered


def _load_qc_agent_commits(
    commit_qc_dir: Path,
    languages: Optional[list[str]] = None,
    language: Optional[str] = None,
) -> dict[str, list[dict]]:
    """Load agent commits from QC CSVs and group them by repository.

    Supports both raw agent-commit datasets and pre-filtered agent test-commit
    datasets so fixture extraction can run directly from either source.
    """
    selected_languages = _normalize_language_filters(languages, language)
    allowed_languages = set(selected_languages or [])
    commits_by_repo: dict[str, list[dict]] = {}
    seen_shas: dict[str, set[str]] = {}

    # Accept both raw agent-commit CSVs and pre-filtered agent test-commit CSVs.
    patterns = [
        "*_agent_commit.csv",
        "*_agent_commit_qc.csv",
        "*_agent_test_commit.csv",
        "*_agent_test_commit_qc.csv",
    ]
    csv_paths = []
    for pat in patterns:
        csv_paths.extend(sorted(Path(commit_qc_dir).glob(pat)))
    for csv_path in csv_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                repo_name = (row.get("repo_name") or "").strip()
                commit_sha = (row.get("commit_sha") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or not commit_sha:
                    continue
                if lang not in PAPER_AGENT_REPOSITORY_LANGUAGES:
                    continue
                if allowed_languages and lang not in allowed_languages:
                    continue

                repo_seen = seen_shas.setdefault(repo_name, set())
                if commit_sha in repo_seen:
                    continue
                repo_seen.add(commit_sha)

                commits_by_repo.setdefault(repo_name, []).append(
                    {
                        "commit_sha": commit_sha,
                        "agent_type": (row.get("agent_type") or "unknown")
                        .strip()
                        .lower(),
                        "commit_date": row.get("commit_date") or "",
                        "author_name": row.get("author_name") or "",
                        "author_email": row.get("author_email") or "",
                    }
                )

    return commits_by_repo


def clone_repo_for_commit_scan(clone_url: str, target_dir: Path) -> bool:
    """
    Clone a repository with full commit history but without downloading large blobs.

    This is the history used for agent-commit detection and fixture extraction.
    Returns False if the repo requires credentials (private/removed repo).
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:limit=10m",
                "--single-branch",
                "--no-tags",
                clone_url,
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if _output_requests_credentials(result.stderr):
            return False
        return bool(
            result.returncode == 0
            and target_dir.exists()
            and (list(target_dir.glob(".git")) or list(target_dir.iterdir()))
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout cloning history for {clone_url}")
        return False
    except Exception as e:
        logger.warning(f"Failed to clone history for {clone_url}: {e}")
        return False


def shallow_clone_repo(clone_url: str, target_dir: Path) -> bool:
    """
    Shallow-clone a repository (depth 1) for quick agent config detection.

    Returns False if the repo requires credentials (private/removed repo).
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--no-tags",
                clone_url,
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if _output_requests_credentials(result.stderr):
            return False
        return result.returncode == 0 and target_dir.exists()
    except Exception as e:
        logger.warning(f"Failed to shallow-clone {clone_url}: {e}")
        return False


def scan_cloned_repo_for_agent_configs(repo_path: Path) -> str | None:
    """
    Check if a cloned repo contains any agent config files.

    Args:
        repo_path: Path to cloned repository

    Returns:
        The matched config-file pattern (e.g. "CLAUDE.md") if found, else None.
    """
    if not repo_path.exists():
        return None

    try:
        return repo_contains_patterns(repo_path, PAPER_AGENT_CONFIG_PATTERNS)
    except Exception as e:
        logger.debug(f"Error scanning for agent files in {repo_path}: {e}")
        return None


def shallow_clone_and_check_repo(clone_url: str, clones_dir: Path) -> Optional[Path]:
    """
    Shallow-clone a repo and return its path if it contains agent configs.

    Returns:
        Path to cloned repo if agent configs found, None otherwise
    """
    repo_name = clone_url.split("/")[-1].replace(".git", "")
    repo_path = clones_dir / repo_name
    if shallow_clone_repo(clone_url, repo_path) and scan_cloned_repo_for_agent_configs(
        repo_path
    ):
        return repo_path
    return None


class AgentCorpusCollector:
    """Collect agent-authored fixtures from quality-controlled repo and commit CSVs."""

    def __init__(
        self,
        clones_dir: Path = CLONES_DIR,
        github_token: Optional[str] = None,
        output_db: Path | None = None,
        repo_qc_dir: Path | None = None,
        commit_qc_dir: Path | None = None,
        test_commits_csv: Path | None = None,
    ):
        """
        Initialize agent corpus collector.

        Args:
            clones_dir: Directory for repository clones
            github_token: Optional GitHub API token
            output_db: Path to output database (default: data/between-group.db)
            repo_qc_dir: Directory containing *_agent_repo.csv files
            commit_qc_dir: Directory containing *_agent_commit_qc.csv files
        """
        self.clones_dir = Path(clones_dir)
        self.github_token = github_token
        self.output_db = (
            Path(output_db) if output_db else (DATA_DIR / "between-group.db")
        )
        self.test_commits_csv = Path(test_commits_csv) if test_commits_csv else None
        project_root = Path(__file__).resolve().parents[1]
        self.repo_qc_dir = (
            Path(repo_qc_dir)
            if repo_qc_dir
            else (project_root / "github-search-agent" / "agent_repositories")
        )
        self.commit_qc_dir = (
            Path(commit_qc_dir)
            if commit_qc_dir
            else (project_root / "github-search-agent" / "agent_repositories")
        )

    def run(
        self,
        repos_per_language: Optional[int] = None,
        languages: Optional[list[str]] = None,
        language: Optional[str] = None,
    ) -> tuple[AgentCorpusStats, Path]:
        """
        Collect agent-authored fixtures from repositories with agent commits.

        Args:
            repos_per_language: Optional per-language cap. None means include all rows.
            languages: Optional list of languages to include
            language: Optional filter to single language

        Returns:
            (stats, output_db_path)
        """
        initialise_db(self.output_db)
        try:
            csv.field_size_limit(10**7)
        except OverflowError:
            csv.field_size_limit(2**31 - 1)
        stats = AgentCorpusStats()
        all_test_commit_rows: list[dict] = []
        agent_extractor = AgentFixtureExtractor(clones_dir=self.clones_dir)

        repos_to_collect = _load_qc_repo_rows(
            self.repo_qc_dir,
            languages=languages,
            language=language,
            repos_per_language=repos_per_language,
        )
        commits_by_repo = _load_qc_agent_commits(
            self.commit_qc_dir,
            languages=languages,
            language=language,
        )

        completion_all_step = "agent_complete:all"

        def completion_step(lang_name: str) -> str:
            return f"agent_complete:{lang_name}"

        selected_languages = sorted(
            {
                (repo.get("language") or "unknown").strip().lower()
                for repo in repos_to_collect
            }
        )

        logger.info(
            "[Agent Corpus] Selected languages: %s | repos to collect: %d",
            selected_languages,
            len(repos_to_collect),
        )
        if language:
            logger.info(
                "[Agent Corpus] Single-language filter active: %s",
                language,
            )

        with db_session(self.output_db) as conn:
            # Only check the "all completed" checkpoint when running without
            # a single-language filter. Otherwise a completed full run would
            # block every subsequent single-language run.
            if not language and is_global_checkpoint_completed(
                conn, completion_all_step
            ):
                logger.info(
                    "[Agent Corpus] Completion checkpoint found; skipping agent collection"
                )
                return stats, self.output_db

            if language and is_global_checkpoint_completed(
                conn, completion_step(language)
            ):
                logger.info(
                    f"[Agent Corpus] Completion checkpoint found for {language}; skipping agent collection"
                )
                return stats, self.output_db

            completed_languages = {
                lang
                for lang in selected_languages
                if is_global_checkpoint_completed(conn, completion_step(lang))
            }

        repos_to_collect = [
            repo
            for repo in repos_to_collect
            if (repo.get("language") or "unknown").strip().lower()
            not in completed_languages
        ]

        if not repos_to_collect:
            with db_session(self.output_db) as conn:
                mark_global_checkpoint(conn, completion_all_step)
            logger.info(
                "[Agent Corpus] All selected languages already completed; skipping agent collection"
            )
            return stats, self.output_db

        repos_to_collect.sort(
            key=lambda repo: (
                (repo.get("language") or "unknown").strip().lower(),
                repo.get("full_name", ""),
            )
        )

        logger.info(
            "[Agent Corpus] Loaded %d QC repositories from %s and commit rows from %s",
            len(repos_to_collect),
            self.repo_qc_dir,
            self.commit_qc_dir,
        )

        # Trackers for statistics
        repo_ages = []
        lang_test_commit_rows: list[dict] = []

        try:
            for idx, repo in tqdm(
                enumerate(repos_to_collect, 1),
                total=len(repos_to_collect),
                desc="Agent Corpus",
            ):
                stats.repos_scanned += 1
                repo_name = repo.get("full_name", "unknown")
                language_name = repo.get("language", "unknown")
                repo_path = self.clones_dir / repo_name.replace("/", "__")

                logger.info(
                    f"[Agent Corpus] Processing {repo_name} ({stats.repos_scanned}/{len(repos_to_collect)})"
                )

                # Replace shallow clones with full-history by removing shallow state.
                if repo_path.exists():
                    shallow_flag = repo_path / ".git" / "shallow"
                    if shallow_flag.exists():
                        logger.info(
                            f"[Agent Corpus] Replacing shallow clone for {repo_name} with full-history clone..."
                        )
                        shutil.rmtree(repo_path, ignore_errors=True)

                # Use managed clone context to ensure cleanup and disk guards.
                logger.info(
                    f"[Agent Corpus] Cloning {repo_name} with history for commit scan..."
                )
                with clone_with_function(
                    clone_repo_for_commit_scan, repo.get("clone_url", ""), repo_path
                ) as managed_repo_path:
                    if managed_repo_path is None:
                        stats.repos_failed_qc += 1
                        stats.qc_skip_reasons["clone_failed"] = (
                            stats.qc_skip_reasons.get("clone_failed", 0) + 1
                        )
                        continue

                    # From here onward use managed_repo_path as the repository path
                    repo_path = managed_repo_path

                    stats.repos_cloned += 1
                    stats.repos_with_agent_config += 1

                    # Per-repo agent-commit stats (Dataset A). Initialised here so
                    # every early-exit path below can still persist a full row.
                    repo_commit_stats = {
                        "agent_commits_touching_tests": 0,
                        "rejected_mixed_test_diff": 0,
                        "accepted": 0,
                    }
                    repo_fixture_count = 0
                    repo_fixture_commit_shas: list[str] = []
                    all_repo_fixtures: list[dict] = []

                    # Compute control variables at AGENT_CORPUS_START_DATE using shared utility
                    metadata = compute_repo_metadata(repo, AGENT_CORPUS_START_DATE)
                    domain = metadata["domain"]
                    star_tier = metadata["star_tier"]
                    repo_age = metadata["repo_age_years"]

                    # Track distributions
                    stats.domain_distribution[domain] = (
                        stats.domain_distribution.get(domain, 0) + 1
                    )
                    stats.star_tier_distribution[star_tier] = (
                        stats.star_tier_distribution.get(star_tier, 0) + 1
                    )
                    if repo_age is not None:
                        repo_ages.append(repo_age)

                    # Find agent commits from the QCed commit dataset.
                    agent_commits = commits_by_repo.get(repo_name, [])
                    logger.info(
                        f"[Agent Corpus] {repo_name}: {len(agent_commits)} agent commits to inspect"
                    )

                    # Compute agent adoption intensity before persisting repo metadata
                    from .tiered_agent_corpus_scanner import (
                        compute_adoption_intensity,
                        count_total_commits_since,
                    )

                    total_commits = count_total_commits_since(
                        repo_path, AGENT_CORPUS_START_DATE
                    )
                    adoption_intensity = compute_adoption_intensity(
                        repo_path,
                        AGENT_CORPUS_START_DATE,
                        agent_commit_count=len(agent_commits),
                        total_commit_count=total_commits,
                    )
                    logger.info(
                        f"[Agent Corpus] {repo_name}: {len(agent_commits)} agent / "
                        f"{total_commits} total commits → {adoption_intensity}"
                    )

                    # Persist repository metadata using shared utility
                    repo_data = construct_repo_dict(
                        full_name=repo_name,
                        language=language_name,
                        stars=repo.get("stars", 0),
                        forks=repo.get("forks", 0),
                        description=repo.get("description", "") or "",
                        topics=(
                            json.dumps(repo.get("topics", []))
                            if isinstance(repo.get("topics"), list)
                            else repo.get("topics", "[]")
                        ),
                        created_at=repo.get("created_at", ""),
                        pushed_at=repo.get("pushed_at", ""),
                        clone_url=repo.get("clone_url", ""),
                        github_id=repo.get("github_id"),
                        num_contributors=repo.get("num_contributors", 0),
                        domain=domain,
                        star_tier=star_tier,
                        repo_age_years=repo_age,
                        agent_adoption_intensity=adoption_intensity,
                    )
                    with db_session(self.output_db) as conn:
                        repo_row, _ = upsert_repository(conn, repo_data)

                    if not agent_commits:
                        logger.debug(
                            f"[Agent Corpus] No agent commits found in {repo_name}"
                        )
                        stats.repos_failed_qc += 1
                        stats.qc_skip_reasons["no_agent_commits"] = (
                            stats.qc_skip_reasons.get("no_agent_commits", 0) + 1
                        )
                        self._persist_repo_agent_commit_stats(
                            repo_row=repo_row,
                            repo_name=repo_name,
                            language_name=language_name,
                            repo=repo,
                            repo_data=repo_data,
                            repo_commit_stats=repo_commit_stats,
                            repo_fixture_count=repo_fixture_count,
                            repo_fixture_commit_shas=repo_fixture_commit_shas,
                            all_repo_fixtures=all_repo_fixtures,
                        )
                        continue

                    stats.repos_passed_qc += 1
                    stats.agent_commits_found += len(agent_commits)
                    stats.repos_by_language[language_name] = (
                        stats.repos_by_language.get(language_name, 0) + 1
                    )

                    test_commits: list[dict] = []
                    for commit_info in agent_commits:
                        test_files = collect_test_files_for_commit(
                            repo_path, commit_info["commit_sha"], language_name
                        )
                        if not test_files:
                            continue

                        test_commits.append(
                            {
                                "commit_info": commit_info,
                                "repo_id": repo_row,
                                "commit_sha": commit_info["commit_sha"],
                                "commit_role": "agent",
                                "agent_type": commit_info.get("agent_type"),
                                "commit_date": commit_info.get("commit_date"),
                                "language": language_name,
                                "test_file_count": len(test_files),
                                "test_file_paths": json.dumps(
                                    test_files, ensure_ascii=False
                                ),
                            }
                        )

                    # Agent test-commit detection is done: this is the same count
                    # that lands in the *_agent_test_commit_qc.csv rows for this repo.
                    repo_commit_stats["agent_commits_touching_tests"] = len(
                        test_commits
                    )

                    if not test_commits:
                        logger.debug(
                            f"[Agent Corpus] No agent test commits found in {repo_name}"
                        )
                        stats.repos_failed_qc += 1
                        stats.qc_skip_reasons["no_test_commits"] = (
                            stats.qc_skip_reasons.get("no_test_commits", 0) + 1
                        )
                        self._persist_repo_agent_commit_stats(
                            repo_row=repo_row,
                            repo_name=repo_name,
                            language_name=language_name,
                            repo=repo,
                            repo_data=repo_data,
                            repo_commit_stats=repo_commit_stats,
                            repo_fixture_count=repo_fixture_count,
                            repo_fixture_commit_shas=repo_fixture_commit_shas,
                            all_repo_fixtures=all_repo_fixtures,
                        )
                        continue

                    stats.test_commits_found += len(test_commits)
                    all_test_commit_rows.extend(test_commits)
                    lang_test_commit_rows.extend(test_commits)

                    # Extract fixtures from test commits. Per-repo fixture
                    # metadata (repo_fixture_count etc.) was already initialised
                    # above so early-exit paths can persist a full stats row.
                    with db_session(self.output_db) as conn:
                        for test_commit in test_commits:
                            insert_test_commit(conn, test_commit)

                    for test_commit in test_commits:
                        commit_info = test_commit["commit_info"]
                        agent_type = commit_info.get("agent_type")
                        stats.agent_types_distribution[agent_type] = (
                            stats.agent_types_distribution.get(agent_type, 0) + 1
                        )

                        try:
                            commit_purity_stats: dict = {}
                            fixtures = agent_extractor._extract_from_agent_commits(
                                repo_name=repo_name,
                                commits={
                                    commit_info["commit_sha"]: commit_info.get(
                                        "agent_type", "unknown"
                                    )
                                },
                                stats=commit_purity_stats,
                            )

                            # Classify this commit using the commit-level diff
                            # purity gate: rejected if any test file had
                            # deletions/edits, accepted if all test files were
                            # pure additions (regardless of fixture yield).
                            if commit_purity_stats.get("commits_skipped_commit_level"):
                                repo_commit_stats["rejected_mixed_test_diff"] += 1
                            elif commit_purity_stats.get(
                                "commits_proceeded"
                            ) or commit_purity_stats.get("commits_skipped_file_level"):
                                repo_commit_stats["accepted"] += 1

                            fixtures = [
                                fixture
                                for fixture in fixtures
                                if fixture.get("is_complete_addition")
                            ]

                            logger.info(
                                f"[Agent Corpus] {repo_name}: commit {commit_info['commit_sha'][:8]} yielded {len(fixtures)} complete fixtures"
                            )

                            if fixtures:
                                repo_fixture_count += len(fixtures)
                                repo_fixture_commit_shas.append(
                                    commit_info["commit_sha"]
                                )
                                # Persistence (DB row + CSV export) reads commit_sha and
                                # agent_type directly from each fixture dict, but not
                                # commit_kind — tag it here so both paths label these
                                # rows correctly.
                                for fixture in fixtures:
                                    fixture["commit_kind"] = "agent"
                                all_repo_fixtures.extend(fixtures)

                            stats.fixtures_collected += len(fixtures)
                        except Exception as e:
                            logger.debug(
                                f"Failed to extract fixtures from {commit_info['commit_sha']}: {e}"
                            )

                    # cleanup is handled by the clone manager context
                    logger.debug(
                        f"[Agent Corpus] Cleaned up clone (managed): {repo_name}"
                    )

                # Always persist the repo-level agent-commit stats + summary row
                # (even for repos that yielded zero fixtures), and additionally
                # write the per-fixture detail CSV/DB rows when fixtures exist.
                self._persist_repo_agent_commit_stats(
                    repo_row=repo_row,
                    repo_name=repo_name,
                    language_name=language_name,
                    repo=repo,
                    repo_data=repo_data,
                    repo_commit_stats=repo_commit_stats,
                    repo_fixture_count=repo_fixture_count,
                    repo_fixture_commit_shas=repo_fixture_commit_shas,
                    all_repo_fixtures=all_repo_fixtures,
                )

                next_language = None
                if idx + 1 < len(repos_to_collect):
                    next_language = (
                        repos_to_collect[idx + 1]
                        .get("language", "unknown")
                        .strip()
                        .lower()
                    )
                current_language = (language_name or "unknown").strip().lower()

                # Write checkpoint + CSV incrementally after every repo that
                # produced test-commit rows, so progress is preserved even if
                # the process crashes mid-language.
                if lang_test_commit_rows:
                    if self.test_commits_csv and self.test_commits_csv.suffix == "":
                        out_dir = Path(self.test_commits_csv)
                        out_dir.mkdir(parents=True, exist_ok=True)
                        out_path = (
                            out_dir / f"{current_language}_agent_test_commit_qc.csv"
                        )
                        write_test_commits_csv(lang_test_commit_rows, out_path)
                    with db_session(self.output_db) as conn:
                        mark_global_checkpoint(conn, completion_step(current_language))

                # Early-exit for single-language runs: stop when we've finished
                # all repos of the target language.
                if language:
                    if next_language and next_language != language:
                        logger.info(
                            "[Agent Corpus] Single-language run (%s) complete; stopping early",
                            language,
                        )
                        break
                    elif next_language is None:
                        logger.info(
                            "[Agent Corpus] Single-language run (%s) complete (end of list)",
                            language,
                        )
                        break

                lang_test_commit_rows = []

            # Final progress log
            # Flush any remaining test-commit rows for the last language
            if lang_test_commit_rows:
                current_language = (
                    repos_to_collect[-1].get("language", "unknown").strip().lower()
                    if repos_to_collect
                    else (language or "unknown")
                )
                if self.test_commits_csv and self.test_commits_csv.suffix == "":
                    out_dir = Path(self.test_commits_csv)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{current_language}_agent_test_commit_qc.csv"
                    write_test_commits_csv(lang_test_commit_rows, out_path)
                with db_session(self.output_db) as conn:
                    mark_global_checkpoint(conn, completion_step(current_language))

        except KeyboardInterrupt:
            logger.info("[Agent Corpus] Collection interrupted by user")
            raise

        # Compute means
        if repo_ages:
            stats.mean_repo_age_years = sum(repo_ages) / len(repo_ages)

        if self.test_commits_csv:
            if not (self.test_commits_csv.suffix == ""):
                write_test_commits_csv(all_test_commit_rows, self.test_commits_csv)

        with db_session(self.output_db) as conn:
            if all(
                is_global_checkpoint_completed(conn, completion_step(lang))
                for lang in selected_languages
            ):
                mark_global_checkpoint(conn, completion_all_step)

        # Generate summary
        self._generate_summary(stats)

        return stats, self.output_db

    def _persist_repo_agent_commit_stats(
        self,
        repo_row: int,
        repo_name: str,
        language_name: str,
        repo: dict,
        repo_data: dict,
        repo_commit_stats: dict,
        repo_fixture_count: int,
        repo_fixture_commit_shas: list[str],
        all_repo_fixtures: list[dict],
    ) -> None:
        """Persist Dataset A's per-repo agent-commit stats and fixture output.

        Always updates the repositories DB row and appends a row to the
        per-language repo-summary CSV (fixtures-from-agents/repos/), even for
        repos with zero test-touching or zero accepted commits, so the stats
        reflect every processed agent-enabled repo. Per-fixture persistence
        (DB rows + the *_agent_fixtures.csv detail file) still only happens
        when the repo actually yielded fixtures.
        """
        try:
            with db_session(self.output_db) as conn:
                update_agent_commit_stats(conn, repo_row, repo_commit_stats)
        except Exception as e:
            logger.debug(
                f"Failed to persist agent commit stats for {repo_name}: {e}"
            )

        try:
            project_root = Path(__file__).resolve().parents[1]
            fixture_list_dir = (
                project_root / "fixtures-from-agents" / COLLECTION_OUTPUT_TAG
            )
            fixture_list_dir.mkdir(parents=True, exist_ok=True)

            # Repo-level summary CSV — keep separate from fixture rows. Always
            # written so every processed repo shows up, regardless of yield.
            repo_list_dir = fixture_list_dir / "repos"
            repo_list_dir.mkdir(parents=True, exist_ok=True)
            repo_list_path = (
                repo_list_dir / f"{language_name}_agent_fixture_repos.csv"
            )
            first_sha = (
                repo_fixture_commit_shas[0] if repo_fixture_commit_shas else ""
            )
            last_sha = (
                repo_fixture_commit_shas[-1] if repo_fixture_commit_shas else ""
            )
            get_adapter().append_dicts(
                repo_list_path,
                [
                    {
                        "repo_name": repo_name,
                        "language": language_name,
                        "fixture_count": repo_fixture_count,
                        "commit_count_with_fixtures": len(
                            repo_fixture_commit_shas
                        ),
                        "first_fixture_commit": first_sha,
                        "last_fixture_commit": last_sha,
                        "clone_url": repo.get("clone_url", ""),
                        "agent_commits_touching_tests": repo_commit_stats[
                            "agent_commits_touching_tests"
                        ],
                        "rejected_mixed_test_diff": repo_commit_stats[
                            "rejected_mixed_test_diff"
                        ],
                        "accepted": repo_commit_stats["accepted"],
                    }
                ],
                [
                    "repo_name",
                    "language",
                    "fixture_count",
                    "commit_count_with_fixtures",
                    "first_fixture_commit",
                    "last_fixture_commit",
                    "clone_url",
                    "agent_commits_touching_tests",
                    "rejected_mixed_test_diff",
                    "accepted",
                ],
            )

            if repo_fixture_count > 0:
                # Per-fixture DB rows + CSV (one row per fixture). Fixtures
                # already carry their own commit_sha/agent_type/commit_kind,
                # so no extra fields need injecting here.
                fixtures_list_path = (
                    fixture_list_dir / f"{language_name}_agent_fixtures.csv"
                )
                persist_repository_and_fixtures(
                    self.output_db,
                    repo_data,
                    all_repo_fixtures,
                    out_path=fixtures_list_path,
                    handle_mocks=True,
                )
        except Exception as e:
            logger.debug(
                f"Failed to write agent fixture repo list for {repo_name}: {e}"
            )

    def _generate_summary(self, stats: AgentCorpusStats) -> None:
        """Generate and save agent corpus summary."""
        generate_corpus_summary(
            stats=stats,
            corpus_name="agent_fixtures",
            output_db=self.output_db,
            temporal_scope=f"after {AGENT_CORPUS_START_DATE}",
            extra_metadata={
                "detection_tier": "Tier 1 (co-authored-by trailers only)",
                "agent_corpus_start_date": AGENT_CORPUS_START_DATE,
                "agent_config_patterns": PAPER_AGENT_CONFIG_PATTERNS,
                "min_commits": MIN_COMMITS,
                "repos_with_agent_config": stats.repos_with_agent_config,
                "repos_cloned": stats.repos_cloned,
                "agent_commits_found": stats.agent_commits_found,
                "agent_types_distribution": dict(stats.agent_types_distribution),
            },
            output_dir=self.output_db.parent,
        )


def main(args):
    """CLI entry point for agent corpus collection."""
    collector = AgentCorpusCollector(
        github_token=args.github_token,
        output_db=args.output_db,
    )
    stats, db_path = collector.run(
        repos_per_language=args.repos_per_language,
        languages=args.languages,
        language=args.language,
    )
    logger.info(
        f"Agent corpus collection complete: {stats.fixtures_collected} fixtures in {db_path}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect agent corpus (Tier 1 agent-authored commits)"
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=None,
        help="GitHub API token (optional for rate limits)",
    )
    parser.add_argument(
        "--output-db",
        type=Path,
        default=None,
        help="Path to output between-group.db (default: data/between-group.db)",
    )
    parser.add_argument(
        "--repos-per-language",
        type=int,
        default=None,
        help="Number of repos per language (None = all repos)",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=sorted(PAPER_AGENT_REPOSITORY_LANGUAGES),
        help="Limit collection to one or more languages",
    )
    parser.add_argument(
        "--language",
        choices=list(LANGUAGE_CONFIGS.keys()),
        help="Limit to one language",
    )
    args = parser.parse_args()
    main(args)
