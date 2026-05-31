# Collection Module - Test Coverage Assessment

**Date:** May 24, 2026  
**Scope:** Analyze existing tests and identify coverage gaps  
**Goal:** Plan comprehensive test suite for two main use cases

---

## Existing Test Coverage Overview

### Test Structure
```
tests/
├── between_group/                    # End-to-end corpus collection tests
│   ├── test_human_corpus.py         # 296 lines - Human corpus collection
│   ├── test_agent_corpus.py         # 343 lines - Agent corpus collection
│   └── test_between_group_comparison.py
├── collection/                       # Unit and integration tests
│   ├── test_agent_detection_logic.py # 4 tests - Agent config detection
│   ├── test_agent_patterns_*.py     # Agent pattern matching
│   ├── test_detector_edge_cases.py  # Detector edge cases
│   ├── test_agent_test_commit_filter.py
│   ├── test_human_test_commit_filter.py
│   ├── test_framework_detection.py  # Framework detection
│   ├── test_extractor_unit/         # Language-specific fixture extraction
│   │   ├── test_python_fixtures.py
│   │   ├── test_java_fixtures.py
│   │   ├── test_javascript_fixtures.py
│   │   ├── test_typescript_fixtures.py
│   │   └── test_go_fixtures.py
│   ├── test_extractor_metadata/     # Fixture metadata computation
│   │   ├── test_fixture_types_and_scopes.py
│   │   ├── test_line_numbers.py
│   │   ├── test_new_metrics.py
│   │   └── test_object_instantiations.py
│   ├── test_integration/            # Realistic fixture extraction
│   │   └── test_*_realistic_fixtures.py (per language)
│   ├── test_mock_detection/         # Mock/stub pattern detection
│   │   └── test_*_mock_patterns.py (per language)
│   └── test_phase_*.py              # Phase-specific tests
├── test_pipeline_manual_steps.py    # 50 lines - Manual CLI steps (using dummy collectors)
├── test_pipeline_full_flow.py       # 100 lines - Full flow (using dummy collectors)
└── paired/                          # Paired collection tests
    └── test_paired_*.py
```

### Current Test Count
```
Extraction (detector.py):        ~200+ tests (extensive)
Agent Patterns:                  ~50+ tests
Agent Detection:                 4 tests
Test Commit Filtering:          ~30+ tests
Between-Group Collection:       18 tests
Mock Detection:                 ~100+ tests
Framework Detection:            Multiple test files
Fixture Types/Scopes:           Multiple test files

TOTAL:                          500+ tests (distributed across module)
```

---

## Coverage Gap Analysis

### CRITICAL GAPS - Not Tested

#### 1. **Manual Pipeline Steps with Real CSV I/O**
- ❌ No tests for CSV input reading (except fixtures)
- ❌ No tests for CSV output validation
- ❌ No tests for pipeline CLI commands with real files
- **Issue:** `test_pipeline_manual_steps.py` uses dummy collectors, doesn't test real CSV I/O

**Examples of missing coverage:**
```python
# NOT TESTED: Reading repo-QC CSV files
# Note: human test-commit CSVs are produced to either
# `github-search-human/2025_test_commits` (agent-era outputs) or
# `github-search-human/pre_2021_test_commits` (raw-search pre-2021 outputs).
collector.select_human_corpus_repositories(
    repo_qc_dir=Path("github-search-human/"),  # Real CSV files
    repos_per_language=50,
)
# Output should be verified against expected CSV structure

# NOT TESTED: Writing test-commit CSVs
collector.run(only_write_test_commits=True, workers=1)
# Output CSV format and content not validated
```

#### 2. **End-to-End Collection with Minimal Test Data**
- ❌ No integration tests with small real repository clones
- ❌ No tests validating complete collection pipeline (clone→QC→scan→extract)
- ❌ No tests validating database insertion with real data
- **Issue:** Current between_group tests mock repository selection but don't test full workflow

