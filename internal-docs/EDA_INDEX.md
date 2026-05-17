# FixtureDB EDA — Complete Index & Navigation Guide

**Last Generated:** April 28, 2026  
**Status:** ✅ All 21 plots ready | 434 tests passing | Zenodo export synchronized

---

## 📊 What's New

- **8 new plots** directly reflecting improved CSV structure
- **4 reference guides** explaining all 21 plots
- **Complete data insights** revealing fixture patterns across languages
- **Full documentation sync** with new CSV columns

---

## 🗂️ Documentation Files (Start Here)

### For Understanding What Changed
1. **[EDA_COMPLETE_SUMMARY.md](EDA_COMPLETE_SUMMARY.md)** ← **START HERE**
   - Executive summary of all improvements
   - What changed, why, and how to use it
   - Integration with Zenodo release
   - ~500 lines, 10-min read

2. **[EDA_IMPROVEMENTS_2026.md](EDA_IMPROVEMENTS_2026.md)**
   - Detailed description of 8 new plots
   - Design principles and benefits
   - Publication readiness specs
   - ~400 lines, 5-min read per plot

### For Practical Use
3. **[EDA_QUICK_REFERENCE.md](EDA_QUICK_REFERENCE.md)**
   - Which plot to use for what research question
   - Data exploration workflows (4 example scenarios)
   - CSV column mapping
   - Plot-to-insight guide
   - **Use this** when analyzing the dataset

4. **[EDA_KEY_INSIGHTS.md](EDA_KEY_INSIGHTS.md)**
   - Data-driven findings from new plots
   - Language comparison tables with statistics
   - Fixture type patterns
   - Teardown adoption analysis (Python 76% vs Java 13%)
   - **Read this** for empirical context

---

## 📈 Plot Categories

### Group 1: Corpus Overview (4 plots)
- `01a_corpus_by_tier.png` — Repository distribution by star count
- `01b_pipeline_status.png` — Data collection completeness
- `02a_creation_timeline.png` — Repository creation dates
- `02b_activity_recency.png` — Last commit recency

**Use When:** Describing dataset composition and quality

### Group 2: Fixture Characteristics (8 plots)
- `03a_fixtures_per_repo.png` — Distribution across projects
- `03b_fixture_scope.png` — Scope distribution
- **`03c_fixture_types.png`** ⭐ NEW — Detection pattern adoption
- **`03d_fixture_scopes.png`** ⭐ NEW — Scope percentages by language
- `04a_mock_adoption.png` — Mock usage rates
- `04b_framework_diversity.png` — Framework adoption
- **`04c_lines_of_code.png`** ⭐ NEW — Fixture size analysis (4 panels)
- **`04d_complexity_metrics.png`** ⭐ NEW — Cyclomatic vs cognitive (4 panels)

**Use When:** Analyzing fixture patterns, distributions, and frameworks

### Group 3: Advanced Metrics (7 plots)
- `05a_nesting_depth.png` — Code nesting analysis
- `05b_nesting_complexity_correlation.png` — Nesting vs complexity
- `05c_fixture_reuse_distribution.png` — Reuse patterns
- `05d_reuse_complexity_correlation.png` — Reused fixtures simpler?
- `05e_teardown_adoption.png` — Cleanup code prevalence
- **`05g_test_file_characteristics.png`** ⭐ NEW — File organization (4 panels)
- **`05h_design_patterns.png`** ⭐ NEW — Dependencies & cleanup (4 panels)

**Use When:** Deep-diving into fixture design and quality signals

### Group 4: Comparative Analysis (2 plots)
- **`04e_framework_by_scope.png`** ⭐ NEW — Framework-specific scope patterns
- **`05i_repo_maturity.png`** ⭐ NEW — Popularity vs fixture quality (4 panels)

**Use When:** Comparing languages, frameworks, or project characteristics

---

## 🎯 How to Use This

### Scenario 1: "I want to understand the dataset"
1. Read **[EDA_COMPLETE_SUMMARY.md](EDA_COMPLETE_SUMMARY.md)** (executive overview)
2. Browse plots in `/output/eda/quantitative/latest/` (visual tour)
3. Refer to **[EDA_QUICK_REFERENCE.md](EDA_QUICK_REFERENCE.md)** as needed

### Scenario 2: "I'm writing about fixture patterns"
1. Read **[EDA_KEY_INSIGHTS.md](EDA_KEY_INSIGHTS.md)** (empirical findings)
2. Use plots: `03c`, `03d`, `04c`, `04d`, `05h`
3. Include statistics from tables in Quick Reference

### Scenario 3: "I want to analyze a specific aspect"
1. Go to **[EDA_QUICK_REFERENCE.md](EDA_QUICK_REFERENCE.md)**
2. Find your research question in "Data Exploration Workflows"
3. Follow recommended plot sequence
4. Deep-dive with SQLite queries using CSV columns listed

### Scenario 4: "I'm presenting this data"
1. Select 5-6 plots from Improvements guide based on topic
2. Add context from Key Insights
3. Reference Complete Summary in presentation notes

---

## 📁 File Locations

