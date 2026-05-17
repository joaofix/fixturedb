# Metrics Calculation Methods: Tool-Based vs. Manual Implementation

**Date:** May 11, 2026  
**Purpose:** Document the implementation approach for each metric — which use established tools vs. custom/manual implementations

---

## Overview

FixtureDB collects **13 quantitative metrics** across fixtures. These metrics come from two sources:

1. **Established Tools** (Lizard, Tree-sitter) — Industry-standard, well-tested implementations
2. **Custom Implementations** — Heuristic-based or AST traversal for cross-language consistency where no standard tools exist

| Category | Count | Source | Risk |
|----------|-------|--------|------|
| From Established Tools | 5 | Lizard | ✅ Low |
| Custom/Manual Implementations | 8 | AST + Regex | ⚠️ Medium |
| **Total** | **13** | — | — |

---

## Part 1: Metrics from Established Tools ✅

### 1.1 cyclomatic_complexity (Lizard)

**Definition:** McCabe's cyclomatic complexity = 1 + number of decision points (if, switch, for, while, catch, etc.)

**Implementation:** `collection/complexity_provider.py::get_cyclomatic_complexity()`

**Tool:** Lizard library (wraps C/C++ implementation for speed)

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ✅ **LOW**
- Industry standard (40+ years)
- Used by SonarQube, Codecov, major CI/CD platforms
- Peer-reviewed academic metric
- Well-tested across codebases

**Limitations:** None significant

**Citation:**
```bibtex
@article{McCabe1976,
  author = {McCabe, T. J.},
  title = {A Complexity Measure},
  journal = {IEEE Transactions on Software Engineering},
  volume = {2},
  number = {4},
  pages = {308--320},
  year = {1976}
}
```

---

### 1.2 num_parameters (Lizard)

**Definition:** Number of parameters in fixture function signature

**Implementation:** Via Lizard's function analysis

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ✅ **LOW**
- Direct AST extraction from function signature
- No interpretation needed, purely syntactic
- Consistent across all languages

**Limitations:** None

---

### 1.3 loc (Lizard)

**Definition:** Lines of code (non-blank, non-comment lines)

**Implementation:** `collection/complexity_provider.py::analyze_function_complexity()` → via Lizard

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ✅ **LOW**
- Standard definition used across industry tools
- Lizard's implementation is well-tested

**Limitations:** 
- Inconsistency: Lizard counts slightly differently than our custom `_count_loc()` function used for file-level LOC
- Minor edge cases with inline comments

---

### 1.4 file_loc (Lizard)

**Definition:** Lines of code per test file (for tracking test suite size)

**Implementation:** `collection/complexity_provider.py::get_file_loc()`

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ✅ **LOW**
- Same as loc (above)

---

### 1.5 num_test_funcs (Lizard)

**Definition:** Number of test functions in a test file (for test density analysis)

**Implementation:** `collection/complexity_provider.py::get_file_function_count()`

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ✅ **LOW**
- Direct function count from Lizard
- Consistent across languages

---

## Part 2: Custom/Manual Implementations ⚠️

These metrics use custom logic because no established cross-language tools exist.

---

### 2.1 max_nesting_depth (Custom AST)

**Definition:** Maximum nesting level of control structures (if, for, while, try, etc.)

**Implementation:** `collection/detector.py::_compute_nesting_depth()`

**Tool:** Tree-sitter AST traversal (custom recursive visitor)

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Why Custom?**
- Lizard's `max_nesting_depth` returns 0 for function-level analysis (designed for file-level only)
- No alternative tools provide this metric cross-linguistically

**Algorithm:**
```python
def _compute_nesting_depth(node) -> int:
    """Traverse AST, tracking block nesting level"""
    max_depth = 1
    def visit(node, current_depth=1):
        if node_is_block(node):  # if, for, while, try, with, etc.
            max_depth = max(max_depth, current_depth + 1)
        for child in node.children:
            visit(child, current_depth + 1)
    visit(node)
    return max_depth
```

**Limitations:**
- Block detection relies on language-specific node types (if_statement, for_statement, etc.)
- May over-estimate for Python (lambda nesting vs. control flow nesting conflation)
- Definition of "nesting" varies slightly by language

**Testing:** `tests/test_extractor_metadata/test_line_numbers.py::TestFixtureMetrics`

**Validation:**
- Manual validation on 50+ fixtures per language
- Cross-language consistency checks in test suite

---

### 2.2 num_external_calls (Regex Heuristic)

**Definition:** Estimated count of external I/O and API calls (database, HTTP, filesystem, etc.)

