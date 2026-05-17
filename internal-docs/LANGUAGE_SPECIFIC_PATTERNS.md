# Language-Specific Fixture Detection: Pattern Reference & Tightening Guide

## Python Fixture Detection

### Patterns Detected

| Pattern | Type | Framework | Scope | Confidence | Risk Level |
|---------|------|-----------|-------|-----------|-----------|
| `@pytest.fixture` | `pytest_decorator` | pytest | Varies (parsed from scope param) | ⭐⭐⭐⭐⭐ | Very Low |
| `@given`, `@when`, `@then`, `@step` | `behave_*` | behave | `per_test` | ⭐⭐⭐ | Medium |
| `setUp()`, `tearDown()` in class | `unittest_setup` | unittest | `per_test` | ⭐⭐ | **HIGH** |
| `setUpClass()`, `tearDownClass()` | `unittest_setup` | unittest | `per_class` | ⭐⭐ | **HIGH** |
| `setUpModule()`, `tearDownModule()` | `unittest_setup` | unittest | `per_module` | ⭐⭐ | **HIGH** |
| `setup_method()`, `teardown_method()` | `pytest_class_method` | pytest | `per_test` | ⭐⭐⭐ | Low |
| `setup_class()`, `teardown_class()` | `pytest_class_method` | pytest | `per_class` | ⭐⭐⭐ | Low |
| `setup()`, `teardown()` functions | `nose_fixture` | nose | `per_test` | ⭐ | **VERY HIGH** |
| `setup_module()`, `teardown_module()` | `nose_fixture` | nose | `per_module` | ⭐⭐ | **HIGH** |
| `setup_package()`, `teardown_package()` | `nose_fixture` | nose | `per_module` | ⭐⭐ | **HIGH** |

### Heuristics to Tighten

#### 1. unittest Method Names (Remove 10-15% False Positives)

**Current Implementation**
```python
# detector.py, _detect_python()
if name in ("setUp", "tearDown", "setUpClass", "tearDownClass", ...):
    results.append(_build_result(..., fixture_type="unittest_setup", ...))
```

**Problem**: Matches any method with these names, regardless of class inheritance.

**Proposed Fix** [PRIORITY: HIGH]
```python
def is_unittest_testcase(node: Node, src_bytes: bytes) -> bool:
    """Verify method belongs to TestCase-derived class."""
    # Find enclosing class definition
    parent = node.parent
    while parent and parent.type != "class_definition":
        parent = parent.parent
    
    if not parent:
        return False  # Not in a class
    
    # Get base classes
    bases_node = parent.child_by_field_name("superclasses")
    if not bases_node:
        return False
    
    bases_src = _source(bases_node, src_bytes)
    # Match against known TestCase patterns
    return bool(
        re.search(
            r"\b(unittest\.)?TestCase\b|test\.TestCase",
            bases_src,
            re.IGNORECASE
        )
    )

# In _detect_python(), replace:
if name in ("setUp", "tearDown", ...):
    if is_unittest_testcase(node, src_bytes):  # ← NEW CHECK
        results.append(...)
```

#### 2. Nose Fixtures (Remove 5-10% False Positives)

**Current Implementation**
```python
if name in ("setup", "teardown", "setup_module", "teardown_module", ...):
    results.append(...)
```

**Problem**: `setup` and `teardown` are extremely common utility method names.

**Proposed Fix** [PRIORITY: MEDIUM]
```python
def is_nose_test_file(file_path: str) -> bool:
    """Check if file follows Nose conventions."""
    path = file_path.lower()
    # Nose expects test functions/modules in test discovery paths
    return (
        "test" in path or 
        "tests" in path or
        path.startswith("test_") or 
        path.endswith("_test.py")
    )

# In _detect_python():
if name in ("setup", "teardown", ...):
    if name in ("setup_module", "teardown_module", ...) or is_nose_test_file(file_path):
        results.append(...)
```

#### 3. Behave Fixtures in Library Modules (Remove 2-5% False Positives)

**Current Implementation**
```python
if "given" in dec_text and "behave" in dec_text:
    results.append(...)
```

**Problem**: Behave step definition libraries (`features/steps/`) are not test fixtures.

**Proposed Fix** [PRIORITY: LOW]
```python
def is_behave_step_library(file_path: str) -> bool:
    """Check if file is a Behave step definition library (not a fixture)."""
    path = file_path.lower()
    # Step definitions are libraries, not test fixtures
    return "features" in path and "steps" in path

# In _detect_python():
if behave_match:
    if is_behave_step_library(file_path):
        logger.info(f"Behave step in library module: {file_path}")
        continue
    results.append(...)
```

