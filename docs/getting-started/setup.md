# Setup and Requirements

## Prerequisites

- Python 3.11+
- Git (must be on `PATH`)
- Pre-scraped repository data from SEART-GHS (download CSV files)
- Optionally: A GitHub personal access token (for enhanced cloning pre-checks)

## Installation

```bash
git clone https://github.com/marcelofa/fixture-corpus.git
cd fixture-corpus

pip install -r requirements.txt

# Optional: set GITHUB_TOKEN for GitHub API pre-checks during cloning
# This improves performance but is not required. Pre-checks fail gracefully.
cp .env.example .env
# Open .env and set GITHUB_TOKEN=<your token> (optional)
# Get a token at: https://github.com/settings/tokens

# Download SEART-GHS CSV files and place in github-search/ folder
# See docs/data/data-collection.md for details

python pipeline.py init
```

## Dependencies

| Package         | Purpose |
|-----------------|---------|
| `tree-sitter` + language bindings | AST parsing for fixture detection (all 6 languages) |
| `lizard`        | Cyclomatic complexity metrics and parameter count |
| `complexipy`    | SonarQube-standard cognitive complexity for Python (fast, Rust-based) |
| `requests`      | GitHub API calls for cloning pre-checks (optional) |
| `python-dotenv` | `.env` file loading |
| `pandas`        | CSV export and validation sample generation |
| `tqdm`          | Progress bars |
| `gitpython`     | Git operations in the cloner |
