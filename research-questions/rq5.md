# RQ5 -- Agent Configuration Files

> How often do agent configuration files mention test-related and fixture-related guidance, for the repositories that contribute a fixture to Dataset A?

Generated: 2026-10-27 03:45:22 UTC

Snapshot date: 2026-10-06 (each repository's files are read at its last commit on or before this date).
Keyword catalog: `collection/heuristics/rq5_agent_file_keywords.yaml`.
File names: `collection/heuristics/rq5_agent_guidance_files.yaml`.
Guidance files: a file named AGENTS.md, CLAUDE.md, GEMINI.md (case-insensitive) at the root or in any subdirectory; references between files are not followed. Files under these directories are not read: .git, node_modules, vendor, venv, .venv, build, dist, target, .tox, __pycache__, .mypy_cache, .pytest_cache.
Repositories skipped (no commit at or before the snapshot, or a failed fetch): 0 of 2,167.

## Overall

| # | Statistic | Repositories | % | Denominator |
|---|---|---|---|---|
| 1 | Repositories in the corpus | 2,167 | -- | -- |
| 1 | Repositories analyzed | 2,167 | 100.0% | corpus |
| 2 | With a guidance file | 1,976 | 91.2% | analyzed |
| 2a | -- with a guidance file at the root | 1,845 | 93.4% | with guidance file |
| 3 | With a test keyword (`ardic_test_keywords`) | 1,821 | 92.2% | with guidance file |
| 4 | With a fixture keyword match (`fixture_keywords`) | 678 | 34.3% | with guidance file |

## By language

Shares of repositories with a guidance file.

| Language | Analyzed | With guidance file (% of analyzed) | Test keyword (%) | Fixture keyword match (%) |
|---|---|---|---|---|
| Python | 812 | 724 (89.2%) | 92.1% | 35.8% |
| Java | 175 | 157 (89.7%) | 92.4% | 29.3% |
| JavaScript | 207 | 193 (93.2%) | 94.3% | 35.8% |
| TypeScript | 973 | 902 (92.7%) | 91.7% | 33.7% |

## Guidance files

| Statistic | Count |
|---|---|
| Repositories with a guidance file at the root | 1,845 |
| Repositories with a guidance file in a subdirectory | 771 |
| Repositories with guidance files in subdirectories only | 131 |
| Guidance files in subdirectories | 4,881 |
| Repositories whose fixture match is only in subdirectory files | 165 |
| Guidance files read through a symbolic link | 12 |
| Repositories whose file list was fetched in parts (GitHub truncated it) | 8 |

A symbolic link whose target is another guidance file already read is not counted again.

### Guidance files per file name

| File name | Files | Repositories | At the root | Nested |
|---|---|---|---|---|
| AGENTS.md | 4,619 | 1,515 | 1,383 | 3,236 |
| CLAUDE.md | 2,572 | 1,207 | 1,067 | 1,505 |
| GEMINI.md | 184 | 94 | 44 | 140 |

## Fixture terms

Repositories whose guidance files contain each term.

| Fixture term | Repositories |
|---|---|
| fixture | 348 |
| fixtures | 491 |
| conftest | 127 |
| test setup | 60 |
| setup and teardown | 3 |
| beforeEach | 74 |
| afterEach | 44 |
| beforeAll | 32 |
| afterAll | 22 |

## Fixture matches in fenced code blocks

Counted per match (one line of a file matching a term), not per repository.

| Fixture term | Matches | In a fenced code block | % |
|---|---|---|---|
| fixture | 1,239 | 114 | 9.2% |
| fixtures | 1,688 | 146 | 8.6% |
| conftest | 307 | 21 | 6.8% |
| test setup | 87 | 9 | 10.3% |
| setup and teardown | 3 | 1 | 33.3% |
| beforeEach | 138 | 51 | 37.0% |
| afterEach | 63 | 11 | 17.5% |
| beforeAll | 68 | 21 | 30.9% |
| afterAll | 39 | 15 | 38.5% |
| All terms | 3,632 | 389 | 10.7% |

## Skipped repositories

No repositories were skipped.

## Keyword lists

- Test keywords (the keyword set of Ardic et al., SCAM 2026): test, tests, testing, tested
- Fixture keywords: fixture, fixtures, conftest, test setup, setup and teardown, beforeEach, afterEach, beforeAll, afterAll

Matching is case-insensitive and whole-word.
