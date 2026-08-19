"""Real (non-mocked) tests for collection.__main__._merge_tier2_repos_into_csv.

This writer must stay in exact column-order sync with
agent_repository_counter.py's Tier-1 writer (_process_single's row +
get_adapter().append_dicts(csv_path, [row], list(row.keys()))) -- both
append to the same datasets/a/repos/{lang}_repo.csv, and append_dicts
raises ValueError on any header mismatch (see csv_adapter.py). A schema
change to one writer's row shape that isn't mirrored in the other's
_TIER2_REPO_FIELDNAMES/row dict is exactly the kind of bug that stays
invisible under mocks -- caught here once already (a `forks` column added
to the row dict but not to _TIER2_REPO_FIELDNAMES, which append_dicts's
underlying csv.DictWriter's default extrasaction='raise' would reject).
"""

from __future__ import annotations

import csv

from collection.__main__ import _merge_tier2_repos_into_csv
from collection.csv_adapter import get_adapter
from collection.db import db_session, initialise_db, upsert_repository
from collection.repository_quality_control.agent_repository_counter import (
    _process_single,
)


def test_merge_tier2_repos_into_csv_carries_forks_through(tmp_path):
    db_path = tmp_path / "corpus.db"
    initialise_db(db_path)
    with db_session(db_path) as conn:
        upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/tier2-repo",
                "language": "python",
                "stars": 50,
                "forks": 8,
                "clone_url": "https://github.com/owner/tier2-repo.git",
                "num_contributors": 3,
                "created_at": "2025-01-01T00:00:00Z",
                "pushed_at": "2025-06-01T00:00:00Z",
                "description": "",
                "topics": "[]",
                "domain": None,
                "repo_age_years": None,
            },
        )

    out_dir = tmp_path / "repos"
    count = _merge_tier2_repos_into_csv(
        db_path, [{"repo_name": "owner/tier2-repo"}], out_dir
    )

    assert count == 1
    with (out_dir / "python_repo.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["forks"] == "8"
    assert rows[0]["discovery_tier"] == "2"
    assert rows[0]["pushed_at"] == "2025-06-01T00:00:00Z"


def test_tier2_writer_schema_matches_tier1_writer(tmp_path, monkeypatch):
    """The real regression case: Tier 1 writes a row first (its own schema),
    then Tier 2 appends to the same file -- must not raise from a header
    mismatch, and both writers' columns must actually agree."""
    monkeypatch.setattr(
        "collection.repository_quality_control.agent_repository_counter.scan_cloned_repo_for_agent_configs",
        lambda repo_path: "CLAUDE.md",
    )

    from contextlib import contextmanager

    @contextmanager
    def fake_temp_clone(*args, **kwargs):
        yield tmp_path / "clone"

    monkeypatch.setattr(
        "collection.repository_quality_control.agent_repository_counter.temp_clone_commit_history",
        fake_temp_clone,
    )

    out_dir = tmp_path / "repos"
    tier1_row = _process_single(
        {"full_name": "owner/tier1-repo", "language": "python", "stars": 1, "forks": 2},
        since="2025-01-01",
    )
    get_adapter().append_dicts(
        out_dir / "python_repo.csv", [tier1_row], list(tier1_row.keys())
    )

    db_path = tmp_path / "corpus.db"
    initialise_db(db_path)
    with db_session(db_path) as conn:
        upsert_repository(
            conn,
            {
                "github_id": 2,
                "full_name": "owner/tier2-repo",
                "language": "python",
                "stars": 9,
                "forks": 4,
                "clone_url": "https://github.com/owner/tier2-repo.git",
                "num_contributors": 1,
                "created_at": "2025-01-01T00:00:00Z",
                "pushed_at": "",
                "description": "",
                "topics": "[]",
                "domain": None,
                "repo_age_years": None,
            },
        )

    # Must not raise ValueError("... already has header ...").
    count = _merge_tier2_repos_into_csv(
        db_path, [{"repo_name": "owner/tier2-repo"}], out_dir
    )
    assert count == 1

    with (out_dir / "python_repo.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert rows[0]["forks"] == "2"
    assert rows[1]["forks"] == "4"
    # Tier 1's row (via _process_single, no pushed_at in the input dict)
    # and Tier 2's row (via the DB's own pushed_at column) both carry a
    # pushed_at value under the same header position -- proves the schemas
    # didn't just avoid raising by accident.
    assert rows[0]["pushed_at"] == ""
    assert rows[1]["pushed_at"] == ""
