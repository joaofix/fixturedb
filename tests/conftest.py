"""
Shared test utilities and fixtures for extractor tests.
"""

import pytest
import tempfile
from pathlib import Path
from collection.detector import extract_fixtures, FixtureResult


@pytest.fixture
def temp_test_file():
    """Create a temporary test file and clean it up after test."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


def create_test_file(language: str, code: str) -> Path:
    """Helper to create a temporary test file with given code."""
    suffix_map = {
        "python": ".py",
        "java": ".java",
        "javascript": ".js",
        "typescript": ".ts",
        "go": ".go",
    }

    suffix = suffix_map.get(language, ".txt")
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(code)
        return Path(f.name)


def extract_and_find_fixtures(
    code: str, language: str, fixture_name: str = None
) -> list[FixtureResult]:
    """
    Helper to extract fixtures from code and optionally filter by name.

    Args:
        code: Source code string
        language: Language key ('python', 'java', etc.)
        fixture_name: Optional name to filter by

    Returns:
        List of FixtureResult objects (or filtered by name)
    """
    temp_file = create_test_file(language, code)
    try:
        extract_result = extract_fixtures(temp_file, language)
        fixtures = extract_result.fixtures  # Extract fixtures list from ExtractResult
        if fixture_name:
            fixtures = [f for f in fixtures if f.name == fixture_name]
        return fixtures
    finally:
        if temp_file.exists():
            temp_file.unlink()


def assert_fixture_detected(
    code: str,
    language: str,
    fixture_name: str,
    fixture_type: str = None,
    scope: str = None,
):
    """Assert that a fixture with given name is detected."""
    fixtures = extract_and_find_fixtures(code, language, fixture_name)
    assert len(fixtures) > 0, f"Fixture '{fixture_name}' not detected in {language}"

    fixture = fixtures[0]
    if fixture_type:
        assert (
            fixture.fixture_type == fixture_type
        ), f"Expected type {fixture_type}, got {fixture.fixture_type}"
    if scope:
        assert fixture.scope == scope, f"Expected scope {scope}, got {fixture.scope}"
    return fixture


def assert_fixture_not_detected(code: str, language: str, fixture_name: str):
    """Assert that a fixture is NOT detected."""
    fixtures = extract_and_find_fixtures(code, language, fixture_name)
    assert len(fixtures) == 0, f"Fixture '{fixture_name}' was detected but shouldn't be"


def assert_fixture_count(code: str, language: str, expected_count: int):
    """Assert the number of detected fixtures."""
    fixtures = extract_and_find_fixtures(code, language)
    assert (
        len(fixtures) == expected_count
    ), f"Expected {expected_count} fixtures, got {len(fixtures)}"


def assert_line_range(fixture: FixtureResult, expected_start: int, expected_end: int):
    """Assert fixture line number range."""
    assert (
        fixture.start_line == expected_start
    ), f"Expected start_line {expected_start}, got {fixture.start_line}"
    assert (
        fixture.end_line == expected_end
    ), f"Expected end_line {expected_end}, got {fixture.end_line}"


def assert_loc(fixture: FixtureResult, expected_loc: int):
    """Assert lines of code count."""
    assert (
        fixture.loc == expected_loc
    ), f"Expected {expected_loc} LOC, got {fixture.loc}"


def assert_fixture_metrics(
    fixture: FixtureResult,
    min_complexity: int = None,
    max_complexity: int = None,
    num_parameters: int = None,
    min_objects_instantiated: int = None,
    max_objects_instantiated: int = None,
    min_external_calls: int = None,
    max_external_calls: int = None,
):
    """Assert fixture metrics.

    Args:
        fixture: FixtureResult to validate
        min_complexity: Minimum cyclomatic complexity (inclusive)
        max_complexity: Maximum cyclomatic complexity (inclusive)
        num_parameters: Exact number of parameters
        min_objects_instantiated: Minimum number of object instantiations (inclusive)
        max_objects_instantiated: Maximum number of object instantiations (inclusive)
        min_external_calls: Minimum number of external calls (inclusive)
        max_external_calls: Maximum number of external calls (inclusive)
    """
    if min_complexity is not None:
        assert (
            fixture.cyclomatic_complexity >= min_complexity
        ), f"Expected complexity >= {min_complexity}, got {fixture.cyclomatic_complexity}"

    if max_complexity is not None:
        assert (
            fixture.cyclomatic_complexity <= max_complexity
        ), f"Expected complexity <= {max_complexity}, got {fixture.cyclomatic_complexity}"

    if num_parameters is not None:
        assert (
            fixture.num_parameters == num_parameters
        ), f"Expected {num_parameters} parameters, got {fixture.num_parameters}"

    if min_objects_instantiated is not None:
        assert (
            fixture.num_objects_instantiated >= min_objects_instantiated
        ), f"Expected objects >= {min_objects_instantiated}, got {fixture.num_objects_instantiated}"

    if max_objects_instantiated is not None:
        assert (
            fixture.num_objects_instantiated <= max_objects_instantiated
        ), f"Expected objects <= {max_objects_instantiated}, got {fixture.num_objects_instantiated}"

    if min_external_calls is not None:
        assert (
            fixture.num_external_calls >= min_external_calls
        ), f"Expected num_external_calls >= {min_external_calls}, got {fixture.num_external_calls}"

    if max_external_calls is not None:
        assert (
            fixture.num_external_calls <= max_external_calls
        ), f"Expected num_external_calls <= {max_external_calls}, got {fixture.num_external_calls}"


def assert_fixture_with_type_detected(
    code: str, language: str, fixture_type: str, scope: str = None, count: int = 1
):
    """Assert that a fixture with given type is detected (useful for anonymous functions).

    Args:
        code: Source code string
        language: Language key ('python', 'java', etc.)
        fixture_type: Expected fixture type (e.g., 'before_each', 'mocha_before')
        scope: Optional expected scope
        count: Expected number of fixtures with this type (default 1)

    Returns:
        List of matching FixtureResult objects
    """
    fixtures = extract_and_find_fixtures(code, language)
    matching = [f for f in fixtures if f.fixture_type == fixture_type]
    assert (
        len(matching) == count
    ), f"Expected {count} fixture(s) with type '{fixture_type}', found {len(matching)}"

    if scope:
        for fixture in matching:
            assert (
                fixture.scope == scope
            ), f"Expected scope {scope}, got {fixture.scope}"

    return matching[0] if count == 1 else matching


# ==================== FixtureDB Split Implementation Fixtures ====================


@pytest.fixture
def temp_clones_directory():
    """Create a temporary clones directory with mock repositories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        clones_dir = Path(tmpdir) / "clones"
        clones_dir.mkdir()

        # Create 5 mock repositories
        for i in range(5):
            repo_dir = clones_dir / f"repo_{i}"
            repo_dir.mkdir()

            # Add some agent files to first 3 repos
            if i < 3:
                (repo_dir / ".cursorrules").touch()

            # Create basic git structure (init repo)
            (repo_dir / ".git").mkdir(exist_ok=True)

        yield clones_dir


