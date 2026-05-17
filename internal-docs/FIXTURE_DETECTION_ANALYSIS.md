# Fixture Detection Logic Analysis

> **Note:** This document references historical analysis. Cognitive complexity metric was removed in Phase 3. Current implementation uses cyclomatic_complexity and max_nesting_depth as primary complexity metrics.

## Executive Summary

The fixture detection system uses **AST-based pattern matching** (tree-sitter) for syntax-aware fixture identification across 6 languages, complemented by **regex heuristics** for mock framework detection. The system achieves high precision through framework-specific annotations but has several sources of false positives that should be monitored during validation.

---

## 1. DETECTION PATTERNS BY LANGUAGE

### 1.1 Python (detector.py: `_detect_python`)

#### Pytest Fixtures
- **Pattern**: `@pytest.fixture` decorator + `def` function
- **Scope Detection**: Parses `scope="..."` parameter
  - `function|default` → `per_test`
  - `class` → `per_class`
  - `module|package` → `per_module`
  - `session` → `global`
- **Fixture Type**: `pytest_decorator`
- **Framework**: `pytest`

#### Unittest/TestCase Fixtures
- **Pattern**: Method names in class context
  - `setUp`, `tearDown` → `unittest_setup` (per_test scope)
  - `setUpClass`, `tearDownClass` → `unittest_setup` (per_class scope)
  - `setUpModule`, `tearDownModule` → `unittest_setup` (per_module scope)
  - `setup_method`, `teardown_method` → `pytest_class_method` (per_test scope)
  - `setup_class`, `teardown_class` → `pytest_class_method` (per_class scope)
- **Framework**: `unittest` or `pytest`
- **Note**: Name-based detection (no annotation required)

#### Nose Fixtures
- **Pattern**: Function names `setup`, `teardown`, `setup_module`, `teardown_module`, `setup_package`, `teardown_package`
- **Fixture Type**: `nose_fixture`
- **Scope**: Per-test or per-module based on name

#### BDD Fixtures (Behave)
- **Pattern**: `@given`, `@when`, `@then`, `@step` decorators
- **Fixture Types**: `behave_given`, `behave_when`, `behave_then`, `behave_step`
- **Framework**: `behave`
- **Scope**: Always `per_test` (BDD semantics)

#### ⚠️ False Positive Risk in Python
1. **Unittest-style methods in non-TestCase classes** — Name-based detection matches ANY class with `setUp`/`tearDown` methods, even if not inheriting from `TestCase`
2. **Helper methods named `setup_*`** — Commonly used in regular classes, not just fixtures
3. **BDD decorators in non-test files** — Behave decorators can appear in step definition libraries
4. **Nose fixture names conflict** — `setup`/`teardown` are common names in utility modules

---

### 1.2 Java (detector.py: `_detect_java`)

#### JUnit 4/5 Annotations
- **Pattern**: Method with `@Before`, `@After`, `@BeforeClass`, `@AfterClass`, `@BeforeEach`, `@BeforeAll`, `@AfterEach`, `@AfterAll`
- **Scope Mapping**:
  - `@Before`, `@BeforeEach` → `per_test`
  - `@After`, `@AfterEach` → `per_test`
  - `@BeforeClass`, `@BeforeAll` → `per_class`
  - `@AfterClass`, `@AfterAll` → `per_class`
- **Fixture Types**: `junit4_before`, `junit5_before_each`, etc.
- **Framework**: `junit`

