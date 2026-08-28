"""
Low-level, single-repo agent-detection primitives.

Pre-clone check for AI agent configuration files, via the GitHub API --
used by `repository_quality_control/agent_repository_counter.py` (Dataset A
repo qualification) and `dedupe_dataset_c_repos.py` (Dataset C dedup) to
avoid cloning a repo just to find out it has no agent config at all.

Used to also host the scan/verify primitives for
`tiered_agent_corpus_scanner.py`'s Tier 2 discovery path
(`AgentFileScanner`, `AgentCommitVerifier`) -- removed alongside Tier 2,
since this module's `GitHubAgentFileChecker` was their only other caller.

Supported agents are whatever `collection/heuristics/agent_heuristics.yaml`
catalogs (~60 as of this writing, see that file's provenance comment) --
not a fixed list hardcoded here.
"""

import time
from typing import Dict, List, Optional, Tuple

import requests

from collection.logging_utils import get_logger

from .agent_patterns import LIGHTWEIGHT_AGENT_CONFIG_PATTERNS, path_matches_pattern

logger = get_logger(__name__)


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
