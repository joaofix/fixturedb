"""Dataset C failure handling: a failure must never be recorded as a finished repository.

Each test pins one of the bug classes found while fixing Dataset A:
- a failed commit count must not look like "too few commits" (permanently complete);
- a failed persist must leave the repository pending for the next run;
- a failed file extraction must be visible and leave the repository pending;
- every failed repository must be reported, not dropped silently;
- one repository's unexpected exception must not stop the whole run;
- file names that are not valid UTF-8 must still be persisted.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from collection import dataset_c
from collection.dataset_c import (
    _process_repo,
    collect_dataset_c_fixtures,
    count_commits_up_to,
)
from collection.db import initialise_db


def _fake_process_factory(outcomes):
    """Return a stand-in for _process_repo: `outcomes` maps repo name to (success, results),
    or to an exception instance to raise."""

    def _fake(repo, cutoffs, extractor, clones_dir):
        outcome = outcomes[repo["full_name"]]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return _fake


def _one_fixture(repo, file_path="tests/test_t.py"):
    return (
        repo,
        {
            "name": "f1",
            "file_path": file_path,
            "start_line": 1,
            "end_line": 5,
            "framework": "pytest",
            "repo_full_name": repo["full_name"],
            "language": repo.get("language", "python"),
        },
    )


def _run_collect(tmp_path, repos, fake, **kwargs):
    output_db = tmp_path / "out.db"
    initialise_db(output_db)
    with patch("collection.dataset_c._process_repo", side_effect=fake), patch(
        "collection.dataset_c.stratified_sample_by_language",
        side_effect=lambda c, t, seed=42: c,
    ):
        collect_dataset_c_fixtures(
            agent_repos=repos,
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=kwargs.pop("workers", 1),
            language="python",
            fixtures_output_dir=tmp_path,
            **kwargs,
        )
    return tmp_path / "dataset_c_checkpoint_python.json"


def _completed(checkpoint_path: Path) -> set[str]:
    if not checkpoint_path.exists():
        return set()
    return set(json.loads(checkpoint_path.read_text(encoding="utf-8"))["completed_repos"])


REPO = {"full_name": "owner/repo", "language": "python", "clone_url": "https://example.invalid/r.git"}


# --- 1. A failed commit count is not a zero count -------------------------------------

def test_count_commits_up_to_returns_none_when_git_fails(tmp_path):
    """A timeout or a git error is "could not count", not "zero commits"."""
    with patch(
        "collection.dataset_c.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git rev-list", timeout=60),
    ):
        assert count_commits_up_to(tmp_path, "abc123") is None


def test_count_commits_up_to_invalid_sha_is_not_zero(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert count_commits_up_to(tmp_path, "0" * 40) is None


def test_failed_commit_count_leaves_repository_pending(tmp_path, monkeypatch):
    """A repository whose commit count failed must not be recorded as "too few commits"."""
    monkeypatch.setattr(dataset_c, "MIN_COMMITS", 1)
    monkeypatch.setattr(dataset_c, "MIN_NON_BLANK_LOC", 0)
    monkeypatch.setattr(dataset_c, "MIN_TEST_FILES", 0)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_t.py").write_text("def test_t():\n    pass\n")

    @contextmanager
    def _clone(clone_fn, clone_url, target_dir):
        yield tmp_path

    with patch("collection.dataset_c.clone_with_function", _clone), patch(
        "collection.dataset_c.count_commits_up_to", return_value=None
    ), patch("collection.dataset_c.subprocess.run"):
        success, results = _process_repo(
            REPO,
            {"owner/repo": {"cutoff_commit_sha": "a" * 40, "cutoff_commit_date": "2020-01-01"}},
            object(),
            tmp_path,
        )

    assert success is False
    assert results == []


# --- 2. A failed persist must not complete the repository ------------------------------

def test_failed_persist_leaves_repository_pending_for_next_run(tmp_path):
    def _persist_fails(*args, **kwargs):
        raise RuntimeError("database is locked")

    fake = _fake_process_factory({REPO["full_name"]: (True, [_one_fixture(REPO)])})
    output_db = tmp_path / "out.db"
    initialise_db(output_db)
    with patch("collection.dataset_c._process_repo", side_effect=fake), patch(
        "collection.dataset_c.persist_repository_and_fixtures", side_effect=_persist_fails
    ), patch(
        "collection.dataset_c.stratified_sample_by_language", side_effect=lambda c, t, seed=42: c
    ):
        collect_dataset_c_fixtures(
            agent_repos=[REPO],
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="python",
            fixtures_output_dir=tmp_path,
        )

    assert REPO["full_name"] not in _completed(tmp_path / "dataset_c_checkpoint_python.json")
    progress = json.loads((tmp_path / "out_dataset_c_python_progress.json").read_text(encoding="utf-8"))
    assert progress["failed_repos"] == [REPO["full_name"]]


def test_repository_whose_persist_failed_is_retried_and_completed_next_run(tmp_path):
    calls = {"persist": 0}

    def _persist_once_fails(*args, **kwargs):
        calls["persist"] += 1
        if calls["persist"] == 1:
            raise RuntimeError("transient")
        return 1

    fake = _fake_process_factory({REPO["full_name"]: (True, [_one_fixture(REPO)])})
    output_db = tmp_path / "out.db"
    initialise_db(output_db)
    kwargs = dict(
        agent_repos=[REPO],
        clones_dir=tmp_path / "clones",
        output_db=output_db,
        workers=1,
        language="python",
        fixtures_output_dir=tmp_path,
    )
    with patch("collection.dataset_c._process_repo", side_effect=fake), patch(
        "collection.dataset_c.persist_repository_and_fixtures", side_effect=_persist_once_fails
    ), patch("collection.dataset_c.stratified_sample_by_language", side_effect=lambda c, t, seed=42: c):
        collect_dataset_c_fixtures(**kwargs)
        checkpoint = tmp_path / "dataset_c_checkpoint_python.json"
        assert REPO["full_name"] not in _completed(checkpoint)
        collect_dataset_c_fixtures(**kwargs)

    assert REPO["full_name"] in _completed(checkpoint)
    assert calls["persist"] == 2


# --- 3. A file that fails extraction must be visible and leave the repository pending ---

def test_failed_file_extraction_is_logged_and_leaves_repository_pending(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(dataset_c, "MIN_COMMITS", 0)
    monkeypatch.setattr(dataset_c, "MIN_NON_BLANK_LOC", 0)
    monkeypatch.setattr(dataset_c, "MIN_TEST_FILES", 0)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bad.py").write_text("def test_bad():\n    pass\n")

    class _ExtractorBroken:
        def _extract_from_snapshot_file(self, **kwargs):
            raise ValueError("parser exploded")

    @contextmanager
    def _clone(clone_fn, clone_url, target_dir):
        yield tmp_path

    with patch("collection.dataset_c.clone_with_function", _clone), patch(
        "collection.dataset_c.count_commits_up_to", return_value=10
    ), patch("collection.dataset_c.subprocess.run"), caplog.at_level(logging.WARNING):
        success, results = _process_repo(
            REPO,
            {"owner/repo": {"cutoff_commit_sha": "a" * 40, "cutoff_commit_date": "2020-01-01"}},
            _ExtractorBroken(),
            tmp_path,
        )

    assert success is False
    assert results == []
    assert any("test_bad.py" in r.message and r.levelno == logging.WARNING for r in caplog.records)


# --- 4. Failed repositories are reported, not dropped silently --------------------------

def test_failed_repositories_are_reported_in_the_log_and_the_progress_file(tmp_path, caplog):
    good = {"full_name": "owner/good", "language": "python", "clone_url": "https://example.invalid/g.git"}
    bad = {"full_name": "owner/bad", "language": "python", "clone_url": "https://example.invalid/b.git"}
    fake = _fake_process_factory({
        "owner/good": (True, []),
        "owner/bad": (False, []),
    })
    output_db = tmp_path / "out.db"
    initialise_db(output_db)
    with caplog.at_level(logging.WARNING), patch(
        "collection.dataset_c._process_repo", side_effect=fake
    ), patch(
        "collection.dataset_c.stratified_sample_by_language", side_effect=lambda c, t, seed=42: c
    ):
        collect_dataset_c_fixtures(
            agent_repos=[good, bad],
            clones_dir=tmp_path / "clones",
            output_db=output_db,
            workers=1,
            language="python",
            fixtures_output_dir=tmp_path,
        )

    progress = json.loads((tmp_path / "out_dataset_c_python_progress.json").read_text(encoding="utf-8"))
    assert progress["failed_repos"] == ["owner/bad"]
    assert any("owner/bad" in r.message and r.levelno == logging.WARNING for r in caplog.records)


# --- 5. One repository's unexpected exception must not stop the whole run ---------------

@pytest.mark.parametrize("workers", [1, 3])
def test_unexpected_exception_in_one_repository_does_not_stop_the_run(tmp_path, workers):
    good = {"full_name": "owner/good", "language": "python", "clone_url": "https://example.invalid/g.git"}
    boom = {"full_name": "owner/boom", "language": "python", "clone_url": "https://example.invalid/b.git"}
    fake = _fake_process_factory({
        "owner/good": (True, []),
        "owner/boom": RuntimeError("unexpected"),
    })
    checkpoint = _run_collect(tmp_path, [good, boom], fake, workers=workers)

    completed = _completed(checkpoint)
    assert "owner/good" in completed  # finished normally, with no candidates
    assert "owner/boom" not in completed  # the failure stays pending for the next run


# --- 6. File names that are not valid UTF-8 are still persisted ------------------------

def test_non_utf8_file_name_is_persisted_with_a_valid_utf8_path(tmp_path):
    raw_name = "tests/caf\udce9_test.py"  # what os.walk returns for a Latin-1 file name
    fake = _fake_process_factory({REPO["full_name"]: (True, [_one_fixture(REPO, file_path=raw_name)])})
    checkpoint = _run_collect(tmp_path, [REPO], fake)

    assert REPO["full_name"] in _completed(checkpoint)
    rows = sqlite3.connect(tmp_path / "out.db").execute("SELECT relative_path FROM test_files").fetchall()
    assert ("tests/caf\ufffd_test.py",) in rows


def test_utf8_safe_keeps_valid_names_and_replaces_undecodable_bytes():
    assert dataset_c._utf8_safe("tests/test_ok.py") == "tests/test_ok.py"
    assert dataset_c._utf8_safe("tests/caf\udce9.py") == "tests/caf�.py"


# --- 7. A language's first run must not destroy cross-language leaks an earlier
#        language's run already wrote into its CSV, in the same collection attempt ---

def test_a_later_languages_first_run_does_not_clear_an_earlier_runs_leaked_rows(tmp_path):
    """A sibling language (java) has already run in this attempt and left a real,
    leaked python row in python_fixtures.csv. python's own first run (its own checkpoint
    is still empty) must not clear that file."""
    output_db = tmp_path / "out.db"
    initialise_db(output_db)
    # java already ran in this attempt: its own checkpoint exists, and it left a
    # genuine leaked python fixture in python_fixtures.csv as a side effect.
    (tmp_path / "dataset_c_checkpoint_java.json").write_text(
        '{"completed_repos": ["owner/java-repo"], "counts": {}}', encoding="utf-8"
    )
    python_csv = tmp_path / "python_fixtures.csv"
    python_csv.write_text(
        "repo_name,language,commit_sha,file_path,fixture_name\n"
        "owner/java-repo,python,sha1,conftest.py,leaked\n",
        encoding="utf-8",
    )

    def fake_process(repo, cutoffs, extractor, clones_dir):
        return True, []

    python_repo = {"full_name": "owner/python-repo", "language": "python", "clone_url": "https://example.invalid/p.git"}
    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.persist_repository_and_fixtures"
    ), patch("collection.dataset_c.stratified_sample_by_language", side_effect=lambda c, t, seed=42: c):
        collect_dataset_c_fixtures(
            agent_repos=[python_repo], clones_dir=tmp_path / "clones", output_db=output_db,
            workers=1, language="python", fixtures_output_dir=tmp_path,
        )

    assert "leaked" in python_csv.read_text(), "python's own first run destroyed java's earlier leaked rows"


def test_the_very_first_invocation_of_a_fresh_attempt_still_clears_its_own_stale_csv(tmp_path):
    """With no Dataset C checkpoint anywhere yet, this must be a genuinely fresh attempt,
    so clearing this language's own (possibly stale, leftover) CSV is still safe."""
    output_db = tmp_path / "out.db"
    initialise_db(output_db)
    stale = tmp_path / "java_fixtures.csv"
    stale.write_text("repo_name,language\nowner/stale-old-repo,java\n", encoding="utf-8")

    def fake_process(repo, cutoffs, extractor, clones_dir):
        return True, []

    repo = {"full_name": "owner/java-repo", "language": "java", "clone_url": "https://example.invalid/j.git"}
    with patch("collection.dataset_c._process_repo", side_effect=fake_process), patch(
        "collection.dataset_c.persist_repository_and_fixtures"
    ), patch("collection.dataset_c.stratified_sample_by_language", side_effect=lambda c, t, seed=42: c):
        collect_dataset_c_fixtures(
            agent_repos=[repo], clones_dir=tmp_path / "clones", output_db=output_db,
            workers=1, language="java", fixtures_output_dir=tmp_path,
        )

    assert not stale.exists() or "stale-old-repo" not in stale.read_text()
