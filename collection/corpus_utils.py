"""
Shared utilities for corpus collection (agent and human).

Provides base classes, type definitions, and common functions
for corpus collectors to reduce code duplication.
"""

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

from collection.logging_utils import get_logger

from .db import (
    db_session,
    insert_fixture,
    set_repo_analysed,
    upsert_repository,
    upsert_test_file,
)
from .repo_metadata import classify_domain, compute_repo_age_at_date

logger = get_logger(__name__)


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
    has_teardown_pair: bool
    raw_source: str
    framework: Optional[str]
    num_mocks: int
    commit_sha: str
    commit_kind: str
    agent_type: Optional[str]
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
    repo: Dict[str, Any], temporal_reference: str
) -> Dict[str, Any]:
    """
    Compute repository metadata (domain, repo_age).

    Star count is not part of this: every repo in the corpus already clears
    a hard >=500-star floor at the github-search-raw/ seeding stage (see
    repo_metadata.get_control_variables_at_date's docstring), so a derived
    tier would be constant and uninformative.

    Args:
        repo: Repository metadata dictionary
        temporal_reference: Date string for computing repo age (YYYY-MM-DD)

    Returns:
        Dictionary with computed metadata
    """
    domain = classify_domain(repo.get("topics"), repo.get("description"))
    repo_age = compute_repo_age_at_date(repo.get("created_at", ""), temporal_reference)

    return {
        "domain": domain,
        "repo_age_years": repo_age,
    }


def _build_github_url(
    repo_name: str,
    commit_sha: str,
    file_path: str,
    start_line: int,
    end_line: int,
) -> str:
    """Build a GitHub URL pointing to the fixture's file at the commit.

    Uses the blob URL with line anchors so reviewers can open the exact
    fixture code in the browser without cloning the repo.
    """
    if not repo_name or not commit_sha or not file_path:
        return ""
    sha = commit_sha.strip()
    if not sha:
        return ""
    path = file_path.lstrip("/")
    if start_line > 0 and end_line >= start_line:
        anchor = f"#L{start_line}-L{end_line}"
    else:
        anchor = ""
    return f"https://github.com/{repo_name}/blob/{sha}/{path}{anchor}"


def truncate_fixture_csvs(csv_paths: list[Path]) -> None:
    """Remove output CSV files so collection starts from a clean slate.

    This ensures that re-running the collection pipeline replaces existing
    CSV files instead of appending to them.

    Args:
        csv_paths: List of CSV file paths that should be truncated.
    """
    for path in csv_paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


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
        "scope",
        "cyclomatic_complexity",
        "max_nesting_depth",
        "num_parameters",
        "num_objects_instantiated",
        "num_external_calls",
        "has_teardown_pair",
        "github_url",
        "agent_type",
        "commit_kind",
        "commit_type",
        "raw_source",
    ]

    if extra_fields:
        fieldnames.extend(extra_fields.keys())

    write_header = not out_path.exists()

    try:
        csv.field_size_limit(10**7)
    except Exception:
        pass

    out_path.parent.mkdir(parents=True, exist_ok=True)

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
            "scope": fixture.get("scope", ""),
            "cyclomatic_complexity": fixture.get("cyclomatic_complexity", 0),
            "max_nesting_depth": fixture.get("max_nesting_depth", 0),
            "num_parameters": fixture.get("num_parameters", 0),
            "num_objects_instantiated": fixture.get("num_objects_instantiated", 0),
            "num_external_calls": fixture.get("num_external_calls", 0),
            "has_teardown_pair": fixture.get("has_teardown_pair", 0),
            "github_url": _build_github_url(
                repo_name,
                fixture.get("commit_sha", ""),
                fixture.get("file_path", ""),
                fixture.get("start_line", 0),
                fixture.get("end_line", 0),
            ),
            "agent_type": fixture.get("agent_type", ""),
            "commit_kind": fixture.get("commit_kind", "unknown"),
            "commit_type": fixture.get("commit_type", ""),
            "raw_source": fixture.get("raw_source", ""),
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
                    # Fixtures carry their own per-file language (detected
                    # from the actual file extension -- see
                    # agent_fixture_extractor.py's _get_language()), which
                    # can differ from the repo's aggregate language for
                    # multi-language repos (e.g. a Java test file inside a
                    # repo whose overall SEART-assigned language is
                    # JavaScript). Falling back to the repo-level `language`
                    # only covers extraction paths that don't set it.
                    fixture.get("language") or language,
                    fixture,
                    extra_fields={"is_complete_addition": 1},
                )

        # Upsert test files and insert fixtures
        test_files_cache = {}
        for fixture in fixtures:
            file_path = fixture.get("file_path", "unknown")
            fixture_language = fixture.get("language") or language

            # Cache test file lookups (per file_path AND language -- the
            # same relative path could theoretically appear in two
            # differently-labeled scans, though in practice a given
            # file_path has one real language).
            cache_key = (file_path, fixture_language)
            if cache_key not in test_files_cache:
                test_file_id = upsert_test_file(
                    conn, repo_id, file_path, fixture_language
                )
                test_files_cache[cache_key] = test_file_id
            else:
                test_file_id = test_files_cache[cache_key]

            # Build and insert fixture data
            fixture_data: dict[str, Any] = {
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
                "has_teardown_pair": fixture.get("has_teardown_pair"),
                "raw_source": fixture.get("raw_source"),
                "framework": fixture.get("framework"),
                "num_mocks": len(fixture.get("mocks", []) or []),
                "commit_sha": fixture.get("commit_sha", ""),
                "commit_kind": fixture.get("commit_kind", "unknown"),
                "agent_type": fixture.get("agent_type"),
                "is_complete_addition": 1,
                "commit_type": fixture.get("commit_type"),
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
                                    "category": mock.get("category", ""),
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
        # Re-sync the repositories-table summary counts to their true,
        # current totals -- this function is called once per fixture
        # language-group, potentially several times per repo, so these are
        # fresh COUNTs scoped to repo_id rather than accumulated locals
        # (correct regardless of call count/order, and self-healing if a
        # prior run only got partway through a repo's language groups).
        num_test_files_total = conn.execute(
            "SELECT COUNT(*) FROM test_files WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        num_fixtures_total = conn.execute(
            "SELECT COUNT(*) FROM fixtures WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        num_mock_usages_total = conn.execute(
            "SELECT COUNT(*) FROM mock_usages WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        set_repo_analysed(
            conn,
            repo_id,
            num_test_files=num_test_files_total,
            num_fixtures=num_fixtures_total,
            num_mock_usages=num_mock_usages_total,
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
    repo_age_years: Optional[float] = None,
    agent_adoption_intensity: Optional[str] = None,
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
        "repo_age_years": repo_age_years,
        "num_contributors": num_contributors or 0,
        "agent_adoption_intensity": agent_adoption_intensity,
    }


def generate_corpus_summary(
    stats: BaseCorpusStats,
    corpus_name: str,
    output_db: Path,
    temporal_scope: str,
    extra_metadata: Optional[dict] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Generate and save corpus collection summary to JSON.

    Args:
        stats: Collection statistics
        corpus_name: Name of corpus (agent, human)
        output_db: Path to output database
        temporal_scope: Description of temporal window
        extra_metadata: Optional additional metadata to include
        output_dir: Directory to write summary JSON (default: project output/ dir)

    Returns:
        Path to generated summary file
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
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
            "mean_repo_age_years": float(stats.mean_repo_age_years),
            "mean_contributors": float(stats.mean_contributors),
        },
        "output_database": str(output_db),
    }

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Summary saved to {summary_path}")
    return summary_path
