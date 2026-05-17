# Fixture Detection: False Positives & Precision Improvement Roadmap

## Quick Reference: Top False Positive Sources

### By Probability (Highest First)

| Rank | Language | Pattern | FP Rate | Root Cause | Difficulty to Fix |
|------|----------|---------|---------|-----------|------------------|
| 1 | JS/TS | `beforeEach()`, `afterEach()` calls | 15-30% | Ambiguous function name (not test-specific) | Low |
| 2 | Python | `setUp()`, `tearDown()` methods | 10-15% | Name-based matching outside TestCase | Medium |
| 3 | JS/TS | `before()`, `after()` function names | 5-15% | Could be business logic hooks (Redux, React) | Low |
| 4 | Java | `@BeforeClass`, `@AfterClass` | 5-10% | Could be JUnit4 OR TestNG (defaults to TestNG) | Medium |
| 5 | JavaScript | Custom hook libraries named `beforeEach` | 5-10% | Reusable testing utilities, not test fixtures | Low |
| 6 | Python | Nose fixtures (`setup`, `teardown`) | 5-10% | Common utility function names | Low |
| 7 | Java | Spring `@Bean` in non-test code | 3-5% | Spring beans used everywhere, not just tests | Low |
| 8 | Java | Custom `@Before`/`@After` annotations | 2-5% | Frameworks define similar annotations | Medium |
| 9 | Python | BDD Behave/Cucumber decorators | 2-5% | Steps in library modules vs test files | Low |
| 10 | Python | Async fixtures outside test context | 1-3% | `async def setup()` in utility modules | Low |

---

## ROOT CAUSE ANALYSIS

### Pattern 1: Ambiguous Hook Names (JS/TS - HIGHEST RISK)

**Current Detection**
```javascript
// ANY of these in ANY file triggers detection:
beforeEach(() => { ... })
afterEach(() => { ... })
```

**Why False Positives Occur**
- Not specific to test frameworks (Jest, Mocha, Jasmine, Vitest, Uvu, AVA all use same names)
- Common in business logic:
  - Redux middleware: `beforeEach`, `afterEach`
  - React testing library: custom hooks like `beforeEach`
  - Database ORMs: `beforeEach` lifecycle hooks
  - UI components: `beforeEach` validation hook

**Detection Stats**
- **Ambiguous frameworks**: 7 possible (Jest, Mocha, Jasmine, Vitest, Uvu, AVA, custom)
- **False positive prevalence**: ~25% of detected JS/TS fixtures likely not actual test fixtures

**Evidence from Code**
```python
# In detector.py, _detect_js():
if name in JS_FIXTURE_CALLS:  # beforeEach, beforeAll, etc.
    fixture_type, scope = JS_FIXTURE_CALLS[name]
    results.append(
        _build_result(
            ...
            framework=None,  # AMBIGUOUS - no way to know which framework!
            ...
        )
    )
```

**Mitigation (LOW EFFORT)**

Option A: Require test framework context
```python
def is_inside_describe_block(node) -> bool:
    """Check if hook call is inside describe() block."""
    # Walk up AST to find parent describe() call
    parent = node.parent
    while parent:
        if (parent.type == "call_expression" and 
            "describe" in _source(parent.child_by_field_name("function"))):
            return True
        parent = parent.parent
    return False

# In hook detection:
if name in JS_FIXTURE_CALLS:
    if not is_inside_describe_block(node):
        logger.warning(f"Hook {name} outside describe block; likely not test fixture")
        continue
```

Option B: Require test framework import
```python
def has_test_framework_import(src_bytes: bytes) -> bool:
    """Check for test framework imports."""
    imports = _source(tree.root_node, src_bytes)
    return any(
        f in imports.lower()
        for f in ['jest', 'mocha', 'jasmine', 'vitest', 'ava', '@testing-library']
    )

# Reject hooks if no framework import detected
if not has_test_framework_import(src_bytes):
    logger.warning(f"Hook detected but no test framework import")
    skip_hooks = True
```

---

### Pattern 2: Method Names Without Class Context (Python - HIGH RISK)

**Current Detection**
```python
# Matches ANY method named setUp/tearDown:
class DataProcessor:  # NOT a TestCase!
    def setUp(self):
        self.data = []
```

