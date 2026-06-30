from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from collection.db import initialise_db
from collection.dataset_c import (
    _load_dataset_c_checkpoint,
    _save_dataset_c_checkpoint,
    collect_dataset_c_fixtures,
    find_test_files_at_commit,
    load_repo_cutoffs,
)


def test_load_repo_cutoffs_reads_csv(tmp_path):
    csv_path = tmp_path / "cutoffs.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["repo_name", "language", "cutoff_commit_sha", "cutoff_commit_date", "clone_url"])
        writer.writeheader()
        writer.writerows([
            {"repo_name": "owner/repo1", "language": "python", "cutoff_commit_sha": "abc123", "cutoff_commit_date": "2021-12-31", "clone_url": "https://github.com/owner/repo1.git"},
            {"repo_name": "owner/repo2", "language": "java", "cutoff_commit_sha": "def456", "cutoff_commit_date": "2020-06-15", "clone_url": "https://github.com/owner/repo2.git"},
        ])

    cutoffs = load_repo_cutoffs(csv_path)
    assert len(cutoffs) == 2
    assert cutoffs["owner/repo1"]["language"] == "python"
    assert cutoffs["owner/repo1"]["cutoff_commit_sha"] == "abc123"
    assert cutoffs["owner/repo2"]["cutoff_commit_date"] == "2020-06-15"


def test_load_repo_cutoffs_missing_file(tmp_path):
    cutoffs = load_repo_cutoffs(tmp_path / "nonexistent.csv")
    assert cutoffs == {}


def test_find_test_files_at_commit_filters_by_language(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    (repo / "tests" / "test_foo.py").write_text("def test_foo(): pass")
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello')")

    files = find_test_files_at_commit(repo, language="python")
    assert any("test_foo.py" in f for f in files)
    assert not any("main.py" in f for f in files)


def test_dataset_c_snapshot_extraction_tags_human_pre2022(tmp_path):
    """Verify _extract_from_snapshot_file tags fixtures correctly."""
    from collection.fixture_extractor import AgentFixtureExtractor

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "tests").mkdir()
    test_file = repo_path / "tests" / "test_foo.py"
    test_file.write_text("""
import pytest

@pytest.fixture
def my_fixture():
    return 42

def test_something(my_fixture):
    assert my_fixture == 42
""")

    extractor = AgentFixtureExtractor(
        clones_dir=tmp_path / "clones",
        source_db=tmp_path / "dummy.db",
        start_date="1970-01-01",
    )

    fixtures = extractor._extract_from_snapshot_file(
        repo_path=repo_path,
        file_path="tests/test_foo.py",
        language="python",
        cutoff_commit_sha="abc123",
        cutoff_commit_date="2021-12-31",
    )

    assert len(fixtures) == 1
    f = fixtures[0]
    assert f["agent_type"] == "human_pre2022"
    assert f["commit_sha"] == "abc123"
    assert f["commit_date"] == "2021-12-31"
    assert f["name"] == "my_fixture"
    assert f["file_path"] == "tests/test_foo.py"


def test_collect_dataset_c_respects_checkpoint(tmp_path):
    output_db = tmp_path / "out.db"
    initialise_db(output_db)

    checkpoint_path = tmp_path / "dataset_c_checkpoint.json"
    _save_dataset_c_checkpoint(checkpoint_path, {"owner/done"}, {"repos_persisted": 1, "fixtures_persisted": 1})

    repos = [
        {"full_name": "owner/done", "language": "python", "clone_url": "https://github.com/owner/done.git"},
        {"full_name": "owner/pending", "language": "python", "clone_url": "https://github.com/owner/pending.git"},
    ]

    processed = []

    def fake_process(repo, cutoffs, extractor, clones_dir):
        processed.append(repo["full_name"])
        return True, []

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), \
         patch("collection.dataset_c.persist_repository_and_fixtures") as mock_persist, \
         patch("collection.dataset_c.stratified_sample_by_language", side_effect=lambda c, t, seed=42: c):
        stats, db_path = collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
        )

    assert processed == ["owner/pending"]
    mock_persist.assert_not_called()


def test_collect_dataset_c_no_dedup_keeps_all_fixtures(tmp_path):
    output_db = tmp_path / "out.db"
    initialise_db(output_db)

    def fake_process(repo, cutoffs, extractor, clones_dir):
        fixture = {"name": "dup", "file_path": "t.py", "start_line": 1, "end_line": 5, "framework": "pytest"}
        return True, [
            (repo, {**fixture, "repo_full_name": repo["full_name"], "language": repo.get("language", "unknown")}),
            (repo, {**fixture, "repo_full_name": repo["full_name"], "language": repo.get("language", "unknown")}),
            (repo, {"name": "unique", "file_path": "t.py", "start_line": 10, "end_line": 15, "framework": "pytest", "repo_full_name": repo["full_name"], "language": repo.get("language", "unknown")}),
        ]

    repos = [{"full_name": "owner/repo", "language": "python", "clone_url": "https://github.com/owner/repo.git"}]

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), \
         patch("collection.dataset_c.stratified_sample_by_language", side_effect=lambda c, t, seed=42: c), \
         patch("collection.dataset_c.persist_repository_and_fixtures") as mock_persist:
        stats, db_path = collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
        )

    assert stats["fixtures_persisted"] == 3
    mock_persist.assert_called_once()
