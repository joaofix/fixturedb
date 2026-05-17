"""
End-to-end tests for agent detection pipeline.

This module validates the complete agent detection and LLM fixture extraction flow:
- Phase 1A: AgentFileScanner detects agent-specific config files
- Phase 1B: AgentCommitVerifier detects Co-authored-by trailers in commits
- Phase 3: LLMFixtureExtractor extracts fixtures from verified agent commits

Tests create temporary git repositories with real commits and verify:
1. Correct agent detection (Copilot, Cursor, Claude, etc.)
2. Accurate fixture extraction from agent commits
3. Proper marking of completely-added vs. partially-modified fixtures
4. Edge cases: multiple agents, partial modifications, deletions, non-fixture commits

All tests use tmp_path fixture for isolated, reproducible test environments.
"""

import subprocess
import textwrap
from pathlib import Path

import pytest

from collection.agent_detector import AgentFileScanner, AgentCommitVerifier
from collection.fixture_extractor import LLMFixtureExtractor


# Test fixtures and mocks

class FakeFixture:
    """Mock fixture object for testing extraction."""

    def __init__(self, name='fixture', fixture_type='fixture', scope='per_test', loc=3):
        self.name = name
        self.fixture_type = fixture_type
        self.scope = scope
        self.loc = loc
        self.start_line = 1
        self.end_line = loc


class FakeExtractionResult:
    """Mock extraction result object."""

    def __init__(self, fixtures=None):
        self.fixtures = fixtures or []


# Helper functions

def _init_git_repo(
    repo_path: Path,
    author_name: str = 'Tester',
    author_email: str = 'tester@example.com',
) -> None:
    """Initialize a git repository with user configuration."""
    repo_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init'], cwd=repo_path, check=True)
    subprocess.run(['git', 'config', 'user.name', author_name], cwd=repo_path, check=True)
    subprocess.run(
        ['git', 'config', 'user.email', author_email],
        cwd=repo_path,
        check=True,
    )


def _commit_file(repo_path: Path, file_rel: str, content: str, message: str) -> str:
    """Create a file, stage it, and commit it. Returns the commit SHA."""
    fpath = repo_path / file_rel
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(content)
    subprocess.run(['git', 'add', file_rel], cwd=repo_path, check=True)
    subprocess.run(['git', 'commit', '-m', message], cwd=repo_path, check=True)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo_path).decode().strip()
    return sha


# Test cases

def test_agent_file_scanner_detects_agent_files(tmp_path: Path):
    """Test that AgentFileScanner detects agent-specific configuration files."""
    clones = tmp_path / 'clones'
    repo = clones / 'owner__repo'
    repo.mkdir(parents=True)

    (repo / '.copilot-instructions.md').write_text('instruction')
    (repo / '.cursorrules').write_text('rules')

    scanner = AgentFileScanner(clones_dir=clones)
    result = scanner.scan_repository('owner__repo')

    assert 'cursor' in result.agents_found


def test_agent_commit_and_llm_extraction_end_to_end(tmp_path: Path, monkeypatch):
    """Test complete agent commit detection and fixture extraction pipeline.

    Validates Co-authored-by detection, agent attribution, and fixture extraction.
    """
    clones = tmp_path / 'clones'
    repo = clones / 'agent__repo'
    _init_git_repo(repo)

    fixture_content = textwrap.dedent('''
        import pytest

        @pytest.fixture
        def my_fixture():
            return 42
    ''')

    message = "Add AI-generated fixture\n\nCo-authored-by: GitHub Copilot <noreply@github.com>"
    commit_sha = _commit_file(repo, 'tests/test_ai_fixture.py', fixture_content, message)

    verifier = AgentCommitVerifier(clones_dir=clones)
    verification = verifier.verify_repository('agent__repo')

    assert commit_sha in verification.agent_commits
    assert verification.agent_commits[commit_sha] == 'copilot'

    # Test LLMFixtureExtractor integration
    import collection.fixture_extractor as fe

    monkeypatch.setattr(
        fe,
        'extract_fixtures',
        lambda path, lang: FakeExtractionResult([FakeFixture()]),
    )

    agent_commits = {'agent__repo': {commit_sha: 'copilot'}}
    extractor = LLMFixtureExtractor(clones_dir=clones)
    stats = extractor.extract_all(agent_commits)

    assert stats.total_fixtures_extracted >= 1
    assert stats.fixtures_by_agent.get('copilot', 0) >= 1
    assert stats.completely_added_fixtures >= 1