### Mock Framework Patterns (Python)

```python
MOCK_PATTERNS = [
    (r"mock\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "unittest_mock"),
    (r"mocker\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "pytest_mock"),
    (r"MagicMock\s*\(|Mock\s*\(|AsyncMock\s*\(", "unittest_mock"),
]
```

**Validation**: Mock framework checked against `requirements.txt`, `setup.py`, `pyproject.toml`, `poetry.lock`

---

## Java Fixture Detection

### Patterns Detected

| Pattern | Type | Framework | Scope | Confidence | Risk |
|---------|------|-----------|-------|-----------|------|
| `@BeforeEach` | `junit5_before_each` | junit | per_test | ⭐⭐⭐⭐⭐ | Very Low |
| `@AfterEach` | `junit5_after_each` | junit | per_test | ⭐⭐⭐⭐⭐ | Very Low |
| `@BeforeAll` | `junit5_before_all` | junit | per_class | ⭐⭐⭐⭐⭐ | Very Low |
| `@AfterAll` | `junit5_after_all` | junit | per_class | ⭐⭐⭐⭐⭐ | Very Low |
| `@Before` | `junit4_before` | junit | per_test | ⭐⭐⭐⭐ | Low |
| `@After` | `junit4_after` | junit | per_test | ⭐⭐⭐⭐ | Low |
| `@BeforeClass` | `junit4_before_class` / `testng_before_class` | ? | per_class | ⭐⭐⭐ | **MEDIUM** |
| `@AfterClass` | `junit4_after_class` / `testng_after_class` | ? | per_class | ⭐⭐⭐ | **MEDIUM** |
| `@BeforeMethod` (TestNG) | `testng_before_method` | testng | per_test | ⭐⭐⭐⭐ | Low |
| `@AfterMethod` (TestNG) | `testng_after_method` | testng | per_test | ⭐⭐⭐⭐ | Low |
| `@DataProvider` (TestNG) | `testng_data_provider` | testng | per_test | ⭐⭐⭐⭐ | Low |
| `@Mock` | N/A (mock, not fixture) | mockito | — | ⭐⭐⭐⭐⭐ | Very Low |
| `@Bean` (Spring) | `spring_bean` | spring | per_class | ⭐⭐ | **MEDIUM** |
| `@TestConfiguration` | `spring_test_config` | spring | per_class | ⭐⭐⭐⭐ | Low |
| `setUp()`, `tearDown()` (JUnit 3) | `junit3_setup`, `junit3_teardown` | junit | per_test | ⭐⭐ | **MEDIUM** |
| `@Rule`, `@ClassRule` | `junit_rule`, `junit_class_rule` | junit | per_test/per_class | ⭐⭐⭐ | Low |
| Cucumber `@Given`, `@When`, `@Then` | `cucumber_*` | cucumber | per_test | ⭐⭐⭐⭐ | Low |

### Heuristics to Tighten

#### 1. Disambiguate @BeforeClass / @AfterClass (Remove 2-5% False Positives)

**Current Implementation**
```python
if ann_key in JUNIT_TESTNG_AMBIGUOUS:
    junit4_type, testng_type, scope = JUNIT_TESTNG_AMBIGUOUS[ann_key]
    # DEFAULT TO TESTNG!
    fixture_type = testng_type
```

**Problem**: No way to tell if it's JUnit4 or TestNG; code defaults to TestNG.

**Proposed Fix** [PRIORITY: MEDIUM]
```python
def detect_test_framework(src_bytes: bytes) -> str:
    """Detect JUnit4 vs TestNG from imports."""
    source = src_bytes.decode("utf-8", errors="replace")
    
    testng_imports = [
        "import org.testng",
        "org.testng.annotations",
    ]
    junit_imports = [
        "import org.junit",
        "org.junit.jupiter",
        "org.junit.platform",
    ]
    
    has_testng = any(imp in source for imp in testng_imports)
    has_junit = any(imp in source for imp in junit_imports)
    
    if has_testng and not has_junit:
        return "testng"
    elif has_junit:
        return "junit"
    else:
        return "junit"  # Default to JUnit (more common)

# In _detect_java():
framework_hint = detect_test_framework(src_bytes)

for ann_key in JUNIT_TESTNG_AMBIGUOUS:
    junit4_type, testng_type, scope = JUNIT_TESTNG_AMBIGUOUS[ann_key]
    
    if framework_hint == "testng":
        fixture_type = testng_type
    else:
        fixture_type = junit4_type
    
    results.append(...)
```

