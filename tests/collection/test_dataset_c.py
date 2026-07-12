from __future__ import annotations

import csv
import sqlite3
import subprocess
from contextlib import contextmanager
from unittest.mock import patch

from collection.dataset_c import (
    _process_repo,
    _save_dataset_c_checkpoint,
    collect_dataset_c_fixtures,
    count_commits_up_to,
    find_test_files_at_commit,
    load_repo_cutoffs,
)
from collection.db import initialise_db
from collection.fixture_extractor import AgentFixtureExtractor


def _git(repo_path, *args, env=None):
    subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _make_git_repo(tmp_path, name="repo"):
    repo_path = tmp_path / name
    repo_path.mkdir()
    _git(repo_path, "init", "-b", "main")
    _git(repo_path, "config", "user.email", "test@example.com")
    _git(repo_path, "config", "user.name", "Test")
    return repo_path


def _commit(repo_path, filename, content, date, message="commit"):
    (repo_path / filename).write_text(content)
    _git(repo_path, "add", filename)
    import os

    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = date
    env["GIT_COMMITTER_DATE"] = date
    _git(repo_path, "commit", "-m", message, env=env)
    return subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_load_repo_cutoffs_reads_csv(tmp_path):
    csv_path = tmp_path / "cutoffs.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "repo_name",
                "language",
                "cutoff_commit_sha",
                "cutoff_commit_date",
                "clone_url",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "repo_name": "owner/repo1",
                    "language": "python",
                    "cutoff_commit_sha": "abc123",
                    "cutoff_commit_date": "2021-12-31",
                    "clone_url": "https://github.com/owner/repo1.git",
                },
                {
                    "repo_name": "owner/repo2",
                    "language": "java",
                    "cutoff_commit_sha": "def456",
                    "cutoff_commit_date": "2020-06-15",
                    "clone_url": "https://github.com/owner/repo2.git",
                },
            ]
        )

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

    checkpoint_path = tmp_path / "dataset_c_checkpoint_python.json"
    _save_dataset_c_checkpoint(
        checkpoint_path, {"owner/done"}, {"repos_persisted": 1, "fixtures_persisted": 1}
    )

    repos = [
        {
            "full_name": "owner/done",
            "language": "python",
            "clone_url": "https://github.com/owner/done.git",
        },
        {
            "full_name": "owner/pending",
            "language": "python",
            "clone_url": "https://github.com/owner/pending.git",
        },
    ]

    processed = []

    def fake_process(repo, cutoffs, extractor, clones_dir):
        processed.append(repo["full_name"])
        return True, []

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.persist_repository_and_fixtures"
    ) as mock_persist, patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ):
        stats, db_path = collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="python",
        )

    assert processed == ["owner/pending"]
    mock_persist.assert_not_called()


def test_collect_dataset_c_no_dedup_keeps_all_fixtures(tmp_path):
    output_db = tmp_path / "out.db"
    initialise_db(output_db)

    def fake_process(repo, cutoffs, extractor, clones_dir):
        fixture = {
            "name": "dup",
            "file_path": "t.py",
            "start_line": 1,
            "end_line": 5,
            "framework": "pytest",
        }
        return True, [
            (
                repo,
                {
                    **fixture,
                    "repo_full_name": repo["full_name"],
                    "language": repo.get("language", "unknown"),
                },
            ),
            (
                repo,
                {
                    **fixture,
                    "repo_full_name": repo["full_name"],
                    "language": repo.get("language", "unknown"),
                },
            ),
            (
                repo,
                {
                    "name": "unique",
                    "file_path": "t.py",
                    "start_line": 10,
                    "end_line": 15,
                    "framework": "pytest",
                    "repo_full_name": repo["full_name"],
                    "language": repo.get("language", "unknown"),
                },
            ),
        ]

    repos = [
        {
            "full_name": "owner/repo",
            "language": "python",
            "clone_url": "https://github.com/owner/repo.git",
        }
    ]

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ), patch("collection.dataset_c.persist_repository_and_fixtures") as mock_persist:
        stats, db_path = collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="python",
        )

    assert stats["fixtures_persisted"] == 3
    mock_persist.assert_called_once()


