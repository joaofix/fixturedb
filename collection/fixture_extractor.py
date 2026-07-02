"""
Fixture Extraction Module

Handles extraction of fixtures from repositories using different strategies:
- Phase 2: Pre-2021 fixtures (snapshot-based extraction at pinned_commit)
- Phase 3: agent-generated fixtures (commit-by-commit with completeness validation)
"""

import fcntl
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import sleep
from typing import Dict, List, Optional, Tuple

from collection.logging_utils import get_logger

from .config import AGENT_CORPUS_START_DATE, CLONES_DIR, DB_PATH
from .db import db_session
from .detector import _get_parser, extract_fixtures
from .temp_clone import _output_requests_credentials
from .test_commit_utils import is_test_file_path

logger = get_logger(__name__)


def _resolve_repo_path(clones_dir: Path, repo_name: str) -> Path:
    """Resolve a repository path using either slash or double-underscore naming."""
    candidates = [
        clones_dir / repo_name,
        clones_dir / repo_name.replace("/", "__"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


@contextmanager
def _repo_worktree_lock(repo_path: Path):
    """Serialize checkout-based extraction for a repository path."""
    lock_path = repo_path / ".collection.lock"
    lock_path.touch(exist_ok=True)
    lock_file = lock_path.open("r+")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
        finally:
            lock_file.close()


def _checkout_commit(repo_path: Path, commit_sha: str) -> None:
    """Checkout a commit, falling back to fetching full history if needed.

    Raises RuntimeError if credentials are required (repo became private or was deleted).
    """
    lock_path = repo_path / ".git" / "index.lock"

    for attempt in range(3):
        try:
            result = subprocess.run(
                ["git", "checkout", commit_sha, "--quiet"],
                cwd=repo_path,
                timeout=30,
                check=True,
                capture_output=True,
                text=True,
            )
            return
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            stdout = exc.stdout or ""
            combined = stderr.lower() + stdout.lower()
            if _output_requests_credentials(stderr) or _output_requests_credentials(
                stdout
            ):
                raise RuntimeError("Repository requires credentials for checkout")
            if "index.lock" in combined:
                if lock_path.exists():
                    try:
                        lock_path.unlink()
                        logger.warning(
                            "Removed stale git index lock in %s before retrying checkout of %s",
                            repo_path,
                            commit_sha,
                        )
                    except Exception:
                        pass
                sleep(0.5 * (attempt + 1))
                continue

            try:
                result = subprocess.run(
                    ["git", "fetch", "--unshallow", "--tags", "origin"],
                    cwd=repo_path,
                    timeout=300,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                if _output_requests_credentials(result.stderr):
                    raise RuntimeError("Repository requires credentials for fetch")
                result = subprocess.run(
                    ["git", "checkout", commit_sha, "--quiet"],
                    cwd=repo_path,
                    timeout=30,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return
            except subprocess.CalledProcessError as fetch_exc:
                if _output_requests_credentials(fetch_exc.stderr or ""):
                    raise RuntimeError("Repository requires credentials for fetch")
                raise RuntimeError(f"Failed to checkout {commit_sha}: {fetch_exc}")
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Checkout timeout for {commit_sha}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Checkout timeout for {commit_sha}")

    raise RuntimeError(
        f"Failed to checkout {commit_sha}: stale git index lock persisted after retries"
    )


def extract_fixtures_at_commit(
    repo_path: Path, commit_sha: str, language: str
) -> List[Dict]:
    """Extract fixtures from a repository at a specific commit.

    This is the commit-level primitive used by the paired study workflow.
    """
    if not Path(repo_path).exists():
        raise RuntimeError(f"Repository not found: {repo_path}")

    with _repo_worktree_lock(repo_path):
        _checkout_commit(repo_path, commit_sha)

        extractor = Pre2021FixtureExtractor(
            clones_dir=repo_path.parent, source_db=DB_PATH
        )
        fixtures: List[Dict] = []

        try:
            test_files = extractor._find_test_files(repo_path, language)

            for test_file in test_files:
                try:
                    result = extract_fixtures(test_file, language)
                    for fixture in result.fixtures:
                        fixtures.append(
                            {
                                "name": fixture.name,
                                "fixture_type": fixture.fixture_type,
                                "framework": fixture.framework,
                                "scope": fixture.scope,
                                "loc": fixture.loc,
                                "language": language,
                                "file_path": str(test_file.relative_to(repo_path)),
                                "start_line": fixture.start_line,
                                "end_line": fixture.end_line,
                                "cyclomatic_complexity": fixture.cyclomatic_complexity,
                                "max_nesting_depth": fixture.max_nesting_depth,
                                "num_objects_instantiated": fixture.num_objects_instantiated,
                                "num_external_calls": fixture.num_external_calls,
                                "num_parameters": fixture.num_parameters,
                                "reuse_count": fixture.reuse_count,
                                "has_teardown_pair": fixture.has_teardown_pair,
                                "raw_source": fixture.raw_source,
                                "mocks": [
                                    {
                                        "framework": m.framework,
                                        "target_identifier": m.target_identifier,
                                        "num_interactions_configured": m.num_interactions_configured,
                                        "raw_snippet": m.raw_snippet,
                                    }
                                    for m in fixture.mocks
                                ],
                            }
                        )
                except Exception as exc:
                    logger.debug(f"Failed to extract from {test_file}: {exc}")
        except Exception as exc:
            raise RuntimeError(f"Failed to extract fixtures: {exc}")

    return fixtures


@dataclass
class Pre2021ExtractionStats:
    """Statistics from pre-2021 fixture extraction."""

    total_repositories: int = 0
    repositories_with_fixtures: int = 0
    total_fixtures_extracted: int = 0
    fixtures_by_type: Dict[str, int] = field(default_factory=dict)
    repositories_processed: List[str] = field(default_factory=list)
    repositories_failed: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class AgentExtractionStats:
    """Statistics from agent fixture extraction."""

    total_repositories: int = 0
    repositories_with_agent_commits: int = 0
    total_fixtures_extracted: int = 0
    fixtures_by_agent: Dict[str, int] = field(default_factory=dict)
    completely_added_fixtures: int = 0
    partially_modified_fixtures: int = 0
    repositories_processed: List[str] = field(default_factory=list)
    repositories_failed: List[Tuple[str, str]] = field(default_factory=list)


_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,\d+)? \+(?P<new_start>\d+)(?:,\d+)? @@"
)


def is_pure_addition(modified_file) -> bool:
    """Return True if the modified file's diff contains exclusively added lines.

    A file is considered a "pure addition" when:
    - It was not renamed, deleted, or copied (change_type not in RENAME/DELETE/COPY)
    - Its diff_parsed contains no deleted lines

    This uses PyDriller's ModifiedFile.diff_parsed and ModifiedFile.change_type.
    """
    from pydriller.domain.commit import ModificationType

    if modified_file.change_type in (
        ModificationType.RENAME,
        ModificationType.DELETE,
        ModificationType.COPY,
    ):
        return False

    diff_parsed = modified_file.diff_parsed
    if diff_parsed.get("deleted"):
        return False

    return True


def _raw_diff_file_is_pure_addition(diff_text: str, file_path: str) -> bool:
    """Check whether *file_path*'s chunk in a unified diff has no deletions or renames.

    Parses raw ``git show`` / ``git diff`` output and returns True only when
    the file's diff contains exclusively added lines (no ``-`` lines in hunks)
    and the old/new paths are identical (no rename).
    """
    lines = diff_text.splitlines()
    in_target = False
    old_path = None
    new_path = None

    for line in lines:
        if line.startswith("diff --git"):
            in_target = False
            parts = line.split()
            if len(parts) >= 4:
                a_path = parts[2][2:]  # strip "a/"
                b_path = parts[3][2:]  # strip "b/"
                if b_path == file_path or a_path == file_path:
                    in_target = True
                    old_path = a_path
                    new_path = b_path
            continue

        if not in_target:
            continue

        # Rename / copy / delete markers
        if line.startswith("rename from ") or line.startswith("rename to "):
            return False

        if line.startswith("copy from ") or line.startswith("copy to "):
            return False

        if line.startswith("deleted file mode"):
            return False

        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        # Hunk lines: a deletion line means the file is not a pure addition
        if line.startswith("-") and not line.startswith("---"):
            return False

        # Once we hit the next file header, we're done with this file's chunk
        # (but the loop already handles this via the diff --git check above)

    # If we never found the file in the diff, treat as not pure
    if old_path is None:
        return False

    # Cross-check: if old_path != new_path, it's effectively a rename
    if old_path != new_path:
        return False

    return True


def commit_is_pure_addition(commit) -> bool:
    """Return True only if every test file in *commit* is a pure addition.

    Iterates over ``commit.modified_files``, ignores non-test files, and
    returns False if any test file has deletions, is a DELETE, or is a RENAME.
    Uses PyDriller's ``ModifiedFile.diff_parsed`` and ``ModificationType``.
    """
    from pydriller.domain.commit import ModificationType

    for modified_file in commit.modified_files:
        filename = modified_file.new_path or modified_file.old_path or ""
        path_obj = Path(filename)
        language = get_language_static(path_obj)
        if language == "unknown" or not is_test_file_path(str(filename), language):
            continue

        if modified_file.change_type in (
            ModificationType.RENAME,
            ModificationType.DELETE,
            ModificationType.COPY,
        ):
            return False

        diff_parsed = modified_file.diff_parsed
        if diff_parsed.get("deleted"):
            return False

    return True


def get_language_static(file_path: Path) -> str:
    """Infer language from file extension (module-level, no instance needed)."""
    ext = file_path.suffix.lower()
    return {
        ".py": "python",
        ".java": "java",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".mts": "typescript",
        ".cts": "typescript",
    }.get(ext, "unknown")


def _raw_diff_commit_is_pure_addition(diff_text: str) -> bool:
    """Return True only if every test file in *diff_text* is a pure addition.

    Parses raw ``git show`` / ``git diff`` output.  For each file found in the
    diff, if the file is a test file and its hunk(s) contain any ``-`` line
    (deletion), or if it is a rename/delete, return False.
    Non-test files are ignored.
    """
    lines = diff_text.splitlines()
    current_file: Optional[str] = None
    current_test_lang: Optional[str] = None

    for line in lines:
        if line.startswith("diff --git"):
            current_file = None
            current_test_lang = None
            parts = line.split()
            if len(parts) >= 4:
                b_path = parts[3][2:]  # strip "b/"
                current_file = b_path
                path_obj = Path(current_file)
                lang = get_language_static(path_obj)
                if lang != "unknown" and is_test_file_path(current_file, lang):
                    current_test_lang = lang
            continue

        if current_file is None:
            continue

        # Rename / copy / delete markers
        if line.startswith("rename from ") or line.startswith("rename to "):
            if current_test_lang is not None:
                return False
            continue

        if line.startswith("copy from ") or line.startswith("copy to "):
            if current_test_lang is not None:
                return False
            continue

        if line.startswith("deleted file mode"):
            if current_test_lang is not None:
                return False
            continue

        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        # A deletion line in a hunk
        if line.startswith("-") and not line.startswith("---"):
            if current_test_lang is not None:
                return False

    return True


@dataclass(frozen=True)
class DiffLineMap:
    """Per-file map of new-file line numbers to diff states."""

    line_states: Dict[int, str]

    def fixture_is_completely_added(self, start_line: int, end_line: int) -> bool:
        """Return True only if every line in the fixture span is newly added."""
        if start_line <= 0 or end_line < start_line:
            return False

        for line_no in range(start_line, end_line + 1):
            if self.line_states.get(line_no) != "added":
                return False

        return True


class Pre2021FixtureExtractor:
    """Phase 2: Extract fixtures from pinned commits (snapshot-based)."""

    def __init__(
        self,
        clones_dir: Path = CLONES_DIR,
        source_db: Path = DB_PATH,
    ):
        """
        Initialize pre-2021 fixture extractor.

        Args:
            clones_dir: Directory containing cloned repositories
            source_db: Source database (corpus.db) to query
        """
        self.clones_dir = Path(clones_dir)
        self.source_db = Path(source_db) if source_db is not None else None
        self.stats = Pre2021ExtractionStats()
        self.all_fixtures: List[Dict] = []

    def extract_all(
        self,
        min_year: int = 2000,
        max_year: int = 2020,
        show_progress: bool = True,
        repo_names: Optional[List[str]] = None,
    ) -> Pre2021ExtractionStats:
        """
        Extract pre-2021 fixtures from all eligible repositories.

        Args:
            min_year: Minimum year for repository creation
            max_year: Maximum year for fixture extraction (2020 = up to 2020-12-31)
            show_progress: Whether to log progress

        Returns:
            Pre2021ExtractionStats with extraction results
        """
        logger.info(f"Starting pre-2021 fixture extraction ({min_year}-{max_year})")
        self.stats = Pre2021ExtractionStats()
        self.all_fixtures = []

        # Get repositories from corpus.db
        repos = self._get_eligible_repositories()

        if repo_names:
            selected = set(repo_names)
            repos = [repo for repo in repos if repo.get("full_name") in selected]

        self.stats.total_repositories = len(repos)

        if not repos:
            logger.warning("No repositories found in corpus.db")
            return self.stats

        logger.info(f"Found {len(repos)} repositories to process")

        for idx, repo in enumerate(repos, 1):
            repo["id"]
            repo_name = repo["full_name"]
            pinned_commit = repo["pinned_commit"]
            language = repo["language"]

            try:
                # Extract fixtures from this repository at its pinned commit
                fixtures = self._extract_from_repo(
                    repo_name=repo_name,
                    commit_sha=pinned_commit,
                    language=language,
                )

                if fixtures:
                    self.stats.repositories_with_fixtures += 1
                    self.stats.total_fixtures_extracted += len(fixtures)
                    self.all_fixtures.extend(fixtures)

                    # Count by type
                    for fixture in fixtures:
                        fixture_type = fixture.get("fixture_type", "unknown")
                        self.stats.fixtures_by_type[fixture_type] = (
                            self.stats.fixtures_by_type.get(fixture_type, 0) + 1
                        )

                    self.stats.repositories_processed.append(repo_name)

                    if show_progress:
                        logger.info(
                            f"[{idx}/{len(repos)}] {repo_name}: "
                            f"Extracted {len(fixtures)} fixtures"
                        )
                else:
                    if show_progress and idx % 20 == 0:
                        logger.info(
                            f"[{idx}/{len(repos)}] Processed {idx} repos, "
                            f"{self.stats.total_fixtures_extracted} fixtures so far"
                        )

            except Exception as e:
                logger.warning(f"Failed to extract from {repo_name}: {e}")
                self.stats.repositories_failed.append((repo_name, str(e)))

        return self.stats

    def insert_all(self, target_db: Path) -> int:
        """
        Insert all collected pre-2021 fixtures into the target database.

        Args:
            target_db: Path to target database (fixturedb-human.db)

        Returns:
            Number of fixtures currently stored after this extraction pass.
        """
        from .db import (
            db_session,
            insert_fixture,
            insert_mock_usage,
            upsert_repository,
            upsert_test_file,
        )

        if not self.all_fixtures:
            logger.warning("No human fixtures to insert")
            return 0

        logger.info(f"Inserting {len(self.all_fixtures)} human fixtures")

        try:
            with db_session(target_db) as conn:
                before_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM fixtures"
                ).fetchone()["c"]

                fixtures_by_repo: Dict[str, List[Dict]] = {}
                for fixture in self.all_fixtures:
                    repo_name = fixture.get("repo_name")
                    if repo_name not in fixtures_by_repo:
                        fixtures_by_repo[repo_name] = []
                    fixtures_by_repo[repo_name].append(fixture)

                for repo_name, repo_fixtures in fixtures_by_repo.items():
                    try:
                        lookup_name = (
                            repo_name.replace("__", "/")
                            if "__" in repo_name
                            else repo_name
                        )

                        with db_session(self.source_db) as source_conn:
                            source_row = source_conn.execute(
                                """
                                SELECT github_id, full_name, language, stars, forks,
                                       description, topics, created_at, pushed_at, clone_url
                                FROM repositories
                                WHERE full_name = ?
                                """,
                                (lookup_name,),
                            ).fetchone()

                        if source_row is None:
                            logger.debug(
                                "Repository metadata not found in source DB for %s; "
                                "using minimal repo metadata from fixtures",
                                repo_name,
                            )
                            repo_data = {
                                "id": None,
                                "github_id": None,
                                "full_name": repo_name,
                                "language": (
                                    repo_fixtures[0].get("language", "unknown")
                                    if repo_fixtures
                                    else "unknown"
                                ),
                                "stars": 0,
                                "forks": 0,
                                "description": "",
                                "topics": "[]",
                                "created_at": "",
                                "pushed_at": "",
                                "clone_url": f"https://github.com/{repo_name}.git",
                                "num_contributors": 0,
                                "status": "analysed",
                            }
                        else:
                            repo_data = dict(source_row)
                            repo_data["status"] = "analysed"
                        repo_id, _ = upsert_repository(conn, repo_data)

                        files_by_path: Dict[str, List[Dict]] = {}
                        for fixture in repo_fixtures:
                            file_path = fixture.get("file_path", "unknown")
                            if file_path not in files_by_path:
                                files_by_path[file_path] = []
                            files_by_path[file_path].append(fixture)

                        for file_path, file_fixtures in files_by_path.items():
                            file_id = upsert_test_file(
                                conn,
                                repo_id,
                                file_path,
                                file_fixtures[0].get("language", "unknown"),
                            )

                            for fixture in file_fixtures:
                                mocks = fixture.get("mocks", [])
                                fixture_data = {
                                    "file_id": file_id,
                                    "repo_id": repo_id,
                                    "name": fixture.get("name"),
                                    "fixture_type": fixture.get("fixture_type"),
                                    "scope": fixture.get("scope", "unknown"),
                                    "start_line": fixture.get("start_line", 0),
                                    "end_line": fixture.get("end_line", 0),
                                    "loc": fixture.get("loc", 0),
                                    "cyclomatic_complexity": fixture.get(
                                        "cyclomatic_complexity", 0
                                    ),
                                    "max_nesting_depth": fixture.get(
                                        "max_nesting_depth", 0
                                    ),
                                    "num_objects_instantiated": fixture.get(
                                        "num_objects_instantiated", 0
                                    ),
                                    "num_external_calls": fixture.get(
                                        "num_external_calls", 0
                                    ),
                                    "num_parameters": fixture.get("num_parameters", 0),
                                    "reuse_count": fixture.get("reuse_count", 0),
                                    "has_teardown_pair": fixture.get(
                                        "has_teardown_pair", 0
                                    ),
                                    "raw_source": fixture.get("raw_source", ""),
                                    "framework": fixture.get("framework"),
                                    "num_mocks": len(mocks),
                                }
                                fixture_id = insert_fixture(conn, fixture_data)

                                for mock in mocks:
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
                        logger.warning(
                            f"Failed to insert human fixtures from {repo_name}: {e}"
                        )

                conn.execute("""
                    UPDATE fixtures
                    SET num_mocks = (
                        SELECT COUNT(*)
                        FROM mock_usages
                        WHERE mock_usages.fixture_id = fixtures.id
                    )
                    """)

                after_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM fixtures"
                ).fetchone()["c"]
                inserted_count = max(0, after_count - before_count)
                logger.info(f"Stored {inserted_count} human fixtures in {target_db}")
                return inserted_count

        except Exception as e:
            logger.error(f"Error inserting human fixtures: {e}", exc_info=True)
            raise RuntimeError(f"Failed to insert human fixtures: {e}") from e

    def _get_eligible_repositories(self) -> List[Dict]:
        """
        Get repositories from corpus.db that have fixtures and pinned commits.

        Returns:
            List of repository dicts with id, full_name, pinned_commit, language
        """
        repos = []

        try:
            with db_session(self.source_db) as conn:
                rows = conn.execute("""
                    SELECT
                        id, full_name, pinned_commit, language,
                        num_test_files, num_fixtures, created_at
                    FROM repositories
                    WHERE
                        pinned_commit IS NOT NULL
                        AND num_fixtures > 0
                        AND status IN ('analysed', 'cloned')
                    ORDER BY num_fixtures DESC
                """).fetchall()

                repos = [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to query repositories: {e}")

        return repos

    def _extract_from_repo(
        self,
        repo_name: str,
        commit_sha: str,
        language: str,
    ) -> List[Dict]:
        """
        Extract fixtures from a repository at a specific commit.

        Args:
            repo_name: Repository name (e.g., 'owner__repo')
            commit_sha: Commit SHA to extract from
            language: Programming language

        Returns:
            List of fixture dicts extracted from the repository
        """
        repo_path = _resolve_repo_path(self.clones_dir, repo_name)

        if not repo_path.exists():
            raise RuntimeError(f"Repository not found: {repo_path}")

        fixtures = []

        with _repo_worktree_lock(repo_path):
            # Checkout specific commit
            _checkout_commit(repo_path, commit_sha)

            # Extract fixtures from test files
            try:
                # Find test files
                test_files = self._find_test_files(repo_path, language)

                for test_file in test_files:
                    try:
                        result = extract_fixtures(test_file, language)

                        for fixture in result.fixtures:
                            fixtures.append(
                                {
                                    "repo_name": repo_name,
                                    "name": fixture.name,
                                    "fixture_type": fixture.fixture_type,
                                    "framework": fixture.framework,
                                    "scope": fixture.scope,
                                    "loc": fixture.loc,
                                    "language": language,
                                    "file_path": str(test_file.relative_to(repo_path)),
                                    "start_line": fixture.start_line,
                                    "end_line": fixture.end_line,
                                    "cyclomatic_complexity": fixture.cyclomatic_complexity,
                                    "max_nesting_depth": fixture.max_nesting_depth,
                                    "num_objects_instantiated": fixture.num_objects_instantiated,
                                    "num_external_calls": fixture.num_external_calls,
                                    "num_parameters": fixture.num_parameters,
                                    "reuse_count": fixture.reuse_count,
                                    "has_teardown_pair": fixture.has_teardown_pair,
                                    "raw_source": fixture.raw_source,
                                    "mocks": [
                                        {
                                            "framework": m.framework,
                                            "target_identifier": m.target_identifier,
                                            "num_interactions_configured": m.num_interactions_configured,
                                            "raw_snippet": m.raw_snippet,
                                        }
                                        for m in fixture.mocks
                                    ],
                                }
                            )

                    except Exception as e:
                        logger.debug(f"Failed to extract from {test_file}: {e}")

            except Exception as e:
                raise RuntimeError(f"Failed to extract fixtures: {e}")

        return fixtures

    def _find_test_files(self, repo_path: Path, language: str) -> List[Path]:
        """
        Find test files in a repository for given language.

        Args:
            repo_path: Path to repository
            language: Programming language

        Returns:
            List of test file paths
        """
        from .config import LANGUAGE_CONFIGS

        config = LANGUAGE_CONFIGS.get(language.lower())
        if not config:
            return []

        test_files: List[Path] = []
        seen: set[Path] = set()

        # First pass: canonical test filename conventions (fast and precise).
        for suffix in config.test_file_suffixes:
            for match in repo_path.rglob(f"*{suffix}"):
                if match.is_file() and self._should_process_file(match, language):
                    if match not in seen:
                        seen.add(match)
                        test_files.append(match)

        # Second pass: fallback to files located under common test directories.
        path_markers = [p.strip("/") for p in config.test_path_patterns]
        for match in repo_path.rglob("*"):
            if not match.is_file() or not self._should_process_file(match, language):
                continue

            rel_parts = set(match.relative_to(repo_path).parts)
            if any(marker in rel_parts for marker in path_markers):
                if match not in seen:
                    seen.add(match)
                    test_files.append(match)

        return test_files

    def _should_process_file(self, file_path: Path, language: str) -> bool:
        """
        Check if a file should be processed.

        Args:
            file_path: Path to file
            language: Programming language

        Returns:
            True if file should be processed
        """
        from .config import MAX_FILE_SIZE_BYTES, NON_CODE_EXTENSIONS

        language_extensions = {
            "python": {".py"},
            "java": {".java"},
            "javascript": {".js", ".jsx", ".mjs", ".cjs"},
            "typescript": {".ts", ".tsx", ".mts", ".cts"},
        }

        # Check extension
        allowed_extensions = language_extensions.get(language.lower(), set())
        if not allowed_extensions or file_path.suffix.lower() not in allowed_extensions:
            return False
        if file_path.suffix.lower() in NON_CODE_EXTENSIONS:
            return False

        # Check file size
        try:
            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                return False
        except (OSError, ValueError):
            return False

        return True


class AgentFixtureExtractor:
    """Phase 3: Extract agent-generated fixtures with completeness validation."""

    def __init__(
        self,
        clones_dir: Path = CLONES_DIR,
        source_db: Path = DB_PATH,
        start_date: str = AGENT_CORPUS_START_DATE,
    ):
        """
        Initialize AGENT fixture extractor.

        Args:
            clones_dir: Directory containing cloned repositories
            source_db: Source database to query
            start_date: Only extract commits after this date (ISO format)
        """
        self.clones_dir = Path(clones_dir)
        self.source_db = Path(source_db) if source_db is not None else None
        self.start_date = start_date
        self.stats = AgentExtractionStats()
        self.all_fixtures = []

    def extract_all(
        self,
        agent_commits: Dict[str, Dict[str, str]],
        show_progress: bool = True,
    ) -> AgentExtractionStats:
        """
        Extract AGENT-generated fixtures from verified agent commits.

        Args:
            agent_commits: Dict from Phase 1B: {repo_name: {commit_sha: agent_type}}
            show_progress: Whether to log progress

        Returns:
            AgentExtractionStats with extraction results
        """
        logger.info("Starting agent fixture extraction from verified agent commits")

        repos_to_process = list(agent_commits.keys())
        self.stats = AgentExtractionStats()
        self.stats.total_repositories = len(repos_to_process)
        self.stats.repositories_with_agent_commits = len(repos_to_process)
        self.all_fixtures = []

        logger.info(f"Found {len(repos_to_process)} repositories with agent commits")

        for idx, repo_name in enumerate(repos_to_process, 1):
            commits_dict = agent_commits[repo_name]

            try:
                # Extract fixtures from agent commits
                fixtures = self._extract_from_agent_commits(
                    repo_name=repo_name,
                    commits=commits_dict,
                )

                if fixtures:
                    self.stats.total_fixtures_extracted += len(fixtures)
                    self.all_fixtures.extend(fixtures)

                    # Count by agent type
                    for fixture in fixtures:
                        agent_type = fixture.get("agent_type", "unknown")
                        self.stats.fixtures_by_agent[agent_type] = (
                            self.stats.fixtures_by_agent.get(agent_type, 0) + 1
                        )

                        if fixture.get("is_complete_addition"):
                            self.stats.completely_added_fixtures += 1
                        else:
                            self.stats.partially_modified_fixtures += 1

                    self.stats.repositories_processed.append(repo_name)

                    if show_progress:
                        logger.info(
                            f"[{idx}/{len(repos_to_process)}] {repo_name}: "
                            f"Extracted {len(fixtures)} fixtures "
                            f"({self.stats.completely_added_fixtures} complete)"
                        )

            except Exception as e:
                logger.warning(f"Failed to extract from {repo_name}: {e}")
                self.stats.repositories_failed.append((repo_name, str(e)))

        return self.stats

    def insert_all(self, target_db: Path, match_scope: str = "within_repo") -> int:
        """
        Insert all collected fixtures into the target database with a match_scope label.

        Args:
            target_db: Path to target database (fixturedb-agent.db)
            match_scope: Source matching scope ('within_repo' or 'cross_repo'). Default: 'within_repo'

        Returns:
            Number of fixtures inserted

        Raises:
            RuntimeError: If target database is not initialized
        """
        from .db import (
            db_session,
            insert_fixture,
            insert_mock_usage,
            upsert_repository,
            upsert_test_file,
        )

        if not self.all_fixtures:
            logger.warning("No fixtures to insert")
            return 0

        logger.info(
            f"Inserting {len(self.all_fixtures)} fixtures with match_scope={match_scope}"
        )

        try:
            with db_session(target_db) as conn:
                before_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM fixtures"
                ).fetchone()["c"]

                # Group fixtures by repository
                fixtures_by_repo = {}
                for fixture in self.all_fixtures:
                    repo_name = fixture.get("repo_name")
                    if repo_name not in fixtures_by_repo:
                        fixtures_by_repo[repo_name] = []
                    fixtures_by_repo[repo_name].append(fixture)

                # Insert fixtures repo by repo
                for repo_name, repo_fixtures in fixtures_by_repo.items():
                    try:
                        lookup_name = (
                            repo_name.replace("__", "/")
                            if "__" in repo_name
                            else repo_name
                        )

                        with db_session(self.source_db) as source_conn:
                            source_row = source_conn.execute(
                                """
                                SELECT github_id, full_name, language, stars, forks,
                                       description, topics, created_at, pushed_at, clone_url
                                FROM repositories
                                WHERE full_name = ?
                                """,
                                (lookup_name,),
                            ).fetchone()

                        if source_row is None:
                            logger.debug(
                                "Repository metadata not found in source DB for %s; "
                                "using minimal repo metadata from fixtures",
                                repo_name,
                            )
                            repo_data = {
                                "id": None,
                                "github_id": None,
                                "full_name": repo_name,
                                "language": (
                                    repo_fixtures[0].get("language", "unknown")
                                    if repo_fixtures
                                    else "unknown"
                                ),
                                "stars": 0,
                                "forks": 0,
                                "description": "",
                                "topics": "[]",
                                "created_at": "",
                                "pushed_at": "",
                                "clone_url": f"https://github.com/{repo_name}.git",
                                "num_contributors": 0,
                                "status": "analysed",
                            }
                        else:
                            repo_data = dict(source_row)
                            repo_data["status"] = "analysed"

                        repo_id, _ = upsert_repository(conn, repo_data)

                        # Process test files
                        files_by_path = {}
                        for fixture in repo_fixtures:
                            file_path = fixture.get("file_path", "unknown")
                            if file_path not in files_by_path:
                                files_by_path[file_path] = []
                            files_by_path[file_path].append(fixture)

                        # Insert test file records and fixtures
                        for file_path, file_fixtures in files_by_path.items():
                            test_file_data = {
                                "repo_id": repo_id,
                                "relative_path": file_path,
                                "language": file_fixtures[0].get("language", "unknown"),
                                "file_loc": 0,  # Not computed for AGENT extraction
                                "num_test_funcs": 0,
                                "num_fixtures": len(file_fixtures),
                            }
                            file_id = upsert_test_file(
                                conn,
                                repo_id,
                                file_path,
                                test_file_data["language"],
                            )

                            # Insert each fixture with match_scope label
                            for fixture in file_fixtures:
                                mocks = fixture.get("mocks", [])
                                fixture_data = {
                                    "file_id": file_id,
                                    "repo_id": repo_id,
                                    "name": fixture.get("name"),
                                    "fixture_type": fixture.get("fixture_type"),
                                    "scope": fixture.get("scope", "unknown"),
                                    "start_line": fixture.get("start_line", 0),
                                    "end_line": fixture.get("end_line", 0),
                                    "loc": fixture.get("loc", 0),
                                    "cyclomatic_complexity": 0,
                                    "max_nesting_depth": 0,
                                    "num_objects_instantiated": 0,
                                    "num_external_calls": 0,
                                    "num_parameters": 0,
                                    "reuse_count": 0,
                                    "has_teardown_pair": 0,
                                    "raw_source": fixture.get("raw_source", ""),
                                    "framework": fixture.get("framework"),
                                    "num_mocks": len(mocks),
                                    # Agent-specific fields
                                    "commit_sha": fixture.get("commit_sha"),
                                    "agent_type": fixture.get("agent_type"),
                                    "match_scope": match_scope,
                                    "is_complete_addition": (
                                        1 if fixture.get("is_complete_addition") else 0
                                    ),
                                }
                                fixture_id = insert_fixture(conn, fixture_data)

                                for mock in mocks:
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
                        logger.warning(
                            f"Failed to insert fixtures from {repo_name}: {e}"
                        )

                conn.execute("""
                    UPDATE fixtures
                    SET num_mocks = (
                        SELECT COUNT(*)
                        FROM mock_usages
                        WHERE mock_usages.fixture_id = fixtures.id
                    )
                    """)

                conn.commit()
                after_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM fixtures"
                ).fetchone()["c"]
                inserted_count = max(0, after_count - before_count)
                logger.info(f"Successfully inserted {inserted_count} fixtures")
                return inserted_count

        except Exception as e:
            logger.error(f"Error inserting fixtures: {e}", exc_info=True)
            raise RuntimeError(f"Failed to insert fixtures: {e}") from e

    def _extract_from_agent_commits(
        self,
        repo_name: str,
        commits: Dict[str, str],
    ) -> List[Dict]:
        """
        Extract fixtures from agent commits in a repository.

        Args:
            repo_name: Repository name
            commits: Dict mapping commit_sha to agent_type

        Returns:
            List of fixture dicts with commit_sha, agent_type, is_complete_addition
        """
        repo_path = _resolve_repo_path(self.clones_dir, repo_name)

        if not repo_path.exists():
            raise RuntimeError(f"Repository not found: {repo_path}")

        fixtures = []
        seen_fixtures: set[tuple] = set()

        # Per-repo purity counters
        total_agent_commits = len(commits)
        commits_skipped_commit_level = 0
        commits_skipped_file_level = 0
        commits_proceeded = 0
        duplicates_skipped = 0

        for commit_sha, agent_type in commits.items():
            try:
                with _repo_worktree_lock(repo_path):
                    # Checkout commit
                    _checkout_commit(repo_path, commit_sha)

                    # Get commit metadata
                    commit_info = self._get_commit_info(repo_path, commit_sha)
                    if not commit_info:
                        continue

                    # Check if commit date is within range
                    if commit_info["date"] < self.start_date:
                        continue

                    # Get diff to check for complete additions
                    diff_info = self._get_commit_diff(repo_path, commit_sha)

                    # ── Commit‑level purity gate ──
                    if not diff_info:
                        continue

                    if not _raw_diff_commit_is_pure_addition(diff_info):
                        logger.debug(
                            "Skipping entire commit %s in %s: a test file contains "
                            "deletions, is deleted, or is renamed",
                            commit_sha[:8],
                            repo_name,
                        )
                        commits_skipped_commit_level += 1
                        continue

                    # Extract fixtures
                    commit_fixtures = self._extract_from_diff(
                        repo_path=repo_path,
                        repo_name=repo_name,
                        diff_info=diff_info,
                        commit_sha=commit_sha,
                        agent_type=agent_type,
                    )

                    if commit_fixtures:
                        commits_proceeded += 1
                    else:
                        # Commit passed commit-level gate but all files were filtered
                        # at file level → count as file-level skip
                        commits_skipped_file_level += 1

                    for fixture in commit_fixtures:
                        fixture_key = (
                            fixture.get("file_path"),
                            fixture.get("start_line"),
                            fixture.get("end_line"),
                            fixture.get("name"),
                            fixture.get("fixture_type"),
                        )
                        if fixture_key in seen_fixtures:
                            duplicates_skipped += 1
                            continue
                        seen_fixtures.add(fixture_key)
                        fixtures.append(fixture)

            except Exception as e:
                logger.debug(f"Failed to extract from {commit_sha}: {e}")

        logger.info(
            "Repo %s: %d commits found, %d skipped (commit-level), "
            "%d skipped (file-level), %d proceeded to extraction, "
            "%d duplicates skipped, %d fixtures extracted",
            repo_name,
            total_agent_commits,
            commits_skipped_commit_level,
            commits_skipped_file_level,
            commits_proceeded,
            duplicates_skipped,
            len(fixtures),
        )

        return fixtures

    def _get_commit_info(self, repo_path: Path, commit_sha: str) -> Optional[Dict]:
        """
        Get commit metadata (date, author, message).

        Args:
            repo_path: Path to repository
            commit_sha: Commit SHA

        Returns:
            Dict with commit info or None
        """
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%ai|%an|%ae|%B", commit_sha],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )

            parts = result.stdout.strip().split("|", 3)
            if len(parts) < 4:
                return None

            timestamp = parts[0]
            date = timestamp.split(" ")[0]  # Extract YYYY-MM-DD

            return {
                "date": date,
                "author_name": parts[1],
                "author_email": parts[2],
                "message": parts[3] if len(parts) > 3 else "",
            }

        except Exception as e:
            logger.debug(f"Failed to get commit info: {e}")
            return None

    def _get_commit_diff(self, repo_path: Path, commit_sha: str) -> Optional[str]:
        """
        Get unified diff for a commit.

        Args:
            repo_path: Path to repository
            commit_sha: Commit SHA

        Returns:
            Unified diff string or None
        """
        try:
            result = subprocess.run(
                ["git", "show", "--unified=3", commit_sha],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            return result.stdout

        except Exception as e:
            logger.debug(f"Failed to get diff: {e}")
            return None

    def _extract_from_diff(
        self,
        repo_path: Path,
        repo_name: str,
        diff_info: str,
        commit_sha: str,
        agent_type: str,
    ) -> List[Dict]:
        """
        Extract fixtures from commit diff.

        CRITICAL: Only include fixtures that are completely added (100% new lines).
        No modifications or refactoring.

        Args:
            repo_path: Path to repository
            repo_name: Repository name (for tracking)
            diff_info: Unified diff output
            commit_sha: Commit SHA
            agent_type: Agent type (from Phase 1B)

        Returns:
            List of fixtures completely added in this commit
        """
        if not diff_info:
            return []

        fixtures = []
        diff_maps = self._build_diff_line_maps(diff_info)

        # Parse diff to find added test functions/methods with fixture decorator
        # This is a simplified implementation - real implementation would parse diff
        # and detect fixture definitions line by line

        # For now, extract all fixtures and mark as complete/partial based on
        # whether all lines in the diff are additions (not modifications)

        test_files = self._find_added_test_files(diff_info)

        purity_skipped_count = 0

        for file_path in test_files:
            # ── Purity gate: only extract from files whose diff is 100% additions ──
            if not _raw_diff_file_is_pure_addition(diff_info, file_path):
                logger.debug(
                    "Skipping %s in %s: diff contains deletions or is a rename",
                    file_path,
                    commit_sha[:8],
                )
                purity_skipped_count += 1
                continue

            full_path = repo_path / file_path

            if full_path.exists():
                try:
                    language = self._get_language(full_path)
                    result = extract_fixtures(full_path, language)
                    diff_map = diff_maps.get(file_path)

                    for fixture in result.fixtures:
                        is_complete = self._is_fixture_completely_added(
                            full_path=full_path,
                            fixture=fixture,
                            diff_map=diff_map,
                            language=language,
                        )

                        fixtures.append(
                            {
                                "repo_name": repo_name,
                                "name": fixture.name,
                                "fixture_type": fixture.fixture_type,
                                "scope": fixture.scope,
                                "loc": fixture.loc,
                                "language": language,
                                "file_path": file_path,
                                "start_line": fixture.start_line,
                                "end_line": fixture.end_line,
                                "cyclomatic_complexity": fixture.cyclomatic_complexity,
                                "max_nesting_depth": fixture.max_nesting_depth,
                                "num_objects_instantiated": fixture.num_objects_instantiated,
                                "num_external_calls": fixture.num_external_calls,
                                "num_parameters": fixture.num_parameters,
                                "reuse_count": fixture.reuse_count,
                                "has_teardown_pair": fixture.has_teardown_pair,
                                "raw_source": fixture.raw_source,
                                "framework": fixture.framework,
                                "mocks": [
                                    {
                                        "framework": m.framework,
                                        "target_identifier": m.target_identifier,
                                        "num_interactions_configured": m.num_interactions_configured,
                                        "raw_snippet": m.raw_snippet,
                                    }
                                    for m in fixture.mocks
                                ],
                                "commit_sha": commit_sha,
                                "agent_type": agent_type,
                                "is_complete_addition": is_complete,
                            }
                        )

                except Exception as e:
                    logger.debug(f"Failed to extract from {file_path}: {e}")

        if purity_skipped_count > 0:
            logger.info(
                "Commit %s: purity filter skipped %d file(s) (deletions or rename detected)",
                commit_sha[:8],
                purity_skipped_count,
            )

        return fixtures

    def _extract_from_snapshot_file(
        self,
        repo_path: Path,
        file_path: str,
        language: str,
        cutoff_commit_sha: str,
        cutoff_commit_date: str,
    ) -> List[Dict]:
        """Extract ALL fixtures from a full test file at the repo checkout.

        No diff analysis, no pure-addition gate. Used for Dataset C snapshot extraction.
        """
        full_path = repo_path / file_path
        if not full_path.exists():
            return []

        try:
            result = extract_fixtures(full_path, language)
        except Exception as exc:
            logger.debug("Failed to extract fixtures from %s: %s", file_path, exc)
            return []

        fixtures = []
        for fixture in result.fixtures:
            fixtures.append(
                {
                    "repo_name": repo_path.name,
                    "name": fixture.name,
                    "fixture_type": fixture.fixture_type,
                    "scope": fixture.scope,
                    "loc": fixture.loc,
                    "language": language,
                    "file_path": file_path,
                    "start_line": fixture.start_line,
                    "end_line": fixture.end_line,
                    "cyclomatic_complexity": fixture.cyclomatic_complexity,
                    "max_nesting_depth": fixture.max_nesting_depth,
                    "num_objects_instantiated": fixture.num_objects_instantiated,
                    "num_external_calls": fixture.num_external_calls,
                    "num_parameters": fixture.num_parameters,
                    "reuse_count": fixture.reuse_count,
                    "has_teardown_pair": fixture.has_teardown_pair,
                    "raw_source": fixture.raw_source,
                    "framework": fixture.framework,
                    "mocks": [
                        {
                            "framework": m.framework,
                            "target_identifier": m.target_identifier,
                            "num_interactions_configured": m.num_interactions_configured,
                            "raw_snippet": m.raw_snippet,
                        }
                        for m in fixture.mocks
                    ],
                    "commit_sha": cutoff_commit_sha,
                    "commit_date": cutoff_commit_date,
                    "agent_type": "human_pre2022",
                    "commit_kind": "human",
                    "is_complete_addition": 1,
                }
            )
        return fixtures

    def _is_fixture_completely_added(
        self,
        full_path: Path,
        fixture,
        diff_map: Optional[DiffLineMap],
        language: str,
    ) -> bool:
        """Check completeness using AST node spans first, then fall back to line spans."""
        if diff_map is None:
            return False

        if fixture.start_line <= 0 or fixture.end_line < fixture.start_line:
            return False

        try:
            parser = _get_parser(language)
            source_bytes = full_path.read_bytes()
            tree = parser.parse(source_bytes)
            target_node = self._find_enclosing_node(
                tree.root_node,
                fixture.start_line,
                fixture.end_line,
            )

            if target_node is not None:
                line_numbers = self._collect_named_node_lines(target_node)
                if line_numbers:
                    return all(
                        diff_map.line_states.get(line_no) == "added"
                        for line_no in line_numbers
                    )
        except Exception as exc:
            logger.debug(
                "AST completeness check failed for %s:%s-%s (%s): %s",
                full_path,
                fixture.start_line,
                fixture.end_line,
                language,
                exc,
            )

        return diff_map.fixture_is_completely_added(
            fixture.start_line,
            fixture.end_line,
        )

    def _find_enclosing_node(self, root, start_line: int, end_line: int):
        """Find the smallest AST node that encloses the fixture span."""
        best_node = None
        best_rank = None

        def visit(node):
            nonlocal best_node, best_rank

            node_start = node.start_point[0] + 1
            node_end = node.end_point[0] + 1

            if node_start <= start_line and node_end >= end_line:
                span = node_end - node_start
                rank = (span, 1 if node.type == "module" else 0)
                if best_rank is None or rank < best_rank:
                    best_node = node
                    best_rank = rank

                for child in node.children:
                    child_start = child.start_point[0] + 1
                    child_end = child.end_point[0] + 1
                    if child_start <= end_line and child_end >= start_line:
                        visit(child)

        visit(root)
        return best_node

    def _collect_named_node_lines(self, node) -> set[int]:
        """Collect line numbers covered by named leaf AST nodes under a target node."""
        lines: set[int] = set()

        def visit(current):
            named_children = list(getattr(current, "named_children", []))

            if getattr(current, "type", None) == "comment":
                return

            if getattr(current, "is_named", False) and not named_children:
                start_line = current.start_point[0] + 1
                end_line = current.end_point[0] + 1
                for line_no in range(start_line, end_line + 1):
                    lines.add(line_no)

            for child in named_children:
                visit(child)

        visit(node)
        return lines

    def _find_added_test_files(self, diff: str) -> List[str]:
        """
        Find test files that were added in the diff.
        Args:
            diff: Unified diff output

        Returns:
            List of test file paths
        """
        files = []

        for line in diff.split("\n"):
            if line.startswith("diff --git"):
                # Extract file path
                parts = line.split()
                if len(parts) >= 4:
                    file_path = parts[3][2:]  # Remove 'b/' prefix
                    path_obj = Path(file_path)
                    language = self._get_language(path_obj)

                    if language != "unknown" and is_test_file_path(file_path, language):
                        files.append(file_path)

        return files

    def _build_diff_line_maps(self, diff: str) -> Dict[str, DiffLineMap]:
        """
        considered completely added when every line in its [start_line, end_line]
        span is marked as ``added``.
        """
        file_states: Dict[str, Dict[int, str]] = {}
        current_file: Optional[str] = None
        new_line_no: Optional[int] = None

        for raw_line in diff.splitlines():
            if raw_line.startswith("diff --git"):
                current_file = None
                new_line_no = None
                continue

            if raw_line.startswith("+++ b/"):
                current_file = raw_line[len("+++ b/") :].strip()
                file_states.setdefault(current_file, {})
                continue

            hunk_match = _HUNK_HEADER_RE.match(raw_line)
            if hunk_match:
                new_line_no = int(hunk_match.group("new_start"))
                continue

            if current_file is None or new_line_no is None:
                continue

            if raw_line.startswith(" "):
                file_states[current_file][new_line_no] = "context"
                new_line_no += 1
            elif raw_line.startswith("+") and not raw_line.startswith("+++"):
                file_states[current_file][new_line_no] = "added"
                new_line_no += 1
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                # Deletions do not advance the new-file line number.
                continue

        return {path: DiffLineMap(states) for path, states in file_states.items()}

    def _get_language(self, file_path: Path) -> str:
        """
        Infer language from file extension.

        Args:
            file_path: Path to file

        Returns:
            Language name or 'unknown'
        """
        ext = file_path.suffix.lower()

        mapping = {
            ".py": "python",
            ".java": "java",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }

        return mapping.get(ext, "unknown")
