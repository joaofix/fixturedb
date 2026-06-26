Purpose
-------
This file documents the `make_csv` test helper (defined in `tests/conftest.py`) used across the
test-suite to generate small, deterministic CSV fixtures at runtime. Prefer using `make_csv`
instead of committing sample CSV files into the repository.

Usage
-----
- The fixture is provided as `make_csv` in tests and returns a callable helper named `_make`.
- Signature of the returned helper:

    _make(base_dir: Path, name: str, rows: Optional[list[dict]] = None, dest_name: Optional[str] = None) -> Path

- Typical usage in a test:

    def test_example(tmp_path, make_csv):
        csv_path = make_csv(tmp_path, "python_agent_repo.csv")
        assert csv_path.exists()

- Writing custom rows:

    rows = [{"repo_name": "owner/repo", "language": "python", "stars": "10"}]
    csv_path = make_csv(tmp_path, "custom.csv", rows=rows)

- Writing to a specific destination path (subdirectory/rename):

    csv_path = make_csv(tmp_path, "python_agent_repo.csv", dest_name="input/agent_repos.csv")

Behavior details
----------------
- If `rows` is provided, those rows are written. Otherwise the helper looks up a predefined
  sample by `name` from `SAMPLE_DATA` defined in `tests/conftest.py`.
- The CSV header is derived from the keys of the first row.
- Files are written with UTF-8 encoding and newline handling suitable for CSV.

Available sample names
----------------------
The following sample names are available by default in `SAMPLE_DATA` (see `tests/conftest.py`):

- python_agent_repo.csv
- mixed_agent_repo.csv
- python_agent_repo_small.csv
- python_human_test_commit.csv
- python_agent_test_commit.csv
- python_agent_fixture_repos.csv
- python_agent_commit_qc.csv
- python_agent_test_commit_qc.csv

Adding or changing samples
-------------------------
- To change or add sample fixtures, edit the `SAMPLE_DATA` mapping in `tests/conftest.py`.
- Keep samples small and deterministic; tests should pass using only data provided in `SAMPLE_DATA`
  or explicit `rows=` passed when calling the helper.

Best practices
--------------
- Prefer `tmp_path` (or a temporary directory) as `base_dir` so tests stay hermetic.
- Avoid committing generated CSVs to the repo; use this helper for reproducible test inputs.
- If a test requires a specific CSV schema, pass a small explicit `rows=` value to make the
  test self-contained and easy to reason about.

Further notes
-------------
- The helper is intentionally simple; it does not validate column types beyond writing the
  header derived from the first row. If you need stronger validation in tests, create the CSV
  using `rows=` and assert the file contents in the test.
