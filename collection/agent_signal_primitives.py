"""
Low-level, single-repo agent-detection primitives.

Two independent building blocks used by `tiered_agent_corpus_scanner.py`'s
Tier 2 discovery path (and directly by `phase_1b_verify_agent_commits.py`):
scanning a repo's file tree for AI agent configuration files, and verifying/
classifying agent-authored commits via `Co-authored-by`/author-metadata
trailer parsing. This module does not orchestrate corpus-scale scanning
itself — see `tiered_agent_corpus_scanner.py` for that.

Supported agents: Claude, Cursor, Copilot, Aider, OpenHands, Devin, Jules, Cline, Junie, Gemini
"""

import fnmatch
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import platformdirs
import requests
from pydriller import Repository

from collection.logging_utils import get_logger

from .agent_patterns import (
    _EXCLUDED_DIR_NAMES,
    AGENT_SIGNATURES,
    LIGHTWEIGHT_AGENT_CONFIG_PATTERNS,
    is_bot_author,
    match_agent_keyword,
    path_matches_pattern,
)
from .config import AGENT_CORPUS_START_DATE
from .utils import AGENT_TRAILER_RE

logger = get_logger(__name__)

DEFAULT_CLONES_DIR = Path(platformdirs.user_data_dir("icsme-nier", "clones"))


@dataclass
class AgentFileDetectionResult:
    """Result of scanning a single repository for agent files.

    total_agent_files is a property, not a stored field computed once at
    construction time: scan_repository() builds this object with an empty
    agents_found and populates it afterward via direct dict mutation
    (result.agents_found[agent_name] = files_found), so a value computed in
    __post_init__ would freeze at 0 and never reflect what was actually
    found -- which is exactly what happened before this was a property (the
    Tier 2 gate `if agent_files.total_agent_files <= 0: continue` in
    tiered_agent_corpus_scanner.py rejected every repository unconditionally,
    regardless of agent, since total_agent_files could never be anything but
    its construction-time default of 0).
    """

    repo_name: str
    agents_found: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def total_agent_files(self) -> int:
        return sum(len(files) for files in self.agents_found.values())


