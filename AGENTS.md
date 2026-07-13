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
- **Dataset A** (`datasets/a/`): agent-authored fixtures from agent-enabled repos
- **Dataset B** (`datasets/b/`): human-authored fixtures from the same repos (matched control)
- **Dataset C** (`datasets/c/`): human-authored fixtures from pre-2021 repos (cross-repo baseline)

Every dataset is built through the same CLI verbs, selected via `--dataset {a,b,c}`
(`python -m collection <verb> --dataset X`) — see "Command-line interface" below.
Each verb calls exactly one collector/function; no runtime branching decides which
dataset a run produces:

| Dataset | `extract-fixtures` collector |
|---|---|
| A | `agent_corpus.AgentCorpusCollector` |
| B | `human_corpus.HumanCorpusCollector.run()` |
| C | `dataset_c.collect_dataset_c_fixtures()` |

## Languages we collect fixtures for

Python, Java, JavaScript, TypeScript.

## Architecture

```
collection/          # Main pipeline code (the "library")
  __main__.py        # `python -m collection <verb> --dataset {a,b,c}` -- the one CLI surface
  paths.py           # Central path registry: datasets/{a,b,c}/{stage}, db/{a,b,c}.db, export/{a,b,c}.zip
  config.py          # Thresholds, dates -- loads catalogs from config_data/ below
  config_data/       # Reference-data catalogs as YAML (non-code extensions, boilerplate-
                     # repo exclusion keywords, framework registry, per-language configs,
                     # feature extraction patterns) -- edit these, not the .py files, to update a catalog
  db.py              # SQLite schema, upsert helpers, migrations
  tiered_agent_corpus_scanner.py  # Commit scanning, agent detection, adoption intensity (formerly agent_commit_detector.py)
  agent_signal_primitives.py  # Low-level agent config-file + commit-trailer detection (formerly agent_detector.py)
  agent_patterns.py  # Loads the agent catalog (see heuristics/ below) and derives detection dicts
  tier2_discovery.py # Tier-1 corpus assessment + Tier-2 SEART discovery (discover-commits --dataset a --tier2)
  heuristics/agent_heuristics.yaml  # paper_scope only now -- edit here to change the paper's strict-scope agent subset (this project's own catalog, kept at heuristics/ root)
  heuristics/agent-mining/agent_files.csv  # Config-file/directory patterns (pattern,tool,start_date,end_date) -- mirrors labri-progress/agent-mining's files.csv schema+content for citation
  heuristics/agent-mining/agent_authors.csv  # Commit author/trailer signatures (pattern,tool,start_date,end_date) -- mirrors labri-progress/agent-mining's authors.csv schema+content for citation
  heuristics/agent-mining/bots.csv  # CI/automation bot account patterns (pattern,tool) -- mirrors labri-progress/agent-mining's bots.csv schema+content for citation
  heuristics/fixture_definitions.yaml  # Operational definition of "fixture" per language -- edit here to update a detector pattern; also documents per-language `excluded` boundary cases the fixture detectors deliberately don't catch (reviewer audit trail)
  clone_primitives.py / ephemeral_clone.py / persistent_clone.py  # Layered cloning: raw primitive / throttled ephemeral / DB-tracked persistent
  repository_quality_control/agent_repository_counter.py  # discover-repos --dataset a
  repository_quality_control/agent_commit_counter.py      # discover-commits --dataset a
  repo_resolve.py    # discover-repos --dataset b (resolves Dataset B's repo list from Dataset A's)
  select_dataset_c_repos.py  # discover-repos --dataset c
  test_commit_filter.py      # filter-test-commits --dataset {a,b}
  agent_corpus.py    # Dataset A: extract agent fixtures (extract-fixtures --dataset a)
  human_corpus.py    # Dataset B: extract human fixtures, within-repo (extract-fixtures --dataset b)
  dataset_c.py        # Dataset C: extract human fixtures, cross-repo baseline (extract-fixtures --dataset c)
  dataset_pipeline.py # analyze-distribution / sample / export cross-cutting stages
  dataset_validator.py # validate stage
  toy.py              # `toy --dataset {a,b,c}`: small real end-to-end run under toy-dataset/
  fixture_extractor.py     # Tree-sitter AST fixture extraction
  detector.py        # Fixture pattern detection
  corpus_utils.py    # Shared repo/fixture persistence helpers
  between_group_comparison.py  # Statistical balance tests
  validation_sampling.py  # Manual, on-demand Cochran-formula sampling for human review (not part of the automatic pipeline)
tests/               # pytest suite
eda/                 # Exploratory data analysis notebooks
docs/                # Full documentation
internal-docs/       # Internal notes, methodology improvements
```

## Command-line interface

One CLI, one set of step verbs shared across all three datasets:

```bash
python -m collection discover-repos       --dataset {a,b,c}
python -m collection discover-commits     --dataset a [--tier2]
python -m collection filter-test-commits  --dataset {a,b}
python -m collection extract-fixtures     --dataset {a,b,c}
python -m collection analyze-distribution --dataset a --against b
python -m collection sample               --dataset {a,b,c}
python -m collection export               --dataset {a,b,c}
python -m collection validate             --dataset {a,b,c}
python -m collection toy                  --dataset {a,b,c} [--repos N]
```

Not every verb applies to every dataset (`discover-commits`/most of `filter-test-commits`
are Dataset-A/B-specific, since Dataset C has no per-commit history scan) — invoking one
that doesn't apply exits 1 with an explicit message. Every verb resolves its default
input/output directories through `collection/paths.py`; `toy` runs the identical step
functions rooted under `toy-dataset/` instead of `datasets/`+`db/`.

`python -m collection paired` bootstraps `db/corpus.db`, only needed for `--tier2`.

## Database

SQLite via `collection/db.py`. One output database per dataset: `db/a.db`, `db/b.db`,
`db/c.db` (plus `db/corpus.db`, the paired-study bootstrap DB). Schema includes
`repositories`, `test_files`, `fixtures`, `commit_observations`, `test_commits`,
`mock_usages`. Use `db_session()` context manager for all DB access — it handles WAL
mode, retries, and connection pooling. The database is secondary: the CSV files under
`datasets/{a,b,c}/` are the real, reviewable output of each pipeline stage.

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
- We use a python virtualenv called venv to run tests, using the command "pytest tests/"
- A prompt that changed code is only considered finished if all tests are passing
- If we change collection/, we evaluate the need to update the docs/ folder as well. collection/ represents the methodology of this work as code. We want to keep documentation up to date with the methodology.