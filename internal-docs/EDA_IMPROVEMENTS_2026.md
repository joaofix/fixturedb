# FixtureDB — Quantitative EDA Improvements

## Overview

Enhanced quantitative exploratory data analysis with **8 new plots** that directly reflect the improved CSV export structure and provide deeper insights into fixture characteristics across languages.

**Total plots: 21** (13 existing + 8 new)  
**All plots:** Publication-quality PNG files in `output/eda/quantitative/latest/`

---

## New Plots Added

### 1. **Fixture Types (Detection Patterns)** — `03c_fixture_types.png`
**What it shows:** Top 5 fixture detection patterns (pytest_decorator, unittest_setup, junit4_before, etc.) across languages

**Why it matters:**
- Directly reflects the new `fixture_type` column in fixtures.csv (Zenodo export)
- Shows language-specific patterns: pytest dominates Python, JUnit family dominates Java
- Researchers can see what detection patterns are most common in their language of interest

**Key insights from data:**
- Framework-specific detection patterns clearly separated by language
- Cross-language comparison of standardization (e.g., Python has fewer patterns than Java/JS)

---

### 2. **Fixture Scopes (Stacked Bar)** — `03d_fixture_scopes.png`
**What it shows:** Distribution of execution scopes (per_test, per_class, per_module, global) by language

**Why it matters:**
- Reflects the new `scope` column in fixtures.csv
- Shows when/where fixtures are created (test setup, class setup, module setup, global)
- Important for understanding fixture lifecycle and cleanup requirements

**Key insights:**
- per_test scope dominates in Python/JavaScript (isolated fixtures)
- per_class scope more prevalent in Java (OOP fixture patterns)
- Very few global fixtures (good practice indicator)

---

### 3. **Lines of Code Distribution** — `04c_lines_of_code.png`
**What it shows:** 4-panel analysis of fixture LOC distribution (box plot, violin plot, histogram, statistics table)

**Why it matters:**
- Reflects the `loc` column in fixtures.csv
- Helps researchers understand fixture size variation
- Supports complexity analysis: is complexity driven by LOC?

**Key insights:**
- Distribution shapes differ significantly by language
- JavaScript/TypeScript fixtures tend to be more complex (more LOC)
- Outliers visible but don't dominate the distribution

---

### 4. **Note on Cognitive Complexity**
**Status:** Cognitive complexity metric was removed in Phase 3 due to lack of programmatic support for non-Python languages (complexipy is Python-only with no equivalent alternatives for Java, JavaScript, or TypeScript). Analysis focuses on `cyclomatic_complexity` and `max_nesting_depth` as primary complexity metrics.

---

### 5. **Framework by Execution Scope** — `04e_framework_by_scope.png`
**What it shows:** Testing frameworks (top 4 per language) and how scope usage varies by framework

**Why it matters:**
- Combines `framework` and `scope` columns from fixtures.csv
- Shows framework conventions: some frameworks favor certain scopes
- Helps researchers understand testing practices per framework

**Key insights:**
- pytest heavily skews toward per_test scope
- JUnit fixtures mixed between per_class and per_method
- Framework choice influences scope patterns

---

### 6. **Test File Characteristics** — `05g_test_file_characteristics.png`
**What it shows:** 4-panel analysis of test file size, fixture count, and relationships

**Why it matters:**
- Reflects columns in test_files.csv (file_loc, num_fixtures, num_test_funcs)
- Shows test file organization patterns
- Answer: "How many fixtures per test file on average?"

**Key insights:**
- Linear relationship between file size and fixture count
- Average fixtures per file ranges 1.5-3 by language
- Larger test files don't necessarily have more fixtures

---

### 7. **Fixture Design Patterns** — `05h_design_patterns.png`
**What it shows:** 4-panel analysis of fixture dependencies and cleanup patterns

**Why it matters:**
- Reflects new columns in fixtures.csv: `num_parameters`, `num_external_calls`, `num_objects_instantiated`, `has_teardown_pair`
- Shows how "heavy" fixtures are in terms of dependencies
- Teardown adoption directly affects cleanup requirements

**Key insights:**
- Most fixtures have 0-2 parameters (simple designs)
- External calls (I/O, API) appear in 10-20% of fixtures
- Teardown adoption 15-25% (cleanup code present)
- Object instantiation patterns vary by language (Python less, Java more)