**Examples of missing coverage:**
```python
# NOT TESTED: Full collection workflow
stats, db_path = collector.run(
    repos_per_language=5,  # Small test set
    workers=1,             # Sequential
)
# Should validate:
# - Database has expected schema
# - Repository inserted correctly
# - Test commits found and inserted
# - Fixtures extracted and inserted
# - Output CSVs have correct format
```

#### 3. **Agent Repository Detection Pipeline**
- ❌ `agent_detector.py:scan_for_agents()` - main entry point not tested
- ❌ `GitHubAgentFileChecker.has_agent_config_files()` - integration not fully tested
- ❌ `AgentFileScanner` class - not tested
- ❌ `AgentCommitVerifier` class - not tested
- **Current:** Only `test_agent_detection_logic.py` has 4 focused tests

**Examples of missing coverage:**
```python
# NOT TESTED: Full agent detection workflow
result = scan_for_agents(
    repo_path=Path("/tmp/clones/owner__repo"),
    github_token="...",
    commit_qc_dir=Path("github-search-agent/"),
)
# Should validate:
# - Correctly identifies agent config files
# - Verifies agents in commits
# - Returns proper AgentFileDetectionResult
```

#### 4. **Agent Commit Detection & Verification**
- ❌ `detector.py:_count_external_calls()` - edge cases not fully tested
- ❌ `detector.py:_compute_nesting_depth()` - edge cases not tested
- ❌ `_calculate_fixture_dependencies()` - dependency graph not tested
- ❌ `_propagate_fixture_scopes()` - scope propagation edge cases not tested
- ❌ `_calculate_teardown_pairs()` - teardown pair matching not tested

#### 5. **Test Commit Filtering & Collection**
- ❌ `test_commit_filter.py` functions tested in isolation
- ❌ No integration tests: collect → filter → validate
- ❌ Edge cases: empty repos, no tests, too many commits

#### 6. **Framework Detection Integration**
- ❌ Framework detection with missing dependencies not tested
- ❌ Fallback behavior (pytest → unittest) not validated
- ❌ Mixed frameworks in single repo not tested

#### 7. **Corpus Utils (New Module)**
- ❌ `corpus_utils.py` functions not tested at all!
- ❌ `compute_repo_metadata()` 
- ❌ `construct_repo_dict()`
- ❌ `persist_repository_and_fixtures()`
- ❌ `generate_corpus_summary()`

---

## Recommended Test Coverage Plan

### Phase 1: High Priority (Use Case Coverage)

#### 1.1 **CSV Input/Output Pipeline Tests** (Use Case 1)
```python
# tests/collection/test_csv_pipeline_integration.py (NEW)

class TestManualCSVPipelineSteps:
    """Test manual pipeline execution with CSV input/output."""
    
    def test_human_corpus_reads_input_csv_files(tmp_path):
        """Verify CSV reading and repository selection from input files."""
        # Create input CSVs in tmp_path
        # Run collector with repo_qc_dir=tmp_path
        # Assert output fixtures CSV has correct format
        
    def test_human_corpus_writes_output_fixtures_csv(tmp_path):
        """Verify fixture CSV export format and content."""
        # Run collection
        # Validate output CSV:
        #   - Column headers present
        #   - All rows have required fields
        #   - No truncation or data loss
        
    def test_agent_corpus_csv_export_consistency(tmp_path):
        """Verify agent CSV export matches schema."""
        # Similar to human but for agent fixtures
        
    def test_test_commit_csv_export_format(tmp_path):
        """Verify test-commit CSV format is correct."""
        # Row structure, encoding, quoting
```
**Estimated Coverage:** 4-6 tests, ~100 lines

