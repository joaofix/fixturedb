"""
GitHub Archive data access module.

Provides access to historical GitHub repository metadata (stars, commits, etc.)
from GitHub Archive (gharchive.org) via BigQuery.

This is used to compute control variables (star tier, repo age) at specific
historical dates (e.g., 2020-12-31 for human corpus, 2025-01-01 for agent corpus).
"""

from datetime import datetime
from typing import Optional

from collection.logging_utils import get_logger

logger = get_logger(__name__)


class GitHubArchiveClient:
    """Access GitHub Archive data via BigQuery API."""

    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize GitHub Archive client.

        Args:
            project_id: Google Cloud Project ID (for BigQuery)
                       If None, will try to auto-detect or skip archive queries
        """
        self.project_id = project_id
        self.bq_client = None

        if project_id:
            try:
                from google.cloud import bigquery

                self.bq_client = bigquery.Client(project=project_id)
                logger.info(
                    f"[GitHub Archive] Connected to BigQuery project: {project_id}"
                )
            except (ImportError, Exception) as e:
                logger.warning(f"[GitHub Archive] BigQuery unavailable: {e}")
                logger.info(
                    "[GitHub Archive] Will use fallback methods for historical data"
                )

    def get_repo_stars_at_date(
        self, repo_full_name: str, target_date: str
    ) -> Optional[int]:
        """
        Get approximate star count for a repository at a specific date.

        Uses GitHub Archive BigQuery data to find historical star counts.
        Returns None if data unavailable (fallback: use current stars).

        Args:
            repo_full_name: Repository full name (e.g., "owner/repo")
            target_date: ISO date string (e.g., "2020-12-31")

        Returns:
            Star count at target date, or None if unavailable
        """
        if not self.bq_client:
            logger.debug(
                f"[GitHub Archive] BigQuery unavailable; cannot get stars for {repo_full_name} at {target_date}"
            )
            return None

        try:
            # Parse date
            datetime.fromisoformat(target_date)
            # BigQuery table is partitioned by day; look for earliest data >= target_date
            query = f"""
            SELECT
                stargazers_count
            FROM
                `bigquery-public-data.github_repos.raw_commits`
            WHERE
                repo_name = '{repo_full_name}'
                AND DATE(commit_timestamp) >= '{target_date}'
            ORDER BY
                commit_timestamp ASC
            LIMIT 1
            """

            query_job = self.bq_client.query(query)
            results = query_job.result()

            for row in results:
                return row.stargazers_count

            logger.debug(
                f"[GitHub Archive] No data for {repo_full_name} at {target_date}"
            )
            return None

        except Exception as e:
            logger.warning(f"[GitHub Archive] Query failed for {repo_full_name}: {e}")
            return None

    def get_repo_age_at_date(
        self, repo_full_name: str, target_date: str
    ) -> Optional[float]:
        """
        Get repository age (in years) relative to a specific date.

        Queries GitHub Archive for repository creation date and computes
        age relative to target_date.

        Args:
            repo_full_name: Repository full name (e.g., "owner/repo")
            target_date: ISO date string (e.g., "2020-12-31")

        Returns:
            Repository age in years, or None if unavailable
        """
        if not self.bq_client:
            logger.debug(
                f"[GitHub Archive] BigQuery unavailable; cannot get age for {repo_full_name}"
            )
            return None

        try:
            query = f"""
            SELECT
                created_at
            FROM
                `bigquery-public-data.github_repos.repositories`
            WHERE
                CONCAT(owner.login, '/', name) = '{repo_full_name}'
            LIMIT 1
            """

            query_job = self.bq_client.query(query)
            results = query_job.result()

            for row in results:
                created_at = row.created_at
                target_dt = datetime.fromisoformat(target_date)

                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)

                age_days = (target_dt - created_at).days
                age_years = age_days / 365.25
                return age_years

            logger.debug(f"[GitHub Archive] No creation date for {repo_full_name}")
            return None

        except Exception as e:
            logger.warning(f"[GitHub Archive] Query failed for {repo_full_name}: {e}")
            return None


# Global client instance (lazy-initialized)
_archive_client = None


def get_archive_client(project_id: Optional[str] = None) -> GitHubArchiveClient:
    """
    Get or create global GitHub Archive client.

    Args:
        project_id: Google Cloud Project ID (optional)

    Returns:
        GitHubArchiveClient instance
    """
    global _archive_client
    if _archive_client is None:
        _archive_client = GitHubArchiveClient(project_id=project_id)
    return _archive_client


def get_repo_stars_at_date(
    repo_full_name: str,
    target_date: str,
    project_id: Optional[str] = None,
) -> Optional[int]:
    """
    Convenience function: get historical star count.

    Args:
        repo_full_name: Repository full name (e.g., "owner/repo")
        target_date: ISO date string (e.g., "2020-12-31")
        project_id: Google Cloud Project ID (optional)

    Returns:
        Star count at target date, or None if unavailable
    """
    client = get_archive_client(project_id=project_id)
    return client.get_repo_stars_at_date(repo_full_name, target_date)


def get_repo_age_at_date(
    repo_full_name: str,
    target_date: str,
    project_id: Optional[str] = None,
) -> Optional[float]:
    """
    Convenience function: get historical repo age.

    Args:
        repo_full_name: Repository full name (e.g., "owner/repo")
        target_date: ISO date string (e.g., "2020-12-31")
        project_id: Google Cloud Project ID (optional)

    Returns:
        Repository age in years at target date, or None if unavailable
    """
    client = get_archive_client(project_id=project_id)
    return client.get_repo_age_at_date(repo_full_name, target_date)