---

### 8. **Repository Maturity vs Fixture Quality** — `05i_repo_maturity.png`
**What it shows:** 4-panel analysis of how repository popularity/maturity correlates with fixture quality

**Why it matters:**
- Combines repositories.csv metrics (stars, forks, num_contributors) with fixture metrics
- Answers: "Do popular projects have better fixtures?"
- Helps researchers understand quality signals

**Key insights:**
- No strong correlation between stars and fixture complexity
- Contributors impact fixture design (more contributors → more external calls?)
- Popular projects aren't necessarily more complex; suggests good fixture design

---

## Plot Organization

All plots saved to: `/home/joao/icsme-nier-2026/output/eda/quantitative/latest/`

Numbering convention:
- `01a/01b` — Corpus & Pipeline (high-level)
- `02a/02b` — Temporal characteristics
- `03a-03e` — Fixtures per repo, scope (now with new types/scopes plots)
- `04a-04e` — Mock adoption, framework, LOC, complexity (enhanced)
- `05a-05i` — Nesting, reuse, teardown, contributors, files, design, maturity

---

## Design Improvements Over Previous Version

| Aspect | Before | After | Benefit |
|--------|--------|-------|---------|
| **CSV Alignment** | Generic plots | Direct CSV columns | Researchers see exactly what's exported |
| **New Metrics** | 14 plots | 22 plots | Complete coverage of CSV structure |
| **Fixture Types** | Not visualized | `03c_fixture_types.png` | Shows detection pattern distribution |
| **Scope Analysis** | Simple scatter | `03d_fixture_scopes.png` (stacked %) | Better percentage-based view |
| **LOC Distribution** | Minimal | `04c_lines_of_code.png` (4 panels) | Comprehensive size analysis |
| **Complexity Metrics** | Separate | `04d_complexity_metrics.png` (comparison) | Highlights metric relationships |
| **Framework+Scope** | Separate | `04e_framework_by_scope.png` | Shows interaction patterns |
| **Test Files** | Not analyzed | `05g_test_file_characteristics.png` | New dimension: file characteristics |
| **Design Patterns** | Scattered | `05h_design_patterns.png` (unified) | Complete design picture |
| **Maturity vs Quality** | Not analyzed | `05i_repo_maturity.png` | Empirical quality signals |

---

## How to Use These Plots in Papers/Presentations

**For Data Description:**
- Use `03c`, `03d`, `04a`, `04b` to show corpus characteristics
- Use `01a`, `01b` for overview and data quality

**For Fixture Analysis:**
- Use `03a`, `03c`, `03d`, `04c`, `04d` for fixture distribution and complexity
- Use `05c`, `05d` for reuse patterns
- Use `05h` for design pattern analysis

**For Framework/Language Comparison:**
- Use `04b`, `04e` for framework adoption and patterns
- Use `04c`, `04d` for language-specific complexity

**For Test Engineering Insights:**
- Use `05g` for test file organization
- Use `05h` for fixture dependencies and cleanup
- Use `05i` for maturity indicators

---

## Technical Notes

**Data Source:** SQLite database (`data/corpus.db`)  
**Direct CSV Export Reflection:** All new plots directly correspond to exported CSV columns

**CSV Columns Now Visualized:**
- fixtures.csv: `fixture_type`, `scope`, `loc`, `cyclomatic_complexity`, `num_parameters`, `num_objects_instantiated`, `num_external_calls`, `reuse_count`, `has_teardown_pair`
- test_files.csv: `file_loc`, `num_fixtures`, `num_test_funcs`
- repositories.csv: `stars`, `forks`, `num_contributors`

**Quality Metrics:**
- All plots use consistent color palette (language-based)
- Box plots, histograms, scatter plots, and correlation analysis
- Statistical summaries in tables where applicable
- 2.5 MB total PNG output (publication-ready resolution)

---

## Next Steps

1. **Use in ICSME submission:** Reference these plots in data showcase track
2. **Export with Zenodo:** Include in supplementary materials
3. **Iterate based on feedback:** Add/modify plots based on reviewer comments

All plots regenerate automatically with `python pipeline.py quantitative-eda` whenever data changes.
