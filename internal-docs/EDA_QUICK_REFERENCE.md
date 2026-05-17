# FixtureDB EDA — Quick Reference Guide

## What Each Plot Shows (Research Applications)

### Corpus Overview
| Plot | Purpose | CSV Columns | Key Question |
|------|---------|-------------|---------------|
| `01a_corpus_by_tier` | Repository distribution by quality tier | repositories: stars | How many repos at each star level? |
| `01b_pipeline_status` | Data collection pipeline progress | repositories: status | What % of repos were successfully analyzed? |
| `02a_creation_timeline` | When were repositories created? | repositories: created_at | How old are the projects? |
| `02b_activity_recency` | Last commit dates across corpus | repositories: pushed_at | Are projects still active? |

### Fixture Characteristics (Primary Analysis)
| Plot | Purpose | CSV Columns | Key Question |
|------|---------|-------------|---------------|
| `03a_fixtures_per_repo` | How many fixtures per repository? | fixtures: id → grouped by repo | Fixture distribution across projects |
| `03b_fixture_scope` | Execution scope distribution | fixtures: scope | per_test vs per_class vs global? |
| **`03c_fixture_types`** | Detection patterns (NEW) | fixtures: fixture_type | What detection patterns are used? |
| **`03d_fixture_scopes`** | Scope percentages stacked (NEW) | fixtures: scope | Scope adoption by language % |
| `04a_mock_adoption` | Fixtures using mocks | mock_usages (SQLite) | Mock usage prevalence |
| `04b_framework_diversity` | Testing framework distribution | fixtures: framework | Which frameworks dominate? |

### Fixture Complexity & Size
| Plot | Purpose | CSV Columns | Key Question |
|------|---------|-------------|---------------|
| **`04c_lines_of_code`** | LOC distribution (NEW) | fixtures: loc | Typical fixture size? |
| `05a_nesting_depth` | Nesting level distribution | fixtures: max_nesting_depth | How deeply nested? |
| `05b_nesting_complexity_correlation` | Nesting vs complexity | fixtures: max_nesting_depth, cyclomatic_complexity | Does nesting drive complexity? |

### Fixture Design Patterns
| Plot | Purpose | CSV Columns | Key Question |
|------|---------|-------------|---------------|
| **`04e_framework_by_scope`** | Framework × scope interaction (NEW) | fixtures: framework, scope | Framework-specific scope patterns |
| **`05h_design_patterns`** | Parameters, calls, cleanup (NEW) | fixtures: num_parameters, num_objects_instantiated, num_external_calls, has_teardown_pair | How complex are fixture dependencies? |
| `05c_fixture_reuse_distribution` | How often are fixtures reused? | fixtures: reuse_count | Fixture reuse patterns |
| `05d_reuse_complexity_correlation` | Reuse vs complexity | fixtures: reuse_count, cyclomatic_complexity | Do reused fixtures differ in complexity? |
| `05e_teardown_adoption` | Cleanup code prevalence | fixtures: has_teardown_pair | Cleanup code adoption rate |

### Test File & Repository Analysis
| Plot | Purpose | CSV Columns | Key Question |
|------|---------|-------------|---------------|
| **`05g_test_file_characteristics`** | File size vs fixture count (NEW) | test_files: file_loc, num_fixtures, num_test_funcs | How are test files organized? |
| **`05i_repo_maturity`** | Popularity vs fixture quality (NEW) | repositories: stars, forks, num_contributors + fixture metrics | Do popular projects have better fixtures? |

---

## Data Exploration Workflows

### "I want to understand fixture sizes and complexity across languages"
1. Start with `03a_fixtures_per_repo` (fixture distribution)
2. Then `04c_lines_of_code` (size distribution)
3. Then `04d_complexity_metrics` (complexity patterns)
4. Then `05b_nesting_complexity_correlation` (what drives complexity?)

### "I want to see how different frameworks use fixtures"
1. Start with `04b_framework_diversity` (which frameworks present)
2. Then `04e_framework_by_scope` (how frameworks use scopes)
3. Then `03c_fixture_types` (detection patterns)
4. Deep dive: Use SQLite for framework-specific queries

### "I want to understand fixture design patterns"
1. Start with `05h_design_patterns` (parameters, calls, cleanup)
2. Then `05c_fixture_reuse_distribution` (how much reuse?)
3. Then `05d_reuse_complexity_correlation` (reused = simpler?)
4. Then `05g_test_file_characteristics` (file-level view)

### "I want to compare languages"
1. All plots show language comparison (colored by language)
2. Focus on `04c`, `04d` (complexity by language)
3. Focus on `03d` (scope patterns by language)
4. Focus on `04e` (framework patterns by language)

### "I want to see if repository maturity matters"
1. Start with `05i_repo_maturity` (4 panels of correlations)
2. Ask: Do stars correlate with fixture complexity? (usually no)
3. Ask: Do contributors correlate with reuse patterns? (maybe)

---

## CSV Columns Used in EDA

### fixtures.csv columns covered:
- ✓ id, language, repo, file_path, name
- ✓ **fixture_type** (new: `03c`)
- ✓ **scope** (new: `03d`) + existing `03b`
- ✓ **loc** (new: `04c`)
- ✓ **cyclomatic_complexity** (via Lizard)
- ✓ **num_parameters**, **num_objects_instantiated**, **num_external_calls** (new: `05h`)
- ✓ reuse_count (`05c`, `05d`)
- ✓ **has_teardown_pair** (new: `05h`) + existing `05e`
- ✓ framework (`04b`, `04e`)
- ✓ github_url, pinned_commit (in export, not visualized)

### repositories.csv columns covered:
- ✓ **stars**, **forks**, **num_contributors** (new: `05i`)
- ✓ created_at, pushed_at (`02a`, `02b`)
- ✓ num_test_files, num_fixtures (`03a`)
- ✓ status (`01b`)

### test_files.csv columns covered:
- ✓ **file_loc**, **num_fixtures**, **num_test_funcs** (new: `05g`)

---

## Reproducing the Plots

```bash
cd /home/joao/icsme-nier-2026

# Generate all plots
python pipeline.py quantitative-eda

# View in browser/screen instead of saving
python pipeline.py quantitative-eda --show

# Save to custom directory
python pipeline.py quantitative-eda --out figures/

# Run individual plot
python eda/quantitative/p03c_fixture_types.py --show
```

Output: `output/eda/quantitative/<timestamp>/` (latest symlink available)

---

## Plot Specifications

- **Resolution:** 300 DPI (publication-ready)
- **Format:** PNG
- **Size:** ~50-300 KB each (average 120 KB)
- **Total:** 21 plots, 2.5 MB
- **Style:** Consistent color palette, readable fonts
- **Data:** SQLite database (up-to-date with latest run)

---

## Connection to Zenodo Dataset

These plots directly reflect the three CSV files in the Zenodo archive:
- `fixtures.csv` — 35,169 fixtures with 20 columns
- `repositories.csv` — 200 repositories with 14 columns
- `test_files.csv` — 257,764 test files with 8 columns

**All plots use SQLite source but show what researchers will see in CSV exports.**

Use `python pipeline.py export --version <version>` to create new Zenodo exports with the latest plots.