@pytest.fixture
def temp_database():
    """Create a temporary SQLite database for testing."""
    import sqlite3

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create basic schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                fixture_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                scope TEXT,
                file_id INTEGER,
                repo_id INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_files (
                file_id INTEGER PRIMARY KEY,
                repo_id INTEGER,
                file_path TEXT,
                language TEXT
            )
        """)

        conn.commit()
        conn.close()

        yield db_path


@pytest.fixture
def sample_agent_commits():
    """Provide sample agent commit data for testing."""
    return {
        "repo_1": {
            "claude": [
                "abc123def456",
                "ghi789jkl012",
            ],
            "copilot": ["mno345pqr678"],
        },
        "repo_2": {
            "cursor": ["stu901vwx234"],
        },
    }


@pytest.fixture
def sample_fixture_data():
    """Provide sample fixture data for testing."""
    return [
        {
            "fixture_id": 1,
            "name": "test_client",
            "type": "pytest.fixture",
            "scope": "function",
            "file_id": 1,
            "repo_id": 1,
        },
        {
            "fixture_id": 2,
            "name": "setup_database",
            "type": "pytest.fixture",
            "scope": "module",
            "file_id": 1,
            "repo_id": 1,
        },
        {
            "fixture_id": 3,
            "name": "mock_config",
            "type": "pytest.fixture",
            "scope": "function",
            "file_id": 2,
            "repo_id": 2,
        },
    ]


@pytest.fixture
def sample_fixture_distribution():
    """Provide sample fixture distribution by type."""
    return {
        "pytest.fixture": {
            "count": 700,
            "repos": 150,
        },
        "unittest.TestCase": {
            "count": 200,
            "repos": 50,
        },
        "jasmine.describe": {
            "count": 100,
            "repos": 30,
        },
    }


@pytest.fixture
def mock_git_output():
    """Provide sample git log output for testing."""
    return (
        "abc123def456|2023-01-15|John Doe <john@example.com>|Fix bug\n"
        "Co-authored-by: claude\n"
        "---\n"
        "ghi789jkl012|2023-02-20|Jane Smith <jane@example.com>|Add feature\n"
        "Co-authored-by: copilot <copilot@github.com>\n"
        "---\n"
        "mno345pqr678|2023-03-10|Bob Johnson <bob@example.com>|Refactor\n"
        "---\n"
    )


def create_mock_agent_config_file(repo_dir: Path, agent_type: str) -> Path:
    """Create a mock agent configuration file in a repository."""
    config_map = {
        "claude": ".cursorrules",
        "cursor": ".cursorrules",
        "copilot": ".copilot",
        "aider": ".aider.conf",
        "devin": ".devin.config",
    }

    config_file = repo_dir / config_map.get(agent_type, ".agent.config")
    config_file.write_text(f"# Mock {agent_type} configuration")

    return config_file


def create_mock_fixture_file(repo_dir: Path, fixtures_count: int = 3) -> Path:
    """Create a mock Python test file with fixtures."""
    test_file = repo_dir / "tests" / "conftest.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    fixture_code = "import pytest\n\n"
    for i in range(fixtures_count):
        fixture_code += f"""
@pytest.fixture
def fixture_{i}():
    \"\"\"Test fixture {i}.\"\"\"
    return {i}

"""

    test_file.write_text(fixture_code)
    return test_file


def create_mock_agent_commit_data(
    agent_type: str = "claude",
    commit_count: int = 5,
) -> dict:
    """Create mock agent commit data."""
    commits = {}
    for i in range(commit_count):
        commits[f"repo_{i}"] = {agent_type: [f"commit_{i}_{j}" for j in range(2)]}

    return commits
