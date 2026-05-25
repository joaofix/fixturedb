# Collection Package

This package implements the paired within-repository study for FixtureDB.

## Primary Command

```bash
python -m collection paired
```

The paired command samples repositories that contain both human and agent commits, extracts fixtures at the commit level, and writes a paired-study summary plus the study database.

## Command Reference

- `python -m collection paired` - run the paired study
- `python -m collection status` - print a short status message

The top-level wrapper `python pipeline.py paired` is equivalent.

## Agent-first Workflow (recommended)

You can run lower-level collection commands directly to implement an agent-first extraction flow:

- Run agent extraction (detect agent commits, extract fixtures, and write per-language fixture repo lists):

```bash
python -m collection.agent_corpus --language python --repos-per-language 50
```

- Optionally export human test-commit CSVs (useful as an intermediate step):

```bash
python -m collection.human_corpus --corpus-db data/corpus.db --repo-qc-dir github-search-agent --language python --test-commits-csv /path/to/out --only-write-test-commits
```

- Run human fixture extraction (the human collector will prefer the agent-produced repo lists under `github-search-agent/agent_fixtures`):

```bash
python -m collection.human_corpus --corpus-db data/corpus.db --repo-qc-dir github-search-agent --language python
```

Backwards compatibility: if the agent fixture repo lists are not present, the human collector falls back to `github-search-agent/tests_commits/*_agent_test_commit.csv` and then to `*_agent_repo_qc.csv`.

## Study Model

- unit of comparison: commit
- pairing container: repository
- primary outcome: commit-level fixture observations
- statistical framing: paired comparisons within the same repository

This is intentionally not a human-vs-agent repository split. The repository provides the matching context for the pair, not a class label for the whole dataset.

## Internal Phases

The phase scripts remain available for lower-level inspection and troubleshooting, but they are implementation details of the paired pipeline rather than the main user workflow.
