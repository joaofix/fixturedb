"""Tier 1 corpus-scale agent-detection orchestration.

The actual pipeline entry point for agent detection:
`Tier1RepositoryScanner` scans the existing corpus for `Co-authored-by`
trailer commits and computes adoption-intensity stats. See
`docs/architecture/agent-detection.md` for the methodology.

Used to also host a Tier 2 (`Tier2RepoMatcher`) supplementary-discovery
mechanism -- removed since Tier 1 alone consistently met the statistical-
power thresholds in every real collection run, so the extra GitHub-search-
based fallback was never actually triggered. The module keeps its
`tiered_` name since several other modules (`agent_corpus.py`,
`human_corpus.py`, `paired_collection.py`, `test_commit_filter.py`,
`human_test_commit_filter.py`, `backfill_total_commits.py`, `dataset_c.py`)
import `Tier1RepositoryScanner` from it by that name; renaming buys nothing
functionally.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydriller import Repository

from collection.logging_utils import get_logger

from .agent_patterns import AGENT_SIGNATURES, is_bot_author
from .config import AGENT_CORPUS_START_DATE
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
        and its full rationale live there). The only thing specific to
        this call site is the external contract: callers here need to
        distinguish "excluded as bot" (returns the `_BOT` sentinel, so
        `scan_repo_for_agent_commits` can skip it without counting it as
        either agent or human activity) from "no agent detected" (returns
        None) -- `detect_agent_in_commit` itself collapses both to None,
        so that check is done here first.

        Returns:
            Agent type (any key in AGENT_SIGNATURES, e.g. claude/cursor/copilot/
            aider/...), None for human-authored, or `_BOT` for bot-authored commits.
        """
        if is_bot_author(f"{author_name} {author_email}"):
            return _BOT

        return detect_agent_in_commit(
            author_name, author_email, body, self.agent_signatures
        )


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