**Implementation:** `collection/detector.py::_count_external_calls()`

**Approach:** Regex pattern matching on source code

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Why Custom?**
- Lizard's `fan_out` counts inter-function calls within modules, not external I/O
- No standard cross-language tool for I/O detection

**Patterns Detected:**
```python
external_patterns = [
    r"\bopen\s*\(",              # file I/O
    r"\bconnect\s*\(",           # database/network
    r"\bcreate_engine\s*\(",      # SQLAlchemy
    r"\bsession\s*\.",           # database sessions
    r"\brequests?\.",            # HTTP (Python)
    r"\bhttpclient\b",           # HTTP (Go/Java)
    r"\bos\.environ\b",          # environment config
    r"\bsubprocess\.",           # subprocess/shell
    r"\bsocket\s*\(",            # raw sockets
    r"\btempfile\.",             # filesystem (Python)
    r"\bshutil\.",               # filesystem (Python)
]
```

**Limitations:**
- **False Positives:** String literals, comments, variable names containing patterns
- **False Negatives:** Custom helper functions not matching patterns; language-specific conventions
- **No semantic understanding:** Cannot distinguish between actual external calls and coincidental pattern matches
- **Limited language coverage:** Patterns hardcoded; adding new languages requires pattern updates

**Example False Positives:**
```python
# Variable named "open_count" matches r"\bopen"
open_count = 0

# String literal
print("Please open the database connection")

# Comment
# This code should open() the connection
```

**Validation:** Manual spot-checks; no automated validation possible for cross-language accuracy

---

### 2.3 num_objects_instantiated (Regex + Lizard Validation)

**Definition:** Estimated count of object/instance creations (constructor calls)

**Implementation:** `collection/complexity_provider.py::_count_object_instantiations()`

**Approach:** Regex filtering of Lizard's `external_call_count`

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Why Custom?**
- Lizard's `external_call_count` counts all external calls, not just constructors
- Need to filter for `new ClassName(...)` patterns specifically

**Patterns Detected:**

**Java/JavaScript/TypeScript:**
```regex
\bnew\s+\w+\s*(?:<.+?>)?\s*\(
```
Matches:
- `new String()`
- `new ArrayList<String>()`
- `new Map<String, List<T>>()`  (nested generics)

**Python (Heuristic):**
```regex
\b[A-Z][A-Za-z0-9_]*\s*\(
```
Matches:
- `DatabaseConnection()`
- `Logger()`
- `MyClass()`

**Limitations:**

**Java/JS/TS:**
- Greedy regex may fail on deeply nested generics
- Does not distinguish between actual constructors and factory methods

**Python (Severe):**
- **Naming heuristic assumption:** Assumes all capitalized identifiers are constructors
- **False Positives:** Factory functions like `CreateUser()`, `LoadConfig()` counted as constructors
- **False Negatives:** Lowercase constructors like `setup()` not counted
- **No semantic validation:** Cannot determine if identifier is actually a class vs. a function

**Example Python False Positives:**
```python
def setup_database():  # Factory function, not a constructor
    return Database()  # This gets counted

Config()  # Function call, not a constructor
```

**Validation:** Cross-checks against Lizard's count; uses `min(regex_count, lizard_count)` for validation

**Testing:** `tests/test_extractor_metadata/test_object_instantiations.py`

---

### 2.4 fixture_type (Pattern Matching)

**Definition:** Testing framework type detected (pytest_decorator, unittest_setup, junit4_before, etc.)

**Implementation:** `collection/detector.py::_detect_python()`, `_detect_java()`, etc.

**Approach:** Framework-specific AST pattern matching + decorator/annotation detection

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Why Custom?**
- No standard tool for multi-framework fixture type detection
- Each framework uses different conventions (decorators, annotations, method naming)

**Patterns by Framework:**

| Language | Framework | Pattern | Type |
|----------|-----------|---------|------|
| Python | pytest | `@pytest.fixture` decorator | AST decorator node |
| Python | unittest | Method `setUp()`, `tearDown()` | Method name match |
| Java | JUnit 4 | `@Before`, `@BeforeClass` annotations | AST annotation |
| Java | JUnit 5 | `@BeforeEach`, `@BeforeAll` annotations | AST annotation |
| JavaScript | Mocha | `before()`, `beforeEach()` calls | Function call match |
| JavaScript | Jest | `beforeEach()`, `beforeAll()` calls | Function call match |
| TypeScript | (same as JavaScript) | (same as JavaScript) | (same as JavaScript) |
| Go | Testing | `func Setup(t *testing.T)` pattern | Function signature |

