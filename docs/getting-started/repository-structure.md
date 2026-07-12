# Repository Structure - FixtureDB Between-Group Study

Directory structure and file organization for the between-group study project.

```
icsme-nier-2026/
│
├── MAIN CLI & PIPELINES
│   ├── The authoritative, reproducible pipeline is the numbered phase scripts below.
│   │   pipeline.py (root) is a separate, older manual convenience CLI — not
│   │   the pipeline used to build the paper's datasets.
│   │
│   └── collection/
│       ├── __main__.py                      # Package CLI: `python -m collection`
│       ├── phase_1a_scan_agent_commits.py   # Phase 1A: scan for agent commits
│       ├── phase_1b_verify_agent_commits.py # Phase 1B: verify agent commits
│       ├── phase_1c_assess_tier1_yield.py   # Phase 1C: assess Tier 1 yield
│       ├── phase_1d_discover_matched_repos.py # Phase 1D: Tier 2 matched repos (optional)
│       ├── phase_2_extract_human.py         # Phase 2: Dataset B (human, within-repo)
│       ├── select_dataset_c_repos.py        # Selects Dataset C repos (creation-date window, no sampling) -- run before Phase 2B
│       ├── phase_2b_extract_dataset_c.py    # Phase 2B: Dataset C (human, cross-repo baseline)
│       ├── phase_3_extract_agent.py         # Phase 3: Dataset A (agent-authored)
│       ├── phase_4_analyze_distribution.py  # Phase 4: distribution analysis
│       ├── phase_5_stratified_sample.py     # Phase 5: stratified sampling
│       ├── phase_6_7_export_and_document.py # Phase 6-7: export + ZIP archives
│       ├── phase_8_final_validation.py      # Phase 8: final validation
│       │
│       ├── agent_corpus.py                  # Dataset A collector (AgentCorpusCollector)
│       ├── human_corpus.py                  # Dataset B collector (HumanCorpusCollector)
│       ├── dataset_c.py                     # Dataset C collector (collect_dataset_c_fixtures)
│       ├── between_group_comparison.py      # Statistical comparison
│       ├── agent_signal_primitives.py       # Agent detection in commits (formerly agent_detector.py)
│       ├── tiered_agent_corpus_scanner.py   # Tier1/Tier2 corpus-scale orchestration (formerly agent_commit_detector.py)
│       ├── fixture_extractor.py             # Fixture extraction at commit level
│       ├── db.py                            # Database schema and helpers
│       ├── config.py                        # Paths, thresholds, dates -- loads catalogs from config_data/
│       ├── config_data/                     # Reference-data catalogs as YAML (extensions, frameworks, ...)
│       ├── detector.py                      # Fixture detection (tree-sitter)
│       └── persistent_clone.py              # Repository cloning utilities
│
├── TEST SUITE
│   └── tests/
│       ├── conftest.py                      # Pytest fixtures and helpers
│       ├── test_fixture_extractor_small.py  # Fixture extraction tests
│       ├── test_db_helpers.py                # Database operation tests
│       └── collection/                      # Per-phase-script tests, incl.
│                                             # test_phase_2_extract_human.py,
│                                             # test_phase_2b_extract_dataset_c.py
│
├── DATA & DATABASES
│   ├── data/
│   │   ├── corpus.db                        # Original FixtureDB (INPUT)
│   │   └── between-group.db                 # Between-group results (OUTPUT)
│   │
│   ├── clones/                              # Git repositories (auto-populated)
│   │   ├── pytest__pytest/
│   │   ├── django__django/
│   │   ├── owner__repo/
│   │   └── ... (for agent corpus only)
│   │
│   └── output/                              # Collection outputs
│       ├── human_corpus_summary_*.json      # Human corpus statistics
│       ├── agent_corpus_summary_*.json      # Agent corpus statistics
│       └── between_group_comparison_*.json  # Balance tests and comparison
│
├── DOCUMENTATION
│   ├── docs/
│   │   ├── INDEX.md                         # Documentation navigation hub
│   │   │
│   │   ├── getting-started/                 # Quick start guides
│   │   │   ├── intro.md                     # Between-group study overview
│   │   │   ├── setup.md                     # Setup and installation
│   │   │   └── repository-structure.md      # This file
│   │   │
│   │   ├── architecture/                    # Technical architecture
│   │   │   ├── database-schema.md           # Between-group schema
│   │   │   ├── agent-detection.md           # Agent detection methodology
│   │   │   ├── detection.md                 # Fixture detection logic
│   │   │   ├── configuration.md             # Configuration reference
│   │   │   ├── metrics-reference.md         # Metric definitions
│   │   │   └── ...
│   │   │
│   │   ├── usage/                           # How to analyze the dataset
│   │   │   ├── usage.md                     # Analysis examples with SQL
│   │   │   ├── fixture-patterns-reference.md # Fixture type reference
│   │   │   ├── reproducing.md               # Three-stage reproducibility guide
│   │   │   └── ...
│   │   │
│   │   ├── data/                            # Data format documentation
│   │   │   ├── csv-user-guide.md            # CSV export guide
│   │   │   ├── csv-export-guide.md          # CSV export detailed reference
│   │   │   ├── storage.md                   # Storage and size estimates
│   │   │   └── ...
│   │   │
│   │   ├── reference/                       # Reference material
│   │   │   ├── license.md                   # MIT (code) + CC BY 4.0 (data)
│   │   │   ├── references.md                # Academic citations
│   │   │   ├── limitations.md               # Study limitations
│   │   │   └── testing.md                   # Test suite documentation
│   │   │
│   │   └── split/                           # DEPRECATED: Paired study documentation
│   │       ├── README.md                    # Paired methodology (legacy)
│   │       ├── OVERVIEW.md                  # Paired design notes (legacy)
│   │       └── ... (archived for reference)
│   │
│   ├── README.md                            # Project README
│   ├── LICENSE                              # Project license
│   └── papers/                              # Associated papers and references
│
├── PROJECT FILES
│   ├── requirements.txt                     # Python dependencies
│   ├── pyproject.toml                       # Project metadata and pytest config
│   ├── collection/
│   │   └── README.md                        # Collection package documentation
│   └── .gitignore
│
└── LOGS & ARTIFACTS
    ├── logs/                                # Execution logs
    ├── output/                              # Exported JSON summaries
    ├── validation/                          # Validation reports
    └── htmlcov/                             # Test coverage reports
```

