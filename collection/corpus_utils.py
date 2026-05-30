"""
Shared utilities for corpus collection (agent and human).

Provides base classes, type definitions, and common functions
for corpus collectors to reduce code duplication.
"""

import csv
import time
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, TypedDict, Any

from .config import LANGUAGE_CONFIGS
from .db import (
    classify_domain,
    compute_star_tier,
    compute_repo_age_at_date,
    upsert_repository,
    upsert_test_file,
    insert_fixture,
    insert_test_commit,
    db_session,
)

logger = logging.getLogger(__name__)


class RepositoryMetadata(TypedDict, total=False):
    """Type definition for repository metadata dictionaries."""

    id: int
    github_id: int
    full_name: str
    language: str
    stars: int
    forks: int
    description: str
    topics: str
    created_at: str
    pushed_at: str
    clone_url: str
    num_contributors: int
    status: str


class FixtureData(TypedDict, total=False):
    """Type definition for fixture data."""

    file_id: int
    repo_id: int
    name: str
    fixture_type: str
    scope: str
    start_line: int
    end_line: int
    loc: int
    cyclomatic_complexity: int
    max_nesting_depth: int
    num_objects_instantiated: int
    num_external_calls: int
    num_parameters: int
    reuse_count: int
    has_teardown_pair: bool
    raw_source: str
    framework: str
    num_mocks: int
    commit_sha: str
    commit_kind: str
    is_complete_addition: int


@dataclass
class BaseCorpusStats:
    """Base statistics for corpus collection."""

    repos_scanned: int = 0
    repos_cloned: int = 0
    repos_passed_qc: int = 0
    repos_failed_qc: int = 0
    qc_skip_reasons: Dict[str, int] = field(default_factory=dict)
    fixtures_collected: int = 0
    test_commits_found: int = 0
    repos_by_language: Dict[str, int] = field(default_factory=dict)
    domain_distribution: Dict[str, int] = field(default_factory=dict)
    star_tier_distribution: Dict[str, int] = field(default_factory=dict)
    mean_repo_age_years: float = 0.0
    mean_contributors: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def record_skip(self, reason: str) -> None:
        """Record a skipped repository with reason."""
        self.repos_failed_qc += 1
        self.qc_skip_reasons[reason] = self.qc_skip_reasons.get(reason, 0) + 1


def compute_repo_metadata(
    repo: RepositoryMetadata, temporal_reference: str
) -> Dict[str, Any]:
    """
    Compute repository metadata (domain, star_tier, repo_age).

    Args:
        repo: Repository metadata dictionary
        temporal_reference: Date string for computing repo age (YYYY-MM-DD)

    Returns:
        Dictionary with computed metadata
    """
    domain = classify_domain(repo.get("topics"), repo.get("description"))
    star_tier = compute_star_tier(repo.get("stars", 0))
    repo_age = compute_repo_age_at_date(repo.get("created_at", ""), temporal_reference)

    return {
        "domain": domain,
        "star_tier": star_tier,
        "repo_age_years": repo_age,
    }


def write_fixture_csv_row(
    out_path: Path,
    repo_name: str,
    language: str,
    fixture: dict,
    extra_fields: Optional[dict] = None,
) -> None:
    """
    Write a single fixture to a per-language CSV file.

    Args:
        out_path: Path to fixture CSV file
        repo_name: Full repository name
        language: Programming language
        fixture: Fixture data dictionary
        extra_fields: Optional extra fields to include (e.g., is_complete_addition)
    """
    fieldnames = [
        "repo_name",
        "language",
        "commit_sha",
        "file_path",
        "fixture_name",
        "fixture_type",
        "start_line",
        "end_line",
        "loc",
        "framework",
        "num_mocks",
    ]

    if extra_fields:
        fieldnames.extend(extra_fields.keys())

    write_header = not out_path.exists()

    try:
        csv.field_size_limit(10**7)
    except Exception:
        pass

    with out_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        row = {
            "repo_name": repo_name,
            "language": language,
            "commit_sha": fixture.get("commit_sha", ""),
            "file_path": fixture.get("file_path", ""),
            "fixture_name": fixture.get("name", ""),
            "fixture_type": fixture.get("fixture_type", ""),
            "start_line": fixture.get("start_line", 0),
            "end_line": fixture.get("end_line", 0),
            "loc": fixture.get("loc", 0),
            "framework": fixture.get("framework", ""),
            "num_mocks": len(fixture.get("mocks", []) or []),
        }

        if extra_fields:
            row.update(extra_fields)

        writer.writerow(row)


