# Setup and Requirements - FixtureDB Between-Group Study

Instructions for setting up the FixtureDB between-group study collection environment.

## Prerequisites

Required: Python 3.10+ (tested with 3.12.3), and Git on PATH (needed for repository cloning and agent detection).

Optional:
- A `clones/` directory for repository cloning during collection — auto-populated if not present, and only needed once `discover-commits`/`extract-fixtures` actually clones repos.
- A GitHub API token, for higher rate limits when discovering agent repositories. Set it via `--github-token` or the `GITHUB_TOKEN` environment variable.

## Installation

```bash
git clone <repo-url>
cd fixturedb

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Verify the install:

```bash
python3 -c "import collection; print('✓ Collection package ready')"
python3 -m collection status
```

## Project Structure

See [Repository Structure](repository-structure.md) for the full, authoritative
directory layout — not duplicated here to avoid the two pages drifting apart.

## Dependencies

Core: `sqlite3` and `subprocess` (both built-in), `pathlib`/`os` for the filesystem, `json`/`csv` for data formats, `tree-sitter` for fixture detection, and `requests` (optional) for GitHub API calls.

Analysis (optional): `pandas`, `scipy` (Mann-Whitney U, chi-square), `numpy`.

Testing: `pytest`, `pytest-cov`.

## Running the Between-Group Study

The authoritative, reproducible pipeline for the paper's three datasets is
`python -m collection <verb> --dataset {a,b,c}`, run from the project root:

```bash
# Dataset A: discover repos, scan for agent commits, filter to test-touching commits, extract
python -m collection discover-repos      --dataset a
python -m collection discover-commits    --dataset a
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
pytest tests/test_agent_detector_pure.py -v
```

See [Test Suite & Validation](../reference/testing.md) for test organization and categories.

## Troubleshooting

### ImportError: No module named 'collection'
**Solution:** Ensure you're in the project root directory:
```bash
cd fixturedb
python -m collection --help
```

### sqlite3.OperationalError: no such table
**Solution:** Verify the relevant dataset's database exists and is valid
(run `extract-fixtures --dataset {a,b,c}` first if not):
```bash
sqlite3 db/a.db ".tables"  # Should show: fixtures repositories test_files mock_usages
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

1. Read the overview: [What is FixtureDB?](intro.md)
2. Run the pipeline: [Reproducing Results](../usage/reproducing.md)
3. Analyze the dataset: [Analysis Guide](../usage/usage.md)
