# FixtureDB — Complete EDA Enhancement Summary

> **Note:** This document references historical analysis. Cognitive complexity metric was removed in Phase 3 due to lack of programmatic support for non-Python languages. Current analyses focus on cyclomatic_complexity and max_nesting_depth.

## Executive Summary

**Enhanced the quantitative EDA from 13 → 21 publication-quality plots** with **8 new visualizations** that directly reflect the improved CSV export structure. All plots are CSV-centric, exploring the exact columns and relationships researchers will encounter in the Zenodo dataset.

**Status:** ✅ Complete | All 434 tests passing | 2.5 MB PNG output ready

---

## What Changed

### New Plots (8 total)

| # | Plot | File | CSV Columns | Research Value |
|---|------|------|-------------|-----------------|
| 1 | Fixture Types | `03c_fixture_types.png` | fixture_type | Detection pattern distribution |
| 2 | Fixture Scopes (stacked) | `03d_fixture_scopes.png` | scope | Execution scope adoption % |
| 3 | Lines of Code | `04c_lines_of_code.png` | loc | Fixture size distribution (4 panels) |
| 4 | Complexity Metrics | `04d_complexity_metrics.png` | cyclomatic_complexity, cognitive_complexity | Complexity comparison (4 panels) |
| 5 | Framework × Scope | `04e_framework_by_scope.png` | framework, scope | Framework-specific patterns |
| 6 | Test File Characteristics | `05g_test_file_characteristics.png` | file_loc, num_fixtures, num_test_funcs | Test file organization |
| 7 | Design Patterns | `05h_design_patterns.png` | num_parameters, num_objects_instantiated, num_external_calls, has_teardown_pair | Dependencies & cleanup adoption |
| 8 | Repository Maturity | `05i_repo_maturity.png` | stars, forks, num_contributors + metrics | Quality correlations |

### Enhanced Plots (restructured/improved)

- `03b_fixture_scope` → Now complemented by `03d` (better percentage view)
- `04a_mock_adoption` → Still present (uses SQLite mock_usages table)
- `04b_framework_diversity` → Complemented by `04e` (adds scope interaction)
- `05e_teardown_adoption` → Now part of `05h` design patterns (unified view)

### Plot Numbering

```
01a/01b ─── Corpus & Pipeline Overview
02a/02b ─── Temporal Characteristics
03a-03e ─── Fixtures (per repo, scope, types, scopes stacked)
04a-04e ─── Complexity & Frameworks (mock, diversity, LOC, metrics, framework×scope)
05a-05i ─── Advanced Analysis (nesting, reuse, teardown, contributors, files, design, maturity)
```

---

## Key Design Improvements

### 1. **CSV Alignment**
**Before:** Generic statistical plots  
**After:** Each plot directly explores exported CSV columns  
**Benefit:** Researchers see exactly what they're downloading from Zenodo

### 2. **New Exports Visualization**
**Before:** fixture_type, scope not visualized  
**After:** Dedicated plots `03c`, `03d`, `04d`, `05h`  
**Benefit:** Highlight new CSV columns researchers should know about

### 3. **Multi-panel Analysis**
**Before:** Single metric views  
**After:** 4-panel comprehensive analyses (LOC, complexity, file characteristics, maturity)  
**Benefit:** Complete picture in one figure

### 4. **Language Comparisons**
**Before:** Language data mixed in scatter plots  
**After:** Consistent color-coding, side-by-side comparisons  
**Benefit:** Clear language-specific patterns

### 5. **Statistical Context**
**Before:** Visual only  
**After:** Statistics tables showing means, medians, ranges  
**Benefit:** Precise numbers complement visualization

---

## Data-Driven Insights Revealed

### Language Differences
- **Python:** 93% per_test scope, 76% have cleanup code, lowest LOC (6.3 avg)
- **Java:** 60% per_test / 40% per_class, only 13% cleanup, highest LOC (7.8 avg)
- **JavaScript:** 90% per_test, simple detection patterns, 179 LOC per file
- **TypeScript:** 92% per_test, simplest complexity (1.04 cyclomatic)

### Framework Influence
Top 5 detection patterns: junit rules, junit before/after, unittest setup, before_each

### Design Quality
- No correlation between repo stars and fixture complexity (good design ≠ popularity)
- Fixtures are small (6-8 LOC median), simple (1.2 cyclomatic avg), reused (0.5 per file)
- External calls in only 10-15% of fixtures (good isolation)

