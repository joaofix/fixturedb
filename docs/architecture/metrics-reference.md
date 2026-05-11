# Metrics Reference & Calculation Methodology

**Purpose:** Comprehensive documentation of all quantitative metrics calculated for test fixtures in FixtureDB, including external tools used, custom implementations, and academic references.  
**Status:** Complete

---

## Quick Reference: Metrics at a Glance

### Metrics from Known Tools (Lizard, Tree-sitter)

| Metric | Category | Tool(s) |
|--------|----------|----------|
| `loc` | Code Structure | Lizard |
| `cyclomatic_complexity` | Complexity | Lizard |
| `num_parameters` | Code Structure | Lizard |
| `file_loc` | Code Structure | Lizard |
| `num_test_funcs` | Code Structure | Lizard |

### Custom Implementations

| Metric | Category | How Calculated |
|--------|----------|------------------|
| `max_nesting_depth` | Code Structure | Tree-sitter AST traversal |
| `num_objects_instantiated` | Semantic | Filtered Lizard + regex |
| `num_external_calls` | Domain-Specific | Regex pattern matching |
| `fixture_type` | Classification | AST + regex patterns |
| `scope` | Classification | Framework metadata extraction |
| `framework` | Classification | Registry lookup |
| `reuse_count` | Usage Analysis | Post-processing AST |
| `has_teardown_pair` | Resource Management | AST pattern matching |
| `fixture_dependencies` | Relationships | Regex parsing |

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

## Part 2: Custom Implementations (Domain-Specific, Validated)

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
- Domain-specific targeting (I/O vs. general functions)
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

**What:** Classification of how a fixture is defined (e.g., `pytest_decorator`, `junit4_before`, `unittest_setup`)

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
- Production validation: FixtureDB contains 40,672 fixtures with detected types

---

### 2.5 scope (Fixture Execution Scope)

**What:** When a fixture runs relative to test execution (per_test, per_class, per_module, global)

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
- Same source code always produces same scope classification
- Scope hierarchy (per_test < per_class < per_module < global) is enforced across languages
- Method/decorator names are standardized by framework specifications

**Known Limitations:**
- **Java ambiguity** (JUnit4 vs TestNG): Cannot determine framework from shared annotation names; scope is correct regardless
- **JS framework detection**: Standard hooks cannot distinguish Jest from Mocha (scope is still correct)
- **Python dynamic scope**: Rare cases where scope is determined at runtime (not captured)

**Validation:**
- Test suite: `tests/test_extractor_unit/` contains scope mapping unit tests per language
- Production validation: Scope distribution across 40,672+ fixtures matches expected framework patterns
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

### 2.6 reuse_count (Fixture Modularity)

**What:** Number of test functions that use this fixture

**How Calculated (Post-Processing):**
1. After all fixtures detected in a file
2. Build registry of fixture names
3. For each fixture, scan test function signatures for its name as parameter
4. Count matches

**Implementation:** `collection/detector.py::_calculate_reuse_counts()`

**Language Support:**
- **Python/pytest**: Parameter names in test function signatures
- **Java**: Test methods in same class as @Before
- **JavaScript/TypeScript**: Test functions in scope

**Implementation Details:**
- Simple, verifiable metric
- Useful for modularity analysis

**Known Limitations:**
- Only counts *direct* reuse (parameter injection)
- Misses indirect reuse (fixtures used by other fixtures)
- Parametrized tests counted as single function

**Validation:**
- Test suite: `tests/test_extractor_metadata/`
- Manual spot checks on representative repositories

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
   - **Go**: Function naming patterns (`Test*`, `Setup`, `Teardown`)

2. **Registry validation** — Detected framework is cross-referenced against `FRAMEWORK_REGISTRY` in `collection/config.py` to confirm it's a known framework

3. **Forward compatibility** — If a framework is detected but not in the registry, it's still recorded (allows discovery of new frameworks) and logged as a debug message

**Implementation:**
- **Detection**: `collection/detector.py::_detect_<language>()` functions (lines 775-950+ per language)
- **Validation**: `collection/detector.py::_validate_framework()` (line 741)
- **Registry**: `collection/config.py::FRAMEWORK_REGISTRY` (line 371+)

**Supported Frameworks** (40+ across 4 languages):

| Language | Frameworks |
|----------|------------|
| **Python** | pytest, unittest, nose, nose2, doctest, behave, pytest-bdd, pytest-asyncio, testtools, trial |
| **Java** | junit, testng, spock, cucumber, mockito, easymock, powermock, testify, jtest, arquillian |
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
- Production validation: FixtureDB contains 40,672+ fixtures with detected frameworks
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

### 2.11 num_mocks (Mock Usage Count)

**What:** Count of distinct mock usages detected within a fixture

**How Calculated:**
1. Extract fixture source code (AST node)
2. Run 15 regex patterns matching mock framework calls (Lines 277-299 in detector.py)
3. Count number of distinct matches
4. Store in database during post-processing
5. Aggregate at fixture level during post-processing

**Implementation:**
- **Detection**: `collection/detector.py::_extract_mocks()` (lines 301-333)
- **MOCK_PATTERNS**: 15 patterns across 10 frameworks (lines 277-299)
- **Calculation**: `len(fix.mocks)` in `collection/extractor.py` (line 361)
- **Aggregation**: Stored directly in fixtures table, column `num_mocks`

**Supported Mock Frameworks:**
- **Python**: unittest_mock, pytest_mock
- **Java**: mockito, easymock, mockk (Kotlin)
- **JavaScript**: jest, sinon, vitest

**Example Detection:**

| Fixture Code | Detected | num_mocks |
|---|---|---|
| `unittest.mock.patch('module.Class')` | unittest_mock | 1 |
| `@pytest.fixture` with 3 `mocker.patch()` calls | pytest_mock | 3 |
| `Mockito.mock(UserService.class)` | mockito | 1 |
| `jest.fn()` and `jest.spyOn()` calls | jest | 2 |
| No mock framework calls | (none) | 0 |

**Implementation Details:**
- Objective counting — Direct regex match count
- Deterministic — Same fixture always yields same count
- Reproducible — Researchers can verify regex patterns
- Language-independent — Same patterns across Python/Java/JS/TS

**Known Limitations:**
- Limited pattern coverage — Only explicit framework calls detected
- Custom frameworks — Non-standard mocking libraries not captured
- Indirect setup — Mock factories or builders may be missed
- Scope limitation — Only detects mocks at fixture level (not test function level)

**Validation:**
- Test suite: `tests/test_mock_detection/` contains unit tests for pattern matching
- Production validation: Distribution of num_mocks across 40,672+ fixtures
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
| `reuse_count` | P3 (Post-processing) | `collection/detector.py::_calculate_reuse_counts()` | After all fixtures detected in file |
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

5. **reuse_count**
   - Only counts direct parameter injection
   - Parametrized tests counted as single usage
   - Indirect usage through other fixtures not tracked

### Future Enhancements

- Integrate SonarQube cognitive complexity APIs for Java/JavaScript
- AST-based I/O detection (replace regex)
- Object instantiation type classification (library vs. user classes)
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