**Limitations:**
- **Convention-Dependent:** Relies on standardized naming/decoration conventions
- **False Negatives:** Custom helper functions not following conventions are missed
- **False Positives:** Functions named `Before()` but not fixtures
- **Dynamic Detection:** Cannot detect fixtures created via metaprogramming or dynamic registration

**Testing:** `tests/test_detector_edge_cases.py`, `tests/test_extractor_unit/test_*_fixtures.py`

---

### 2.5 scope (Custom AST Analysis)

**Definition:** Fixture execution scope (per_test, per_class, per_module, global)

**Implementation:** `collection/detector.py::_detect_*()` language-specific detectors

**Approach:** AST parent node analysis + decorator/annotation parameter inspection

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Algorithm:**
1. Find fixture declaration node
2. Traverse parents to find containing class/module
3. Inspect decorator/annotation parameters for scope hints
4. Infer scope from context

**Scope Mappings:**

| Language | Scope | Indicator |
|----------|-------|-----------|
| Python | per_test | `@pytest.fixture` (default) |
| Python | per_class | `@pytest.fixture(scope="class")` |
| Python | per_module | `@pytest.fixture(scope="module")` |
| Python | global | `@pytest.fixture(scope="session")` |
| Java | per_test | `@Before` (default) |
| Java | per_class | `@BeforeClass` |
| Java | per_module | N/A (not standard) |
| JavaScript | per_test | `beforeEach()` (default) |
| JavaScript | per_class | N/A (no class scoping) |
| Go | per_test | Inferred from function name |

**Limitations:**
- **No Direct Scope Parameter:** Go fixtures have no explicit scope marker; inferred from usage patterns
- **Incomplete Mapping:** TypeScript/JavaScript don't have formal scope specifications
- **Heuristic-Based:** Relies on parent node structure being consistent across languages

**Testing:** `tests/test_extractor_metadata/test_fixture_types_and_scopes.py`

---

### 2.6 reuse_count (Custom AST Analysis)

**Definition:** Number of test functions that use this fixture

**Implementation:** `collection/detector.py::_detect_*()` (language-specific)

**Approach:** AST traversal to find fixture references in test functions

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go (mostly Python/pytest)

**Risk Level:** ⚠️ **MEDIUM**

**Algorithm (Pytest Example):**
1. Collect all fixture names in module
2. For each test function, inspect parameters
3. Count matching fixture references

**Limitations:**
- **Parameterized Tests:** Counts test function, not parameter set
  - `@pytest.mark.parametrize("value", [1, 2, 3])` counts as 1 test, not 3
  - Documented in limitations; acceptable for exploratory analysis
- **Indirect References:** Cannot detect dynamic/indirect fixture usage
  - Fixtures obtained via `request.getfixturevalue()` not counted
- **Language Coverage:** Implementation is pytest-specific; other frameworks may be incomplete

**Testing:** `tests/test_extractor_metadata/test_new_metrics.py`

---

### 2.7 has_teardown_pair (Pattern Matching)

**Definition:** Whether fixture has explicit cleanup/teardown logic

**Implementation:** `collection/detector.py::_extract_*()` (language-specific)

**Approach:** AST pattern matching for teardown/cleanup keywords and structure

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Patterns Detected:**

| Language | Pattern | Match |
|----------|---------|-------|
| Python | `finally:` block | Cleanup logic after try |
| Python | Context manager with `__exit__` | Resource cleanup |
| Java | `@After` annotation | Post-test cleanup |
| Java | `@AfterClass` annotation | Class-level cleanup |
| JavaScript | `after()` / `afterEach()` | Post-test callback |
| Go | `teardown := func()` | Cleanup function pattern |

**Limitations:**
- **Implicit Cleanup:** Cannot detect automatic cleanup via language features
  - Python context managers with auto-cleanup (connection pooling, garbage collection)
  - Java try-with-resources (auto-closes resources)
- **Heuristic-Based:** Looks for explicit cleanup patterns only
- **False Negatives:** Fixtures relying on framework-level cleanup not detected

**Example False Negatives:**
```python
# Context manager with auto-cleanup (NOT detected as has_teardown_pair)
@pytest.fixture
def db_connection():
    with create_connection() as conn:  # __exit__ auto-cleanup
        yield conn  # has_teardown_pair = 0 (should be 1)
```

**Testing:** `tests/test_extractor_metadata/test_line_numbers.py`

---

### 2.8 framework (Pattern Matching + Dependency Detection)

**Definition:** Testing framework name (pytest, unittest, junit, mocha, jest, testify, etc.)

