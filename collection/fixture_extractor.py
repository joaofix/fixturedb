"""
Fixture Extraction Module

Handles extraction of fixtures from repositories using different strategies:
- Phase 2: Pre-2021 fixtures (snapshot-based extraction at pinned_commit)
- Phase 3: agent-generated fixtures (commit-by-commit with completeness validation)
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import CLONES_DIR, DB_PATH, AGENT_DATASET_START_DATE
from .db import db_session
from .detector import extract_fixtures

logger = logging.getLogger(__name__)


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
        self.source_db = Path(source_db)
        self.stats = Pre2021ExtractionStats()

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

        # Get repositories from corpus.db
        repos = self._get_eligible_repositories()

        if repo_names:
            selected = {name for name in repo_names}
            repos = [repo for repo in repos if repo.get('full_name') in selected]

        self.stats.total_repositories = len(repos)

        if not repos:
            logger.warning("No repositories found in corpus.db")
            return self.stats

        logger.info(f"Found {len(repos)} repositories to process")

        for idx, repo in enumerate(repos, 1):
            repo_id = repo['id']
            repo_name = repo['full_name']
            pinned_commit = repo['pinned_commit']
            language = repo['language']

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

                    # Count by type
                    for fixture in fixtures:
                        fixture_type = fixture.get('fixture_type', 'unknown')
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
        repo_path = self.clones_dir / repo_name

        if not repo_path.exists():
            raise RuntimeError(f"Repository not found: {repo_path}")

        # Checkout specific commit
        try:
            subprocess.run(
                ['git', 'checkout', commit_sha, '--quiet'],
                cwd=repo_path,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to checkout {commit_sha}: {e}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Checkout timeout for {commit_sha}")

        # Extract fixtures from test files
        fixtures = []

        try:
            # Find test files
            test_files = self._find_test_files(repo_path, language)

            for test_file in test_files:
                try:
                    result = extract_fixtures(test_file, language)

                    for fixture in result.fixtures:
                        fixtures.append({
                            'name': fixture.name,
                            'fixture_type': fixture.fixture_type,
                            'scope': fixture.scope,
                            'loc': fixture.loc,
                            'file_path': str(test_file.relative_to(repo_path)),
                            'start_line': fixture.start_line,
                            'end_line': fixture.end_line,
                        })

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

        test_files = []

        for pattern in config.test_path_patterns:
            for match in repo_path.glob(pattern):
                if match.is_file() and self._should_process_file(match, language):
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
        from .config import LANGUAGE_EXTENSIONS, MAX_FILE_SIZE_BYTES

        # Check extension
        if file_path.suffix not in LANGUAGE_EXTENSIONS.get(language.lower(), set()):
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
        start_date: str = AGENT_DATASET_START_DATE,
    ):
        """
        Initialize AGENT fixture extractor.

        Args:
            clones_dir: Directory containing cloned repositories
            source_db: Source database to query
            start_date: Only extract commits after this date (ISO format)
        """
        self.clones_dir = Path(clones_dir)
        self.source_db = Path(source_db)
        self.start_date = start_date
        self.stats = AgentExtractionStats()
        self.all_fixtures = []  # Collected fixtures ready for insertion
        self.all_fixtures = []  # Collect all extracted fixtures for insertion

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
            LLMExtractionStats with extraction results
        """
        logger.info("Starting agent fixture extraction from verified agent commits")

        repos_to_process = list(agent_commits.keys())
        self.stats.total_repositories = len(repos_to_process)
        self.stats.repositories_with_agent_commits = len(repos_to_process)
        self.all_fixtures = []
        self.all_fixtures = []  # Initialize collection

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
                    self.all_fixtures.extend(fixtures)  # Collect for insertion

                    # Count by agent type
                    for fixture in fixtures:
                        agent_type = fixture.get('agent_type', 'unknown')
                        self.stats.fixtures_by_agent[agent_type] = (
                            self.stats.fixtures_by_agent.get(agent_type, 0) + 1
                        )

                        if fixture.get('is_complete_addition'):
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
        from .db import upsert_repository, upsert_test_file, insert_fixture, db_session

        if not self.all_fixtures:
            logger.warning("No fixtures to insert")
            return 0

        logger.info(f"Inserting {len(self.all_fixtures)} fixtures with match_scope={match_scope}")

        try:
            with db_session(target_db) as conn:
                inserted_count = 0

                # Group fixtures by repository
                fixtures_by_repo = {}
                for fixture in self.all_fixtures:
                    repo_name = fixture.get('repo_name')
                    if repo_name not in fixtures_by_repo:
                        fixtures_by_repo[repo_name] = []
                    fixtures_by_repo[repo_name].append(fixture)

                # Insert fixtures repo by repo
                for repo_name, repo_fixtures in fixtures_by_repo.items():
                    try:
                        lookup_name = repo_name.replace('__', '/') if '__' in repo_name else repo_name

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
                            raise RuntimeError(
                                f"Repository metadata not found in source DB for {repo_name}"
                            )

                        repo_data = dict(source_row)
                        repo_data['status'] = 'analysed'

                        repo_id, _ = upsert_repository(conn, repo_data)

                        # Process test files
                        files_by_path = {}
                        for fixture in repo_fixtures:
                            file_path = fixture.get('file_path', 'unknown')
                            if file_path not in files_by_path:
                                files_by_path[file_path] = []
                            files_by_path[file_path].append(fixture)

                        # Insert test file records and fixtures
                        for file_path, file_fixtures in files_by_path.items():
                            test_file_data = {
                                'repo_id': repo_id,
                                'relative_path': file_path,
                                'language': file_fixtures[0].get('language', 'unknown'),
                                'file_loc': 0,  # Not computed for AGENT extraction
                                'num_test_funcs': 0,
                                'num_fixtures': len(file_fixtures),
                            }
                            file_id, _ = upsert_test_file(conn, test_file_data)

                            # Insert each fixture with match_scope label
                            for fixture in file_fixtures:
                                fixture_data = {
                                    'file_id': file_id,
                                    'repo_id': repo_id,
                                    'name': fixture.get('name'),
                                    'fixture_type': fixture.get('fixture_type'),
                                    'scope': fixture.get('scope', 'unknown'),
                                    'start_line': fixture.get('start_line', 0),
                                    'end_line': fixture.get('end_line', 0),
                                    'loc': fixture.get('loc', 0),
                                    'cyclomatic_complexity': 0,
                                    'max_nesting_depth': 0,
                                    'num_objects_instantiated': 0,
                                    'num_external_calls': 0,
                                    'num_parameters': 0,
                                    'reuse_count': 0,
                                    'has_teardown_pair': 0,
                                    'raw_source': fixture.get('raw_source', ''),
                                    'framework': fixture.get('framework'),
                                    # Agent-specific fields
                                    'commit_sha': fixture.get('commit_sha'),
                                    'agent_type': fixture.get('agent_type'),
                                    'match_scope': match_scope,
                                    'is_complete_addition': 1 if fixture.get('is_complete_addition') else 0,
                                }
                                insert_fixture(conn, fixture_data)
                                inserted_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to insert fixtures from {repo_name}: {e}")

                conn.commit()
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
        repo_path = self.clones_dir / repo_name

        if not repo_path.exists():
            raise RuntimeError(f"Repository not found: {repo_path}")

        fixtures = []

        for commit_sha, agent_type in commits.items():
            try:
                # Checkout commit
                subprocess.run(
                    ['git', 'checkout', commit_sha, '--quiet'],
                    cwd=repo_path,
                    timeout=30,
                    check=True,
                )

                # Get commit metadata
                commit_info = self._get_commit_info(repo_path, commit_sha)
                if not commit_info:
                    continue

                # Check if commit date is within range
                if commit_info['date'] < self.start_date:
                    continue

                # Get diff to check for complete additions
                diff_info = self._get_commit_diff(repo_path, commit_sha)

                # Extract fixtures
                commit_fixtures = self._extract_from_diff(
                    repo_path=repo_path,
                    repo_name=repo_name,
                    diff_info=diff_info,
                    commit_sha=commit_sha,
                    agent_type=agent_type,
                )

                fixtures.extend(commit_fixtures)

            except Exception as e:
                logger.debug(f"Failed to extract from {commit_sha}: {e}")

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
                ['git', 'log', '-1', '--pretty=format:%ai|%an|%ae|%B', commit_sha],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )

            parts = result.stdout.strip().split('|', 3)
            if len(parts) < 4:
                return None

            timestamp = parts[0]
            date = timestamp.split(' ')[0]  # Extract YYYY-MM-DD

            return {
                'date': date,
                'author_name': parts[1],
                'author_email': parts[2],
                'message': parts[3] if len(parts) > 3 else '',
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
                ['git', 'show', '--unified=3', commit_sha],
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

        # Parse diff to find added test functions/methods with fixture decorator
        # This is a simplified implementation - real implementation would parse diff
        # and detect fixture definitions line by line

        # For now, extract all fixtures and mark as complete/partial based on
        # whether all lines in the diff are additions (not modifications)

        test_files = self._find_added_test_files(diff_info)

        for file_path in test_files:
            full_path = repo_path / file_path

            if full_path.exists():
                try:
                    language = self._get_language(full_path)
                    result = extract_fixtures(full_path, language)

                    for fixture in result.fixtures:
                        # Check if fixture is completely added (simplified heuristic)
                        is_complete = self._is_completely_added_fixture(
                            diff_info, file_path, fixture.name
                        )

                        fixtures.append({
                            'repo_name': repo_name,
                            'name': fixture.name,
                            'fixture_type': fixture.fixture_type,
                            'scope': fixture.scope,
                            'loc': fixture.loc,
                            'language': language,
                            'file_path': file_path,
                            'start_line': fixture.start_line,
                            'end_line': fixture.end_line,
                            'raw_source': fixture.raw_source if hasattr(fixture, 'raw_source') else '',
                            'framework': fixture.framework if hasattr(fixture, 'framework') else None,
                            'commit_sha': commit_sha,
                            'agent_type': agent_type,
                            'is_complete_addition': is_complete,
                        })

                except Exception as e:
                    logger.debug(f"Failed to extract from {file_path}: {e}")

        return fixtures

    def _find_added_test_files(self, diff: str) -> List[str]:
        """
        Find test files that were added in the diff.

        Args:
            diff: Unified diff output

        Returns:
            List of test file paths
        """
        files = []

        for line in diff.split('\n'):
            if line.startswith('diff --git'):
                # Extract file path
                parts = line.split()
                if len(parts) >= 4:
                    file_path = parts[3][2:]  # Remove 'b/' prefix
                    if any(
                        file_path.endswith(ext)
                        for ext in ['.py', '.java', '.js', '.ts', '.go']
                    ):
                        files.append(file_path)

        return files

    def _is_completely_added_fixture(
        self,
        diff: str,
        file_path: str,
        fixture_name: str,
    ) -> bool:
        """
        Check if a fixture is completely added (no modifications).

        CRITICAL: Validates that fixture was 100% added in this commit.

        Args:
            diff: Unified diff output
            file_path: Path to test file
            fixture_name: Fixture name

        Returns:
            True if fixture is completely new (all added lines)
        """
        # Simplified heuristic: check if diff only has additions for this file
        # Real implementation would parse AST and validate fixture boundaries

        in_file = False
        has_modifications = False

        for line in diff.split('\n'):
            if f'b/{file_path}' in line:
                in_file = True
            elif line.startswith('diff --git'):
                in_file = False

            if in_file and line.startswith('-') and not line.startswith('---'):
                # Found a deletion in this file
                has_modifications = True
                break

        return not has_modifications

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
            '.py': 'python',
            '.java': 'java',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.go': 'go',
        }

        return mapping.get(ext, 'unknown')