class GitHubAgentFileChecker:
    """
    Check for agent configuration files in GitHub repositories via the Contents API.

    This provides fast, pre-clone detection of agent activity signals without
    requiring a full repository clone. Dramatically reduces unnecessary clones.
    """

    # Agent config patterns to check for (lightweight check)
    AGENT_CONFIG_FILES = LIGHTWEIGHT_AGENT_CONFIG_PATTERNS

    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize checker with optional GitHub API token for higher rate limits.

        Args:
            github_token: GitHub API token for authenticated requests (optional)
        """
        self.github_token = github_token
        self.session_cache: Dict[Tuple[str, str], Tuple[bool, List[str]]] = {}  # Cache API results for efficiency

    def has_agent_config_files(
        self, full_repo_name: str, ref: str = "HEAD", timeout: int = 5
    ) -> Tuple[bool, List[str]]:
        """
        Check if repository has agent configuration files via GitHub API.

        Args:
            full_repo_name: Repository name (e.g., 'owner/repo')
            ref: Git reference (branch name, tag, commit SHA; default: HEAD)
            timeout: Request timeout in seconds

        Returns:
            (has_agent_files: bool, agent_files_found: list[str])

        Example:
            has_files, found = checker.has_agent_config_files('pytorch/pytorch')
            # Returns: (True, ['.cursorrules', 'copilot_instructions.md'])
        """
        try:
            # Check cache first
            cache_key: Tuple[str, str] = (full_repo_name, ref)
            if cache_key in self.session_cache:
                return self.session_cache[cache_key]

            # Fetch root directory contents via GitHub API and recurse one level into
            # any top-level directories so we can see nested config files too.
            contents = self._get_repo_contents_one_level(
                full_repo_name, ref=ref, timeout=timeout
            )
            if contents is None:
                logger.debug(
                    f"[github-api] Could not fetch {full_repo_name} contents (API failure or private repo)"
                )
                return False, []

            # Check if any agent config files are present
            found_files = []
            for _agent, config_files in self.AGENT_CONFIG_FILES.items():
                for config_file in config_files:
                    if any(
                        path_matches_pattern(
                            item.get("path", item.get("name", "")),
                            config_file,
                            is_dir=item.get("type") == "dir",
                        )
                        for item in contents
                    ):
                        found_files.append(config_file)

            result = (len(found_files) > 0, found_files)
            self.session_cache[cache_key] = result
            return result

        except Exception as e:
            logger.debug(f"[github-api] Error checking {full_repo_name}: {e}")
            return False, []

    @staticmethod
    def _is_rate_limited(response: Optional[requests.Response]) -> bool:
        """True for a 429, or a 403 GitHub reports as exhausted rate limit
        (as opposed to a 403 for a private/blocked repo, which has no
        X-RateLimit-Remaining: 0 header)."""
        if response is None:
            return False
        if response.status_code == 429:
            return True
        return (
            response.status_code == 403
            and response.headers.get("X-RateLimit-Remaining") == "0"
        )

    @staticmethod
    def _rate_limit_wait_seconds(response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0.5)
            except ValueError:
                pass
        return min(2**attempt, 30)

    def _get_repo_contents(
        self,
        full_repo_name: str,
        path: str = "",
        ref: str = "HEAD",
        timeout: int = 5,
        *,
        max_retries: int = 3,
    ) -> Optional[List[Dict]]:
        """
        Fetch repository contents from GitHub API.

        Args:
            full_repo_name: Repository name (owner/repo)
            path: File path (empty for root)
            ref: Git reference
            timeout: Request timeout

        Returns:
            List of file/folder info dicts, or None if the API call fails --
            either genuinely (404, private repo) or after exhausting retries
            on a rate-limited response. Both cases return the same shape
            since callers treat None as "unavailable," but a rate-limited
            None is logged distinctly (warning, not debug) so it's visible:
            it means "unknown," not "verified absent," even though
            has_agent_config_files() currently has no way to represent that
            distinction to its own callers.
        """
        url = f"https://api.github.com/repos/{full_repo_name}/contents/{path}"
        params = {"ref": ref} if ref and ref != "HEAD" else None

        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"

        for attempt in range(max_retries + 1):
            try:
                response = requests.get(
                    url, headers=headers, params=params, timeout=timeout
                )
                response.raise_for_status()
                data = response.json()
                # Handle single file vs directory listing
                if isinstance(data, list):
                    return data
                return [data] if isinstance(data, dict) else None
            except requests.HTTPError as e:
                if self._is_rate_limited(e.response) and attempt < max_retries:
                    wait_seconds = self._rate_limit_wait_seconds(e.response, attempt)
                    logger.warning(
                        f"[github-api] Rate limited fetching {full_repo_name} "
                        f"(attempt {attempt + 1}/{max_retries + 1}); "
                        f"retrying in {wait_seconds:.1f}s"
                    )
                    time.sleep(wait_seconds)
                    continue
                if self._is_rate_limited(e.response):
                    logger.warning(
                        f"[github-api] Rate limited fetching {full_repo_name}; "
                        "exhausted retries"
                    )
                elif e.response is not None and e.response.status_code == 404:
                    logger.debug(f"[github-api] Not found: {full_repo_name}")
                else:
                    status = e.response.status_code if e.response is not None else None
                    logger.debug(f"[github-api] HTTP {status}: {full_repo_name}")
                return None
            except requests.RequestException as e:
                logger.debug(f"[github-api] Exception fetching {full_repo_name}: {e}")
                return None
        return None

    def _get_repo_contents_one_level(
        self,
        full_repo_name: str,
        ref: str = "HEAD",
        timeout: int = 5,
    ) -> Optional[List[Dict]]:
        """Fetch root contents and one level of child directory contents."""
        root_contents = self._get_repo_contents(
            full_repo_name, path="", ref=ref, timeout=timeout
        )
        if root_contents is None:
            return None

        collected = list(root_contents)
        for item in root_contents:
            if item.get("type") == "dir" and item.get("path"):
                child_contents = self._get_repo_contents(
                    full_repo_name,
                    path=item["path"],
                    ref=ref,
                    timeout=timeout,
                )
                if child_contents:
                    collected.extend(child_contents)

        return collected


class AgentFileScanner:
    """Scan repositories for agent configuration files."""

    # Agent configuration file patterns (case-insensitive)
    AGENT_FILE_PATTERNS = {
        "claude": {
            "file_names": [
                "CLAUDE.md",
                ".claudeignore",
                ".claude",
                "claude.config",
            ],
            "patterns": [r"claude\.md$", r"\.claudeignore$", r"\.claude$", r"claude\.config$"],
        },
        "cursor": {
            "file_names": [
                ".cursor",
                ".cursorrules",
                ".cursorignore",
                "cursor.config",
            ],
            "patterns": [r"\.cursor(rules|ignore)?$", r"cursor\.config$"],
        },
        "copilot": {
            "file_names": [
                ".copilot",
                ".copilot.config",
                ".copilot-config",
                "copilot.config",
            ],
            "patterns": [r"\.copilot", r"copilot\.config"],
        },
        "aider": {
            "file_names": [
                ".aider.conf",
                ".aider.conf.json",
                ".aider-config",
                "aider.config",
            ],
            "patterns": [r"\.aider", r"aider\.config", r"aider\.conf"],
        },
        "openhands": {
            "file_names": [
                ".openhands.config",
                ".openhands",
                "openhands.config",
            ],
            "patterns": [r"\.openhands", r"openhands\.config"],
        },
        "devin": {
            "file_names": [
                ".devin.config",
                ".devin",
                "devin.config",
            ],
            "patterns": [r"\.devin", r"devin\.config"],
        },
        "cline": {
            "file_names": [
                ".cline.config",
                ".cline",
                "cline.config",
            ],
            "patterns": [r"\.cline", r"cline\.config"],
        },
        "other_agents": {
            "file_names": [
                ".junie.config",
                ".gemini.config",
                ".julius.config",
                "agent.config",
            ],
            "patterns": [r"\.junie", r"\.gemini", r"\.julius", r"agent\.config"],
        },
    }

    def __init__(self, clones_dir: Optional[Path] = None):
        """
        Initialize the agent file scanner.

        Args:
            clones_dir: Path to directory containing cloned repositories.
                       Defaults to user data dir + clones/.
        """
        if clones_dir is None:
            clones_dir = DEFAULT_CLONES_DIR

        self.clones_dir = Path(clones_dir)

        if not self.clones_dir.exists():
            raise ValueError(f"Clones directory not found: {self.clones_dir}")

    def scan_repository(self, repo_name: str) -> AgentFileDetectionResult:
        """
        Scan a single repository for agent configuration files.

        Args:
            repo_name: Name of repository subdirectory in clones_dir

        Returns:
            AgentFileDetectionResult with agents and files found

        Raises:
            ValueError: If repository directory not found
        """
        repo_path = self.clones_dir / repo_name

        if not repo_path.exists():
            raise ValueError(f"Repository not found: {repo_path}")

        if not repo_path.is_dir():
            raise ValueError(f"Not a directory: {repo_path}")

        result = AgentFileDetectionResult(repo_name=repo_name)

        # Scan for each agent type
        for agent_name, patterns in self.AGENT_FILE_PATTERNS.items():
            files_found = self._find_agent_files(repo_path, patterns)

            if files_found:
                result.agents_found[agent_name] = files_found

        return result

    def _find_agent_files(
        self, repo_path: Path, patterns: Dict[str, List]
    ) -> List[str]:
        """
        Find agent configuration files matching patterns.

        Args:
            repo_path: Path to repository
            patterns: Dict with 'file_names' and 'patterns' lists

        Returns:
            List of relative paths to found files
        """
        found_files = []
        file_names = patterns.get("file_names", [])
        regex_patterns = patterns.get("patterns", [])

        # os.walk with in-place dirname pruning (rather than rglob("*"))
        # skips .git/node_modules/vendor/etc entirely instead of merely
        # filtering their entries afterward -- avoids both false positives
        # from a vendored dependency's own config file and the wasted I/O
        # of walking .git's internal objects/hooks on every scan.
        all_paths: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(repo_path):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIR_NAMES]
            base = Path(dirpath)
            all_paths.extend(base / d for d in dirnames)
            all_paths.extend(base / f for f in filenames)

        # Search by exact filename (case-insensitive)
        for file_name in file_names:
            file_name_lower = file_name.lower()
            for found_path in all_paths:
                rel_path = found_path.relative_to(repo_path)
                rel_lower = str(rel_path).lower()
                if found_path.name.lower() == file_name_lower or fnmatch.fnmatchcase(
                    rel_lower, file_name_lower
                ):
                    found_files.append(str(rel_path))

        # Search by regex pattern (case-insensitive)
        for pattern in regex_patterns:
            compiled = re.compile(pattern, re.IGNORECASE)
            for found_path in all_paths:
                if compiled.search(found_path.name):
                    rel_path = found_path.relative_to(repo_path)
                    found_files.append(str(rel_path))

        # Remove duplicates while preserving order
        return list(dict.fromkeys(found_files))

    def scan_all(
        self, show_progress: bool = True
    ) -> Dict[str, AgentFileDetectionResult]:
        """
        Scan all repositories in clones directory.

        Args:
            show_progress: Whether to log progress for each repository

        Returns:
            Dict mapping repo_name to AgentFileDetectionResult
            (Only includes repositories with agent files found)
        """
        results = {}
        repo_dirs = [d for d in self.clones_dir.iterdir() if d.is_dir()]
        total = len(repo_dirs)

        logger.info(f"Scanning {total} repositories for agent files")

        for idx, repo_dir in enumerate(repo_dirs, 1):
            repo_name = repo_dir.name

            try:
                result = self.scan_repository(repo_name)

                if result.total_agent_files > 0:
                    results[repo_name] = result
                    if show_progress:
                        agent_list = ", ".join(result.agents_found.keys())
                        logger.info(
                            f"[{idx}/{total}] {repo_name}: Found agents: {agent_list} "
                            f"({result.total_agent_files} files)"
                        )
                else:
                    if show_progress and idx % 50 == 0:
                        logger.info(
                            f"[{idx}/{total}] Scanned {idx} repos, "
                            f"{len(results)} with agent files so far"
                        )

            except Exception as e:
                logger.warning(f"Failed to scan {repo_name}: {e}")

        logger.info(
            f"Scan complete: Found agent files in {len(results)}/{total} repositories"
        )

        return results

    def get_summary(self, scan_results: Dict[str, AgentFileDetectionResult]) -> Dict:
        """
        Generate summary statistics from scan results.

        Args:
            scan_results: Dict from scan_all()

        Returns:
            Dict with summary statistics
        """
        agent_counts: Dict[str, int] = {}
        total_files = 0
        repo_with_multiple_agents = 0

        for result in scan_results.values():
            total_files += result.total_agent_files

            if len(result.agents_found) > 1:
                repo_with_multiple_agents += 1

            for agent_name in result.agents_found.keys():
                agent_counts[agent_name] = agent_counts.get(agent_name, 0) + 1

        return {
            "total_repositories_with_agents": len(scan_results),
            "total_agent_files_found": total_files,
            "repositories_with_multiple_agents": repo_with_multiple_agents,
            "agent_counts": agent_counts,
        }


def scan_for_agents(
    clones_dir: Optional[Path] = None, show_progress: bool = True
) -> Tuple[Dict[str, AgentFileDetectionResult], Dict]:
    """
    Convenience function to scan all repositories for agent files.

    Args:
        clones_dir: Path to clones directory (defaults to ./clones)
        show_progress: Whether to log progress information

    Returns:
        Tuple of (results_dict, summary_dict)
    """
    scanner = AgentFileScanner(clones_dir)
    results = scanner.scan_all(show_progress=show_progress)
    summary = scanner.get_summary(results)

    return results, summary


# ============================================================================
# PHASE 1B: Commit Verification via Co-authored-by Trailers
# ============================================================================


@dataclass
class AgentCommitVerificationResult:
    """Result of verifying agent commits in a single repository."""

    repo_name: str
    agent_commits: Dict[str, str] = field(
        default_factory=dict
    )  # {commit_sha: agent_type}
    total_agent_commits: int = 0
    verification_method: str = "co-authored-by"  # Method used for detection

    def __post_init__(self):
        """Calculate total agent commits found."""
        self.total_agent_commits = len(self.agent_commits)


class AgentCommitVerifier:
    """Verify agent commits via Co-authored-by trailer parsing."""

    # Case-insensitive keywords for agent detection in commit messages.
    AGENT_KEYWORDS = AGENT_SIGNATURES

    def __init__(self, clones_dir: Optional[Path] = None):
        """
        Initialize the commit verifier.

        Args:
            clones_dir: Path to directory containing cloned repositories.
                       Defaults to user data dir + clones/.
        """
        if clones_dir is None:
            clones_dir = DEFAULT_CLONES_DIR

        self.clones_dir = Path(clones_dir)

    def verify_repository(
        self, repo_name: str, start_date: str = AGENT_CORPUS_START_DATE
    ) -> AgentCommitVerificationResult:
        """
        Verify agent commits in a single repository.

        Args:
            repo_name: Repository directory name
            start_date: Filter commits after this date (ISO format YYYY-MM-DD)

        Returns:
            AgentCommitVerificationResult with commits found

        Raises:
            RuntimeError: If git operations fail
        """
        repo_path = self.clones_dir / repo_name

        if not repo_path.exists():
            raise RuntimeError(f"Repository not found: {repo_path}")

        if not repo_path.is_dir():
            raise RuntimeError(f"Not a directory: {repo_path}")

        agent_commits = {}

        try:
            since_date = datetime.fromisoformat(start_date)
            for commit in Repository(
                str(repo_path),
                since=since_date,
                only_no_merge=True,
            ).traverse_commits():
                commit_data = {
                    "sha": commit.hash,
                    "date": commit.author_date.date().isoformat(),
                    "author_name": commit.author.name,
                    "author_email": commit.author.email,
                    "message": commit.msg,
                }
                agent_type = self._detect_agent_in_commit(commit_data)
                if agent_type:
                    agent_commits[commit_data["sha"]] = agent_type
        except Exception as e:
            raise RuntimeError(f"Git operation failed for {repo_name}: {e}")

        return AgentCommitVerificationResult(
            repo_name=repo_name, agent_commits=agent_commits
        )

    def verify_all(
        self,
        repo_names: List[str],
        start_date: str = AGENT_CORPUS_START_DATE,
        show_progress: bool = True,
    ) -> Dict[str, AgentCommitVerificationResult]:
        """
        Verify agents in multiple repositories.

        Args:
            repo_names: List of repository names to verify
            start_date: Filter commits after this date (ISO format)
            show_progress: Whether to log progress for each repository

        Returns:
            Dict mapping repo_name to AgentCommitVerificationResult
            (Only includes repositories with agent commits)
        """
        results = {}
        total = len(repo_names)

        logger.info(f"Verifying {total} repositories for agent commits")

        for idx, repo_name in enumerate(repo_names, 1):
            try:
                result = self.verify_repository(repo_name, start_date)

                if result.total_agent_commits > 0:
                    results[repo_name] = result
                    if show_progress:
                        logger.info(
                            f"[{idx}/{total}] {repo_name}: "
                            f"Found {result.total_agent_commits} agent commits"
                        )
                else:
                    if show_progress and idx % 20 == 0:
                        logger.info(
                            f"[{idx}/{total}] Verified {idx} repos, "
                            f"{len(results)} with agent commits so far"
                        )

            except Exception as e:
                logger.warning(f"Failed to verify {repo_name}: {e}")

        logger.info(
            f"Verification complete: {len(results)}/{total} repositories have agent commits"
        )

        return results

    def _detect_agent_in_commit(self, commit_data: Dict) -> Optional[str]:
        """
        Detect agent type from commit metadata.

        Checks in order, first match wins:
        1. Bot status (author name/email against bots.csv) -- never
           overridable by a later signal. A bot-authored commit whose
           message happens to contain an agent-style trailer (e.g. a
           templated "Generated-by:" line some tooling stamps onto
           dependency-bump commits) must still be excluded as bot, not
           misattributed to that agent.
        2. Co-Authored-By/Assisted-by/Generated-by trailer (highest
           confidence agent signal, since it's a deliberate, structured
           convention only agents/tooling emit -- as opposed to author
           identity below, which is a freely-editable field real humans
           also populate).
        3. Author name
        4. Author email

        Deliberately does NOT scan the free-text commit message body: a
        prose mention of an agent's name (e.g. "Revert a bad Claude
        suggestion", or "Fix cursor blinking bug" -- "cursor" the UI
        element, not the agent) is not evidence of agent authorship, and
        scanning it produced verified false positives. The structured
        fields above (trailer/author identity) are the legitimate Tier 2
        signal.

        Args:
            commit_data: Dict with sha, date, author_name, author_email, message

        Returns:
            Agent type (claude|copilot|cursor|etc) or None if no match

        Note:
            Matching is word-boundary-based (not a bare substring check),
            case-insensitive. First match wins. Word boundaries prevent a
            keyword from matching inside an unrelated compound word/surname
            (e.g. "cline" inside "McLine"), but cannot distinguish a keyword
            that is *also* a common standalone first name (e.g. an author
            literally named "Devin") -- see agent_heuristics.yaml's module
            comment for this known, inherent limitation. Checking the
            trailer before author identity (see order above) avoids this
            collision whenever a commit has both a colliding author name
            and a correct, unambiguous trailer.
        """
        message = commit_data["message"]
        author_name = commit_data["author_name"]
        author_email = commit_data["author_email"]

        if is_bot_author(f"{author_name} {author_email}"):
            return None

        # Check Co-Authored-By/Assisted-by/Generated-by trailers. Uses the
        # same AGENT_TRAILER_RE as Tier1RepositoryScanner (collection/utils.py)
        # rather than a separate ad-hoc regex here -- previously this method
        # had its own inline pattern that required a literal "co-authored-by"
        # (hyphens mandatory) and an angle-bracket email, so it silently
        # missed the "assisted-by"/"generated-by" trailer forms and
        # hyphen-omitted variants ("Coauthored-by") that AGENT_TRAILER_RE
        # already handles.
        for trailer_value in AGENT_TRAILER_RE.findall(message):
            agent_type = self._match_agent_keywords(trailer_value)
            if agent_type:
                return agent_type

        # Check author name
        agent_type = self._match_agent_keywords(author_name)
        if agent_type:
            return agent_type

        # Check author email
        agent_type = self._match_agent_keywords(author_email)
        if agent_type:
            return agent_type

        return None

    def _match_agent_keywords(self, text: str) -> Optional[str]:
        """
        Match agent keywords in text as whole words/phrases.

        Args:
            text: Text to search

        Returns:
            Agent type if matched, None otherwise
        """
        return match_agent_keyword(text, self.AGENT_KEYWORDS)

    def get_verification_summary(
        self, verification_results: Dict[str, AgentCommitVerificationResult]
    ) -> Dict:
        """
        Generate summary statistics from verification results.

        Args:
            verification_results: Dict from verify_all()

        Returns:
            Dict with summary statistics
        """
        agent_commit_counts: Dict[str, int] = {}
        total_agent_commits = 0
        total_repos = len(verification_results)

        for result in verification_results.values():
            total_agent_commits += result.total_agent_commits

            for agent_type in result.agent_commits.values():
                agent_commit_counts[agent_type] = (
                    agent_commit_counts.get(agent_type, 0) + 1
                )

        return {
            "total_repositories_verified": total_repos,
            "total_agent_commits_found": total_agent_commits,
            "agent_commit_counts": agent_commit_counts,
            "average_commits_per_repo": (
                total_agent_commits / total_repos if total_repos > 0 else 0
            ),
        }