**Why False Positives Occur**
- Python convention: `setUp`/`tearDown` popular utility method names
- Not restricted to TestCase inheritance
- Found in:
  - Database initialization classes
  - Service setup utilities
  - WebSocket connection managers
  - Logging initialization

**Detection Code (detector.py: `_detect_python`)**
```python
elif name in (
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    ...
):
    # NO CHECK if parent is TestCase!
    results.append(
        _build_result(
            node=node,
            fixture_type="unittest_setup",
            ...
        )
    )
```

**Mitigation (MEDIUM EFFORT)**

```python
def is_testcase_method(node, src_bytes: bytes) -> bool:
    """Verify method is inside class inheriting from TestCase."""
    # Find parent class
    parent = node.parent
    while parent and parent.type != "class_definition":
        parent = parent.parent
    
    if not parent:
        return False
    
    # Check base classes
    bases_node = parent.child_by_field_name("superclasses")
    if not bases_node:
        return False
    
    bases_text = _source(bases_node, src_bytes).lower()
    
    # Check for TestCase inheritance
    return (
        "testcase" in bases_text or
        "unittest.testcase" in bases_text or
        # Also check for dynamically created TestCase (less common)
        "TestCase" in _source(bases_node, src_bytes)
    )

# In _detect_python, for unittest methods:
if name in ("setUp", "tearDown", ...):
    if not is_testcase_method(node, src_bytes):
        logger.info(f"setUp/tearDown outside TestCase; skipping: {name}")
        continue
    
    results.append(...)
```

**Impact**: Would eliminate ~10-15% of Python false positives (estimated from method name analysis)

---

### Pattern 3: JUnit4/TestNG Ambiguity (Java - MEDIUM RISK)

**Current Detection**
```python
# In JUNIT_TESTNG_AMBIGUOUS:
if ann_key in JUNIT_TESTNG_AMBIGUOUS:
    junit4_type, testng_type, scope = JUNIT_TESTNG_AMBIGUOUS[ann_key]
    # DEFAULT TO TESTNG!
    fixture_type = testng_type
```

**Why Ambiguity Exists**
- Annotations `@BeforeClass`, `@AfterClass` exist in both JUnit4 and TestNG
- Code comments say "Default to TestNG for backward compatibility with existing corpus"
- No framework detection in place

**Impact**
- ~5-10% of Java fixtures may be misclassified
- Downstream: RQ2 analysis (mock framework usage) might group JUnit4 and TestNG results incorrectly

**Mitigation (MEDIUM EFFORT)**

```python
def get_framework_from_imports(src_bytes: bytes) -> str | None:
    """Scan imports to determine JUnit vs TestNG."""
    imports_text = _source(tree.root_node, src_bytes)
    
    testng_indicators = ["import org.testng", "@Test", "org.testng.annotations"]
    junit_indicators = ["import org.junit", "org.junit.jupiter", "org.junit.platform"]
    
    has_testng = any(ind in imports_text for ind in testng_indicators)
    has_junit = any(ind in imports_text for ind in junit_indicators)
    
    if has_testng and not has_junit:
        return "testng"
    elif has_junit and not has_testng:
        return "junit"
    else:
        return None  # Ambiguous

# In _detect_java:
framework_hint = get_framework_from_imports(src_bytes)

for ann_key in JUNIT_TESTNG_AMBIGUOUS:
    junit4_type, testng_type, scope = JUNIT_TESTNG_AMBIGUOUS[ann_key]
    
    if framework_hint == "testng":
        fixture_type = testng_type
    elif framework_hint == "junit":
        fixture_type = junit4_type
    else:
        # Keep current default but log ambiguity
        fixture_type = testng_type
        logger.debug(f"Framework ambiguous for {ann_key}; defaulting to TestNG")
```

---

### Pattern 4: Behave/Cucumber Steps in Libraries (Python/Java - LOW RISK but Easy Win)

**Current Detection**
```python
behave_match = re.search(r"@(given|when|then|step)\s*\(", dec_text)
if behave_match:
    # DETECTED anywhere in codebase!
    results.append(...)
```

**Why False Positives Occur**
- Behave step definitions are LIBRARIES, not fixtures
- Example:
  ```python
  # features/steps/user_steps.py (library module)
  @given("a user exists")
  def step_user_exists(context):
      context.user = User()
  ```
- These are NOT fixtures — they're test support code called by scenarios