def test_dataset_c_checkpoint_is_language_specific(tmp_path):
    """Java checkpoint must not skip typescript repos and vice-versa."""
    output_db = tmp_path / "out.db"
    initialise_db(output_db)

    repos = [
        {
            "full_name": "owner/done-java",
            "language": "java",
            "clone_url": "https://github.com/owner/done-java.git",
        },
        {
            "full_name": "owner/done-ts",
            "language": "typescript",
            "clone_url": "https://github.com/owner/done-ts.git",
        },
        {
            "full_name": "owner/pending-java",
            "language": "java",
            "clone_url": "https://github.com/owner/pending-java.git",
        },
        {
            "full_name": "owner/pending-ts",
            "language": "typescript",
            "clone_url": "https://github.com/owner/pending-ts.git",
        },
    ]

    processed = []

    def fake_process(repo, cutoffs, extractor, clones_dir):
        processed.append(repo["full_name"])
        return True, []

    # Save language-specific checkpoints for repos that are "done"
    java_ckpt = tmp_path / "dataset_c_checkpoint_java.json"
    _save_dataset_c_checkpoint(
        java_ckpt, {"owner/done-java"}, {"repos_persisted": 1, "fixtures_persisted": 1}
    )

    ts_ckpt = tmp_path / "dataset_c_checkpoint_typescript.json"
    _save_dataset_c_checkpoint(
        ts_ckpt, {"owner/done-ts"}, {"repos_persisted": 1, "fixtures_persisted": 1}
    )

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.persist_repository_and_fixtures"
    ), patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ):
        collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="java",
        )

    assert "owner/done-java" not in processed
    assert "owner/pending-java" in processed
    assert "owner/done-ts" in processed
    assert "owner/pending-ts" in processed

    processed.clear()

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.persist_repository_and_fixtures"
    ), patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ):
        collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="typescript",
        )

    assert "owner/done-ts" not in processed
    assert "owner/pending-ts" in processed
    assert "owner/done-java" in processed
    assert "owner/pending-java" in processed


def test_load_agent_targets_from_csv_counts_fixtures(tmp_path):
    """CSV fallback should count agent fixtures per language from fixture CSVs."""
    import csv

    fixtures_dir = tmp_path / "fixtures-from-agents"
    fixtures_dir.mkdir()

    # Write minimal CSVs with varying row counts
    for lang, rows in [("python", 50), ("java", 30), ("typescript", 10)]:
        csv_path = fixtures_dir / f"{lang}_agent_fixtures.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "repo_name",
                    "language",
                    "commit_sha",
                    "agent_type",
                    "test_file_count",
                    "test_file_paths",
                ],
            )
            writer.writeheader()
            for i in range(rows):
                writer.writerow(
                    {
                        "repo_name": f"owner/repo{i}",
                        "language": lang,
                        "commit_sha": f"abc{i:03d}",
                        "agent_type": "claude",
                        "test_file_count": 1,
                        "test_file_paths": "tests/test_foo.py",
                    }
                )

    from collection.dataset_c import _load_agent_targets_from_csv

    targets = _load_agent_targets_from_csv(fixtures_dir)
    assert targets["python"] == 50
    assert targets["java"] == 30
    assert targets["typescript"] == 10


def test_load_agent_targets_from_csv_missing_dir(tmp_path):
    from collection.dataset_c import _load_agent_targets_from_csv

    targets = _load_agent_targets_from_csv(tmp_path / "nonexistent")
    assert targets == {}


