"""
Agent corpus collection for between-group comparison.

Collects fixtures from agent-authored commits (Tier 1: co-authored-by trailers
only) detected from repositories with agent configuration files.
"""

import argparse
import csv
import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from tqdm import tqdm

from .config import (
    AGENT_CORPUS_START_DATE,
    CLONES_DIR,
    COLLECTION_OUTPUT_TAG,
    DATA_DIR,
    LANGUAGE_CONFIGS,
    MIN_COMMITS,
)
from .db import (
    db_session,
    initialise_db,
    mark_global_checkpoint,
    is_global_checkpoint_completed,
    upsert_repository,
    upsert_test_file,
    insert_fixture,
    insert_test_commit,
)
from .fixture_extractor import AgentFixtureExtractor
from .test_commit_utils import collect_test_files_for_commit, write_test_commits_csv
from .agent_patterns import (
    AGENT_SIGNATURES,
    PAPER_AGENT_CONFIG_PATTERNS,
    PAPER_AGENT_REPOSITORY_LANGUAGES,
    repo_contains_patterns,
)
from .corpus_utils import (
    BaseCorpusStats,
    compute_repo_metadata,
    construct_repo_dict,
    generate_corpus_summary,
    persist_repository_and_fixtures,
    write_fixture_csv_row,
)
from .clone_manager import clone_with_function
from .utils import (
    _normalize_language_filters,
    build_repo_row,
    _date_only,
    AGENT_TRAILER_RE,
)

from collection.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class AgentCorpusStats(BaseCorpusStats):
    """Statistics for agent corpus collection (inherits from base)."""

    repos_with_agent_config: int = 0
    agent_commits_found: int = 0
    agent_types_distribution: Dict[str, int] = field(default_factory=dict)


def detect_agent_type(commit_message: str) -> Optional[str]:
    """
    Detect agent type from commit metadata.

    Tier 1: Matches author name/email or co-authored-by trailers

    Returns:
        Agent type (claude, copilot, cursor, aider) or None
    """
    message_lower = commit_message.lower()

    for agent_type, signatures in AGENT_SIGNATURES.items():
        for sig in signatures:
            if sig.lower() in message_lower:
                return agent_type

    return None


def _extract_coauthors(commit_body: str) -> list[str]:
    """Extract agent trailer values (co-authored-by, assisted-by, generated-by) from the commit body."""
    if not commit_body:
        return []
    return [
        match.strip()
        for match in AGENT_TRAILER_RE.findall(commit_body)
        if match.strip()
    ]


def detect_agent_in_commit(
    author_name: str, author_email: str, commit_body: str
) -> tuple[Optional[str], str]:
    """
    Detect agent type from commit author metadata and co-authored-by trailers.

    Returns:
        (agent_type, matched_field) where matched_field is one of
        {"author", "coauthored-by"} or "" if no match.
    """
    if "[bot]" in author_name.lower():
        return None, ""

    author_text = f"{author_name} {author_email}".lower()
    for agent_type, signatures in AGENT_SIGNATURES.items():
        for sig in signatures:
            if sig.lower() in author_text:
                return agent_type, "author"

    for coauthor in _extract_coauthors(commit_body):
        coauthor_lower = coauthor.lower()
        for agent_type, signatures in AGENT_SIGNATURES.items():
            for sig in signatures:
                if sig.lower() in coauthor_lower:
                    return agent_type, "coauthored-by"

    return None, ""


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
        from .agent_commit_detector import Tier1RepositoryScanner

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
                    clone_url=row.get("clone_url"),
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
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
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
        return target_dir.exists() and (
            list(target_dir.glob(".git")) or list(target_dir.iterdir())
        )
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"Failed to clone history for {clone_url}: {e}")
        return False