#### 2. Spring @Bean in Test Context Only (Remove 1-2% False Positives)

**Current Implementation**
```python
# Detects @Bean anywhere in codebase
if ann_key == "@Bean":
    results.append(...)
```

**Problem**: Spring @Bean used in main code too; should be restricted to test files.

**Proposed Fix** [PRIORITY: LOW]
```python
def is_test_file_java(file_path: str) -> bool:
    """Check if file is in test directory."""
    path = file_path.lower()
    return (
        "/test/" in path or 
        "\\test\\" in path or
        path.endswith("test.java") or
        path.endswith("tests.java") or
        path.endswith("it.java")
    )

# In _detect_java(), for Spring @Bean:
if ann_key == "@Bean":
    if not is_test_file_java(file_path):
        logger.debug(f"Skipping @Bean outside test directory: {file_path}")
        continue
    results.append(...)
```

#### 3. JUnit 3 setUp/tearDown (Remove 1-2% False Positives)

**Current Implementation**
```python
if method_name in ("setUp", "tearDown"):
    # Check if not already matched by annotation
    has_annotation = any(
        ann for ann in annotations
        if "@Before" in ann or "@After" in ann
    )
    if not has_annotation:
        results.append(...)
```

**Problem**: No check that class inherits from `TestCase`.

**Proposed Fix** [PRIORITY: MEDIUM]
```python
if method_name in ("setUp", "tearDown"):
    has_annotation = any(
        ann for ann in annotations
        if "@Before" in ann or "@After" in ann
    )
    if not has_annotation:
        # Verify parent class is TestCase
        parent = node.parent
        while parent and parent.type != "class_declaration":
            parent = parent.parent
        
        if parent:
            superclass_node = parent.child_by_field_name("superclass")
            if superclass_node:
                superclass_src = _source(superclass_node, src_bytes)
                if "TestCase" in superclass_src:
                    results.append(...)
```

### Mock Framework Patterns (Java)

```python
MOCK_PATTERNS = [
    (r"Mockito\.mock\s*\(\s*(\w+)\.class", "mockito"),
    (r"@Mock\b", "mockito"),
    (r"EasyMock\.createMock\s*\(\s*(\w+)\.class", "easymock"),
    (r"mock\s*\(\s*(\w+)\.class", "mockk"),
]
```

**Validation**: Mock framework checked in `pom.xml`, `build.gradle`, `build.gradle.kts`

---

## JavaScript / TypeScript Fixture Detection

### Patterns Detected

| Pattern | Type | Framework | Scope | Confidence | Risk |
|---------|------|-----------|-------|-----------|------|
| `beforeEach()` | `before_each` | ? | per_test | ⭐⭐⭐ | **HIGH** |
| `afterEach()` | `after_each` | ? | per_test | ⭐⭐⭐ | **HIGH** |
| `beforeAll()` | `before_all` | ? | per_class | ⭐⭐⭐ | **HIGH** |
| `afterAll()` | `after_all` | ? | per_class | ⭐⭐⭐ | **HIGH** |
| `before()` | `mocha_before` | mocha? | per_test | ⭐⭐ | **VERY HIGH** |
| `after()` | `mocha_after` | mocha? | per_test | ⭐⭐ | **VERY HIGH** |
| `test.before`, `test.after` | `ava_before`, `ava_after` | ava | per_class | ⭐⭐⭐⭐ | Low |
| `test.serial.before` | `ava_serial_before` | ava | per_test | ⭐⭐⭐⭐ | Low |
| `@Before`, `@After` decorators | Various | ? | Varies | ⭐⭐⭐ | Low |

### Heuristics to Tighten

#### 1. Require describe() Block Context (Remove 10-15% False Positives)

**Current Implementation**
```python
# Detects hook calls ANYWHERE in file
if name in JS_FIXTURE_CALLS:
    fixture_type, scope = JS_FIXTURE_CALLS[name]
    results.append(_build_result(...))
```

**Problem**: `beforeEach()`, `afterEach()` are common names in business logic:
- Redux: `beforeEach` middleware
- React testing library: custom hooks
- Database ORMs: lifecycle hooks
- UI validation: `beforeEach` validation hook