## Key Directories Explained

### Main CLI (Root)
- **The numbered `collection/phase_1a...phase_8` scripts** are the authoritative,
  reproducible entry points — run as `python -m collection.phase_N_name`.
- **pipeline.py** — a separate, older manual convenience CLI (`human-fixtures`,
  `agent-fixtures`, `between-group-stats`, `status`, ...) for ad-hoc single-stage
  runs. Not the authoritative pipeline.

### collection/ Module
Core implementation with one collector module per dataset:

**1. human_corpus.py — Dataset B (within-repo human control)**
- Extracts human fixtures from the same agent-enabled repos and 2025+ window as Dataset A
- Computes control variables at the `AGENT_CORPUS_START_DATE` snapshot
- Quality filters and statistics tracking
- Entry point: `phase_2_extract_human.py`

**2. dataset_c.py — Dataset C (cross-repo pre-2021 baseline)**
- Repos come from `select_dataset_c_repos.py`: every repo created within a fixed
  window (`DATASET_C_MIN_CREATED_DATE` to `HUMAN_CORPUS_CUTOFF_DATE`), no sampling
- Checks out each one at its pinned pre-2021 cutoff commit and extracts
  every fixture from every test file at that snapshot
- Commit-count/test-file-count quality floor measured from real git history at
  the cutoff commit, not GitHub's live metadata (`count_commits_up_to()`)
- Entry point: `phase_2b_extract_dataset_c.py`

**3. agent_corpus.py — Dataset A (agent-authored)**
- Uses the QC'd repo/commit CSVs to find agent-authored commits
- Tier 1 detection: author metadata + co-authored-by trailers
- Agent type classification (claude, copilot, cursor, etc.)
- Entry point: `phase_3_extract_agent.py`

**4. between_group_comparison.py**
- Chi-square tests for categorical controls (language, domain, star_tier)
- Mann-Whitney U tests for continuous controls (repo_age_years)
- Balance report generation

