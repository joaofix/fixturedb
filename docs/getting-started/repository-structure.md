# Repository Structure - FixtureDB Split

Directory structure and file organization for the split dataset project.

```
icsme-nier-2026/
│
├── PHASE RUNNER SCRIPTS (8-phase pipeline)
│   ├── phase_1a_scan_agent_files.py         # Scan for agent config files
│   ├── phase_1b_verify_agent_commits.py     # Verify agent commits via git
│   ├── phase_2_extract_pre_2021.py          # Extract pre-2021 fixtures
│   ├── phase_3_extract_llm.py               # Extract AGENT-generated fixtures
│   ├── phase_4_analyze_distribution.py      # Analyze distribution
│   ├── phase_5_stratified_sample.py         # Stratified sampling
│   ├── phase_6_7_export_and_document.py     # Export and documentation
│   └── phase_8_final_validation.py          # Final validation
│
├── CORE COLLECTION MODULES
│   └── collection/
│       ├── __init__.py
│       ├── agent_detector.py                # Phase 1A/1B: Agent detection logic
│       ├── fixture_extractor.py             # Phase 2/3: Fixture extraction logic
│       ├── dataset_sampler.py               # Phase 5: Stratification logic
│       ├── dataset_exporter.py              # Phase 6-7: Export logic
│       └── [+10 other supporting modules]
│
├── TEST SUITE
│   └── tests/
│       ├── conftest.py                      # Pytest fixtures and helpers
│       ├── test_split_agent_detector.py     # Tests for Phase 1A/1B
│       ├── test_split_fixture_extractor.py  # Tests for Phase 2/3
│       ├── test_split_dataset_sampler.py    # Tests for Phase 5
│       ├── test_split_dataset_exporter.py   # Tests for Phase 6-7
│       └── test_split_integration.py        # Integration tests
│
├── DATA & DATABASES
│   ├── corpus.db                            # Original FixtureDB (INPUT)
│   ├── fixturedb-human.db                   # Pre-2021 fixtures (OUTPUT Phase 2)
│   ├── fixturedb-agent.db                     # AGENT-generated fixtures (OUTPUT Phase 3)
│   ├── clones/                              # Git repositories (Phases 1, 3)
│   │   ├── owner1__repo1/
│   │   ├── owner2__repo2/
│   │   └── ...
│   └── output/                              # Exported CSV files and ZIPs
│
├── DOCUMENTATION
│   ├── docs/
│   │   ├── INDEX.md                         # Documentation navigation hub
│   │   │
│   │   ├── split/                           # PRIMARY: Split dataset docs
│   │   │   ├── README.md                    # Quick start and overview
│   │   │   ├── OVERVIEW.md                  # Architecture and design
│   │   │   ├── PHASES.md                    # Detailed phase documentation
│   │   │   ├── DATA_MODELS.md               # Schema and data structure
│   │   │   ├── EXECUTION_GUIDE.md           # Step-by-step execution
│   │   │   └── IMPLEMENTATION_STATUS.md     # Progress and validation
│   │   │
│   │   ├── architecture/                    # System architecture
│   │   │   ├── agent-detection.md           # Agent detection methodology
│   │   │   ├── database-schema.md           # Three-database schema
│   │   │   ├── detection.md                 # Fixture detection metrics
│   │   │   ├── configuration.md             # Configuration reference
│   │   │   ├── metrics-reference.md         # Metric definitions
│   │   │   └── ...
│   │   │
│   │   ├── getting-started/                 # Quick start guides
│   │   │   ├── intro.md                     # Introduction to split dataset
│   │   │   ├── setup.md                     # Setup and installation
│   │   │   └── repository-structure.md      # This file
│   │   │
│   │   ├── usage/                           # How to use the datasets
│   │   │   ├── usage.md                     # Analysis examples (SQL, pandas)
│   │   │   ├── fixture-patterns-reference.md # Fixture type reference
│   │   │   ├── reproducing.md               # Reproducibility guide
│   │   │   └── ...
│   │   │
│   │   ├── data/                            # Data format documentation
│   │   │   ├── csv-user-guide.md            # CSV export guide
│   │   │   ├── storage.md                   # Storage and size estimates
│   │   │   └── ...
│   │   │
│   │   ├── reference/                       # Reference material
│   │   │   ├── license.md
│   │   │   ├── references.md
│   │   │   ├── limitations.md
│   │   │   └── ...
│   │   │
│   │   └── internal/                        # Implementation notes
│   │       ├── FIXTUREDB_SPLIT_IMPLEMENTATION_PLAN.md
│   │       └── FIXTUREDB_SPLIT_TASK_BREAKDOWN.md
│   │
│   ├── README.md                            # Project README
│   ├── LICENSE                              # Project license
│   └── papers/                              # Associated papers and references
│
├── PROJECT FILES
│   ├── requirements.txt                     # Python dependencies
│   ├── pyproject.toml                       # Project metadata and pytest configuration
│   └── .gitignore
│
└── LOGS & ARTIFACTS
    ├── logs/                                # Execution logs
    ├── output/                              # Exported datasets (CSV, ZIP)
    ├── validation/                          # Validation reports
    └── htmlcov/                             # Test coverage reports
```