#### 1.2 **End-to-End Collection with Test Data** (Use Case 2)
```python
# tests/collection/test_end_to_end_collection.py (NEW)

class TestEndToEndCollection:
    """Test complete collection pipeline with minimal test repositories."""
    
    def test_human_corpus_full_workflow_minimal_data(tmp_path):
        """End-to-end: select→clone→QC→scan→extract→persist."""
        # Create 2-3 small test repos in tmp_path
        # Run HumanCorpusCollector
        # Verify:
        #   - DB schema correct
        #   - Repositories inserted
        #   - Test commits found
        #   - Fixtures extracted
        #   - Output CSVs generated
        
    def test_agent_corpus_full_workflow_minimal_data(tmp_path):
        """End-to-end agent corpus with test data."""
        # Similar to human
        
    def test_concurrent_vs_sequential_same_results(tmp_path):
        """Verify workers=1 and workers=4 produce same results."""
        # Run with sequential, then concurrent
        # Compare stats and output
        
    def test_collection_with_missing_repos_handles_gracefully(tmp_path):
        """Verify collection skips missing repos without crashing."""
```
**Estimated Coverage:** 4-5 tests, ~150 lines

### Phase 2: Detector Unit Tests (Small-Scoped)

#### 2.1 **Agent Repository Detection**
```python
# tests/collection/test_agent_detector_comprehensive.py (NEW)

class TestAgentRepositoryDetection:
    """Comprehensive tests for agent config detection."""
    
    def test_scan_for_agents_detects_all_patterns(tmp_path):
        """Verify all PAPER_AGENT_CONFIG_PATTERNS are detected."""
        # Create files matching each pattern
        # Assert all patterns detected
        
    def test_scan_for_agents_with_nested_directories(tmp_path):
        """Verify nested config file detection."""
        
    def test_agent_file_checker_github_api_fallback(monkeypatch):
        """Verify GitHub API checker works correctly."""
        
    def test_agent_commit_verifier_extracts_coauthor(monkeypatch):
        """Verify co-authored-by trailer extraction."""
```
**Estimated Coverage:** 6-8 tests, ~120 lines

#### 2.2 **Fixture Dependency & Scope Calculation**
```python
# tests/collection/test_fixture_dependencies.py (NEW)

class TestFixtureDependencies:
    """Test fixture dependency graph and scope propagation."""
    
    def test_calculate_fixture_dependencies_simple(tmp_path):
        """Verify simple fixture call graph."""
        code = '''
        def fixture_a(): return 1
        def fixture_b(fixture_a): return fixture_a + 1
        def test_uses_b(fixture_b): assert fixture_b == 2
        '''
        # Extract and verify dependency: b → a
        
    def test_propagate_fixture_scopes_transitive(tmp_path):
        """Verify scope propagation through dependency chain."""
        # If a is function-scoped and b depends on a,
        # b should be max(function, a's scope) = function
        
    def test_calculate_teardown_pairs_matching(tmp_path):
        """Verify fixture teardown pair matching."""
        # Fixture with cleanup() or teardown() methods
        # Should be marked as having teardown pair
```
**Estimated Coverage:** 4-6 tests, ~100 lines

#### 2.3 **Test Commit Filtering Edge Cases**
```python
# tests/collection/test_test_commit_filter_comprehensive.py (EXPAND EXISTING)

class TestTestCommitFilteringComprehensive:
    """Comprehensive edge cases for test commit detection."""
    
    def test_detect_test_files_all_patterns_per_language():
        """Verify all test file patterns detected per language."""
        # test_*.py, *_test.py, tests/ dir, spec/ dir, __tests__/, etc.
        
    def test_detect_test_files_false_positives():
        """Ensure no false positives (test-related but not tests)."""
        # test_data.json (data file)
        # tests.config (config file)
        # testing_utils.py (utility file)
```
**Estimated Coverage:** 3-4 tests, ~60 lines

### Phase 3: Corpus Utils Module Tests (NEW!)

