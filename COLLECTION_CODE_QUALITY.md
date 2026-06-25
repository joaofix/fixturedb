# Collection Module Code Quality Audit

**Date:** 2026-06-24  
**Scope:** `collection/` module (45+ Python files, ~8,000+ lines)  
**Method:** Static analysis + manual review  

---

## Executive Summary

The collection pipeline is functionally sound with clear phase separation, but has significant maintainability debt from code duplication, missing imports that will crash at runtime, SQL injection anti-patterns, and oversized files. The most critical issues are concentrated in a handful of large files.

**Risk Level:** HIGH — some bugs will cause runtime failures; others silently corrupt data quality.

---

## Critical Issues (Fix Immediately)

### 1. Missing `fnmatch` Import
- **File:** `agent_detector.py:344`
- **Severity:** HIGH (crashes at runtime)
- **Issue:** `fnmatch.fnmatchcase(...)` is called but `fnmatch` is never imported
- **Impact:** `_find_agent_files` will raise `NameError` on any file match attempt
- **Fix:** Add `import fnmatch` at top of file

### 2. SQL Query References Non-Existent Column
- **File:** `phase_4_analyze_distribution.py:70`
- **Severity:** HIGH (crashes at runtime)
- **Issue:** Queries `SELECT category, COUNT(*) FROM fixtures WHERE category IS NOT NULL` but `fixtures` table has no `category` column
- **Impact:** `sqlite3.OperationalError: no such column: category`
- **Fix:** Remove `category` column reference or add column to schema

### 3. Duplicate Constant Definition
- **File:** `config.py:473`
- **Severity:** HIGH (dead code / confusion)
- **Issue:** `MIN_FIXTURES_FOUND = 1` is defined twice; second definition is unreachable
- **Fix:** Remove duplicate at line 473

### 4. SQL Injection via f-String Column Names
- **Files:** `between_group_comparison.py:83-91`, `dataset_exporter.py:152-172`, `phase_6_7_export_and_document.py:84`
- **Severity:** HIGH (security anti-pattern)
- **Issue:** SQL queries constructed with `f"SELECT r.{variable}..."` where `variable` comes from function parameters
- **Current Risk:** LOW (inputs are hardcoded strings in practice)
- **Future Risk:** HIGH (any refactor passing user input would be vulnerable)
- **Fix:** Use allowlist validation or SQLite identifier quoting

---

## High-Impact Maintainability Issues

### 5. Massive Code Duplication: Repo-Row Construction
- **Files:** `agent_corpus.py:225-242`, `human_corpus.py:466-512`, `agent_fixture_counter.py`, `agent_repository_counter.py`, `paired_collection.py`
- **Severity:** HIGH
- **Issue:** The same dict structure (`github_id`, `full_name`, `language`, `stars`, `forks`, `clone_url`, etc.) is built independently in 5+ places
- **Impact:** Schema changes require updating all locations; high chance of inconsistency
- **Fix:** Extract to `collection/utils.py::build_repo_row()`

### 6. Duplicated `AGENT_TRAILER_RE` Regex
- **Files:** `agent_corpus.py:61`, `agent_commit_detector.py:39`
- **Severity:** MEDIUM
- **Issue:** Regex pattern is copy-pasted verbatim
- **Fix:** Import from single source (`agent_patterns.py` or new `utils.py`)

### 7. Duplicated `_stable_repo_id` Function
- **Files:** `agent_corpus.py:187`, `human_corpus.py:84`
- **Severity:** MEDIUM
- **Issue:** Identical MD5-based repo ID function defined twice
- **Fix:** Consolidate into `utils.py`

### 8. Worker/Single-Path Logic Duplication
- **File:** `test_commit_filter.py:285-358, 509-581, 837-876`
- **Severity:** HIGH
- **Issue:** Three copies of nearly identical logic for collecting results, filtering seen SHAs, persisting progress, and logging
- **Impact:** Bug fixes must be applied 3 times; already showing divergence
- **Fix:** Extract common worker orchestration into shared helper

### 9. Fixture Column Lists Duplicated in db.py
- **File:** `db.py:570-626, 634-683, 691-758`
- **Severity:** MEDIUM
- **Issue:** `insert_fixture`, `insert_human_within_fixture`, `insert_human_inter_fixture` all rebuild nearly identical column lists
- **Fix:** Define once as module constant, reuse across functions

---

## Code Smells

### 10. Bare `except Exception:` Blocks
- **Count:** 15+ instances across multiple files
- **Severity:** HIGH
- **Examples:**
  - `agent_corpus.py:180` — `except (subprocess.TimeoutExpired, Exception)`
  - `human_corpus.py:101-119` — bare except on checkpoint I/O
  - `test_commit_filter.py:921` — bare except swallows all errors
- **Fix:** Use specific exceptions; at minimum log `logger.debug(f"...: {e}")`