def persist_repository_and_fixtures(
    output_db: Path,
    repo_data: Dict[str, Any],
    fixtures: list[dict],
    out_path: Optional[Path] = None,
    handle_mocks: bool = False,
) -> int:
    """
    Persist repository and its fixtures to database and optionally to CSV.

    Args:
        output_db: Path to output database
        repo_data: Repository metadata with computed fields
        fixtures: List of fixture dictionaries
        out_path: Optional CSV path for fixture export
        handle_mocks: If True, also insert mock_usage records (for human corpus)

    Returns:
        Number of fixtures persisted
    """
    repo_name = repo_data["full_name"]
    language = repo_data["language"]
    fixture_count = 0

    start_ts = time.time()
    with db_session(output_db) as conn:
        # Upsert repository
        repo_id, _ = upsert_repository(conn, repo_data)

        if not fixtures:
            return 0

        # Export to CSV if path provided
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            for fixture in fixtures:
                write_fixture_csv_row(
                    out_path,
                    repo_name,
                    language,
                    fixture,
                    extra_fields={"is_complete_addition": 1},
                )

        # Upsert test files and insert fixtures
        test_files_cache = {}
        for fixture in fixtures:
            file_path = fixture.get("file_path", "unknown")

            # Cache test file lookups
            if file_path not in test_files_cache:
                test_file_id = upsert_test_file(conn, repo_id, file_path, language)
                test_files_cache[file_path] = test_file_id
            else:
                test_file_id = test_files_cache[file_path]

            # Build and insert fixture data
            fixture_data: FixtureData = {
                "file_id": test_file_id,
                "repo_id": repo_id,
                "name": fixture.get("name"),
                "fixture_type": fixture.get("fixture_type"),
                "scope": fixture.get("scope"),
                "start_line": fixture.get("start_line"),
                "end_line": fixture.get("end_line"),
                "loc": fixture.get("loc"),
                "cyclomatic_complexity": fixture.get("cyclomatic_complexity"),
                "max_nesting_depth": fixture.get("max_nesting_depth"),
                "num_objects_instantiated": fixture.get("num_objects_instantiated"),
                "num_external_calls": fixture.get("num_external_calls"),
                "num_parameters": fixture.get("num_parameters"),
                "reuse_count": fixture.get("reuse_count"),
                "has_teardown_pair": fixture.get("has_teardown_pair"),
                "raw_source": fixture.get("raw_source"),
                "framework": fixture.get("framework"),
                "num_mocks": len(fixture.get("mocks", []) or []),
                "commit_sha": fixture.get("commit_sha", ""),
                "commit_kind": fixture.get("commit_kind", "unknown"),
                "is_complete_addition": 1,
            }

            fixture_id = insert_fixture(conn, fixture_data)
            fixture_count += 1

            # Handle mock_usage records if requested
            if handle_mocks:
                mocks = fixture.get("mocks", []) or []
                if mocks:
                    from .db import insert_mock_usage

                    for mock in mocks:
                        try:
                            insert_mock_usage(
                                conn,
                                {
                                    "fixture_id": fixture_id,
                                    "repo_id": repo_id,
                                    "framework": mock.get("framework"),
                                    "target_identifier": mock.get(
                                        "target_identifier", ""
                                    ),
                                    "num_interactions_configured": mock.get(
                                        "num_interactions_configured", 0
                                    ),
                                    "raw_snippet": mock.get("raw_snippet", ""),
                                },
                            )
                        except Exception as e:
                            logger.debug(
                                f"Failed to insert mock for fixture {fixture_id} in {repo_name}: {e}"
                            )
        duration = time.time() - start_ts
        logger.debug(
            f"persist_repository_and_fixtures: persisted {fixture_count} fixtures for {repo_name} in {duration:.3f}s"
        )
        return fixture_count


def construct_repo_dict(
    full_name: str,
    language: str,
    stars: int = 0,
    forks: int = 0,
    description: str = "",
    topics: str = "[]",
    created_at: str = "",
    pushed_at: str = "",
    clone_url: str = "",
    github_id: Optional[int] = None,
    num_contributors: int = 0,
    domain: Optional[str] = None,
    star_tier: Optional[str] = None,
    repo_age_years: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Construct a repository data dictionary for database insertion.

    Standardizes repository representation across collectors.

    Args:
        full_name: Repository full name (owner/repo)
        language: Programming language
        Other fields: Repository metadata

    Returns:
        Dictionary ready for upsert_repository
    """
    return {
        "github_id": github_id or 0,
        "full_name": full_name,
        "language": language,
        "stars": stars,
        "forks": forks,
        "description": description or "",
        "topics": topics or "[]",
        "created_at": created_at or "",
        "pushed_at": pushed_at or "",
        "clone_url": clone_url or f"https://github.com/{full_name}.git",
        "domain": domain,
        "star_tier": star_tier,
        "repo_age_years": repo_age_years,
        "num_contributors": num_contributors or 0,
    }


def generate_corpus_summary(
    stats: BaseCorpusStats,
    corpus_name: str,
    output_db: Path,
    temporal_scope: str,
    extra_metadata: Optional[dict] = None,
) -> Path:
    """
    Generate and save corpus collection summary to JSON.

    Args:
        stats: Collection statistics
        corpus_name: Name of corpus (agent, human)
        output_db: Path to output database
        temporal_scope: Description of temporal window
        extra_metadata: Optional additional metadata to include

    Returns:
        Path to generated summary file
    """
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    summary_path = (
        output_dir
        / f"{corpus_name}_corpus_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    summary = {
        "timestamp": datetime.now().isoformat(),
        "methodology": {
            "corpus": corpus_name,
            "temporal_scope": temporal_scope,
        },
        "parameters": extra_metadata or {},
        "summary_statistics": {
            "repos_scanned": stats.repos_scanned,
            "repos_passed_qc": stats.repos_passed_qc,
            "repos_failed_qc": stats.repos_failed_qc,
            "qc_skip_reasons": dict(stats.qc_skip_reasons),
            "fixtures_collected": stats.fixtures_collected,
            "test_commits_found": stats.test_commits_found,
            "repos_by_language": dict(stats.repos_by_language),
        },
        "control_variables": {
            "domain_distribution": dict(stats.domain_distribution),
            "star_tier_distribution": dict(stats.star_tier_distribution),
            "mean_repo_age_years": float(stats.mean_repo_age_years),
            "mean_contributors": float(stats.mean_contributors),
        },
        "output_database": str(output_db),
    }

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Summary saved to {summary_path}")
    return summary_path
