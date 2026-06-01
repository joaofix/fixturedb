"""Paired within-repository collection for Andre-style commit-level comparison."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter

from .cli_utils import add_language_arg, add_repos_per_language_arg
from .cloner import clone_repo
from .config import CLONES_DIR, DATA_DIR, HUMAN_CORPUS_CUTOFF_DATE, LANGUAGE_CONFIGS
from .db import (
    db_session,
    initialise_db,
    insert_commit_observation,
    upsert_repository,
    classify_domain,
    compute_star_tier,
    compute_repo_age_years,
)
from .fixture_extractor import extract_fixtures_at_commit
from .agent_commit_detector import Tier1RepositoryScanner

from collection.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class PairedStudyStats:
    repos_scanned: int = 0
    repos_with_pairs: int = 0
    repos_passed_qc: int = 0
    repos_failed_qc: int = 0
    qc_skip_reasons: Dict[str, int] = field(default_factory=dict)
    agent_commits: int = 0
    human_commits: int = 0
    observations_inserted: int = 0
    fixtures_observed: int = 0
    mock_usages_observed: int = 0
    repos_by_language: Dict[str, int] = field(default_factory=dict)
    agent_type_breakdown: Dict[str, int] = field(default_factory=dict)
    domain_distribution: Dict[str, int] = field(default_factory=dict)
    star_tier_distribution: Dict[str, int] = field(default_factory=dict)
    language_distribution: Dict[str, int] = field(default_factory=dict)
    mean_repo_age_years: float = 0.0
    mean_contributors: float = 0.0
    balance_tests: Dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def select_paired_repositories(
    corpus_db: Path,
    repos_per_language: int,
    language: Optional[str] = None,
) -> list[dict]:
    """Select repositories for the paired study from the existing corpus."""
    with db_session(corpus_db) as conn:
        rows = conn.execute("""
            SELECT id, github_id, full_name, language, stars, forks,
                   description, topics, created_at, pushed_at, clone_url, status,
                   num_contributors, num_test_files
            FROM repositories
            WHERE status IN ('analysed', 'cloned')
            ORDER BY language, created_at ASC, id ASC
            """).fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        repo = dict(row)
        if language and repo["language"] != language:
            continue
        grouped.setdefault(repo["language"], []).append(repo)

    selected: list[dict] = []
    for lang in ([language] if language else list(LANGUAGE_CONFIGS.keys())):
        if not lang:
            continue
        selected.extend(grouped.get(lang, [])[:repos_per_language])

    return selected


class PairedStudyCollector:
    """Collect commit-level paired observations within the same repository."""

    def __init__(
        self,
        corpus_db_path: Path,
        clones_dir: Path = CLONES_DIR,
        output_db: Path | None = None,
    ):
        self.corpus_db_path = Path(corpus_db_path)
        self.clones_dir = Path(clones_dir)
        self.output_db = (
            Path(output_db) if output_db else (DATA_DIR / "paired-study.db")
        )
        self.scanner = Tier1RepositoryScanner(corpus_db_path=self.corpus_db_path)

    def _collect_control_variables(self, repo: dict) -> dict:
        """Collect control variables (domain, star_tier, repo_age_years) for a repository."""
        domain = classify_domain(repo.get("topics"), repo.get("description"))
        star_tier = compute_star_tier(repo.get("stars"))
        repo_age = compute_repo_age_years(repo.get("created_at"))

        return {
            "domain": domain,
            "star_tier": star_tier,
            "repo_age_years": repo_age,
        }

    def _validate_quality_filters(
        self, repo_path: Path, language: str, repo_name: str
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that repository meets quality criteria.

        Returns: (passes_qc: bool, skip_reason: Optional[str])
        """
        # Note: SEART already filtered for 100 commits and 500 stars,
        # but we validate MIN_TEST_FILES (5) during extraction
        # For now, we accept SEART-filtered repos.
        # Quality filtering happens per-commit during extraction.
        return True, None

    def _compute_chi_square_balance(
        self, agent_counts: Dict[str, int], human_counts: Dict[str, int]
    ) -> dict:
        """
        Compute chi-square test for balance between agent and non-agent distributions.

        Args:
            agent_counts: Dictionary of category -> count for agent commits
            human_counts: Dictionary of category -> count for human commits

        Returns:
            Dict with chi_square, p_value, and status
        """
        try:
            from scipy.stats import chi2_contingency

            # Get all categories
            all_categories = set(agent_counts.keys()) | set(human_counts.keys())

            # Build contingency table: rows = categories, cols = [agent, human]
            agent_vals = [agent_counts.get(cat, 0) for cat in sorted(all_categories)]
            human_vals = [human_counts.get(cat, 0) for cat in sorted(all_categories)]

            # Need at least 2x2 table
            if len(all_categories) < 2 or sum(agent_vals) < 5 or sum(human_vals) < 5:
                return {
                    "chi_square": None,
                    "p_value": None,
                    "status": "insufficient_data",
                    "message": "Not enough data for chi-square test",
                }

            contingency_table = [agent_vals, human_vals]
            chi2, p_val, dof, expected = chi2_contingency(contingency_table)

            status = "balanced" if p_val >= 0.05 else "imbalanced"
            return {
                "chi_square": float(chi2),
                "p_value": float(p_val),
                "status": status,
                "degrees_of_freedom": int(dof),
            }
        except ImportError:
            logger.warning(
                "scipy not available for balance testing; skipping chi-square analysis"
            )
            return {
                "chi_square": None,
                "p_value": None,
                "status": "unavailable",
                "message": "scipy not installed",
            }

    def _check_balance(self, stats: PairedStudyStats) -> dict:
        """
        Check statistical balance between agent and human commits across dimensions.

        Returns: Dictionary with balance test results for language and domain
        """
        # Build agent/human distributions from collected data
        agent_lang = Counter()
        human_lang = Counter()
        agent_domain = Counter()
        human_domain = Counter()

        # We'll populate these during the main collection loop
        # For now, return empty structure
        balance_results = {
            "language_distribution": self._compute_chi_square_balance(
                {}, {}  # Will be populated during run()
            ),
            "domain_distribution": self._compute_chi_square_balance(
                {}, {}  # Will be populated during run()
            ),
        }

        return balance_results

    def run(
        self,
        repos_per_language: int = 50,
        language: Optional[str] = None,
        max_commits_per_role: int = 8,
        seed: int = 42,
    ) -> tuple[PairedStudyStats, Path]:
        _ = seed  # Kept for reproducibility hooks if sampling strategy changes later.
        initialise_db(self.output_db)

        stats = PairedStudyStats()
        selected_repos = select_paired_repositories(
            self.corpus_db_path, repos_per_language, language
        )
        selected_full_names = [repo["full_name"] for repo in selected_repos]
        logger.info(f"Selected {len(selected_repos)} repositories for paired study")

        # Trackers for balance checking
        agent_lang_dist = Counter()
        human_lang_dist = Counter()
        agent_domain_dist = Counter()
        human_domain_dist = Counter()
        repo_ages = []
        repo_contributors = []

        for repo in selected_repos:
            stats.repos_scanned += 1
            repo_name = repo["full_name"]
            language_name = repo["language"]
            repo_path = self.clones_dir / repo_name.replace("/", "__")

            # Collect control variables
            control_vars = self._collect_control_variables(repo)
            domain = control_vars["domain"]
            star_tier = control_vars["star_tier"]
            repo_age = control_vars["repo_age_years"]

            # Track distributions
            stats.domain_distribution[domain] = (
                stats.domain_distribution.get(domain, 0) + 1
            )
            stats.star_tier_distribution[star_tier] = (
                stats.star_tier_distribution.get(star_tier, 0) + 1
            )
            if repo_age is not None:
                repo_ages.append(repo_age)
            if repo.get("num_contributors"):
                repo_contributors.append(repo["num_contributors"])

            # Quality check (SEART repos already filtered for 100 commits, 500 stars)
            passes_qc, skip_reason = self._validate_quality_filters(
                repo_path, language_name, repo_name
            )
            if not passes_qc:
                stats.repos_failed_qc += 1
                stats.qc_skip_reasons[skip_reason] = (
                    stats.qc_skip_reasons.get(skip_reason, 0) + 1
                )
                logger.debug(f"[paired] Skip {repo_name}: QC failed ({skip_reason})")
                continue
            stats.repos_passed_qc += 1

            if not repo_path.exists():
                repo_id, status, commit, skip_reason = clone_repo(
                    repo["id"], repo_name, repo["clone_url"], language_name
                )
                if status != "cloned":
                    logger.debug(f"[paired] Skip {repo_name}: {status} ({skip_reason})")
                    continue

            commit_roles = self.scanner.scan_repo_commit_roles(
                repo_path, start_date=HUMAN_CORPUS_CUTOFF_DATE
            )
            agent_commits = [c for c in commit_roles if c.commit_role == "agent"]
            human_commits = [c for c in commit_roles if c.commit_role == "human"]

            if not agent_commits or not human_commits:
                logger.debug(
                    f"[paired] Skip {repo_name}: agent={len(agent_commits)} human={len(human_commits)}"
                )
                continue

            pair_count = min(
                len(agent_commits), len(human_commits), max_commits_per_role
            )
            if pair_count <= 0:
                continue

            stats.repos_with_pairs += 1
            stats.repos_by_language[language_name] = (
                stats.repos_by_language.get(language_name, 0) + 1
            )

            # Persist repository metadata in the paired dataset.
            with db_session(self.output_db) as conn:
                repo_row, _ = upsert_repository(
                    conn,
                    {
                        "github_id": repo["github_id"],
                        "full_name": repo_name,
                        "language": language_name,
                        "stars": repo.get("stars", 0),
                        "forks": repo.get("forks", 0),
                        "description": repo.get("description", "") or "",
                        "topics": repo.get("topics", "[]") or "[]",
                        "created_at": repo.get("created_at", ""),
                        "pushed_at": repo.get("pushed_at", ""),
                        "clone_url": repo.get("clone_url", ""),
                        "domain": domain,
                        "star_tier": star_tier,
                        "repo_age_years": repo_age,
                        "num_contributors": repo.get("num_contributors", 0),
                    },
                )

                # Match the same number of agent and human commits within the repo.
                paired_commits = [(c, "agent") for c in agent_commits[:pair_count]] + [
                    (c, "human") for c in human_commits[:pair_count]
                ]

                for commit_info, role in paired_commits:
                    fixtures = extract_fixtures_at_commit(
                        repo_path, commit_info.commit_sha, language_name
                    )
                    fixture_count = len(fixtures)
                    mock_usage_count = sum(len(f.get("mocks", [])) for f in fixtures)

                    insert_commit_observation(
                        conn,
                        {
                            "repo_id": repo_row,
                            "commit_sha": commit_info.commit_sha,
                            "commit_role": role,
                            "agent_type": (
                                commit_info.agent_type if role == "agent" else None
                            ),
                            "commit_date": commit_info.commit_date,
                            "fixture_count": fixture_count,
                            "mock_usage_count": mock_usage_count,
                            "test_file_count": len(
                                {f.get("file_path") for f in fixtures}
                            ),
                        },
                    )

                    stats.observations_inserted += 1
                    stats.fixtures_observed += fixture_count
                    stats.mock_usages_observed += mock_usage_count

                    # Track agent type
                    if role == "agent" and commit_info.agent_type:
                        agent_type = commit_info.agent_type
                    elif role == "agent":
                        agent_type = "other"
                    else:
                        agent_type = None

                    if agent_type:
                        stats.agent_type_breakdown[agent_type] = (
                            stats.agent_type_breakdown.get(agent_type, 0) + 1
                        )

                    # Track distributions for balance checking
                    if role == "agent":
                        stats.agent_commits += 1
                        agent_lang_dist[language_name] += 1
                        agent_domain_dist[domain] += 1
                    else:
                        stats.human_commits += 1
                        human_lang_dist[language_name] += 1
                        human_domain_dist[domain] += 1

        # Compute control variable means
        if repo_ages:
            stats.mean_repo_age_years = sum(repo_ages) / len(repo_ages)
        if repo_contributors:
            stats.mean_contributors = sum(repo_contributors) / len(repo_contributors)

        # Compute balance tests
        stats.balance_tests = {
            "language_distribution": self._compute_chi_square_balance(
                dict(agent_lang_dist), dict(human_lang_dist)
            ),
            "domain_distribution": self._compute_chi_square_balance(
                dict(agent_domain_dist), dict(human_domain_dist)
            ),
        }

        # Track language distribution of commits
        stats.language_distribution = {
            "agent": dict(agent_lang_dist),
            "human": dict(human_lang_dist),
        }

        # Generate comprehensive summary
        project_root = Path(__file__).resolve().parents[1]
        output_dir = project_root / "output"
        output_dir.mkdir(exist_ok=True)
        summary_path = (
            output_dir
            / f"paired_study_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        # Build summary with all fields
        summary = {
            "timestamp": datetime.now().isoformat(),
            "methodology": {
                "design": "paired within-repository commit-level comparison",
                "unit_of_analysis": "individual commit",
                "pairing_container": "repository (controls for project-specific confounds)",
                "comparison_type": "agent vs non-agent commits in same repo",
                "statistical_framing": "paired tests (Wilcoxon, Cliff's delta, paired t-test)",
            },
            "parameters": {
                "repos_per_language": repos_per_language,
                "language": language,
                "max_commits_per_role": max_commits_per_role,
                "seart_quality_filters": {
                    "min_commits": 100,
                    "min_stars": 500,
                    "note": "SEART corpus already filtered before collection",
                },
            },
            "data_collection": {
                "timestamp": datetime.now().isoformat(),
                "selected_repositories": selected_full_names,
            },
            "summary_statistics": {
                "sampling": {
                    "repos_scanned": stats.repos_scanned,
                    "repos_passed_qc": stats.repos_passed_qc,
                    "repos_failed_qc": stats.repos_failed_qc,
                    "qc_skip_reasons": dict(stats.qc_skip_reasons),
                    "repos_with_pairs": stats.repos_with_pairs,
                },
                "commit_observations": {
                    "total_observations_inserted": stats.observations_inserted,
                    "agent_commits": stats.agent_commits,
                    "human_commits": stats.human_commits,
                    "pairing_ratio": (
                        stats.agent_commits / stats.human_commits
                        if stats.human_commits > 0
                        else 0
                    ),
                },
                "fixtures_and_mocks": {
                    "total_fixtures_observed": stats.fixtures_observed,
                    "total_mock_usages_observed": stats.mock_usages_observed,
                    "fixtures_per_agent_commit": (
                        stats.fixtures_observed / stats.agent_commits
                        if stats.agent_commits > 0
                        else 0
                    ),
                    "fixtures_per_human_commit": (
                        stats.fixtures_observed / stats.human_commits
                        if stats.human_commits > 0
                        else 0
                    ),
                },
                "repositories_by_language": dict(stats.repos_by_language),
            },
            "control_variables": {
                "domain_distribution": dict(stats.domain_distribution),
                "star_tier_distribution": dict(stats.star_tier_distribution),
                "mean_repo_age_years": float(stats.mean_repo_age_years),
                "mean_contributors": float(stats.mean_contributors),
            },
            "agent_analysis": {
                "agent_type_breakdown": dict(stats.agent_type_breakdown),
                "language_distribution": dict(stats.language_distribution),
            },
            "balance_testing": {
                "language_distribution": dict(
                    stats.balance_tests.get("language_distribution", {})
                ),
                "domain_distribution": dict(
                    stats.balance_tests.get("domain_distribution", {})
                ),
                "interpretation": (
                    "p_value >= 0.05 indicates balanced distribution (no significant difference); "
                    "p_value < 0.05 indicates imbalanced distribution (significant difference detected)"
                ),
            },
            "quality_notes": {
                "seart_filtering": "SEART corpus filtered for 100+ commits and 500+ stars before this collection",
                "within_repo_pairing": "Automatically controls for project-specific confounds",
                "commit_level_analysis": "Statistical tests should use paired test variants (Wilcoxon, paired t-test)",
            },
            "dataset": str(self.output_db),
        }

        with open(summary_path, "w") as handle:
            json.dump(summary, handle, indent=2)

        logger.info(f"Paired study summary written to: {summary_path}")
        return stats, summary_path


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for the paired study collector."""
    parser = argparse.ArgumentParser(
        description="Run the paired within-repository study"
    )
    add_language_arg(parser, LANGUAGE_CONFIGS, "Limit to one language")
    add_repos_per_language_arg(parser, 50, "Repositories per language to consider")
    parser.add_argument(
        "--max-commits-per-role",
        type=int,
        default=8,
        help="Max commits per role to sample per repo",
    )
    args = parser.parse_args(argv)

    collector = PairedStudyCollector(
        corpus_db_path=DATA_DIR / "corpus.db", clones_dir=CLONES_DIR
    )
    stats, summary_path = collector.run(
        repos_per_language=args.repos_per_language,
        language=args.language,
        max_commits_per_role=args.max_commits_per_role,
    )
    logger.info(f"Paired study complete: {stats.to_dict()}")
    logger.info(f"Summary written to: {summary_path}")
    return 0
