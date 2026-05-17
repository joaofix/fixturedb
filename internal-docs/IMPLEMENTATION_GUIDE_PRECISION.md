# Implementation Guide: Precision-Focused Detection Improvements

**Date:** April 16, 2026  
**Purpose:** Specific code changes to reduce false positives by 25-40%  
**Audience:** Developers implementing detection improvements

---

## Overview

This guide provides concrete code changes you can implement immediately to improve precision. Each improvement includes:
- Current code (what's wrong)
- Proposed code (the fix)
- Expected FP reduction
- Implementation time

---

## HIGH-PRIORITY: Week 1 Improvements

### Improvement #1: JavaScript Test Context Check

**Problem:** Detects `beforeEach()` everywhere, including Redux middleware and React hooks.

**Current Code:** `collection/detector.py::_detect_fixtures_javascript()`
```python
# CURRENT: Matches beforeEach/afterEach in ANY file
if function_name in ("beforeEach", "afterEach", "beforeAll", "afterAll"):
    if _is_jest_or_describe_context(node):
        fixtures.append(...)
```

**Root Issue:** `_is_jest_or_describe_context()` checks for `describe()` blocks, which Redux middleware also uses.

**Proposed Fix:**
```python
def _is_test_file(file_path: Path) -> bool:
    """Check if file is a test file based on naming patterns."""
    name = file_path.stem
    return (
        name.endswith('.test') or 
        name.endswith('.spec') or
        'test' in file_path.parts or
        '__tests__' in file_path.parts
    )

def _detect_fixtures_javascript(file_path: Path, src_bytes: bytes, language: str):
    """Detect Jest/Mocha fixtures in JavaScript/TypeScript."""
    
    # IMPROVEMENT #1: Only proceed if file looks like test file
    if not _is_test_file(file_path):
        return []
    
    # ... rest of detection ...
```

**Expected Impact:** 10-15% FP reduction  
**Effort:** 30 minutes  
**Risk:** LOW (test file naming is standard practice)

**Testing:**
```python
# tests/test_detector/test_js_precision.py
def test_beforeEach_in_redux_middleware_not_detected():
    """Redux middleware uses describe/beforeEach but should not be fixture."""
    code = """
    const reducer = describe("Redux", () => {
        beforeEach(() => {
            // Redux middleware setup - NOT a test fixture
        });
    });
    """
    # This should return NO fixtures if not in test file context
```

---

### Improvement #2: Python TestCase Inheritance Check

**Problem:** Detects `setUp()` and `tearDown()` in any class, including non-test classes.

**Current Code:** `collection/detector.py::_detect_fixtures_python()`
```python
# CURRENT: Matches setUp/tearDown in ANY class
if function_name in ("setUp", "tearDown"):
    scope = "per_test"
    fixtures.append(...)
```

**Root Issue:** No check that the parent class inherits from `unittest.TestCase`.

**Proposed Fix:**
```python
def _is_unittest_testcase(class_node) -> bool:
    """Check if class inherits from unittest.TestCase."""
    # Get base class nodes
    bases_node = class_node.child_by_field_name("superclasses")
    
    if not bases_node:
        return False
    
    # Check if any base class is "TestCase" or includes "TestCase"
    for child in bases_node.children:
        if "TestCase" in _source(child, b"").decode():
            return True
    
    return False

def _detect_fixtures_python(file_path: Path, src_bytes: bytes):
    """Detect pytest/unittest fixtures in Python."""
    
    # ... existing code ...
    
    # When processing class method:
    if function_name in ("setUp", "tearDown"):
        # IMPROVEMENT #2: Only include if class inherits from TestCase
        if not _is_unittest_testcase(class_node):
            continue  # Skip false positive
        
        scope = "per_test"
        fixtures.append(...)
```

**Expected Impact:** 8-12% FP reduction  
**Effort:** 1 hour  
**Risk:** LOW (standard Python unittest pattern)

**Testing:**
```python
# tests/test_detector/test_python_precision.py
def test_setUp_in_non_testcase_not_detected():
    """setUp in non-TestCase class should not be detected."""
    code = """
    class DataSetup:
        def setUp(self):
            self.data = load_data()
    
    class MyTest(unittest.TestCase):
        def setUp(self):
            self.db = setup_db()
    """
    result = extract_fixtures(code, "python")
    
    # Should find 1 (in MyTest), not 2
    assert len(result.fixtures) == 1
    assert result.fixtures[0].start_line == 6  # MyTest.setUp
```

---

### Improvement #3: Add Root Cause Tracking to Validation

**Purpose:** Track WHY each false positive occurs so you can prioritize fixes.

**Current Code:** `collection/validator.py::generate_sample()`
```python
# CURRENT: No false_positive_reason column
sample["is_true_fixture"] = ""
sample["reviewer_notes"] = ""
```

**Proposed Enhancement:**
```python
def generate_sample(n_per_language: int = 50) -> Path:
    """Generate stratified sample with FP tracking."""
    
    # ... existing sampling code ...
    
    sample = pd.concat(frames, ignore_index=True)
    
    # IMPROVEMENT #3: Add false_positive_reason column
    sample["is_true_fixture"] = ""  # 1=true, 0=false
    sample["false_positive_reason"] = ""  # Only fill if is_true_fixture=0
    sample["reviewer_notes"] = ""
    
    # Add guidance to CSV header comment
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = VALIDATION_DIR / f"sample_{timestamp}.csv"
    sample.to_csv(out_path, index=False)
    
    logger.info(f"\nValidation sample written to: {out_path}")
    logger.info(
        "Instructions:\n"
        "  1. Open the CSV in a spreadsheet editor.\n"
        "  2. Read each 'raw_source' value.\n"
        "  3. Set 'is_true_fixture' to 1 (true fixture) or 0 (false positive).\n"
        "  4. If 0, set 'false_positive_reason' to one of:\n"
        "     - JS_non_test_hook (beforeEach not in test)\n"
        "     - python_setUp_no_testcase (setUp outside TestCase)\n"
        "     - java_framework_ambiguous (@BeforeClass w/o context)\n"
        "     - helper_function (not for setup)\n"
        "     - other (describe in reviewer_notes)\n"
        "  5. Run: python pipeline.py validate --compute <path_to_csv>"
    )
    return out_path
```

**Then Update compute_metrics():**
```python
def compute_metrics(csv_path: Path) -> dict:
    """Compute precision with FP root cause analysis."""
    
    df = pd.read_csv(csv_path)
    
    # ... existing code ...
    
    # IMPROVEMENT #3: Analyze false positive distribution
    fp_items = labelled[labelled["is_true_fixture"] == 0]
    
    if len(fp_items) > 0:
        print("\n\nFALSE POSITIVE ROOT CAUSE ANALYSIS:")
        print("-" * 60)
        fp_reasons = fp_items["false_positive_reason"].value_counts()
        for reason, count in fp_reasons.items():
            if pd.notna(reason) and reason != "":
                pct = 100 * count / len(fp_items)
                print(f"  {reason:<35} {count:>3} ({pct:>5.1f}%)")
        
        # Recommendations based on distribution
        top_reason = fp_reasons.index[0]
        print(f"\nTop false positive source: {top_reason}")
        print("Recommended fix priority: See FALSE_POSITIVES_ROADMAP.md")
    
    return results
```

**Expected Impact:** Enables data-driven improvement decisions  
**Effort:** 45 minutes  
**Risk:** VERY LOW (only adds tracking, doesn't change logic)

---

## MEDIUM-PRIORITY: Week 2-3 Improvements

### Improvement #4: Java @BeforeClass Disambiguation

**Problem:** `@BeforeClass` exists in both JUnit4 and TestNG; current code defaults to TestNG incorrectly.

**Location:** `collection/detector.py::_detect_fixtures_java()`

**Implementation:** Check import statements
```python
def _infer_test_framework_java(src_bytes: bytes) -> str:
    """Infer test framework from imports (JUnit4 vs TestNG)."""
    src_text = src_bytes.decode()
    
    # JUnit4 indicators
    if "import org.junit.Test" in src_text:
        return "junit4"
    if "import org.junit.Before" in src_text:
        return "junit4"
    
    # TestNG indicators
    if "import org.testng.annotations" in src_text:
        return "testng"
    if "import org.testng.Assert" in src_text:
        return "testng"
    
    # Default: JUnit4 (most common)
    return "junit4"

def _detect_fixtures_java(file_path: Path, src_bytes: bytes):
    """Detect JUnit/TestNG fixtures in Java."""
    
    # IMPROVEMENT #4: Determine framework context
    framework = _infer_test_framework_java(src_bytes)
    
    # ... detection code ...
```

**Expected Impact:** 2-5% FP reduction  
**Effort:** 1 hour  
**Risk:** LOW (conservative detection)

---

### Improvement #5: Behave/Cucumber Library Filtering

**Problem:** Detects Behave/Cucumber steps as fixtures (they're behavior specs, not setup).

**Location:** `collection/detector.py::_detect_fixtures_python()`

**Implementation:**
```python
def _filter_behave_steps(fixtures: list[FixtureResult]) -> list[FixtureResult]:
    """Remove Behave/Cucumber steps (not test fixtures)."""
    filtered = []
    
    for fixture in fixtures:
        src = fixture.raw_source
        
        # Behave decorators: @given, @when, @then
        if any(src.startswith(f"@{step}") for step in ["given", "when", "then"]):
            logger.debug(f"Filtering Behave step: {fixture.name}")
            continue
        
        filtered.append(fixture)
    
    return filtered

def extract_fixtures(file_path: Path, language: str) -> ExtractResult:
    """Extract fixtures from test file."""
    
    # ... existing code ...
    
    if language == "python":
        # IMPROVEMENT #5: Remove Behave/Cucumber steps
        fixtures = _filter_behave_steps(fixtures)
    
    return ExtractResult(...)
```

**Expected Impact:** 2-3% FP reduction  
**Effort:** 30 minutes  
**Risk:** LOW (Behave steps have distinct pattern)

---

## Enhancement: Confidence Intervals for Validation

**Location:** `collection/validator.py::compute_metrics()`

**Implementation:**
```python
import numpy as np
from scipy import stats

def wilson_confidence_interval(tp: int, fp: int, confidence: float = 0.95) -> tuple:
    """
    Compute Wilson score confidence interval for binomial proportion.
    More accurate than normal approximation for small samples.
    
    Args:
        tp: True positives
        fp: False positives
        confidence: Confidence level (0.95 = 95%)
    
    Returns:
        (lower_bound, upper_bound)
    """
    n = tp + fp
    if n == 0:
        return (0, 1)
    
    p = tp / n
    z = stats.norm.ppf((1 + confidence) / 2)
    denominator = 1 + z**2 / n
    centre_adjusted = p + z**2 / (2*n)
    adjusted_std = np.sqrt(p*(1-p)/n + z**2/(4*n**2))
    
    lower = (centre_adjusted - z*adjusted_std) / denominator
    upper = (centre_adjusted + z*adjusted_std) / denominator
    
    return (max(0, lower), min(1, upper))

def compute_metrics(csv_path: Path) -> dict:
    """Compute precision with confidence intervals."""
    
    # ... existing code ...
    
    print(
        f"{'Language':<14} {'Sample':>8} {'Precision':>12} {'95% CI':<20}"
    )
    print("-" * 56)
    
    for lang, group in labelled.groupby("language"):
        tp = (group["is_true_fixture"] == 1).sum()
        fp = (group["is_true_fixture"] == 0).sum()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        
        # ENHANCEMENT: Add confidence interval
        lower, upper = wilson_confidence_interval(int(tp), int(fp))
        ci_str = f"[{lower:.3f}, {upper:.3f}]"
        
        results[lang] = {
            "sampled": len(group),
            "true_positives": int(tp),
            "false_positives": int(fp),
            "precision": round(precision, 3),
            "ci_lower": round(lower, 3),
            "ci_upper": round(upper, 3),
        }
        
        print(f"{lang:<14} {len(group):>8} {precision:>11.1%} {ci_str:<20}")
```

**Expected Impact:** Improved academic rigor  
**Effort:** 1 hour  
**Risk:** VERY LOW (display enhancement only)

---

## Testing Strategy

### Unit Tests to Add

**File:** `tests/test_detector/test_precision.py` (NEW)

```python
class TestPrecisionImprovements:
    """Test that precision improvements reduce false positives."""
    
    def test_js_beforeeach_outside_test_file_not_detected(self):
        """JS beforeEach in non-test file should not be detected."""
        # Redux middleware using describe/beforeEach
        js_code = """
        const middleware = describe("Redux Store", () => {
            beforeEach(() => {
                store.reset();
            });
        });
        """
        # Should return 0 fixtures if not in test file context
        
    def test_python_setup_outside_testcase_not_detected(self):
        """Python setUp outside TestCase should not be detected."""
        # Non-test class with setUp method
        py_code = """
        class DataLoader:
            def setUp(self):
                self.db = connect()
        """
        # Should return 0 fixtures
        
    def test_python_setup_inside_testcase_is_detected(self):
        """Python setUp inside TestCase should be detected."""
        py_code = """
        import unittest
        class MyTest(unittest.TestCase):
            def setUp(self):
                self.db = setup_test_db()
        """
        # Should return 1 fixture
```

### Integration Tests

**File:** `tests/test_validator/test_precision_computation.py`

```python
class TestPrecisionComputation:
    """Test precision calculation and FP tracking."""
    
    def test_compute_metrics_with_fp_reasons(self, tmp_path):
        """Precision computation should track FP reasons."""
        # Create sample CSV with FP reasons
        csv_path = tmp_path / "sample.csv"
        csv_content = """language,fixture_name,is_true_fixture,false_positive_reason
python,test_setup,1,
javascript,beforeEach,0,JS_non_test_hook
python,setUp,0,python_setUp_no_testcase
java,setUp,1,
"""
        csv_path.write_text(csv_content)
        
        # Compute metrics
        results = compute_metrics(csv_path)
        
        # Check FP reason distribution
        assert results['python']['false_positives'] == 1
        assert results['javascript']['false_positives'] == 1
```

---

## Integration Checklist

Before committing changes:

- [ ] **Unit tests pass:** `pytest tests/test_detector/test_precision.py -v`
- [ ] **Integration tests pass:** `pytest tests/test_validator/ -v`
- [ ] **Full test suite passes:** `pytest`
- [ ] **No new regressions:** Compare precision before/after on same sample
- [ ] **Documentation updated:** Add improvements to detection docs
- [ ] **Code reviewed:** Peer review of precision changes

---

## Rollout Plan

### Week 1: JavaScript + Python Quick Wins
1. Implement JavaScript test context check
2. Implement Python TestCase inheritance check
3. Implement FP root cause tracking
4. Run precision sample, analyze results

### Week 2: Medium Improvements
5. Implement Java framework disambiguation
6. Implement Behave/Cucumber filtering
7. Test on full corpus

### Week 3: Validation Infrastructure
8. Add confidence intervals
9. Implement recall sampling (if needed)
10. Document findings

---

## Performance Impact

All improvements are **O(1) or O(log n)** additions:
- Test file context check: 1 regex match (FAST)
- TestCase inheritance check: 1 AST traversal (FAST)
- Framework inference: 1 string scan (FAST)
- FP reason tracking: CSV field (FAST)

**Expected runtime impact:** <1% slower collection

---

## Success Criteria

| Metric | Before | Target | Status |
|--------|--------|--------|--------|
| Precision | 85% | 92-93% | To be measured |
| JS FP rate | 20% | <5% | Target after Improvement #1 |
| Python FP rate | 12% | <3% | Target after Improvement #2 |
| Root cause tracking | None | 100% | After Improvement #3 |

---

## References

- [FALSE_POSITIVES_ROADMAP.md](FALSE_POSITIVES_ROADMAP.md) — Strategic overview
- [FIXTURE_DETECTION_ANALYSIS.md](FIXTURE_DETECTION_ANALYSIS.md) — Analysis details
- `collection/detector.py` — Implementation location
- `collection/validator.py` — Sampling & validation code
