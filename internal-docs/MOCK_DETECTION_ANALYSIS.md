# Mock Detection Analysis

**Date**: April 25, 2026  
**Status**: Mock classification has been **removed entirely** from codebase  
**Analysis Scope**: `collection/detector.py`, Lines 277-333  
**Languages Covered**: Python, Java, JavaScript, TypeScript  
**Database**: `collection/db.py` (mock_usages table, lines 100-110)

---

## Summary

Mock detection in FixtureDB uses **objective regex pattern matching** to identify mock framework calls. All subjective classifications (mock style, target layer) have been removed per data quality standards (April 25, 2026).

**Kept**: Framework identification (objective regex patterns)  
**Removed**: Mock style and target layer classifications (subjective heuristics)

---

## Mock Detection (Objective)

### Detection Mechanism

**Tool**: Regular expressions (15 patterns) matching framework-specific syntax  
**Languages**: Python, Java, JavaScript, TypeScript  
**Frameworks Detected**: 10 frameworks

```python
# Lines 277-299 in collection/detector.py
MOCK_PATTERNS = [
    # Python (3 patterns)
    (r"mock\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "unittest_mock"),
    (r"mocker\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "pytest_mock"),
    (r"MagicMock\s*\(|Mock\s*\(|AsyncMock\s*\(", "unittest_mock"),
    
    # Java (4 patterns)
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
]
```

### Detection Logic

**File**: `collection/detector.py`, Lines 301-333  
**Function**: `_extract_mocks(node, src_bytes: bytes) -> list[MockResult]`