def scan_cloned_repo_for_agent_configs(repo_path: Path) -> bool:
    """
    Check if a cloned repo contains any agent config files.

    Args:
        repo_path: Path to cloned repository

    Returns:
        True if any agent config file found, False otherwise
    """
    if not repo_path.exists():
        return False

    try:
        return repo_contains_patterns(repo_path, PAPER_AGENT_CONFIG_PATTERNS)
    except Exception as e:
        logger.debug(f"Error scanning for agent files in {repo_path}: {e}")
        return False


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
        repo_contributors = []
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

                    # Persist repository metadata using shared utility
                    with db_session(self.output_db) as conn:
                        repo_row, _ = upsert_repository(
                            conn,
                            construct_repo_dict(
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
                            ),
                        )

                    # Find agent commits from the QCed commit dataset.
                    agent_commits = commits_by_repo.get(repo_name, [])
                    logger.info(
                        f"[Agent Corpus] {repo_name}: {len(agent_commits)} agent commits to inspect"
                    )

                    if not agent_commits:
                        logger.debug(
                            f"[Agent Corpus] No agent commits found in {repo_name}"
                        )
                        stats.repos_failed_qc += 1
                        stats.qc_skip_reasons["no_agent_commits"] = (
                            stats.qc_skip_reasons.get("no_agent_commits", 0) + 1
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

                    if not test_commits:
                        logger.debug(
                            f"[Agent Corpus] No agent test commits found in {repo_name}"
                        )
                        stats.repos_failed_qc += 1
                        stats.qc_skip_reasons["no_test_commits"] = (
                            stats.qc_skip_reasons.get("no_test_commits", 0) + 1
                        )
                        continue

                    stats.test_commits_found += len(test_commits)
                    all_test_commit_rows.extend(test_commits)
                    lang_test_commit_rows.extend(test_commits)

                    # Extract fixtures from test commits
                    test_files_cache = {}  # Cache to avoid re-inserting same test file
                    # Track per-repo fixture metadata to write repo list CSV
                    repo_fixture_count = 0
                    repo_fixture_commit_shas: list[str] = []
                    all_repo_fixtures: list[dict] = []

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
                                fixtures = agent_extractor._extract_from_agent_commits(
                                    repo_name=repo_name,
                                    commits={
                                        commit_info["commit_sha"]: commit_info.get(
                                            "agent_type", "unknown"
                                        )
                                    },
                                )
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
                                    all_repo_fixtures.extend(fixtures)

                                for fixture in fixtures:
                                    file_path = fixture.get("file_path", "unknown")

                                    # Ensure test file exists in database (upsert, cached)
                                    if file_path not in test_files_cache:
                                        test_file_id = upsert_test_file(
                                            conn, repo_row, file_path, language_name
                                        )
                                        test_files_cache[file_path] = test_file_id
                                    else:
                                        test_file_id = test_files_cache[file_path]

                                    insert_fixture(
                                        conn,
                                        {
                                            "file_id": test_file_id,
                                            "repo_id": repo_row,
                                            "name": fixture.get("name"),
                                            "fixture_type": fixture.get("fixture_type"),
                                            "scope": fixture.get("scope"),
                                            "start_line": fixture.get("start_line"),
                                            "end_line": fixture.get("end_line"),
                                            "loc": fixture.get("loc"),
                                            "cyclomatic_complexity": fixture.get(
                                                "cyclomatic_complexity"
                                            ),
                                            "max_nesting_depth": fixture.get(
                                                "max_nesting_depth"
                                            ),
                                            "num_objects_instantiated": fixture.get(
                                                "num_objects_instantiated"
                                            ),
                                            "num_external_calls": fixture.get(
                                                "num_external_calls"
                                            ),
                                            "num_parameters": fixture.get(
                                                "num_parameters"
                                            ),
                                            "reuse_count": fixture.get("reuse_count"),
                                            "has_teardown_pair": fixture.get(
                                                "has_teardown_pair"
                                            ),
                                            "raw_source": fixture.get("raw_source"),
                                            "framework": fixture.get("framework"),
                                            "num_mocks": len(fixture.get("mocks", [])),
                                            "is_complete_addition": (
                                                1
                                                if fixture.get("is_complete_addition")
                                                else 0
                                            ),
                                            "commit_sha": commit_info["commit_sha"],
                                            "agent_type": agent_type,
                                            "commit_kind": "agent",
                                        },
                                    )

                                stats.fixtures_collected += len(fixtures)
                            except Exception as e:
                                logger.debug(
                                    f"Failed to extract fixtures from {commit_info['commit_sha']}: {e}"
                                )

                        # cleanup is handled by the clone manager context
                        logger.debug(
                            f"[Agent Corpus] Cleaned up clone (managed): {repo_name}"
                        )

                # If we extracted fixtures from this repo, write two CSVs:
                # 1. Per-language repo summary (for downstream human selection)
                # 2. Per-fixture detail (one row per fixture, for analysis)
                try:
                    if repo_fixture_count > 0:
                        project_root = Path(__file__).resolve().parents[1]
                        fixture_list_dir = (
                            project_root / "fixtures-from-agents" / COLLECTION_OUTPUT_TAG
                        )
                        fixture_list_dir.mkdir(parents=True, exist_ok=True)

                        # Repo-level summary CSV — keep separate from fixture rows
                        repo_list_dir = fixture_list_dir / "repos"
                        repo_list_dir.mkdir(parents=True, exist_ok=True)
                        repo_list_path = (
                            repo_list_dir
                            / f"{language_name}_agent_fixture_repos.csv"
                        )
                        write_header = not repo_list_path.exists()
                        with repo_list_path.open(
                            "a", encoding="utf-8", newline=""
                        ) as fh:
                            writer = csv.DictWriter(
                                fh,
                                fieldnames=[
                                    "repo_name",
                                    "language",
                                    "fixture_count",
                                    "commit_count_with_fixtures",
                                    "first_fixture_commit",
                                    "last_fixture_commit",
                                    "clone_url",
                                ],
                            )
                            if write_header:
                                writer.writeheader()

                            first_sha = (
                                repo_fixture_commit_shas[0]
                                if repo_fixture_commit_shas
                                else ""
                            )
                            last_sha = (
                                repo_fixture_commit_shas[-1]
                                if repo_fixture_commit_shas
                                else ""
                            )
                            writer.writerow(
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
                                }
                            )

                        # Per-fixture CSV (new: one row per fixture)
                        fixtures_list_path = (
                            fixture_list_dir
                            / f"{language_name}_agent_fixtures.csv"
                        )
                        for fixture in all_repo_fixtures:
                            write_fixture_csv_row(
                                fixtures_list_path,
                                repo_name,
                                language_name,
                                fixture,
                                extra_fields={
                                    "agent_type": fixture.get(
                                        "agent_type", agent_type
                                    ),
                                    "commit_kind": "agent",
                                },
                            )
                except Exception as e:
                    logger.debug(
                        f"Failed to write agent fixture repo list for {repo_name}: {e}"
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
                    out_path = (
                        out_dir / f"{current_language}_agent_test_commit_qc.csv"
                    )
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
