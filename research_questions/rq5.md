# RQ5 -- Agent Configuration Files

> How often do root-level agent configuration files mention test-related and fixture-related guidance?

Generated: 2026-10-03 20:11:00 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ5 definition.

Snapshot date: 2026-09-08 (same commit-pinning policy as RQ1 -- see `collection/rq5_agent_file_scan.py`'s module docstring).
Target files searched (repository root only, case-insensitive, catalog version 1): AGENTS.md, CLAUDE.md.
Repositories analyzed (commit found at/before the snapshot date, root tree/blob fetch succeeded): 24,604.
Repositories skipped (no commit at/before the snapshot date, or a fetch failed): 73.
Every statistic below is at the repository level -- a repo counts as having test (or fixture) guidance if ANY of its root agent files matches >=1 test (or fixture) keyword. The denominator throughout is "repositories with >=1 root agent file", not "repositories analyzed" (most analyzed repos have none).

## Overall

| Metric | Value |
|---|---|
| Repositories with >=1 root agent file | 4,763 |
| ... with >=1 test keyword | 4,172 (87.6%) |
| ... with >=1 fixture keyword | 1,201 (25.2%) |
| Test-guidance repos that also have fixture guidance | 1,192 (28.6%) |

## By repository language

| Language | Repositories with >=1 agent file | Test keyword (%) | Fixture keyword (%) |
|---|---|---|---|
| Python | 1,511 | 89.2% | 28.9% |
| Java | 475 | 88.0% | 17.9% |
| JavaScript | 463 | 83.8% | 25.1% |
| TypeScript | 2,314 | 87.2% | 24.4% |

## Keyword frequency -- test keywords

| Test keyword | Repositories containing it |
|---|---|
| test | 3,851 |
| tests | 3,593 |
| testing | 2,562 |
| pytest | 1,034 |
| vitest | 931 |
| test file | 638 |
| test suite | 638 |
| unit test | 387 |
| jest | 370 |
| junit | 200 |
| integration test | 172 |
| unittest | 132 |
| test case | 131 |
| mocha | 108 |
| e2e test | 105 |
| jasmine | 26 |
| end-to-end test | 21 |
| testng | 17 |
| acceptance test | 11 |
| functional test | 9 |

## Keyword frequency -- fixture keywords

| Fixture keyword | Repositories containing it |
|---|---|
| fixtures | 711 |
| fixture | 421 |
| after each | 170 |
| conftest | 169 |
| before each | 142 |
| teardown | 128 |
| beforeEach | 79 |
| test setup | 75 |
| after all | 55 |
| afterEach | 48 |
| before all | 31 |
| beforeAll | 24 |
| afterAll | 20 |
| setup and teardown | 4 |

## Keyword lists used (catalog version 1, `collection/heuristics/rq5_agent_file_keywords.yaml`)

- Test keywords: test, tests, testing, unit test, integration test, functional test, acceptance test, end-to-end test, e2e test, test suite, test case, test file, pytest, unittest, jest, vitest, mocha, jasmine, junit, testng
- Fixture keywords: fixture, fixtures, conftest, teardown, test setup, setup and teardown, before each, after each, before all, after all, beforeEach, afterEach, beforeAll, afterAll