```python
def _extract_mocks(node, src_bytes: bytes) -> list[MockResult]:
    text = _source(node, src_bytes)
    found = []
    
    # Regex matching over entire fixture source
    for pattern, framework in MOCK_PATTERNS:
        for m in re.finditer(pattern, text):
            # Extract target identifier (what's being mocked)
            target = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            
            # Extract context snippet around match
            snippet_start = max(m.start() - SNIPPET_CONTEXT_BEFORE, 0)
            snippet_end = min(m.end() + SNIPPET_CONTEXT_AFTER, len(text))
            snippet = text[snippet_start:snippet_end].replace("\n", " ")
            
            # Count mock configuration calls
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

### Reliability Assessment

**Reliability: 4 (Reliable, Minor Caveats)**

**Pros:**
- Deterministic regex matching — Same fixture always finds same mocks
- Language-specific patterns — Reduces false positives vs generic pattern
- Well-tested — 10 distinct frameworks across 4 languages
- Framework validation — Matches standard framework class/method names

**Cons:**
- Limited pattern coverage — Only detects explicit framework calls
- Custom mocking libraries — Patterns for non-standard frameworks won't be detected
- Partial matches — Captures mock instantiation, not always mock usage
- Go patterns removed (per language support decision)

**False Positive Risks:**
- Variable names coincidentally matching patterns (e.g., `mock_object` variable read as pattern)
- Comments containing mock patterns (e.g., "// use Mockito.mock()")
- String literals with framework names (rare)

---

## Metrics Exported (Objective Only)

**Fields Included in mock_usages.csv**:

| Field | Type | Objective? | Why |
|---|---|---|---|
| `framework` | TEXT | ✓ YES | Explicit regex match from MOCK_PATTERNS |
| `target_identifier` | TEXT | ✓ YES | String extracted from regex capture group |
| `num_interactions_configured` | INT | ✓ YES | Regex count of return_value/side_effect patterns |

**Aggregated at Fixture Level**:

| Field | Type | Objective? | Why |
|---|---|---|---|
| `num_mocks` | INT | ✓ YES | COUNT(*) FROM mock_usages WHERE fixture_id = X |

**Note on raw_snippet**: Excluded from CSV export (see exporter.py, line 150) as it is redundant with fixtures table raw_source and GitHub URLs. Kept in SQLite for researcher deep-dive.

---

## Removed Components (April 25, 2026)

The following subjective classifications were removed due to data quality standards:

### Removed: mock_style
- Was: Classification of mock type (stub/mock/spy/fake) using keyword heuristics
- Why Removed: Assumptions about method names indicating intent do not hold universally
- Example false positive: A `verify()` call on a stub is still a stub (verification doesn't make it a mock per original definition)

### Removed: target_layer
- Was: Classification of mocked target by architecture layer (boundary/infrastructure/internal/framework)
- Why Removed: Depends entirely on variable naming conventions; vulnerable to systematic misclassification
- Example false positive: `AwsHelper` (internal utility) classified as boundary due to "Aws" keyword

---

## Database Schema (Current)

**mock_usages table** (Lines 100-110 in db.py):

```sql
CREATE TABLE IF NOT EXISTS mock_usages (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id                  INTEGER NOT NULL REFERENCES fixtures(id),
    repo_id                     INTEGER NOT NULL REFERENCES repositories(id),
    framework                   TEXT,   -- unittest_mock/pytest_mock/mockito/
                                        -- easymock/jest/sinon/gomock/testify/...
    target_identifier           TEXT,   -- the string passed to mock (e.g. "mymodule.Client")
    num_interactions_configured INTEGER DEFAULT 0,
    raw_snippet                 TEXT    -- the mock call source text
);
```

**Changes from Previous Schema**:
- ~~mock_style~~ (TEXT) — REMOVED
- ~~target_layer~~ (TEXT) — REMOVED

---

## Data Export Policy

**✓ Include in mock_usages.csv**:
- `framework` (objective regex match)
- `target_identifier` (extracted string)
- `num_interactions_configured` (interaction count)
- `num_mocks` (aggregate count at fixture level)

**✗ Exclude from mock_usages.csv**:
- `raw_snippet` (redundant with fixtures.raw_source)

**✓ Store in SQLite Only**:
- `raw_snippet` (useful for researcher verification)

---

## Recommendations for Publication

1. **Document the regex patterns** — All 15 patterns are deterministic and reproducible; include in appendix or supplementary materials

2. **Limitations transparency** — Acknowledge that pattern-based detection has known limitations:
   - Custom frameworks not detected
   - Indirect setup (factory patterns) may be missed
   - Scope limited to fixture-level detection

3. **Use for aggregate analysis** — Safe to report:
   - "X% of fixtures use mocks"
   - "Average fixture has Y mocks"
   - Framework distribution (e.g., "Jest used in 60% of JavaScript fixtures")

4. **Enable reproducibility** — Researchers can:
   - Join fixtures → mock_usages tables to verify counts
   - Run same regex patterns on publicly available source code
   - Check GitHub URLs for fixture source inspection

5. **Avoid subjective claims** — Do NOT report classifications based on removed (mock_style, target_layer) fields

---

## Related Documentation

- **Framework Detection**: [docs/architecture/20-metrics-reference.md#210-framework-testing-framework-identification](docs/architecture/20-metrics-reference.md#210-framework-testing-framework-identification)
- **num_mocks Metric**: [docs/architecture/20-metrics-reference.md#211-num_mocks-mock-usage-count](docs/architecture/20-metrics-reference.md#211-num_mocks-mock-usage-count)
- **CSV Export Decisions**: [docs/data/14-csv-export-guide.md](docs/data/14-csv-export-guide.md)
- **Database Schema**: [collection/db.py](collection/db.py#L100-L110) (mock_usages table)

---

## Part 1: Mock Detection (Objective)

### 1.1 Detection Mechanism

**Tool**: Regular expressions (15 patterns) matching framework-specific syntax  
**Languages**: Python, Java, JavaScript, TypeScript (Go patterns will be removed per user request)  
**Frameworks Detected**: 10 frameworks

```python
# Lines 277-299 in collection/detector.py
MOCK_PATTERNS = [
    # Python (3 patterns)
    (r"mock\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "unittest_mock"),
    (r"mocker\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "pytest_mock"),
    (r"MagicMock\s*\(|Mock\s*\(|AsyncMock\s*\(", "unittest_mock"),
    
    # Java (4 patterns)
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
]
```

### 1.2 Detection Logic

**File**: `collection/detector.py`, Lines 301-333  
**Function**: `_extract_mocks(node, src_bytes: bytes) -> list[MockResult]`

```python
def _extract_mocks(node, src_bytes: bytes) -> list[MockResult]:
    text = _source(node, src_bytes)
    found = []
    
    # Regex matching over entire fixture source
    for pattern, framework in MOCK_PATTERNS:
        for m in re.finditer(pattern, text):
            # Extract target identifier (what's being mocked)
            target = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            
            # Extract context snippet around match
            snippet_start = max(m.start() - SNIPPET_CONTEXT_BEFORE, 0)
            snippet_end = min(m.end() + SNIPPET_CONTEXT_AFTER, len(text))
            snippet = text[snippet_start:snippet_end].replace("\n", " ")
            
            # Count mock configuration calls
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
                    mock_style=_classify_mock_style(...),  # Subjective (see Part 2)
                    target_layer=_classify_target_layer(...),  # Subjective (see Part 2)
                )
            )
    return found
