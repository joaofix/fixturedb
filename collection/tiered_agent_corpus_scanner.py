"""Tier1/Tier2 corpus-scale agent-detection orchestration.

The actual pipeline entry point for agent detection: Tier 1
(`Tier1RepositoryScanner`) scans the existing corpus for `Co-authored-by`
trailer commits and computes adoption-intensity stats; Tier 2
(`Tier2RepoMatcher`) discovers new candidate repos via GitHub search and
verifies them using `agent_signal_primitives.py`'s low-level scan/verify
primitives. See `docs/architecture/agent-detection.md` for the methodology.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from pydriller import Repository

from collection.logging_utils import get_logger

from .agent_patterns import AGENT_SIGNATURES, is_bot_author
from .agent_signal_primitives import (
    AgentCommitVerifier,
    AgentFileScanner,
    GitHubAgentFileChecker,
)
from .config import (
    AGENT_CORPUS_START_DATE,
    CLONES_DIR,
    TIER1_MINIMUM_AGENT_COMMITS,
    TIER1_MINIMUM_REPOS_WITH_AGENT,
    TIER2_MATCHING_MAX_STARS,
    TIER2_MATCHING_MIN_STARS,
    TIER2_MIN_TEST_FILES,
)
from .db import db_session
from .persistent_clone import clone_repo
from .test_commit_utils import is_test_file_path as _shared_is_test_file_path
from .utils import detect_agent_in_commit

logger = get_logger(__name__)

_BOT = "bot"


@dataclass
class AgentCommitInfo:
    """Information about a single agent commit."""

    commit_sha: str
    agent_type: str
    commit_date: str
    author_name: str
    author_email: str


@dataclass
class CommitRoleInfo:
    """Information about a commit classified for paired analysis."""

    commit_sha: str
    commit_role: str  # agent or human
    agent_type: Optional[str]
    commit_date: str
    author_name: str
    author_email: str
    is_test_commit: bool = False
    test_files: List[str] = field(default_factory=list)


def _parse_since_date(start_date: str) -> datetime:
    return datetime.fromisoformat(start_date)


def _is_test_file_path(relative_path: str, language: Optional[str] = None) -> bool:
    """Thin wrapper around the canonical `test_commit_utils.is_test_file_path`.

    This used to be an independent, duplicated implementation that drifted
    from its sibling: a false-positive fix applied to `test_commit_utils.py`
    (bare suffixes like "IT.java"/"test.js" matching unrelated files, e.g.
    "Deposit.java"/"latest.js") was never applied here, so the same bug
    stayed live at this call site. Delegating avoids future drift.
    """
    if language is None:
        return False
    return _shared_is_test_file_path(relative_path, language)


def _collect_test_files_from_pydriller(commit, language: str) -> list[str]:
    """Extract test files from a PyDriller commit's modified files."""
    test_files: list[str] = []
    seen: set[str] = set()
    for modified_file in commit.modified_files:
        path = modified_file.new_path or modified_file.old_path or ""
        if not path:
            continue
        if path not in seen and _is_test_file_path(path, language):
            seen.add(path)
            test_files.append(path)
    return test_files


