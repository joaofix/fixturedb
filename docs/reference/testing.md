# Testing

The test suite is in `tests/`. It runs with pytest and needs no GitHub token.

## Run the tests

```bash
pytest tests/                                      # everything
pytest tests/collection/test_extractor_unit/ -v    # one folder
pytest tests/ -k python                            # by name
pytest tests/ --cov=collection --cov-report=html   # coverage
```

The suite takes about a minute. Run it before every commit.

## What is covered

| Area | Where |
|------|-------|
| Fixture detection, per language | `tests/collection/test_extractor_unit/` |
| Fixture metrics and roles | `tests/collection/test_extractor_metadata/` |
| Edge cases | `tests/collection/test_extractor_edge_cases/` |
| Mock detection | `tests/collection/test_mock_detection/` |
| Realistic multi-language code | `tests/collection/test_integration/` |
| Agent detection | `tests/test_agent_detector_pure.py`, `tests/collection/test_agent_*.py` |
| Dataset A and C collectors | `tests/between_group/`, `tests/collection/test_dataset_c.py` |
| CLI | `tests/collection/test_main_cli.py` |
| Research-question reports | `tests/collection/test_rq*.py` |

Catalog tests run every entry of the YAML catalogs through the detector. Adding
an entry to a catalog adds a test.

## Test helpers

`tests/conftest.py` provides helpers for detector tests:

```python
fixture = assert_fixture_detected(code, "python", "setUp")
assert fixture.fixture_type == "unittest_setup"
assert_loc(fixture, 1)
```

Other helpers: `extract_and_find_fixtures`, `assert_fixture_not_detected`,
`assert_fixture_count`, `assert_line_range`, `assert_fixture_metrics`.

## Guards

Two guards run in every test.

- Tests cannot write CSV output into `datasets/`. The guard is in
  `tests/conftest.py`. A test that tries fails, and pytest shows its name.
- `pytest` ignores the `clones/` folder. It holds external repositories with
  their own tests.

## Adding a test

Put the file in the folder that matches its subject. Use a relative import for
the helpers:

```python
from ..conftest import assert_fixture_detected
```

A bug fix needs a test that fails before the fix and passes after it.