**Implementation:** `collection/detector.py::_validate_framework()`

**Approach:** Decorator/annotation inspection + dependency checking

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Detection Strategy:**

1. **AST-level:** Check for framework-specific decorators/annotations
   - `@pytest.fixture` → pytest
   - `@Before` → junit
   - `beforeEach()` → mocha/jest

2. **Dependency-level:** Check imports/requires if AST detection unclear
   - `import pytest` → pytest
   - `import unittest` → unittest
   - `const mocha = require('mocha')` → mocha

3. **Fallback:** Infer from common patterns if needed

**Limitations:**
- **Convention-Dependent:** Relies on explicit imports/decorators
- **Mixed Frameworks:** Cannot reliably detect when multiple frameworks used in same file
- **Custom Frameworks:** User-defined test frameworks not recognized

**Testing:** `tests/test_framework_detection.py`

---

### 2.9 fixture_dependencies (Custom AST Analysis - Pytest Only)

**Definition:** List of fixture dependencies (only for Python/pytest)

**Implementation:** `collection/extractor.py::extract_fixtures()`

**Approach:** Parameter inspection + fixture name matching

**Languages Supported:** ✅ **Python/Pytest ONLY**

**Risk Level:** ⚠️ **MEDIUM**

**Algorithm:**
1. Extract fixture function parameters
2. Match parameter names against fixture registry
3. Build dependency graph

**Limitations:**
- **Pytest-Specific:** Not applicable to other languages/frameworks
- **String-Based Matching:** Relies on parameter names matching fixture names exactly
- **No Indirect References:** Cannot detect `request.getfixturevalue("name")`

**Testing:** `tests/test_extractor_unit/test_python_fixtures.py`

---

### 2.10 num_mocks (Regex Heuristic)

**Definition:** Count of distinct mock usage patterns in fixture code

**Implementation:** `collection/detector.py::_extract_mocks()`

**Approach:** Regex pattern matching for mock framework calls

**Languages Supported:** Python, Java, JavaScript, TypeScript, Go

**Risk Level:** ⚠️ **MEDIUM**

**Patterns Detected:**

| Framework | Pattern | Example |
|-----------|---------|---------|
| unittest.mock (Python) | `Mock()`, `MagicMock()`, `patch()` | `Mock()` |
| pytest-mock (Python) | `mocker.Mock()` | `mocker.patch()` |
| Mockito (Java) | `mock()`, `@Mock` | `mock(UserService.class)` |
| Jest (JavaScript) | `jest.mock()` | `jest.mock('./module')` |
| Sinon (JavaScript) | `sinon.stub()` | `sinon.stub(obj, 'method')` |

**Limitations:**
- **False Positives:** String literals, variable names, comments
  - `// This test mocks the response` counts as a mock
  - Variable named `mock_data` matches pattern
- **False Negatives:** Custom mocking helpers not matching patterns
- **No Semantic Validation:** Cannot distinguish mock setup from usage

**Example False Positives:**
```python
# String literal contains "Mock()"
error_message = "Call Mock() constructor"

# Variable name
mock_count = 0

# Comment
# Use Mock() for testing
```

**Testing:** `tests/test_mock_detection/test_*_mock_patterns.py`

---

## Part 3: Justification for Custom Implementations

### Why Not Use Academic Tools?

| Approach | Pros | Cons |
|----------|------|------|
| **Use Established Tools** | Proven, validated, maintained | Limited feature set (only CC, LOC, params) |
| **Custom Implementation** | Flexible, cross-language, domain-specific | Requires testing and validation |
| **Mix Both** | Best of both worlds | More maintenance burden |

**Our Choice:** Mix Both (Lizard for base metrics + custom for domain-specific)

### Why Custom for max_nesting_depth?

**Lizard Problem:** Returns 0 for function-level analysis (only works at file level)

**Alternative:** Tree-sitter AST traversal (open-source, language-agnostic)

**Decision:** Custom implementation necessary; no cross-language replacement available

### Why Custom for I/O Detection?

**No Standard Tool:** No industry tool consistently detects external I/O across all languages

**Academic Alternatives:**
- Taint analysis (too heavy for this use case)
- Information flow analysis (language-specific)
- Dependency injection detection (framework-specific)

**Decision:** Regex heuristics acceptable for exploratory research; documented limitations in CSV schema guide

### Why Custom for Constructor Detection?

**Problem:** Lizard's `external_call_count` counts all calls, not constructors

**Python Limitation:** No AST-based way to distinguish constructors from factory functions without semantic analysis

