"""
Human corpus collection for between-group comparison.

Collects human-generated fixtures from the same agent-enabled repositories
used for the agent corpus. Commits are scanned in the same temporal window as
the agent dataset, and only non-AI commits that fully add a fixture are kept.
"""

import argparse
import csv
import hashlib
import json
import logging
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional
from collections import defaultdict

from .config import (
    CLONES_DIR,
    DATA_DIR,
    AGENT_CORPUS_START_DATE,
    LANGUAGE_CONFIGS,
    EXTRACT_WORKERS,
)
from .db import (
    db_session,
    initialise_db,
    upsert_repository,
    insert_test_commit,
)
from .agent_corpus import clone_repo_for_commit_scan
from .fixture_extractor import AgentFixtureExtractor
from .test_commit_utils import write_test_commits_csv
from .agent_commit_detector import Tier1RepositoryScanner
from .agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES
from .corpus_utils import (
    BaseCorpusStats,
    compute_repo_metadata,
    construct_repo_dict,
    generate_corpus_summary,
    persist_repository_and_fixtures,
)

logger = logging.getLogger(__name__)


def _stable_repo_id(full_name: str) -> int:
    """Derive a stable synthetic repository ID from a repository slug."""
    digest = hashlib.md5(full_name.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


@dataclass
class HumanCorpusStats(BaseCorpusStats):
    """Statistics for human corpus collection (inherits from base)."""

    pass


def select_human_corpus_repositories(
    repo_qc_dir: Path,
    repos_per_language: Optional[int] = None,
    language: Optional[str] = None,
) -> list[dict]:
    """
    Select agent-enabled repositories for human corpus collection.

    Queries the repo-QC CSV exports for repositories with agent config files.

    Args:
        repo_qc_dir: Directory containing *_agent_repo_qc.csv files
        repos_per_language: Optional per-language cap. None means include all rows.
        language: Optional filter to single language

    Returns:
        List of repository dicts with required metadata
    """
    # Backwards-compatible behaviour: if a SQLite corpus DB path is provided,
    # query the `repositories` table for pre-2021 repos. Otherwise fall back to
    # reading repo-QC CSV exports in `repo_qc_dir`.
    repo_path = Path(repo_qc_dir)
    selected: list[dict] = []

    if repo_path.exists() and repo_path.is_file():
        # Treat as corpus DB
        import sqlite3

        conn = sqlite3.connect(str(repo_path))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, github_id, full_name, language, stars, forks, description,
                   topics, created_at, pushed_at, clone_url, status, num_contributors, num_test_files
            FROM repositories
            WHERE created_at >= ? AND status IN ('analysed', 'cloned')
            ORDER BY language ASC, created_at ASC
            """,
            (AGENT_CORPUS_START_DATE,),  # Use agent temporal window (post-2023)
        )
        rows = cur.fetchall()
        conn.close()

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            (
                _id,
                github_id,
                full_name,
                lang,
                stars,
                forks,
                description,
                topics,
                created_at,
                pushed_at,
                clone_url,
                status,
                num_contributors,
                num_test_files,
            ) = row

            lang = (lang or "unknown").strip().lower()
            if language and lang != language:
                continue
            if lang not in LANGUAGE_CONFIGS:
                continue

            repo_row = {
                "id": _id,
                "github_id": github_id,
                "full_name": full_name,
                "language": lang,
                "stars": stars,
                "forks": forks,
                "description": description or "",
                "topics": topics or "[]",
                "created_at": created_at or "",
                "pushed_at": pushed_at or "",
                "clone_url": clone_url or f"https://github.com/{full_name}.git",
                "num_contributors": num_contributors or 0,
                "status": status,
            }
            grouped.setdefault(lang, [])
            grouped[lang].append(repo_row)

        for lang in ([language] if language else list(LANGUAGE_CONFIGS.keys())):
            if not lang:
                continue
            lang_repos = grouped.get(lang, [])
            selected.extend(
                lang_repos
                if repos_per_language is None
                else lang_repos[:repos_per_language]
            )

        return selected

    # Fallback: read repo-QC CSVs
    grouped: dict[str, list[dict]] = {}
    # New fallback: accept per-language human test-commit CSVs produced earlier
    # e.g., python_human_test_commit_qc.csv. These contain `repo_name` and
    # `language` columns and can be used to select repositories directly.
    # Increase CSV field size limit to handle very large `test_file_paths` fields
    try:
        csv.field_size_limit(10**7)
    except Exception:
        pass

    for csv_path in sorted(Path(repo_qc_dir).glob("*_human_test_commit_qc.csv")):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name:
                    continue
                if language and lang != language:
                    continue
                repo_row = {
                    "id": _stable_repo_id(repo_name),
                    "github_id": _stable_repo_id(repo_name),
                    "full_name": repo_name,
                    "language": lang,
                    "stars": 0,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "",
                    "pushed_at": "",
                    "clone_url": f"https://github.com/{repo_name}.git",
                    "num_contributors": 0,
                }
                grouped.setdefault(lang, [])
                if repo_name not in {r["full_name"] for r in grouped[lang]}:
                    grouped[lang].append(repo_row)

    for csv_path in sorted(Path(repo_qc_dir).glob("*_agent_repo_qc.csv")):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if str(row.get("has_agent_config") or "").strip().lower() not in {
                    "1",
                    "true",
                }:
                    continue

                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name:
                    continue
                if language and lang != language:
                    continue

                repo_row = {
                    "id": _stable_repo_id(repo_name),
                    "github_id": _stable_repo_id(repo_name),
                    "full_name": repo_name,
                    "language": lang,
                    "stars": int(float(row.get("stars") or 0)),
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "",
                    "pushed_at": "",
                    "clone_url": (
                        row.get("clone_url") or f"https://github.com/{repo_name}.git"
                    ).strip(),
                    "num_contributors": int(float(row.get("num_contributors") or 0)),
                }
                grouped.setdefault(lang, [])
                if repo_name not in {r["full_name"] for r in grouped[lang]}:
                    grouped[lang].append(repo_row)

    for lang in ([language] if language else list(LANGUAGE_CONFIGS.keys())):
        if not lang:
            continue
        lang_repos = grouped.get(lang, [])
        selected.extend(
            lang_repos
            if repos_per_language is None
            else lang_repos[:repos_per_language]
        )

    return selected


class HumanCorpusCollector:
    """Collect human-authored fixtures from agent-enabled repositories."""

    def __init__(
        self,
        corpus_db_path: Path,
        clones_dir: Path = CLONES_DIR,
        output_db: Path | None = None,
        repo_qc_dir: Path | None = None,
        test_commits_csv: Path | None = None,
    ):
        """
        Initialize human corpus collector.

        Args:
            corpus_db_path: Path to source corpus.db (kept for metadata lookups)
            clones_dir: Directory for temporary clones
            output_db: Path to output database (default: data/between-group.db)
            repo_qc_dir: Directory containing *_agent_repo_qc.csv files
        """
        self.corpus_db_path = Path(corpus_db_path)
        self.clones_dir = Path(clones_dir)
        self.output_db = (
            Path(output_db) if output_db else (DATA_DIR / "between-group.db")
        )
        self.test_commits_csv = Path(test_commits_csv) if test_commits_csv else None
        project_root = Path(__file__).resolve().parents[1]
        self.repo_qc_dir = (
            Path(repo_qc_dir) if repo_qc_dir else (project_root / "github-search-agent")
        )

    def _validate_quality_filters(
        self, repo_path: Path, language: str, repo_name: str
    ) -> tuple[bool, Optional[str]]:
        """
        Validate repository meets quality criteria.

        Returns:
            (passes_qc: bool, skip_reason: Optional[str])
        """
        # Count commits in the same window used for agent collection.
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", f"--since={AGENT_CORPUS_START_DATE}"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False, "git_log_failed"
            num_commits = (
                len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
            )
        except Exception as e:
            logger.debug(f"Failed to count commits for {repo_name}: {e}")
            return False, "commit_count_failed"

        if num_commits == 0:
            return False, "no_commits_in_agent_window"

        # Quality threshold checks will happen during extraction
        return True, None

    def _process_human_repository(self, repo: dict) -> dict:
        """Process one repository end-to-end up to, but not including, DB writes."""
        repo_name = repo["full_name"]
        language_name = repo["language"]
        repo_path = self.clones_dir / repo_name.replace("/", "__")

        logger.info(f"[Human Corpus] Processing {repo_name}")

        if repo_path.exists() and (repo_path / ".git" / "shallow").exists():
            shutil.rmtree(repo_path, ignore_errors=True)

        if not repo_path.exists():
            logger.info(
                f"[Human Corpus] Cloning {repo_name} with full history for commit scan..."
            )
            if not clone_repo_for_commit_scan(repo.get("clone_url", ""), repo_path):
                return {
                    "repo_name": repo_name,
                    "language_name": language_name,
                    "status": "clone_failed",
                    "skip_reason": "clone_failed",
                    "test_commit_rows": [],
                    "fixtures": [],
                }

        passes_qc, skip_reason = self._validate_quality_filters(
            repo_path, language_name, repo_name
        )
        if not passes_qc:
            return {
                "repo_name": repo_name,
                "language_name": language_name,
                "status": "qc_failed",
                "skip_reason": skip_reason or "commit_count_failed",
                "test_commit_rows": [],
                "fixtures": [],
            }

        scanner = Tier1RepositoryScanner(self.corpus_db_path)
        extractor = AgentFixtureExtractor(
            clones_dir=self.clones_dir,
            source_db=self.corpus_db_path,
            start_date=AGENT_CORPUS_START_DATE,
        )

        # Compute control variables using shared utility
        metadata = compute_repo_metadata(repo, AGENT_CORPUS_START_DATE)
        domain = metadata["domain"]
        star_tier = metadata["star_tier"]
        repo_age = metadata["repo_age_years"]

        commit_roles = scanner.scan_repo_commit_roles(
            repo_path,
            start_date=AGENT_CORPUS_START_DATE,
            language=language_name,
            detect_test_files=True,
        )

        test_commit_rows = [
            {
                "repo_name": repo_name,
                "commit_sha": commit.commit_sha,
                "commit_role": commit.commit_role,
                "agent_type": commit.agent_type,
                "commit_date": commit.commit_date,
                "language": language_name,
                "test_file_count": len(commit.test_files),
                "test_file_paths": json.dumps(commit.test_files, ensure_ascii=False),
            }
            for commit in commit_roles
            if commit.commit_role == "human" and commit.is_test_commit
        ]

        human_commits = {
            commit.commit_sha: "human"
            for commit in commit_roles
            if commit.commit_role == "human" and commit.is_test_commit
        }

        fixtures = []
        if human_commits:
            logger.info(
                f"[Human Corpus] {repo_name}: scanning {len(human_commits)} human commits"
            )
            fixtures = extractor._extract_from_agent_commits(
                repo_name=repo_name,
                commits=human_commits,
            )
            fixtures = [
                fixture for fixture in fixtures if fixture.get("is_complete_addition")
            ]

        return {
            "repo_name": repo_name,
            "language_name": language_name,
            "status": "ok",
            "skip_reason": None,
            "domain": domain,
            "star_tier": star_tier,
            "repo_age": repo_age,
            "num_contributors": repo.get("num_contributors", 0),
            "repo_data": construct_repo_dict(
                full_name=repo_name,
                language=language_name,
                stars=repo.get("stars", 0),
                forks=repo.get("forks", 0),
                description=repo.get("description", "") or "",
                topics=repo.get("topics", "[]") or "[]",
                created_at=repo.get("created_at", ""),
                pushed_at=repo.get("pushed_at", ""),
                clone_url=repo.get("clone_url", ""),
                github_id=repo.get("github_id"),
                num_contributors=repo.get("num_contributors", 0),
                domain=domain,
                star_tier=star_tier,
                repo_age_years=repo_age,
            ),
            "test_commit_rows": test_commit_rows,
            "fixtures": fixtures,
        }

    def run(
        self,
        repos_per_language: Optional[int] = None,
        language: Optional[str] = None,
        only_write_test_commits: bool = False,
        workers: Optional[int] = None,
        seed: int = 42,
    ) -> tuple[HumanCorpusStats, Path]:
        """
        Collect human corpus with sequential language processing and progress tracking.

        Safe checkpoint: After all repos for a language are processed, CSV is written
        before moving to the next language.

        Args:
            repos_per_language: Optional per-language cap. None means include all rows.
            language: Optional filter to single language
            workers: Optional number of parallel workers. None uses the configured default.
            seed: Random seed (for reproducibility)

        Returns:
            (stats, output_db_path)
        """
        _ = seed  # Kept for reproducibility hooks
        initialise_db(self.output_db)

        workers = max(1, int(workers or EXTRACT_WORKERS))

        stats = HumanCorpusStats()
        all_test_commit_rows: list[dict] = []
        test_commit_rows_by_language: dict[str, list[dict]] = defaultdict(list)
        
        # If running in write-only mode and the repo_qc_dir already contains
        # per-language human test-commit CSVs, copy them to the output and exit.
        if only_write_test_commits:
            existing = list(Path(self.repo_qc_dir).glob("*_human_test_commit_qc.csv"))
            if existing:
                out_dir = Path(self.test_commits_csv)
                # If input and output are the same directory, nothing to do.
                if out_dir.resolve() == Path(self.repo_qc_dir).resolve():
                    logger.info(
                        f"Input and output directory are the same ({out_dir}); skipping copy"
                    )
                    return stats, self.output_db
                out_dir.mkdir(parents=True, exist_ok=True)
                for p in sorted(existing):
                    shutil.copy(p, out_dir / p.name)
                logger.info(
                    f"Copied {len(existing)} human test-commit CSVs to {out_dir}"
                )
                return stats, self.output_db

        selected_repos = select_human_corpus_repositories(
            self.repo_qc_dir, repos_per_language, language
        )

        logger.info(
            f"[Human Corpus] Selected {len(selected_repos)} agent-enabled repositories"
        )
        logger.info(f"[Human Corpus] Using {workers} worker(s)")

        # Group repos by language for sequential processing
        repos_by_language: dict[str, list[dict]] = defaultdict(list)
        for repo in selected_repos:
            lang = repo.get("language", "unknown").lower()
            repos_by_language[lang].append(repo)

        logger.info(
            f"[Human Corpus] Languages to process: {', '.join(sorted(repos_by_language.keys()))}"
        )
        for lang, repos in sorted(repos_by_language.items()):
            logger.info(f"[Human Corpus]   {lang}: {len(repos)} repositories")

        # Trackers for statistics and progress
        repo_ages = []
        repo_contributors = []
        language_progress = {}  # Track per-language progress for logging
        progress_lock = threading.Lock()

        def log_progress():
            """Log progress every 3 minutes."""
            while not hasattr(log_progress, "stop_flag") or not log_progress.stop_flag:
                with progress_lock:
                    completed_total = stats.repos_scanned
                    fixtures_total = stats.fixtures_collected
                    logger.info(
                        f"[Human Corpus Progress] {completed_total} repos scanned, "
                        f"{stats.repos_passed_qc} passed QC, {fixtures_total} fixtures collected"
                    )
                    for lang in sorted(language_progress.keys()):
                        total_repos = language_progress[lang]["total_repos"]
                        completed = language_progress[lang]["completed"]
                        pct = (completed / total_repos * 100) if total_repos > 0 else 0
                        avg_fixtures = (
                            language_progress[lang]["avg_fixtures_per_repo"]
                        )
                        logger.info(
                            f"  {lang}: {completed}/{total_repos} ({pct:.1f}%) "
                            f"~{avg_fixtures:.0f} fixtures/repo"
                        )
                time.sleep(180)  # 3 minutes

        # Start progress logging thread
        log_progress.stop_flag = False
        progress_thread = threading.Thread(target=log_progress, daemon=True)
        progress_thread.start()

        try:
            # Process each language sequentially
            for lang_idx, (current_lang, lang_repos) in enumerate(
                sorted(repos_by_language.items()), 1
            ):
                logger.info(
                    f"[Human Corpus] Processing language {lang_idx}/{len(repos_by_language)}: {current_lang} ({len(lang_repos)} repos)"
                )

                language_progress[current_lang] = {
                    "total_repos": len(lang_repos),
                    "completed": 0,
                    "avg_fixtures_per_repo": 0,
                }

                # Accumulate all results for this language
                lang_results = []
                lang_all_fixtures = []
                lang_test_commit_rows = []

                if workers <= 1:
                    for repo in lang_repos:
                        lang_results.append(self._process_human_repository(repo))
                else:
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        futures = {
                            executor.submit(self._process_human_repository, repo): repo
                            for repo in lang_repos
                        }
                        for future in as_completed(futures):
                            lang_results.append(future.result())

                # Process all results for this language
                for result in lang_results:
                    with progress_lock:
                        stats.repos_scanned += 1
                        language_progress[current_lang]["completed"] += 1

                    repo_name = result["repo_name"]

                    if result["status"] != "ok":
                        stats.record_skip(result.get("skip_reason") or "unknown")
                        logger.debug(
                            f"[Human Corpus] Skip {repo_name}: {result.get('skip_reason')}"
                        )
                        continue

                    stats.repos_passed_qc += 1

                    domain = result["domain"]
                    star_tier = result["star_tier"]
                    repo_age = result["repo_age"]
                    if repo_age is not None:
                        repo_ages.append(repo_age)
                    if result.get("num_contributors"):
                        repo_contributors.append(result["num_contributors"])

                    stats.domain_distribution[domain] = (
                        stats.domain_distribution.get(domain, 0) + 1
                    )
                    stats.star_tier_distribution[star_tier] = (
                        stats.star_tier_distribution.get(star_tier, 0) + 1
                    )

                    repo_data = result["repo_data"]
                    test_commit_rows = result["test_commit_rows"]
                    fixtures = result["fixtures"]

                    # Upsert repository and enrich test commits with repo_id
                    with db_session(self.output_db) as conn:
                        repo_row, _ = upsert_repository(conn, repo_data)

                        # Insert test commits with repo_id
                        for test_commit in test_commit_rows:
                            test_commit["repo_id"] = repo_row
                            insert_test_commit(conn, test_commit)

                    lang_test_commit_rows.extend(test_commit_rows)
                    test_commit_rows_by_language[current_lang].extend(test_commit_rows)
                    stats.test_commits_found += len(test_commit_rows)

                    if fixtures:
                        lang_all_fixtures.append((repo_data, fixtures))
                        stats.repos_by_language[current_lang] = (
                            stats.repos_by_language.get(current_lang, 0) + 1
                        )
                    else:
                        logger.debug(
                            f"[Human Corpus] No complete human fixtures found in {repo_name}"
                        )
                        stats.repos_by_language[current_lang] = (
                            stats.repos_by_language.get(current_lang, 0) + 1
                        )

                    # Clean up clone after extraction is complete
                    repo_path = self.clones_dir / repo_name.replace("/", "__")
                    if repo_path.exists():
                        shutil.rmtree(repo_path, ignore_errors=True)
                        logger.debug(f"[Human Corpus] Cleaned up clone: {repo_name}")

                # SAFE CHECKPOINT: Write all fixtures for this language to CSV before moving to next language
                if lang_all_fixtures:
                    logger.info(
                        f"[Human Corpus] Writing {len(lang_all_fixtures)} repositories' fixtures to CSV for {current_lang}"
                    )
                    fixtures_out_path = (
                        Path(self.repo_qc_dir) / f"{current_lang}_human_fixtures.csv"
                    )
                    for repo_data, fixtures_list in lang_all_fixtures:
                        fixture_count = persist_repository_and_fixtures(
                            self.output_db,
                            repo_data,
                            fixtures_list,
                            out_path=fixtures_out_path,
                            handle_mocks=True,
                        )
                        with progress_lock:
                            stats.fixtures_collected += fixture_count
                            if stats.repos_by_language[current_lang] > 0:
                                language_progress[current_lang][
                                    "avg_fixtures_per_repo"
                                ] = (
                                    stats.fixtures_collected
                                    / stats.repos_by_language[current_lang]
                                )

                    logger.info(
                        f"[Human Corpus] Checkpoint complete for {current_lang}: "
                        f"{stats.fixtures_collected} total fixtures collected"
                    )

        finally:
            # Stop progress logging thread
            log_progress.stop_flag = True
            progress_thread.join(timeout=5)

        # Compute means
        if repo_ages:
            stats.mean_repo_age_years = sum(repo_ages) / len(repo_ages)
        if repo_contributors:
            stats.mean_contributors = sum(repo_contributors) / len(repo_contributors)

        if self.test_commits_csv:
            # If running in "only write test commits" mode and a directory
            # path is provided, write per-language CSVs and skip fixture extraction.
            if only_write_test_commits:
                out_dir = Path(self.test_commits_csv)
                out_dir.mkdir(parents=True, exist_ok=True)
                for lang, rows in test_commit_rows_by_language.items():
                    out_path = out_dir / f"{lang}_human_test_commit_qc.csv"
                    write_test_commits_csv(rows, out_path)
            else:
                write_test_commits_csv(all_test_commit_rows, self.test_commits_csv)

        # Generate summary
        self._generate_summary(stats)

        return stats, self.output_db

    def _generate_summary(self, stats: HumanCorpusStats) -> None:
        """Generate and save human corpus summary."""
        generate_corpus_summary(
            stats=stats,
            corpus_name="human",
            output_db=self.output_db,
            temporal_scope=f"since {AGENT_CORPUS_START_DATE}",
            extra_metadata={
                "dataset_temporal_window": AGENT_CORPUS_START_DATE,
            },
        )


def main(args):
    """CLI entry point for human corpus collection."""
    collector = HumanCorpusCollector(
        corpus_db_path=args.corpus_db,
        output_db=args.output_db,
        repo_qc_dir=args.repo_qc_dir,
    )
    stats, db_path = collector.run(
        repos_per_language=args.repos_per_language,
        language=args.language,
        only_write_test_commits=args.only_write_test_commits,
        workers=args.workers,
    )
    logger.info(
        f"Human corpus collection complete: {stats.fixtures_collected} fixtures in {db_path}"
    )


if __name__ == "__main__":
    # Ensure logging is configured for CLI runs so INFO progress messages are visible
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Collect human corpus from agent-enabled repositories"
    )
    parser.add_argument(
        "--corpus-db",
        type=Path,
        default=DATA_DIR / "corpus.db",
        help="Path to source corpus.db",
    )
    parser.add_argument(
        "--output-db",
        type=Path,
        default=None,
        help="Path to output between-group.db (default: data/between-group.db)",
    )
    parser.add_argument(
        "--repos-per-language",
        type=int,
        default=None,
        help="Number of repos per language (None = all repos)",
    )
    parser.add_argument(
        "--language",
        choices=list(LANGUAGE_CONFIGS.keys()),
        help="Limit to one language",
    )
    parser.add_argument(
        "--test-commits-csv",
        type=Path,
        default=None,
        help="Directory path to write per-language human test-commit CSVs and exit",
    )
    parser.add_argument(
        "--only-write-test-commits",
        action="store_true",
        help="If set, write per-language human test-commit CSVs and skip fixture extraction",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=EXTRACT_WORKERS,
        help="Number of concurrent worker threads for repo processing",
    )
    parser.add_argument(
        "--repo-qc-dir",
        type=Path,
        default=None,
        help="Directory containing repo-QC CSVs or per-language human test-commit CSVs (overrides default)",
    )
    args = parser.parse_args()
    # If user provided a test-commits path, wire it into the collector and run in write-only mode
    if args.test_commits_csv:
        args.test_commits_csv = Path(args.test_commits_csv)
        collector = HumanCorpusCollector(
            corpus_db_path=args.corpus_db,
            output_db=args.output_db,
            test_commits_csv=args.test_commits_csv,
            repo_qc_dir=args.repo_qc_dir,
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            language=args.language,
            only_write_test_commits=True,
            workers=args.workers,
        )
        logger.info(f"Wrote human test-commit CSVs to {args.test_commits_csv}")
    else:
        # Build collector with optional repo_qc_dir and run normally
        collector = HumanCorpusCollector(
            corpus_db_path=args.corpus_db,
            output_db=args.output_db,
            repo_qc_dir=args.repo_qc_dir,
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            language=args.language,
            only_write_test_commits=False,
            workers=args.workers,
        )
        logger.info(
            f"Human corpus collection complete: {stats.fixtures_collected} fixtures in {db_path}"
        )