def test_collect_dataset_c_empty_targets_selects_all(tmp_path):
    """When no agent targets exist in DB, all candidates should be selected."""
    output_db = tmp_path / "out.db"
    initialise_db(output_db)

    def fake_process(repo, cutoffs, extractor, clones_dir):
        return True, [
            (
                repo,
                {
                    "name": f"fixture_{i}",
                    "file_path": "t.py",
                    "start_line": i,
                    "end_line": i + 3,
                    "framework": "pytest",
                    "repo_full_name": repo["full_name"],
                    "language": repo.get("language", "unknown"),
                },
            )
            for i in range(3)
        ]

    repos = [
        {
            "full_name": "owner/repo",
            "language": "python",
            "clone_url": "https://github.com/owner/repo.git",
        }
    ]

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.persist_repository_and_fixtures"
    ), patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ):
        # Pass empty targets to simulate fresh DB
        stats, db_path = collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="python",
            targets={},
        )

    assert stats["fixtures_persisted"] == 3
    assert stats["completed_repos"] == 1


def test_dataset_c_persistence_error_logs_warning(tmp_path, caplog):
    """Persistence failures must be logged at WARNING, not DEBUG."""
    import logging

    output_db = tmp_path / "out.db"
    initialise_db(output_db)

    def fake_process(repo, cutoffs, extractor, clones_dir):
        return True, [
            (
                repo,
                {
                    "name": "f1",
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 5,
                    "framework": "pytest",
                    "repo_full_name": repo["full_name"],
                    "language": repo.get("language", "unknown"),
                },
            )
        ]

    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.persist_repository_and_fixtures",
        side_effect=RuntimeError("disk full"),
    ), patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ):
        with caplog.at_level("WARNING"):
            collect_dataset_c_fixtures(
                agent_repos=[
                    {
                        "full_name": "owner/repo",
                        "language": "python",
                        "clone_url": "https://github.com/owner/repo.git",
                    }
                ],
                clones_dir=tmp_path / "clones",
                output_db=output_db,
                workers=1,
                language="python",
            )

    assert any("Failed to persist" in record.message for record in caplog.records)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


# ---------------------------------------------------------------------------
# count_commits_up_to / _process_repo quality gates
#
# These enforce MIN_COMMITS/MIN_TEST_FILES against the repo's real state at
# its cutoff commit, not GitHub's live metadata -- see
# internal-docs/methodology-improvements/dataset-c-repo-selection.md.
# ---------------------------------------------------------------------------


def test_count_commits_up_to_counts_reachable_commits(tmp_path):
    repo_path = _make_git_repo(tmp_path)
    sha1 = _commit(repo_path, "a.txt", "1", "2016-01-01T00:00:00")
    sha2 = _commit(repo_path, "a.txt", "2", "2017-01-01T00:00:00")
    sha3 = _commit(repo_path, "a.txt", "3", "2018-01-01T00:00:00")

    assert count_commits_up_to(repo_path, sha1) == 1
    assert count_commits_up_to(repo_path, sha2) == 2
    assert count_commits_up_to(repo_path, sha3) == 3


def test_count_commits_up_to_invalid_sha_returns_zero(tmp_path):
    repo_path = _make_git_repo(tmp_path)
    _commit(repo_path, "a.txt", "1", "2016-01-01T00:00:00")
    assert count_commits_up_to(repo_path, "0" * 40) == 0


@contextmanager
def _fake_clone_at(repo_path):
    """Stand-in for clone_with_function that just yields an already-built
    local repo instead of doing a real network clone."""
    yield repo_path


def test_process_repo_rejects_below_commit_floor_at_cutoff(tmp_path):
    """A repo can have many commits in total (today) but few by the actual
    cutoff date -- this must be measured honestly, not from a live total."""
    repo_path = _make_git_repo(tmp_path)
    # Only 2 commits before the cutoff...
    _commit(repo_path, "a.txt", "1", "2018-01-01T00:00:00")
    _commit(repo_path, "a.txt", "2", "2019-01-01T00:00:00")
    # ...but 10 more after it, well within today's 2026 crawl.
    for i in range(10):
        _commit(repo_path, "a.txt", str(i), f"2022-0{(i % 9) + 1}-01T00:00:00")

    extractor = AgentFixtureExtractor(
        clones_dir=tmp_path, source_db=None, start_date="1970-01-01"
    )
    repo = {
        "full_name": "owner/repo",
        "language": "python",
        "clone_url": "https://example.com/owner/repo.git",
    }

    with patch("collection.dataset_c.MIN_COMMITS", 5), patch(
        "collection.dataset_c.clone_with_function",
        side_effect=lambda fn, url, path: _fake_clone_at(repo_path),
    ):
        success, results = _process_repo(repo, {}, extractor, tmp_path)

    assert success is True
    assert results == []