```

### 1.3 Reliability Assessment

**Reliability: 4 (Reliable, Minor Caveats)**

**Pros:**
- Deterministic regex matching — Same fixture always finds same mocks
- Language-specific patterns — Reduces false positives vs generic pattern
- Well-tested — 10 distinct frameworks across 4 languages
- Framework validation — Matches standard framework class/method names

**Cons:**
- Limited pattern coverage — Only detects explicit framework calls
- Custom mocking libraries — Patterns for non-standard frameworks won't be detected
- Partial matches — Captures mock instantiation, not always mock usage
- Go patterns will be removed (user decision)

**False Positive Risks:**
- Variable names coincidentally matching patterns (e.g., `mock_object` variable read as pattern)
- Comments containing mock patterns (e.g., "// use Mockito.mock()")
- String literals with framework names (rare)

---

## Part 2: Mock Classification (Subjective)

### 2.1 Mock Style Classification

**File**: `collection/detector.py`, Lines 336-375  
**Function**: `_classify_mock_style(snippet: str, full_code: str, framework: str) -> str`

**Classification Priority (Heuristic-Based):**

```python
def _classify_mock_style(snippet: str, full_code: str, framework: str) -> str:
    """
    Classify mock object type: fake/spy/mock/stub
    
    Classification priority:
    1. fake: Custom implementation classes with logic
    2. spy: spy/wrap pattern with real object
    3. mock: Verify/assert patterns
    4. stub: Default (only return_value patterns)
    """
    
    # Priority 1: fake — Custom class implementation
    if re.search(r"class\s+\w+.*:", snippet):
        return "fake"
    
    # Priority 2: spy — Spy/wrap patterns
    spy_patterns = [
        r"spy\s*\(",              # Mockito: spy(object)
        r"patch\.object\s*\(",    # unittest_mock: patch.object
        r"spyOn\s*\(",            # Jest: spyOn
        r"spy\(",                 # Sinon: spy()
        r"\.when\s*\(",           # Mockito spy: when(...) on spy
    ]
    if any(re.search(p, snippet) for p in spy_patterns):
        return "spy"
    
    # Priority 3: mock — Verify/assert patterns
    verify_patterns = [
        r"\.verify\s*\(",         # Mockito: verify(mock)
        r"assert_called",         # unittest_mock: assert_called_*
        r"\.toHaveBeenCalled",    # Jest: toHaveBeenCalled
        r"calledWith\s*\(",       # Sinon: calledWith
        r"was_called_with",       # Mockito syntax variant
        r"\.verify\(",            # Mockito verify call
    ]
    if any(re.search(p, full_code) for p in verify_patterns):
        return "mock"
    
    # Default: stub (only return_value configured)
    return "stub"
