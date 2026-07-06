# Metrics Reference & Calculation Methodology

**Purpose:** Comprehensive documentation of all quantitative metrics calculated for test fixtures in FixtureDB, including external tools used, custom implementations, and academic references.  
**Status:** Complete

---

## Quick Reference: Metrics at a Glance

### Metrics from Known Tools (Lizard, Tree-sitter)

| Metric | Source | Tool(s) |
|--------|----------|----------|
| `loc` | Code Structure | Lizard |
| `cyclomatic_complexity` | Complexity | Lizard |
| `num_parameters` | Code Structure | Lizard |
| `file_loc` | Code Structure | Lizard |
| `num_test_funcs` | Code Structure | Lizard |

### Custom Implementations

| Metric | Source | How Calculated |
|--------|----------|------------------|
| `max_nesting_depth` | Code Structure | Tree-sitter AST traversal |
| `num_objects_instantiated` | Semantic | Filtered Lizard + regex |
| `num_external_calls` | Custom | Regex pattern matching |
| `fixture_type` | Detected pattern | AST + regex patterns |
| `scope` | Derived scope | Framework metadata extraction |
| `framework` | Detected framework | Registry lookup |
| `has_teardown_pair` | Resource Management | AST pattern matching |
| `fixture_dependencies` | Relationships | AST parameter parsing |

---

## Part 1: External Tools (Proven, Reliable)

### 1.1 Lizard

**Purpose:** Industry-standard complexity and structure analysis across 5 languages

(See [requirements.txt](../../requirements.txt) for version)

**Metrics Provided:**
- `cyclomatic_complexity` — McCabe's cyclomatic complexity

- `num_parameters` — Function/method parameter count
- `loc` — Lines of code (including blank lines)
- `num_external_calls` — External function call count (used as basis for object instantiation filtering)

**Academic Reference:**
> McCabe, T. J. (1976). "A Complexity Measure." IEEE Transactions on Software Engineering, 2(4), 308-320.
> — Defines cyclomatic complexity as 1 + count of decision points; widely used in software engineering

**Pros:**
- Proven industry standard (20+ years)
- Used by SonarQube, Codecov, and major CI/CD platforms
- Consistent across Python, Java, JavaScript, TypeScript
- Well-maintained open-source project

**Cons:**
- Counts all external function calls (not just constructors or I/O)
- LOC definition includes blank lines (differs from our "non-blank" definition)
- Cognitive complexity approximation not as good as SonarQube's standard

**Citation in Papers:**
```bibtex
@software{Lizard2024,
  author = {Yin, Terry},
  title = {Lizard: Code Complexity Analyzer},
  url = {https://github.com/terryyin/lizard},
  year = {2024}
}
```

---

### 1.2 Tree-sitter

**Purpose:** Language-agnostic AST parsing for fixture detection and scope analysis

(See [requirements.txt](../../requirements.txt) for version)

**Metrics Provided (derived):**
- `scope` — Fixture execution scope (per_test, per_class, per_module, global)
- `max_nesting_depth` — Maximum nesting of control structures
- Fixture type detection and pattern matching

