"""Repository control-variable computation: domain, star tier, age.

Split out of db.py -- these are pure functions with no sqlite3/DB
dependency at all (domain classification from topics/description text,
star-tier thresholding, date arithmetic); they happen to feed columns in
the `repositories` table, but don't belong in the database layer itself.
"""

from __future__ import annotations

import json
import re
from datetime import datetime as dt


def classify_domain(topics_str: str | None, description_str: str | None) -> str:
    """
    Classify repository domain from topics and description.

    Returns one of: web, systems, ml, security, database, devops, other
    """
    text = ""
    if topics_str:
        try:
            topics_list = (
                json.loads(topics_str) if isinstance(topics_str, str) else topics_str
            )
            text += " ".join(str(t).lower() for t in topics_list) + " "
        except (json.JSONDecodeError, TypeError):
            pass

    if description_str:
        text += description_str.lower()

    # Domain classification keywords
    domain_keywords = {
        "web": [
            "web",
            "rest",
            "http",
            "frontend",
            "react",
            "vue",
            "angular",
            "django",
            "flask",
            "rails",
        ],
        "systems": [
            "kernel",
            "driver",
            "os",
            "system",
            "compiler",
            "linux",
            "windows",
            "os/2",
            "unix",
        ],
        "ml": [
            "machine learning",
            "ml",
            "ai",
            "neural",
            "deep learning",
            "tensorflow",
            "pytorch",
            "scikit",
        ],
        "security": ["security", "crypto", "encryption", "ssl", "tls", "auth", "oauth"],
        "database": [
            "database",
            "db",
            "sql",
            "nosql",
            "mongodb",
            "postgresql",
            "mysql",
            "cache",
            "redis",
        ],
        "devops": [
            "devops",
            "kubernetes",
            "docker",
            "ci/cd",
            "jenkins",
            "ansible",
            "terraform",
        ],
    }

    # Word-boundary matching, not a plain substring check: several keywords
    # are short/common enough to collide with unrelated English words (e.g.
    # "ai" inside "email", "os" inside "postgresql", "auth" inside "author"),
    # which previously mis-tagged ordinary repo descriptions.
    for domain, keywords in domain_keywords.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords):
            return domain

    return "other"


def compute_star_tier(stars: int | None) -> str:
    """
    Classify repository into star tier based on GitHub stars.

    Returns: "core" (>=500 stars) or "extended" (<500 stars)
    """
    if stars is None:
        return "extended"
    return "core" if stars >= 500 else "extended"


def compute_repo_age_years(created_at_str: str | None) -> float | None:
    """
    Compute repository age in years from creation date string (ISO format).

    Returns: age in years as float, or None if created_at is None/invalid
    """
    if not created_at_str:
        return None

    try:
        created = dt.fromisoformat(created_at_str.replace("Z", "+00:00"))
        now = dt.now(created.tzinfo) if created.tzinfo else dt.now()
        age_days = (now - created).days
        return age_days / 365.25
    except (ValueError, AttributeError):
        return None


def compute_repo_age_at_date(
    created_at_str: str | None, target_date_str: str
) -> float | None:
    """
    Compute repository age in years relative to a specific date.

    Used for between-group design to compute control variables at historical
    snapshots (e.g., 2020-12-31 for human corpus, 2025-01-01 for agent corpus).

    Args:
        created_at_str: Repository creation date (ISO format)
        target_date_str: Target date for age computation (ISO format)

    Returns:
        Age in years as float, or None if inputs are invalid
    """
    if not created_at_str or not target_date_str:
        return None

    try:
        created = dt.fromisoformat(created_at_str.replace("Z", "+00:00"))
        target = dt.fromisoformat(target_date_str.replace("Z", "+00:00"))
        age_days = (target - created).days

        # Handle negative age (repo created after target date)
        if age_days < 0:
            return None

        return age_days / 365.25
    except (ValueError, AttributeError):
        return None


def get_control_variables_at_date(repo: dict, target_date: str) -> dict:
    """
    Compute control variables (domain, star_tier, repo_age) at a specific date.

    For between-group comparison, control variables should reflect repo state
    at fixture writing time (2020-12-31 for human, 2025-01-01 for agent).

    Args:
        repo: Repository metadata dict with keys: topics, description, stars, created_at
        target_date: ISO date string (e.g., "2020-12-31")

    Returns:
        Dict with control_variables keys:
        - domain: str (web, systems, ml, security, database, devops, other)
        - star_tier: str (core >=500, extended <500) — current stars only
        - repo_age_years: float (age at target_date) or None
    """
    domain = classify_domain(repo.get("topics"), repo.get("description"))
    # Note: Star tier uses current stars (historical unavailable from API)
    star_tier = compute_star_tier(repo.get("stars"))
    repo_age = compute_repo_age_at_date(repo.get("created_at"), target_date)

    return {
        "domain": domain,
        "star_tier": star_tier,
        "repo_age_years": repo_age,
    }
