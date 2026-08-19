"""Tests for agent_corpus.py's _load_qc_repo_rows() -- the CSV-to-repo-dict
step between `datasets/a/repos/{lang}_repo.csv` (written by
agent_repository_counter.py / __main__.py's Tier-2 merge) and the fields
`collect_agent_fixtures()` ultimately passes to `construct_repo_dict()`.

No existing test exercised this function directly before -- every test of
`AgentCorpusCollector.run()` mocks the repo-loading step entirely, so a
column silently dropped between the CSV and `build_repo_row()`'s call site
(exactly what happened to pushed_at) stayed invisible. See
internal-docs/methodology-improvements/dataset-c-repo-selection.md's
section 11 (the same class of bug, first found in Dataset C's own
pipeline) and its Dataset A counterpart section.
"""

from __future__ import annotations

import csv
from pathlib import Path

from collection.agent_corpus import _load_qc_repo_rows


def _write_repo_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_load_qc_repo_rows_carries_pushed_at_through(tmp_path):
    repo_qc_dir = tmp_path / "repos"
    _write_repo_csv(
        repo_qc_dir / "python_repo.csv",
        [
            {
                "repo_name": "owner/repo",
                "has_agent_config": "1",
                "language": "python",
                "stars": "10",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": "2",
                "forks": "1",
                "created_at": "2025-01-01",
                "pushed_at": "2025-06-01T00:00:00Z",
                "topics": "[]",
            }
        ],
    )

    rows = _load_qc_repo_rows(repo_qc_dir, language="python")

    assert len(rows) == 1
    assert rows[0]["pushed_at"] == "2025-06-01T00:00:00Z"


def test_load_qc_repo_rows_missing_pushed_at_column_defaults_to_empty_string(tmp_path):
    """A CSV written before this fix (no pushed_at column at all) must
    still load cleanly -- pushed_at just comes back empty, not KeyError."""
    repo_qc_dir = tmp_path / "repos"
    _write_repo_csv(
        repo_qc_dir / "python_repo.csv",
        [
            {
                "repo_name": "owner/repo",
                "has_agent_config": "1",
                "language": "python",
                "stars": "10",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": "2",
                "forks": "1",
                "created_at": "2025-01-01",
                "topics": "[]",
            }
        ],
    )

    rows = _load_qc_repo_rows(repo_qc_dir, language="python")

    assert len(rows) == 1
    assert rows[0]["pushed_at"] == ""
