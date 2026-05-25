# Repository Structure - FixtureDB Between-Group Study

Directory structure and file organization for the between-group study project.

```
icsme-nier-2026/
│
├── MAIN CLI & PIPELINES
│   ├── pipeline.py                          # Main CLI entrypoint
│   │   ├── python pipeline.py human          # Stage 1: Human corpus (pre-2021)
│   │   ├── python pipeline.py agent          # Stage 2: Agent corpus (2023+)
│   │   └── python pipeline.py between-group-stats  # Stage 3: Comparison
│   │
│   └── collection/
│       ├── __main__.py                      # Package CLI: `python -m collection`
│       ├── human_corpus.py                  # Human corpus collection (430+ lines)
│       ├── agent_corpus.py                  # Agent corpus collection (380+ lines)
│       ├── between_group_comparison.py      # Statistical comparison (410+ lines)
│       ├── github_api_search.py             # GitHub API integration
│       ├── agent_detector.py                # Agent detection in commits
│       ├── fixture_extractor.py             # Fixture extraction at commit level
│       ├── db.py                            # Database schema and helpers
│       ├── config.py                        # Configuration constants
│       ├── detector.py                      # Fixture detection (tree-sitter)
│       └── cloner.py                        # Repository cloning utilities
│
├── TEST SUITE
│   └── tests/
│       ├── conftest.py                      # Pytest fixtures and helpers
│       ├── test_agent_detector.py           # Agent detection tests
│       ├── test_fixture_extractor.py        # Fixture extraction tests
│       ├── test_db.py                       # Database operation tests
│       └── test_integration.py              # Integration tests (all passing)
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
- **pipeline.py** — Entry point for all commands
  - `python pipeline.py human` — Stage 1: Collect pre-2021 fixtures
  - `python pipeline.py agent` — Stage 2: Collect 2023+ agent-authored fixtures
  - `python pipeline.py between-group-stats` — Stage 3: Run statistical comparison
  - `python pipeline.py status` — Check database and output status

### collection/ Module
Core implementation of between-group study with three main collection modules:

**1. human_corpus.py (430+ lines)**
- Extracts pre-2021 fixtures from corpus.db
- Computes control variables at 2021-01-01 snapshot
- Quality filters and statistics tracking
- Outputs JSON summary to `output/human_corpus_summary_*.json`

**2. agent_corpus.py (380+ lines)**
- Uses GitHub API to find agent-authored commits
- Tier 1 detection: co-authored-by trailers only
- Agent type classification (claude, copilot, cursor, etc.)
- Outputs JSON summary to `output/agent_corpus_summary_*.json`

**3. between_group_comparison.py (410+ lines)**
- Chi-square tests for categorical controls (language, domain, star_tier)
- Mann-Whitney U tests for continuous controls (repo_age_years)
- Balance report generation
- Outputs JSON to `output/between_group_comparison_*.json`

Supporting modules:
- **agent_detector.py** — Agent detection utilities
- **fixture_extractor.py** — Fixture extraction at commit level
- **db.py** — Database schema, helpers, and control variable functions
- **config.py** — Configuration constants (temporal boundaries, patterns)

### Data Flow

```
corpus.db (input)
    ↓
Stage 1: python pipeline.py human
    → Reads pre-2021 repositories
    → Extracts fixtures at 2021-01-01 snapshot
    → Computes control variables (language, domain, star_tier, repo_age)
    → Outputs human_corpus_summary_*.json
    → Writes to between-group.db (commit_kind='human')
    ↓
Stage 2: python pipeline.py agent
    → Queries GitHub API for agent configs
    → Detects agent commits (co-authored-by trailers)
    → Extracts fixtures from agent commits (2023+)
    → Computes control variables at 2023-06-01 snapshot
    → Outputs agent_corpus_summary_*.json
    → Appends to between-group.db (commit_kind='agent', agent_type)
    ↓
Stage 3: python pipeline.py between-group-stats
    → Loads human_corpus_summary_*.json
    → Loads agent_corpus_summary_*.json
    → Runs chi-square and Mann-Whitney U tests
    → Generates balance report
    → Outputs between_group_comparison_*.json
    ↓
Final: between-group.db with both corpora + comparison summary JSON
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
- One test file per core module
- Test fixtures in conftest.py
- Run with: `pytest tests/ -v`
- All 19 tests passing

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

### Stage Outputs

| Stage | Output Files | Format | Description |
|-------|--------------|--------|-------------|
| 1 | human_corpus_summary_*.json | JSON | Pre-2021 fixtures, control distributions, QC results |
| 2 | agent_corpus_summary_*.json | JSON | Agent-authored fixtures, agent types, control distributions |
| 3 | between_group_comparison_*.json | JSON | Chi-square/Mann-Whitney results, balance tests, p-values |

### Final Output

```
data/between-group.db
├── repositories      # Control variables (language, domain, star_tier, repo_age)
├── test_files       # File-level metadata
├── fixtures         # Human and agent fixtures with commit_kind, agent_type
└── mock_usages      # Mock framework usage per fixture

output/
├── human_corpus_summary_YYYYMMDD_HHMMSS.json     # JSON (Stage 1)
├── agent_corpus_summary_YYYYMMDD_HHMMSS.json     # JSON (Stage 2)
└── between_group_comparison_YYYYMMDD_HHMMSS.json # JSON (Stage 3)
```

## Documentation Navigation

- **New to the project?** Start with [Introduction](../getting-started/intro.md)
- **Want to run the pipeline?** Go to [Setup](../getting-started/setup.md)
- **Need to understand the design?** Read [Between-Group Study](../getting-started/intro.md)
- **Ready to collect data?** See [Reproducing Results](../usage/reproducing.md)
- **Want to analyze data?** Check [Usage Guide](../usage/usage.md)
- **Looking for database schema?** See [Database Schema](../architecture/database-schema.md)