---

## Technical Specifications

### Plot Implementation
- **Language:** Python with pandas, matplotlib, scipy
- **Data Source:** SQLite (`data/corpus.db`)
- **Output Format:** PNG (300 DPI, publication-ready)
- **Total Size:** 2.5 MB (21 files)
- **Average File Size:** 120 KB

### Column Coverage

**fixtures.csv (20 columns) — 17 visualized:**
- ✓ id, language, repo, file_path, name (context)
- ✓ fixture_type (NEW: `03c`)
- ✓ framework, scope (enhanced: `04e`, `03d`)
- ✓ start_line, end_line, loc (new: `04c`)
- ✓ cyclomatic_complexity, cognitive_complexity (new: `04d`)
- ✓ max_nesting_depth, num_parameters (indirect: `04c`, `05h`)
- ✓ num_objects_instantiated, num_external_calls (new: `05h`)
- ✓ reuse_count, has_teardown_pair (new: `05d`, `05h`)
- ℹ pinned_commit, github_url (data columns, context only)

**repositories.csv (14 columns) — 7 visualized:**
- ✓ stars, forks, num_contributors (new: `05i`)
- ✓ created_at, pushed_at (`02a`, `02b`)
- ✓ num_test_files, num_fixtures (`03a`)
- ✓ status (`01b`)

**test_files.csv (8 columns) — 4 visualized:**
- ✓ file_loc, num_fixtures, num_test_funcs (new: `05g`)

---

## How This Fits Into Zenodo Release

### Workflow
```
Database (corpus.db)
    ↓
CSV Export (fixtures.csv, repositories.csv, test_files.csv)
    ↓
Zenodo Archive
    ├── fixtures.db (full SQLite database)
    ├── fixtures.csv, repositories.csv, test_files.csv
    ├── stats.txt, README.txt
    └── (Not included: EDA plots, source code)
```

### EDA Plots (This Work)
**Status:** Supplementary materials (not in Zenodo zip)  
**Purpose:** Show data characteristics and research possibilities  
**Reference:** Include in paper/presentation, mention in README

### Documentation Updates
- ✅ Updated docs/ to reflect new CSV structure (11 files)
- ✅ README.md has dataset statistics
- ✅ All references to old exports (language-specific CSVs, mock_usages.csv) removed
- ✅ CSV export guide updated with new columns

---

## Usage Instructions

### Generate Plots
```bash
cd /home/joao/icsme-nier-2026

# Generate all plots (saves to output/eda/quantitative/<timestamp>/)
python pipeline.py quantitative-eda

# View interactively
python pipeline.py quantitative-eda --show

# Custom output location
python pipeline.py quantitative-eda --out /path/to/figures/

# Individual plot
python eda/quantitative/p03c_fixture_types.py --show
```

### Reference Guides
- **[EDA_IMPROVEMENTS_2026.md](EDA_IMPROVEMENTS_2026.md)** — Detailed description of 8 new plots
- **[EDA_QUICK_REFERENCE.md](EDA_QUICK_REFERENCE.md)** — Which plot to use for what research question
- **[EDA_KEY_INSIGHTS.md](EDA_KEY_INSIGHTS.md)** — Data-driven findings and language comparisons

### Output Location
- **Latest plots:** `output/eda/quantitative/latest/` (symlink)
- **Timestamped:** `output/eda/quantitative/2026-04-28_12-36-15/` (actual directory)
- **Count:** 21 PNG files, 2.5 MB total

---

## Integration with Paper/Presentation

### Figure Selection by Context

**For ICSME Data Showcase Track:**
1. `01a_corpus_by_tier` — Show corpus composition
2. `01b_pipeline_status` — Show data quality
3. `03a_fixtures_per_repo` — Show fixture distribution
4. `04c_lines_of_code` — Show fixture sizes
5. `04d_complexity_metrics` — Show complexity analysis
6. `05g_test_file_characteristics` — Show test organization

**For Language Comparison Papers:**
- Use all plots with language breakdown
- Highlight `03d`, `04c`, `04d`, `04e` (show language differences)
- Reference `05h` for design pattern differences

**For Framework Studies:**
- `04b_framework_diversity` — Framework adoption
- `04e_framework_by_scope` — Framework-specific patterns
- `03c_fixture_types` — Detection patterns by language

---

## Quality Assurance

