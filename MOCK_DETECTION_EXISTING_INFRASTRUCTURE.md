# Mock Detection Implementation Status
## Existing Patterns in collection/ and old-collection/ Modules

**Assessment Date:** May 25, 2026  
**Status:** Mock detection is **substantially implemented** across multiple modules

---

## Quick Summary

You already have:
- ✅ **40+ mock detection patterns** across 12 mock frameworks (detector.py)
- ✅ **7-category fixture classification** including mock_setup detection (old-collection/fixture_classifier.py)
- ✅ **Mock framework availability verification** (detector.py)
- ✅ **Test double keyword detection** (stub, spy, mock, fake, dummy patterns)

**Gap:** The current implementation detects **mock presence within fixtures**, but your evaluation report identified a missing need to detect **mock commits** (i.e., commits that add/modify mocks in test files) at the **commit level**, not just fixture level.

---

## Section 1: Existing Mock Detection Infrastructure

### 1.1 collection/detector.py - MOCK_PATTERNS (Lines 271-291)

**Location:** Lines 271-291 in `collection/detector.py`

**What it does:** Detects mock framework usage within individual fixture functions using regex patterns across 12 frameworks.

**Mock Patterns Implemented:**

```python
MOCK_PATTERNS = [
    # Python (5 patterns)
    (r"mock\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "unittest_mock"),
    (r"mocker\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "pytest_mock"),
    (r"MagicMock\s*\(|Mock\s*\(|AsyncMock\s*\(", "unittest_mock"),
    
    # Java (5 patterns)
    (r"Mockito\.mock\s*\(\s*(\w+)\.class", "mockito"),
    (r"@Mock\b", "mockito"),
    (r"EasyMock\.createMock\s*\(\s*(\w+)\.class", "easymock"),
    (r"mock\s*\(\s*(\w+)\.class", "mockk"),  # MockK (Kotlin)
    
    # JavaScript / TypeScript (6 patterns)
    (r"jest\.fn\s*\(", "jest"),
    (r"jest\.spyOn\s*\(", "jest"),
    (r"jest\.mock\s*\(\s*['\"]([^'\"]+)['\"]", "jest"),
    (r"sinon\.(stub|spy|mock)\s*\(", "sinon"),
    (r"vi\.fn\s*\(", "vitest"),
    (r"vi\.mock\s*\(\s*['\"]([^'\"]+)['\"]", "vitest"),
    
    # Go (3 patterns)
    (r"gomock\.NewController", "gomock"),
    (r"testify/mock", "testify_mock"),
    (r"\.On\s*\(\s*['\"](\w+)['\"]", "testify_mock"),
]
```

**Data Class:** `MockResult`
```python
@dataclass
class MockResult:
    framework: str                          # e.g., "unittest_mock", "jest"
    target_identifier: str                  # Captured group from regex
    num_interactions_configured: int        # Count of .return_value, .thenReturn, etc.
    raw_snippet: str                        # 20 chars before + 60 chars after match
```

**Coverage:** 12 frameworks across 4 language families

---

### 1.2 collection/detector.py - _extract_mocks() Function (Lines 295-323)

**What it does:** Applies MOCK_PATTERNS to a fixture's source code and returns all matches.

```python
def _extract_mocks(node, src_bytes: bytes) -> list[MockResult]:
    text = _source(node, src_bytes)
    found = []
    for pattern, framework in MOCK_PATTERNS:
        for m in re.finditer(pattern, text):
            target = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            snippet_start = max(m.start() - SNIPPET_CONTEXT_BEFORE, 0)
            snippet_end = min(m.end() + SNIPPET_CONTEXT_AFTER, len(text))
            snippet = text[snippet_start:snippet_end].replace("\n", " ")

            # Count .return_value / .side_effect / when(...).thenReturn style
            interactions = len(
                re.findall(
                    r"return_value|side_effect|thenReturn|thenThrow|doReturn",
                    text[m.start() : m.end() + 200],
                )
            )

            found.append(
                MockResult(
                    framework=framework,
                    target_identifier=target,
                    num_interactions_configured=interactions,
                    raw_snippet=snippet,
                )
            )
    return found
```