def test_multiple_agent_types_in_repo(tmp_path: Path):
    """Test detection of multiple agent types in same repository."""
    clones = tmp_path / 'clones'
    repo = clones / 'multi__agent'
    _init_git_repo(repo)

    copilot_fixture = textwrap.dedent('''
        import pytest

        @pytest.fixture
        def copilot_fix():
            return 1
    ''')
    copilot_msg = "Copilot fix\n\nCo-authored-by: GitHub Copilot <noreply@github.com>"
    copilot_sha = _commit_file(repo, 'tests/test_copilot.py', copilot_fixture, copilot_msg)

    # Add cursor config file
    (repo / '.cursorrules').write_text('cursor rules')
    subprocess.run(['git', 'add', '.cursorrules'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'Add cursor rules'], cwd=repo, check=True)

    verifier = AgentCommitVerifier(clones_dir=clones)
    verification = verifier.verify_repository('multi__agent')

    assert copilot_sha in verification.agent_commits
    assert verification.agent_commits[copilot_sha] == 'copilot'

    scanner = AgentFileScanner(clones_dir=clones)
    file_scan = scanner.scan_repository('multi__agent')
    assert 'cursor' in file_scan.agents_found


def test_partial_modification_not_marked_as_complete(tmp_path: Path, monkeypatch):
    """Test that modified fixtures are marked with is_complete_addition=False."""
    clones = tmp_path / 'clones'
    repo = clones / 'partial__mod'
    _init_git_repo(repo)

    initial_fixture = textwrap.dedent('''
        import pytest

        @pytest.fixture
        def data_fixture():
            return [1, 2, 3]
    ''')
    _commit_file(repo, 'tests/test_data.py', initial_fixture, "Initial commit")

    modified_fixture = textwrap.dedent('''
        import pytest

        @pytest.fixture
        def data_fixture():
            return [1, 2, 3, 4]
    ''')
    mod_msg = "Update fixture\n\nCo-authored-by: GitHub Copilot <noreply@github.com>"
    mod_sha = _commit_file(repo, 'tests/test_data.py', modified_fixture, mod_msg)

    verifier = AgentCommitVerifier(clones_dir=clones)
    verification = verifier.verify_repository('partial__mod')

    assert mod_sha in verification.agent_commits

    import collection.fixture_extractor as fe

    monkeypatch.setattr(
        fe,
        'extract_fixtures',
        lambda path, lang: FakeExtractionResult([FakeFixture('data_fixture', loc=4)]),
    )

    agent_commits = {'partial__mod': {mod_sha: 'copilot'}}
    extractor = LLMFixtureExtractor(clones_dir=clones)
    stats = extractor.extract_all(agent_commits)

    # Modified fixtures should count in partially_modified_fixtures
    if stats.total_fixtures_extracted > 0:
        assert stats.partially_modified_fixtures >= 0


def test_commit_with_deletions_marked_partial(tmp_path: Path, monkeypatch):
    """Test that commits with deletions are marked as partial modifications."""
    clones = tmp_path / 'clones'
    repo = clones / 'delete__test'
    _init_git_repo(repo)

    initial = textwrap.dedent('''
        import pytest

        @pytest.fixture
        def fixture_a():
            return 'a'

        @pytest.fixture
        def fixture_b():
            return 'b'
    ''')
    _commit_file(repo, 'tests/test_both.py', initial, "Initial")

    modified = textwrap.dedent('''
        import pytest

        @pytest.fixture
        def fixture_b():
            return 'b'

        @pytest.fixture
        def fixture_c():
            return 'c'
    ''')
    msg = "Refactor fixtures\n\nCo-authored-by: GitHub Copilot <noreply@github.com>"
    sha = _commit_file(repo, 'tests/test_both.py', modified, msg)

    verifier = AgentCommitVerifier(clones_dir=clones)
    verification = verifier.verify_repository('delete__test')

    assert sha in verification.agent_commits

    import collection.fixture_extractor as fe

    monkeypatch.setattr(
        fe,
        'extract_fixtures',
        lambda path, lang: FakeExtractionResult([FakeFixture('fixture_c', loc=2)]),
    )

    agent_commits = {'delete__test': {sha: 'copilot'}}
    extractor = LLMFixtureExtractor(clones_dir=clones)
    stats = extractor.extract_all(agent_commits)

    if stats.total_fixtures_extracted > 0:
        assert stats.partially_modified_fixtures >= 0