def test_process_repo_rejects_below_test_file_floor_at_cutoff(tmp_path):
    repo_path = _make_git_repo(tmp_path)
    for i in range(6):
        _commit(repo_path, f"f{i}.txt", str(i), f"2018-01-0{i + 1}T00:00:00")
    # Only one test file at the cutoff.
    (repo_path / "test_only_one.py").write_text("def test_x(): pass")
    _git(repo_path, "add", "test_only_one.py")
    import os

    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = "2018-06-01T00:00:00"
    env["GIT_COMMITTER_DATE"] = "2018-06-01T00:00:00"
    _git(repo_path, "commit", "-m", "add test file", env=env)

    extractor = AgentFixtureExtractor(
        clones_dir=tmp_path, source_db=None, start_date="1970-01-01"
    )
    repo = {
        "full_name": "owner/repo",
        "language": "python",
        "clone_url": "https://example.com/owner/repo.git",
    }

    with patch("collection.dataset_c.MIN_COMMITS", 3), patch(
        "collection.dataset_c.MIN_TEST_FILES", 5
    ), patch(
        "collection.dataset_c.clone_with_function",
        side_effect=lambda fn, url, path: _fake_clone_at(repo_path),
    ):
        success, results = _process_repo(repo, {}, extractor, tmp_path)

    assert success is True
    assert results == []


def test_process_repo_extracts_fixtures_when_both_floors_pass(tmp_path):
    repo_path = _make_git_repo(tmp_path)
    for i in range(4):
        _commit(repo_path, f"f{i}.txt", str(i), f"2018-01-0{i + 1}T00:00:00")

    (repo_path / "test_foo.py").write_text(
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def my_fixture():\n"
        "    return 1\n"
    )
    _git(repo_path, "add", "test_foo.py")
    import os

    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = "2018-06-01T00:00:00"
    env["GIT_COMMITTER_DATE"] = "2018-06-01T00:00:00"
    _git(repo_path, "commit", "-m", "add test file", env=env)

    extractor = AgentFixtureExtractor(
        clones_dir=tmp_path, source_db=None, start_date="1970-01-01"
    )
    repo = {
        "full_name": "owner/repo",
        "language": "python",
        "clone_url": "https://example.com/owner/repo.git",
    }

    with patch("collection.dataset_c.MIN_COMMITS", 3), patch(
        "collection.dataset_c.MIN_TEST_FILES", 1
    ), patch(
        "collection.dataset_c.clone_with_function",
        side_effect=lambda fn, url, path: _fake_clone_at(repo_path),
    ):
        success, results = _process_repo(repo, {}, extractor, tmp_path)

    assert success is True
    assert len(results) == 1
    _, fixture = results[0]
    assert fixture["name"] == "my_fixture"


