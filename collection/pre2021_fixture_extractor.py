"""Phase 2: extract fixtures from pinned pre-2021 commits (snapshot-based).

Checks out each eligible repository at its `pinned_commit`, walks its test
files, and calls `detector.extract_fixtures()` per file — no diff/purity
gating, since this is a single fixed snapshot rather than a commit-by-commit
scan (contrast with `agent_fixture_extractor.py`'s Phase 3 workflow).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from collection.logging_utils import get_logger

from .commit_checkout import _checkout_commit, _repo_worktree_lock, _resolve_repo_path
from .config import CLONES_DIR, DB_PATH
from .db import db_session
from .detector import extract_fixtures, fixture_result_to_dict
from .test_commit_utils import is_test_file_path

logger = get_logger(__name__)


@dataclass
class Pre2021ExtractionStats:
    """Statistics from pre-2021 fixture extraction."""

    total_repositories: int = 0
    repositories_with_fixtures: int = 0
    total_fixtures_extracted: int = 0
    fixtures_by_type: Dict[str, int] = field(default_factory=dict)
    repositories_processed: List[str] = field(default_factory=list)
    repositories_failed: List[Tuple[str, str]] = field(default_factory=list)


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
                                fixture_result_to_dict(
                                    fixture,
                                    language=language,
                                    file_path=str(test_file.relative_to(repo_path)),
                                    repo_name=repo_name,
                                )
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

        for match in repo_path.rglob("*"):
            if not match.is_file() or not self._should_process_file(match, language):
                continue

            rel_path = match.relative_to(repo_path).as_posix()
            if is_test_file_path(rel_path, language.lower()):
                test_files.append(match)

        return test_files

    def _should_process_file(self, file_path: Path, language: str) -> bool:
        """
        Check if a file should be processed.

        A pre-filter ahead of the rglob walk in _find_test_files -- avoids
        queuing files extract_fixtures() would reject anyway. Uses
        detector.py's own ALLOWED_EXTS rather than a separate hand-copied
        extension set: this file used to carry its own, and it had already
        drifted from the authoritative one in detector.py (missing .pyw/.pyi
        for python; an extra .cts entry for typescript that would pass this
        filter only to be silently rejected by extract_fixtures()'s own
        allowlist check one step later, since that check -- not this one --
        is what actually gates which files get analyzed).

        Args:
            file_path: Path to file
            language: Programming language

        Returns:
            True if file should be processed
        """
        from .config import MAX_FILE_SIZE_BYTES, NON_CODE_EXTENSIONS
        from .detector import ALLOWED_EXTS

        # Check extension
        allowed_extensions = ALLOWED_EXTS.get(language.lower(), set())
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
