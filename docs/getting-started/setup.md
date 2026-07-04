# Setup and Requirements - FixtureDB Between-Group Study

Instructions for setting up the FixtureDB between-group study collection environment.

## Prerequisites

### Required
- **Python 3.10+** (tested with 3.12.3)
- **Git** (must be on PATH, required for repository cloning and agent detection)
- **corpus.db** (original FixtureDB database with repository list)

### Optional
- **clones/ directory** (for agent corpus collection)
  - Will be auto-populated during collection if not present
  - Only needed for Stage 2 (agent corpus)
- **GitHub API token** (for higher rate limits when discovering agent repositories)
  - Can be set via `--github-token` flag or `GITHUB_TOKEN` environment variable

## Installation

### 1. Clone Repository
```bash
git clone <repo-url>
cd icsme-nier-2026
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Verify Installation
```bash
# Check the collection package is importable
python3 -c "import collection; print('✓ Collection package ready')"

# Test CLI
python3 pipeline.py status
```

## Project Structure

```
icsme-nier-2026/
├── pipeline.py                        # Main CLI entrypoint
├── collection/
│   ├── __init__.py
│   ├── __main__.py                    # Package CLI (python -m collection)
│   ├── human_corpus.py                # Human corpus collection (pre-2021)
│   ├── agent_corpus.py                # Agent corpus collection (2025+)
│   ├── between_group_comparison.py    # Statistical comparison
│   ├── github_api_search.py           # GitHub API integration
│   ├── github_archive.py              # Historical data access (optional)
│   ├── agent_signal_primitives.py     # Agent detection in commits (formerly agent_detector.py)
│   ├── tiered_agent_corpus_scanner.py # Tier1/Tier2 corpus-scale orchestration (formerly agent_commit_detector.py)
│   ├── fixture_extractor.py           # Fixture extraction
│   ├── db.py                          # Database schema and helpers
│   ├── config.py                      # Configuration constants
│   ├── detector.py                    # Fixture detection (tree-sitter)
│   └── persistent_clone.py            # Repository cloning utilities
│
├── data/
│   ├── corpus.db                      # Original FixtureDB corpus (INPUT)
│   └── between-group.db               # Between-group database (OUTPUT)
│
├── clones/                            # Git repositories (auto-populated)
│   ├── pytest__pytest/
│   ├── django__django/
│   └── ...
│
├── output/                            # Collection outputs
│   ├── human_corpus_summary_*.json    # Human corpus statistics
│   ├── agent_corpus_summary_*.json    # Agent corpus statistics
│   └── between_group_comparison_*.json # Statistical comparison
│
├── docs/                              # This documentation
│   ├── getting-started/               # Quick start guides
│   ├── architecture/                  # Technical documentation
│   ├── usage/                         # Analysis guides
│   ├── data/                          # Data format documentation
│   └── reference/                     # Citations and reference material
│
├── tests/                             # Test suite
│   ├── conftest.py
│   └── test_*.py
│
└── requirements.txt
```

## Dependencies

### Core
- **sqlite3** — Database operations (built-in)
- **subprocess** — Git operations
- **pathlib, os** — File system operations
- **json, csv** — Data formats
- **requests** (optional) — GitHub API calls
- **tree-sitter** — Fixture detection

### Analysis (Optional)
- **pandas** — Data analysis
- **scipy** — Statistical tests (Mann-Whitney U, chi-square)
- **numpy** — Numerical operations

### Testing
- **pytest** — Test framework
- **pytest-cov** — Coverage reporting

## Running the Between-Group Study

The authoritative, reproducible pipeline for the paper's three datasets is the
numbered `collection/phase_1a_scan_agent_commits.py` through
`collection/phase_8_final_validation.py` sequence — run from the project
root as modules:

```bash
# Phase 1A-1D: discover agent-enabled repos, scan for agent commits
python -m collection.phase_1a_scan_agent_commits
python -m collection.phase_1b_verify_agent_commits
python -m collection.phase_1c_assess_tier1_yield
python -m collection.phase_1d_discover_matched_repos  # only if Tier 1 is insufficient

