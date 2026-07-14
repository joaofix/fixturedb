# Setup and Requirements - FixtureDB Between-Group Study

Instructions for setting up the FixtureDB between-group study collection environment.

## Prerequisites

### Required
- **Python 3.10+** (tested with 3.12.3)
- **Git** (must be on PATH, required for repository cloning and agent detection)
- **corpus.db** (original FixtureDB database with repository list)

### Optional
- **clones/ directory** (for repository cloning during collection)
  - Will be auto-populated during collection if not present
  - Only needed once `discover-commits`/`extract-fixtures` actually clones repos
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
python3 -m collection status
```

## Project Structure

```
fixturedb/
├── collection/
│   ├── __init__.py
│   ├── __main__.py                    # Package CLI (python -m collection)
│   ├── human_corpus.py                # Human corpus collection (pre-2021)
│   ├── agent_corpus.py                # Agent corpus collection (2025+)
│   ├── between_group_comparison.py    # Statistical comparison
│   ├── agent_signal_primitives.py     # Agent detection in commits (formerly agent_detector.py)
│   ├── tiered_agent_corpus_scanner.py # Tier1/Tier2 corpus-scale orchestration (formerly agent_commit_detector.py)
│   ├── fixture_extractor.py           # Fixture extraction
│   ├── db.py                          # Database schema and helpers
│   ├── config.py                      # Paths, thresholds, dates -- re-exports catalogs from study_parameters/ and heuristics/
│   ├── study_parameters/              # Settings + study-design constants as YAML (extensions, frameworks, ...)
│   ├── heuristics/                    # Detection-heuristic catalogs as YAML/CSV (agent, fixture, mock patterns)
│   ├── detector.py                    # Fixture detection (tree-sitter)
│   └── persistent_clone.py            # Repository cloning utilities
│
├── db/
│   ├── corpus.db                      # Paired-study bootstrap DB (INPUT, only needed for --tier2)
│   └── a.db, b.db, c.db                # Per-dataset databases (OUTPUT)
│
├── datasets/                          # Per-dataset CSV output (the real, reviewable artifact)
│   ├── a/{repos,commits,test-commits,fixtures}/
│   ├── b/{repos,test-commits,fixtures}/
│   └── c/{repos,fixtures}/
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

The authoritative, reproducible pipeline for the paper's three datasets is
`python -m collection <verb> --dataset {a,b,c}`, run from the project root:

```bash
# Dataset A: discover repos, scan for agent commits, filter to test-touching commits, extract
python -m collection discover-repos      --dataset a
python -m collection discover-commits    --dataset a  # add --tier2 only if Tier 1 yield is insufficient
python -m collection filter-test-commits --dataset a
python -m collection extract-fixtures    --dataset a

# Dataset B (within-repo human) and Dataset C (cross-repo baseline)
python -m collection discover-repos      --dataset b
python -m collection filter-test-commits --dataset b
python -m collection extract-fixtures    --dataset b

python -m collection discover-repos   --dataset c
python -m collection extract-fixtures --dataset c

# Cross-cutting: distribution analysis, sampling, export, validation (per dataset)
python -m collection analyze-distribution --dataset a --against b
python -m collection sample    --dataset a
python -m collection export    --dataset a
python -m collection validate  --dataset a
```

See [docs/architecture/collection.md](../architecture/collection.md) for the
Dataset A/B/C → collector map, and
[Reproducing Results](../usage/reproducing.md) for detailed instructions and
optional parameters.

There is no separate root-level convenience CLI — `python -m collection` is
the one, authoritative surface for every stage.

## Quick Start

### Minimal Test (Dataset B Only)
```bash
python -m collection discover-repos      --dataset b --language python
python -m collection extract-fixtures    --dataset b --repos-per-language 5 --language python
```

This will:
1. Resolve Dataset B's repo list from Dataset A's already-discovered agent-enabled repositories
2. Extract human fixtures from the same 2025+ commit window as Dataset A
3. Write a small sample to `db/b.db`
4. Complete in 5-10 minutes

For a smaller, fully self-contained smoke test that never touches real data,
use `python -m collection toy --dataset b --repos 5` instead (writes under
`toy-dataset/` rather than `datasets/`/`db/`).

## Configuration

All parameters are command-line arguments. No configuration files needed:

```bash
# See all available options
python -m collection extract-fixtures --dataset b --help
python -m collection extract-fixtures --dataset c --help
python -m collection extract-fixtures --dataset a --help
```

## Database Setup

`db/corpus.db` (only needed for `discover-commits --tier2`) should already be
present in the root directory if you're bootstrapping from a paired-study
corpus. Verify:

```bash
sqlite3 db/corpus.db "SELECT COUNT(*) as fixture_count FROM fixtures;"
```

## GitHub API Setup (Optional)

For higher rate limits when discovering agent repositories:

```bash
export GITHUB_TOKEN=your_token_here
python -m collection discover-repos --dataset a
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
cd fixturedb
python -m collection --help
```

### sqlite3.OperationalError: no such table
**Solution:** Verify db/corpus.db exists and is valid:
```bash
sqlite3 db/corpus.db ".tables"  # Should show: fixtures repositories test_files
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
export GITHUB_TOKEN=your_token_here
python -m collection discover-repos --dataset a
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
