# Methodology Corrections - Implementation Summary

**Date:** May 24, 2026  
**Status:** ✅ COMPLETE - All changes tested, 461/461 tests passing

---

## Overview of Corrections

Three critical methodology updates were implemented to align code and documentation with the correct study design:

1. **Removed Tier 2 references** - Only Tier 1 agent detection from co-authored-by trailers
2. **Unified temporal window** - Both human and agent fixtures collected post-2025 (AGENT_CORPUS_START_DATE)
3. **Removed repository capping** - Process all agent-enabled repos without per-language limits

---

## Code Changes

### 1. collection/agent_corpus.py

**Changed:** Repository selection parameters and docstrings

- `repos_per_language` parameter: changed default from `int = 50` to `Optional[int] = None`
- Function signature: `_load_qc_repo_rows()` now accepts `Optional[int]` instead of `int`
- CLI argument: `--repos-per-language` default changed from `20` to `None`
- Docstring updates to reflect "include all rows" when None

**Impact:** Agent corpus now processes all repositories without per-language caps

### 2. collection/human_corpus.py

**Changed:** Temporal window and repository selection logic

- Import: Changed from `HUMAN_CORPUS_CUTOFF_DATE` to `AGENT_CORPUS_START_DATE`
- Repository selection query: Changed `WHERE created_at < ?` to `WHERE created_at >= ?`
- All date parameters: Changed from `HUMAN_CORPUS_CUTOFF_DATE` to `AGENT_CORPUS_START_DATE` (5 locations)
- Docstrings: Updated to reflect same temporal window as agent collection
- Summary metadata: Updated to reference "dataset_temporal_window" instead of "agent_dataset_start_date"

**Locations updated:**
- `select_human_corpus_repositories()` - repository query filter
- `_process_human_repository()` - fixture extractor init, scanner init
- Database query construction - temporal filter
- Summary generation metadata

**Impact:** Human corpus now collected from same post-2025 temporal window as agent corpus

### 3. collection/two_tier_agent_collection.py

**Changed:** Module docstring to remove Tier 2 reference

- Old: "Two-tier methodology... Tier 1: ... Tier 2: ... (between-repo comparison, if Tier 1 insufficient)"
- New: "Utilities for agent commit detection and classification... for paired-sample analysis"

**Impact:** Clarifies that module is for agent identification only, not Tier 2 discovery

### 4. tests/between_group/test_human_corpus.py

**Changed:** Test data and assertions to match new temporal window

- Test docstring: Updated to reflect post-2025 temporal window
- Import: Changed from `HUMAN_CORPUS_CUTOFF_DATE` to `AGENT_CORPUS_START_DATE`
- Test fixture data: Replaced pre-2021 repos with post-2025 agent-era repos
- Test assertions: Changed from `< HUMAN_CORPUS_CUTOFF_DATE` to `>= AGENT_CORPUS_START_DATE`
- Test names: Updated to reflect new temporal semantics

**Specific test changes:**
- `test_select_human_corpus_repositories_filters_by_date` - now asserts `>=` instead of `<`
- `test_human_corpus_cutoff_is_2021_01_01` → `test_human_corpus_temporal_window` - now checks 2025-01-01
- `test_repositories_at_boundary_not_included` → `test_repositories_at_boundary_included` - semantics reversed

**Result:** All 44 existing human/agent corpus tests still passing ✅

---

## Documentation Changes

### 1. docs/getting-started/intro.md

**Changed:** Study design overview from temporal separation to within-repository comparison

- **Old design:** Pre-2021 human repos vs 2025+ agent repos (unpaired, different populations)
- **New design:** Agent-enabled repos with both human and agent fixtures in same temporal window (within-repo pairs)
- Updated rationale to emphasize natural pairs within codebases
- Updated output description to reflect single temporal window and paired structure

**Key sections updated:**
- Study design bullets
- Why within-repository design section
- What the pipeline produces section

### 2. docs/usage/reproducing.md

