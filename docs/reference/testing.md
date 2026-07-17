# Testing Strategy and Execution

This document describes the comprehensive test suite for FixtureDB, including test organization, how to run tests, and guidelines for creating new tests.

## Test Overview

The test suite validates the **fixture extraction module** (`collection/detector.py`), which uses Tree-sitter ASTs to detect test fixtures, plus the rest of the collection pipeline (agent detection, dataset collectors, sampling, dedup). 431 test files across `tests/` as of this writing.

**Coverage:**
- **Languages covered**: Python, Java, JavaScript, TypeScript (Go patterns exist for structural parity but are dead code — out of this study's scope; see "Mock Detection" below)
- **Test framework**: pytest with custom assertion helpers (`tests/conftest.py`)

## Test Organization

### Directory Structure

The fixture-detector test categories described below live under `tests/collection/`,
alongside per-module unit tests for the rest of the `collection/` package
(agent detection, dataset collectors, sampling, dedup, etc.). Top-level `tests/`
also has `between_group/` (agent/human corpus + comparison tests), `paired/`
(legacy paired-collection tests), and `eda/` (exploratory-analysis scripts).

```
tests/
├── conftest.py                      # Shared pytest fixtures and helpers
├── TEST_PLAN.md                     # Test strategy document
├── test_*.py                        # Module-level tests (clone manager, sampling, db, ...)
├── between_group/                   # Agent/human corpus + between-group comparison tests
├── paired/                          # Legacy paired-collection tests
├── eda/                             # Exploratory data-analysis scripts
├── fixtures/                        # Static test data (see fixtures/README.md)
└── collection/                      # Per-module tests for collection/, including:
    ├── test_extractor_unit/         # Category 1: small-snippet detection unit tests
    │   ├── test_python_fixtures.py
    │   ├── test_java_fixtures.py
    │   ├── test_javascript_fixtures.py
    │   ├── test_typescript_fixtures.py
    │   └── test_go_fixtures.py      # Skipped: Go isn't in this study's language scope
    ├── test_extractor_metadata/     # Category 2: metadata accuracy
    │   ├── test_line_numbers.py
    │   ├── test_fixture_types_and_scopes.py
    │   ├── test_fixture_dependencies.py
    │   ├── test_new_metrics.py
    │   └── test_object_instantiations.py
    ├── test_extractor_edge_cases/   # Category 3: edge-case robustness
    │   └── test_edge_cases.py
    ├── test_mock_detection/         # Category 4: mock framework patterns
    │   ├── test_mock_patterns.py    # Cross-language + false-positive/negative checks
    │   ├── test_mock_pattern_catalog_coverage.py
    │   ├── test_python_mock_patterns.py
    │   ├── test_java_mock_patterns.py
    │   ├── test_javascript_mock_patterns.py
    │   ├── test_typescript_mock_patterns.py
    │   └── test_go_mock_patterns.py # Skipped: Go isn't in this study's language scope
    ├── test_integration/            # Category 5: realistic fixtures
    │   ├── test_python_realistic_fixtures.py
    │   ├── test_java_realistic_fixtures.py
    │   ├── test_javascript_realistic_fixtures.py
    │   ├── test_typescript_realistic_fixtures.py
    │   ├── test_realistic_fixtures.py
    │   └── test_go_realistic_fixtures.py  # Skipped: same reason as above
    └── test_*.py                    # Per-module tests: agent detection, dataset
                                      # collectors (A/B/C), dedup, sampling, CLI, ...
```

## Test Categories

**1. Unit Tests** — Small code snippets (1-10 lines). Validate fixture detection and scope classification across all languages.

**2. Metadata Tests** — Line numbers, LOC, fixture type, scope, complexity metrics (cyclomatic, cognitive), code metrics (parameters, objects instantiated, I/O calls), fixture dependency detection and scope propagation (pytest only — see [Metrics Reference § fixture_dependencies](../architecture/metrics-reference.md#fixture_dependencies-pythonpytest-only)).

**3. Edge Cases** — Large fixtures (100+ lines), deep nesting, false positive prevention, unicode, special characters, indentation variations, empty fixtures, malformed code.

**4. Mock Detection**

**Scope:** Mock framework identification and test-double category
classification (`dummy`/`stub`/`spy`/`mock`/`fake`, per Meszaros), across
languages. See
[Fixture Detection Logic § Mock Detection](../architecture/detection.md#mock-detection)
for the full methodology and
[collection/heuristics/feature_extraction_patterns.yaml](../../collection/heuristics/feature_extraction_patterns.yaml)
for the exact pattern/framework/category catalog (30 patterns, 11
frameworks).

**What they test:**
- **Python**: `unittest.mock` (`patch`/`patch.object`, bare and `mock.`-qualified; `Mock`/`MagicMock`/`AsyncMock`; `create_autospec`), `pytest-mock` (`mocker.patch`/`mocker.patch.object`), pytest's built-in `monkeypatch`
- **Java**: Mockito, EasyMock, MockK — **not** PowerMock (a documented exclusion, not detected)
- **JavaScript**: Jest (`fn`/`spyOn`/`mock`/`mocked`/`createMockFromModule`), Sinon (`stub`/`spy`/`mock`/`fake`/`replace`/`createStubInstance`)
- **TypeScript**: Same Jest/Sinon patterns, plus Vitest (`vi.fn`/`vi.mock`)
- **Go**: patterns exist for parity (`gomock`, `testify`) but are unreachable — Go detection is dead code, not in this study's scope; `test_go_mock_patterns.py` is skipped accordingly

Every test in this category asserts on `fixture.mocks` directly (framework,
category, target_identifier) rather than just that the surrounding fixture
was extracted — a fixture can be detected correctly while its mock usage
inside is silently missed, which is how several real gaps were originally
found (see `mock_patterns_excluded` in the YAML catalog for what's still
knowingly unhandled).

### 5. Integration Tests

**Scope:** Realistic, multi-language test code

**What they test:**
- Django TestCase hierarchy (Python)
- JUnit 5 with nested classes (Java)
- Jest with beforeAll/afterAll (JavaScript)
- Type-annotated Jest (TypeScript)
- Implicit vs. explicit setup patterns
- Complex fixture dependencies
- Large test modules with many fixtures

## Running Tests

### Prerequisites

Ensure pytest is installed:

```bash
pip install pytest pytest-cov
```

Or install from updated requirements:

```bash
pip install -r requirements.txt
```

### Quick Start

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_extractor_unit/test_python_fixtures.py -v

# Run a specific test class
pytest tests/test_extractor_unit/test_python_fixtures.py::TestPythonUnittestFixtures -v

# Run a specific test method
pytest tests/test_extractor_unit/test_python_fixtures.py::TestPythonUnittestFixtures::test_setUp_method_detected -v
```

### Running by Category

```bash
# Unit tests for all languages
pytest tests/test_extractor_unit/ -v

# Unit tests for specific language
pytest tests/test_extractor_unit/test_python_fixtures.py -v
pytest tests/test_extractor_unit/test_java_fixtures.py -v

# Metadata tests
pytest tests/test_extractor_metadata/ -v

# Edge case tests
pytest tests/test_extractor_edge_cases/ -v

# Mock detection tests
pytest tests/collection/test_mock_detection/ -v

# Integration tests
pytest tests/test_integration/ -v
```

### Running with Coverage

```bash
# Generate coverage report
pytest tests/ --cov=collection.detector --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

This generates an HTML report showing coverage of `collection/detector.py`.

### Running with Different Options

```bash
# Run tests with detailed output
pytest tests/ -vv

# Run tests with print statements visible
pytest tests/ -v -s

# Run tests and stop on first failure
pytest tests/ -v -x

# Run tests and show slowest 10
pytest tests/ -v --durations=10

# Run tests matching a pattern
pytest tests/ -v -k "python"  # All tests with "python" in name
pytest tests/ -v -k "setUp"   # All tests related to setUp

# Run with parallel execution (if pytest-xdist installed)
pytest tests/ -v -n auto
```

### Collecting Tests (without running)

```bash
# List all available tests
pytest tests/ --collect-only -q

# Count total number of tests
pytest tests/ --collect-only -q | wc -l
```

## Test Helpers (conftest.py)

The `tests/conftest.py` file provides reusable pytest fixtures and assertion helpers:

```python
# Create a temporary test file
create_test_file(language, code)

# Extract fixtures and find specific fixture
extract_and_find_fixtures(code, language)
fixture = extract_and_find_fixtures(code, language, fixture_name='setUp')

# Assertion helpers
assert_fixture_detected(code, language, name)
assert_fixture_not_detected(code, language, name)
assert_fixture_count(code, language, expected_count)
assert_line_range(fixture, start_line, end_line)
assert_loc(fixture, expected_loc)
assert_fixture_metrics(fixture, **kwargs)
```

Example usage:

```python
def test_setUp_detected(self):
    code = """
class Test(unittest.TestCase):
    def setUp(self):
        self.x = 1
"""
    fixture = assert_fixture_detected(code, 'python', 'setUp')
    assert fixture.scope == 'per_test'
    assert_loc(fixture, 1)
```

## Agent Detection Tests

Agent detection (file scanning, commit-trailer/author-identity matching, fixture
completeness marking — see [Agent Detection Methodology](../architecture/agent-detection.md))
is covered across several files under `tests/collection/`, not one single
end-to-end module:

- `test_agent_detection_logic.py` — agent config file scanning, GitHub API
  file-listing helper (retry/rate-limit handling)
- `test_agent_patterns_thorough.py`, `test_agent_patterns_extra.py` — agent
  signature catalog matching (author identity, trailers)
- `test_conventional_commits.py` — commit-trailer parsing
- `test_end_to_end_collection.py` — collector initialization, DB persistence,
  concurrency, error handling for both Dataset A and B collectors
- `tests/between_group/test_agent_corpus.py` — Dataset A's collector, using
  real git repositories in `tmp_path` with `Co-authored-by` trailers

```bash
pytest tests/collection/test_agent_detection_logic.py -v
pytest tests/collection/ -v -k agent
pytest tests/collection/test_agent_detection_logic.py --cov=collection.agent_patterns --cov=collection.agent_signal_primitives --cov-report=term-missing -v
```

## pytest Configuration

The project uses `pyproject.toml` to configure test discovery and execution:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
norecursedirs = ["clones", ".git", "venv", "dist", "build"]
addopts = "-q"
```

### Why the Pytest Configuration is Important

- **Prevents importing external test code**: The `clones/` directory contains hundreds of external repositories with their own tests. Without the pytest configuration in `pyproject.toml`, pytest would try to import and run them, causing dependency and timeout issues.
- **Ensures consistency**: CI/CD and local runs use the same configuration, preventing environment-specific failures.
- **Performance**: Running only project tests instead of external dependencies is ~100x faster.

### Verifying the Pytest Configuration

CI workflows use the shared pytest configuration:

```bash
pytest -q                     # Uses pyproject.toml configuration
pytest --override-ini testpaths=tests  # Alternative: override at runtime
```

## Adding New Tests

### 1. Identify the Category

- **Unit tests**: Single fixture patterns (use `tests/collection/test_extractor_unit/test_<language>_fixtures.py`)
- **Metadata tests**: Fixture metadata accuracy (use `tests/collection/test_extractor_metadata/`)
- **Edge cases**: Unusual patterns (use `tests/collection/test_extractor_edge_cases/`)
- **Mock detection**: Mock framework patterns (use `tests/collection/test_mock_detection/test_<language>_mock_patterns.py`)
- **Integration tests**: Real-world code (use `tests/collection/test_integration/test_<language>_realistic_fixtures.py`)
- **Agent detection**: Agent commit and file detection (use `tests/collection/test_agent_detection_logic.py` or a new file under `tests/collection/`)

### 2. Use Existing Helpers

Import from conftest and use assertion helpers:

```python
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
)

class TestNewFeature:
    def test_example(self):
        code = "..."
        fixture = assert_fixture_detected(code, 'python', 'setUp')
        assert fixture.fixture_type == 'setUp'
```

### 3. Follow Naming Conventions

- **Test class**: `Test<FeatureOrLanguage><Pattern>`
- **Test method**: `test_<what_is_tested>`
- **File name**: `test_<language>_<category>.py`

Example:

```python
class TestPythonAsyncFixtures:
    def test_async_setUp_with_await(self):
        ...
```

### 4. Add Docstrings

```python
def test_setUp_with_parameters(self):
    """setUp method with multiple initialization parameters"""
    code = """..."""
    fixture = assert_fixture_detected(code, 'python', 'setUp')
    assert fixture.fixture_type == 'unittest_setup'  # not the method name itself
    assert fixture.num_parameters >= 2
```

## Common Issues

### ImportError: No module named 'conftest'

Use relative imports:

```python
from ..conftest import assert_fixture_detected  # Correct
from conftest import assert_fixture_detected    # Wrong
```

### Tests not being discovered

Ensure:
- File name starts with `test_`
- Test classes start with `Test`
- Test methods start with `test_`
- `__init__.py` exists in all test subdirectories

### Tests failing because detector not imported

The conftest automatically imports from `collection.detector`. Ensure the module is installed:

```bash
cd /path/to/project
pip install -e .
```

## References

- **Test Plan**: [tests/TEST_PLAN.md](../../tests/TEST_PLAN.md)
- **Detector Implementation**: [collection/detector.py](../../collection/detector.py)
- **FixtureResult Dataclass**: [collection/detector_shared.py](../../collection/detector_shared.py)
- **Pytest Documentation**: https://docs.pytest.org/