## Key Directories Explained

### Phase Runner Scripts (Root)
- One script per phase (phase_1a.py through phase_8.py)
- Run sequentially or with selective phases
- Each script can be run independently if inputs exist
- See [EXECUTION_GUIDE](../split/EXECUTION_GUIDE.md)

### collection/ Module
- Core implementation of all 8 phases
- Fully typed Python with comprehensive error handling
- Well-tested (19 unit tests, all passing)
- Import examples:
  ```python
  from collection.agent_detector import AgentFileScanner
  from collection.fixture_extractor import Pre2021FixtureExtractor
  from collection.dataset_sampler import StratifiedSampler
  from collection.dataset_exporter import HumanDatasetExporter
  ```

### Data Flow
```
corpus.db (input)
    ↓
Phase 2 (pre-2021 extraction) → fixtures_pre_2021.json
    ↓
Phase 5 (stratified sampling) → sampled_fixtures.json
    ↓
Phase 6-7 (export) → fixturedb-human.db + CSVs

clones/ (input for Phases 1, 3)
    ↓
Phase 1A → phase_1a_agent_files.json
    ↓
Phase 1B → phase_1b_agent_commits.json
    ↓
Phase 3 (AGENT extraction) → fixtures_llm.json
    ↓
Phase 4 (distribution) → distribution_analysis.json
    ↓
Phase 5 (sampling) → sampled_fixtures.json
    ↓
Phase 6-7 (export) → fixturedb-agent.db + CSVs
    ↓
Phase 8 (validation) → validation_report.json
```

### docs/ Organization
- **split/** — Primary: Everything about the split dataset
- **architecture/** — System design and methodology
- **getting-started/** — Quick start guides
- **usage/** — How to query and analyze
- **data/** — Data format details
- **reference/** — Citations and supplemental material
- **internal/** — Implementation notes

### tests/ Organization
- One test file per core module
- Test fixtures in conftest.py
- Run with: `pytest tests/ -v`

## Data Files Generated

### Phase Outputs
| Phase | Output Files | Format |
|-------|--------------|--------|
| 1A | phase_1a_agent_files.json | Agent file detection results |
| 1B | phase_1b_agent_commits.json | Agent commit verification |
| 2 | fixtures_pre_2021.json | Pre-2021 fixture extraction |
| 3 | fixtures_llm.json, llm_extraction_stats.json | AGENT extraction with agent metadata |
| 4 | distribution_analysis.json | Statistical distribution analysis |
| 5 | sampled_fixtures.json | Stratified sample IDs |
| 6-7 | fixturedb-*.db, *.csv, *.zip | Databases, exports, documentation |
| 8 | validation_report.json | Quality assurance report |

### Final Outputs
```
output/
├── fixturedb-human.db           (~50-100 MB)
├── fixturedb-agent.db             (~150-250 MB)
├── fixturedb-human.csv          (~20-40 MB)
├── fixturedb-agent.csv            (~40-80 MB)
├── repositories.csv
├── test_files.csv
├── README.md
├── SCHEMA.md
└── fixturedb-split-2026.zip     (~300-550 MB)
```

## Important Files

| File | Purpose | Modified For Split? |
|------|---------|---------------------|
| corpus.db | Original FixtureDB (unchanged) | No (read-only) |
| conftest.py | Test fixtures | Yes (split-specific) |
| requirements.txt | Python dependencies | Yes (phase-specific) |
| docs/split/* | Split dataset documentation | Yes (new files) |
| phase_*.py | 8-phase pipeline | Yes (core implementation) |
| collection/* | Core modules | Yes (split logic) |

## Not Included (Removed)

The following old documentation files have been removed (obsolete):
- collection/ (new command-line pipeline)
- docs/architecture/data-pipeline-overview.md (old architecture)
- docs/data/data-collection.md (SEART-GHS loading)
- docs/data/csv-export-guide.md (old corpus exports)
- docs/data/language-specific-csv-export.md (old framework exports)

These were replaced with split-specific documentation.

## Documentation Navigation

- **First-time user?** Start with [Introduction](../getting-started/intro.md)
- **Want to run the new dataset pipeline?** Go to [Collection CLI](../../collection/README.md)
- **Need to understand design?** Read [OVERVIEW](../split/OVERVIEW.md)
- **Want to analyze data?** See [Usage Guide](../usage/usage.md)
- **Looking for schema?** Check [Data Models](../split/DATA_MODELS.md)
