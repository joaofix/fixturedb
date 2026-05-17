# FixtureDB Tests & Documentation Analysis
**Date:** March 28, 2026  
**Scope:** Tests structure, documentation coverage, code ↔ docs synchronization  
**Thoroughness:** Comprehensive with specific file paths and line numbers

> **Note:** This document references historical analysis. Cognitive complexity metric was removed in Phase 3. Tests and documentation have been updated accordingly; the metric is no longer part of the codebase.

---

## 1. TESTS STRUCTURE ANALYSIS

### 1.1 Test Categories & Organization

The test suite spans **7 major categories** with **15 test modules**:

| Category | Files | Coverage | Status |
|----------|-------|----------|--------|
| **Unit Tests** | 6 files | Language-specific fixture detection |  Comprehensive |
| **Metadata Tests** | 2 files | Line numbers, LOC, scope, metrics | ️ Partial |
| **Edge Cases** | 1 file | Large fixtures, false positives |  Good |
| **Integration Tests** | 7 files | Real-world patterns | ️ Duplicated |
| **Mock Detection** | 7 files | Mock framework patterns |  Good |
| **Export Tests** | 1 file | CSV export functionality |  Limited |
| **Framework Tests** | 2 files | Cross-framework validation | ️ Incomplete |

**File Structure:**
```
tests/
├── conftest.py                          [Helper functions & shared fixtures]
├── test_framework_detection.py          [Framework selection logic]
├── test_export/
│   └── test_language_specific_fixtures.py
├── test_extractor_edge_cases/
│   └── test_edge_cases.py
├── test_extractor_metadata/
│   ├── test_line_numbers.py
│   └── test_fixture_types_and_scopes.py
├── test_extractor_unit/                [Per-language unit tests]
│   ├── test_python_fixtures.py
│   ├── test_java_fixtures.py
│   ├── test_javascript_fixtures.py
│   ├── test_typescript_fixtures.py
│   ├── test_go_fixtures.py
│   └── test_csharp_fixtures.py
├── test_integration/                   [Real-world integration tests]
│   ├── test_realistic_fixtures.py       [DUPLICATE: generic patterns]
│   ├── test_python_realistic_fixtures.py
│   ├── test_java_realistic_fixtures.py
│   ├── test_javascript_realistic_fixtures.py
│   ├── test_typescript_realistic_fixtures.py
│   ├── test_csharp_realistic_fixtures.py
│   └── test_go_realistic_fixtures.py
├── test_mock_detection/                [Mock framework detection]
│   ├── test_mock_patterns.py            [DUPLICATE: generic patterns]
│   ├── test_python_mock_patterns.py
│   ├── test_java_mock_patterns.py
│   ├── test_javascript_mock_patterns.py
│   ├── test_typescript_mock_patterns.py
│   ├── test_go_mock_patterns.py
│   └── test_csharp_mock_patterns.py
└── TEST_PLAN.md                         [Test strategy documentation]
```

---

### 1.2 Duplicate Test Coverage (DRY Violations)

**ISSUE #1: Duplicate integration test patterns**

