#!/usr/bin/env python3
"""
Build a toy validation dataset for the collection pipeline.

This mirrors the old collection pipeline's toy mode, but uses the new
human-vs-agent methodology. By default it keeps 20 repositories per language.
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .agent_detector import AgentCommitVerifier
from .config import LANGUAGE_CONFIGS, DB_PATH, AGENT_DATASET_START_DATE
from .db import db_session, initialise_db
from .fixture_extractor import Pre2021FixtureExtractor, LLMFixtureExtractor
from .two_tier_agent_collection import Tier1RepositoryScanner


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def select_toy_repositories(corpus_db: Path, repos_per_language: int, language: str | None = None) -> list[dict]:
    """Select a balanced subset of repositories for toy mode."""
    with db_session(corpus_db) as conn:
        rows = conn.execute(
            """
            SELECT id, full_name, language, created_at, status, stars
            FROM repositories
            WHERE status IN ('analysed', 'cloned')
            ORDER BY language, created_at ASC, id ASC
            """
        ).fetchall()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        repo = dict(row)
        if language and repo['language'] != language:
            continue
        grouped[repo['language']].append(repo)

    selected: list[dict] = []
    language_order = [language] if language else list(LANGUAGE_CONFIGS.keys())

    for lang in language_order:
        if not lang:
            continue
        selected.extend(grouped.get(lang, [])[:repos_per_language])

    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a toy collection dataset")
    parser.add_argument(
        "--language",
        choices=list(LANGUAGE_CONFIGS),
        help="Limit to one language (default: all languages)",
    )
    parser.add_argument(
        "--repos-per-language",
        type=int,
        default=20,
        help="Target repositories per language for toy mode",
    )
    args = parser.parse_args(argv)

    project_root = Path(__file__).parent
    clones_dir = project_root / 'clones'
    corpus_db = project_root / 'data' / 'corpus.db'
    human_db = project_root / 'data' / 'fixturedb-human.db'
    llm_db = project_root / 'data' / 'fixturedb-llm.db'
    output_dir = project_root / 'output'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_file = output_dir / f'toy_dataset_summary_{timestamp}.json'

    if not corpus_db.exists():
        logger.error(f"Corpus database not found: {corpus_db}")
        return 1
    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        return 1

    selected_repos = select_toy_repositories(
        corpus_db=corpus_db,
        repos_per_language=args.repos_per_language,
        language=args.language,
    )

    if not selected_repos:
        logger.error("No repositories selected for toy dataset")
        return 1

    selected_full_names = [repo['full_name'] for repo in selected_repos]
    selected_clone_names = [repo['full_name'].replace('/', '__') for repo in selected_repos]

    logger.info("=" * 70)
    logger.info("TOY DATASET: Human vs Agent")
    logger.info("=" * 70)
    logger.info(f"Repositories per language: {args.repos_per_language}")
    logger.info(f"Languages: {args.language or 'all'}")
    logger.info(f"Selected repositories: {len(selected_repos)}")
    logger.info("")

    # Phase 1A: scan selected repos for agent commits
    scanner = Tier1RepositoryScanner(corpus_db_path=corpus_db)
    phase_1a = {
        'tier': 1,
        'repos_scanned': 0,
        'repos_with_agent_commits': 0,
        'total_agent_commits': 0,
        'agents_by_type': {},
        'repo_details': {},
        'timestamp': datetime.now().isoformat(),
    }

    for repo in selected_repos:
        clone_name = repo['full_name'].replace('/', '__')
        repo_path = clones_dir / clone_name
        if not repo_path.exists():
            logger.debug(f"Repo not found on disk: {clone_name}")
            continue

        agent_commits = scanner.scan_repo_for_agent_commits(repo_path)
        phase_1a['repos_scanned'] += 1
        if agent_commits:
            phase_1a['repos_with_agent_commits'] += 1
            phase_1a['total_agent_commits'] += len(agent_commits)
            for commit in agent_commits:
                phase_1a['agents_by_type'][commit.agent_type] = (
                    phase_1a['agents_by_type'].get(commit.agent_type, 0) + 1
                )
            phase_1a['repo_details'][repo['full_name']] = {
                'repo_id': repo['id'],
                'commits': [
                    {
                        'sha': commit.commit_sha,
                        'agent_type': commit.agent_type,
                        'date': commit.commit_date,
                        'author': commit.author_name,
                    }
                    for commit in agent_commits
                ],
            }

    phase_1a_file = output_dir / f'toy_phase_1a_agent_commits_{timestamp}.json'
    with open(phase_1a_file, 'w') as f:
        json.dump(phase_1a, f, indent=2)

    # Phase 1B: verify agent commits in the same toy subset
    verifier = AgentCommitVerifier(clones_dir=clones_dir)
    verified_results = verifier.verify_all(selected_clone_names, start_date=AGENT_DATASET_START_DATE, show_progress=True)
    verified_agent_commits = {
        repo_name: result.agent_commits
        for repo_name, result in verified_results.items()
    }

    phase_1b_file = output_dir / f'toy_phase_1b_verified_agents_{timestamp}.json'
    with open(phase_1b_file, 'w') as f:
        json.dump(
            {
                'timestamp': datetime.now().isoformat(),
                'repositories': {
                    repo_name: {
                        'agent_commits': result.agent_commits,
                        'total_commits': result.total_agent_commits,
                    }
                    for repo_name, result in verified_results.items()
                },
            },
            f,
            indent=2,
        )

    # Phase 2: extract human fixtures from the same toy repo subset
    initialise_db(human_db)
    human_extractor = Pre2021FixtureExtractor(clones_dir=clones_dir, source_db=corpus_db)
    human_stats = human_extractor.extract_all(show_progress=True, repo_names=selected_full_names)

    # Phase 3: extract agent fixtures and insert with tier labels
    initialise_db(llm_db)
    llm_extractor = LLMFixtureExtractor(clones_dir=clones_dir, source_db=corpus_db)
    llm_stats = llm_extractor.extract_all(verified_agent_commits, show_progress=True)
    inserted_count = llm_extractor.insert_all(llm_db, tier=1)

    summary = {
        'timestamp': datetime.now().isoformat(),
        'repos_per_language': args.repos_per_language,
        'language': args.language,
        'selected_repositories': len(selected_repos),
        'selected_full_names': selected_full_names,
        'phase_1a': phase_1a,
        'phase_2': {
            'total_repositories': human_stats.total_repositories,
            'repositories_with_fixtures': human_stats.repositories_with_fixtures,
            'total_fixtures_extracted': human_stats.total_fixtures_extracted,
        },
        'phase_3': {
            'repositories_with_agent_commits': llm_stats.repositories_with_agent_commits,
            'total_fixtures_extracted': llm_stats.total_fixtures_extracted,
            'fixtures_inserted': inserted_count,
            'completely_added_fixtures': llm_stats.completely_added_fixtures,
            'partially_modified_fixtures': llm_stats.partially_modified_fixtures,
        },
    }

    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    logger.info("")
    logger.info(f"Toy dataset summary written to: {summary_file}")
    logger.info("Toy dataset complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())