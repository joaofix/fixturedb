"""
GitHub API search module for discovering repositories with agent configuration files.

Searches GitHub for repositories that contain agent configuration files
(.cursorrules, .claude/, .cursor/, copilot-instructions.md, etc.),
indicating active use of AI coding agents.
"""

import time
from pathlib import Path
from typing import Optional

import requests

from collection.logging_utils import get_logger

from .agent_patterns import (
    LIGHTWEIGHT_AGENT_CONFIG_PATTERNS,
    iter_exact_filename_patterns,
    repo_contains_patterns,
)
from .config import GITHUB_TOKEN, MIN_STARS

logger = get_logger(__name__)


class GitHubAPISearcher:
    """Search GitHub API for repositories with agent configuration files."""

    BASE_URL = "https://api.github.com"
    SEARCH_ENDPOINT = f"{BASE_URL}/search/repositories"
    CODE_SEARCH_ENDPOINT = f"{BASE_URL}/search/code"

    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub API searcher.

        Args:
            token: GitHub API token (optional, increases rate limits)
        """
        self.token = token or GITHUB_TOKEN
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})
        self.rate_limit_remaining = None
        self.rate_limit_reset = None

    def search_repos_with_agent_configs(
        self,
        language: str,
        min_stars: int = MIN_STARS,
        max_results: int = 1000,
    ) -> list[dict]:
        """
        Search GitHub for repositories with agent configuration files.

        Searches for repos with any of the agent config files:
        .cursorrules, .claude/, .cursor/, copilot-instructions.md, etc.

        Args:
            language: Programming language to filter (e.g., "python", "javascript")
            min_stars: Minimum star count for filtering
            max_results: Maximum results to return

        Returns:
            List of repository dicts with keys: full_name, stars, created_at,
            pushed_at, clone_url, language, topics, description, num_contributors
        """
        # We'll use the code search endpoint to look for agent config filenames
        # because filename: qualifiers are supported by /search/code. The
        # repository search endpoint does not accept filename: and will return
        # no results for this use-case.
        repos = {}
        page = 1
        per_page = 100

        # Query the code search endpoint once per config filename to avoid
        # complex OR groups that can produce 422 errors. We'll aggregate unique
        # repositories across all config filename searches.
        logger.info(
            f"[GitHub API] Searching for {language} repos with agent configs (code search per-filename)"
        )

        for config_file in iter_exact_filename_patterns(
            LIGHTWEIGHT_AGENT_CONFIG_PATTERNS
        ):
            if len(repos) >= max_results:
                break

            # Build a simple per-file code search query
            query = f'filename:"{config_file}" language:{language}'
            logger.debug(f"[GitHub API] Code search query: {query}")

            page = 1
            while len(repos) < max_results:
                # Per-request retry/backoff for transient errors
                max_retries = 3
                attempt = 0
                while attempt < max_retries:
                    attempt += 1
                    try:
                        response = self.session.get(
                            self.CODE_SEARCH_ENDPOINT,
                            params={
                                "q": query,
                                "page": page,
                                "per_page": per_page,
                            },
                            timeout=30,
                        )

                        # If GitHub responds 422 for a particular filename query,
                        # skip that filename and continue with the next; this avoids
                        # failing the whole discovery due to a single unsupported
                        # filename pattern.
                        if response.status_code == 422:
                            logger.warning(
                                f"[GitHub API] Code search returned 422 for query: {query}; skipping this filename"
                            )
                            attempt = max_retries
                            break

                        # Handle 403 (forbidden / rate limit).
                        # Code search has a strict 30/min limit (separate from core limit).
                        # Rather than waiting/retrying extensively, bail out and let
                        # the caller fall back to local scan.
                        if response.status_code == 403:
                            remaining = int(
                                response.headers.get("X-RateLimit-Remaining", "0")
                            )
                            reset = int(response.headers.get("X-RateLimit-Reset", "0"))
                            logger.warning(
                                f"[GitHub API] Code search rate-limited (403) for {config_file}. "
                                f"Remaining={remaining}, Reset={reset}. "
                                "Skipping remote search; caller should use local fallback."
                            )
                            # Return empty results to allow caller to fall back
                            return []

                        response.raise_for_status()

                        items = response.json().get("items", [])
                        if not items:
                            logger.info(
                                f"[GitHub API] No more code results for {config_file} at page {page}"
                            )
                            attempt = max_retries
                            break

                        for item in items:
                            repo_info = item.get("repository") or item.get("repo")
                            if not repo_info:
                                continue

                            full_name = repo_info.get("full_name")
                            if not full_name or full_name in repos:
                                continue

                            try:
                                owner, name = full_name.split("/")
                                details = self.get_repo_details(owner, name)
                            except Exception:
                                continue

                            stars_count = details.get("stargazers_count", 0)
                            if stars_count < min_stars:
                                continue

                            repo_dict = {
                                "full_name": full_name,
                                "stars": stars_count,
                                "forks": details.get("forks_count", 0),
                                "created_at": details.get("created_at"),
                                "pushed_at": details.get("pushed_at"),
                                "clone_url": details.get("clone_url"),
                                "language": details.get("language"),
                                "topics": details.get("topics", []),
                                "description": details.get("description", ""),
                                "github_id": details.get("id"),
                                "num_contributors": self.get_repo_contributors_count(
                                    owner, name
                                ),
                            }

                            repos[full_name] = repo_dict

                            if len(repos) >= max_results:
                                break

                        # Successful request, move to next page
                        page += 1
                        break

                    except requests.exceptions.RequestException as e:
                        # For timeouts and other transient issues, retry with
                        # exponential backoff. If attempts exhausted, log and
                        # move on to the next filename.
                        logger.warning(
                            f"[GitHub API] Request attempt {attempt} failed for {config_file}: {e}"
                        )
                        if attempt >= max_retries:
                            logger.error(
                                f"[GitHub API] Code search failed for {config_file} after {max_retries} attempts: {e}"
                            )
                            break
                        backoff = 2**attempt
                        time.sleep(backoff)
                        continue

        logger.info(
            f"[GitHub API] Found {len(repos)} repos with agent configs for {language}"
        )
        return list(repos.values())[:max_results]

    def get_repo_details(self, owner: str, repo: str) -> dict:
        """
        Get detailed repository information from GitHub API.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with repository metadata
        """
        try:
            response = self.session.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}",
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"[GitHub API] Failed to get details for {owner}/{repo}: {e}")
            raise

    def get_repo_contributors_count(self, owner: str, repo: str) -> int:
        """
        Get approximate contributor count for a repository.

        Note: GitHub API limits to first 30 contributors; this is approximate.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Approximate contributor count
        """
        try:
            response = self.session.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/contributors",
                params={"per_page": 1},  # Only need to check if endpoint works
                timeout=30,
            )
            response.raise_for_status()

            # Check the Link header for pagination info
            link_header = response.headers.get("Link", "")
            if "last" in link_header:
                # Extract page number from last link
                for link_part in link_header.split(","):
                    if 'rel="last"' in link_part:
                        # Extract page parameter from URL
                        import re

                        match = re.search(r"page=(\d+)", link_part)
                        if match:
                            return int(match.group(1))

            return len(response.json())
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"[GitHub API] Failed to get contributor count for {owner}/{repo}: {e}"
            )
            return 0

    def check_rate_status(self) -> dict:
        """
        Check current GitHub API rate limit status.

        Returns:
            Dict with rate_limit_remaining and rate_limit_reset
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/rate_limit", timeout=10)
            response.raise_for_status()
            data = response.json()
            rate = data["resources"]["core"]
            return {
                "rate_limit_remaining": rate["remaining"],
                "rate_limit_reset": rate["reset"],
                "rate_limit_total": rate["limit"],
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[GitHub API] Failed to check rate limits: {e}")
            return {}


def search_repos_with_agent_configs(
    language: str,
    min_stars: int = MIN_STARS,
    max_results: int = 1000,
    token: Optional[str] = None,
) -> list[dict]:
    """
    Convenience function: search for repos with agent configs.

    Args:
        language: Programming language (e.g., "python", "javascript")
        min_stars: Minimum star count
        max_results: Maximum results to return
        token: GitHub API token (optional)

    Returns:
        List of repository dicts
    """
    searcher = GitHubAPISearcher(token=token)
    return searcher.search_repos_with_agent_configs(language, min_stars, max_results)


def _detect_repo_language(repo_path: Path) -> str:
    """
    Detect primary language of a repository by examining file extensions.

    Args:
        repo_path: Path to the repository.

    Returns:
        Language string (python, javascript, java, typescript, etc.)
    """
    language_scores = {
        "python": 0,
        "javascript": 0,
        "java": 0,
        "typescript": 0,
    }

    # Count files by extension
    for suffix, lang in [
        (".py", "python"),
        (".js", "javascript"),
        (".jsx", "javascript"),
        (".ts", "typescript"),
        (".tsx", "typescript"),
        (".java", "java"),
    ]:
        try:
            matches = list(repo_path.rglob(f"*{suffix}"))
            language_scores[lang] += len(matches)
        except Exception:
            pass

    # Return the language with highest count, default to python
    if not any(language_scores.values()):
        return "python"
    return max(language_scores, key=language_scores.get)


def search_repos_with_agent_configs_local(
    language: str,
    max_results: int = 100,
    clones_dir: Optional[str] = None,
) -> list[dict]:
    """
    Local fallback: scan the workspace `clones/` directory for agent config files.

    This avoids GitHub API usage and is useful when code search is slow or
    rate-limited. It looks for known agent configuration patterns anywhere inside
    each repo under `clones/` and returns a lightweight repo dict.

    Args:
        language: (unused strict filter) kept for API compatibility.
        max_results: Maximum results to return.
        clones_dir: Optional path to clones directory. Defaults to repository `clones/`.

    Returns:
        List of repo dicts with `full_name` and `clone_path`.
    """
    repo_root = Path(__file__).resolve().parents[1]
    clones_path = Path(clones_dir) if clones_dir else repo_root / "clones"
    results = []
    if not clones_path.exists():
        logger.warning(f"[Local Scan] clones directory not found: {clones_path}")
        return []

    for entry in clones_path.iterdir():
        if len(results) >= max_results:
            break
        if not entry.is_dir():
            continue

        if not repo_contains_patterns(entry, LIGHTWEIGHT_AGENT_CONFIG_PATTERNS):
            continue

        # Derive a plausible full_name from directory name like owner__repo
        name = entry.name
        if "__" in name:
            owner, repo = name.split("__", 1)
            full_name = f"{owner}/{repo}"
        else:
            full_name = name

        # Detect actual language from repo files
        detected_language = _detect_repo_language(entry)

        results.append(
            {
                "full_name": full_name,
                "clone_path": str(entry),
                "stars": 0,
                "forks": 0,
                "created_at": None,
                "pushed_at": None,
                "clone_url": f"https://github.com/{full_name}.git",
                "language": detected_language,
                "topics": [],
                "description": f"Local clone: {name} (detected: {detected_language})",
                "github_id": hash(full_name)
                % 2147483647,  # Placeholder ID for local repos
                "num_contributors": 0,
            }
        )

    logger.info(
        f"[Local Scan] Found {len(results)} repos with agent configs in {clones_path}"
    )
    return results[:max_results]
