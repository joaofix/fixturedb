# Agent detection

This page explains how a commit is marked as written by a coding agent. It
covers only who authored a commit. Fixture detection is on
[its own page](detection.md).

## Which repositories are checked

A repository is agent-enabled when two things hold:

1. Its tree has a file or folder from the agent catalog, such as `AGENTS.md`,
   `CLAUDE.md`, `.cursor/` or `.github/instructions/`.
2. It has at least one agent commit after 2025-01-01.

The file catalog is in
[`agent_files.csv`](../../collection/heuristics/agent-mining/agent_files.csv).
The paper uses the full catalog. The check runs in
`collection/agent_patterns.py`.

## How a commit is classified

The checks run in this order. The first match decides:

1. **Bot.** If the author name or email matches the bot list
   ([`bots.csv`](../../collection/heuristics/agent-mining/bots.csv)), the commit
   is a bot commit. Trailers are not checked. A bot is never counted as an agent.
2. **Trailers.** The commit message is scanned for `Co-authored-by`,
   `Assisted-by` and `Generated-by` lines. Matching ignores case, and
   `Co-authored-by` also matches without the hyphen. A line that names an agent
   counts as agent work.
3. **Author.** The author name and email are compared with the author catalog
   ([`agent_authors.csv`](../../collection/heuristics/agent-mining/agent_authors.csv)).

Matching uses whole words. `cline` does not match inside `McLine`.

Merge commits are excluded everywhere.

The code is in `Tier1RepositoryScanner._detect_agent_in_commit()`
(`collection/tiered_agent_corpus_scanner.py`).

## Why only these signals

The study favours precision. A human commit wrongly marked as agent work hurts
the results more than a missed agent commit. Trailers and author names are
explicit. Free-text commit messages are not scanned. A message such as
"Revert a bad Claude suggestion" is not agent work.

As a result, an agent that adds no trailer and uses a neutral author name is
counted as human. The agent counts are lower bounds.

## Known problems

**Common names.** Some agent names are also real names or common words. An
author named "Claude Smith" would match `claude` on the name check alone. We
accept this. Keep an eye on it in manual review.

**Removed names.** The bare patterns `devin` and `cline` were removed from the
author catalog. They matched real people, including employees of the Cline
company. The bot identity `devin-ai-integration` is kept.

**`CURSOR.md`.** The upstream catalog has a `CURSOR.md` entry. It was removed
because Cursor does not use that file name, and the entry matched unrelated
files.

**Narrow bot list.** The bot list is short. Bots with unusual names are not
excluded.

## Date cutoff

Only commits from 2025-01-01 on count for Dataset A. This is the start of the
agent window.

## Catalog files

| File | Contents |
|------|----------|
| [`agent_files.csv`](../../collection/heuristics/agent-mining/agent_files.csv) | Config file and folder patterns |
| [`agent_authors.csv`](../../collection/heuristics/agent-mining/agent_authors.csv) | Author names and trailer names |
| [`bots.csv`](../../collection/heuristics/agent-mining/bots.csv) | Bot account patterns |
| [`known_human_collisions.csv`](../../collection/heuristics/agent-mining/known_human_collisions.csv) | Real people whose names match an agent pattern |

The first rows of each file come from
[labri-progress/agent-mining](https://github.com/labri-progress/agent-mining).
Project additions come after a `#` line. Each file's header says how the
additions were checked.

## Reproducibility

The result depends only on the commit data and the catalog. The same commit and
the same catalog give the same classification. New commits in a repository can
change the result on a rerun.

## Tests

The tests for this page are in `tests/test_agent_detector_pure.py` and
`tests/collection/test_agent_patterns_*.py`.