```

### 2.2 Classification Issues (Subjective)

| Classification | Heuristic | Risk Level | Example False Positive |
|---|---|---|---|
| **fake** | Presence of `class` keyword in snippet | **High** | Helper class definition, test utility class |
| **spy** | `spy()`, `patch.object()`, `spyOn()` keywords | **Medium** | Spy used for testing internals (valid), but spy assumes wrapping |
| **mock** | `.verify()`, `assert_called()`, `.toHaveBeenCalled()` keywords | **Low** | Rarely appears in non-mock context |
| **stub** | Default fallback (no other keywords match) | **Medium** | Legitimate stubbed behavior may not match keyword list |

**Key Issue**: The classification assumes **method names indicate intent**. But:
- A `verify()` call on a stub is still a stub (verification doesn't make it a mock per original definition)
- A `spy()` call might be testing internals (not wrapping a real object)
- A `class` definition might be a helper, not a test double

### 2.3 Mock Style in Database

**Storage**: `mock_usages` table, column `mock_style` (Line 105 in db.py)

```sql
CREATE TABLE mock_usages (
    ...
    mock_style  TEXT,  -- stub/mock/spy/fake (filled by classifier)
    ...
);
```

**CSV Export**: **EXCLUDED** (Line 146 in exporter.py)
```python
exclude_cols=["mock_style", "target_layer", "raw_snippet"]
```

**Rationale**: Subjective classification; not suitable for public dataset.

---

## Part 3: Target Layer Classification (Subjective)

### 3.1 Classification Mechanism

**File**: `collection/detector.py`, Lines 377-433  
**Function**: `_classify_target_layer(target_id: str, framework: str, snippet: str, full_code: str) -> str`

**Classification Priority (Keyword-Matching Heuristics):**

```python
def _classify_target_layer(target_id: str, framework: str, snippet: str, full_code: str) -> str:
    """
    Classify mocked target by architectural layer.
    
    Classification priority:
    1. framework: Testing/DI framework components
    2. boundary: External services and APIs
    3. infrastructure: Persistence, caching, logging
    4. internal: Application domain classes (default)
    """
    target_lower = target_id.lower()
    
    # Priority 1: Framework keywords (23 keywords)
    framework_keywords = [
        "pytest", "unittest", "junit", "spring", "django", "fastapi",
        "request", "response", "session", "engine", "httpresponse",
        "servletrequest", "httpservletresponse", "mockmvc",
        "dependency", "inject", "container", "bean",
        "resolver", "interceptor", "aspect", "middleware", "decorator"
    ]
    if any(kw in target_lower for kw in framework_keywords):
        return "framework"
    
    # Priority 2: Boundary layer keywords (21 keywords)
    boundary_keywords = [
        "requests", "urllib", "httplib", "axios", "fetch",
        "stripe", "paypal", "aws", "azure", "gcp", "gmail", "email",
        "twilio", "sendgrid", "github", "gitlab",
        "apikey", "api_", "oauth", "auth", "service", "client", "sdk"
    ]
    if any(kw in target_lower for kw in boundary_keywords):
        return "boundary"
    
    # Priority 3: Infrastructure layer keywords (20 keywords)
    infrastructure_keywords = [
        "database", "db", "cache", "redis", "mongo", "sql", "postgres",
        "repository", "dao", "store", "logger", "log",
        "file", "filesystem", "path", "queue", "kafka", "rabbitmq",
        "bucket", "storage", "stream"
    ]
    if any(kw in target_lower for kw in infrastructure_keywords):
        return "infrastructure"
    
    # Default: Internal (application domain)
    return "internal"
