#!/usr/bin/env python3
"""
Dry-run script for the full agent → human fixture collection pipeline.

Generates minimal test CSVs from known repos with agent test-commit activity,
then runs agent fixture extraction (which produces agent_fixture_repos.csv),
then runs human fixture extraction (which reads the agent-produced repo list).

Usage:
    python scripts/dry_run.py [--language python] [--repos-per-language 3] [--workers 1]

Requirements:
    - Valid GITHUB_TOKEN in .env (for cloning)
    - The repos must be public and accessible
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

# ── Known repos with confirmed agent test-commit activity ──────────────────
# These repos were verified earlier to have agent-authored test commits in
# github-search-agent/tests_commits/*.csv before those files were cleaned.
# Using these as dry-run candidates.
KNOWN_AGENT_REPOS = {
    "python": [
        {
            "repo_name": "trustedsec/hate_crack",
            "stars": 600,
            "clone_url": "https://github.com/trustedsec/hate_crack.git",
        },
        {
            "repo_name": "andfanilo/streamlit-echarts",
            "stars": 1500,
            "clone_url": "https://github.com/andfanilo/streamlit-echarts.git",
        },
        {
            "repo_name": "michaelchu/optopsy",
            "stars": 3800,
            "clone_url": "https://github.com/michaelchu/optopsy.git",
        },
    ],
    "javascript": [
        {
            "repo_name": "goldbergyoni/nodebestpractices",
            "stars": 105000,
            "clone_url": "https://github.com/goldbergyoni/nodebestpractices.git",
        },
    ],
    "typescript": [
        {
            "repo_name": "calcom/cal.com",
            "stars": 35000,
            "clone_url": "https://github.com/calcom/cal.com.git",
        },
    ],
    "java": [
        {
            "repo_name": "iluwatar/java-design-patterns",
            "stars": 92000,
            "clone_url": "https://github.com/iluwatar/java-design-patterns.git",
        },
    ],
}


def generate_dry_run_csvs(output_dir: Path, language: str, repos_per_language: int):
    """Generate minimal repo-QC and commit-QC CSVs for the dry run."""
    output_dir.mkdir(parents=True, exist_ok=True)

    repos = KNOWN_AGENT_REPOS.get(language, [])[:repos_per_language]
    if not repos:
        print(f"  No known repos for language {language}, skipping CSV generation")
        return

    # ── agent_repo_qc.csv ──
    repo_rows = []
    for r in repos:
        repo_rows.append(
            {
                "repo_name": r["repo_name"],
                "full_name": r["repo_name"],
                "language": language,
                "stars": r["stars"],
                "forks": 0,
                "num_contributors": 10,
                "clone_url": r["clone_url"],
                "has_agent_config": "1",
            }
        )

    repo_csv = output_dir / f"{language}_agent_repo_qc.csv"
    with open(repo_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=repo_rows[0].keys())
        writer.writeheader()
        writer.writerows(repo_rows)
    print(f"  Generated {repo_csv} ({len(repo_rows)} repos)")

    # ── agent_commit_qc.csv (minimal — will be scanned by git log at runtime) ──
    # The AgentCorpusCollector uses commits_by_repo for commit metadata, but
    # the actual scanning of commits for test-file modifications happens via
    # git commands. We supply empty commit CSVs; the collector will scan the
    # cloned repos itself. For backwards compatibility, write them anyway.
    commit_csv = output_dir / f"{language}_agent_commit_qc.csv"
    with open(commit_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "repo_name",
                "commit_sha",
                "agent_type",
                "commit_date",
                "author_name",
                "author_email",
                "language",
                "clone_url",
                "processed_at",
            ],
        )
        writer.writeheader()
    print(f"  Generated {commit_csv} (empty — commits will be detected at runtime)")


def run_agent_extraction(
    language: str,
    repos_per_language: int,
    repo_qc_dir: Path,
    output_db: Path,
    workers: int,
):
    """Run the agent corpus collector."""
    print(f"\n{'=' * 60}")
    print(f"STEP 1: Agent fixture extraction [{language}]")
    print(f"{'=' * 60}")

    cmd = [
        sys.executable,
        "-m",
        "collection.agent_corpus",
        "--language",
        language,
        "--repos-per-language",
        str(repos_per_language),
        "--output-db" if output_db else "",
    ]
    if output_db:
        cmd.extend([str(output_db)])
    else:
        cmd = [c for c in cmd if c]

    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parents[1]))
    if result.returncode != 0:
        print(f"  Agent extraction failed with exit code {result.returncode}")
        return False

    # Check that the fixtures-from-agents/repos directory was created
    fixture_list_dir = repo_qc_dir / "fixtures-from-agents"
    expected_csv = fixture_list_dir / "repos" / f"{language}_agent_fixture_repos.csv"
    if expected_csv.exists():
        with open(expected_csv, "r") as f:
            count = sum(1 for _ in f) - 1  # minus header
        print(f"  ✓ Agent fixture repo list written: {expected_csv} ({count} repos)")
    else:
        print(f"  ⚠ Agent fixture repo list NOT found at {expected_csv}")
        print(f"    (This is OK if no repos produced agent fixtures)")

    return True


def run_human_extraction(
    language: str,
    repos_per_language: int,
    repo_qc_dir: Path,
    output_db: Path,
    workers: int,
):
    """Run the human corpus collector (test-commit CSV step + fixture extraction)."""
    print(f"\n{'=' * 60}")
    print(f"STEP 2: Human test-commit collection [{language}]")
    print(f"{'=' * 60}")

    test_commits_out = Path(repo_qc_dir) / f"{language}_human_test_commit_qc.csv"

    # Step 2a: Write human test-commit CSVs
    cmd = [
        sys.executable,
        "-m",
        "collection.human_corpus",
        "--corpus-db",
        str(output_db),
        "--repo-dir",
        str(repo_qc_dir),
        "--language",
        language,
        "--test-commits-csv",
        str(repo_qc_dir),
        "--only-write-test-commits",
    ]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parents[1]))
    if result.returncode != 0:
        print(
            f"  Human test-commit collection failed with exit code {result.returncode}"
        )
        return False

    # Step 2b: Extract human fixtures
    print(f"\n{'=' * 60}")
    print(f"STEP 3: Human fixture extraction [{language}]")
    print(f"{'=' * 60}")
    cmd2 = [
        sys.executable,
        "-m",
        "collection.human_corpus",
        "--corpus-db",
        str(output_db),
        "--repo-dir",
        str(repo_qc_dir),
        "--language",
        language,
        "--workers",
        str(workers),
    ]
    print(f"  Running: {' '.join(cmd2)}")
    result2 = subprocess.run(cmd2, cwd=str(Path(__file__).resolve().parents[1]))
    if result2.returncode != 0:
        print(f"  Human fixture extraction failed with exit code {result2.returncode}")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run the full agent → human fixture collection pipeline"
    )
    parser.add_argument(
        "--language",
        default="python",
        choices=["python", "javascript", "typescript", "java"],
        help="Language to dry-run (default: python)",
    )
    parser.add_argument(
        "--repos-per-language",
        type=int,
        default=3,
        help="Number of repos per language (default: 3)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1)",
    )
    parser.add_argument(
        "--dry-run-dir",
        default="./_dry_run",
        help="Output directory for dry-run CSVs and DB (default: ./_dry_run)",
    )
    parser.add_argument(
        "--skip-clean",
        action="store_true",
        help="Skip cleaning the dry-run directory before starting",
    )

    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    dry_run_dir = project_root / args.dry_run_dir

    if not args.skip_clean and dry_run_dir.exists():
        import shutil

        shutil.rmtree(dry_run_dir, ignore_errors=True)

    dry_run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Dry run started")
    print(f"  Language:          {args.language}")
    print(f"  Repos per language: {args.repos_per_language}")
    print(f"  Workers:           {args.workers}")
    print(f"  Output dir:        {dry_run_dir}")
    print()

    # ── Generate test CSVs ──
    print("Generating dry-run CSVs...")
    generate_dry_run_csvs(dry_run_dir, args.language, args.repos_per_language)

    # ── DB path ──
    output_db = dry_run_dir / "between-group.db"

    # ── Run agent extraction ──
    success = run_agent_extraction(
        language=args.language,
        repos_per_language=args.repos_per_language,
        repo_qc_dir=dry_run_dir,
        output_db=output_db,
        workers=args.workers,
    )
    if not success:
        print("\n⚠ Step 1 (agent) did not complete successfully. Review logs above.")
        # Continue anyway to try human step

    # ── Run human extraction ──
    success2 = run_human_extraction(
        language=args.language,
        repos_per_language=args.repos_per_language,
        repo_qc_dir=dry_run_dir,
        output_db=output_db,
        workers=args.workers,
    )
    if not success2:
        print("\n⚠ Step 2/3 (human) did not complete successfully. Review logs above.")

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print("DRY RUN COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Output DB:     {output_db}")
    print(f"  Agent fixtures: {dry_run_dir}/fixtures-from-agents/")
    print(f"  CSVs:          {dry_run_dir}/")

    # Print DB summary if it exists
    if output_db.exists():
        import sqlite3

        conn = sqlite3.connect(str(output_db))
        repos = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
        fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        test_commits = conn.execute("SELECT COUNT(*) FROM test_commits").fetchone()[0]
        conn.close()
        print(f"\n  DB contents:")
        print(f"    Repositories:  {repos}")
        print(f"    Test commits:  {test_commits}")
        print(f"    Fixtures:      {fixtures}")

    print(f"\n  To resume with more repos, run:")
    print(f"    python scripts/dry_run.py --skip-clean --repos-per-language 5")
    print()


if __name__ == "__main__":
    main()