@dataclass
class Tier1Assessment:
    """Results of Tier 1 (corpus repos) assessment."""

    repos_with_agent: int = 0
    total_agent_commits: int = 0
    agent_commits_in_test_files: int = 0
    repos_by_agent: Dict[str, int] = field(default_factory=dict)
    sufficient: bool = False  # True if Tier 1 meets minimum thresholds
    tier2_recommended: bool = False  # True if Tier 2 should be triggered
    summary: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class Tier1RepositoryScanner:
    """Scan corpus repositories for agent commits (Tier 1)."""

    def __init__(self, corpus_db_path: Path):
        """
        Initialize Tier 1 scanner.

        Args:
            corpus_db_path: Path to corpus.db containing repository list
        """
        self.corpus_db_path = Path(corpus_db_path)
        self.agent_signatures = AGENT_SIGNATURES

    def scan_repo_for_agent_commits(
        self, repo_path: Path, start_date: str = AGENT_CORPUS_START_DATE
    ) -> tuple[List[AgentCommitInfo], int]:
        """
        Scan a single repository for agent commits (Co-authored-by trailers).

        Args:
            repo_path: Path to repository on disk
            start_date: Only include commits after this date (ISO format)

        Returns:
            (commits, total_examined): commits is the list of AgentCommitInfo
            for agent commits found; total_examined is every commit this scan
            looked at in the date window (agent, human, and bot alike) -- the
            total this class already computes internally via the same
            traversal but historically discarded once it filtered down to
            agent-only rows. Callers that only need the agent commits can
            ignore the second element.
        """
        if not repo_path.is_dir():
            return [], 0

        commits = []
        total_examined = 0

        try:
            since_date = _parse_since_date(start_date)
            for commit in Repository(
                str(repo_path),
                since=since_date,
                only_no_merge=True,
            ).traverse_commits():
                total_examined += 1
                commit_sha = commit.hash
                author_name = commit.author.name
                author_email = commit.author.email
                commit_date = commit.author_date.isoformat()
                body = commit.msg

                agent_type = self._detect_agent_in_commit(
                    author_name, author_email, body
                )

                if agent_type == "bot":
                    continue

                if agent_type:
                    commits.append(
                        AgentCommitInfo(
                            commit_sha=commit_sha,
                            agent_type=agent_type,
                            commit_date=commit_date,
                            author_name=author_name,
                            author_email=author_email,
                        )
                    )

        except Exception as e:
            logger.error(f"Error scanning {repo_path.name}: {e}")

        return commits, total_examined

    def scan_repo_commit_roles(
        self,
        repo_path: Path,
        start_date: str = AGENT_CORPUS_START_DATE,
        language: Optional[str] = None,
        detect_test_files: bool = False,
    ) -> List[CommitRoleInfo]:
        """Scan a repository and classify each commit as agent or human."""
        if not repo_path.is_dir():
            return []

        commit_roles: List[CommitRoleInfo] = []

        try:
            since_date = _parse_since_date(start_date)
            for commit in Repository(
                str(repo_path),
                since=since_date,
                only_no_merge=True,
            ).traverse_commits():
                commit_sha = commit.hash
                author_name = commit.author.name
                author_email = commit.author.email
                commit_date = commit.author_date.isoformat()
                body = commit.msg

                agent_type = self._detect_agent_in_commit(
                    author_name, author_email, body
                )

                if agent_type == "bot":
                    continue

                test_files: list[str] = []
                if detect_test_files and language:
                    test_files = _collect_test_files_from_pydriller(commit, language)

                commit_roles.append(
                    CommitRoleInfo(
                        commit_sha=commit_sha,
                        commit_role="agent" if agent_type else "human",
                        agent_type=agent_type,
                        commit_date=commit_date,
                        author_name=author_name,
                        author_email=author_email,
                        is_test_commit=bool(test_files),
                        test_files=test_files,
                    )
                )
        except Exception as exc:
            logger.error(f"Error scanning {repo_path.name}: {exc}")

        return commit_roles

    def _detect_agent_in_commit(
        self, author_name: str, author_email: str, body: str
    ) -> str | None:
        """Detect if commit author indicates agent authorship.

        Thin wrapper around `utils.detect_agent_in_commit` (the priority
        order -- bot, then trailer, then author name, then author email --
        and its full rationale live there, shared with Tier 2's
        `AgentCommitVerifier`). The only thing specific to this call site is
        the external contract: callers here need to distinguish "excluded
        as bot" (returns the `_BOT` sentinel, so `scan_repo_for_agent_commits`
        can skip it without counting it as either agent or human activity)
        from "no agent detected" (returns None) -- `detect_agent_in_commit`
        itself collapses both to None, so that check is done here first.

        Returns:
            Agent type (any key in AGENT_SIGNATURES, e.g. claude/cursor/copilot/
            aider/...), None for human-authored, or `_BOT` for bot-authored commits.
        """
        if is_bot_author(f"{author_name} {author_email}"):
            return _BOT

        return detect_agent_in_commit(
            author_name, author_email, body, self.agent_signatures
        )

    def assess_tier1(self, corpus_repos: List[Dict]) -> Tier1Assessment:
        """
        Assess Tier 1 yield from corpus repositories.

        Args:
            corpus_repos: List of repo metadata from corpus.db
                         Should include: name, path

        Returns:
            Tier1Assessment with results and recommendations
        """
        assessment = Tier1Assessment()
        repos_scanned = 0
        repos_with_agent = {}  # {repo_name: [AgentCommitInfo]}

        logger.info(
            f"Scanning {len(corpus_repos)} corpus repositories for agent commits..."
        )

        for repo_meta in corpus_repos:
            repos_scanned += 1
            repo_name = repo_meta.get("name", "unknown")
            repo_path = Path(repo_meta.get("path", f"/tmp/not_found/{repo_name}"))

            if not repo_path.exists():
                # Try to find in clones
                repo_path = Path("/tmp") / "clones" / repo_name
                if not repo_path.exists():
                    logger.debug(f"Repo not found: {repo_name}")
                    continue

            commits = self.scan_repo_for_agent_commits(repo_path)

            if commits:
                repos_with_agent[repo_name] = commits
                assessment.repos_with_agent += 1
                assessment.total_agent_commits += len(commits)

                # Count by agent type
                for commit in commits:
                    agent = commit.agent_type
                    assessment.repos_by_agent[agent] = (
                        assessment.repos_by_agent.get(agent, 0) + 1
                    )

        # Assess if sufficient
        assessment.sufficient = (
            assessment.repos_with_agent >= TIER1_MINIMUM_REPOS_WITH_AGENT
            and assessment.total_agent_commits >= TIER1_MINIMUM_AGENT_COMMITS
        )

        assessment.tier2_recommended = not assessment.sufficient

        # Generate summary
        assessment.summary = self._generate_summary(assessment)

        return assessment

    def _generate_summary(self, assessment: Tier1Assessment) -> str:
        """Generate human-readable summary of Tier 1 assessment."""
        lines = [
            "Tier 1 Assessment Results:",
            f"  Repos with agent commits: {assessment.repos_with_agent}",
            f"  Total agent commits: {assessment.total_agent_commits}",
            f"  Agent distribution: {assessment.repos_by_agent}",
        ]

        if assessment.sufficient:
            lines.append("  ✓ SUFFICIENT for statistical power (Tier 2 not needed)")
        else:
            lines.append("  ⚠ INSUFFICIENT (Tier 2 matching recommended)")
            lines.append(
                f"    - Need at least {TIER1_MINIMUM_REPOS_WITH_AGENT} repos, found {assessment.repos_with_agent}"
            )
            lines.append(
                f"    - Need at least {TIER1_MINIMUM_AGENT_COMMITS} commits, found {assessment.total_agent_commits}"
            )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent adoption intensity