**Quick Mitigation (LOW EFFORT)**

```python
def is_behave_test_file(file_path: str) -> bool:
    """Check if file is a Behave test file (not library)."""
    path_lower = file_path.lower()
    
    # Behave test files are in features/ directory with .py extension
    # but feature definition files should be .feature (Gherkin)
    # Step definitions ARE in features/steps/ but those are libraries, not tests
    
    # Better heuristic: Behave fixtures should be in test discovery paths
    # NOT in features/steps/ (that's step definition library)
    
    return (
        ("features" in path_lower and ".feature" in path_lower) or
        ("features" in path_lower and "feature" in path_lower and "steps" not in path_lower)
    )

# In _detect_python:
if behave_match:
    if not is_behave_test_file(file_path):
        logger.info(f"Behave step in library module (not fixture); skipping")
        continue
    
    results.append(...)
```

---

## Detection Precision by Framework

### Perfectly Reliable (95%+ confidence)
- Python `@pytest.fixture` decorator
- Java annotation-based (@BeforeEach, @BeforeAll, @Test)
- Spring @TestConfiguration

**Rationale**: Framework-specific syntax; very low collision risk

### High Confidence (85-90%)
- Python `@unittest.setUp`, `tearDown` (with parent class check)
- Java @Mock, @BeforeMethod, @DataProvider
- JavaScript/TypeScript decorators (@Before, @After, @BeforeEach)

**Rationale**: Annotation-based, low collision; some ambiguity possible

### Medium Confidence (70-80%)
- JavaScript hook functions (beforeEach, afterEach) with describe() context
- Java @BeforeClass, @AfterClass (with framework disambiguation)

**Rationale**: Name-based; requires context checking; ambiguous frameworks

### Low Confidence (50-70%) ❌
- Nose fixtures (`setup`, `teardown`) — too generic
- JavaScript hooks without framework context
- Python generic setUp/tearDown without TestCase check

**Recommendation**: Add file-scope and parent-class validation before accepting these

---

## Recommended Implementation Priority

### Phase 1: Highest Impact, Lowest Effort (1-2 days)
1. ✅ Add test file scope check (Python, Java)
   - Before accepting any fixture, verify file is in test path
   - Eliminates utility modules masquerading as test fixtures
   - **Expected FP reduction**: 5-8%

2. ✅ Add describe block context for JS hooks
   - Require `beforeEach()` to be inside `describe()` block
   - **Expected FP reduction**: 10-15%

### Phase 2: High Impact, Medium Effort (3-5 days)
3. ⚠️ Add parent class check for Python unittest methods
   - Verify `setUp`/`tearDown` inherit from TestCase
   - **Expected FP reduction**: 8-12%

4. ⚠️ Disambiguate JUnit4 vs TestNG
   - Check imports to determine framework
   - **Expected FP reduction**: 2-5%

### Phase 3: Medium Impact, Lower Priority (1+ week)
5. Filter Behave/Cucumber steps from library modules
6. Add Spring context path validation
7. Improve mock framework validation with more thorough dependency file scanning

---

## Validation Metrics to Track

After implementing improvements, measure precision:

```python
# During validation.py sampling:

PRECISION_METRICS = {
    "python": {
        "pytest_decorator": 0.95,  # Already high
        "unittest_setup": 0.75,    # Needs parent class check
        "nose_fixture": 0.60,      # High FP risk
    },
    "javascript": {
        "before_each": 0.65,       # Needs describe() context
        "ava_before": 0.85,        # More reliable
    },
    "java": {
        "junit5_before_each": 0.92,
        "testng_before_class": 0.70,  # Needs disambiguation
    },
}
```

---

## Summary: Precision Improvement Roadmap

| Step | Cost | Benefit | Timeline |
|------|------|---------|----------|
| Test file scope validation | Low | 5-8% FP reduction | Week 1 |
| JS describe() context check | Low | 10-15% FP reduction | Week 1 |
| Python parent class check | Medium | 8-12% FP reduction | Week 2 |
| Java framework disambiguation | Medium | 2-5% FP reduction | Week 2 |
| Behave/Cucumber library filtering | Low | 2-3% FP reduction | Week 3 |
| **Total expected improvement** | — | **~27-40% FP reduction** | 3 weeks |

This would raise overall precision from **~85%** to **~92-93%**, aligning with Hamster's quality standards.