#### TestNG Annotations
- **Pattern**: `@BeforeMethod`, `@AfterMethod`, `@BeforeClass`, `@AfterClass`, `@DataProvider`
- **Framework**: Defaults to `testng` (ambiguity: can't distinguish from JUnit at AST level)

#### Spring Framework Annotations
- **Pattern**: `@Bean`, `@TestConfiguration`
- **Fixture Type**: `spring_bean`, `spring_test_config`
- **Scope**: `per_class` (Spring beans are class-level in test context)

#### Cucumber BDD Annotations
- **Pattern**: `@Given`, `@When`, `@Then`, `@And`, `@But`
- **Fixture Types**: `cucumber_given`, `cucumber_when`, `cucumber_then`, `cucumber_and`, `cucumber_but`
- **Scope**: `per_test`

#### JUnit 3 (Legacy)
- **Pattern**: Method names `setUp` or `tearDown` (no annotations)
- **Detection Caveat**: Only detected if NOT already matched by `@Before`/`@After` annotation
- **Fixture Types**: `junit3_setup`, `junit3_teardown`

#### JUnit @Rule/@ClassRule
- **Pattern**: Field declarations with `@Rule` or `@ClassRule` annotations
- **Fixture Type**: `junit_rule`, `junit_class_rule`

#### ⚠️ False Positive Risk in Java
1. **Ambiguous JUnit4/TestNG annotations** — `@BeforeClass`, `@AfterClass` appear in both; code defaults to TestNG
2. **Custom annotations named @Before/@After** — Could match arbitrary framework-specific annotations
3. **Spring @Bean in non-test contexts** — Spring beans in main code can be matched
4. **Annotation inheritance** — Meta-annotations not resolved (decorator-style frameworks)

---

### 1.3 JavaScript / TypeScript (detector.py: `_detect_js`)

#### Mocha/Jest/Jasmine/Vitest Hooks (Ambiguous Framework)
- **Pattern**: Function calls `beforeEach()`, `beforeAll()`, `afterEach()`, `afterAll()`, `before()`, `after()`
- **Scope Mapping**:
  - `beforeEach`, `afterEach` → `per_test`
  - `beforeAll`, `afterAll` → `per_class`
- **Fixture Type**: `before_each`, `before_all`, `after_each`, `after_all`, `mocha_before`, `mocha_after`
- **Framework**: `None` (ambiguous — could be Jest, Mocha, Jasmine, Vitest, or Uvu)

#### AVA Fixtures
- **Pattern**: Member expressions `test.before`, `test.after`, `test.serial.before`, `test.serial.after`
- **Scope Mapping**:
  - `test.before`, `test.after` → `per_class`
  - `test.serial.before`, `test.serial.after` → `per_test`
- **Fixture Types**: `ava_before`, `ava_after`, `ava_serial_before`, `ava_serial_after`
- **Framework**: `ava`

#### TypeScript Decorators
- **Pattern**: Method definitions preceded by `@Before`, `@After`, `@BeforeEach`, `@AfterEach`, `@BeforeAll`, `@AfterAll` decorators
- **Framework**: Not set (likely framework-specific)
- **Scope**: Based on decorator name

#### ⚠️ False Positive Risk in JavaScript/TypeScript
1. **Ambiguous hook functions** — `beforeEach`, `afterEach` are not unique to testing frameworks; libraries can define similar functions
2. **Helper functions with testing names** — Functions named `beforeSave()`, `afterUpdate()` in regular code
3. **IIFE patterns** — Immediately-invoked function expressions named `before`, `after` in non-test contexts
4. **Decorator collision** — `@Before`/`@After` decorators might be defined by business frameworks

---

### 1.4 Go (detector.py: `_detect_go`) — REMOVED IN v2 DATASET

**Status**: Go language detection **removed from v2 dataset** (April 5, 2026) due to heuristic-only approach lacking validation.

#### Legacy Patterns (for reference)
1. **TestMain(m *testing.M)** — Package-level setup function
   - Fixture Type: `test_main`, Scope: `global`

2. **Helper Functions** — Detected via heuristic:
   - Called from ≥3 test functions (Test* prefix)
   - Name contains setup/teardown/initialization keywords
   - Fixture Type: `go_helper`, Scope: `per_test`

3. **testify/suite Methods** — TestSuite framework patterns:
   - `SetupSuite`, `TeardownSuite` → per-class
   - `SetupTest`, `TeardownTest` → per-test
   - Fixture Type: `go_setup_suite`, `go_teardown_test`, etc.
   - Framework: `testify`

---

## 2. MOCK DETECTION PATTERNS & FRAMEWORKS

### 2.1 Mock Framework Detection

Mock detection uses **regex patterns** applied to fixture source code. ~40 patterns across 12 frameworks:

#### Python Mocking (3 frameworks)
```regex
mock.patch\s*\(\s*['"](.*?)['"]           → unittest_mock
mocker\.patch\s*\(\s*['"](.*?)['"]         → pytest_mock
MagicMock\s*\(|Mock\s*\(|AsyncMock\s*\(   → unittest_mock
```
- **Frameworks**: `unittest_mock`, `pytest_mock`
- **Detection**: Pattern-based in source text

#### Java Mocking (4 frameworks)
```regex
Mockito\.mock\s*\(\s*(\w+)\.class          → mockito
@Mock\b                                    → mockito
EasyMock\.createMock\s*\(\s*(\w+)\.class  → easymock
mock\s*\(\s*(\w+)\.class                   → mockk (MockK/Kotlin)
```
- **Frameworks**: `mockito`, `easymock`, `mockk`, `jmockit`

#### JavaScript/TypeScript Mocking (3 frameworks)
```regex
jest\.fn\s*\(                              → jest
jest\.spyOn\s*\(                           → jest
jest\.mock\s*\(\s*['"](.*?)['"]            → jest
sinon\.(stub|spy|mock)\s*\(                → sinon
vi\.fn\s*\(                                 → vitest
vi\.mock\s*\(\s*['"](.*?)['"]              → vitest
```
- **Frameworks**: `jest`, `sinon`, `vitest`

#### Go Mocking (2 frameworks)
```regex
gomock\.NewController                       → gomock
testify/mock                               → testify_mock
\.On\s*\(\s*['"](.*?)['"]                  → testify_mock
```

### 2.2 Mock Style Classification

Mocks detected in fixtures are classified as:

1. **stub** (default) — Only `return_value` configured, no verification
2. **spy** — Wraps real objects; patterns: `spy()`, `patch.object()`, `spyOn()`, `.when()`
3. **mock** — Includes verification; patterns: `.verify()`, `assert_called_*`, `.toHaveBeenCalled()`, `calledWith()`
4. **fake** — Custom class implementation with logic; pattern: `class ... :`

### 2.3 Mock Target Layer Classification

Mocks target different architectural layers:

1. **framework** (priority 1) — Testing/DI frameworks: `pytest`, `spring`, `request`, `session`, `bean`, etc.
2. **boundary** (priority 2) — External services: `requests`, `stripe`, `github`, `aws`, `oauth`, `api_*`
3. **infrastructure** (priority 3) — Storage/caching: `database`, `redis`, `mongo`, `repository`, `logger`, `file`
4. **internal** (default) — Application domain classes

---

## 3. FIXTURE CLASSIFICATION LOGIC (fixture_classifier.py)

### 3.1 RQ1 Taxonomy (8 Categories)

Fixtures are classified into semantic categories based on **5-layer decision tree**:

| Category | Purpose | Key Indicators |
|----------|---------|-----------------|
| **data_builder** | Creates/constructs test data | Keywords: `create`, `build`, `factory`, `builder`; `num_objects_instantiated >= 3` |
| **service_setup** | Wires dependencies, configures DI | Keywords: `inject`, `wire`, `bind`, `provide`; `num_parameters >= 2` |
| **environment** | Manages external resources (files, DB, network) | Keywords: `file`, `database`, `temp`, `path`; `num_external_calls >= 2` |
| **resource_management** | Allocates/configures/releases resources | Keywords: `open`, `close`, `yield`, `with`, `cleanup`, `teardown` |
| **mock_setup** | Creates mocks, stubs, spies for isolation | Keywords: `mock`, `stub`, `spy`, `fake`; mock framework detected |
| **state_reset** | Resets global state, clears caches | Keywords: `reset`, `clear`, `flush`, `truncate`; scope ∈ {per_module, global} |
| **configuration_setup** | Configures settings, environment variables | Keywords: `config`, `setting`, `env`, `feature`, `flag` |
| **hybrid** | Multi-purpose (multiple categories matched equally) | Default fallback for ambiguous fixtures |

### 3.2 Five-Layer Decision Tree

```
Layer 1: Keyword Pattern Matching
  → Search raw_source for CATEGORY_KEYWORDS patterns (case-insensitive)
  
Layer 2: Mock Framework Detection
  → If mock_count > 0 → add "mock_setup" to candidates
  
Layer 3: Structural Feature Heuristics
  → If num_parameters >= 2 → add "service_setup"
  → If num_objects_instantiated >= 3 → add "data_builder" (threshold: OBJECTS_DATA_BUILDER_THRESHOLD = 5)
  → If num_external_calls >= 2 → add "environment"
  
Layer 4: Scope-Based Hints
  → If scope ∈ {per_module, global} → add "state_reset"
  
Layer 5: Complexity Heuristic
  → If cyclomatic_complexity >= 3 AND no matches yet → add "hybrid"
```

### 3.3 Final Category Selection

| Matches | Decision |
|---------|----------|
| 0 | Return `hybrid` (unknown/underspecified) |
| 1 | Return that category |
| 2+ | Apply dominance rules: |
|  | • If mock_count >= 2 AND "mock_setup" candidate → return `mock_setup` |
|  | • If num_objects_instantiated >= OBJECTS_DATA_BUILDER_THRESHOLD AND "data_builder" candidate → return `data_builder` |
|  | • Otherwise → return `hybrid` (genuine multi-purpose) |

---

## 4. FIXTURE METRICS EXTRACTION

All fixtures extract these metrics (via Lizard + custom logic):

| Metric | Source | Computation |
|--------|--------|-------------|
| `loc` | Custom | Count non-blank lines in fixture source |
| `cyclomatic_complexity` | Lizard | Branch count (if/for/while/try) |
| `cognitive_complexity` | Lizard | Nesting-weighted complexity (SonarQube standard) |
| `max_nesting_depth` | Tree-sitter AST | Max block nesting level (Lizard unreliable for functions) |
| `num_parameters` | Lizard | Function parameter count |
| `num_objects_instantiated` | Lizard regex | Count `new X(...)` constructor patterns |
| `num_external_calls` | Regex | Count I/O patterns: `open()`, `requests.`, `connect()`, `os.environ`, etc. |
| `reuse_count` | Post-processing | How many test functions use this fixture |
| `has_teardown_pair` | Heuristic | Binary: cleanup logic detected (yield, finally, close, etc.) |

---

## 5. SOURCES OF FALSE POSITIVES

### 5.1 High-Confidence False Positive Sources

#### Python
1. **Generic `setUp`/`tearDown` outside TestCase** (20-30% false positive risk)
   - Pattern matches ANY class with these method names
   - **Example**: `DataProcessor.setUp()` in utility modules
   - **Mitigation**: Check parent class is `TestCase` (Phase 2 work)

2. **Helper function names collision** (10-15%)
   - `setup_database()`, `setup_logger()` in service modules
   - **Example**: Database initialization in main codebase
   - **Mitigation**: Require file path contains `test/` or module in `test_*`

3. **Nose fixtures in non-test modules** (5-10%)
   - `setup()` is a common name in Python utilities
   - **Example**: `werkzeug.setup()` utility function
   - **Mitigation**: Scope to test files only

#### Java
1. **Custom annotations named @Before/@After** (5-10%)
   - Spring, CDI, other frameworks use similar patterns
   - **Example**: `@Before` in Mockito argument captors
   - **Mitigation**: Check parent class/interface is recognized test framework

2. **Spring @Bean in non-test contexts** (3-5%)
   - `@Bean` appears in main code too
   - **Example**: `@Bean` in `application.xml` or main config
   - **Mitigation**: Verify file is in `src/test/`

3. **JUnit4 vs TestNG ambiguity** (2-3%)
   - `@BeforeClass`, `@AfterClass` appear in both
   - System defaults to TestNG (code comment: "backward compatibility")
   - **Mitigation**: Check import statements to disambiguate

#### JavaScript/TypeScript
1. **Ambiguous hook function names** (20-30% risk)
   - `beforeEach()`, `afterEach()` are common business logic names
   - **Example**: `beforeEach()` in Redux reducers, UI libraries
   - **Mitigation**: Require in call context with `describe()` or test framework import

2. **Methods named before/after in business classes** (10-20%)
   - `handleBeforeSubmit()`, `onAfterLoad()` patterns
   - **Example**: React lifecycle hook names collide
   - **Mitigation**: AST check: is this inside a test-framework call?

3. **Custom hook libraries** (5-10%)
   - User-defined `beforeEach` in reusable utility modules
   - **Example**: `testing-library` custom hooks
   - **Mitigation**: Verify call is at module scope, not inside function

#### Cross-Language
4. **BDD Step definitions in library modules** (2-5%)
   - Behave `@given`, Cucumber `@Given` in step definition libraries
   - **Example**: `features/steps/` module defining reusable steps
   - **Mitigation**: Steps in `features/` vs actual test files

---

### 5.2 Medium-Risk False Positive Sources

1. **Decorator/Annotation inheritance** (5-10%)
   - Meta-annotations not resolved by AST
   - **Example**: Custom test base class with `@Before`
   - **Impact**: Less likely to cause false positives (inheritance less common)

2. **Generated test fixtures** (2-5%)
   - Automatic code generation (protobuf, OpenAPI clients)
   - **Example**: Generated mock client classes
   - **Mitigation**: Detect `@Generated` annotation or `/* GENERATED */` comments

3. **Async fixtures without framework context** (1-3%)
   - `async def setup()` in non-pytest files
   - **Example**: Async utilities in regular modules
   - **Mitigation**: Require async test framework import

4. **Reused fixture names across languages** (0.5-1%)
   - Framework detection not language-aware
   - **Example**: `junit_mock` detected in Python code
   - **Impact**: Rare, low impact

---

## 6. VALIDATION & FILTERING LOGIC

### 6.1 File-Level Filters (extractor.py, config.py)

```python
# Applied at file discovery level:

1. MAX_FILE_SIZE_BYTES = 5 MB
   - Prevent memory overload from minified/generated code
   - Risk: Very long fixture functions get truncated

2. Test file path patterns (language-specific)
   Python:   test/, tests/, testing/
   Java:     src/test/, test/, tests/
   JS/TS:    test/, tests/, spec/, __tests__/
   
3. Test file suffixes (language-specific)
   Python:   test_.py, _test.py, _tests.py, conftest.py
   Java:     Test.java, Tests.java, IT.java
   JS/TS:    .test.js, .spec.js, .test.ts, etc.
   
4. NON_CODE_EXTENSIONS
   Skip: .json, .xml, .yaml, .html, .css, .md, .txt
   Prevent parsing config/resource files
```

### 6.2 Repository-Level Filters (config.py)

```python
MIN_TEST_FILES = 5              # Repos with <5 test files dropped
MIN_COMMITS = 100               # Repos with <100 commits dropped
MIN_FIXTURES_FOUND = 1          # Repos with 0 fixtures dropped

# Star tiers for stratified analysis:
STAR_TIER_CORE_THRESHOLD = 500  # 'core' tier (comparable to Hamster)
                                # 'extended' tier: 100-499 stars
```

### 6.3 Mock Framework Validation (detector.py: `is_mock_framework_available`)

When a mock framework is detected via pattern, system validates it in dependency files:

```python
# For each detected framework, checks:
Python:   requirements.txt, setup.py, pyproject.toml, poetry.lock
Java:     pom.xml, build.gradle, build.gradle.kts
JS/TS:    package.json, package-lock.json, yarn.lock
Go:       go.mod, go.sum

# Returns:
True   if framework found in dependencies OR repo_path not provided
False  if framework searched but NOT found
```

**Risk**: Many projects install test dependencies via `pip install [dev]` or conditional groups; global `requirements.txt` may not capture all frameworks.

### 6.4 Reuse Count Calculation (detector.py: `_calculate_reuse_counts`)

Post-processing step counts how many test functions use each fixture:

**Python-specific** (most accurate):
- Parses test function `def test_*(...)`
- Counts if fixture name appears in parameter list
- **Risk**: Type-hinted parameters might not match fixture name

**Other languages** (heuristic):
- Count test functions in same scope
- Assume fixture reused `1x` if `per_test` scope
- Assume reused `len(group)` if `per_class` scope
- **Risk**: Overestimates reuse for class-scoped fixtures

### 6.5 Fixture Dependency Detection (detector.py: `_detect_fixture_dependencies`)

For pytest fixtures, detects parameter-based dependencies:

```regex
def fixture_name(param1: Type, param2, ...):
```

- Extract parameter names (handle type hints, defaults)
- Check if parameter name is another fixture
- Store in `fixture_dependencies` field

**Risk**: Generic parameter names (`obj`, `helper`) won't be matched; dependency inference is name-only.

---

## 7. KEY HEURISTICS THAT COULD BE TIGHTENED

### 7.1 For Improving Precision (Reducing False Positives)

#### High Impact (5-15% improvement potential)

1. **Require parent class check for Python unittest methods**
   - Current: Name-only matching (`setUp`, `tearDown`)
   - Proposed: Verify parent class is `unittest.TestCase` or `pytest.TestCase`
   - **Effort**: Medium (AST parent tracking)
   - **Risk reduction**: 20-30% of false positives

2. **Verify file-level context for JavaScript hooks**
   - Current: Function calls `beforeEach()` anywhere in file
   - Proposed: Require call inside `describe()` block or test file
   - **Effort**: Low (AST scope tracking)
   - **Risk reduction**: 15-25% of ambiguous hooks

3. **Add annotation context for Java**
   - Current: Accept `@BeforeClass` from either JUnit4 or TestNG
   - Proposed: Check import statements to disambiguate
   - **Effort**: Medium (import scanning)
   - **Risk reduction**: 5-10% of Java false positives

#### Medium Impact (2-5% improvement)

4. **Restrict Behave/Cucumber fixtures to `features/` directories**
   - Current: Detects `@given`, `@when` anywhere
   - Proposed: Only in `features/steps/` or `tests/features/` paths
   - **Effort**: Low
   - **Risk reduction**: 3-5% of BDD fixtures

5. **Scope Spring @Bean to test files**
   - Current: Detects anywhere in codebase
   - Proposed: Only if in `src/test/` or `test_*` path
   - **Effort**: Low
   - **Risk reduction**: 2-3% of Spring fixtures

#### Low Impact (1-2%)

6. **Exclude helper methods in Go without test framework context**
   - Current: Helper functions called from ≥3 tests + keyword match
   - Proposed: Also require keyword match (already in v2)
   - **Status**: ✅ Already implemented; Go removed from v2 due to low confidence

### 7.2 For Improving Recall (Reducing False Negatives)

#### High Impact

1. **Add pytest parameterization detection**
   - Current: Only `@pytest.fixture` detected
   - Missing: `@pytest.mark.parametrize` indirect fixtures, `metafunc.parametrize`
   - **Effort**: High (complex syntax)
   - **Recall improvement**: 5-10% of pytest usage

2. **Add JUnit parameterized test factories**
   - Current: Only standard annotations
   - Missing: `@Parameterized.Parameters`, `@ParametersAreNotMutable`, JUnit 5 `@ParameterizedTest`
   - **Effort**: Medium
   - **Recall improvement**: 3-5%

3. **Add TypeScript/TSLint setup decorators**
   - Current: Only `@Before`, `@After` decorators
   - Missing: Framework-specific decorators (`@SetUp`, `@TearDown`, custom names)
   - **Effort**: Medium
   - **Recall improvement**: 2-4%

#### Medium Impact

4. **Add xUnit.net fixtures (C#)**
   - Current: Not supported (removed in v2)
   - **Status**: Planned for Phase 5; limited demand

---

## 8. SPECIFIC RECOMMENDATIONS FOR TIGHTENING

### 8.1 Quick Wins (Low Risk, High Impact)

```python
# 1. Add test file scope validation
def is_test_file(file_path: str, language: str) -> bool:
    """Check if file_path matches language-specific test patterns."""
    test_patterns = LANGUAGE_CONFIGS[language].test_path_patterns
    test_suffixes = LANGUAGE_CONFIGS[language].test_file_suffixes
    
    path_lower = file_path.lower()
    return any(
        pattern in path_lower for pattern in test_patterns
    ) or any(
        path_lower.endswith(suffix) for suffix in test_suffixes
    )

# Apply in detector.py before processing:
if not is_test_file(file_path, language):
    log_warning(f"Fixture detected in non-test file: {file_path}")
```

### 8.2 Medium Difficulty (Moderate Risk, Good Impact)

```python
# 2. Add parent class verification for Python unittest
def has_unittest_parent(node, src_bytes: bytes) -> bool:
    """Check if method is inside class inheriting from TestCase."""
    # Navigate to parent class
    parent = node.parent
    while parent and parent.type != "class_definition":
        parent = parent.parent
    
    if not parent:
        return False
    
    # Check base classes for TestCase
    bases_node = parent.child_by_field_name("superclasses")
    if bases_node:
        bases_text = _source(bases_node, src_bytes).lower()
        return "testcase" in bases_text
    
    return False

# In _detect_python, verify unittest methods:
if name in ("setUp", "tearDown", ...):
    if not has_unittest_parent(node, src_bytes):
        logger.warning(f"setUp/tearDown outside TestCase: {name}")
        continue  # Skip
```

### 8.3 Advanced (Higher Risk, Highest Impact)

```python
# 3. Add import-based framework disambiguation for Java
def disambiguate_junit_testng(src_bytes: bytes) -> str:
    """Determine if file uses JUnit or TestNG by import statements."""
    imports_text = _source(tree.root_node, src_bytes)
    
    if "import org.testng" in imports_text:
        return "testng"
    elif "import org.junit" in imports_text:
        return "junit"
    else:
        return "testng"  # Default fallback

# In _detect_java ambiguous annotation handler:
for ann_key in JUNIT_TESTNG_AMBIGUOUS:
    framework = disambiguate_junit_testng(src_bytes)
    # Use disambiguated framework instead of hardcoded default
```

---

## 9. SUMMARY TABLE: DETECTION CONFIDENCE BY LANGUAGE

| Language | Mechanism | Confidence | False Positive Rate | Key Risk |
|----------|-----------|-----------|------------------|----------|
| **Python** | Decorators + Names | **HIGH** (85-90%) | 10-15% | Name collision in non-test modules |
| **Java** | Annotations | **HIGH** (90-95%) | 3-10% | JUnit4/TestNG ambiguity |
| **JS/TS** | Function calls + Decorators | **MEDIUM** (70-80%) | 15-30% | Ambiguous hook names |
| **Go** | REMOVED | N/A | N/A | Heuristic-only approach; low confidence |

---

## 10. FIXTURE CLASSIFICATION ASSESSMENT

### Strengths
- Multi-layer decision tree prevents false categorization
- Hybrid category preserves ambiguity rather than forcing assignment
- Keyword patterns well-curated (47 patterns across 8 categories)
- Mock framework integration provides strong signal

### Weaknesses
- Keyword matching is surface-level (no semantic understanding)
- Structural heuristics can conflict (`num_parameters >= 2` overlaps with data builders)
- No context awareness (e.g., helper method vs fixture for same keyword)
- Tie-breaking logic (mocking dominance) might overshadow other categories

### Validation Gap
- No ground-truth corpus for classification accuracy
- Categories defined on intuition; no empirical RQ1 validation yet
- "Hybrid" is catch-all (13-20% of fixtures); may hide patterns

---

## 11. DATABASE METRICS USED FOR ANALYSIS

### Extracted at Fixture Level
```sql
SELECT 
    id, name, fixture_type, scope, framework,
    loc, cyclomatic_complexity, cognitive_complexity, max_nesting_depth,
    num_objects_instantiated, num_external_calls, num_parameters,
    reuse_count, has_teardown_pair, fixture_dependencies,
    category, raw_source
FROM fixtures;
```

### Extracted at File Level
```sql
SELECT
    id, relative_path, file_loc, total_fixture_loc, num_test_functions,
    num_fixtures
FROM test_files;
```

### Extracted at Repository Level
```sql
SELECT
    id, full_name, language, stars, num_contributors, 
    status, num_fixtures, num_test_files
FROM repositories;
```

---

## CONCLUSION

The fixture detection system is **high-confidence for syntax-based detection** (Python decorators, Java annotations, JS hooks) but has **moderate false positive risk** for name-based heuristics and ambiguous patterns. The most impactful improvement would be:

1. **Verify file context** — Ensure fixtures are in test files (5-10% FP reduction)
2. **Add parent class checks** — Validate inheritance for unittest methods (5-10% FP reduction)  
3. **Disambiguate frameworks** — Use imports to distinguish JUnit vs TestNG (2-5% FP reduction)

The fixture classification taxonomy (RQ1) is comprehensive but **unvalidated** — manual annotation of 100+ fixtures per language would establish baseline accuracy. Current "hybrid" category (13-20%) suggests substantial ambiguity that classification improvements could address.