# ---------------------------------------------------------------------------

# Adoption intensity levels based on ratio of agent commits to total commits
# since AGENT_CORPUS_START_DATE (2025-01-01).
_ADOPTION_THRESHOLD_EXPERIMENTAL = 0.01   # <1%
_ADOPTION_THRESHOLD_LIMITED = 0.05        # 1–5%
_ADOPTION_THRESHOLD_CONSISTENT = 0.20     # 5–20%
# >20% is "pervasive"


def count_total_commits_since(repo_path: Path, start_date: str) -> int:
    """Count total non-merge commits in a repo since *start_date*.

    Uses ``git rev-list --count`` (via GitPython) for performance (avoids
    full PyDriller traversal when only the count is needed) -- a local,
    read-only operation, so no subprocess-level timeout guard is needed
    (unlike clone/fetch, which stay subprocess calls elsewhere in this
    codebase for exactly that reason).

    Args:
        repo_path: Path to a git repository on disk.
        start_date: ISO-format date string (e.g. "2025-01-01").

    Returns:
        Number of non-merge commits since *start_date*, or 0 on failure.
    """
    import git as gitpython

    try:
        repo = gitpython.Repo(repo_path)
        count = repo.git.rev_list(
            "--count",
            "--no-merges",
            f"--since={start_date}",
            "HEAD",
            kill_after_timeout=30,
        )
        return int(count or 0)
    except (gitpython.GitError, ValueError, OSError):
        return 0


