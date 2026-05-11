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