def test_process_repo_embeds_github_id_in_fixture_dicts(tmp_path):
    """github_id is the repositories table's UNIQUE key -- it must survive
    from the input repo dict into every returned fixture dict, since the
    persist loop in collect_dataset_c_fixtures() reads it from
    fixtures_list[0], not from the original repo dict (which isn't in
    scope there). See test_collect_dataset_c_repos_with_distinct_github_ids_
    get_distinct_db_rows below for the real bug this caused."""
    repo_path = _make_git_repo(tmp_path)
    for i in range(4):
        _commit(repo_path, f"f{i}.txt", str(i), f"2018-01-0{i + 1}T00:00:00")
    (repo_path / "test_foo.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef my_fixture():\n    return 1\n"
    )
    _git(repo_path, "add", "test_foo.py")
    import os

    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = "2018-06-01T00:00:00"
    env["GIT_COMMITTER_DATE"] = "2018-06-01T00:00:00"
    _git(repo_path, "commit", "-m", "add test file", env=env)

    extractor = AgentFixtureExtractor(
        clones_dir=tmp_path, source_db=None, start_date="1970-01-01"
    )
    repo = {
        "full_name": "owner/repo",
        "language": "python",
        "clone_url": "https://example.com/owner/repo.git",
        "github_id": 987654,
    }

    with patch("collection.dataset_c.MIN_COMMITS", 3), patch(
        "collection.dataset_c.MIN_TEST_FILES", 1
    ), patch(
        "collection.dataset_c.clone_with_function",
        side_effect=lambda fn, url, path: _fake_clone_at(repo_path),
    ):
        success, results = _process_repo(repo, {}, extractor, tmp_path)

    assert success is True
    _, fixture = results[0]
    assert fixture["github_id"] == 987654


def test_collect_dataset_c_repos_with_distinct_github_ids_get_distinct_db_rows(
    tmp_path,
):
    """Regression: construct_repo_dict() defaults github_id to 0 when a
    fixture dict doesn't carry one. The repositories table's github_id
    UNIQUE constraint (ON CONFLICT(github_id) DO UPDATE) means every repo
    that defaults to 0 collides on the same row -- an entire collection
    run's repos silently collapse into one, with every fixture
    misattributed to whichever repo inserted first. This was found by a
    real end-to-end toy collection, not a unit test: every other test in
    this file mocks _process_repo, so persist_repository_and_fixtures's
    real behavior was never exercised with realistic (missing-until-now
    github_id) data. This test does NOT mock persist_repository_and_fixtures,
    specifically so it exercises the real upsert path against a real
    sqlite DB.
    """
    output_db = tmp_path / "out.db"
    initialise_db(output_db)

    def fake_process(repo, cutoffs, extractor, clones_dir):
        return True, [
            (
                repo,
                {
                    "name": f"fixture_{repo['full_name']}",
                    "file_path": "t.py",
                    "start_line": 1,
                    "end_line": 5,
                    "framework": "pytest",
                    "repo_full_name": repo["full_name"],
                    "language": repo["language"],
                    "github_id": repo["github_id"],
                },
            )
        ]

    repos = [
        {
            "full_name": "owner/repo-a",
            "language": "python",
            "clone_url": "https://example.com/owner/repo-a.git",
            "github_id": 111,
        },
        {
            "full_name": "owner/repo-b",
            "language": "python",
            "clone_url": "https://example.com/owner/repo-b.git",
            "github_id": 222,
        },
    ]

    # This test deliberately exercises the real persist_repository_and_
    # fixtures() path (see docstring), which also writes a CSV side-output
    # via human_corpus._human_fixture_csv_path() -- redirect it into
    # tmp_path via fixtures_output_dir instead of writing into the real,
    # tracked datasets/c/fixtures/ directory on every test run.
    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ):
        stats, db_path = collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="python",
            targets={},
            fixtures_output_dir=tmp_path,
        )

    assert stats["repos_persisted"] == 2
    assert stats["fixtures_persisted"] == 2

    with sqlite3.connect(output_db) as conn:
        rows = conn.execute(
            "SELECT full_name, github_id FROM repositories ORDER BY full_name"
        ).fetchall()
        assert rows == [("owner/repo-a", 111), ("owner/repo-b", 222)]

        fixture_repo_ids = conn.execute(
            "SELECT DISTINCT repo_id FROM fixtures"
        ).fetchall()
        assert len(fixture_repo_ids) == 2, (
            "both repos' fixtures must be attributed to their own repo_id, "
            "not collapsed onto a single row via a github_id collision"
        )