#### 3.1 **Corpus Utilities**
```python
# tests/collection/test_corpus_utils.py (NEW)

class TestCorpusUtils:
    """Test shared corpus utility functions."""
    
    def test_compute_repo_metadata_returns_all_fields():
        """Verify compute_repo_metadata returns domain, star_tier, repo_age."""
        
    def test_construct_repo_dict_has_all_required_fields():
        """Verify constructed dict has all DB fields."""
        
    def test_persist_repository_and_fixtures_csv_export(tmp_path):
        """Verify CSV export format and content."""
        
    def test_persist_repository_and_fixtures_db_insertion(tmp_path):
        """Verify DB insertion with proper transaction handling."""
        
    def test_generate_corpus_summary_json_structure():
        """Verify summary JSON has expected structure."""
        
    def test_persist_with_handle_mocks_true():
        """Verify mock insertion when handle_mocks=True."""
```
**Estimated Coverage:** 6-7 tests, ~120 lines

---

## Test Coverage Summary

### Current State
- **Extraction/Detector Logic:** 200+ tests ✅ GOOD
- **Agent Patterns:** 50+ tests ✅ GOOD
- **Mock Detection:** 100+ tests ✅ GOOD
- **Manual Pipeline with CSV:** ❌ MISSING
- **End-to-End Collection:** ❌ MISSING (only mocked)
- **Corpus Utils:** ❌ MISSING (just added module)
- **Fixture Dependencies/Scopes:** ⚠️ PARTIAL
- **Test Commit Filtering:** ~30 tests ⚠️ PARTIAL

### Gap Summary
| Category | Status | Gap | Priority |
|----------|--------|-----|----------|
| **CSV Pipeline I/O** | ❌ Missing | Medium (Use Case 1) | 🔴 HIGH |
| **End-to-End Collection** | ❌ Missing | Large (Use Case 2) | 🔴 HIGH |
| **Corpus Utils** | ❌ Missing | Medium (new module) | 🔴 HIGH |
| **Fixture Dependencies** | ⚠️ Partial | Small | 🟡 MEDIUM |
| **Agent Detection** | ⚠️ Partial (4 tests) | Small | 🟡 MEDIUM |
| **Test Commit Filtering** | ⚠️ Partial | Small | 🟡 MEDIUM |
| **Framework Detection** | ✅ Good | Very small | 🟢 LOW |
| **Extraction Logic** | ✅ Good | None | 🟢 LOW |

---

## Proposed Test Files to Create

1. **tests/collection/test_csv_pipeline_integration.py** - 4-6 tests, ~100 lines
2. **tests/collection/test_end_to_end_collection.py** - 4-5 tests, ~150 lines  
3. **tests/collection/test_agent_detector_comprehensive.py** - 6-8 tests, ~120 lines
4. **tests/collection/test_fixture_dependencies.py** - 4-6 tests, ~100 lines
5. **tests/collection/test_test_commit_filter_comprehensive.py** (EXPAND) - 3-4 tests, ~60 lines
6. **tests/collection/test_corpus_utils.py** (NEW) - 6-7 tests, ~120 lines

### Total New Tests: 27-36 tests, ~650 lines

---

## Testing Infrastructure Needs

### Fixtures Needed
- **Temp repositories:** Small git repos with test files
- **CSV files:** Sample repo-QC, agent-commit CSVs
- **Database:** Pre-populated between-group.db for integration tests
- **Mock GitHub API:** For agent detection tests

### Existing Helpers
- `tests/collection/conftest.py` - Should be enhanced
- Mock utilities in `pytest` built-in

---

## Success Criteria

✅ **Use Case 1 (Manual CSV Steps):** Verified with 4-6 tests  
✅ **Use Case 2 (End-to-End):** Verified with 4-5 tests  
✅ **Detector Coverage:** Small-scoped tests for agent/fixture detection  
✅ **All New Tests Passing:** 100% pass rate  
✅ **No Regressions:** Existing tests still passing  

---

## Implementation Order

1. **Phase 1a:** Corpus utils tests (foundational - uses new module)
2. **Phase 1b:** CSV pipeline tests (validates use case 1)
3. **Phase 1c:** End-to-end tests (validates use case 2)
4. **Phase 2a:** Agent detection comprehensive tests
5. **Phase 2b:** Fixture dependencies tests
6. **Phase 2c:** Test commit filtering comprehensive tests