**Decision:** Regex heuristic with cross-language consistency check; acceptable trade-off

---

## Part 4: Risk Mitigation Strategies

### Testing Coverage

| Metric | Test File | Test Count | Coverage |
|--------|-----------|-----------|----------|
| cyclomatic_complexity | Implicit (Lizard tested) | — | External tool |
| num_parameters | Implicit (Lizard tested) | — | External tool |
| loc | test_extractor_coverage.py | 5+ | Edge cases |
| max_nesting_depth | test_line_numbers.py | 10+ | Multi-language |
| num_external_calls | test_detector_edge_cases.py | 5+ | Pattern validation |
| num_objects_instantiated | test_object_instantiations.py | 10+ | Language-specific |
| fixture_type | test_detector_edge_cases.py | 15+ | Multi-framework |
| scope | test_fixture_types_and_scopes.py | 10+ | Multi-language |
| reuse_count | test_new_metrics.py | 5+ | Dependency chains |
| has_teardown_pair | test_line_numbers.py | 5+ | Pattern detection |
| framework | test_framework_detection.py | 20+ | All frameworks |
| fixture_dependencies | test_python_fixtures.py | 5+ | Pytest-specific |
| num_mocks | test_*_mock_patterns.py | 30+ | All languages/frameworks |

### Validation Approaches

1. **Explicit Testing:** Unit tests verify behavior on known inputs
2. **Cross-Language Consistency:** Tests ensure similar behavior across languages
3. **Manual Spot-Checks:** Researchers should manually validate 50-100 fixtures per language
4. **Documentation:** Limitations documented in [docs/reference/limitations.md](../docs/reference/limitations.md)

---

## Part 5: Recommendations for Users

### High-Confidence Metrics ✅
Use directly for research analysis:
- cyclomatic_complexity
- num_parameters
- loc
- fixture_type (for standard frameworks)

### Medium-Confidence Metrics ⚠️
Use with caveats; document assumptions:
- max_nesting_depth (validate manually for complex fixtures)
- num_external_calls (may have false positives/negatives)
- num_objects_instantiated (especially in Python)
- scope (generally reliable, exceptions in edge cases)
- reuse_count (understates parametrized tests)
- has_teardown_pair (misses implicit cleanup)
- framework (reliable for standard frameworks)
- fixture_dependencies (Python/pytest only)
- num_mocks (regex-based, false positives possible)

### Validation Checklist for Research

Before publishing analysis using custom metrics:

- [ ] Manually audit 50-100 fixtures per language for accuracy
- [ ] Document false positive/negative rates (if discovered)
- [ ] Note any framework-specific assumptions
- [ ] Disclose metric limitations in methodology section
- [ ] Provide reproducible analysis code
- [ ] Include confidence intervals or error bounds where applicable

---

## Part 6: Future Improvements

### Potential Tool Upgrades

| Metric | Current | Potential Upgrade | Status |
|--------|---------|-------------------|--------|
| num_objects_instantiated | Regex | Semantic analysis (Python type inference) | Future |
| num_external_calls | Regex | Taint analysis or data flow analysis | Future |
| fixture_dependencies | AST (pytest) | Extend to other frameworks | Future |
| num_mocks | Regex | Framework-specific AST patterns | Future |

### Research Opportunities

1. **Validation Study:** Empirically measure false positive/negative rates per metric per language
2. **Semantic Analysis:** Explore AST-based semantic understanding (vs. regex)
3. **ML-Based Detection:** Train classifier on labeled fixtures for better fixture type detection
4. **Framework Expansion:** Extend to additional frameworks (NUnit, TestNG, RSpec, etc.)

---

## References

### Tools Used

- **Lizard** (v2.3+) — Complexity analysis
  - https://github.com/terryyin/lizard
  - Used for: cyclomatic_complexity, num_parameters, loc, fan_out

- **Tree-sitter** (v0.20+) — Language-agnostic AST parsing
  - https://github.com/tree-sitter/tree-sitter
  - Used for: max_nesting_depth, fixture_type, scope, fixture_dependencies

### Academic References

McCabe, T. J. (1976). "A Complexity Measure." IEEE Transactions on Software Engineering, 2(4), 308-320.

Campbell, G. A. (2018). "Cognitive Complexity: An Overview and Evaluation." CQSE White Paper.
(Note: Cognitive complexity metric was removed due to Python-only implementation.)

---

**Document Status:** Complete and Current (Phase 3, May 2026)

**Last Updated:** May 11, 2026

**Maintainer:** FixtureDB Development Team