```
/home/joao/icsme-nier-2026/
├── EDA_COMPLETE_SUMMARY.md           ← Master reference (start here)
├── EDA_IMPROVEMENTS_2026.md           ← Detailed plot descriptions
├── EDA_QUICK_REFERENCE.md            ← Research workflows & CSV mapping
├── EDA_KEY_INSIGHTS.md               ← Data-driven findings
├── EDA_INDEX.md                      ← This file
│
├── output/eda/quantitative/
│   └── latest/                       ← All 21 PNG plots (symlink)
│       ├── 01a_corpus_by_tier.png
│       ├── 03c_fixture_types.png     ⭐ NEW
│       ├── 03d_fixture_scopes.png    ⭐ NEW
│       ├── 04c_lines_of_code.png     ⭐ NEW
│       ├── 04d_complexity_metrics.png ⭐ NEW
│       ├── 04e_framework_by_scope.png ⭐ NEW
│       ├── 05g_test_file_characteristics.png ⭐ NEW
│       ├── 05h_design_patterns.png   ⭐ NEW
│       ├── 05i_repo_maturity.png     ⭐ NEW
│       └── ... (13 existing plots)
│
├── eda/quantitative/
│   ├── quantitative_eda.py           (MAIN: runs all plots)
│   ├── p03c_fixture_types.py         ⭐ NEW
│   ├── p03e_fixture_scopes.py        ⭐ NEW
│   ├── p04c_lines_of_code.py         ⭐ NEW
│   ├── p04d_complexity_metrics.py    ⭐ NEW
│   ├── p04e_framework_by_scope.py    ⭐ NEW
│   ├── p05g_test_file_characteristics.py ⭐ NEW
│   ├── p05h_design_patterns.py       ⭐ NEW
│   ├── p05i_repo_maturity.py         ⭐ NEW
│   └── ... (existing plot scripts)
│
├── data/corpus.db                    (Data source: SQLite)
├── export/fixturedb_v1.0-zenodo_*/   (Zenodo exports with new CSVs)
└── docs/                             (Updated: 11 files synchronized)
```

---

## 🔄 Regenerating Plots

```bash
# All plots (creates new timestamp directory)
python pipeline.py quantitative-eda

# View interactively (no save)
python pipeline.py quantitative-eda --show

# Custom output location
python pipeline.py quantitative-eda --out figures/

# Individual plot
python eda/quantitative/p03c_fixture_types.py --show
```

**Output:** `output/eda/quantitative/<timestamp>/` (latest symlink always points to newest)

---

## 📊 Plot Statistics

| Metric | Value |
|--------|-------|
| **Total Plots** | 21 |
| **New Plots** | 8 ⭐ |
| **Total Size** | 2.5 MB |
| **Average Size** | 120 KB |
| **Resolution** | 300 DPI (publication-ready) |
| **CSV Columns Covered** | 28+ |
| **Languages Analyzed** | 4 (Python, Java, JS, TS) |
| **Data Points** | 35K fixtures, 200 repos, 257K test files |

---

## ✅ Quality Assurance

- **Tests:** 434/434 passing ✅
- **CSV Alignment:** All 8 new plots directly explore export columns ✅
- **Documentation:** All 11 docs files updated ✅
- **Zenodo Export:** Synchronized and ready ✅
- **Plot Output:** All 21 PNG files generated successfully ✅

---

## 📚 Recommended Reading Order

1. **First Time Users:** EDA_COMPLETE_SUMMARY → EDA_IMPROVEMENTS_2026
2. **Researchers:** EDA_QUICK_REFERENCE → EDA_KEY_INSIGHTS
3. **Paper Writers:** EDA_IMPROVEMENTS_2026 (plot descriptions) → EDA_KEY_INSIGHTS (findings)
4. **Practitioners:** EDA_QUICK_REFERENCE (workflows)
5. **Quick Answer:** EDA_QUICK_REFERENCE (table of contents)

---

## 🎯 Key Statistics

From EDA_KEY_INSIGHTS (see file for complete analysis):

| Language | Scope (per_test) | Teardown | Avg LOC | Avg Complexity |
|----------|------------------|----------|---------|-----------------|
| **Python** | 93.4% | 76.3% | 6.34 | 1.32 cycl / 0.33 cog |
| **Java** | 59.6% | 13.4% | 7.80 | 1.18 cycl / 0.90 cog |
| **JavaScript** | 90.1% | 16.4% | 8.00 | 1.09 cycl / 1.05 cog |
| **TypeScript** | 91.6% | 14.7% | 7.59 | 1.04 cycl / 0.96 cog |

---

## 💡 Use Cases

### For ICSME Data Showcase Track
Include 5-6 plots showing:
- Corpus composition (`01a`, `01b`)
- Fixture distribution (`03a`, `04c`)
- Language comparisons (`03d`, `04d`)

### For Research Paper
Reference plots for:
- Dataset background (use 01a/01b)
- Fixture characteristics (use 03c, 04c, 04d)
- Design patterns (use 05h)
- Research findings (use relevant plots)

### For Presentations
- Show 5-10 key plots
- Use EDA_KEY_INSIGHTS for statistics
- Build narrative around language/framework differences

### For Zenodo Release
- Include EDA plots in supplementary materials
- Link to these guides in README
- Mention plots in dataset description

---

## 🔗 Related Resources

- **CSV Export Guide:** `docs/data/csv-export-guide.md`
- **CSV User Guide:** `docs/data/csv-user-guide.md`
- **Database Schema:** `docs/architecture/database-schema.md`
- **Quick Start:** `docs/getting-started/`

---

## 📝 Summary

**8 new plots** created to directly visualize:
- ✅ New CSV columns (fixture_type, scope, LOC, complexity)
- ✅ Design patterns (parameters, external calls, teardown)
- ✅ Test file characteristics
- ✅ Repository maturity correlations

**All plots support Zenodo release** with synchronized documentation.

**Ready for:** Publication, presentation, research, Zenodo supplementary materials

---

**Questions?** Refer to the appropriate guide above. Start with [EDA_COMPLETE_SUMMARY.md](EDA_COMPLETE_SUMMARY.md).
