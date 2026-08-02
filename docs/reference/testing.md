# Testing Strategy and Execution

This document describes the test suite for FixtureDB: test organization, how to run tests, and guidelines for adding new ones.

## Test Overview

The test suite validates the fixture extraction module (`collection/detector.py`, which uses Tree-sitter ASTs to detect test fixtures) plus the rest of the collection pipeline — agent detection, dataset collectors, sampling, dedup. 431 test files across `tests/` as of this writing.

Languages covered: Python, Java, JavaScript, TypeScript. Go patterns exist for structural parity but are dead code, out of this study's scope (see Mock Detection below). Test framework: pytest, with custom assertion helpers in `tests/conftest.py`.

## Test Organization

The fixture-detector test categories described below live under `tests/collection/`, alongside per-module unit tests for the rest of the `collection/` package (agent detection, dataset collectors, sampling, dedup, etc.). Top-level `tests/` also has `between_group/` (agent/human corpus and comparison tests), `paired/` (legacy paired-collection tests), and `eda/` (exploratory-analysis scripts).

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

1. **Unit tests** — small code snippets (1–10 lines), validating fixture detection and scope classification across all languages.
2. **Metadata tests** — line numbers, LOC, fixture type, scope, complexity metrics (cyclomatic, cognitive), code metrics (parameters, objects instantiated, I/O calls), fixture dependency detection, and scope propagation (pytest only — see [Metrics Reference § fixture_dependencies](../architecture/metrics-reference.md#fixture_dependencies-pythonpytest-only)).
3. **Edge cases** — large fixtures (100+ lines), deep nesting, false positive prevention, unicode, special characters, indentation variations, empty fixtures, malformed code.
4. **Mock detection** — mock framework identification and test-double category classification (`dummy`/`stub`/`spy`/`mock`/`fake`, per Meszaros), across languages. See [Fixture Detection Logic § Mock Detection](../architecture/detection.md#mock-detection) for the full methodology and [feature_extraction_patterns.yaml](../../collection/heuristics/feature_extraction_patterns.yaml) for the exact pattern/framework/category catalog (30 patterns, 11 frameworks). Coverage: Python (`unittest.mock`'s `patch`/`patch.object`, bare and `mock.`-qualified; `Mock`/`MagicMock`/`AsyncMock`; `create_autospec`; `pytest-mock`'s `mocker.patch`/`mocker.patch.object`; pytest's built-in `monkeypatch`), Java (Mockito, EasyMock, MockK — not PowerMock, a documented exclusion), JavaScript (Jest's `fn`/`spyOn`/`mock`/`mocked`/`createMockFromModule`, Sinon's `stub`/`spy`/`mock`/`fake`/`replace`/`createStubInstance`), TypeScript (same Jest/Sinon patterns, plus Vitest's `vi.fn`/`vi.mock`), and Go (patterns exist for parity — `gomock`, `testify` — but are unreachable, since Go detection is dead code; `test_go_mock_patterns.py` is skipped accordingly). Every test in this category asserts on `fixture.mocks` directly (framework, category, target_identifier) rather than just that the surrounding fixture was extracted — a fixture can be detected correctly while its mock usage inside is silently missed, which is how several real gaps were originally found (see `mock_patterns_excluded` in the YAML catalog for what's still knowingly unhandled).
5. **Integration tests** — realistic, multi-language test code: Django TestCase hierarchy (Python), JUnit 5 with nested classes (Java), Jest with beforeAll/afterAll (JavaScript), type-annotated Jest (TypeScript), implicit vs. explicit setup patterns, complex fixture dependencies, large test modules with many fixtures.

## Running Tests

```bash
pytest tests/ -v                                                    # run everything
pytest tests/test_extractor_unit/test_python_fixtures.py -v         # one file
pytest tests/collection/test_mock_detection/ -v                     # one category
pytest tests/ -v -k "python"                                        # by name pattern
pytest tests/ --cov=collection.detector --cov-report=html           # coverage report
```

See `pytest --help` for the rest of pytest's own flags (`-x` to stop on first failure, `-s` for print output, `--durations=10` for slowest tests, `-n auto` for parallel execution with pytest-xdist, etc.) — nothing about this project changes their behavior.

## Test Helpers (conftest.py)

`tests/conftest.py` provides reusable pytest fixtures and assertion helpers:

```python
create_test_file(language, code)
extract_and_find_fixtures(code, language)
fixture = extract_and_find_fixtures(code, language, fixture_name='setUp')

assert_fixture_detected(code, language, name)
assert_fixture_not_detected(code, language, name)
assert_fixture_count(code, language, expected_count)
assert_line_range(fixture, start_line, end_line)
assert_loc(fixture, expected_loc)
assert_fixture_metrics(fixture, **kwargs)
```

Example:

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

Agent detection — file scanning, commit-trailer/author-identity matching, fixture completeness marking (see [Agent Detection Methodology](../architecture/agent-detection.md)) — is covered across several files under `tests/collection/`, not one single end-to-end module:

- `test_agent_detection_logic.py` — agent config file scanning, GitHub API file-listing helper (retry/rate-limit handling)
- `test_agent_patterns_thorough.py`, `test_agent_patterns_extra.py` — agent signature catalog matching (author identity, trailers)
- `test_conventional_commits.py` — commit-trailer parsing
- `test_end_to_end_collection.py` — collector initialization, DB persistence, concurrency, error handling for both Dataset A and B collectors
- `tests/between_group/test_agent_corpus.py` — Dataset A's collector, using real git repositories in `tmp_path` with `Co-authored-by` trailers

```bash
pytest tests/collection/test_agent_detection_logic.py -v
pytest tests/collection/ -v -k agent
```

## pytest Configuration

The project configures test discovery and execution via `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
norecursedirs = ["clones", ".git", "venv", "dist", "build"]
addopts = "-q"
```

`norecursedirs` matters in particular: `clones/` holds hundreds of externally-cloned repositories with their own tests, and without excluding it, pytest would try to import and run them — causing dependency and timeout issues, and making a full run roughly 100x slower.

## Adding New Tests

Put the test under the matching category directory (`test_extractor_unit/`, `test_extractor_metadata/`, `test_extractor_edge_cases/`, `test_mock_detection/`, `test_integration/`, or `test_agent_detection_logic.py` for agent detection), reuse the `conftest` helpers, and follow the existing naming conventions (`Test<FeatureOrLanguage><Pattern>` for classes, `test_<what_is_tested>` for methods, `test_<language>_<category>.py` for files):

```python
from ..conftest import assert_fixture_detected

class TestPythonAsyncFixtures:
    def test_async_setUp_with_await(self):
        code = "..."
        fixture = assert_fixture_detected(code, 'python', 'setUp')
        assert fixture.fixture_type == 'unittest_setup'  # not the method name itself
```

If `ImportError: No module named 'conftest'` shows up, use the relative import (`from ..conftest import ...`), not a bare `from conftest import ...`.

## References

- [tests/TEST_PLAN.md](../../tests/TEST_PLAN.md) — test strategy document
- [collection/detector.py](../../collection/detector.py) — detector implementation
- [collection/detector_shared.py](../../collection/detector_shared.py) — `FixtureResult` dataclass
- [pytest documentation](https://docs.pytest.org/)