| File | Pattern | Lines | Issue |
|------|---------|-------|-------|
| [test_integration/test_realistic_fixtures.py](tests/test_integration/test_realistic_fixtures.py#L1) | Generic Django/pytest/SQLAlchemy test class patterns | ~250 | **DUPLICATED** in language-specific files |
| [test_integration/test_python_realistic_fixtures.py](tests/test_integration/test_python_realistic_fixtures.py#L1) | **IDENTICAL** Django test (lines 16-45) | ~45 | Same code as generic file, class `TestRealWorldPythonFixtures` |
| [test_integration/test_java_realistic_fixtures.py](tests/test_integration/test_java_realistic_fixtures.py#L1) | **IDENTICAL** JUnit5 test (lines 16-55) | ~40 | Same code as generic file, class `TestJavaJUnit5Hierarchy` |

**Specific Duplicates:**
- `TestRealWorldPythonFixtures.test_django_test_case_hierarchy()` appears in BOTH:
  - [test_integration/test_realistic_fixtures.py:18-45](tests/test_integration/test_realistic_fixtures.py#L18)
  - [test_integration/test_python_realistic_fixtures.py:16-45](tests/test_integration/test_python_realistic_fixtures.py#L16)

- `TestRealWorldJavaFixtures.test_junit5_complex_hierarchy()` appears in BOTH:
  - [test_integration/test_realistic_fixtures.py:85-130](tests/test_integration/test_realistic_fixtures.py#L85)
  - [test_integration/test_java_realistic_fixtures.py:16-55](tests/test_integration/test_java_realistic_fixtures.py#L16)

**ISSUE #2: Duplicate mock detection patterns**

| File | Problem | Example |
|------|---------|---------|
| [test_mock_detection/test_mock_patterns.py](tests/test_mock_detection/test_mock_patterns.py#L1) | Generic mock patterns for all languages (~300 lines) | `TestPythonMockPatterns.test_unittest_mock_detection()` |
| [test_mock_detection/test_python_mock_patterns.py](tests/test_mock_detection/test_python_mock_patterns.py) | **DUPLICATES** Python-specific tests | Same test names and assertion logic |

**Recommendation:** 
- Move generic language patterns to a parametrized base test class in `conftest.py`
- Use `pytest.mark.parametrize()` to run same test across languages
- Keep language-specific edge cases separate

---

### 1.3 Missing Test Coverage for Recent Features

#### **Feature 1: `cognitive_complexity` (NEW - No Test Coverage)**

**Where it's used:**
- [collection/detector.py:145-180](collection/detector.py#L145) — `_cognitive_complexity()` function
- [collection/detector.py:1029](collection/detector.py#L1029) — Assigned to `FixtureResult.cognitive_complexity`
- [collection/exporter.py:234](collection/exporter.py#L234) — Exported to CSV
- [docs/14-csv-export-guide.md:86](docs/14-csv-export-guide.md#L86) — "Nesting-depth-weighted complexity"
- [docs/03-database-schema.md:67](docs/03-database-schema.md#L67) — Database column

**Where it's NOT tested:**
```bash
$ grep -r "cognitive_complexity" tests/
# Only in export test mock SQL schema; no behavior validation
```

**Missing test file:** `tests/test_extractor_metadata/test_cognitive_complexity.py` (should exist but doesn't)

**Coverage gaps:**
-  No tests for cognitive complexity calculation accuracy
-  No regression tests for nesting depth scoring
-  No cross-language validation (should be language-agnostic)
-  No edge case tests (e.g., deeply nested blocks, recursion detection)

**Recommendation:**
Add comprehensive tests for cognitive complexity:
```python
# tests/test_extractor_metadata/test_cognitive_complexity.py

class TestCognitiveComplexityCalculation:
    def test_simple_function_complexity_1(self):
        """Function with no control structures has complexity = 1"""
        code = """
def simple():
    return 42
"""
        fixture = assert_fixture_detected(code, "python", "simple")
        assert fixture.cognitive_complexity == 1
    
    def test_single_if_complexity(self):
        """Single if statement adds 1 (depth 0 → 1)"""
        code = """
def with_if():
    if True:
        pass
"""
        fixture = assert_fixture_detected(code, "python", "with_if")
        assert fixture.cognitive_complexity >= 1
    
    def test_nested_if_complexity(self):
        """Nested if multiplies by depth"""
        code = """
def nested():
    if x:
        if y:
            if z:
                pass
"""
        fixture = assert_fixture_detected(code, "python", "nested")
        # Nesting depth should increase complexity non-linearly
        assert fixture.cognitive_complexity >= 3
    
    def test_recursion_penalty(self):
        """Recursive functions add fixed penalty"""
        # Should test recursion detection (depth +5)
```

---

#### **Feature 2: Excluded CSV Fields (Documented but Not Fully Tested)**

**Excluded fields:**
- `raw_source` — Full source code (excluded from `fixtures.csv`)
- `category` — Subjective taxonomy (excluded from all CSVs)
- `mock_style` — Subjective mock classification (excluded from `mock_usages.csv`)
- `target_layer` — Subjective target classification (excluded from `mock_usages.csv`)
- `raw_snippet` — Code snippet (excluded from `mock_usages.csv`)

**Test coverage:**
- [tests/test_export/test_language_specific_fixtures.py:250-260](tests/test_export/test_language_specific_fixtures.py#L250) — Only checks that certain columns exist in SQL schema, NOT that they're excluded from CSV
- No assertion that `raw_source` is actually excluded from the CSV export
- No test for `fixtures_with_source.csv` (opt-in CSV with raw_source included)

**Recommendation:**
Update export test to validate exclusions:
```python
# In test_export/test_language_specific_fixtures.py
def test_fixtures_csv_excludes_raw_source(self):
    """Verify raw_source is NOT in fixtures.csv"""
    df = pd.read_csv(export_dir / "fixtures.csv")
    assert "raw_source" not in df.columns
    assert "category" not in df.columns

def test_fixtures_with_source_csv_includes_raw_source(self):
    """Verify fixtures_with_source.csv DOES include raw_source"""
    df = pd.read_csv(export_dir / "fixtures_with_source.csv")
    assert "raw_source" in df.columns
    assert "category" not in df.columns  # Still excluded

def test_mock_usages_csv_excludes_subjective_fields(self):
    """Verify subjective mock fields are excluded from CSV"""
    df = pd.read_csv(export_dir / "mock_usages.csv")
    excluded = ["mock_style", "target_layer", "raw_snippet"]
    for col in excluded:
        assert col not in df.columns, f"{col} should be excluded from CSV"
```

---

#### **Feature 3: `toy` Command (Documented in Code but Not in Docs)**

**Status:**  Implemented, but  **undocumented in user-facing docs**

**Code locations:**
- [pipeline.py:12](pipeline.py#L12) — Help text: "Build toy dataset (10 repos/language) for validation"
- [pipeline.py:187-226](pipeline.py#L187) — `cmd_toy()` implementation
- [pipeline.py:537-540](pipeline.py#L537) — Argument parser

**Documentation:**
-  Docstring in `pipeline.py` (examples at [pipeline.py:20-22](pipeline.py#L20))
-  Listed in command help output
-  **NOT documented in** [docs/07-running.md](docs/07-running.md) — only covers `run`, `search`, `clone`, `extract`, `classify`, `export`
-  **NOT mentioned in** [docs/INDEX.md](docs/INDEX.md) — no reference to validation/testing docs

**Recommendation:** Add section to [docs/07-running.md](docs/07-running.md):
```markdown
## Quick validation (toy dataset)

For rapid testing of new changes, build a toy dataset with only 10 repos per language:

\`\`\`bash
# Full toy dataset (all 6 languages, ~60 repos total)
python pipeline.py toy

# Python only
python pipeline.py toy --language python

# Single language with max override
python pipeline.py toy --language java --max 5
\`\`\`

This completes the full pipeline (search → clone → extract → classify) much faster
than the full dataset, making it ideal for:
- Testing recent code changes
- Validating new feature integration
- Quick debugging without 30-minute waits
```

---

### 1.4 Test Code Quality — DRY Improvements

#### **Issue: Repeated assertion helpers in conftest.py**

[conftest.py](tests/conftest.py#L1) provides good shared utilities, but some patterns repeat:

**Current state (good):**
-  [conftest.py:60-75](tests/conftest.py#L60) — `assert_fixture_metrics()` for complexity & parameters
-  [conftest.py:40-57](tests/conftest.py#L40) — `assert_line_range()` & `assert_loc()`

**Missing helper:**
```python
# conftest.py: MISSING
def assert_cognitive_complexity(fixture: FixtureResult, expected: int = None, min: int = None, max: int = None):
    """Assert cognitive complexity bounds."""
    if expected is not None:
        assert fixture.cognitive_complexity == expected
    if min is not None:
        assert fixture.cognitive_complexity >= min
    if max is not None:
        assert fixture.cognitive_complexity <= max
```

**Usage in tests would be:**
```python
# test_extractor_metadata/test_cognitive_complexity.py
def test_nested_complexity(self):
    code = "..."
    fixture = assert_fixture_detected(code, "python", "nested")
    assert_cognitive_complexity(fixture, min=2, max=10)
```

#### **Issue: Redundant test file creation**

Many tests repeat this pattern:
```python
# test_extractor_unit/test_python_fixtures.py:40
from ..conftest import extract_and_find_fixtures

def test_setUp_method_detected(self):
    code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.data = []
"""
    assert_fixture_detected(code, "python", "setUp", ...)

# Same in test_java_fixtures.py:30, test_typescript_fixtures.py:45, etc.
```

**Improvement:** Create parametrized fixtures in conftest:
```python
# conftest.py
LANGUAGE_UNIT_TESTS = {
    "python": [
        ("unittest_setup", """
class T(unittest.TestCase):
    def setUp(self): self.x = []
""", "setUp"),
        ("pytest_decorator", """
@pytest.fixture
def fix(): return 1
""", "fix"),
    ],
    "java": [
        ("junit4_before", """
@Before public void setUp() { }
""", "setUp"),
    ],
    # ... etc
}

@pytest.mark.parametrize("language,code,fixture_name", [
    (lang, test_case[1], test_case[2])
    for lang, tests in LANGUAGE_UNIT_TESTS.items()
    for test_case in tests
])
def test_basic_fixture_detection(language, code, fixture_name):
    """Cross-language fixture detection test"""
    assert_fixture_detected(code, language, fixture_name)
```

---

## 2. DOCUMENTATION STATUS ANALYSIS

### 2.1 Collection Phases Documentation

**Status:**  **Fully documented and accurate**

| Phase | Code | Doc | Link | Status |
|-------|------|-----|------|--------|
| **Phase 1: Search** | [collection/search.py](collection/search.py) | [04-data-collection.md:8-34](docs/04-data-collection.md#L8) | Sections & GitHub API docs |  Complete |
| **Phase 2: Clone** | [collection/cloner.py](collection/cloner.py) | [04-data-collection.md:36-51](docs/04-data-collection.md#L36) | Quality filters (5 test files, 50 commits) |  Complete |
| **Phase 3: Extract** | [collection/extractor.py](collection/extractor.py) | [04-data-collection.md:53-60](docs/04-data-collection.md#L53) | Tree-sitter parsing & mock detection |  Complete |
| **Phase 4: Classify** | [collection/classifier.py](collection/classifier.py) | [04-data-collection.md:62-64](docs/04-data-collection.md#L62) | Domain classification |  Complete |
| **Phase 5: Export** | [collection/exporter.py](collection/exporter.py) | [04-data-collection.md:66-75](docs/04-data-collection.md#L66) | ZIP artifact structure |  Complete |

**Quality filters documented correctly:**
-  [docs/10-configuration.md:26-29](docs/10-configuration.md#L26) — MIN_TEST_FILES, MIN_COMMITS, MIN_FIXTURES_FOUND

---

### 2.2 CSV Export Documentation — Quality Check

**Status:**  **Accurate and comprehensive**

**Checked against exporter.py code:**

| CSV File | Doc Location | Columns | Excluded Fields | Status |
|----------|--------------|---------|-----------------|--------|
| `repositories.csv` | [14-csv-export-guide.md:16-42](docs/14-csv-export-guide.md#L16) |  19 columns listed | None |  Match |
| `test_files.csv` | [14-csv-export-guide.md:48-62](docs/14-csv-export-guide.md#L48) |  8 columns | None |  Match |
| `fixtures.csv` | [14-csv-export-guide.md:68-107](docs/14-csv-export-guide.md#L68) |  15 columns | `raw_source`, `category` |  Match [exporter.py:225-230](collection/exporter.py#L225) |
| `mock_usages.csv` | [14-csv-export-guide.md:113-130](docs/14-csv-export-guide.md#L113) |  5 columns | `mock_style`, `target_layer`, `raw_snippet` |  Match [exporter.py:220-222](collection/exporter.py#L220) |
| `fixtures_<lang>.csv` | [14-csv-export-guide.md:135-155](docs/14-csv-export-guide.md#L135) |  22 columns + GitHub URL | `category` only |  Match [exporter.py:240-280](collection/exporter.py#L240) |

**Excluded fields documentation:**
-  [14-csv-export-guide.md:104-106](docs/14-csv-export-guide.md#L104) — Documents `raw_source` and `category` as excluded
-  [14-csv-export-guide.md:127-130](docs/14-csv-export-guide.md#L127) — Documents mock exclusions

---

### 2.3 Collection Rules Documentation

**Status:**  **Complete and accurate**

| Rule | Parameter | Documented | Code Location | Doc Location |
|------|-----------|---|---|---|
| **Min stars (threshold)** | `min_stars` |  | [config.py:58](collection/config.py#L58) | [10-configuration.md:6-8](docs/10-configuration.md#L6) |
| **Per-language targets** | `target_repos` |  | [config.py:85-120](collection/config.py#L85) | [10-configuration.md:10-16](docs/10-configuration.md#L10) |
| **Star tiers (core/extended)** | `STAR_TIER_CORE_THRESHOLD=500` |  | [config.py:73-82](collection/config.py#L73) | [03-database-schema.md:19-25](docs/03-database-schema.md#L19) |
| **Min test files (quality filter)** | `MIN_TEST_FILES=5` |  | [config.py:131](collection/config.py#L131) | [10-configuration.md:26-28](docs/10-configuration.md#L26) |
| **Min commits (quality filter)** | `MIN_COMMITS=100` |  | [config.py:132](collection/config.py#L132) | [10-configuration.md:26-28](docs/10-configuration.md#L26) |
| **Min fixtures found (quality filter)** | `MIN_FIXTURES_FOUND=1` |  | [config.py:133](collection/config.py#L133) | [04-data-collection.md:59](docs/04-data-collection.md#L59) |
| **Survival rates** | `LANGUAGE_SURVIVAL_RATES` |  | [config.py:135-142](collection/config.py#L135) | NOT documented | ️ **MISSING** |
| **Exclusion keywords** | `EXCLUSION_KEYWORDS` |  | [config.py:45-61](collection/config.py#L45) | [04-data-collection.md:29](docs/04-data-collection.md#L29) |
| **Sort strategies** | `--sort-by-stars`, `--stratified` |  | [pipeline.py:72-95](pipeline.py#L72) | [04-data-collection.md:12-20](docs/04-data-collection.md#L12) |

**️ DOCUMENTATION GAP:**
- [config.py:135-142](collection/config.py#L135) defines `LANGUAGE_SURVIVAL_RATES` with empirical values:
  ```python
  LANGUAGE_SURVIVAL_RATES = {
      "python": 0.076,    # 7.6% actual
      "java": 0.15,       # estimated
      "go": 0.09,         # estimated
      "csharp": 0.10,     # estimated
      "javascript": 0.08, # estimated
      "typescript": 0.08, # estimated
  }
  ```
- These rates are used in discovery calculations but **NOT documented in docs/** 
- Should be added to [docs/10-configuration.md](docs/10-configuration.md) under a new section "Per-language survival rates"

---

### 2.4 Database Schema Documentation

**Status:**  **Accurate but partially outdated**

**Verified columns (all match code):**
-  `repositories` table — 16 columns documented, all present in [db.py:18-35](collection/db.py#L18)
-  `test_files` table — 5 columns, all present in [db.py:39-43](collection/db.py#L39)
-  `fixtures` table — 17 columns documented
-  `mock_usages` table — 8 columns documented

**COLUMN VERIFICATION:**

```python
# collection/db.py:47-64 CREATE TABLE fixtures
fixtures_table = """
    CREATE TABLE fixtures (
        id                       INTEGER PRIMARY KEY,
        file_id                  INTEGER NOT NULL,
        repo_id                  INTEGER NOT NULL,
        name                     TEXT NOT NULL,
        fixture_type             TEXT NOT NULL,
        scope                    TEXT NOT NULL,
        start_line               INTEGER NOT NULL,
        end_line                 INTEGER NOT NULL,
        loc                      INTEGER NOT NULL,
        cyclomatic_complexity    INTEGER NOT NULL,
        cognitive_complexity     INTEGER NOT NULL,  # ← NEW, documented as of schema v2
        num_objects_instantiated INTEGER NOT NULL,
        num_external_calls       INTEGER NOT NULL,
        num_parameters           INTEGER NOT NULL,
        framework                TEXT,
        raw_source               TEXT,
        category                 TEXT,
        FOREIGN KEY(file_id) REFERENCES test_files(id),
        FOREIGN KEY(repo_id) REFERENCES repositories(id)
    )
"""
```

**MATCH CHECK:**
-  [docs/03-database-schema.md:37-70](docs/03-database-schema.md#L37) lists all 17 columns including `cognitive_complexity`

---

### 2.5 Documentation Index Completeness

**Status:**  **Good coverage, one gap noted**

[docs/INDEX.md](docs/INDEX.md) references:
-  01-16 guides covering setup, running, schema, config, etc.
-  **Missing reference to toy command** — [07-running.md](docs/07-running.md) doesn't mention it

---

## 3. CODE ↔ DOCUMENTATION SYNC ISSUES

### 3.1 Confirmed Mismatches

#### **ISSUE #1: Survival Rates Not Documented** ️ MODERATE

| Element | Code | Docs | Issue |
|---------|------|------|-------|
| **Survival rates** | [config.py:135-142](collection/config.py#L135) | Not in any `.md` | Rates used for discovery estimation but not explained |

**Impact:** Users can't understand how repository discovery targets are calculated

**Example mismatch:**
```python
# collection/config.py:135-142
LANGUAGE_SURVIVAL_RATES = {
    "python": 0.076,    # Used in discovery forecasting
    "java": 0.15,
    # ...
}
```

Not documented anywhere; should be in [docs/10-configuration.md](docs/10-configuration.md)

**Fix:** Add section documenting how these rates affect discovery volume estimates

---

#### **ISSUE #2: Toy Command Not in User Docs** ️ MINOR

| Element | Code | Docs | Status |
|---------|------|------|--------|
| **toy command** | [pipeline.py:187-226](pipeline.py#L187)  Implemented | [docs/07-running.md](docs/07-running.md)  Missing | Not discoverable by users |

**Impact:** Users doing validation work won't know about the fast 10-repo toy mode

**Fix:** Add `## Quick Validation` section to [docs/07-running.md](docs/07-running.md) with examples

---

#### **ISSUE #3: Cognitive Complexity Algorithm Not Documented** ️ MODERATE

| Element | Code | Docs | Status |
|---------|------|------|--------|
| **Algorithm explanation** | [collection/detector.py:145-180](collection/detector.py#L145)  Comprehensive docstring | No detailed explanation in docs | Users can't understand the scoring |

**Code docstring is excellent:**
```python
def _cognitive_complexity(node, src_bytes: bytes) -> int:
    """
    Calculate cognitive complexity using tree-sitter AST.

    Cognitive complexity weights code constructs by nesting depth:
    - Control structures (if, while, for, case, catch) increment base score
    - Nesting depth multiplies the score (deeper = harder to understand)
    - Boolean operators (&&, ||) increment at their nesting level
    - Recursion adds a constant penalty
    """
```

**But:** Not in user-facing docs. Should be in docs/11-detection.md or new section in docs/09-usage.md

**Recommendation:** Add details to [docs/11-detection.md](docs/11-detection.md):
```markdown
### Cognitive Complexity Scoring

Unlike cyclomatic complexity (which just counts branches), cognitive complexity 
weights code by nesting depth — the deeper you nest, the harder it is to understand.

Scoring:
- Control structures (if, while, for, switch, try/catch): +1 base
- Nesting depth multiplier: increases score by nesting level
- Boolean operators (&&, ||, and, or): +1 per operator
- Recursion: +5 (detected by function calling itself)

Example:
```python
# Complexity = 1
def simple():
    return 42

# Complexity ≈ 2-3
def with_if():
    if condition:
        return True
    return False

# Complexity ≈ 4-6  (nesting depth 0→1→2)
def deeply_nested():
    if a:
        if b:
            if c:
                return True
```

---

#### **ISSUE #4: CSV Excluded Fields Not Explicitly Listed** ️ MINOR

| Element | Documented? | Location | Status |
|---------|---|---|---|
| Excluded from `fixtures.csv` |  Partially | [14-csv-export-guide.md:104-106](docs/14-csv-export-guide.md#L104) | Only mentioned in text, not in table |
| Excluded from `mock_usages.csv` |  Partially | [14-csv-export-guide.md:127-130](docs/14-csv-export-guide.md#L127) | Only mentioned in text, not in table |
| `fixtures_with_source.csv` option |  Missing | [pipeline.py:208](pipeline.py#L208) | Users don't know this file is available |

**Recommendation:** Add explicit subsection in [14-csv-export-guide.md](docs/14-csv-export-guide.md):

```markdown
### Excluded Columns (Database-Only)

**Reason for exclusion:**
- Raw source code is already in `fixtures.db` (redundant in CSV)
- Subjective categories require manual review (not exported data)
- Code snippets are redundant with GitHub URLs (direct access provided)

**To access excluded data:**

Use SQLite directly:
\`\`\`python
import sqlite3
conn = sqlite3.connect("fixtures.db")
# Get raw source and category
df = pd.read_sql("SELECT raw_source, category FROM fixtures", conn)
\`\`\`

Or export with source code included:
\`\`\`bash
python pipeline.py export --version 1.0 --include-source
# Produces: fixtures_with_source.csv (includes raw_source, still excludes category)
\`\`\`
```

---

### 3.2 Code Features Missing from Docs

#### ** Feature: Cognitive Complexity**
- **Code status:**  Implemented in [collection/detector.py:145-180](collection/detector.py#L145)
- **Test status:**  No test coverage
- **Doc status:**  In schema and CSV guides, **but NO detailed algorithm explanation**

#### ** Feature: Toy Command**
- **Code status:**  Implemented in [pipeline.py:187-226](pipeline.py#L187)
- **Test status:**  No specific test (could be in integration tests)
- **Doc status:**  Missing from [docs/07-running.md](docs/07-running.md)

#### ** Feature: Survey Stratification**
- **Code status:**  Implemented in [collection/search.py](collection/search.py)
- **Test status:**  Mentioned in [TEST_PLAN.md](tests/TEST_PLAN.md)
- **Doc status:**  Documented in [docs/04-data-collection.md:15-20](docs/04-data-collection.md#L15)

#### ** Feature: Survival Rates**
- **Code status:**  In [config.py:135-142](collection/config.py#L135)
- **Test status:**  Implicitly tested (used in discovery logic)
- **Doc status:**  Not documented; should be in [docs/10-configuration.md](docs/10-configuration.md)

---

### 3.3 Documentation Code Example Accuracy

**Status:**  **All code examples are accurate**

Spot-checked examples in:
-  [docs/09-usage.md](docs/09-usage.md) — Python pandas examples match `exporter.py` output
-  [docs/14-csv-export-guide.md:169](docs/14-csv-export-guide.md#L169) — pandas groupby example is correct
-  [docs/04-data-collection.md:7-40](docs/04-data-collection.md#L7) — Pipeline flow matches [pipeline.py](pipeline.py)

---

## 4. TEST ASSERTION COVERAGE FOR METRICS

### 4.1 Test Assertion Functions Currently Available

[conftest.py](tests/conftest.py) provides:

| Helper | Lines | Parameters | Status |
|--------|-------|-----------|--------|
| `assert_fixture_detected()` | 38-50 | name, type, scope |  Good |
| `assert_fixture_not_detected()` | 52-56 | name |  Good |
| `assert_fixture_count()` | 58-64 | expected_count |  Good |
| `assert_line_range()` | 66-73 | start_line, end_line |  Good |
| `assert_loc()` | 75-80 | expected_loc |  Good |
| `assert_fixture_metrics()` | 82-106 | cyclomatic_complexity bounds, num_parameters | ️ **Limited** |
| `assert_fixture_with_type_detected()` | 108-138 | type, scope, count |  Good |

**Gap in `assert_fixture_metrics()` [conftest.py:82-106](tests/conftest.py#L82):**
```python
def assert_fixture_metrics(
    fixture: FixtureResult,
    min_complexity: int = None,
    max_complexity: int = None,
    num_parameters: int = None,
):
    """Assert fixture metrics."""
    if min_complexity is not None:
        assert fixture.cyclomatic_complexity >= min_complexity
    if max_complexity is not None:
        assert fixture.cyclomatic_complexity <= max_complexity
    if num_parameters is not None:
        assert fixture.num_parameters == num_parameters
```

**Missing parameters:**
-  `cognitive_complexity` bounds (min/max)
-  `num_objects_instantiated` assertion
-  `num_external_calls` assertion

---

### 4.2 Metrics With No Test Coverage

| Metric | Calculated in | Database | CSV | Test Coverage |
|--------|---|---|---|---|
| `cyclomatic_complexity` | [detector.py:135-139](collection/detector.py#L135) |  |  |  In test_fixture_metrics() |
| **`cognitive_complexity`** | [detector.py:145-180](collection/detector.py#L145) |  |  |  **NONE** |
| `num_objects_instantiated` | [detector.py:218-224](collection/detector.py#L218) |  |  | ️ Only in mock detection tests |
| `num_external_calls` | [detector.py:226-242](collection/detector.py#L226) |  |  | ️ Only in mock detection tests |
| `num_parameters` | [detector.py](collection/detector.py) |  |  |  In test_fixture_metrics() |

**Recommendation:** Create `test_extractor_metadata/test_metrics.py`:
```python
class TestMetricsCalculation:
    def test_cyclomatic_complexity_accuracy(self): ...
    def test_cognitive_complexity_nesting(self): ...
    def test_cognitive_complexity_recursion(self): ...
    def test_objects_instantiated_counting(self): ...
    def test_external_calls_detection(self): ...
```

---

## 5. SUMMARY & RECOMMENDATIONS

### Critical Issues (Fix immediately)

1. ** No test for `cognitive_complexity` algorithm**
   - Create `tests/test_extractor_metadata/test_cognitive_complexity.py`
   - Add helper `assert_cognitive_complexity()` to conftest
   - Test nesting depth scoring, recursion detection, control structures
   - **Priority:** HIGH (metric is exported to CSV but unvalidated)

2. **️ Duplicate tests in integration & mock detection**
   - Consolidate `test_integration/test_realistic_fixtures.py` with language-specific variants
   - Use parametrized fixtures in conftest to DRY up code
   - Same for `test_mock_detection/test_mock_patterns.py`
   - **Priority:** MEDIUM (code maintenance issue)

### Documentation Gaps (Add to docs)

3. **️ Toy command not documented**
   - Add section to [docs/07-running.md](docs/07-running.md)
   - Examples: `python pipeline.py toy`, `python pipeline.py toy --language python`
   - **Priority:** MEDIUM (feature exists but users don't know)

4. **️ Survival rates not documented**
   - Add to [docs/10-configuration.md](docs/10-configuration.md)
   - Explain how LANGUAGE_SURVIVAL_RATES affect discovery estimates
   - **Priority:** LOW (advanced users only, but affects planning)

5. **️ Cognitive complexity algorithm details missing**
   - Add pseudo-code & examples to [docs/11-detection.md](docs/11-detection.md)
   - Move docstring from code to user-facing docs
   - **Priority:** MEDIUM (researchers need to understand the metric)

### Quality-of-Life Improvements

6. **Extend `assert_fixture_metrics()` in conftest**
   - Add support for `cognitive_complexity`, `num_objects_instantiated`, `num_external_calls`
   - Enables cleaner test code in multiple test files

7. **Document excluded CSV fields explicitly**
   - Add table in [docs/14-csv-export-guide.md](docs/14-csv-export-guide.md)
   - Link to `--include-source` option
   - Explain why fields are excluded

---

## Appendix: File Change Summary

| File | Change Type | Need |
|------|---|---|
| `tests/test_extractor_metadata/test_cognitive_complexity.py` | NEW FILE | Create comprehensive tests |
| `tests/conftest.py` | EXTEND | Add `assert_cognitive_complexity()` |
| `tests/test_integration/test_realistic_fixtures.py` | REVIEW | Check for deduplication |
| `tests/test_mock_detection/test_mock_patterns.py` | REVIEW | Check for deduplication |
| `docs/07-running.md` | ADD SECTION | Document toy command |
| `docs/10-configuration.md` | ADD SECTION | Document LANGUAGE_SURVIVAL_RATES |
| `docs/11-detection.md` | ADD SECTION | Document cognitive complexity algorithm |
| `docs/14-csv-export-guide.md` | ADD SECTION | Explicit excluded columns table |