Supporting modules:
- **agent_signal_primitives.py** — Agent detection utilities (formerly agent_detector.py)
- **fixture_extractor.py** — Fixture extraction at commit level
- **db.py** — Database schema, helpers, and control variable functions
- **config.py** — Configuration constants (temporal boundaries, thresholds); loads reference-data catalogs from **config_data/** (see [Configuration Reference](../architecture/configuration.md))

### Data Flow

```
corpus.db (input)
    ↓
Phase 1A-1D: discover agent-enabled repos, scan/verify agent commits
    ↓
Phase 2: phase_2_extract_human.py           → Dataset B → fixturedb-human.db
select_dataset_c_repos.py                   → dataset_c_{lang}.csv (repo list, no sampling)
Phase 2B: phase_2b_extract_dataset_c.py     → Dataset C → fixturedb-human.db
    ↓
Phase 3: phase_3_extract_agent.py           → Dataset A → fixturedb-agent.db
    ↓
Phase 4-5: distribution analysis + stratified sampling
    ↓
Phase 6-7: export CSVs + ZIP archives per dataset
    ↓
Phase 8: final validation (each dataset is independently usable)
    ↓
Final: fixturedb-human.db (Datasets B + C) and fixturedb-agent.db (Dataset A),
plus per-dataset CSV/ZIP exports and comparison summary JSON
```

### docs/ Organization

**getting-started/** — For newcomers
- **intro.md** — Between-group study design and methodology
- **setup.md** — Installation and running the pipeline
- **repository-structure.md** — This file

**architecture/** — Technical deep dives
- **database-schema.md** — Between-group schema with control variables
- **agent-detection.md** — How agents are identified in commits
- **detection.md** — Fixture detection methodology (tree-sitter)
- **metrics-reference.md** — How each metric is calculated

**usage/** — How to analyze results
- **reproducing.md** — Three-stage pipeline with parameters
- **usage.md** — SQL queries for analysis, statistical tests
- **fixture-patterns-reference.md** — Catalog of 50+ fixture types

**data/** — Data format documentation
- **csv-user-guide.md** — How to use CSV exports
- **storage.md** — Database sizes, temporary storage during processing

**reference/** — Citations and limitations
- **limitations.md** — Study limitations and threats to validity
- **references.md** — Academic citations and how to cite

**split/** — DEPRECATED
- Legacy documentation for paired within-repository design
- Kept for reference but no longer the active methodology

### tests/ Organization
- One test file per core module (plus `tests/collection/` for phase-script tests)
- Test fixtures in conftest.py
- Run with: `pytest tests/ -v`

## Important Files

| File | Purpose | Between-Group? |
|------|---------|---------|
| pipeline.py | CLI entrypoint | Yes (3 new commands) |
| collection/*.py | Core modules | Yes (1,800+ new lines) |
| data/corpus.db | Original corpus | Input only (read-only) |
| data/between-group.db | Between-group results | Output (created during collection) |
| conftest.py | Test fixtures | Yes (updated) |
| requirements.txt | Dependencies | Yes (updated) |
| docs/INDEX.md | Documentation hub | Yes (updated) |
| docs/getting-started/intro.md | Overview | Yes (new) |
| docs/architecture/database-schema.md | Schema | Yes (updated) |
| docs/usage/reproducing.md | Pipeline guide | Yes (updated) |
| collection/README.md | Package docs | Yes (updated) |

## Data Files Generated

### Phase Outputs

| Dataset | Phase | Output Files | Format |
|-------|-------|--------------|--------|
| B | 2 | phase_2_extraction_stats_*.json | JSON |
| C | 2B | phase_2b_extraction_stats_*.json | JSON |
| A | 3 | (repo summary + fixture CSVs under fixtures-from-agents/) | JSON + CSV |
| — | 4-8 | phase_4/5/6_7/8_*.json | JSON |

### Final Output

```
data/fixturedb-human.db      # Datasets B and C (repositories/fixtures/mock_usages)
data/fixturedb-agent.db      # Dataset A (repositories/fixtures/mock_usages)

fixtures-from-agents/        # Dataset A CSV exports
fixtures-from-humans/        # Dataset B (same-repo/) and Dataset C (cross-repo/) CSV exports

output/
├── phase_2_extraction_stats_YYYYMMDD_HHMMSS.json
├── phase_2b_extraction_stats_YYYYMMDD_HHMMSS.json
├── phase_4_distribution_analysis_*.json
└── ... (phases 5-8)
```

## Documentation Navigation

- **New to the project?** Start with [Introduction](../getting-started/intro.md)
- **Want to run the pipeline?** Go to [Setup](../getting-started/setup.md)
- **Need to understand the design?** Read [Between-Group Study](../getting-started/intro.md)
- **Ready to collect data?** See [Reproducing Results](../usage/reproducing.md)
- **Want to analyze data?** Check [Usage Guide](../usage/usage.md)
- **Looking for database schema?** See [Database Schema](../architecture/database-schema.md)