**Changed:** Pipeline instructions from two-stage to collection-focused

- Removed references to corpus.db and pre-2021 extraction
- Updated to use `github-search/` as data source
- Changed command format: `human` → `human_corpus`, `agent` → `agent_corpus`
- Added clarity about "no capping" parameter behavior
- Simplified from 3-stage (human, agent, stats) to 2-stage collection (parallel possible)

**Key sections updated:**
- Overview explaining within-repo pairs
- Stage 1: Repository selection (from github-search/)
- Stage 2: Collection (both human and agent)
- Parameters table showing all options
- Removed Stage 3 (between-group stats) as separate command

### 3. docs/architecture/agent-detection.md

**Changed:** Simplified to focus on Tier 1 only

- Removed "Tier 2/3 (Optional)" section
- Removed sensitivity analysis language
- Streamlined overview to single detection method
- Maintained algorithm details for co-authored-by trailer detection

**Key changes:**
- New "Overview" section states Tier 1 exclusively
- "Tier 1: Co-authored-by Trailer Detection (Primary Method)" → "Co-authored-by Trailer Detection"
- Removed supplementary detection methods

### 4. docs/INDEX.md

**Changed:** Study design description in index

- Updated "Between-Group Study Design" → "Study Design" 
- Changed from temporal separation to within-repo basis
- Updated control variables to reflect single temporal window
- Changed statistical framing from unpaired to paired

**Key sections:**
- Quick links table (unchanged)
- Study Design section (revised design bullets)

### 5. docs/usage/usage.md

**Changed:** Analysis guide to reflect new design

- Updated overview from "two distinct populations" to "fixtures within repositories"
- Changed design description from temporal separation to within-repo comparison
- Clarified agent identification uses Tier 1 only
- Updated control variable computation to single snapshot

---

## Testing & Validation

### Test Results
- ✅ **461/461 tests passing** (all existing + new tests)
- ✅ **Zero regressions** - all test suites passing
- ✅ **New temporal window tests** - updated and passing

### Test Coverage by Module
- `tests/between_group/test_human_corpus.py` - 18 tests ✅
- `tests/between_group/test_agent_corpus.py` - 26 tests ✅
- `tests/collection/test_corpus_utils.py` - 20 tests ✅
- `tests/collection/test_csv_pipeline_integration.py` - 9 tests ✅
- `tests/collection/test_end_to_end_collection.py` - 15 tests ✅
- All other test suites - 373 tests ✅

---

## Summary of Changes

| Component | Change | Impact |
|-----------|--------|--------|
| **Code** | Removed Tier 2, unified temporal window, removed capping | Simpler, more consistent methodology |
| **Tests** | Updated for post-2025 temporal window | Tests align with implementation |
| **Docs** | Clarified within-repo design, single temporal window | Clear, accurate methodology explanation |

---

## Key Design Principles Now Documented

1. **Single temporal window** - Both agent and human fixtures from post-2025 onwards
2. **Repository basis** - Agent-enabled repos as fundamental unit
3. **Tier 1 only** - Conservative co-authored-by trailer detection
4. **No capping** - Process all matching repositories
5. **Within-repo pairs** - Natural pairing through repository context
6. **Same controls** - Control variables computed at single temporal snapshot

---

## Backwards Compatibility

All changes are **backwards compatible** with existing data:
- Database schema unchanged
- API signatures compatible (defaults changed but parameters remain optional)
- Existing test data adapted to new semantics
- No breaking changes to output formats

---

## Next Steps

The codebase is now aligned with the correct methodology:
1. ✅ Code implements new design correctly
2. ✅ Tests verify implementation
3. ✅ Documentation explains design clearly
4. Ready for production collection run on 2096+ agent-enabled repositories

**Production command:**
```bash
./env/bin/python -m collection.human_corpus --repo-qc-dir github-search --workers 8
./env/bin/python -m collection.agent_corpus --repo-qc-dir github-search --workers 8
```
