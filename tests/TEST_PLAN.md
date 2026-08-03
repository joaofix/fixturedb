# FixtureDB Extractor Test Plan

## Overview

This document outlines the comprehensive testing strategy for the fixture extraction module. The extractor uses Tree-sitter ASTs to identify test fixture definitions across 6 programming languages and extract their metadata.

**Goal:** Ensure that fixture detection rules are accurate, comprehensive, and trustworthy across all supported languages and edge cases.

---

## Test Categories

### 1. Unit Tests (Per-Language)

**Purpose:** Validate that language-specific fixture patterns are correctly detected.

**Scope:** Small code snippets (1-10 lines) for each language.

**What we test:**
- ✅ **Positive detection**: Fixtures found when they exist
- ✅ **Negative detection**: Non-fixtures correctly excluded
- ✅ Multiple fixture types per language
- ✅ Different fixture scopes (per-test, per-class, module-level)

**Files:**
- `test_extractor_unit/test_python_fixtures.py`
- `test_extractor_unit/test_java_fixtures.py`
- `test_extractor_unit/test_javascript_fixtures.py`
- `test_extractor_unit/test_typescript_fixtures.py`
- `test_extractor_unit/test_csharp_fixtures.py`

**Language-specific patterns to test:**

**Python:**
- `setUp()` / `tearDown()` methods (unittest)
- `@pytest.fixture` decorators
- `setup_class()` / `teardown_class()`
- `setup_module()` / `teardown_module()`
- Fixture functions with `@pytest.fixture`
- Fixture factories and parameterization

**Java:**
- `@Before` / `@After` (JUnit 3-4)
- `@BeforeClass` / `@AfterClass` (class-level)
- `@BeforeEach` / `@AfterEach` (JUnit 5)
- Class initializers / static initializers
- TestNG `@BeforeMethod` / `@AfterMethod`

**JavaScript/TypeScript:**
- `beforeEach()` / `afterEach()` (Mocha, Jest, etc.)
- `before()` / `after()` (hooks)
- `beforeAll()` / `afterAll()`
- Factory functions
- Shared setup objects

**C#:**
- `[SetUp]` / `[TearDown]` (NUnit)
- `[OneTimeSetUp]` / `[OneTimeTearDown]`
- `[Before]` / `[After]` (xUnit)
- Constructor fixtures
- `IDisposable` cleanup

---

### 2. Extraction Metadata Tests

**Purpose:** Validate that extracted fixture metadata is accurate.

**What we test:**
- ✅ **Line numbers**: `start_line` and `end_line` match actual code range
- ✅ **Line counts**: `loc` (lines of code) is correct
- ✅ **Fixture type**: Classification (setUp, tearDown, fixture, etc.)
- ✅ **Fixture scope**: per_test, per_class, per_module, or global
- ✅ **Complexity metrics**: cyclomatic_complexity, num_parameters
- ✅ **Code metrics**: num_objects_instantiated, num_external_calls

**Files:**
- `test_extractor_metadata/test_line_numbers.py`
- `test_extractor_metadata/test_fixture_types.py`
- `test_extractor_metadata/test_scopes.py`
- `test_extractor_metadata/test_metrics.py`

**Test scenarios:**
- Single-line fixtures
- Multi-line fixtures with blank lines
- Fixtures with comments
- Nested code blocks
- Parameterized fixtures

---

### 3. Language-Specific Pattern Tests

**Purpose:** Comprehensive validation of language-specific fixture definitions.

