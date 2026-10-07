# RQ5 -- Agent Configuration Files

> How often do root-level agent configuration files mention test-related and fixture-related guidance, for the repositories that contribute a fixture to Dataset A?

Generated: 2026-10-07 20:49:12 UTC

Snapshot date: 2026-10-06 (each repository's root files are read at its last commit on or before this date).
Keyword catalog: `collection/heuristics/rq5_agent_file_keywords.yaml`.
Target files (repository root only, case-insensitive): AGENTS.md, CLAUDE.md.
Repositories skipped (no commit at or before the snapshot, or a failed fetch): 0 of 2,169.

## Overall

| # | Statistic | Count | Percentage | Denominator |
|---|---|---|---|---|
| 1 | Repositories in the corpus | 2,169 | -- | -- |
| 1 | Repositories analyzed | 2,169 | 100.0% | corpus |
| 2 | With a root agent file (AGENTS.md or CLAUDE.md) | 1,845 | 85.1% | analyzed |
| 3 | With a test keyword (`test_keywords`) | 1,695 | 91.9% | with agent file |
| 4 | With an Ardic test term (`ardic_test_keywords`) | 1,692 | 91.7% | with agent file |
| 5 | With a fixture keyword match (`fixture_keywords`) | 510 | 27.6% | with agent file |

## By language

| Language | Analyzed | With agent file (% of analyzed) | Test keyword (% of with agent file) | Ardic test term (%) | Fixture keyword match (%) |
|---|---|---|---|---|---|
| Python | 812 | 671 (82.6%) | 92.7% | 92.4% | 29.5% |
| Java | 177 | 152 (85.9%) | 93.4% | 93.4% | 19.7% |
| JavaScript | 207 | 175 (84.5%) | 93.7% | 93.7% | 26.9% |
| TypeScript | 973 | 847 (87.1%) | 90.6% | 90.4% | 27.7% |

## Fixture terms

Repositories with at least one root agent file that contain each term.

| Fixture term | Repositories containing it |
|---|---|
| fixture | 220 |
| fixtures | 350 |
| conftest | 86 |
| test setup | 38 |
| setup and teardown | 2 |
| beforeEach | 40 |
| afterEach | 23 |
| beforeAll | 14 |
| afterAll | 9 |

## Fixture matches in fenced code blocks

Counted per match (one line of a root agent file matching a term), not per repository.

| Fixture term | Fixture matches | In a fenced code block | Percentage |
|---|---|---|---|
| fixture | 486 | 34 | 7.0% |
| fixtures | 759 | 62 | 8.2% |
| conftest | 136 | 11 | 8.1% |
| test setup | 44 | 5 | 11.4% |
| setup and teardown | 2 | 0 | 0.0% |
| beforeEach | 54 | 17 | 31.5% |
| afterEach | 27 | 4 | 14.8% |
| beforeAll | 28 | 6 | 21.4% |
| afterAll | 17 | 5 | 29.4% |
| All terms | 1,553 | 144 | 9.3% |

## Skipped repositories

No repositories were skipped.

## Keyword lists

- Test keywords: test, tests, testing, tested, unit test, integration test, functional test, acceptance test, end-to-end test, e2e test, test suite, test case, test file, pytest, unittest, jest, vitest, mocha, jasmine, junit, testng
- Ardic test terms (the keyword set of Ardic et al., SCAM 2026): test, tests, testing, tested
- Fixture keywords: fixture, fixtures, conftest, test setup, setup and teardown, beforeEach, afterEach, beforeAll, afterAll

Matching is case-insensitive and whole-word.
`test_keywords` match 3 repositories that `ardic_test_keywords` do not.
