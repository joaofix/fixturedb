# AGENTS.md — FixtureDB Project Context

This file provides context for AI coding assistants (GitHub Copilot, Kilo AI, Claude Code, etc.) working on this repository.

---

## What is this project?

**FixtureDB** is the replication package for a conference paper:

> *"An empirical study on test fixture usage by coding agents on open source software"*

It's a master's thesis companion codebase. The pipeline detects agent-authored commits in GitHub repositories, extracts test fixtures from them, and compares agent vs human fixture characteristics.


## Key concepts
- Agnet enabled repository: A Github repository that has passed our validation that checks for AI conding agent configuration files. Meaning that the repository is probably using the AI conding agent for conding tasks.
- Agent commit: a commit authored or co-authored by an AI coding agent (Claude, Copilot, Cursor, Aider, etc.), detected via `Co-authored-by:` trailers and author metadata
- Agent test commit: An agent commit that specifically modifies a test file.
- SEART Github Search: The tool we use to collect a complete list of Github repositories that matches our quality criteria. Stored at github-search-raw/. This is the list of repos we start with for datasets A and C.

## Key datasets we build
- **Dataset A** (`fixtures-from-agents/`): agent-authored fixtures from agent-enabled repos
- **Dataset B** (`fixtures-from-humans/`): human-authored fixtures from the same repos (matched control)
- **Dataset C** (`fixtures-from-humans/cross-repo/`): human-authored fixtures from pre-2021 repos (inter-repo baseline)

## Languages we collect fixtures for

Python, Java, JavaScript, TypeScript.

## Architecture

```
collection/          # Main pipeline code (the "library")
  config.py          # All constants, paths, thresholds
  db.py              # SQLite schema, upsert helpers, migrations
  agent_commit_detector.py  # Commit scanning, agent detection, adoption intensity
  agent_corpus.py    # Phase 3: extract agent fixtures
  human_corpus.py    # Phase 2: extract human fixtures (within-repo)
  fixture_extractor.py     # Tree-sitter AST fixture extraction
  detector.py        # Fixture pattern detection
  corpus_utils.py    # Shared repo/fixture persistence helpers
  between_group_comparison.py  # Statistical balance tests
  phase_*.py         # Pipeline phases 1–8 (orchestration scripts)
tests/               # pytest suite (752 tests)
eda/                 # Exploratory data analysis notebooks
docs/                # Full documentation
internal-docs/       # Internal notes, methodology improvements
```

## Pipeline phases

1. **Phase 1A–1D**: Discover agent-enabled repos, scan for agent commits, assess yield
2. **Phase 2**: Extract human fixtures from agent-enabled repos → `fixturedb-human.db`
3. **Phase 3**: Extract agent fixtures from the same repos → `fixturedb-agent.db`
4. **Phase 4**: Analyze fixture distribution
5. **Phase 5**: Stratified sampling
6. **Phase 6–7**: Export CSVs + ZIP archives
7. **Phase 8**: Final validation

## Database

SQLite via `collection/db.py`. Two output databases: `fixturedb-agent.db` and `fixturedb-human.db`. Schema includes `repositories`, `test_files`, `fixtures`, `commit_observations`, `test_commits`, `mock_usages`. Use `db_session()` context manager for all DB access — it handles WAL mode, retries, and connection pooling.

## Key constants (config.py)

- `AGENT_CORPUS_START_DATE = "2025-01-01"` — adoption window start
- `HUMAN_CORPUS_CUTOFF_DATE = "2020-12-31"` — pre-agent cutoff for Dataset C
- `MIN_STARS = 500`, `MIN_COMMITS = 100`, `MIN_TEST_FILES = 5` — quality thresholds

## Testing

```bash
python3 -m pytest tests/ -v     # Full suite (~33s)
python3 -m pytest tests/test_adoption_intensity.py -v  # Single module
```

Tests use `tmp_path` fixtures for temporary git repos and SQLite databases. Never run pytest from the repo root without `testpaths = ["tests"]` in config — the `clones/` directory contains hundreds of external repos with their own tests.

## Code style

- Python 3.12+, formatted with ruff (line-length 88), linted with Ruff
- Type hints used throughout `collection/`
- Logging via `collection/logging_utils.py` (`get_logger(__name__)`)
- Database access always through `db_session()` context manager
- Shared utilities in `corpus_utils.py` — avoid duplicating repo/fixture persistence logic

---

## Personal instructions
- If we fix a bug, we unit test that
- If we implement a new feature, we unit test that
- We use a python virtualenv called venv to run tests
- A prompt that changed code is only considered finished if all tests are passing
- If we change collection/, we evaluate the need to update the docs/ folder as well. collection/ represents the methodology of this work as code. We want to keep documentation up to date with the methodology.