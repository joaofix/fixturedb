"""Phase 3: extract agent-generated fixtures with completeness validation.

Walks each verified agent commit, applies the diff-purity gates from
`diff_purity.py` (only completely-added test files/commits are eligible),
calls `detector.extract_fixtures()` per file, and tags each fixture with
whether its exact span was 100% newly added (via AST-node completeness
checking, falling back to line-based diff state) — the core "no partial
credit for modified fixtures" rule of the agent-corpus methodology.

Commit metadata and diffs come from PyDriller's `Git`/`Commit` objects, not
hand-rolled `git log`/`git show` subprocess calls with regex/string-prefix
text parsing. PyDriller's `ModifiedFile.diff_parsed` already gives
structured (line_no, text) tuples for added/deleted lines, `.change_type`
already distinguishes ADD/MODIFY/RENAME/DELETE, and `.new_path`/`.old_path`
are plain strings -- eliminating an entire class of diff-text-parsing bugs
(several found and fixed earlier this session: "---"/"+++" prefix
collisions with real diff content, and space-in-path ambiguity in
"diff --git a/X b/Y" headers) by construction, not by adding more parsing
special-cases.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydriller import Git

from collection.logging_utils import get_logger

from .commit_checkout import _checkout_commit, _repo_worktree_lock, _resolve_repo_path
from .config import AGENT_CORPUS_START_DATE, CLONES_DIR, DB_PATH
from .conventional_commits import classify_commit_type
from .detector import _get_parser, extract_fixtures, fixture_result_to_dict
from .diff_purity import DiffLineMap, commit_is_pure_addition, is_pure_addition
from .language_utils import get_language_static
from .test_commit_utils import is_test_file_path

logger = get_logger(__name__)


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


class AgentFixtureExtractor:
    """Phase 3: Extract agent-generated fixtures with completeness validation."""

    def __init__(
        self,
        clones_dir: Path = CLONES_DIR,
        source_db: Optional[Path] = DB_PATH,
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
        self.all_fixtures: list[dict[str, Any]] = []

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

    def _extract_from_agent_commits(
        self,
        repo_name: str,
        commits: Dict[str, str],
        stats: Optional[Dict[str, int]] = None,
    ) -> List[Dict]:
        """
        Extract fixtures from agent commits in a repository.

        Args:
            repo_name: Repository name
            commits: Dict mapping commit_sha to agent_type
            stats: Optional dict to accumulate commit-level purity counters into
                (commits_skipped_commit_level, commits_proceeded,
                commits_skipped_file_level). Callers use these to distinguish
                commits rejected for mixed test-file diffs from commits whose
                test files were pure additions. Left untouched when None.

        Returns:
            List of fixture dicts with commit_sha, agent_type, is_complete_addition
        """
        repo_path = _resolve_repo_path(self.clones_dir, repo_name)

        if not repo_path.exists():
            raise RuntimeError(f"Repository not found: {repo_path}")

        git_repo = Git(str(repo_path))

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
                    # Checkout commit (needed so extract_fixtures() can read
                    # the actual working-tree files; PyDriller's Commit
                    # object below is independent of working-tree state --
                    # it reads historical metadata/diffs from git's object
                    # database directly).
                    _checkout_commit(repo_path, commit_sha)

                    try:
                        commit = git_repo.get_commit(commit_sha)
                    except Exception as e:
                        logger.debug(f"Failed to get commit {commit_sha}: {e}")
                        continue

                    # Check if commit date is within range
                    commit_date = commit.author_date.strftime("%Y-%m-%d")
                    if commit_date < self.start_date:
                        continue

                    # ── Commit‑level purity gate ──
                    if not commit_is_pure_addition(commit):
                        logger.debug(
                            "Skipping entire commit %s in %s: a test file contains "
                            "deletions, is deleted, or is renamed",
                            commit_sha[:8],
                            repo_name,
                        )
                        commits_skipped_commit_level += 1
                        if stats is not None:
                            stats["commits_skipped_commit_level"] = (
                                stats.get("commits_skipped_commit_level", 0) + 1
                            )
                        continue

                    # Extract fixtures
                    commit_fixtures = self._extract_from_commit(
                        repo_path=repo_path,
                        repo_name=repo_name,
                        commit=commit,
                        commit_sha=commit_sha,
                        agent_type=agent_type,
                    )

                    if commit_fixtures:
                        commits_proceeded += 1
                        if stats is not None:
                            stats["commits_proceeded"] = (
                                stats.get("commits_proceeded", 0) + 1
                            )
                    else:
                        # Commit passed commit-level gate but all files were filtered
                        # at file level → count as file-level skip
                        commits_skipped_file_level += 1
                        if stats is not None:
                            stats["commits_skipped_file_level"] = (
                                stats.get("commits_skipped_file_level", 0) + 1
                            )

                    # Classify the commit's Conventional Commits type so
                    # fixture-producing commits (agent or human) can be
                    # compared against literature baselines and against each
                    # other. `agent_type` is "human" for Dataset B commits
                    # routed through this same method (human_corpus.py) —
                    # classification applies the same way regardless.
                    commit_type = classify_commit_type(commit.msg or "")

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
                        fixture["commit_type"] = commit_type
                        fixtures.append(fixture)

            except Exception as e:
                logger.debug(f"Failed to extract from {commit_sha}: {e}")

        # agent_corpus.py's per-repo loop calls this once per commit (a
        # single-commit dict each time), so this fires once per commit, not
        # once per repo -- debug, not info, to avoid flooding at thousands
        # of commits scale.
        logger.debug(
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

    def _extract_from_commit(
        self,
        repo_path: Path,
        repo_name: str,
        commit,
        commit_sha: str,
        agent_type: str,
    ) -> List[Dict]:
        """
        Extract fixtures from a commit.

        CRITICAL: Only include fixtures that are completely added (100% new lines).
        No modifications or refactoring.

        Args:
            repo_path: Path to repository
            repo_name: Repository name (for tracking)
            commit: PyDriller Commit object
            commit_sha: Commit SHA
            agent_type: Agent type (from Phase 1B)

        Returns:
            List of fixtures completely added in this commit
        """
        fixtures = []
        diff_maps = self._build_diff_line_maps(commit)
        test_files = self._find_added_test_files(commit)
        modified_files_by_path = {
            (mf.new_path or mf.old_path): mf for mf in commit.modified_files
        }

        purity_skipped_count = 0

        for file_path in test_files:
            # ── Purity gate: only extract from files whose diff is 100% additions ──
            modified_file = modified_files_by_path.get(file_path)
            if modified_file is None or not is_pure_addition(modified_file):
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
                            fixture_result_to_dict(
                                fixture,
                                language=language,
                                file_path=file_path,
                                repo_name=repo_name,
                                commit_sha=commit_sha,
                                agent_type=agent_type,
                                is_complete_addition=is_complete,
                            )
                        )

                except Exception as e:
                    logger.debug(f"Failed to extract from {file_path}: {e}")

        if purity_skipped_count > 0:
            logger.debug(
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
                fixture_result_to_dict(
                    fixture,
                    language=language,
                    file_path=file_path,
                    repo_name=repo_path.name,
                    commit_sha=cutoff_commit_sha,
                    commit_date=cutoff_commit_date,
                    agent_type="human_pre2022",
                    commit_kind="human",
                    is_complete_addition=1,
                )
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

    # Comment node type names across this project's supported grammars.
    # Python/JavaScript/TypeScript all use "comment"; Java is the odd one out
    # with separate "line_comment"/"block_comment" types -- a single
    # `== "comment"` check silently never excluded Java comments, causing a
    # comment line inside an otherwise-100%-added Java fixture to be
    # evaluated (and potentially rejected) differently than the identical
    # Python/JS/TS case.
    _COMMENT_NODE_TYPES = frozenset({"comment", "line_comment", "block_comment"})

    def _collect_named_node_lines(self, node) -> set[int]:
        """Collect line numbers covered by named leaf AST nodes under a target node."""
        lines: set[int] = set()

        def visit(current):
            named_children = list(getattr(current, "named_children", []))

            if (
                getattr(current, "type", None)
                in AgentFixtureExtractor._COMMENT_NODE_TYPES
            ):
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

    def _find_added_test_files(self, commit) -> List[str]:
        """
        Find test files present in this commit's new state.

        Any change type is included here -- the pure-addition purity gate is
        applied separately, per file, in _extract_from_commit(). A deleted
        file has no new_path (PyDriller sets it to None), so it's naturally
        excluded without any special-casing.

        Args:
            commit: PyDriller Commit object

        Returns:
            List of test file paths
        """
        files = []
        for modified_file in commit.modified_files:
            file_path = modified_file.new_path
            if file_path is None:
                continue
            language = self._get_language(Path(file_path))
            if language != "unknown" and is_test_file_path(file_path, language):
                files.append(file_path)
        return files

    def _build_diff_line_maps(self, commit) -> Dict[str, DiffLineMap]:
        """
        Build a per-file map of new-file line numbers to diff states.

        Sourced directly from PyDriller's own parsed diff
        (ModifiedFile.diff_parsed's "added" list of (line_no, text) tuples)
        -- no hand-rolled hunk-header or line-prefix parsing needed.
        DiffLineMap.fixture_is_completely_added() only ever checks for the
        "added" state, so a line being context, deleted, or simply absent
        from this map are all equivalent (anything not explicitly "added"
        fails the check) -- there's no need to track "context" separately.
        """
        diff_maps: Dict[str, DiffLineMap] = {}
        for modified_file in commit.modified_files:
            path = modified_file.new_path or modified_file.old_path
            if path is None:
                continue
            added_lines = {
                line_no: "added"
                for line_no, _ in modified_file.diff_parsed.get("added", [])
            }
            diff_maps[path] = DiffLineMap(added_lines)
        return diff_maps

    def _get_language(self, file_path: Path) -> str:
        """Infer language from file extension (delegates to the shared mapping)."""
        return get_language_static(file_path)
