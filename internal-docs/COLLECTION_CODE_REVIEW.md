# Collection Module Code Review

**Date:** May 24, 2026  
**Focus:** Agent & Human Corpus Collectors, Test-Commit Infrastructure  
**Goal:** Identify duplication, complexity, and best-practice violations

---

## Executive Summary

The collection module has undergone significant methodology changes (agent vs. human corpus separation, test-commit collectors). While the implementation is functional, there are significant opportunities for:
- **Duplication reduction** (~150+ lines shared between `agent_corpus.py` and `human_corpus.py`)
- **Common infrastructure extraction** (repository processing pipeline)
- **Code clarity and maintainability** (splitting large classes)
- **Error handling consistency** (exception patterns vary)

---

## Key Findings

### 1. **Significant Duplication: `AgentCorpusCollector` vs `HumanCorpusCollector`**

**Files:** `collection/agent_corpus.py` (650 lines), `collection/human_corpus.py` (785 lines)

**Duplicated Patterns:**
- `_validate_quality_filters()` method (nearly identical in both)
- Repository metadata upsert + domain/star_tier/age computation (identical logic)
- Test-commit row construction and insertion (identical)
- Fixture CSV export logic (identical field list, same append pattern)
- Per-language CSV path construction
- Stats aggregation and summary generation

**Example - Identical Code:**
```python
# agent_corpus.py lines ~380-400
domain = classify_domain(repo.get("topics"), repo.get("description"))
star_tier = compute_star_tier(repo.get("stars"))
repo_age = compute_repo_age_at_date(repo.get("created_at"), AGENT_CORPUS_START_DATE)

# human_corpus.py lines ~447-450 (nearly identical except date constant)
domain = classify_domain(repo.get("topics"), repo.get("description"))
star_tier = compute_star_tier(repo.get("stars"))
repo_age = compute_repo_age_at_date(repo.get("created_at"), HUMAN_CORPUS_CUTOFF_DATE)
```

**Impact:** When bug fixes or feature updates are needed, changes must be made in two places.

---

### 2. **Shared Repository Processing Pipeline**

Both collectors follow an identical workflow:
1. **Clone** (if missing) → check for shallow clones
2. **QC Validate** (commit count, temporal window)
3. **Scan commits** (detect agent/human markers)
4. **Extract fixtures** (from qualifying commits)
5. **Insert to DB** (repository + test_files + fixtures)
6. **Export CSVs** (per-language fixture files)
7. **Aggregate stats**

This workflow is a candidate for a **base class or shared mixin**.

---

### 3. **Concurrency Implementation Inconsistency**

**agent_corpus.py:**
- Uses `ThreadPoolExecutor` for repository processing (with as_completed)
- Serializes DB writes in main thread
- Has explicit error handling in futures loop

**human_corpus.py (after recent changes):**
- Also uses `ThreadPoolExecutor` for repository processing
- Serializes DB writes in main thread (same pattern)
- Identical error handling

**Issue:** Both implementations are nearly identical but live in separate files. This suggests both should inherit from a common base or use a shared utility function.

---

### 4. **Test-Commit Collection Utilities Fragmentation**

**Files Involved:**
- `collection/test_commit_filter.py` (564 lines) - 3 large functions with nearly identical patterns
- `collection/human_corpus.py` - calls scanner directly
- `collection/agent_corpus.py` - calls scanner directly

**Issues:**
- `collect_agent_test_commits()`, `collect_human_test_commits()`, `collect_agent_test_commits_from_repos()` share 80% of code
- Repository scanning logic (`Tier1RepositoryScanner`) only called from collectors, not reused elsewhere
- Test-commit row construction is duplicated (agent collector constructs rows, human collector also constructs rows)

**Example Duplication (test_commit_filter.py):**
```python
def collect_agent_test_commits(commit_qc_dir: Path, output_dir: Path, workers: int = 12):
    # Reads CSVs, processes commits, writes output
    # ~120 lines of setup/loop/export logic
    
def collect_human_test_commits(repo_qc_dir: Path, output_dir: Path, workers: int = 12):
    # Nearly identical structure, different data source
    # ~100 lines of setup/loop/export logic
```

---

### 5. **Large Methods Violating Single Responsibility**

**`HumanCorpusCollector.run()` (240+ lines):**
- Selects repositories
- Processes (clones + QC + scans + extracts)
- Constructs database rows
- Performs DB writes
- Writes CSVs
- Generates stats/summaries

Should be broken into smaller, testable units.

---

### 6. **Configuration Management Inconsistencies**

**Issues:**
- Date constants scattered across imports: `AGENT_CORPUS_START_DATE`, `HUMAN_CORPUS_CUTOFF_DATE`
- Worker count defaults defined separately in `config.py` (`EXTRACT_WORKERS = 8`) and CLI defaults
- Min commit threshold (`MIN_COMMITS = 1`) not consistently applied
- Hard-coded paths in CSV export (e.g., `fixtures-from-humans` → changed to repo_qc_dir)

**Better approach:** Central configuration registry for corpus collection parameters.

---

### 7. **Error Handling Patterns**

**Issues:**
- Inconsistent exception handling in cloner vs. extractor vs. DB layer
- Silent failures in fixture extraction (oversized files, recursion limit)
- Limited retry logic for transient failures (network timeouts, lock contention)
- Database transaction errors not always logged distinctly