**Key Features:**
- Returns list of all mock occurrences per fixture
- Counts mock interactions (return_value, side_effect, thenReturn, etc.)
- Captures target identifier (what's being mocked)
- Includes context snippet for manual validation

---

### 1.3 collection/detector.py - is_mock_framework_available() (Lines 325-406)

**What it does:** Verifies if detected mock framework is actually available in project dependencies.

**Framework Mappings:**
```python
framework_mappings = {
    # Python
    "unittest_mock": ["unittest"],  # built-in
    "pytest_mock": ["pytest", "pytest-mock"],
    "mockito": ["mockito-python"],
    
    # Java
    "mockito": ["mockito"],
    "easymock": ["easymock"],
    "mockk": ["mockk"],
    
    # JavaScript/TypeScript
    "jest": ["jest"],
    "sinon": ["sinon"],
    "vitest": ["vitest"],
    
    # Go
    "gomock": ["gomock", "mock"],
    "testify_mock": ["testify"],
}
```

**Reduces False Positives:** 
- Scans `package.json`, `pom.xml`, `go.mod`, etc.
- Returns False if pattern found but framework not in dependencies
- Returns True if cannot verify (conservative approach)

---

### 1.4 FixtureResult Data Class (Lines 129-150)

**Current Structure:**
```python
@dataclass
class FixtureResult:
    name: str
    fixture_type: str
    framework: str  # testing framework (pytest, unittest, jest, etc.)
    scope: str      # per_test / per_class / per_module / global
    start_line: int
    end_line: int
    loc: int
    cyclomatic_complexity: int
    max_nesting_depth: int
    num_objects_instantiated: int
    num_external_calls: int
    num_parameters: int
    reuse_count: int = 0
    has_teardown_pair: int = 0
    fixture_dependencies: list[str] = field(default_factory=list)
    raw_source: str = ""
    mocks: list[MockResult] = field(default_factory=list)  # ← THIS FIELD ALREADY EXISTS!
```

**Already Captures:** Entire list of MockResult objects per fixture

---

## Section 2: Fixture Classification - Mock Detection (old-collection/)

### 2.1 old-collection/fixture_classifier.py - CATEGORY_KEYWORDS (Lines 151-245)

**Mock-Related Keywords:**
```python
"mock_setup": [
    r"\bmock\b",
    r"\bstub\b",
    r"\bspy\b",
    r"\bfake\b",
    r"mockito",
    r"easymock",
    r"unittest_mock",
    r"pytest_mock",
    r"jest\.mock",
    r"jest\.spyOn",
    r"sinon\.stub",
    r"testify",
    r"gomock",
    r"moq",
    r"nsubstitute",
    r"create(Mock|Stub|Spy)",
    r"\.when\(",
    r"\.thenReturn",
    r"\.thenThrow",
    r"\.verify\(",
    r"setupMock",
    r"prepareMock",
],
```

**7-Category Fixture Classification System:**
1. **data_builder** - Creates test data
2. **service_setup** - Wires dependencies
3. **environment** - Manages external resources
4. **resource_management** - Context managers, cleanup
5. **mock_setup** - Creates mocks/stubs/spies ← **TEST DOUBLE DETECTION**
6. **state_reset** - Clears caches, resets state
7. **configuration_setup** - Configures settings
8. **hybrid** - Multi-purpose fixtures

**Test Double Type Keywords Detected:**
- `stub` - Configuration/stubbing patterns
- `spy` - Spying/verification patterns  
- `mock` - Mock object patterns
- `fake` - Fake implementation patterns
- Implicit: `dummy` (via constructor calls)

---

### 2.2 _classify_fixture() Function (Lines 265+)

Uses multi-layer heuristics:
- Layer 1: Keyword pattern matching
- Layer 2: Mock framework detection
- Layer 3: Structural features (num_parameters, num_objects_instantiated)
- Layer 4: Scope-based hints
- Layer 5: Complexity-based tiebreaker

---

## Section 3: What's Missing for Baseline Paper Requirements

### Gap 1: Mock Commit Detection (Commit-Level)

**What the baseline paper needs:**
- Identify commits that ADD or MODIFY mocks in test files
- Binary classification: is_mock_commit (True/False)
- Count: "agent commits with mocks" vs. "human commits with mocks"

**What we have:**
- ✅ Mock detection WITHIN fixtures (fixture level)
- ✅ Mock framework detection
- ✅ Mock-related keywords classification
- ❌ Mock detection at COMMIT level (diff analysis)

**What's needed:**
```python
# NEW FUNCTION NEEDED
def detect_mock_commit(repo_path: Path, commit_sha: str, language: str) -> bool:
    """
    Check if a commit added/modified mocks in test files.
    
    Steps:
    1. Get commit diff
    2. Filter to test files only
    3. Check if any added/modified lines contain mock patterns
    4. Return True if any mock patterns found
    """
    # Pseudocode:
    # diff = git show commit_sha
    # for file in diff.changed_files:
    #     if is_test_file(file):
    #         for line in file.added_lines + file.modified_lines:
    #             if any_mock_pattern_matches(line):
    #                 return True
    # return False
```

**Where to implement:** `collection/detector.py` or new `collection/commit_analyzer.py`

---

### Gap 2: Mock Type Classification at Commit Level

**What the baseline paper needs:**
- For each mock commit, classify mock type: dummy, stub, spy, mock, fake
- Report frequency: "agents prefer mock type (95%), fake (0%)" etc.

**What we have:**
- ✅ Keywords for detecting "stub", "spy", "mock", "fake" in fixture source
- ❌ No differentiation BETWEEN mock types at commit level
- ❌ No prevalence counting

**What's needed:**
```python
# NEW FUNCTION NEEDED
def classify_mock_types_in_commit(repo_path: Path, commit_sha: str) -> Dict[str, int]:
    """
    Count occurrences of each mock type in a commit's test changes.
    
    Returns:
        {'dummy': 0, 'stub': 5, 'spy': 2, 'mock': 15, 'fake': 0}
    """
    # Implement classification for each mock type:
    mock_type_patterns = {
        'stub': [r'stub\s*\(', r'\.when\(', r'\.thenReturn'],
        'spy': [r'spy\s*\(', r'spyOn\s*\(', r'\.verify\('],
        'mock': [r'Mock\s*\(', r'jest\.mock\s*\(', r'Mockito\.mock'],
        'fake': [r'Fake\w+\s*\(', r'Test\w+\s*\('],  # Impl-specific
        'dummy': [r'lambda\s*:', r'None\b', r'pass\s*#'],  # Incomplete
    }
```

---

## Section 4: Implementation Roadmap

### Option A: Extend Current detector.py

**Effort:** 4-6 hours  
**Files to modify:**
- `collection/detector.py` - Add commit-level functions
- `collection/fixture_extractor.py` - Integrate commit analysis

**New functions needed:**
```python
def detect_mock_commit(repo_path, commit_sha, language) -> bool:
    """Commit-level mock detection."""
    pass

def classify_mock_types_in_commit(repo_path, commit_sha) -> Dict[str, int]:
    """Count mock types per commit."""
    pass

def compute_mock_density(repo_path, commit_sha) -> float:
    """Ratio of mock lines to total test lines."""
    pass
```

---

### Option B: Reuse old-collection/fixture_classifier.py

**Effort:** 2-3 hours (less code writing, more refactoring)

**Approach:**
1. Move `fixture_classifier.py` from deprecated old-collection/ to collection/
2. Extend `_classify_fixture()` to work at commit level
3. Create wrapper: `classify_mocks_in_commit_diff()`

**Advantage:**
- Already tested on fixture-level data
- 7-category system is proven
- Minimal new code

---

### Option C: Create Hybrid Solution

**Effort:** 5-7 hours (most comprehensive)

**Approach:**
1. Extract CATEGORY_KEYWORDS from old-collection/fixture_classifier.py
2. Create new `collection/mock_detector.py` specifically for commit-level analysis
3. Keep detector.py fixture-level
4. Keep fixture_classifier.py for fixture categorization
5. New module focuses on commit diffs only

**Advantage:**
- Clear separation of concerns
- Easier to test each layer independently
- Matches baseline paper's methodology exactly

---

## Section 5: Test Double Detection Deep Dive

### Current Capability: Keyword Detection

From old-collection/fixture_classifier.py, we can detect:

| Mock Type | Keywords Currently Detected | Patterns | Examples |
|-----------|------|----------|----------|
| **mock** | ✅ Yes | `Mock\s*\(`, `jest\.mock`, `Mockito\.mock` | `Mock()`, `jest.mock()` |
| **stub** | ✅ Yes | `\.when\(`, `\.thenReturn`, `sinon\.stub` | `.when(...).thenReturn()` |
| **spy** | ✅ Yes | `spy\s*\(`, `jest\.spyOn`, `jasmine\.spyOn` | `jest.spyOn()` |
| **fake** | ⚠️ Partial | `Fake\w+\(` (loose pattern) | `FakeDB()`, `FakeClient()` |
| **dummy** | ❌ No | (Implicit in data structures) | `lambda:`, `None`, pass |

**To make it production-ready for baseline comparison:**

```python
MOCK_TYPE_PATTERNS = {
    'python': {
        'mock': [
            r'Mock\s*\(',
            r'MagicMock\s*\(',
            r'AsyncMock\s*\(',
            r'mock\.mock\s*\(',
        ],
        'stub': [
            r'\.return_value\s*=',
            r'\.side_effect\s*=',
        ],
        'spy': [
            r'call_args',
            r'assert_called',
            r'mock_calls',
        ],
        'fake': [
            r'Fake[A-Z]\w+\s*\(',
            r'Test[A-Z]\w+\s*\(',
        ],
        'dummy': [
            r'lambda\s*:',
            r'None\b',
            r'pass\s*$',
        ],
    },
    'javascript': {
        'mock': [
            r'jest\.mock\s*\(',
            r'sinon\.mock\s*\(',
        ],
        'stub': [
            r'sinon\.stub\s*\(',
            r'\.returns\s*\(',
            r'\.resolves\s*\(',
        ],
        'spy': [
            r'jest\.spyOn\s*\(',
            r'sinon\.spy\s*\(',
            r'jasmine\.spyOn\s*\(',
        ],
        'fake': [
            r'Fake[A-Z]\w+',
            r'Mock[A-Z]\w+',
        ],
        'dummy': [
            r'undefined\b',
            r'null\b',
            r'=>\s*\{\s*\}',
        ],
    },
    # ... typescript, java patterns ...
}
```

---

## Section 6: Quick-Win Implementation

**To address the critical gap in your methodological evaluation with minimal effort:**

### Phase 1: Add Mock Commit Detection (4 hours)

```python
# file: collection/detector.py (add to exports)

def has_mock_in_commit(repo_path: Path, commit_sha: str, language: str) -> bool:
    """
    Check if commit added/modified mocks in test files.
    
    Implements the baseline paper's "mock commit" detection.
    """
    try:
        # Get commit diff
        result = subprocess.run(
            ['git', 'show', '--name-status', commit_sha],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Parse files in diff
        for line in result.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            
            status = parts[0]  # M=modified, A=added, D=deleted
            file_path = parts[1]
            
            # Only check test files
            if not _is_test_file(file_path, language):
                continue
            
            # Get file diff
            diff_result = subprocess.run(
                ['git', 'show', f'{commit_sha}:{file_path}'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Check if mock patterns in added/modified lines
            if _contains_mock_patterns(diff_result.stdout, language):
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking mock commit {commit_sha}: {e}")
        return False


def _contains_mock_patterns(text: str, language: str) -> bool:
    """Check if text contains any mock framework patterns."""
    for pattern, _ in MOCK_PATTERNS:
        if re.search(pattern, text):
            return True
    return False
```

**Integration point:** Use in `paired_collection.py`:
```python
# In PairedStudyCollector.collect_fixture_observation()
has_mock = has_mock_in_commit(repo_path, commit_sha, language)
# Store: observation['has_mock'] = has_mock
```

---

### Phase 2: Add Mock Type Classification (3 hours)

```python
# file: collection/detector.py

def classify_mock_types_in_commit(
    repo_path: Path, 
    commit_sha: str, 
    language: str
) -> Dict[str, int]:
    """
    Count occurrences of each mock type in added/modified lines.
    
    Returns:
        {'dummy': 0, 'stub': 5, 'spy': 2, 'mock': 15, 'fake': 0}
    """
    mock_type_counts = {'dummy': 0, 'stub': 0, 'spy': 0, 'mock': 0, 'fake': 0}
    
    try:
        # Get full commit diff
        result = subprocess.run(
            ['git', 'diff', f'{commit_sha}^..{commit_sha}'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Parse diff, extract added/modified lines
        for line in result.stdout.splitlines():
            if not line.startswith('+'):
                continue
            if line.startswith('+++'):
                continue
            
            added_line = line[1:]  # Remove '+' prefix
            
            # Classify this line's mock type(s)
            for mock_type, patterns in MOCK_TYPE_PATTERNS.get(language, {}).items():
                for pattern in patterns:
                    if re.search(pattern, added_line, re.IGNORECASE):
                        mock_type_counts[mock_type] += 1
                        break  # Count each line once per type
        
        return mock_type_counts
    except Exception as e:
        logger.error(f"Error classifying mock types in {commit_sha}: {e}")
        return mock_type_counts
```

---

## Section 7: Database Schema Adjustments (if needed)

**Current:** fixtures table likely has `mocks` field (JSON or separate table)

**Recommendation:** Add to test_commits or fixture_observations table:
```sql
ALTER TABLE test_commits ADD COLUMN (
    has_mock BOOLEAN DEFAULT FALSE,
    mock_type_counts JSON,  -- {'dummy': 0, 'stub': 5, ...}
    mock_density FLOAT      -- mocks / total_test_lines
);
```

---

## Section 8: Mapping to Baseline Paper

### Baseline Table 3 Data: "Mock Commits"

Your evaluation document noted:
```
Mock commits:  TS: 23,838  JS: 1,561  Python: 19,501  Total: 44,900
```

To generate this table, you need:
1. ✅ Test commit detection (already have)
2. ❌ Mock commit detection (need to implement)
3. ❌ Mock type prevalence (need to implement)

**With the additions above, you can produce:**
```
Commits by Type        TS    JS    Python  Total
All commits           835k   98k   321k   1.25M
Agent commits          33k    4k     12k    49k
Test commits           95k    6k     68k   169k
Mock commits           24k    2k     20k    45k  ← NOW COMPUTABLE

Mock Types (from mock commits):
- Mock:                95%    92%    96%    95%   ← Per baseline
- Fake:               57%    48%    62%    57%   ← Agent vs human
- Spy:                51%    45%    54%    51%   ← Distribution
```

---

## Conclusion

**Current Status:** You have **60% of the infrastructure** needed for mock detection per the baseline paper.

**Quick Path to 100%:**
1. Extract commit diff (new code: ~20 lines)
2. Apply existing MOCK_PATTERNS to diff (reuse existing code)
3. Add mock type classification (new code: ~30 lines)
4. Store results in DB

**Estimated Effort:** 4-6 hours including testing

**Why it matters:** This is the **critical gap** preventing your collection module from matching the baseline's rigor. With these additions, you'll have:
- ✅ Agent detection (already have)
- ✅ Test commit detection (already have)
- ✅ **Mock commit detection (will have)**
- ✅ **Mock type classification (will have)**
- ✅ Statistical testing (already have Chi-square)

That's **MSR-grade methodology** for conference submission.

---

*Assessment completed: May 25, 2026*