# Phase 2 / 2B: Dataset B (within-repo human) and Dataset C (cross-repo baseline)
python -m collection.phase_2_extract_human
python -m collection.phase_2b_extract_dataset_c

# Phase 3: Dataset A (agent fixtures)
python -m collection.phase_3_extract_agent

# Phase 4-8: distribution analysis, stratified sampling, export, validation
python -m collection.phase_4_analyze_distribution
python -m collection.phase_5_stratified_sample
python -m collection.phase_6_7_export_and_document
python -m collection.phase_8_final_validation
```

Each phase script prints "Next steps" pointing at the following phase. See
[docs/architecture/collection.md](../architecture/collection.md) for the
Dataset A/B/C → script → collector map, and
[Reproducing Results](../usage/reproducing.md) for detailed instructions and
optional parameters.

The root `pipeline.py` is a separate, older manual convenience CLI (`python
pipeline.py human-fixtures`, `agent-fixtures`, `between-group-stats`,
`status`, ...) kept around for ad-hoc single-stage runs. It is **not** the
authoritative pipeline above — use the phase scripts for reproducing the
paper's datasets.

## Quick Start

### Minimal Test (Dataset B Only)
```bash
python -m collection.phase_2_extract_human --repos-per-language 5 --language python
```

This will:
1. Query corpus.db for agent-enabled repositories
2. Extract human fixtures from the same 2025+ commit window as Dataset A
3. Write a small sample to `data/fixturedb-human.db`
4. Complete in 5-10 minutes

## Configuration

All parameters are command-line arguments. No configuration files needed:

```bash
# See all available options
python -m collection.phase_2_extract_human --help
python -m collection.phase_2b_extract_dataset_c --help
python -m collection.phase_3_extract_agent --help
```

## Database Setup

The corpus.db should already be present in the root directory. Verify:

```bash
sqlite3 data/corpus.db "SELECT COUNT(*) as fixture_count FROM fixtures;"
```

Expected output: approximately `35169` fixtures in the original corpus.

## GitHub API Setup (Optional)

For higher rate limits when collecting agent corpus (legacy `pipeline.py` CLI):

```bash
# Option 1: Pass as argument
python pipeline.py agent-fixtures --github-token YOUR_GITHUB_TOKEN

# Option 2: Set environment variable
export GITHUB_TOKEN=your_token_here
python pipeline.py agent-fixtures
```

To get a token: Visit https://github.com/settings/tokens and create a "Personal access token (classic)" with `public_repo` scope.

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=collection --cov-report=html

# Run specific test file
pytest tests/test_agent_detector.py -v
```

Current status: All tests passing.

## Troubleshooting

### ImportError: No module named 'collection'
**Solution:** Ensure you're in the project root directory:
```bash
cd icsme-nier-2026
python -m collection human --help
```

### sqlite3.OperationalError: no such table
**Solution:** Verify corpus.db exists and is valid:
```bash
sqlite3 data/corpus.db ".tables"  # Should show: fixtures repositories test_files
```

### Python version error
**Solution:** Check Python version:
```bash
python --version  # Should be 3.10+
```

### Git not found
**Solution:** Ensure git is installed and on PATH:
```bash
git --version
which git  # On Windows: where git
```

### Rate limit exceeded (GitHub API)
**Solution:** Use an authenticated token:
```bash
python pipeline.py agent-fixtures --github-token YOUR_TOKEN
```

## Next Steps

1. **Read the overview:** [What is FixtureDB?](intro.md)
2. **Run the pipeline:** [Reproducing Results](../usage/reproducing.md)
3. **Analyze the dataset:** [Analysis Guide](../usage/usage.md)
4. **Understand the design:** [Between-Group Study](intro.md)


1. **Understand the approach:** Read [OVERVIEW](../split/OVERVIEW.md)
2. **Run the pipeline:** Follow [Execution Guide](../split/EXECUTION_GUIDE.md)
3. **Explore the data:** Use [Usage Guide](../usage/usage.md) for SQL examples
4. **Review results:** Check [Implementation Status](../split/IMPLEMENTATION_STATUS.md)
