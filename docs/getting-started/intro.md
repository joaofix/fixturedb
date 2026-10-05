# What is FixtureDB?

FixtureDB is the replication package for the paper *"An empirical study on
test fixture usage by coding agents on open source software"*. It collects
test fixtures from open-source repositories and compares fixtures written by
coding agents with fixtures written by humans before LLM coding tools existed.

A *test fixture* is code that prepares the state a test needs (setup) or
cleans it up afterwards (teardown).

## The two datasets

| Dataset | Who wrote the fixtures | Repositories | Time window |
|---------|------------------------|--------------|-------------|
| **A** (agent) | Coding agents (Claude, Copilot, Cursor, and others) | Repositories with an agent configuration file and at least one agent commit | Commits from 2025-01-01 on |
| **C** (human, pre-LLM) | Humans | Repositories created 2016-01-01 to 2020-12-31 | Snapshot at 2020-12-31 |

Dataset A answers "what do agents write?". Dataset C is the baseline: code
written before LLM coding tools were available.

## How we compare them

- We detect agent commits from `Co-authored-by`, `Assisted-by` and
  `Generated-by` trailers and from author names. See
  [Agent Detection](../architecture/agent-detection.md).
- We record language, domain and repository age for every repository. These
  are the control variables.
- The two datasets come from different repositories and different years, so
  the comparison is unpaired. We use Mann-Whitney U for numbers and
  chi-square for categories.

Because the two datasets come from different repositories, differences can
come from who wrote the code or from when it was written. The design cannot
separate the two. See [Limitations](../reference/limitations.md).

## Where to go next

- [Setup](setup.md): install and run a small test.
- [Repository Structure](repository-structure.md): where the code and data live.
- [Research Questions](../research-questions.md): what each question measures.
- [Reproducing the Study](../usage/reproducing.md): the full collection run.