def compute_adoption_intensity(
    repo_path: Path,
    start_date: str,
    agent_commit_count: int,
    total_commit_count: int | None = None,
) -> str | None:
    """Compute the agent adoption intensity category for a repository.

    Categories (based on ratio of agent commits to total commits since
    *start_date*):

    ==============  ==============================
    Category         Agent commit ratio
    ==============  ==============================
    ``no_commits``   0 total commits or 0 agent commits
    ``experimental`` ratio < 1%
    ``limited``      1% ≤ ratio < 5%
    ``consistent``   5% ≤ ratio ≤ 20%
    ``pervasive``    ratio > 20%
    ==============  ==============================

    Args:
        repo_path: Path to a git repository on disk.
        start_date: ISO-format date string.
        agent_commit_count: Number of agent commits (pre-computed).
        total_commit_count: Total commits since *start_date*. If ``None``,
            computed via ``count_total_commits_since``.

    Returns:
        One of ``"no_commits"``, ``"experimental"``, ``"limited"``,
        ``"consistent"``, ``"pervasive"``, or ``None`` if the count
        cannot be determined.
    """
    if total_commit_count is None:
        total_commit_count = count_total_commits_since(repo_path, start_date)

    if total_commit_count == 0:
        return "no_commits"

    if agent_commit_count == 0:
        return "no_commits"

    ratio = agent_commit_count / total_commit_count

    if ratio < _ADOPTION_THRESHOLD_EXPERIMENTAL:
        return "experimental"
    if ratio < _ADOPTION_THRESHOLD_LIMITED:
        return "limited"
    if ratio <= _ADOPTION_THRESHOLD_CONSISTENT:
        return "consistent"
    return "pervasive"


