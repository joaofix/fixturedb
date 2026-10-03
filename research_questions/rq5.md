# RQ5 -- Agent Configuration Files

> How often do root-level agent configuration files mention test-related and fixture-related guidance?

Generated: 2026-10-03 21:04:54 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ5 definition.

Snapshot date: 2026-09-08 (same commit-pinning policy as RQ1 -- see `collection/rq5_agent_file_scan.py`'s module docstring).
Target files searched (repository root only, case-insensitive, catalog version 3): AGENTS.md, CLAUDE.md.
Repositories analyzed (commit found at/before the snapshot date, root tree/blob fetch succeeded): 24,604.
Repositories skipped (no commit at/before the snapshot date, or a fetch failed): 73.
Every statistic below is at the repository level -- a repo counts as having test (or fixture) guidance if ANY of its root agent files matches >=1 test (or fixture) keyword. The denominator throughout is "repositories with >=1 root agent file", not "repositories analyzed" (most analyzed repos have none).

**Inclusive vs. unambiguous fixture guidance:** "fixture"/"fixtures" are kept in the catalog (dropping them would also lose every real fixture-as-code match), but manual sampling of real matches found they are majority fixture-as-test-data-file (e.g. `tests/fixtures/*.json`), not fixture-as-code (e.g. `@pytest.fixture`) -- a sense outside this study's scope. "Inclusive" below counts a repo if ANY fixture keyword matches (what every prior RQ5 report showed); "unambiguous" additionally requires >=1 match from a keyword other than "fixture"/"fixtures" (`conftest`, `beforeEach`/`afterEach`/`beforeAll`/`afterAll`, `test setup`, `setup and teardown`) -- a stricter floor, not a replacement metric.

## Overall

| Metric | Value |
|---|---|
| Repositories with >=1 root agent file | 4,763 |
| ... with >=1 test keyword | 4,172 (87.6%) |
| ... with >=1 fixture keyword (inclusive) | 1,028 (21.6%) |
| ... with >=1 *unambiguous* fixture keyword | 352 (7.4%) |
| Test-guidance repos that also have fixture guidance | 1,025 (24.6%) |

## By repository language

| Language | Repositories with >=1 agent file | Test keyword (%) | Fixture keyword, inclusive (%) | Fixture keyword, unambiguous (%) |
|---|---|---|---|---|
| Python | 1,511 | 89.2% | 25.4% | 11.8% |
| Java | 475 | 88.0% | 14.5% | 2.7% |
| JavaScript | 463 | 83.8% | 21.4% | 4.8% |
| TypeScript | 2,314 | 87.2% | 20.6% | 6.0% |

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
| conftest | 169 |
| beforeEach | 79 |
| test setup | 75 |
| afterEach | 48 |
| beforeAll | 24 |
| afterAll | 20 |
| setup and teardown | 4 |

## Keyword lists used (catalog version 3, `collection/heuristics/rq5_agent_file_keywords.yaml`)

- Test keywords: test, tests, testing, unit test, integration test, functional test, acceptance test, end-to-end test, e2e test, test suite, test case, test file, pytest, unittest, jest, vitest, mocha, jasmine, junit, testng
- Fixture keywords: fixture, fixtures, conftest, test setup, setup and teardown, beforeEach, afterEach, beforeAll, afterAll
