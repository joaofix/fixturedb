"""
Fixture Extraction Module

Handles extraction of fixtures from repositories using different strategies:
- Phase 2: Pre-2021 fixtures (snapshot-based extraction at pinned_commit)
- Phase 3: agent-generated fixtures (commit-by-commit with completeness validation)

This is a slim facade over:
  - commit_checkout.py: repo path resolution, worktree locking, commit checkout
  - diff_purity.py: pure-addition diff gates + DiffLineMap
  - language_utils.py: file-extension-to-language mapping
  - pre2021_fixture_extractor.py: Pre2021FixtureExtractor (Phase 2)
  - agent_fixture_extractor.py: AgentFixtureExtractor (Phase 3)

Only extract_fixtures_at_commit() is defined here — everything else is
re-exported so existing call sites (human_corpus.py, agent_corpus.py,
dataset_c.py, agent_fixture_counter.py, paired_collection.py, and tests)
need no import changes.
"""

from pathlib import Path
from typing import Dict, List

from collection.logging_utils import get_logger

from .agent_fixture_extractor import AgentExtractionStats, AgentFixtureExtractor
from .commit_checkout import _checkout_commit, _repo_worktree_lock, _resolve_repo_path
from .config import DB_PATH
from .detector import extract_fixtures, fixture_result_to_dict
from .diff_purity import (
    DiffLineMap,
    _raw_diff_commit_is_pure_addition,
    _raw_diff_file_is_pure_addition,
    commit_is_pure_addition,
    is_pure_addition,
)
from .pre2021_fixture_extractor import Pre2021ExtractionStats, Pre2021FixtureExtractor

logger = get_logger(__name__)

__all__ = [
    "AgentExtractionStats",
    "AgentFixtureExtractor",
    "DiffLineMap",
    "Pre2021ExtractionStats",
    "Pre2021FixtureExtractor",
    "commit_is_pure_addition",
    "extract_fixtures_at_commit",
    "is_pure_addition",
    "_checkout_commit",
    "_raw_diff_commit_is_pure_addition",
    "_raw_diff_file_is_pure_addition",
    "_resolve_repo_path",
]


def extract_fixtures_at_commit(
    repo_path: Path, commit_sha: str, language: str
) -> List[Dict]:
    """Extract fixtures from a repository at a specific commit.

    This is the commit-level primitive used by the paired study workflow.
    """
    if not Path(repo_path).exists():
        raise RuntimeError(f"Repository not found: {repo_path}")

    with _repo_worktree_lock(repo_path):
        _checkout_commit(repo_path, commit_sha)

        extractor = Pre2021FixtureExtractor(
            clones_dir=repo_path.parent, source_db=DB_PATH
        )
        fixtures: List[Dict] = []

        try:
            test_files = extractor._find_test_files(repo_path, language)

            for test_file in test_files:
                try:
                    result = extract_fixtures(test_file, language)
                    for fixture in result.fixtures:
                        fixtures.append(
                            fixture_result_to_dict(
                                fixture,
                                language=language,
                                file_path=str(test_file.relative_to(repo_path)),
                            )
                        )
                except Exception as exc:
                    logger.debug(f"Failed to extract from {test_file}: {exc}")
        except Exception as exc:
            raise RuntimeError(f"Failed to extract fixtures: {exc}")

    return fixtures
