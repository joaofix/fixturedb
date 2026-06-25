"""
Phase 1A: Scan repositories for AI agent configuration files.

Identifies repositories that may have been worked on with AI assistants
by detecting configuration files commonly created by these tools.

Supported agents: Claude, Cursor, Copilot, Aider, OpenHands, Devin, Jules, Cline, Junie, Gemini
"""

import json
import logging
import platformdirs
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from pydriller import Repository

from .config import AGENT_CORPUS_START_DATE
from .agent_patterns import (
    AGENT_SIGNATURES,
    LIGHTWEIGHT_AGENT_CONFIG_PATTERNS,
    path_matches_pattern,
)

from collection.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_CLONES_DIR = Path(platformdirs.user_data_dir("icsme-nier", "clones"))


@dataclass
class AgentFileDetectionResult:
    """Result of scanning a single repository for agent files."""

    repo_name: str
    agents_found: Dict[str, List[str]] = field(default_factory=dict)
    total_agent_files: int = 0

    def __post_init__(self):
        """Calculate total agent files found."""
        self.total_agent_files = sum(len(files) for files in self.agents_found.values())


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
        self.session_cache = {}  # Cache API results for efficiency

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
            cache_key = f"{full_repo_name}:{ref}"
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
            for agent, config_files in self.AGENT_CONFIG_FILES.items():
                for config_file in config_files:
                    if any(
                        path_matches_pattern(
                            item.get("path", item.get("name", "")), config_file
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

    def _get_repo_contents(
        self, full_repo_name: str, path: str = "", ref: str = "HEAD", timeout: int = 5
    ) -> Optional[List[Dict]]:
        """
        Fetch repository contents from GitHub API.

        Args:
            full_repo_name: Repository name (owner/repo)
            path: File path (empty for root)
            ref: Git reference
            timeout: Request timeout

        Returns:
            List of file/folder info dicts, or None if API call fails
        """
        url = f"https://api.github.com/repos/{full_repo_name}/contents/{path}"
        if ref and ref != "HEAD":
            url += f"?ref={ref}"

        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"

        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                # Handle single file vs directory listing
                if isinstance(data, list):
                    return data
                return [data] if isinstance(data, dict) else None
        except HTTPError as e:
            if e.code == 404:
                logger.debug(f"[github-api] Not found: {full_repo_name}")
            else:
                logger.debug(f"[github-api] HTTP {e.code}: {full_repo_name}")
            return None
        except Exception as e:
            logger.debug(f"[github-api] Exception fetching {full_repo_name}: {e}")
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
    """Phase 1A: Scan repositories for agent configuration files."""

    # Agent configuration file patterns (case-insensitive)
    AGENT_FILE_PATTERNS = {
        "claude": {
            "file_names": [
                ".cursorrules",  # Common for Claude in Cursor editor
                ".cursorignore",
                ".cursor",
                "claude.config",
            ],
            "patterns": [r"\.cursorrules?$", r"claude\.config$"],
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

    def __init__(self, clones_dir: Path = None):
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

        all_paths = list(repo_path.rglob("*"))

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
        agent_counts = {}
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
    clones_dir: Path = None, show_progress: bool = True
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
    """Phase 1B: Verify agent commits via Co-authored-by trailer parsing."""

    # Case-insensitive keywords for agent detection in commit messages.
    AGENT_KEYWORDS = AGENT_SIGNATURES

    def __init__(self, clones_dir: Path = None):
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

        Checks in order:
        1. Co-Authored-By trailer (highest confidence)
        2. Author name for agent keywords
        3. Commit message for agent keywords

        Args:
            commit_data: Dict with sha, date, author_name, author_email, message

        Returns:
            Agent type (claude|copilot|cursor|etc) or None if no match

        Note:
            Matching is case-insensitive. First match wins.
        """
        message = commit_data["message"]
        author_name = commit_data["author_name"]
        author_email = commit_data["author_email"]

        # Check Co-Authored-By trailers (highest confidence)
        for match in re.finditer(
            r"co-authored-by:\s*([^<]+)<[^>]+>", message, re.IGNORECASE
        ):
            co_author = match.group(1).strip().lower()
            agent_type = self._match_agent_keywords(co_author)
            if agent_type:
                return agent_type

        if "[bot]" in author_name.lower():
            return None

        # Check author name
        agent_type = self._match_agent_keywords(author_name.lower())
        if agent_type:
            return agent_type

        # Check author email
        agent_type = self._match_agent_keywords(author_email.lower())
        if agent_type:
            return agent_type

        # Check commit message
        agent_type = self._match_agent_keywords(message.lower())
        if agent_type:
            return agent_type

        return None

    def _match_agent_keywords(self, text: str) -> Optional[str]:
        """
        Match agent keywords in text.

        Args:
            text: Text to search (should already be lowercase)

        Returns:
            Agent type if matched, None otherwise
        """
        for agent_name, keywords in self.AGENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return agent_name

        return None

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
        agent_commit_counts = {}
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