**What we test:**
- ✅ All documented fixture types for each language
- ✅ Variations in decorator/annotation syntax
- ✅ Implicit vs explicit scope declarations
- ✅ Async/await patterns (JavaScript, C#, Python)
- ✅ Context managers / with statements (Python)
- ✅ Inheritance-based fixtures (Java)
- ✅ Parameterized/data-driven fixtures

**Files:**
- `test_extractor_unit/conftest.py` (shared fixtures and utilities)
- `test_extractor_unit/test_*_fixtures.py` (per-language)

**Test cases per language:**

| Language | Patterns | Count |
|----------|----------|-------|
| Python | unittest, pytest, combinations | 15+ |
| Java | JUnit 3/4/5, TestNG | 12+ |
| JavaScript | Mocha, Jest, async patterns | 12+ |
| TypeScript | Same as JS + type declarations | 12+ |
| C# | NUnit, xUnit, async | 12+ |

---

### 4. Edge Cases & Robustness Tests

**Purpose:** Validate that extractor handles unusual but valid code correctly.

**What we test:**
- ✅ **Large fixtures**: 100+ line fixtures
- ✅ **Deeply nested**: Fixtures inside nested classes/functions
- ✅ **Comments**: Fixtures containing fixture-like comments (false positive check)
- ✅ **String literals**: Code resembling fixtures in strings (false positive check)
- ✅ **Malformed code**: Incomplete/syntactically invalid code (graceful degradation)
- ✅ **Line endings**: CRLF vs LF (Windows vs Unix)
- ✅ **Encoding**: UTF-8 with BOM, non-ASCII characters
- ✅ **Empty fixtures**: Fixtures with only pass/return statements
- ✅ **Decorators**: Multiple/chained decorators

**Files:**
- `test_extractor_edge_cases/test_large_fixtures.py`
- `test_extractor_edge_cases/test_nested_code.py`
- `test_extractor_edge_cases/test_false_positives.py`
- `test_extractor_edge_cases/test_special_cases.py`

**Test scenarios:**
- Single line: `def setUp(self): pass`
- Multiple decorators: `@pytest.fixture(scope="class")`
- Comments that look like fixtures but aren't
- Fixtures in docstrings
- Fixtures with type annotations
- Generators with `yield`
- Async fixtures

---

## Test Statistics

**Total planned test cases:** 100+
- Unit tests: 70+ (comprehensive per-language coverage)
- Metadata tests: 15+ (validation of extracted metadata)
- Language-specific tests: 10+ (patterns)
- Edge cases: 15+ (robustness)
- Mock detection: 5+ (secondary feature)
- Integration: 5+ (real fixtures)
- Regression: 10+ (known issues)

---

## Test Execution

### Running all tests
```bash
pytest tests/ -v
```

### Running by category
```bash
pytest tests/test_extractor_unit/ -v
pytest tests/test_extractor_metadata/ -v
pytest tests/test_extractor_edge_cases/ -v
```

### Running by language
```bash
pytest tests/test_extractor_unit/test_python_fixtures.py -v
pytest tests/test_extractor_unit/test_java_fixtures.py -v
```

### Running with coverage
```bash
pytest tests/ --cov=collection.detector --cov-report=html
```

---

## Test Data Organization

```
tests/
├── TEST_PLAN.md                    # This file
├── conftest.py                     # Shared pytest fixtures
├── test_extractor_unit/
│   ├── conftest.py
│   ├── test_python_fixtures.py
│   ├── test_java_fixtures.py
│   ├── test_javascript_fixtures.py
│   ├── test_typescript_fixtures.py
│   └── test_csharp_fixtures.py
├── test_extractor_metadata/
│   ├── test_line_numbers.py
│   ├── test_fixture_types.py
│   ├── test_scopes.py
│   └── test_metrics.py
├── test_extractor_edge_cases/
│   ├── test_large_fixtures.py
│   ├── test_nested_code.py
│   ├── test_false_positives.py
│   └── test_special_cases.py
├── fixtures/
│   ├── python/
│   │   └── test_*.py (mini test files)
│   ├── java/
│   ├── javascript/
│   ├── typescript/
│   ├── go/
│   └── csharp/
```

---

## Future Test Categories

- [ ] **Mock Detection Tests** (category 5)
  - Framework detection (pytest-mock, Mockito, unittest.mock, etc.)
  - Mock usage patterns per language
  - False positive checks

- [ ] **Integration Tests** (category 7)
  - Real test files from popular projects
  - Multiple fixtures per file
  - Complex test hierarchies

- [ ] **Regression Tests** (category 8)
  - Previously missed fixtures
  - Previously over-detected fixtures
  - Language-specific quirks

- [ ] **Performance Tests** (category 9)
  - File timeout validation (5 minutes)
  - Large file handling (1MB+)
  - Thousands of fixtures

---

## Success Criteria

✅ **Precision:** >95% of detected items are actual fixtures
✅ **Recall:** >90% of actual fixtures are detected
✅ **Language coverage:** All 6 languages thoroughly tested
✅ **Edge case handling:** Graceful degradation on malformed code
✅ **Metadata accuracy:** Line numbers and metrics are correct
✅ **Performance:** No fixture timeout violations

---

## References

- **Detector implementation:** `collection/detector.py`
- **FixtureResult dataclass:** Lines 75-91
- **Extract fixtures function:** Line 724+
- **Language-specific detectors:** Lines 150-720 (per-language implementations)

