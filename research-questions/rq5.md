# RQ5 -- Agent Configuration Files

> How often do root-level agent configuration files mention test-related and fixture-related guidance, for the repositories that contribute a fixture to Dataset A?

Generated: 2026-10-06 20:37:15 UTC

Snapshot date: 2026-09-27 (each repository's root files are read at its last commit on or before this date).
Keyword catalog: `collection/heuristics/rq5_agent_file_keywords.yaml`.
Target files (repository root only, case-insensitive): AGENTS.md, CLAUDE.md.
Repositories skipped (no commit at or before the snapshot, or a failed fetch): 4 of 1,687.

## Overall

| # | Statistic | Count | Percentage | Denominator |
|---|---|---|---|---|
| 1 | Repositories in the corpus | 1,687 | -- | -- |
| 1 | Repositories analyzed | 1,683 | 99.8% | corpus |
| 2 | With a root agent file (AGENTS.md or CLAUDE.md) | 1,443 | 85.7% | analyzed |
| 3 | With a test keyword (`test_keywords`) | 1,333 | 92.4% | with agent file |
| 4 | With an Ardic test term (`ardic_test_keywords`) | 1,332 | 92.3% | with agent file |
| 5 | With a fixture keyword match (`fixture_keywords`) | 398 | 27.6% | with agent file |

## By language

| Language | Analyzed | With agent file (% of analyzed) | Test keyword (% of with agent file) | Ardic test term (%) | Fixture keyword match (%) |
|---|---|---|---|---|---|
| Python | 641 | 539 (84.1%) | 93.5% | 93.5% | 28.8% |
| Java | 127 | 106 (83.5%) | 96.2% | 96.2% | 16.0% |
| JavaScript | 140 | 124 (88.6%) | 91.9% | 91.9% | 28.2% |
| TypeScript | 775 | 674 (87.0%) | 90.9% | 90.8% | 28.3% |

## Fixture terms

Repositories with at least one root agent file that contain each term.

| Fixture term | Repositories containing it |
|---|---|
| fixture | 172 |
| fixtures | 266 |
| conftest | 67 |
| test setup | 33 |
| setup and teardown | 1 |
| beforeEach | 36 |
| afterEach | 17 |
| beforeAll | 13 |
| afterAll | 8 |

## Fixture matches in fenced code blocks

Counted per match (one line of a root agent file matching a term), not per repository.

| Fixture term | Fixture matches | In a fenced code block | Percentage |
|---|---|---|---|
| fixture | 396 | 32 | 8.1% |
| fixtures | 602 | 57 | 9.5% |
| conftest | 113 | 7 | 6.2% |
| test setup | 37 | 4 | 10.8% |
| setup and teardown | 1 | 0 | 0.0% |
| beforeEach | 53 | 17 | 32.1% |
| afterEach | 24 | 4 | 16.7% |
| beforeAll | 25 | 6 | 24.0% |
| afterAll | 14 | 5 | 35.7% |
| All terms | 1,265 | 132 | 10.4% |

## Skipped repositories

| Reason | Repositories |
|---|---|
| no_commit_at_or_before_cutoff | 4 |

## Keyword lists

- Test keywords: test, tests, testing, tested, unit test, integration test, functional test, acceptance test, end-to-end test, e2e test, test suite, test case, test file, pytest, unittest, jest, vitest, mocha, jasmine, junit, testng
- Ardic test terms (the keyword set of Ardic et al., SCAM 2026): test, tests, testing, tested
- Fixture keywords: fixture, fixtures, conftest, test setup, setup and teardown, beforeEach, afterEach, beforeAll, afterAll

Matching is case-insensitive and whole-word.
`test_keywords` match 1 repository that `ardic_test_keywords` do not.