### 11. Oversized Files
| File | Lines | Issue |
|------|-------|-------|
| `detector.py` | 1750+ | Should be split into `tree_sitter_detector.py`, `ast_detector.py`, etc. |
| `fixture_extractor.py` | 1586 | Mixes `Pre2021FixtureExtractor`, `AgentFixtureExtractor`, diff parsing |
| `human_corpus.py` | 1411 | `_process_human_within_language` is 140 lines |
| `agent_corpus.py` | 1031 | `run()` is ~200 lines |
| `db.py` | 1318 | Could split into `db_connection.py`, `db_insert.py`, `db_query.py` |

### 12. Magic Numbers
- **File:** `agent_commit_detector.py:646-704`
- **Values:** `0.5`, `1.5`, `2.0`, `0.25` in `_generate_search_attempts`
- **Fix:** Define named constants at module level

### 13. Imports Inside Functions
- `github_api_search.py:267` — `import re` inside `get_repo_contributors_count`
- `complexity_provider.py:189` — `import re` inside `_count_object_instantiations`
- `paired_collection.py:133` — `import scipy.stats` inside `_compute_chi_square_balance`
- **Fix:** Move to module-level imports

### 14. Silent Cleanup Failures
- **Pattern:** `shutil.rmtree(path, ignore_errors=True)` in 5+ locations
- **Files:** `agent_corpus.py:555`, `human_corpus.py:1277`, `clone_manager.py:118`
- **Issue:** Filesystem errors during cleanup are silently ignored
- **Fix:** Use `try/except` with logging, or `ignore_errors=False` with explicit handling

### 15. Type Hint Inconsistencies
- **Fully typed:** `corpus_utils.py`, `agent_patterns.py`
- **Partially typed:** `agent_corpus.py`, `human_corpus.py`
- **Untyped:** `github_fetch.py`, `temp_clone.py`, `github_archive.py`
- **Mixed conventions:** `Path | None` vs `Optional[Path]` vs `Path = None`
- **Fix:** Adopt `from __future__ import annotations` + consistent `X | None` syntax

### 16. Module-Level Side Effects
- **File:** `config.py:55-57`
- **Issue:** `mkdir()` calls run on every import
- **Fix:** Move to explicit initialization function

### 17. Unused Imports
- `agent_commit_detector.py:10` — `import concurrent.futures` imported but never used directly
- `agent_repository_counter.py` — `sys.path` manipulation pattern repeated in all 3 RQC files

### 18. Duplicate Imports
- `agent_repository_counter.py:42` — `import json` imported twice
- `human_corpus.py:1002-1003` — `from collections import defaultdict` imported again

---

## Cross-Cutting Patterns to Consolidate

| Pattern | Locations | Suggested Location |
|---------|-----------|-------------------|
| `AGENT_TRAILER_RE` regex | `agent_corpus.py`, `agent_commit_detector.py` | `agent_patterns.py` |
| `_stable_repo_id()` | `agent_corpus.py`, `human_corpus.py` | `utils.py` |
| `_normalize_language_filters()` | `agent_corpus.py`, `human_corpus.py`, `agent_repository_counter.py` | `utils.py` |
| Repo-row dict construction | 5 files | `utils.py::build_repo_row()` |
| Fixture column list | `db.py` (3 copies), `corpus_utils.py` | `utils.py::FIXTURE_COLUMNS` |
| `_date_only()` helper | `agent_fixture_counter.py`, `agent_repository_counter.py` | `utils.py` |
| Worker orchestration | `test_commit_filter.py` (3 copies) | `utils.py::run_worker_pool()` |

---

## Priority Fix Order

| Priority | Issue | Estimated Effort |
|----------|-------|-----------------|
| 1 | Missing `fnmatch` import | 5 min |
| 2 | `category` column SQL bug | 10 min |
| 3 | Duplicate `MIN_FIXTURES_FOUND` | 2 min |
| 4 | SQL f-string column names → allowlist | 30 min |
| 5 | Bare `except Exception:` → specific + logging | 1 hour |
| 6 | Consolidate duplicated utilities into `utils.py` | 2 hours |
| 7 | Extract repo-row construction helper | 1 hour |
| 8 | Refactor `test_commit_filter.py` worker duplication | 2 hours |
| 9 | Extract fixture column constant from `db.py` | 15 min |
| 10 | Move imports to module level | 30 min |
| 11 | Fix silent `rmtree` failures | 30 min |
| 12 | Split oversized files (`fixture_extractor.py`, `human_corpus.py`) | 4+ hours |

---

## Recommendations

1. **Add linting to CI:** Configure `ruff` (fast, catches missing imports, bare excepts) and `mypy --strict` (catches type issues)
2. **Add pre-commit hooks:** `pre-commit` with `ruff`, `black`, `isort`
3. **Create `collection/utils.py`:** Central home for all shared utilities
4. **Set file size limit:** No file > 500 lines without explicit review exception
5. **Add integration tests for critical paths:** The SQL bugs suggest insufficient test coverage of the actual DB layer

---

*Generated by Kilo code review*