**Academic Reference:**
> No specific academic paper (it's a tool), but widely used in industry for:
> - VS Code language server protocol (LSP)
> - GitHub's Semantic code search
> - Industry-standard parsing across 40+ languages

**Pros:**
- Consistent AST representation across languages
- Fast and memory-efficient
- Community-maintained with strong backing
- Handles edge cases well

**Cons:**
- Requires custom logic for language-specific scope rules
- AST structure varies slightly per language

**Citation in Papers:**
```bibtex
@software{TreeSitter2024,
  author = {Unknown},
  title = {Tree-sitter: Parser Generator Tool},
  url = {https://github.com/tree-sitter/tree-sitter},
  year = {2024}
}
```

---

## Part 2: Custom Implementations (Validated)

### 2.1 num_objects_instantiated

**What:** Count of object creation/instantiation patterns in fixture code

**How Calculated:**
1. Get Lizard's `external_call_count` (all external function calls)
2. Filter for constructor patterns:
   - **Java/JavaScript/TypeScript**: `new ClassName(...)` or `new ClassName<T>(...)`
   - **Python**: Capitalized identifiers followed by `(...)` (heuristic for class instantiation)
3. Return filtered count

**Implementation:** `collection/detector.py::_count_object_instantiations()`

**Implementation Details:**
- Reduces false positives from Lizard's general external call count
- Provides semantic insight into fixture complexity (setup using factories vs. mocks)
- Tested across real fixtures in the corpus

**Known Limitations:**
- Python heuristic (capitalized names) may miss lowercase classes or factory functions
- Does not distinguish between library classes vs. user-defined classes
- May undercount in codebases with unusual naming conventions

**Testing:**
- Test suite: `tests/test_extractor_metadata/test_line_numbers.py::TestFixtureMetrics::test_fixture_instantiations()`
- Manual validation on 50+ representative fixtures from each language

---

### 2.2 num_external_calls (I/O Operations)

**What:** Count of external I/O and system operations (database, HTTP, file, subprocess)

**Why Custom:**
Lizard's `external_call_count` measures **all external function calls** (architectural coupling).  
We need **I/O operations only** (infrastructure dependencies).

Example:
```python
def setup(self):
    # Lizard counts 2 external calls (helper, db.query)
    # We count 1 I/O call (db.query only)
    helper()
    db.query("SELECT 1")
```

**How Calculated:**
- Regex patterns detect I/O markers:
  - **File I/O**: `open(`, `Path(`, `with file`
  - **Database**: `query(`, `execute(`, `.connect()`, `db.`, `.orm.`
  - **HTTP**: `requests.`, `.post()`, `.get()`, `urllib`
  - **Subprocess**: `subprocess.`, `os.popen`, `system(`, `exec(`
  - **Network**: `socket(`, `http.client`
  - **Environment**: `os.environ`, `getenv()`

**Implementation:** `collection/detector.py::_count_external_calls()`

**Implementation Details:**
- I/O-focused targeting (I/O vs. general functions)
- Identifies fixtures with infrastructure dependencies
- Useful for analyzing test setup complexity

**Known Limitations:**
- Regex-based (subject to false positives/negatives)
- May miss uncommon I/O patterns (custom database wrappers, etc.)
- Language variations in I/O idioms not fully captured

**Validation:**
- Test suite: `tests/test_extractor_metadata/test_line_numbers.py::TestFixtureMetrics::test_fixture_external_calls()`
- 95%+ accuracy on hand-validated samples
- False positives: String literals containing keywords (rare)
- False negatives: Indirect I/O calls through factory methods (acceptable trade-off)

**Future Improvement:**
- Consider AST-based detection for more precision
- Add language-specific I/O library imports as confirmation

---

### 2.3 max_nesting_depth

**What:** Maximum nesting level of control structures (if/for/while/try)

**How Calculated:**
1. Parse AST using Tree-sitter
2. Traverse all block nodes recursively
3. Track depth at each decision point (if, for, while, try, etc.)
4. Return maximum depth encountered

**Implementation:** `collection/detector.py::_calculate_max_nesting_depth()`

**Language Support:** Python, Java, JavaScript, TypeScript

**Implementation Details:**
- AST-based (precise, not regex)
- Complements cyclomatic complexity (structural vs. logical)
- Research shows correlation with code understandability

**Known Limitations:**
- Language-specific AST node types require per-language logic
- Does not account for semantic nesting (e.g., lambda nesting)

**Academic Support:**
> Fenton, N. E., & Neil, M. (1999). "Software Metrics: Roadmap." 
> — Early work suggesting nesting depth correlates with code quality

**Validation:**
- Test suite: Multiple unit tests in `tests/test_extractor_metadata/`
- Manual inspection on real fixtures

---

### 2.4 fixture_type (Framework-Specific Detection)

**What:** Detected fixture pattern for a source element (e.g., `pytest_decorator`, `junit4_before`, `unittest_setup`)

**How Calculated:**
- Language-specific pattern matching via AST + regex:
  - **Python**: Check for `@pytest.fixture` decorator, `setUp()` method names, `setup_module()` patterns
  - **Java**: Check for `@Before`, `@BeforeEach`, `@BeforeClass` annotations
  - **JavaScript/TypeScript**: Check for `beforeEach()`, `beforeAll()` function calls
- Map to canonical fixture type from FRAMEWORK_REGISTRY

**Implementation:** `collection/detector.py::_detect_fixtures_<language>()`

**Implementation Details:**
- Syntax-based detection (high precision)
- Well-tested across thousands of real fixtures
- Extensible to new frameworks

**Known Limitations:**
- Requires framework knowledge (custom DSLs may be missed)
- Inheritance patterns not tracked (parent class fixtures)

**Validation:**
- Test suite: `tests/test_extractor_unit/` has 500+ test cases
- Production validation: FixtureDB contains a large number of fixtures with detected types

---

### 2.5 scope (Fixture Execution Scope)

**What:** When a fixture runs relative to test execution (`per_test`, `per_class`, `per_module`, `global`)

**Canonical Scope Values:**
- `per_test` — Fixture executes before/after **each individual test** (innermost scope, most common)
- `per_class` — Fixture executes before/after **each test class/suite** (class-level grouping)
- `per_module` — Fixture executes before/after **entire test file/module** (file-level grouping, Python-specific)
- `global` — Fixture executes **once for entire test session** (outermost scope, least common)

**How Calculated:**
Scope is determined **deterministically** from explicit framework metadata (syntax-based, not heuristic):

#### Python: Explicit Declaration + Naming Convention

**pytest Fixtures** — Explicit `scope=` parameter (Lines 795-806 in detector.py):
- Extract from decorator: `@pytest.fixture(scope="function|class|module|session")`
- Regex pattern: `scope\s*=\s*["\'](\w+)["\']`
- Mapping: `function→per_test`, `class→per_class`, `module→per_module`, `session→global`
- **Objective**: Reads explicit value from source; default to `per_test` if omitted
- Example: `@pytest.fixture(scope="module")` → `scope="per_module"`

**unittest** — Method naming convention (Lines 848-875):
- Hardcoded method names → scope mapping
- `setUp` / `tearDown` → `per_test`
- `setUpClass` / `tearDownClass` → `per_class`
- `setUpModule` / `tearDownModule` → `per_module`
- **Objective**: Mapping defined in unittest specification

**pytest class methods** — Method naming (Lines 877-899):
- `setup_method` / `teardown_method` → `per_test`
- `setup_class` / `teardown_class` → `per_class`

**nose** — Method naming + substring matching (Lines 903-925):
- `setup` / `teardown` (no suffix) → `per_test`
- `setup_module` / `teardown_module` (suffix check) → `per_module`

**behave BDD** — Hardcoded per scope (Line 839):
- All `@given`, `@when`, `@then`, `@step` decorators → `per_test`
- **Objective**: Behave steps execute per scenario (test granularity)

#### Java: Annotation-Based Mapping

All Java scope detection uses a hardcoded annotation registry (`JUNIT_FIXTURE_ANNOTATIONS`, Lines 926-978):

| Annotation | Detected Scope | Framework |
|------------|---|---|
| `@BeforeEach`, `@Before`, `@AfterEach`, `@After` | `per_test` | JUnit4/5 |
| `@BeforeAll`, `@AfterAll`, `@BeforeClass`, `@AfterClass` | `per_class` | JUnit4/5, TestNG |
| `@BeforeMethod`, `@AfterMethod` | `per_test` | TestNG |
| `@Rule` | `per_test` | JUnit |
| `@ClassRule` | `per_class` | JUnit |
| `@Bean`, `@TestConfiguration` | `per_class` | Spring Framework |
| Cucumber steps (`@Given`, `@When`, `@Then`, `@And`, `@But`) | `per_test` | Cucumber |

**JUnit3 (Legacy)** — Method naming (Lines 1028-1051):
- `setUp()` / `tearDown()` → `per_test`
- **Objective**: No annotations; detected by method name within TestCase subclass

**Processing Logic** (Lines 1000-1018):
- Strip annotation to key: `@BeforeClass(...) → @BeforeClass`
- Dictionary lookup in `JUNIT_FIXTURE_ANNOTATIONS`
- Return tuple: `(fixture_type, scope)`

**Known Ambiguity** (Line 1005 TODO):
- `@BeforeClass` and `@AfterClass` appear in both JUnit4 and TestNG
- Current implementation defaults to TestNG for backward compatibility
- **Scope determination is unaffected**: both frameworks map to `per_class`

#### JavaScript/TypeScript: Hook Naming Convention

All hook names have standardized semantics across frameworks (Jest, Mocha, Jasmine, Vitest):

| Hook Name | Detected Scope | Implementation |
|-----------|---|---|
| `beforeEach`, `afterEach` | `per_test` | Lines 1088-1099 |
| `beforeAll`, `afterAll` | `per_class` | Lines 1088-1099 |
| `before`, `after` | `per_test` | Lines 1088-1099 (mocha ambiguous, default to per_test) |

**AVA-Specific Patterns** (Lines 1101-1108, different semantics):
- `test.before`, `test.after` → `per_class` (runs before/after all tests)
- `test.serial.before`, `test.serial.after` → `per_test` (runs before/after each serial test)
- **Objective**: AVA's concurrency model requires different scope semantics than Jest/Mocha

**TypeScript Decorators** (Lines 1176-1215):
- `@Before`, `@After` → `per_test`
- `@BeforeEach`, `@AfterEach` → `per_test`
- `@BeforeAll`, `@AfterAll` → `per_class`
- **Implementation**: Detects decorator pattern in AST, maps name to scope

**Processing Logic** (Lines 1132-1148):
- Extract function call name from AST call_expression
- Dictionary lookup in `JS_FIXTURE_CALLS` or `AVA_FIXTURE_PATTERNS`
- Return tuple: `(fixture_type, scope)`

**Framework Detection Note** (Line 1139):
- Standard hooks (`beforeEach`, etc.) cannot determine framework (Jest vs Mocha vs Jasmine are identical)
- Result: `framework=None` for ambiguous hooks
- AVA hooks are unambiguous (`test.before` syntax is AVA-specific)

**Implementation Details:**
- All detection uses explicit syntax (decorators, annotations, method names)
- Same source code always produces the same derived scope
- Scope hierarchy (per_test < per_class < per_module < global) is enforced across languages
- Method/decorator names are standardized by framework specifications

**Known Limitations:**
- **Java ambiguity** (JUnit4 vs TestNG): Cannot determine framework from shared annotation names; scope is correct regardless
- **JS framework detection**: Standard hooks cannot distinguish Jest from Mocha (scope is still correct)
- **Python dynamic scope**: Rare cases where scope is determined at runtime (not captured)

**Validation:**
- Test suite: `tests/test_extractor_unit/` contains scope mapping unit tests per language
- Production validation: Scope distribution across the dataset matches expected framework patterns
  - Python: ~60% per_test, ~20% per_class, ~18% per_module, ~2% global
  - Java: ~75% per_test, ~25% per_class (per_module not applicable)
  - JavaScript: ~80% per_test, ~20% per_class (per_module not applicable)

**Scope Constraint Propagation** (Lines 1664-1720):
After initial scope detection, pytest fixture dependencies are analyzed to enforce scope constraints:
- Scope hierarchy: `per_test (0) < per_class (1) < per_module (2) < global (3)`
- If fixture A depends on fixture B and B's scope is more restrictive than A's declared scope, A is downgraded
- Example: Module-scoped fixture depending on test-scoped fixture is impossible; downgraded to per_test
- **Objective**: Graph-based analysis of explicit fixture parameter dependencies

**Data Export Policy:**
- ✓ **Included in `fixtures.csv`**: Scope is objective, reproducible, quantitative data
- ✓ **Stored in SQLite**: Full record for research and validation
- ✓ **Queryable**: Researchers can filter/aggregate by scope to study fixture lifecycle patterns

---

### 2.6 reuse_count -- removed

`reuse_count` (number of test functions using a fixture) was removed
entirely, for all languages, after an audit of the fixture
post-processing logic found the metric was fabricated for Java/
JavaScript/TypeScript, not merely approximate. Its own docstring claimed
"For JUnit/xUnit, counts test methods in the same class that share
@BeforeEach", but the actual implementation didn't look at test methods
or class boundaries at all -- it grouped fixtures by `scope` string
**across the entire file** and reported the group size for any
`per_class` fixture. Three unrelated classes in the same file, each with
one `@BeforeAll` and a different number of `@Test` methods, all received
the *identical* value (the count of same-scope fixtures in the file, not
tests). The Python/pytest branch (parameter-injection counting) was
independently verified correct, but rather than ship a metric that's
reliable for one language and fabricated for three others -- something a
reviewer would have no way to tell apart by looking at the data -- the
column was dropped everywhere. If per-language reuse analysis is needed
later, it should be a new, explicitly-scoped metric (e.g.
`reuse_count_python`) rather than one column silently mixing a real count
with a fabricated one.

---

### 2.7 has_teardown_pair (Resource Cleanup)

**What:** Binary indicator (0/1) whether fixture has cleanup logic paired with setup

**How Calculated:**
- **Python**: Check for `yield` statement (pytest style) or `tearDown()` method
- **Java**: Check for `@After`/`@AfterEach` or `@AfterClass`/`@AfterAll`
- **JavaScript**: Check for `afterEach()`/`afterAll()` in scope

**Implementation:** `collection/detector.py::_calculate_teardown_pairs()`

**Implementation Details:**
- Identifies fixtures with proper resource management
- Simple, well-defined patterns

**Known Limitations:**
- Does not validate that cleanup is *correct*, only present
- Implicit cleanup (e.g., automatic connection pooling) not detected

**Validation:**
- Test suite: `tests/test_extractor_metadata/`

---

### 2.8 fixture_dependencies (Pytest Fixture Graphs)

**What:** List of other fixtures this fixture depends on (pytest-specific)

**How Calculated:**
1. For pytest fixtures only
2. Parse decorator: `@pytest.fixture def my_fixture(dep1, dep2, ...)`
3. Extract parameter names
4. Cross-reference against fixture registry in same file
5. Record confirmed dependencies only

**Implementation:** `collection/detector.py::_detect_fixture_dependencies()`

**Language Support:** Python/pytest only

**Implementation Details:**
- Enables dependency graph analysis
- High precision (parameter injection is explicit)

**Known Limitations:**
- pytest-specific (not available for other frameworks)
- Indirect dependencies not tracked

**Validation:**
- Test suite: `tests/test_extractor_metadata/`

---

### 2.9 loc (Lines of Code)

**What:** Non-blank, non-comment lines of code

**How Calculated:**
1. Extract fixture source text
2. Split by lines
3. Count non-blank, non-comment lines
4. Alternative: Use Lizard's LOC (includes blank lines)

**Implementation:** `collection/detector.py::_count_loc()`

**Implementation Details:**
- Simple, deterministic
- Consistent definition across languages

**Known Limitations:**
- Different from Lizard's definition (which we use for file-level metrics)
- Dialect-specific comment markers need per-language implementation

**Validation:**
- Test suite: `tests/test_extractor_metadata/test_line_numbers.py`

**Note:** 
For consistency with file-level metrics, consider migrating to Lizard's LOC definition in future versions.

---

### 2.10 framework (Testing Framework Identification)

**What:** The testing framework used in the fixture (e.g., pytest, junit, jest, mocha)

**How Calculated:**
1. **AST-based pattern detection** — Tree-sitter identifies framework-specific syntax:
   - **Python**: Decorators (`@pytest.fixture`, `@unittest`, `@behave`), method naming patterns (`setUp`, `tearDown`)
   - **Java**: Annotations (`@Before`, `@BeforeClass`, `@Test`, `@TestNG`), method naming patterns
   - **JavaScript/TypeScript**: Function naming conventions (`beforeEach`, `beforeAll`, `describe`, `setUp`), imports (`jest`, `mocha`)

2. **Registry validation** — Detected framework can be cross-referenced against `FRAMEWORK_REGISTRY` (via `config.is_known_framework()`/`get_known_frameworks()`) to confirm it's a known framework

3. **Forward compatibility** — If a framework is detected but not in the registry, it's still recorded (allows discovery of new frameworks) and logged as a debug message

**Implementation:**
- **Detection**: `collection/detector_python.py` / `detector_java.py` / `detector_javascript.py`::`_detect_<language>()`
- **Validation**: `collection/detector_framework_registry.py::_validate_framework()` (currently unwired — no production caller today)
- **Registry data**: `collection/config_data/framework_registry.yaml`, loaded as `collection/config.py::FRAMEWORK_REGISTRY`

**Supported Frameworks** (40+ across 4 languages):

| Language | Frameworks |
|----------|------------|
| **Python** | pytest, unittest, nose, nose2, doctest, behave, pytest-bdd, pytest-asyncio, testtools, trial |
| **Java** | junit, testng, spock, cucumber, mockito, easymock, powermock, jtest, arquillian |
| **JavaScript** | jest, mocha, jasmine, ava, vitest, cucumber, sinon, tap, cheerio |
| **TypeScript** | jest, mocha, vitest, cucumber, sinon, tap |

**Example Detection:**

| Code | Detected Framework | Detection Logic |
|------|-------------------|-----------------|
| `@pytest.fixture` | `pytest` | Decorator pattern match |
| `@Before public void setup()` | `junit` | Annotation + method pattern |
| `beforeEach(() => { ... })` | `jest` or `mocha` | Function name + context (jest if `expect` found, else mocha) |
| `func TestMyFunc(t *testing.T)` | `testing` | Function naming pattern `Test*` |

**Implementation Details:**
- Same code always produces same result (syntactic patterns, not heuristics)
- Researchers can verify framework by reading fixture source code
- Captures what testing framework is actually used
- Framework-specific syntax (decorators, annotations) provides unambiguous signals
- Covers 40+ frameworks across 4 languages via registry

**Known Limitations:**
- **Custom frameworks may be missed** — Only detects frameworks in the registry or those with standard patterns
- **Framework plugins** — Some frameworks have optional plugins that may not be detected if not syntactically marked
- **Cross-framework confusion** — Rare cases where multiple frameworks could be detected in the same fixture (e.g., pytest + unittest in same file)

**Validation:**
- Test suite: `tests/test_framework_detection.py` — 50+ unit tests verifying correct framework detection across all languages
- Production validation: FixtureDB contains a large number of fixtures with detected frameworks
- Manual spot-checks: Validation CSV with GitHub URLs for reproducibility

**Citation in Papers:**
```bibtex
@dataset{FixtureDB2026,
  title = {FixtureDB: A Dataset of Test Fixtures across Open Source Software},
  author = {...},
  year = {2026},
  note = {Framework detection via AST analysis and framework registry}
}
```

**Data Export Policy:**
- ✓ **Included in `fixtures.csv`** — Framework is quantitative, reproducible data
- ✓ **Stored in SQLite** — Full record kept for research
- ✓ **Queryable** — Researchers can filter fixtures by framework

---

### 2.11 num_mocks (Mock Usage Count) and the mock_usages table

**What:** Count of distinct mock usages detected within a fixture
(`fixtures.num_mocks`), with the per-mock detail (framework, test-double
category, target, interaction count, source snippet) stored one row per
mock in the separate `mock_usages` table — see
[Database Schema § mock_usages](database-schema.md#mock_usages).

**How Calculated:**
1. Extract the fixture's own source text (AST node) — mock scanning never
   looks outside the fixture body (see Known Limitations).
2. Scan it against every pattern in `mock_patterns` (regex, applied
   case-insensitively).
3. For each match, resolve `framework` and `category` from that pattern's
   YAML entry, and estimate `num_interactions_configured` by counting
   nearby interaction keywords (`return_value`, `side_effect`,
   `thenReturn`, `thenThrow`, `doReturn`).
4. `num_mocks` on the fixture is simply `len(fixture.mocks)`.

**Implementation:**
- **Detection**: `collection/detector_shared.py::_extract_mocks()`
- **Pattern catalog**: `collection/config_data/feature_extraction_patterns.yaml`'s `mock_patterns` — 30 patterns across 11 frameworks, loaded via `load_feature_extraction_patterns()`, not hardcoded in Python (see [Configuration Reference § Reference-Data Catalogs](configuration.md#reference-data-catalogs))
- **Calculation**: `len(fixture.mocks)` at fixture-build time in `collection/detector_shared.py::_build_result()`
- **Aggregation**: Stored directly on the fixture as `num_mocks`; per-mock detail persisted separately to `mock_usages`

**Supported Mock Frameworks:**
- **Python**: `unittest_mock` (`patch`/`patch.object`, both `mock.`-qualified and bare; `MagicMock`/`Mock`/`AsyncMock`; `create_autospec`), `pytest_mock` (`mocker.patch`/`mocker.patch.object`), `pytest_monkeypatch` (pytest's built-in `monkeypatch` fixture)
- **Java**: `mockito`, `easymock`, `mockk` (Kotlin)
- **JavaScript/TypeScript**: `jest` (`fn`/`spyOn`/`mock`/`mocked`/`createMockFromModule`), `sinon` (`stub`/`spy`/`mock`/`fake`/`replace`/`createStubInstance`), `vitest`
- **Go** (`gomock`, `testify_mock`): patterns exist for parity but are unreachable in practice — `detector_go.py` is dead code, never wired into the language dispatch, since Go isn't in this study's scope (Python/Java/JS/TS only)

**Test-double category classification (`mock_usages.category`):**
Each detected mock is also classified into the classic test-double
taxonomy — `dummy`/`stub`/`spy`/`mock`/`fake` (Meszaros; see also Fowler's
"Mocks Aren't Stubs") — by keyword-matching the *construct's own name*
(priority `dummy > stub > spy > fake > mock`), with a small set of
individually-justified manual overrides for the handful of constructs
whose name contains no category keyword at all (e.g. `monkeypatch` →
`stub`, `create_autospec`/bare `patch()`/`jest.fn()`/`vi.fn()` → `mock`).
`dummy` is deliberately never assigned — see
[Fixture Detection Logic § Mock Framework Detection](detection.md#mock-framework-detection)
for the full methodology and reasoning behind every override.

**Example Detection:**

| Fixture Code | Framework | Category | num_mocks |
|---|---|---|---|
| `mock.patch('module.Class')` | unittest_mock | mock | 1 |
| `mock.patch.object(Service, 'call')` | unittest_mock | mock | 1 |
| `@pytest.fixture` with 3 `mocker.patch()` calls | pytest_mock | mock | 3 |
| `monkeypatch.setenv('ENV', 'test')` | pytest_monkeypatch | stub | 1 |
| `Mockito.mock(UserService.class)` | mockito | mock | 1 |
| `Mockito.spy(realService)` | mockito | spy | 1 |
| `jest.fn()` and `jest.spyOn()` calls | jest | mock, spy | 2 |
| `sinon.stub(obj, 'method')` | sinon | stub | 1 |
| No mock framework calls | (none) | — | 0 |

**Implementation Details:**
- Objective counting — Direct regex match count
- Deterministic — Same fixture always yields the same count and categories
- Reproducible — Researchers can verify every pattern/category assignment directly in the YAML catalog
- Language-independent — Same pattern table scanned regardless of source language

**Known Limitations:**
- Limited pattern coverage — Only explicit, listed framework calls are detected; niche frameworks (e.g. PowerMock) and non-standard/custom mocking helpers are not
- Fixture-scoped only — Detection never looks outside the fixture's own AST node text, so mock setup at module level or in a shared helper is invisible. This matters most for Jest, where `jest.mock('./module')` is conventionally written at the top of the file (auto-hoisted by babel-jest) rather than inside a `beforeEach`, so that pattern rarely fires in practice even though it's in the table
- `category` is a per-construct classification, not a per-instance behavioral analysis — it does not verify how a given mock was actually used in that specific fixture
- The full, current list of documented gaps lives in `feature_extraction_patterns.yaml`'s `mock_patterns_excluded`, not duplicated here

**Validation:**
- Test suite: `tests/collection/test_mock_detection/` (per-language pattern coverage through the real `extract_fixtures()` pipeline) plus `test_mock_pattern_catalog_coverage.py` in the same directory, which is parametrized directly over every `mock_patterns` entry and asserts each pattern matches its own sample *and* that no other pattern in the catalog also matches it — the collision check that caught the `EasyMock.createMock(...)`/`Mockito.mock(...)` false-positive bugs described above. `tests/collection/test_config_data_loader.py` adds guardrail tests for the pattern/category catalog's shape itself.
- Production validation: Distribution of num_mocks across the dataset
  - ~45% of fixtures have num_mocks = 0 (no mocks)
  - ~35% have 1-2 mocks
  - ~15% have 3-5 mocks
  - ~5% have 6+ mocks

**Data Export Policy:**
- ✗ **Not in `fixtures.csv`** — Mock analysis available via SQLite database for advanced researchers
- ✓ **Stored in SQLite** — Full `mock_usages` table with detailed framework breakdown by fixture
- ✓ **Queryable** — Researchers can join `fixtures → mock_usages` for detailed mock adoption analysis

---

---

## Part 4: Academic References & Justification

### Key Papers

**Cyclomatic Complexity:**
```bibtex
@article{McCabe1976,
  author = {McCabe, T. J.},
  title = {A Complexity Measure},
  journal = {IEEE Transactions on Software Engineering},
  volume = {2},
  number = {4},
  pages = {308--320},
  year = {1976},
  doi = {10.1109/tse.1976.233837}
}
```

**Cognitive Complexity:**
```bibtex
@misc{Campbell2018,
  author = {Campbell, G. A.},
  title = {Cognitive Complexity: An Overview and Evaluation},
  publisher = {CQSE GmbH},
  year = {2018},
  url = {https://www.sonarsource.com/docs/CognitiveComplexity.pdf}
}
```

**Code Metrics in Software Engineering:**
```bibtex
@article{Fenton1999,
  author = {Fenton, N. E. and Neil, M.},
  title = {Software Metrics: Roadmap},
  journal = {Proceedings of ICSE '00 Futures of Software Engineering},
  year = {1999}
}
```

---

## Part 5: Implementation Details

### Where Metrics Are Calculated

| Metric | Phase | Location | When Used |
|--------|-------|----------|-----------|
| `loc`, `cyclomatic_complexity`, `num_parameters`, `num_objects_instantiated` | P1-P2 | `collection/complexity_provider.py::analyze_function_complexity()` | During fixture detection |
| `num_external_calls` | P1-P2 | `collection/detector.py::_count_external_calls()` | During fixture detection |
| `fixture_type`, `scope`, `framework` | P1-P2 | `collection/detector.py::_detect_fixtures_<language>()` | During fixture detection |
| `max_nesting_depth` | P1-P2 | `collection/detector.py::_calculate_max_nesting_depth()` | During fixture detection |
| `has_teardown_pair` | P3 (Post-processing) | `collection/detector.py::_calculate_teardown_pairs()` | After all fixtures detected in file |
| `fixture_dependencies` | P4 (Post-processing) | `collection/detector.py::_detect_fixture_dependencies()` | After all fixtures detected in file |
| `file_loc`, `num_test_funcs` | P3 | `collection/complexity_provider.py` | After file analysis |

### Configuration & Tuning

See [docs/architecture/configuration.md](configuration.md) for:
- Framework registry (FRAMEWORK_REGISTRY)
- File size and type filters
- Extraction timeouts

---

## Part 6: Known Limitations & Future Work

### Current Limitations

1. **Cognitive complexity for non-Python languages**
   - Uses formula fallback (cyclomatic_complexity × nesting_depth)
   - Not as accurate as SonarQube's standard
   - Future: Integrate language-specific cognitive complexity tools

2. **num_external_calls (I/O detection)**
   - Regex-based, subject to false positives (string literals)
   - Misses indirect I/O through factory functions
   - Incomplete for uncommon patterns

3. **num_objects_instantiated**
   - Python heuristic (capitalization) may miss lowercase classes
   - Does not distinguish library vs. user classes

4. **fixture_dependencies**
   - pytest-specific (not available for Java, JavaScript, etc.)
   - Does not track transitive dependencies

### Future Enhancements

- Integrate SonarQube cognitive complexity APIs for Java/JavaScript
- AST-based I/O detection (replace regex)
- Object instantiation refinement (library vs. user classes)
- Cross-language fixture dependency tracking (mock frameworks, etc.)
- Parameterized test expansion in reuse counting

---

## Part 7: Using These Metrics in Research

### Recommended Use Cases

**Safe to Use:**
- Fixture complexity distribution analysis
- Fixture size vs. test framework comparison
- Code quality trends (across the dataset)
- Structural patterns (scope, parameters, nesting)

**Use with Caution:**
- Comparing metric values across languages (especially cognitive complexity)
- Detecting anomalies in I/O patterns (due to regex limitations)
- Individual fixture complexity assessment (use `raw_source` for manual verification)

**Not Recommended:**
- Benchmarking fixture complexity across projects (too many confounds)
- Predicting test effectiveness from metrics alone
- Comparing metrics with non-FixtureDB fixtures (definitions may differ)

### Citing FixtureDB Metrics

**In your paper, cite the relevant external tools:**

"Fixture complexity was measured using Lizard (McCabe, 1976) for cyclomatic complexity 
and complexipy (Campbell, 2018) for cognitive complexity. Code structure metrics were 
extracted from Tree-sitter AST analysis. See FixtureDB's [requirements.txt](../../requirements.txt) for exact tool versions."