class Tier2RepoMatcher:
    """Discover supplementary repositories via agent activity signals (Tier 2)."""

    def __init__(
        self,
        corpus_db_path: Path,
        clones_dir: Path = CLONES_DIR,
        github_token: Optional[str] = None,
    ):
        """
        Initialize Tier 2 matcher.

        Args:
            corpus_db_path: Path to corpus.db
            clones_dir: Directory for cloned repositories
            github_token: Optional GitHub API token for faster API checks
        """
        self.corpus_db_path = Path(corpus_db_path)
        self.clones_dir = Path(clones_dir)
        self.github_api_checker = GitHubAgentFileChecker(github_token=github_token)

    def collect_matched_agent_commits(
        self,
        target_repo_count: int,
        exclude_repo_names: Optional[Set[str]] = None,
        language: Optional[str] = None,
        show_progress: bool = True,
        candidate_limit: int = 200,
    ) -> Dict[str, Dict[str, str]]:
        """
        Discover cross-repo candidates and verify their agent commits.

        Uses survival rate tracking to automatically expand discovery if the initial
        batch yields few verified repos (similar to old-collection behavior).

        Returns a mapping compatible with AgentFixtureExtractor.extract_all:
        {repo_name: {commit_sha: agent_type}}.
        """
        if target_repo_count <= 0:
            return {}

        verified: Dict[str, Dict[str, str]] = {}
        attempted_limit = candidate_limit
        max_expansion_attempts = 3
        expansion_factor = 2.0

        for expansion_attempt in range(max_expansion_attempts):
            candidates = self._discover_candidates(
                exclude_repo_names=exclude_repo_names or set(),
                language=language,
                candidate_limit=attempted_limit,
            )
            if not candidates:
                logger.info("No Tier 2 candidates matched the discovery filters")
                break

            logger.info(
                f"Tier 2 attempt {expansion_attempt + 1}: Verifying {len(candidates)} candidates "
                f"(target: {target_repo_count}, limit: {attempted_limit})"
            )

            scanner = AgentFileScanner(self.clones_dir)
            verifier = AgentCommitVerifier(clones_dir=self.clones_dir)
            verified_this_batch = self._verify_candidates(
                candidates=candidates,
                scanner=scanner,
                verifier=verifier,
                show_progress=show_progress,
                target_count=target_repo_count - len(verified),
            )

            verified.update(verified_this_batch)

            # Check if we've met the target
            if len(verified) >= target_repo_count:
                logger.info(
                    f"Tier 2 collection complete: {len(verified)} repositories verified "
                    f"(target: {target_repo_count})"
                )
                break

            # Calculate survival rate for this batch
            survival_rate = (
                len(verified_this_batch) / len(candidates) if candidates else 0.0
            )

            if (
                expansion_attempt < max_expansion_attempts - 1
                and len(verified_this_batch) == 0
            ):
                # Survival rate is 0%, expand search and retry
                logger.warning(
                    f"Tier 2: Batch survival rate 0% ({len(verified_this_batch)}/{len(candidates)} verified). "
                    f"Expanding candidate search by {expansion_factor}x and retrying..."
                )
                attempted_limit = int(attempted_limit * expansion_factor)
            elif expansion_attempt < max_expansion_attempts - 1:
                # Positive survival rate, estimate how many more to discover
                repos_still_needed = target_repo_count - len(verified)
                if repos_still_needed > 0:
                    estimated_discovery_needed = (
                        int(repos_still_needed / survival_rate)
                        if survival_rate > 0
                        else attempted_limit * 2
                    )
                    new_limit = max(attempted_limit, estimated_discovery_needed)
                    logger.info(
                        f"Tier 2: Batch survival rate {survival_rate:.1%} "
                        f"({len(verified_this_batch)}/{len(candidates)} verified). "
                        f"Need {repos_still_needed} more repos; estimated discovery: {estimated_discovery_needed}. "
                        f"Expanding to {new_limit} candidates..."
                    )
                    attempted_limit = new_limit

        logger.info(f"Tier 2 verification complete: {len(verified)} repositories")
        return verified

    def _verify_candidates(
        self,
        candidates: List[Dict],
        scanner: "AgentFileScanner",
        verifier: "AgentCommitVerifier",
        show_progress: bool,
        target_count: int,
    ) -> Dict[str, Dict[str, str]]:
        """
        Verify candidates in this batch and return verified repos.
        Stops early if target is reached.

        Uses GitHub API pre-filtering to avoid unnecessary clones:
        - Quick API check for agent config files in root
        - Only clone repos that have agent signals
        """
        verified: Dict[str, Dict[str, str]] = {}
        api_filtered = 0

        for idx, candidate in enumerate(candidates, 1):
            repo_name = candidate["full_name"]
            clone_name = repo_name.replace("/", "__")

            # Pre-filter: Check for agent config files via GitHub API (fast, no clone needed)
            has_agent_files, found_files = (
                self.github_api_checker.has_agent_config_files(repo_name)
            )

            if not has_agent_files:
                logger.debug(
                    f"[tier2 api-filter] Skip {repo_name}: no agent config files detected via GitHub API"
                )
                api_filtered += 1
                continue

            if show_progress and idx % 10 == 0:
                logger.debug(
                    f"[tier2 api-check {idx}/{len(candidates)}] {repo_name}: agent files detected {found_files}"
                )

            # Clone only if GitHub API indicates agent files exist
            repo_id, status, commit, skip_reason = clone_repo(
                candidate["id"],
                repo_name,
                candidate["clone_url"],
                candidate["language"],
            )

            if status != "cloned":
                logger.debug(
                    f"[tier2] Skip {repo_name}: clone status={status}, reason={skip_reason}"
                )
                continue

            try:
                agent_files = scanner.scan_repository(clone_name)
            except Exception as exc:
                logger.debug(
                    f"[tier2] Failed to scan agent files in {repo_name}: {exc}"
                )
                continue

            if agent_files.total_agent_files <= 0:
                logger.debug(f"[tier2] Skip {repo_name}: no agent config files found")
                continue

            try:
                results = verifier.verify_all(
                    [clone_name],
                    start_date=AGENT_CORPUS_START_DATE,
                    show_progress=False,
                )
            except Exception as exc:
                logger.debug(f"[tier2] Failed to verify commits in {repo_name}: {exc}")
                continue

            result = results.get(clone_name)
            if not result or result.total_agent_commits <= 0:
                continue

            verified[clone_name] = result.agent_commits

            if show_progress:
                logger.info(
                    f"[tier2 {len(verified)}/{target_count}] {repo_name}: "
                    f"found {result.total_agent_commits} agent commits"
                )

            if len(verified) >= target_count:
                break

        if api_filtered > 0:
            logger.info(
                f"[tier2 api-filtering] Skipped {api_filtered} repos without agent config files "
                f"(via GitHub API pre-check; avoided {api_filtered} unnecessary clones)"
            )

        return verified

    def _discover_candidates(
        self,
        exclude_repo_names: Set[str],
        language: Optional[str] = None,
        candidate_limit: int = 200,
    ) -> List[Dict]:
        """
        Query corpus.db for repositories that can act as Tier 2 matches.

        Uses retry logic with progressively relaxed criteria if initial search
        returns no candidates.
        """
        # Attempt progressively relaxed searches
        search_attempts = self._generate_search_attempts(language)

        for attempt_num, criteria in enumerate(search_attempts, 1):
            candidates = self._query_candidates(
                exclude_repo_names=exclude_repo_names,
                candidate_limit=candidate_limit,
                **criteria,
            )

            if candidates:
                if attempt_num > 1:
                    logger.info(
                        f"Tier 2: Found {len(candidates)} candidates "
                        f"on attempt {attempt_num} with relaxed criteria: {criteria}"
                    )
                return candidates

            logger.debug(
                f"Tier 2: No candidates found with criteria {criteria}, retrying..."
            )

        logger.warning("Tier 2: All discovery attempts exhausted, no candidates found")
        return []

    def _generate_search_attempts(self, language: Optional[str]) -> List[Dict]:
        """
        Generate a sequence of search criteria, progressively relaxed.

        Each attempt loosens constraints to improve chances of finding candidates
        if earlier attempts yielded nothing.
        """
        attempts = []

        # Attempt 1: Strict criteria (original)
        attempts.append(
            {
                "language": language,
                "min_test_files": TIER2_MIN_TEST_FILES,
                "min_stars": TIER2_MATCHING_MIN_STARS,
                "max_stars": TIER2_MATCHING_MAX_STARS,
                "include_discovered": False,
            }
        )

        # Attempt 2: Expand star range (±50%)
        attempts.append(
            {
                "language": language,
                "min_test_files": TIER2_MIN_TEST_FILES,
                "min_stars": max(0, int(TIER2_MATCHING_MIN_STARS * 0.5)),
                "max_stars": int(TIER2_MATCHING_MAX_STARS * 1.5),
                "include_discovered": False,
            }
        )

        # Attempt 3: Reduce test files requirement
        attempts.append(
            {
                "language": language,
                "min_test_files": max(1, int(TIER2_MIN_TEST_FILES * 0.5)),
                "min_stars": max(0, int(TIER2_MATCHING_MIN_STARS * 0.5)),
                "max_stars": int(TIER2_MATCHING_MAX_STARS * 1.5),
                "include_discovered": False,
            }
        )

        # Attempt 4: Remove language filter (if language was specified)
        if language:
            attempts.append(
                {
                    "language": None,
                    "min_test_files": max(1, int(TIER2_MIN_TEST_FILES * 0.5)),
                    "min_stars": max(0, int(TIER2_MATCHING_MIN_STARS * 0.5)),
                    "max_stars": int(TIER2_MATCHING_MAX_STARS * 1.5),
                    "include_discovered": False,
                }
            )

        # Attempt 5: Include 'discovered' repos (not just 'analysed'/'cloned')
        attempts.append(
            {
                "language": None,
                "min_test_files": max(1, int(TIER2_MIN_TEST_FILES * 0.25)),
                "min_stars": max(0, int(TIER2_MATCHING_MIN_STARS * 0.25)),
                "max_stars": int(TIER2_MATCHING_MAX_STARS * 2.0),
                "include_discovered": True,
            }
        )

        return attempts

    def _query_candidates(
        self,
        exclude_repo_names: Set[str],
        candidate_limit: int,
        language: Optional[str] = None,
        min_test_files: int = TIER2_MIN_TEST_FILES,
        min_stars: int = TIER2_MATCHING_MIN_STARS,
        max_stars: int = TIER2_MATCHING_MAX_STARS,
        include_discovered: bool = False,
    ) -> List[Dict]:
        """Execute a single candidate discovery query with specified criteria."""
        with db_session(self.corpus_db_path) as conn:
            params: list = [min_test_files, min_stars, max_stars]
            where = [
                "pinned_commit IS NOT NULL",
                "num_test_files >= ?",
                "stars BETWEEN ? AND ?",
            ]

            # Status filter
            if include_discovered:
                where.append("status IN ('discovered', 'analysed', 'cloned')")
            else:
                where.append("status IN ('analysed', 'cloned')")

            # Language filter
            if language:
                where.append("language = ?")
                params.append(language)

            # Exclude existing repos
            if exclude_repo_names:
                placeholders = ",".join(["?"] * len(exclude_repo_names))
                where.append(f"full_name NOT IN ({placeholders})")
                params.extend(sorted(exclude_repo_names))

            query = f"""
                SELECT id, full_name, language, stars, forks, description, topics,
                       created_at, pushed_at, clone_url, pinned_commit, domain,
                       num_test_files, num_fixtures
                FROM repositories
                WHERE {" AND ".join(where)}
                ORDER BY stars DESC, num_test_files DESC, num_fixtures DESC, full_name ASC
                LIMIT ?
            """
            params.append(candidate_limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