```

### 3.2 Classification Issues (Subjective)

| Layer | Keywords | Risk Level | Example False Positive |
|---|---|---|---|
| **framework** | 23 keywords (pytest, django, spring, inject, etc.) | **Medium** | `UserRepository` (not framework), `SessionManager` (not session singleton) |
| **boundary** | 21 keywords (requests, stripe, aws, oauth, etc.) | **High** | `StripeConfiguration` (internal config), `AwsHelper` (utility class) |
| **infrastructure** | 20 keywords (database, redis, logger, etc.) | **High** | `DatabaseFactory` (internal), `LoggerConfiguration` (internal) |
| **internal** | Default fallback | **Low** | Catch-all for unmatchable targets |

**Key Issue**: Classification depends entirely on **variable/class names**:
- `database` in name → classified as infrastructure (could be database factory, config, or domain object)
- `service` in name → classified as boundary (could be internal service, domain service, or utility)
- `aws` in name → classified as boundary (could be internal AWS configuration wrapper)

**Vulnerability**: Misleading naming conventions can cause systematic misclassification.

### 3.3 Target Layer in Database

**Storage**: `mock_usages` table, column `target_layer` (Line 106 in db.py)

```sql
CREATE TABLE mock_usages (
    ...
    target_layer  TEXT,  -- boundary/infrastructure/internal/framework
    ...
);
```

**CSV Export**: **EXCLUDED** (Line 146 in exporter.py)

**Rationale**: Subjective keyword-based classification; not suitable for public dataset.

---

## Part 4: Objective Metrics (Included in CSV)

### 4.1 What's Exported: Objective Data

**Fields Included in fixtures.csv** (via automatic export, not explicitly included):

| Field | Type | Objective? | Why |
|---|---|---|---|
| `num_mocks` | INT | ✓ YES | Direct count from mock_usages table |
| `framework` | TEXT | ✓ YES | Explicit regex match from MOCK_PATTERNS |
| `target_identifier` | TEXT | ✓ YES | String extracted from regex capture group |
| `num_interactions_configured` | INT | ✓ YES | Regex count of return_value/side_effect patterns |

**Note**: `num_mocks` is a **new fixture-level aggregate** (April 2026) calculated as:
```sql
num_mocks = COUNT(*) FROM mock_usages WHERE fixture_id = X
```

### 4.2 What's Excluded: Subjective Data

**Fields EXCLUDED from mock_usages.csv** (Line 146 in exporter.py):

| Field | Excluded Why |
|---|---|
| `mock_style` | Heuristic classification (stub/mock/spy/fake) |
| `target_layer` | Keyword-based classification (boundary/infra/internal/framework) |
| `raw_snippet` | Redundant with fixtures.raw_source + GitHub URLs |

---

## Part 5: Summary Assessment

### 5.1 Objective vs. Subjective Breakdown

| Component | Type | Confidence | Research Use |
|---|---|---|---|
| **Mock detection (framework match)** | Objective | High ✓ | Safe for publication |
| **num_mocks (count)** | Objective | High ✓ | Safe for publication (NEW in April 2026) |
| **target_identifier (extracted name)** | Objective | High ✓ | Safe for publication |
| **num_interactions_configured (count)** | Objective | High ✓ | Safe for publication |
| **mock_style (fake/spy/mock/stub)** | Subjective | Medium ✗ | Internal analysis only |
| **target_layer (boundary/infra/internal)** | Subjective | Medium ✗ | Internal analysis only |

### 5.2 Limitations

1. **Limited pattern coverage** — Only detects explicit mock framework calls
   - Custom mocking libraries not detected
   - Mock factories or builders not captured
   - Indirect mock setup (factory patterns) may be missed

2. **Keyword-based classification risks**
   - Variable naming conventions affect accuracy
   - No semantic understanding of code intent
   - False positives from coincidental naming (e.g., `MockUserService` is a real service, not a test double)

3. **Interaction counting heuristics**
   - Only counts `.return_value|side_effect|thenReturn|thenThrow|doReturn` patterns
   - Other configuration methods (matchers, answers, callbacks) not counted
   - Conservative estimate; actual interactions may be higher

4. **Scope limitations**
   - Detects mocks at fixture level only
   - Mocks setup in test functions not captured
   - Mocks in setup methods may or may not be linked to fixture

### 5.3 Data Export Policy

**✓ Include in fixtures.csv**:
- `num_mocks` (objective count)
- Framew reported with each mock (join to mock_usages table)
- `raw_source` for manual verification

**✗ Exclude from public CSV**:
- `mock_style` (subjective heuristic)
- `target_layer` (keyword-based heuristic)
- `raw_snippet` (redundant with raw_source)

**✓ Store in SQLite**:
- All fields available for researcher deep-dive
- Subjective classifications useful for internal analysis and hypothesis generation

---

## Recommendations for Publication

1. **Document the objective metrics** — `num_mocks`, `framework`, `target_identifier`, `num_interactions_configured` are deterministic and reproducible

2. **Acknowledge limitations** — Pattern-based detection has known limitations (custom frameworks, indirect setup)

3. **Use for aggregate analysis** — Safe to report "X% of fixtures use mocks" or "Average fixture has Y mocks"

4. **Avoid subjective classifications in conclusions** — Don't claim "X% of mocks are boundary layer" without acknowledging keyword-matching heuristics

5. **Transparency in supplementary materials** — Document the 15 regex patterns and 64 keywords used for classification in appendix

6. **Enable reproducibility** — Researchers can:
   - Join fixtures → mock_usages tables to verify counts
   - Run same regex patterns on publicly available source code
   - Check GitHub URLs for fixture source inspection

---

## Related Documentation

- **Framework Detection**: [docs/architecture/20-metrics-reference.md#210-framework-testing-framework-identification](docs/architecture/20-metrics-reference.md#210-framework-testing-framework-identification)
- **Mock Detection Architecture**: [docs/architecture/11-detection.md#mock-detection](docs/architecture/11-detection.md#mock-detection)
- **CSV Export Decisions**: [docs/data/14-csv-export-guide.md](docs/data/14-csv-export-guide.md)
- **Database Schema**: [collection/db.py](collection/db.py#L100-L113) (mock_usages table)
