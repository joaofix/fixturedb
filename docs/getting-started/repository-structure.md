# Repository Structure - FixtureDB Between-Group Study

Directory structure and file organization for the between-group study project.

```
fixturedb/
│
├── MAIN CLI
│   └── collection/
│       ├── __main__.py                      # `python -m collection <verb> --dataset {a,b,c}`
│       ├── paths.py                         # Central path registry: datasets/{a,b,c}/{stage}, db/*.db, export/*.zip
│       │
│       ├── repository_quality_control/
│       │   ├── agent_repository_counter.py  # discover-repos --dataset a
│       │   └── agent_commit_counter.py      # discover-commits --dataset a
│       ├── repo_resolve.py                  # discover-repos --dataset b
│       ├── select_dataset_c_repos.py        # discover-repos --dataset c
│       ├── test_commit_filter.py            # filter-test-commits --dataset {a,b}
│       ├── tier2_discovery.py               # Tier-1/Tier-2 agent-commit discovery (discover-commits --tier2)
│       │
│       ├── agent_corpus.py                  # Dataset A collector (AgentCorpusCollector) -- extract-fixtures --dataset a
│       ├── human_corpus.py                  # Dataset B collector (HumanCorpusCollector) -- extract-fixtures --dataset b
│       ├── dataset_c.py                     # Dataset C collector (collect_dataset_c_fixtures) -- extract-fixtures --dataset c
│       │
│       ├── dataset_pipeline.py              # analyze-distribution / sample / export
│       ├── dataset_validator.py             # validate
│       ├── toy.py                           # toy --dataset {a,b,c}: small real run under toy-dataset/
│       │
│       ├── between_group_comparison.py      # Statistical comparison
│       ├── agent_signal_primitives.py       # Agent detection in commits (formerly agent_detector.py)
│       ├── tiered_agent_corpus_scanner.py   # Tier1/Tier2 corpus-scale orchestration (formerly agent_commit_detector.py)
│       ├── fixture_extractor.py             # Fixture extraction at commit level
│       ├── db.py                            # Database schema and helpers
│       ├── config.py                        # Thresholds, dates -- re-exports catalogs from study_parameters/ and heuristics/
│       ├── study_parameters/                # Settings + study-design constants as YAML (extensions, frameworks, ...)
│       ├── heuristics/                      # Detection-heuristic catalogs as YAML/CSV (agent, fixture, mock patterns)
│       ├── detector.py                      # Fixture detection (tree-sitter)
│       └── persistent_clone.py              # Repository cloning utilities
│
├── TEST SUITE
│   └── tests/
│       ├── conftest.py                      # Pytest fixtures and helpers
│       ├── test_fixture_extractor_small.py  # Fixture extraction tests
│       ├── test_db_helpers_full.py          # Database operation tests
│       ├── between_group/, paired/, eda/    # Corpus-comparison, legacy paired, and EDA tests
│       └── collection/                      # Unit tests per collection/ module, incl.
│                                             # test_main_cli.py (CLI dispatch),
│                                             # test_dataset_pipeline.py, test_repo_resolve.py, test_toy.py
│                                             # -- see docs/reference/testing.md for the fixture-detector categories
│
├── DATA & DATABASES
│   ├── datasets/                            # The real, reviewable output -- CSV files, one tree per dataset
│   │   ├── a/{repos,commits,test-commits,fixtures}/
│   │   ├── b/{repos,test-commits,fixtures}/
│   │   └── c/{repos,fixtures}/
│   │
│   ├── db/                                  # Secondary: per-dataset SQLite DBs
│   │   ├── a.db, b.db, c.db
│   │   └── corpus.db                        # Paired-study bootstrap DB (only needed for --tier2)
│   │
│   ├── export/                              # Final per-dataset export ZIPs (a.zip, b.zip, c.zip)
│   │
│   ├── toy-dataset/                         # Output of `toy --dataset X` -- mirrors datasets/+db/, gitignored
│   │
│   ├── github-search-raw/                   # SEART search export (dataset-agnostic input for A/C)
│   │
│   ├── clones/                              # Git repositories (auto-populated, ephemeral)
│   │
│   └── output/                              # Internal bookkeeping: summaries, sample_{dataset}.json
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
│   │   └── reference/                       # Reference material
│   │       ├── license.md                   # MIT (code) + CC BY 4.0 (data)
│   │       ├── references.md                # Academic citations
│   │       ├── limitations.md               # Study limitations
│   │       └── testing.md                   # Test suite documentation
│   │
│   ├── README.md                            # Project README
│   ├── LICENSE                              # Project license
│   └── references/                          # Associated papers and references (tracked PDFs)
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
- **`python -m collection <verb> --dataset {a,b,c}`** is the one, authoritative CLI
  surface. Verbs: `discover-repos`, `discover-commits` (Dataset A only),
  `filter-test-commits` (A/B only), `extract-fixtures`, `analyze-distribution`,
  `sample`, `export`, `validate`, `toy`, `paired`, `status`.
- There is no longer a separate root-level `pipeline.py` convenience CLI — it was
  retired once every verb it exposed had an equivalent under `python -m collection`.

### collection/ Module
Core implementation with one collector module per dataset:

**1. human_corpus.py — Dataset B (within-repo human control)**
- Extracts human fixtures from the same agent-enabled repos and 2025+ window as Dataset A
- Computes control variables at the `AGENT_CORPUS_START_DATE` snapshot
- Quality filters and statistics tracking
- Entry point: `python -m collection extract-fixtures --dataset b`

**2. dataset_c.py — Dataset C (cross-repo pre-2021 baseline)**
- Repos come from `select_dataset_c_repos.py` (`discover-repos --dataset c`): every
  repo created within a fixed window (`DATASET_C_MIN_CREATED_DATE` to
  `HUMAN_CORPUS_CUTOFF_DATE`), no sampling
- Checks out each one at its pinned pre-2021 cutoff commit and extracts
  every fixture from every test file at that snapshot
- Commit-count/test-file-count quality floor measured from real git history at
  the cutoff commit, not GitHub's live metadata (`count_commits_up_to()`)
- Entry point: `python -m collection extract-fixtures --dataset c`

**3. agent_corpus.py — Dataset A (agent-authored)**
- Uses the QC'd repo/commit CSVs to find agent-authored commits
- Tier 1 detection: author metadata + co-authored-by trailers
- Agent type classification (claude, copilot, cursor, etc.)
- Entry point: `python -m collection extract-fixtures --dataset a`

**4. between_group_comparison.py**
- Chi-square tests for categorical controls (language, domain)
- Mann-Whitney U tests for continuous controls (repo_age_years)
- Balance report generation

Supporting modules:
- **agent_signal_primitives.py** — Agent detection utilities (formerly agent_detector.py)
- **fixture_extractor.py** — Fixture extraction at commit level
- **db.py** — Database schema, helpers, and control variable functions
- **config.py** — Configuration constants (temporal boundaries, thresholds); re-exports reference-data catalogs loaded from **study_parameters/** and **heuristics/** (see [Configuration Reference](../architecture/configuration.md))
- **paths.py** — Central path registry for every dataset's `repos`/`commits`/`test-commits`/`fixtures` stage directories, `db/*.db`, `export/*.zip`

### Data Flow

```
github-search-raw/ (SEART export, dataset-agnostic input for A/C)
    ↓
discover-repos --dataset a   → datasets/a/repos/
discover-repos --dataset c   → datasets/c/repos/
discover-repos --dataset b   → datasets/b/repos/ (resolved from Dataset A's repos)
    ↓
discover-commits --dataset a [--tier2]      → datasets/a/commits/
    ↓
filter-test-commits --dataset a             → datasets/a/test-commits/
filter-test-commits --dataset b             → datasets/b/test-commits/
    ↓
extract-fixtures --dataset a   → Dataset A → db/a.db, datasets/a/fixtures/
extract-fixtures --dataset b   → Dataset B → db/b.db, datasets/b/fixtures/
extract-fixtures --dataset c   → Dataset C → db/c.db, datasets/c/fixtures/
    ↓
analyze-distribution --dataset X --against Y   (recommend a balanced sample size)
sample --dataset {a,b,c}                       → output/sample_{dataset}.json
export --dataset {a,b,c}                       → export/{dataset}.zip
validate --dataset {a,b,c}                     (each dataset is independently usable)
    ↓
Final: db/a.db, db/b.db, db/c.db, plus export/a.zip, export/b.zip, export/c.zip
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
- **fixture-patterns-reference.md** — Catalog of 25+ fixture types

**data/** — Data format documentation
- **csv-user-guide.md** — How to use CSV exports
- **storage.md** — Database sizes, temporary storage during processing

**reference/** — Citations and limitations
- **limitations.md** — Study limitations and threats to validity
- **references.md** — Academic citations and how to cite

### tests/ Organization
- One test file per core module (plus `tests/collection/` for phase-script tests)
- Test fixtures in conftest.py
- Run with: `pytest tests/ -v`

## Important Files

| File | Purpose |
|------|---------|
| collection/__main__.py | CLI entrypoint |
| collection/*.py | Core modules |
| db/corpus.db | Paired-study bootstrap DB (input only, only needed for `--tier2`) |
| db/{a,b,c}.db | Per-dataset results (output, created during collection) |
| conftest.py | Shared pytest fixtures |
| requirements.txt | Dependencies |
| docs/INDEX.md | Documentation hub |
| docs/getting-started/intro.md | Study design overview |
| docs/architecture/database-schema.md | Schema |
| docs/usage/reproducing.md | Pipeline guide |
| collection/README.md | Package docs |

## Data Files Generated

### Stage Outputs

| Dataset | Stage (verb) | Output Files | Format |
|-------|-------|--------------|--------|
| A | `discover-repos` | `datasets/a/repos/{lang}_repo.csv` | CSV |
| A | `discover-commits` | `datasets/a/commits/{lang}_commit.csv` | CSV |
| A/B | `filter-test-commits` | `datasets/{a,b}/test-commits/{lang}_test_commit.csv` | CSV |
| A/B/C | `extract-fixtures` | `datasets/{a,b,c}/fixtures/{lang}_fixtures.csv` + `db/{a,b,c}.db` | CSV + SQLite |
| A/B/C | `sample` | `output/sample_{dataset}.json` | JSON |
| A/B/C | `export` | `export/{dataset}.zip` | ZIP (CSV + docs) |

### Final Output

```
db/a.db, db/b.db, db/c.db    # Per-dataset repositories/fixtures/mock_usages

datasets/a/                  # Dataset A CSV exports (repos, commits, test-commits, fixtures)
datasets/b/                  # Dataset B CSV exports (repos, test-commits, fixtures)
datasets/c/                  # Dataset C CSV exports (repos, fixtures)

export/
├── a.zip                    # Dataset A standalone export
├── b.zip                    # Dataset B standalone export
└── c.zip                    # Dataset C standalone export

output/
├── sample_a.json / sample_b.json / sample_c.json
└── ... (internal bookkeeping, summaries)
```

## Documentation Navigation

- **New to the project?** Start with [Introduction](../getting-started/intro.md)
- **Want to run the pipeline?** Go to [Setup](../getting-started/setup.md)
- **Need to understand the design?** Read [Between-Group Study](../getting-started/intro.md)
- **Ready to collect data?** See [Reproducing Results](../usage/reproducing.md)
- **Want to analyze data?** Check [Usage Guide](../usage/usage.md)
- **Looking for database schema?** See [Database Schema](../architecture/database-schema.md)