**Proposed Fix** [PRIORITY: HIGH]
```python
def is_inside_describe_or_test_block(node: Node) -> bool:
    """Check if hook call is inside describe() or test context."""
    # Walk up AST to parent call expression
    parent = node.parent
    while parent:
        if parent.type == "call_expression":
            func = parent.child_by_field_name("function")
            if func:
                func_name = _source(func, src_bytes).strip()
                # Check if inside describe, it, test, suite, or similar
                if func_name in ("describe", "it", "test", "suite", "context", "specify"):
                    return True
        parent = parent.parent
    
    return False

# In _detect_js():
if name in JS_FIXTURE_CALLS:
    # NEW: Require hook to be inside describe/it block
    if not is_inside_describe_or_test_block(node):
        logger.info(f"Hook {name} outside test block context")
        continue
    
    results.append(...)
```

#### 2. Require Test Framework Import (Remove 5-10% False Positives)

**Alternative/Additional Fix** [PRIORITY: MEDIUM]
```python
def has_test_framework_import(src_bytes: bytes) -> bool:
    """Check for Jest, Mocha, Jasmine, Vitest, etc. imports."""
    source = src_bytes.decode("utf-8", errors="replace")
    
    test_frameworks = [
        "from jest",
        "import jest",
        "from mocha",
        "import mocha",
        "from jasmine",
        "import jasmine",
        "from vitest",
        "import vitest",
        "from ava",
        "import ava",
        "@testing-library",
        "expect",  # Common assertion library
    ]
    
    return any(framework in source.lower() for framework in test_frameworks)

# In _detect_js():
if name in JS_FIXTURE_CALLS:
    if not is_inside_describe_or_test_block(node):
        if not has_test_framework_import(src_bytes):
            logger.info(f"Hook {name} without test framework context")
            continue
    
    results.append(...)
```

#### 3. Distinguish Jest/Vitest from Others (Improve Classification)

**Current Implementation**
```python
results.append(_build_result(..., framework=None))  # AMBIGUOUS
```

**Proposed Fix** [PRIORITY: LOW]
```python
def detect_js_framework(src_bytes: bytes) -> str | None:
    """Detect test framework from imports and patterns."""
    source = src_bytes.decode("utf-8", errors="replace")
    
    if "jest" in source.lower():
        return "jest"
    elif "vitest" in source.lower():
        return "vitest"
    elif "describe" in source and "it(" in source:
        # Generic describe/it (Mocha, Jasmine, Vitest)
        if "@types/jasmine" in source:
            return "jasmine"
        else:
            return "mocha"  # Default
    elif "test.serial" in source or "test.serial" in source:
        return "ava"
    else:
        return None

# In _detect_js():
if name in JS_FIXTURE_CALLS:
    framework = detect_js_framework(src_bytes)
    results.append(_build_result(..., framework=framework))
```

### Mock Framework Patterns (JavaScript)

```python
MOCK_PATTERNS = [
    (r"jest\.fn\s*\(", "jest"),
    (r"jest\.spyOn\s*\(", "jest"),
    (r"jest\.mock\s*\(\s*['\"]([^'\"]+)['\"]", "jest"),
    (r"sinon\.(stub|spy|mock)\s*\(", "sinon"),
    (r"vi\.fn\s*\(", "vitest"),
    (r"vi\.mock\s*\(\s*['\"]([^'\"]+)['\"]", "vitest"),
]
```

**Validation**: Mock framework checked in `package.json` (dependencies + devDependencies)

---

## Summary: Tightening Effort by Language

| Language | Highest-Risk Patterns | Effort to Fix | Expected FP Reduction |
|----------|----------------------|---------------|-----------------------|
| **Python** | `setUp`/`tearDown` (TestCase check), `setup`/`teardown` (Nose) | Medium | 15-25% |
| **Java** | `@BeforeClass` (disambiguation), `@Bean` (scope) | Medium | 5-10% |
| **JavaScript** | `beforeEach`/`afterEach` (describe context) | Low | 15-25% |
| **TypeScript** | Same as JavaScript + decorator ambiguity | Medium | 15-25% |

**Overall Impact**: Implementing these fixes could improve overall precision from ~85% to ~92-93% (27-40% relative FP reduction).

---

## Validation Checklist

After implementing each fix, verify with:

```python
# 1. Test on known-good fixtures in test suite
python -m pytest tests/ -v

# 2. Sample and manually validate output
python pipeline.py validate --sample 50

# 3. Check regression on previous corpus
# (ensure no true positives are lost)

# 4. Measure precision improvement
# python pipeline.py validate --compute validation/sample_TIMESTAMP.csv

# 5. Update metrics in code comments
# Include new confidence levels and FP rates
```
