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
│       ├── tiered_agent_corpus_scanner.py   # Tier 1 corpus-scale orchestration (formerly agent_commit_detector.py)
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
│   │   └── a.db, b.db, c.db
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

### Main CLI (root)

`python -m collection <verb> --dataset {a,b,c}` is the one, authoritative CLI surface. Verbs: `discover-repos`, `discover-commits` (Dataset A only), `filter-test-commits` (A/B only), `extract-fixtures`, `analyze-distribution`, `sample`, `export`, `validate`, `toy`, `paired`, `status`. There is no separate root-level `pipeline.py` convenience CLI — it was retired once every verb it exposed had an equivalent under `python -m collection`.

### collection/ module

One collector module per dataset:

- **`human_corpus.py` — Dataset B (within-repo human control).** Extracts human fixtures from the same agent-enabled repos and 2025+ window as Dataset A, computing control variables at the `AGENT_CORPUS_START_DATE` snapshot. Entry point: `extract-fixtures --dataset b`.
- **`dataset_c.py` — Dataset C (cross-repo pre-2021 baseline).** Repos come from `select_dataset_c_repos.py` (`discover-repos --dataset c`): every repo created within a fixed window (`DATASET_C_MIN_CREATED_DATE` to `HUMAN_CORPUS_CUTOFF_DATE`), no sampling. Each is checked out at its pinned pre-2021 cutoff commit, and every fixture is extracted from every test file at that snapshot. The commit-count/test-file-count quality floor is measured from real git history at the cutoff commit (`count_commits_up_to()`), not GitHub's live metadata. Entry point: `extract-fixtures --dataset c`.
- **`agent_corpus.py` — Dataset A (agent-authored).** Uses the QC'd repo/commit CSVs to find agent-authored commits via Tier 1 detection (author metadata plus co-authored-by trailers) and classify agent type (claude, copilot, cursor, etc.). Entry point: `extract-fixtures --dataset a`.
- **`between_group_comparison.py`.** Chi-square tests for categorical controls (language, domain), Mann-Whitney U for continuous controls (repo_age_years), and balance report generation.

Supporting modules: `agent_signal_primitives.py` (agent detection utilities, formerly `agent_detector.py`), `fixture_extractor.py` (fixture extraction at commit level), `db.py` (schema, helpers, control-variable functions), `config.py` (configuration constants, re-exporting the reference-data catalogs in `study_parameters/` and `heuristics/` — see [Configuration Reference](../architecture/configuration.md)), and `paths.py` (the central path registry for every dataset's stage directories, `db/*.db`, and `export/*.zip`).

### Data Flow

```
github-search-raw/ (SEART export, dataset-agnostic input for A/C)
    ↓
discover-repos --dataset a   → datasets/a/repos/
discover-repos --dataset c   → datasets/c/repos/
discover-repos --dataset b   → datasets/b/repos/ (resolved from Dataset A's repos)
    ↓
discover-commits --dataset a                → datasets/a/commits/
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

See [docs/INDEX.md](../INDEX.md) for the full documentation map — the tree above already shows where each page lives.

### tests/ Organization
- One test file per core module (plus `tests/collection/` for phase-script tests)
- Test fixtures in conftest.py
- Run with: `pytest tests/ -v`

## Important Files

| File | Purpose |
|------|---------|
| collection/__main__.py | CLI entrypoint |
| collection/*.py | Core modules |
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

See [docs/INDEX.md](../INDEX.md) for where to go next.