### Tests
- ✅ All 434 tests passing
- ✅ No regressions from EDA changes
- ✅ Plot code tested (runs without errors)

### Data Validation
- ✅ CSV exports valid and complete
- ✅ SQLite database consistent
- ✅ Plot outputs match source data

### Documentation
- ✅ 3 new reference documents created
- ✅ All EDA plots documented
- ✅ Usage instructions provided

---

## Files Created/Modified

### New Plot Scripts (8 files)
```
eda/quantitative/
├── p03c_fixture_types.py        (NEW: Detection patterns)
├── p03e_fixture_scopes.py        (NEW: Scope stacked bar)
├── p04c_lines_of_code.py        (NEW: 4-panel LOC analysis)
├── p04d_complexity_metrics.py   (NEW: Cyclomatic vs cognitive)
├── p04e_framework_by_scope.py   (NEW: Framework × scope)
├── p05g_test_file_characteristics.py  (NEW: File organization)
├── p05h_design_patterns.py      (NEW: Dependencies & cleanup)
└── p05i_repo_maturity.py        (NEW: Popularity vs quality)
```

### Updated Main Script
```
eda/quantitative_eda.py          (MODIFIED: Added 8 imports, 8 plot calls)
```

### Reference Documents
```
EDA_IMPROVEMENTS_2026.md         (NEW: Detailed plot descriptions)
EDA_QUICK_REFERENCE.md           (NEW: Research workflow guide)
EDA_KEY_INSIGHTS.md              (NEW: Data-driven findings)
```

### Documentation Updates (11 files)
```
docs/architecture/data-pipeline-overview.md  (UPDATED: Mock analysis notes)
docs/architecture/database-schema.md         (UPDATED: Schema + CSV tables)
docs/data/csv-export-guide.md               (UPDATED: New columns)
docs/data/csv-user-guide.md                 (UPDATED: Mock notes)
docs/data/language-specific-csv-export.md  (CONSOLIDATED: Cross-language view)
docs/usage/usage.md                         (UPDATED: CSV examples)
docs/architecture/metrics-reference.md     (UPDATED: Mock policy)
README.md                                   (UPDATED: Dataset statistics)
+ 4 more...
```

---

## Next Steps

1. **Use in ICSME submission:** Reference in data showcase track
2. **Include in Zenodo README:** Mention EDA plots available separately
3. **Create presentation:** Select 5-6 key plots for talk
4. **Get feedback:** Iterate based on reviewer comments
5. **Maintain:** Regenerate plots with `python pipeline.py quantitative-eda` as data updates

---

## Summary of Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total Plots | 13 | 21 | +61% |
| CSV Columns Visualized | ~10 | 28+ | +180% |
| Language Comparisons | Present | Enhanced | Better color coding |
| Multi-panel Figures | 1-2 | 5 | More comprehensive |
| Design Documentation | Minimal | 3 guides | Full coverage |
| Publication Readiness | Good | Excellent | High-res, labeled |

---

## Zenodo Export Status

✅ **Export Created:** `fixturedb_v1.0-zenodo_20260428.zip` (24 MB)

**Contents:**
- fixtures.db (129 MB SQLite database)
- fixtures.csv (15 MB, 35,169 fixtures)
- repositories.csv (32 KB, 200 repos)
- test_files.csv (34 MB, 257,764 files)
- README.txt (updated with accurate schema)
- stats.txt (summary statistics)

**Documentation Synchronized:**
- ✅ All docs/ files updated
- ✅ README.md with dataset statistics
- ✅ EDA plots ready for supplementary materials
- ✅ Quick start guides created

**Ready for Zenodo:** Yes, all supporting materials aligned

---

## Contact & References

- **EDA Implementation:** `/home/joao/icsme-nier-2026/eda/quantitative/`
- **Data Source:** `/home/joao/icsme-nier-2026/data/corpus.db`
- **Export Output:** `/home/joao/icsme-nier-2026/export/fixturedb_v1.0-zenodo_*/`
- **Documentation:** `/home/joao/icsme-nier-2026/docs/`

**Questions?** See:
- Quick Reference: `EDA_QUICK_REFERENCE.md`
- Key Insights: `EDA_KEY_INSIGHTS.md`
- Improvements: `EDA_IMPROVEMENTS_2026.md`

---

**Last Updated:** April 28, 2026  
**All Tests:** ✅ Passing (434/434)  
**Plots Generated:** ✅ 21 ready for use  
**Documentation:** ✅ Complete