**Example:**
```python
# agent_corpus.py - tries clone, logs if failed
if not clone_repo_for_commit_scan(repo.get("clone_url", ""), repo_path):
    logger.debug(f"Skip {repo_name}: clone_failed")
    # Falls through to next repo

# human_corpus.py - same pattern but in a helper method
# Both could use a consistent error context manager
```

---

### 8. **Testing Gaps**

**Current Test Coverage:**
- `tests/between_group/test_human_corpus.py` - repository selection and stats
- No integration tests for concurrent processing
- No tests for fixture CSV export format
- No tests for DB transaction isolation under concurrency
- Limited error case coverage

---

### 9. **Type Hints and Clarity**

**Issues:**
- Some functions use `Optional[int]` but don't document what `None` means
- Return types for large functions are sometimes overly complex
- Dict parameters (`repo: dict`) should use TypedDict for clarity

**Example - Better Typing:**
```python
# Current
def _process_human_repository(self, repo: dict) -> dict:

# Better
from typing import TypedDict

class RepositoryMetadata(TypedDict):
    full_name: str
    language: str
    clone_url: str
    ...

def _process_human_repository(self, repo: RepositoryMetadata) -> RepositoryProcessingResult:
```

---

### 10. **Documentation Gaps**

- No module-level docstrings explaining methodology differences
- `_process_human_repository()` helper in human_corpus doesn't explain return dict structure
- CSV column meanings not documented in fixture export
- Database schema not documented in db.py

---

## Recommendations (Priority Order)

### **High Priority**

1. **Extract Base Corpus Collector Class**
   - Create `BaseCorpusCollector` with shared methods:
     - `_compute_repo_metadata()`
     - `_process_repository()` (template method pattern)
     - `_export_fixtures_to_csv()`
     - `_generate_summary()`
   - Have `AgentCorpusCollector` and `HumanCorpusCollector` inherit
   - **Estimated savings:** ~200 lines of duplication

2. **Refactor Test-Commit Collection**
   - Create base function `_collect_test_commits_generic()` parameterized by:
     - CSV file pattern
     - Row construction logic
     - Filtering predicate
   - Use it as the implementation for all three public functions
   - **Estimated savings:** ~150 lines

3. **Split Large `run()` Methods**
   - Break `run()` into smaller testable stages:
     - `_select_repositories()`
     - `_process_repositories_concurrently()`
     - `_persist_results()`
     - `_generate_reports()`
   - **Benefit:** Easier testing, clearer logic flow

### **Medium Priority**

4. **Standardize Error Handling**
   - Create `@contextmanager` for database transactions with retry logic
   - Consistent logging levels (warn for skips, error for failures)
   - Document expected exceptions per function

5. **Add TypedDict Definitions**
   - `RepositoryMetadata` - all repo dict fields
   - `FixtureData` - all fixture dict fields
   - `ProcessingResult` - return dict from processing helpers

6. **Centralize Configuration**
   - Create `CorpusConfig` dataclass with all parameters
   - Pass as single parameter instead of multiple imports

7. **Improve Test Coverage**
   - Integration tests for concurrent processing
   - CSV export format validation
   - Error path testing

### **Low Priority**

8. **Documentation**
   - Add module docstrings explaining methodology
   - Document CSV export schema
   - Add examples in README

9. **Performance**
   - Profile fixture extraction on large files
   - Consider caching domain/star_tier classification results

10. **Code Style**
    - Run `black` on all collection modules
    - Add `pylint`/`ruff` configuration

---

## Specific Code Issues to Address

### Issue 1: `_stable_repo_id()` Defined in Both Files
**Files:** `agent_corpus.py:50`, `human_corpus.py:50`
**Fix:** Move to `db.py` or create a `collection/utils.py`

### Issue 2: Repository Metadata Computation Duplicated
**Lines affected:** ~10 lines in each file
**Fix:** Create `compute_repo_metadata()` utility
```python
def compute_repo_metadata(repo: dict, temporal_window: str) -> dict:
    return {
        'domain': classify_domain(repo.get('topics'), repo.get('description')),
        'star_tier': compute_star_tier(repo.get('stars')),
        'repo_age_years': compute_repo_age_at_date(repo.get('created_at'), temporal_window),
    }
```

### Issue 3: CSV Writer Setup Duplicated
**Lines affected:** ~15 lines per file
**Fix:** Create `write_fixture_csv_row()` function

### Issue 4: Test-Commit Row Construction Duplicated
**Affected functions:** Multiple in both collectors
**Fix:** Create `ConstructTestCommitRow` factory function parameterized by fields

---

## Refactoring Roadmap

1. **Phase 1 (2-3 hours):** Extract base class, deduplicate stats
2. **Phase 2 (2-3 hours):** Consolidate test-commit utilities  
3. **Phase 3 (1-2 hours):** Add TypedDict definitions and improve typing
4. **Phase 4 (1 hour):** Improve tests and documentation
5. **Validation:** Run full test suite, verify CSV outputs, check line count reduction

**Expected outcome:** ~350-400 lines removed, 20%+ reduction in duplication, improved maintainability.

---

## Conclusion

The recent changes to separate agent and human corpus collection were necessary for methodological clarity, but implementation resulted in significant duplication. The recommendations above, particularly items 1-3, will significantly improve code maintainability with moderate effort.

The codebase is **functionally correct** but **not optimally structured** for long-term maintenance.
