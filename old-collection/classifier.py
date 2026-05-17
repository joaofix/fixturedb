"""
Domain classifier for repositories.

Assigns one of six domain labels to each repository based on GitHub
topics, description, and repository name using a keyword heuristic.

Labels: web | data | cli | infra | library | other

Usage:
    python -m scripts.classify_domains
    # or call classify_all() from the pipeline
"""

import json
import logging
import re
from collection.db import db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword rules — evaluated in order, first match wins
# ---------------------------------------------------------------------------

DOMAIN_RULES: list[tuple[str, list[str]]] = [
    (
        "web",
        [
            "web",
            "http",
            "api",
            "rest",
            "graphql",
            "fastapi",
            "django",
            "flask",
            "express",
            "rails",
            "spring",
            "server",
            "request",
            "endpoint",
            "route",
            "middleware",
            "websocket",
            "grpc",
            "frontend",
            "backend",
            "react",
            "vue",
            "angular",
            "nextjs",
        ],
    ),
    (
        "data",
        [
            "data",
            "ml",
            "machine-learning",
            "deep-learning",
            "neural",
            "pandas",
            "numpy",
            "spark",
            "etl",
            "pipeline",
            "analytics",
            "dataset",
            "dataframe",
            "model",
            "train",
            "inference",
            "nlp",
            "vision",
            "tensorflow",
            "pytorch",
            "scikit",
        ],
    ),
    (
        "cli",
        [
            "cli",
            "command-line",
            "terminal",
            "shell",
            "tool",
            "utility",
            "script",
            "automation",
            "task",
            "runner",
            "build",
            "make",
            "cmd",
            "console",
            "prompt",
        ],
    ),
    (
        "infra",
        [
            "infra",
            "infrastructure",
            "devops",
            "docker",
            "kubernetes",
            "k8s",
            "cloud",
            "aws",
            "gcp",
            "azure",
            "deploy",
            "ci",
            "cd",
            "terraform",
            "ansible",
            "monitoring",
            "logging",
            "observability",
            "container",
            "helm",
        ],
    ),
    (
        "library",
        [
            "library",
            "lib",
            "sdk",
            "framework",
            "package",
            "module",
            "client",
            "wrapper",
            "binding",
            "plugin",
            "extension",
            "adapter",
            "connector",
            "driver",
        ],
    ),
]


def _classify_repo(full_name: str, description: str, topics_json: str) -> str:
    """Return a domain label for a single repository."""
    topics: list[str] = []
    try:
        topics = json.loads(topics_json or "[]")
    except (json.JSONDecodeError, TypeError) as e:
        logger.debug(
            f"Failed to parse topics JSON for repo {full_name}: {type(e).__name__}: {e}"
        )

    # Build a single text blob: name + description + topics
    name_parts = re.split(r"[/_\-]", full_name.split("/")[-1])
    text = " ".join(name_parts + [description or ""] + topics).lower()

    for domain, keywords in DOMAIN_RULES:
        if any(kw in text for kw in keywords):
            return domain

    return "other"


def classify_all(overwrite: bool = False) -> dict[str, int]:
    """
    Classify all repositories that have no domain label yet.
    If overwrite=True, re-classify all repos including already-labelled ones.
    Returns a count dict {domain: n}.
    """
    counts: dict[str, int] = {}

    with db_session() as conn:
        if overwrite:
            rows = conn.execute(
                "SELECT id, full_name, description, topics FROM repositories"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, full_name, description, topics FROM repositories "
                "WHERE domain IS NULL"
            ).fetchall()

        logger.info(f"Classifying {len(rows)} repositories …")

        for row in rows:
            domain = _classify_repo(
                row["full_name"],
                row["description"] or "",
                row["topics"] or "[]",
            )
            conn.execute(
                "UPDATE repositories SET domain = ? WHERE id = ?",
                (domain, row["id"]),
            )
            counts[domain] = counts.get(domain, 0) + 1

    logger.info(f"Domain classification done: {counts}")
    return counts
