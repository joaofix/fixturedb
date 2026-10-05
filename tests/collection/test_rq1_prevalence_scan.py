"""Tests for collection/rq1_prevalence_scan.py.

This scan runs exactly once over ~24.7k repos -- there's no "redo it
tomorrow" if the counting logic is wrong. So every piece of real business
logic here (universe loading + dedup, per-repo counting, cutoff pinning,
DB upsert/resume, CSV output) is exercised directly, with no real cloning
or network access anywhere in this file: `scan_working_tree()` is pure
filesystem logic (no git at all), and `process_repo()`'s clone step is
mocked out to hand back a real local git repo built in `tmp_path`, the
same pattern `tests/collection/test_dataset_c.py` uses for `_process_repo()`.
"""

from __future__ import annotations

import base64
import csv
import gzip
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from collection import rq1_prevalence_scan as rq1scan
from collection.dataset_c import find_cutoff_commit
from collection.rq1_prevalence_scan import (
    REPAIRABLE_ERROR_REASONS,
    RQ1_LANGUAGES,
    _clone_with_shallow_fallback,
    _full_clone_with_timeout,
    _notify,
    _resolve_cutoff_commit,
    _result_row,
    initialise_rq1_db,
    load_duplicate_repo_names,
    load_raw_universe,
    load_repos_needing_retry,
    load_scanned_repo_names,
    main,
    persist_result,
    process_repo,
    retry_failed_repos,
    run_scan,
    scan_working_tree,
    write_csv_outputs,
)

PYTEST_SETUP_ONLY = """
import pytest

@pytest.fixture
def setup_fixture():
    return 1
"""

PYTEST_TEARDOWN_ONLY = """
import pytest

@pytest.fixture
def cleanup_fixture():
    yield
    do_cleanup()
"""

PYTEST_SETUP_AND_TEARDOWN = """
import pytest

@pytest.fixture
def db_conn():
    conn = connect()
    yield conn
    conn.close()
"""

JS_BEFORE_EACH = """
beforeEach(() => {
    setupThing();
});
"""

JS_AFTER_EACH = """
afterEach(() => {
    teardownThing();
});
"""

JAVA_BEFORE_EACH = """
import org.junit.jupiter.api.BeforeEach;

public class TestExample {
    @BeforeEach
    void setUp() {
        service = new UserService();
    }
}
"""


def _write_gz_csv(path, rows, fieldnames):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestLoadDuplicateRepoNames:
    def test_reads_repo_to_remove_column(self, tmp_path):
        path = tmp_path / "dups.csv"
        path.write_text("repo_to_remove,repo_to_keep\nfoo/bar,foo/baz\n")
        assert load_duplicate_repo_names(path) == {"foo/bar"}

    def test_missing_file_returns_empty_set(self, tmp_path):
        assert load_duplicate_repo_names(tmp_path / "missing.csv") == set()

    def test_strips_whitespace_and_skips_blank(self, tmp_path):
        path = tmp_path / "dups.csv"
        path.write_text("repo_to_remove,repo_to_keep\n  foo/bar  ,foo/baz\n,ignored\n")
        assert load_duplicate_repo_names(path) == {"foo/bar"}


class TestLoadRawUniverse:
    def test_mainlanguage_precedence_over_file_bucket(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_gz_csv(
            raw_dir / "python.csv.gz",
            [{"name": "org/py-repo", "mainLanguage": "Python"}],
            ["name", "mainLanguage"],
        )
        repos = load_raw_universe(raw_dir, tmp_path / "missing_dups.csv")
        assert repos == [
            {
                "repo_name": "org/py-repo",
                "language": "python",
                "clone_url": "https://github.com/org/py-repo.git",
            }
        ]

    def test_blank_mainlanguage_falls_back_to_file_bucket(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_gz_csv(
            raw_dir / "java.csv.gz",
            [{"name": "org/java-repo", "mainLanguage": ""}],
            ["name", "mainLanguage"],
        )
        repos = load_raw_universe(raw_dir, tmp_path / "missing_dups.csv")
        assert repos[0]["language"] == "java"

    def test_skips_rows_with_no_name_or_no_slash(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_gz_csv(
            raw_dir / "python.csv.gz",
            [
                {"name": "", "mainLanguage": "Python"},
                {"name": "no-slash", "mainLanguage": "Python"},
            ],
            ["name", "mainLanguage"],
        )
        assert load_raw_universe(raw_dir, tmp_path / "missing_dups.csv") == []

    def test_excludes_known_duplicates(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_gz_csv(
            raw_dir / "python.csv.gz",
            [
                {"name": "org/keep", "mainLanguage": "Python"},
                {"name": "org/drop", "mainLanguage": "Python"},
            ],
            ["name", "mainLanguage"],
        )
        dups_path = tmp_path / "dups.csv"
        dups_path.write_text("repo_to_remove,repo_to_keep\norg/drop,org/keep\n")
        repos = load_raw_universe(raw_dir, dups_path)
        assert [r["repo_name"] for r in repos] == ["org/keep"]

    def test_dedupes_repo_seen_in_more_than_one_file(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_gz_csv(
            raw_dir / "java.csv.gz",
            [{"name": "org/dup", "mainLanguage": "Java"}],
            ["name", "mainLanguage"],
        )
        _write_gz_csv(
            raw_dir / "python.csv.gz",
            [{"name": "org/dup", "mainLanguage": "Java"}],
            ["name", "mainLanguage"],
        )
        repos = load_raw_universe(raw_dir, tmp_path / "missing_dups.csv")
        assert len(repos) == 1


class TestScanWorkingTree:
    def test_no_test_files_returns_all_zeros(self, tmp_path):
        counts = scan_working_tree(tmp_path, "python")
        assert counts == {
            "num_test_files": 0,
            "num_fixtures": 0,
            "num_setup": 0,
            "num_teardown": 0,
        }

    def test_test_file_with_no_fixtures(self, tmp_path):
        (tmp_path / "test_foo.py").write_text("def test_nothing():\n    assert True\n")
        counts = scan_working_tree(tmp_path, "python")
        assert counts["num_test_files"] == 1
        assert counts["num_fixtures"] == 0

    def test_setup_only_fixture_counts_setup_not_teardown(self, tmp_path):
        (tmp_path / "test_foo.py").write_text(PYTEST_SETUP_ONLY)
        counts = scan_working_tree(tmp_path, "python")
        assert counts["num_fixtures"] == 1
        assert counts["num_setup"] == 1
        assert counts["num_teardown"] == 0

    def test_teardown_only_fixture_counts_teardown_not_setup(self, tmp_path):
        (tmp_path / "test_foo.py").write_text(PYTEST_TEARDOWN_ONLY)
        counts = scan_working_tree(tmp_path, "python")
        assert counts["num_fixtures"] == 1
        assert counts["num_setup"] == 0
        assert counts["num_teardown"] == 1

    def test_setup_and_teardown_fixture_counts_toward_both(self, tmp_path):
        """The critical dual-counting behavior -- must match RQ3's own
        setup_and_teardown convention (research_questions/rq3.py)."""
        (tmp_path / "test_foo.py").write_text(PYTEST_SETUP_AND_TEARDOWN)
        counts = scan_working_tree(tmp_path, "python")
        assert counts["num_fixtures"] == 1
        assert counts["num_setup"] == 1
        assert counts["num_teardown"] == 1

    def test_multiple_fixtures_sum_correctly_across_files(self, tmp_path):
        (tmp_path / "test_a.py").write_text(PYTEST_SETUP_ONLY)
        (tmp_path / "test_b.py").write_text(PYTEST_TEARDOWN_ONLY)
        (tmp_path / "test_c.py").write_text(PYTEST_SETUP_AND_TEARDOWN)
        counts = scan_working_tree(tmp_path, "python")
        assert counts["num_test_files"] == 3
        assert counts["num_fixtures"] == 3
        assert counts["num_setup"] == 2  # setup-only + setup_and_teardown
        assert counts["num_teardown"] == 2  # teardown-only + setup_and_teardown

    def test_javascript_before_each_and_after_each(self, tmp_path):
        (tmp_path / "foo.test.js").write_text(JS_BEFORE_EACH + JS_AFTER_EACH)
        counts = scan_working_tree(tmp_path, "javascript")
        assert counts["num_fixtures"] == 2
        assert counts["num_setup"] == 1
        assert counts["num_teardown"] == 1

    def test_java_before_each(self, tmp_path):
        (tmp_path / "ExampleTest.java").write_text(JAVA_BEFORE_EACH)
        counts = scan_working_tree(tmp_path, "java")
        assert counts["num_fixtures"] == 1
        assert counts["num_setup"] == 1
        assert counts["num_teardown"] == 0

    def test_cross_language_file_not_counted_when_restricted_to_repo_language(self, tmp_path):
        """Deliberate design choice (module docstring): a stray JS test
        file inside a python-tagged repo must be invisible to this scan
        entirely, not leaked into python's counts the way Dataset C's
        cross-language-leakage handling would."""
        (tmp_path / "foo.test.js").write_text(JS_BEFORE_EACH)
        counts = scan_working_tree(tmp_path, "python")
        assert counts == {
            "num_test_files": 0,
            "num_fixtures": 0,
            "num_setup": 0,
            "num_teardown": 0,
        }

    def test_non_test_file_is_ignored(self, tmp_path):
        (tmp_path / "helpers.py").write_text(PYTEST_SETUP_ONLY)
        counts = scan_working_tree(tmp_path, "python")
        assert counts["num_test_files"] == 0
        assert counts["num_fixtures"] == 0


class TestDbLayer:
    def test_initialise_is_idempotent(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        initialise_rq1_db(db_path)  # must not raise

    def test_persist_and_load_scanned_repo_names_round_trip(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        row = _result_row(
            "org/a",
            "python",
            "2026-01-01T00:00:00+00:00",
            clone_ok=True,
            counts={"num_test_files": 1, "num_fixtures": 2, "num_setup": 1, "num_teardown": 1},
        )
        persist_result(row, db_path)
        assert load_scanned_repo_names(db_path) == {"org/a"}

    def test_persist_upserts_rather_than_duplicates(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(
            _result_row("org/a", "python", "t1", clone_ok=False, error_reason="clone_failed"),
            db_path,
        )
        persist_result(
            _result_row(
                "org/a",
                "python",
                "t2",
                clone_ok=True,
                counts={"num_test_files": 3, "num_fixtures": 0, "num_setup": 0, "num_teardown": 0},
            ),
            db_path,
        )
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT repo_name, clone_ok, num_test_files, error_reason FROM repo_prevalence"
        ).fetchall()
        conn.close()
        assert rows == [("org/a", 1, 3, None)]

    def test_load_scanned_repo_names_missing_db_returns_empty(self, tmp_path):
        assert load_scanned_repo_names(tmp_path / "missing.db") == set()


class TestWriteCsvOutputs:
    def test_writes_one_file_per_language_filtered_correctly(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(
            _result_row(
                "org/py",
                "python",
                "t",
                clone_ok=True,
                counts={"num_test_files": 1, "num_fixtures": 1, "num_setup": 1, "num_teardown": 0},
            ),
            db_path,
        )
        persist_result(
            _result_row(
                "org/java",
                "java",
                "t",
                clone_ok=True,
                counts={"num_test_files": 2, "num_fixtures": 0, "num_setup": 0, "num_teardown": 0},
            ),
            db_path,
        )

        out_dir = tmp_path / "out"
        written = write_csv_outputs(db_path, out_dir)

        assert set(written.keys()) == set(RQ1_LANGUAGES)

        with written["python"].open() as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert rows[0]["repo_name"] == "org/py"

        with written["java"].open() as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert rows[0]["repo_name"] == "org/java"

        with written["javascript"].open() as fh:
            rows = list(csv.DictReader(fh))
        assert rows == []


class TestAddFileLogging:
    """A plain terminal session (no nohup/tmux) dying mid-run would
    otherwise take every log line with it -- configure_logging() alone
    only attaches a console handler. add_file_logging() must make log
    output land durably on disk too."""

    def test_log_messages_land_in_the_file(self, tmp_path):
        log_path = tmp_path / "rq1.log"
        root = logging.getLogger()
        before_handlers = list(root.handlers)
        before_level = root.level
        try:
            root.setLevel(logging.INFO)
            rq1scan.add_file_logging(log_path)
            rq1scan.logger.info("hello from the test")
            for handler in root.handlers:
                handler.flush()
            assert "hello from the test" in log_path.read_text()
        finally:
            for handler in root.handlers:
                if handler not in before_handlers:
                    handler.close()
            root.handlers = before_handlers
            root.setLevel(before_level)

    def test_appends_rather_than_truncates_on_a_second_call(self, tmp_path):
        """A resumed run's log history must survive a restart -- same
        'never wipe prior progress' principle db_path/progress_path
        already follow."""
        log_path = tmp_path / "rq1.log"
        log_path.write_text("earlier run's log line\n")
        root = logging.getLogger()
        before_handlers = list(root.handlers)
        before_level = root.level
        try:
            root.setLevel(logging.INFO)
            rq1scan.add_file_logging(log_path)
            rq1scan.logger.info("this run's log line")
            for handler in root.handlers:
                handler.flush()
            content = log_path.read_text()
            assert "earlier run's log line" in content
            assert "this run's log line" in content
        finally:
            for handler in root.handlers:
                if handler not in before_handlers:
                    handler.close()
            root.handlers = before_handlers
            root.setLevel(before_level)


class TestGithubAuthEnv:
    """github_auth_env(): the Authorization-header env vars that
    authenticate every clone against GitHub. Never put the token in a
    URL or a -c flag -- both would land in this process's own argv,
    visible to any other user on a shared server via a plain
    `ps aux`/`ps -ef`.

    GitHub's git-over-HTTPS endpoint takes HTTP Basic auth, not Bearer:
    `Authorization: Basic base64("x-access-token:<token>")`.
    """

    def test_no_token_returns_empty_dict(self):
        assert rq1scan.github_auth_env("") == {}

    def test_token_produces_a_basic_auth_header_not_bearer(self):
        env = rq1scan.github_auth_env("my-token-value")
        assert env["GIT_CONFIG_COUNT"] == "1"
        assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"

        assert env["GIT_CONFIG_VALUE_0"].startswith("Authorization: ")
        auth_value = env["GIT_CONFIG_VALUE_0"].split("Authorization: ", 1)[1]
        assert auth_value.startswith("Basic ")  # not "Bearer" -- see class docstring
        decoded = base64.b64decode(auth_value.removeprefix("Basic ")).decode()
        assert decoded == "x-access-token:my-token-value"


class TestRunWithDeadline:
    """run_with_deadline(): the watchdog that bounds a per-repo call's
    overall wall-clock time, even when the underlying work has no timeout
    of its own."""

    def test_returns_true_and_the_result_when_fn_finishes_in_time(self):
        ok, result = rq1scan.run_with_deadline(lambda x: {"value": x}, 5, timeout_seconds=5)
        assert ok is True
        assert result == {"value": 5}

    def test_returns_false_and_none_when_fn_exceeds_the_deadline(self):
        def _slow(*, stop_event):
            stop_event.wait(5)  # far longer than the deadline below
            return {"should": "never be returned"}

        stop_event = threading.Event()
        try:
            ok, result = rq1scan.run_with_deadline(_slow, stop_event=stop_event, timeout_seconds=0.05)
            assert ok is False
            assert result is None
        finally:
            stop_event.set()  # let the orphaned thread exit instead of leaking into other tests

    def test_forwards_args_and_kwargs(self):
        calls = []

        def _fn(a, b, *, c):
            calls.append((a, b, c))
            return "done"

        ok, result = rq1scan.run_with_deadline(_fn, 1, 2, c=3, timeout_seconds=5)
        assert ok is True
        assert result == "done"
        assert calls == [(1, 2, 3)]


class TestFullCloneWithTimeout:
    """_full_clone_with_timeout(): the tightly-bounded fallback clone --
    deliberately NOT clone_repo_for_commit_scan(shallow_since=None), whose
    own 300s timeout (plus its own internal retry-on-truncation, up to
    another 300s) is too generous for a fallback step that should almost
    always finish in single-digit seconds (see its own docstring for the
    673s-under-contention finding that motivated this)."""

    def test_returns_true_on_successful_clone(self, tmp_path):
        target = tmp_path / "repo"

        def _fake_run(args, **kwargs):
            target.mkdir(parents=True, exist_ok=True)
            (target / ".git").mkdir()
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("collection.rq1_prevalence_scan.run_git_no_prompt", side_effect=_fake_run):
            assert _full_clone_with_timeout("url", target) is True

    def test_returns_false_on_nonzero_exit(self, tmp_path):
        with patch(
            "collection.rq1_prevalence_scan.run_git_no_prompt",
            return_value=SimpleNamespace(returncode=128, stdout="", stderr="fatal: not found"),
        ):
            assert _full_clone_with_timeout("url", tmp_path / "repo") is False

    def test_returns_false_on_credential_prompt(self, tmp_path):
        with patch(
            "collection.rq1_prevalence_scan.run_git_no_prompt",
            return_value=SimpleNamespace(returncode=128, stdout="", stderr="Username for 'https://github.com':"),
        ):
            assert _full_clone_with_timeout("url", tmp_path / "repo") is False

    def test_returns_false_on_timeout(self, tmp_path):
        with patch(
            "collection.rq1_prevalence_scan.run_git_no_prompt",
            side_effect=subprocess.TimeoutExpired(cmd="git clone", timeout=90),
        ):
            assert _full_clone_with_timeout("url", tmp_path / "repo") is False

    def test_passes_through_the_given_timeout(self, tmp_path):
        seen_kwargs = {}

        def _fake_run(args, **kwargs):
            seen_kwargs.update(kwargs)
            return SimpleNamespace(returncode=1, stdout="", stderr="")

        with patch("collection.rq1_prevalence_scan.run_git_no_prompt", side_effect=_fake_run):
            _full_clone_with_timeout("url", tmp_path / "repo", timeout=42)

        assert seen_kwargs["timeout"] == 42

    def test_passes_through_extra_env(self, tmp_path):
        seen_kwargs = {}

        def _fake_run(args, **kwargs):
            seen_kwargs.update(kwargs)
            return SimpleNamespace(returncode=1, stdout="", stderr="")

        auth = {"GIT_CONFIG_VALUE_0": "Authorization: Bearer x"}
        with patch("collection.rq1_prevalence_scan.run_git_no_prompt", side_effect=_fake_run):
            _full_clone_with_timeout("url", tmp_path / "repo", extra_env=auth)

        assert seen_kwargs["extra_env"] == auth


class TestCloneWithShallowFallback:
    """git can fail hard on --shallow-since when the boundary lands after
    every commit a repo has. The fallback to a full clone covers that case."""

    def test_returns_true_without_fallback_when_shallow_clone_succeeds(self, tmp_path):
        with (
            patch("collection.rq1_prevalence_scan.clone_repo_for_commit_scan", return_value=True) as shallow_mock,
            patch("collection.rq1_prevalence_scan._full_clone_with_timeout") as fallback_mock,
        ):
            assert _clone_with_shallow_fallback("url", tmp_path / "repo", shallow_since="2026-07-01") is True

        shallow_mock.assert_called_once_with(
            "url", tmp_path / "repo", shallow_since="2026-07-01", extra_env=None
        )
        fallback_mock.assert_not_called()

    def test_falls_back_to_full_clone_when_shallow_clone_fails_outright(self, tmp_path):
        target = tmp_path / "repo"
        target.mkdir()
        (target / "partial.txt").write_text("leftover from the failed attempt")

        def _fake_fallback(url, this_target, extra_env=None):
            # Fallback must run against a cleaned-up target -- the
            # partial shallow attempt's leftover must be gone first.
            assert not this_target.exists()
            return True

        with (
            patch("collection.rq1_prevalence_scan.clone_repo_for_commit_scan", return_value=False),
            patch("collection.rq1_prevalence_scan._full_clone_with_timeout", side_effect=_fake_fallback) as fallback_mock,
        ):
            result = _clone_with_shallow_fallback("url", target, shallow_since="2026-07-01")

        assert result is True
        fallback_mock.assert_called_once_with("url", target, extra_env=None)

    def test_forwards_extra_env_to_both_shallow_and_fallback_attempts(self, tmp_path):
        target = tmp_path / "repo"
        auth = {"GIT_CONFIG_VALUE_0": "Authorization: Bearer x"}

        with (
            patch("collection.rq1_prevalence_scan.clone_repo_for_commit_scan", return_value=False) as shallow_mock,
            patch("collection.rq1_prevalence_scan._full_clone_with_timeout", return_value=True) as fallback_mock,
        ):
            _clone_with_shallow_fallback("url", target, shallow_since="2026-07-01", extra_env=auth)

        shallow_mock.assert_called_once_with("url", target, shallow_since="2026-07-01", extra_env=auth)
        fallback_mock.assert_called_once_with("url", target, extra_env=auth)

    def test_returns_false_when_both_shallow_and_full_clone_fail(self, tmp_path):
        with (
            patch("collection.rq1_prevalence_scan.clone_repo_for_commit_scan", return_value=False),
            patch("collection.rq1_prevalence_scan._full_clone_with_timeout", return_value=False),
        ):
            assert _clone_with_shallow_fallback("url", tmp_path / "repo", shallow_since="2026-07-01") is False


# ---------------------------------------------------------------------------
# process_repo(): orchestration (clone -> pin to cutoff -> checkout -> scan).
# Clone is mocked to hand back a real local git repo instead of hitting the
# network -- same pattern test_dataset_c.py uses for _process_repo().
# ---------------------------------------------------------------------------


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
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = date
    env["GIT_COMMITTER_DATE"] = date
    _git(repo_path, "commit", "-m", message, env=env)


@contextmanager
def _fake_clone_result(path_or_none):
    """Stand-in for clone_with_function that just yields an already-built
    local repo (or None, for a simulated clone failure) instead of doing a
    real network clone."""
    yield path_or_none


class TestProcessRepo:
    def test_successful_scan_returns_clone_ok_row_with_counts(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "README.md", "hi", "2026-08-01T00:00:00")
        _commit(repo_path, "test_foo.py", PYTEST_SETUP_ONLY, "2026-08-15T00:00:00")

        repo = {
            "repo_name": "owner/repo",
            "language": "python",
            "clone_url": "https://example.com/owner/repo.git",
        }

        with patch(
            "collection.rq1_prevalence_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(repo, tmp_path, cutoff_date="2026-09-08")

        assert result["clone_ok"] == 1
        assert result["error_reason"] is None
        assert result["num_test_files"] == 1
        assert result["num_fixtures"] == 1
        assert result["num_setup"] == 1
        assert result["num_teardown"] == 0

    def test_clone_failure_returns_zero_row(self, tmp_path):
        repo = {
            "repo_name": "owner/repo",
            "language": "python",
            "clone_url": "https://example.com/owner/repo.git",
        }
        with patch(
            "collection.rq1_prevalence_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(None),
        ):
            result = process_repo(repo, tmp_path)

        assert result["clone_ok"] == 0
        assert result["error_reason"] == "clone_failed"
        assert result["num_fixtures"] == 0

    def test_no_commit_before_cutoff_returns_zero_row(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "README.md", "hi", "2026-09-10T00:00:00")  # after cutoff

        repo = {
            "repo_name": "owner/repo",
            "language": "python",
            "clone_url": "https://example.com/owner/repo.git",
        }
        with patch(
            "collection.rq1_prevalence_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(repo, tmp_path, cutoff_date="2026-09-08")

        assert result["clone_ok"] == 0
        assert result["error_reason"] == "no_commit_at_or_before_cutoff"

    def test_checkout_failure_returns_zero_row(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "README.md", "hi", "2026-08-01T00:00:00")

        repo = {
            "repo_name": "owner/repo",
            "language": "python",
            "clone_url": "https://example.com/owner/repo.git",
        }
        with (
            patch(
                "collection.rq1_prevalence_scan.clone_with_function",
                side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
            ),
            patch(
                "collection.rq1_prevalence_scan.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "git checkout"),
            ),
        ):
            result = process_repo(repo, tmp_path, cutoff_date="2026-09-08")

        assert result["clone_ok"] == 0
        assert result["error_reason"].startswith("checkout_failed")

    def test_ignores_commits_after_cutoff_date(self, tmp_path):
        """The temporal-pinning guarantee this whole module exists for: a
        fixture added after cutoff_date must not be visible, so this scan
        reflects the same reference point Dataset A/C were collected at,
        not whenever this scan happens to run."""
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "README.md", "hi", "2026-08-01T00:00:00")
        _commit(repo_path, "test_foo.py", PYTEST_SETUP_ONLY, "2026-09-20T00:00:00")  # after cutoff

        repo = {
            "repo_name": "owner/repo",
            "language": "python",
            "clone_url": "https://example.com/owner/repo.git",
        }
        with patch(
            "collection.rq1_prevalence_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(repo, tmp_path, cutoff_date="2026-09-08")

        assert result["clone_ok"] == 1
        assert result["num_test_files"] == 0
        assert result["num_fixtures"] == 0


class TestRunScan:
    def test_run_scan_skips_already_scanned_repos(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(
            _result_row(
                "org/already",
                "python",
                "t",
                clone_ok=True,
                counts={"num_test_files": 1, "num_fixtures": 0, "num_setup": 0, "num_teardown": 0},
            ),
            db_path,
        )

        universe = [
            {"repo_name": "org/already", "language": "python", "clone_url": "x"},
            {"repo_name": "org/new", "language": "python", "clone_url": "y"},
        ]
        processed = []

        def _fake_process_repo(repo, clones_dir, **kwargs):
            processed.append(repo["repo_name"])
            return _result_row(repo["repo_name"], repo["language"], "t2", clone_ok=True)

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
        ):
            counts = run_scan(
                db_path=db_path,
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        assert processed == ["org/new"]
        assert counts == {"total": 2, "already_done": 1, "scanned_this_run": 1}
        assert load_scanned_repo_names(db_path) == {"org/already", "org/new"}

    def test_run_scan_records_a_timeout_instead_of_hanging(self, tmp_path):
        """A repo whose processing never returns must not block the scan. It
        is recorded as a timeout and the run continues."""
        db_path = tmp_path / "rq1.db"
        stop_event = threading.Event()
        universe = [
            {"repo_name": "org/stuck", "language": "python", "clone_url": "x"},
            {"repo_name": "org/fine", "language": "python", "clone_url": "y"},
        ]

        def _fake_process_repo(repo, clones_dir, **kwargs):
            if repo["repo_name"] == "org/stuck":
                stop_event.wait(5)  # far longer than process_repo_timeout_seconds below
                return _result_row(repo["repo_name"], repo["language"], "never", clone_ok=True)
            return _result_row(repo["repo_name"], repo["language"], "t", clone_ok=True)

        try:
            with (
                patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
                patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
            ):
                counts = run_scan(
                    db_path=db_path,
                    workers=2,
                    clones_dir=tmp_path / "clones",
                    progress_path=tmp_path / "progress.json",
                    notify=False,
                    process_repo_timeout_seconds=0.05,
                )
        finally:
            stop_event.set()  # let the orphaned thread exit instead of leaking into other tests

        assert counts == {"total": 2, "already_done": 0, "scanned_this_run": 2}
        rows = {
            row[0]: (row[1], row[2])
            for row in sqlite3.connect(db_path).execute(
                "SELECT repo_name, clone_ok, error_reason FROM repo_prevalence"
            )
        }
        assert rows["org/stuck"] == (0, "timeout")
        assert rows["org/fine"] == (1, None)

    def test_run_scan_threads_extra_env_through_to_process_repo(self, tmp_path):
        auth = {"GIT_CONFIG_VALUE_0": "Authorization: Bearer x"}
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "x"}]
        seen_kwargs = {}

        def _fake_process_repo(repo, clones_dir, **kwargs):
            seen_kwargs.update(kwargs)
            return _result_row(repo["repo_name"], repo["language"], "t", clone_ok=True)

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
        ):
            run_scan(
                db_path=tmp_path / "rq1.db",
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=False,
                extra_env=auth,
            )

        assert seen_kwargs["extra_env"] == auth

    def test_run_scan_writes_progress_file_with_correct_tallies(self, tmp_path):
        """The progress file (not resume -- db_path's own rows already
        handle that, see test_run_scan_skips_already_scanned_repos) is
        purely for monitoring a multi-hour run. log_every=1 so every
        completion refreshes it, for a deterministic assertion."""
        db_path = tmp_path / "rq1.db"
        progress_path = tmp_path / "progress.json"
        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "x"},
            {"repo_name": "org/b", "language": "python", "clone_url": "y"},
        ]

        def _fake_process_repo(repo, clones_dir, **kwargs):
            ok = repo["repo_name"] == "org/a"
            return _result_row(repo["repo_name"], repo["language"], "t", clone_ok=ok, error_reason=None if ok else "clone_failed")

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
        ):
            run_scan(
                db_path=db_path,
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=progress_path,
                log_every=1,
                notify=False,
            )

        assert progress_path.exists()
        state = json.loads(progress_path.read_text())
        assert state["total_repos"] == 2
        assert state["pending_this_run"] == 2
        assert state["completed_this_run"] == 2
        assert state["clone_ok"] == 1
        assert state["clone_failed"] == 1
        assert state["estimated_remaining_seconds"] == 0.0

    def test_run_scan_progress_file_not_written_when_log_every_is_zero(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        progress_path = tmp_path / "progress.json"
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "x"}]

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch(
                "collection.rq1_prevalence_scan.process_repo",
                side_effect=lambda repo, clones_dir, **kw: _result_row(repo["repo_name"], repo["language"], "t", clone_ok=True),
            ),
        ):
            run_scan(
                db_path=db_path,
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=progress_path,
                log_every=0,
                notify=False,
            )

        assert not progress_path.exists()


class TestNotify:
    """_notify(): the ntfy.sh push itself, in isolation -- never hits the
    real network in tests, and a failure here must never raise (a
    multi-hour scan can't die over a notification)."""

    def test_calls_curl_with_the_message_and_topic(self):
        with patch("collection.rq1_prevalence_scan.subprocess.run") as run_mock:
            _notify("hello", topic="my_topic")

        args = run_mock.call_args[0][0]
        assert args[:2] == ["curl", "-s"]
        assert "hello" in args
        assert "ntfy.sh/my_topic" in args

    def test_swallows_any_exception(self):
        with patch("collection.rq1_prevalence_scan.subprocess.run", side_effect=OSError("no network")):
            _notify("hello")  # must not raise


class TestRunScanNotifications:
    """run_scan()'s per-language + final ntfy.sh pushes -- mocking _notify
    directly (its own curl-call shape is covered by TestNotify above) so
    this just checks run_scan() calls it the right number of times, with
    no real network in either case."""

    def _fake_process_repo(self, repo, clones_dir, **kwargs):
        return _result_row(repo["repo_name"], repo["language"], "t", clone_ok=True)

    def test_notifies_once_per_language_plus_one_final_push(self, tmp_path):
        universe = [
            {"repo_name": "org/py", "language": "python", "clone_url": "x"},
            {"repo_name": "org/js", "language": "javascript", "clone_url": "y"},
            # java/typescript deliberately have zero pending repos --
            # must still get a push, not be skipped.
        ]
        notify_calls = []

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=self._fake_process_repo),
            patch("collection.rq1_prevalence_scan._notify", side_effect=lambda msg: notify_calls.append(msg)),
        ):
            run_scan(
                db_path=tmp_path / "rq1.db",
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=True,
            )

        # One push per RQ1_LANGUAGES entry (4, in RQ1_LANGUAGES's own
        # order: java/javascript/python/typescript), plus one final push.
        assert len(notify_calls) == len(RQ1_LANGUAGES) + 1
        assert "java done" in notify_calls[0]
        assert "javascript done" in notify_calls[1]
        assert "python done" in notify_calls[2]
        assert "typescript done" in notify_calls[3]
        assert "all done" in notify_calls[-1]
        assert "2/2 total" in notify_calls[-1]

    def test_no_notifications_when_notify_is_false(self, tmp_path):
        universe = [{"repo_name": "org/py", "language": "python", "clone_url": "x"}]

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=self._fake_process_repo),
            patch("collection.rq1_prevalence_scan._notify") as notify_mock,
        ):
            run_scan(
                db_path=tmp_path / "rq1.db",
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        notify_mock.assert_not_called()


class TestResolveCutoffCommit:
    """A repo with zero commits inside [shallow_since, cutoff_date] has every
    commit visible in its `--shallow-since` clone after cutoff_date. A plain
    `find_cutoff_commit()` call then reports "no commit found", although the
    real answer lies just outside the shallow boundary. Uses real local `--shallow-since`
    clones against a `file://` source (no network) to reproduce git's
    actual shallow-boundary behavior exactly, not a simulation of it."""

    def _shallow_clone(self, tmp_path, source_path, *, shallow_since, name="target"):
        target = tmp_path / name
        _git(tmp_path, "clone", "--quiet", f"--shallow-since={shallow_since}", f"file://{source_path}", str(target))
        return target

    def test_full_clone_without_shallow_marker_trusts_a_none_result(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "a.txt", "x", "2026-09-10T00:00:00")  # only after cutoff
        assert not (repo_path / ".git" / "shallow").exists()

        result = _resolve_cutoff_commit(repo_path, "https://example.invalid/unreachable.git", "2026-09-08")
        assert result is None

    def test_shallow_clone_with_a_commit_in_window_is_trusted_without_retry(self, tmp_path):
        source = _make_git_repo(tmp_path, name="source")
        _commit(source, "a.txt", "one", "2026-06-16T00:00:00")
        _commit(source, "b.txt", "two", "2026-08-01T00:00:00")  # inside [shallow_since, cutoff]
        _commit(source, "c.txt", "three", "2026-09-12T00:00:00")  # after cutoff

        target = self._shallow_clone(tmp_path, source, shallow_since="2026-07-01")
        assert (target / ".git" / "shallow").exists()

        result = _resolve_cutoff_commit(target, f"file://{source}", "2026-09-08")
        assert result is not None
        assert result["date"] == "2026-08-01"

    def test_shallow_clone_missing_the_window_retries_full_and_finds_the_real_answer(self, tmp_path):
        """The exact bug: the only pre-cutoff commit sits before
        shallow_since, so the shallow clone's earliest commit is already
        after cutoff_date. find_cutoff_commit() alone reports None;
        _resolve_cutoff_commit() must not trust that and must recover the
        real answer via a full-clone retry."""
        source = _make_git_repo(tmp_path, name="source")
        _commit(source, "a.txt", "one", "2026-06-16T00:00:00")  # the true answer
        _commit(source, "b.txt", "two", "2026-09-12T00:00:00")  # after cutoff; all the shallow clone sees

        target = self._shallow_clone(tmp_path, source, shallow_since="2026-07-01")
        assert (target / ".git" / "shallow").exists()
        assert find_cutoff_commit(target, cutoff_date="2026-09-08") is None  # confirms the bug reproduces

        result = _resolve_cutoff_commit(target, f"file://{source}", "2026-09-08")
        assert result is not None
        assert result["date"] == "2026-06-16"

    def test_genuinely_no_commit_before_cutoff_is_still_none_after_retry(self, tmp_path):
        """A repo truly created after the cutoff date -- the full-clone
        retry must still correctly report no commit, not loop or
        fabricate an answer."""
        source = _make_git_repo(tmp_path, name="source")
        _commit(source, "a.txt", "one", "2026-09-12T00:00:00")  # only commit, after cutoff

        target = self._shallow_clone(tmp_path, source, shallow_since="2026-07-01")
        result = _resolve_cutoff_commit(target, f"file://{source}", "2026-09-08")
        assert result is None

    def test_full_clone_retry_failure_degrades_to_none_not_a_crash(self, tmp_path):
        source = _make_git_repo(tmp_path, name="source")
        _commit(source, "a.txt", "one", "2026-06-16T00:00:00")
        _commit(source, "b.txt", "two", "2026-09-12T00:00:00")

        target = self._shallow_clone(tmp_path, source, shallow_since="2026-07-01")
        assert (target / ".git" / "shallow").exists()

        result = _resolve_cutoff_commit(target, "https://example.invalid/does-not-exist.git", "2026-09-08")
        assert result is None


class TestLoadReposNeedingRetry:
    def test_missing_db_returns_empty_list(self, tmp_path):
        assert load_repos_needing_retry(db_path=tmp_path / "missing.db") == []

    def test_selects_only_matching_error_reasons_and_restores_language_and_url(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(_result_row("org/a", "python", "t", clone_ok=False, error_reason="clone_failed"), db_path)
        persist_result(
            _result_row("org/b", "python", "t", clone_ok=False, error_reason="no_commit_at_or_before_cutoff"),
            db_path,
        )
        persist_result(_result_row("org/c", "python", "t", clone_ok=False, error_reason="scan_failed: boom"), db_path)
        persist_result(_result_row("org/d", "python", "t", clone_ok=True), db_path)

        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "url-a"},
            {"repo_name": "org/b", "language": "python", "clone_url": "url-b"},
            {"repo_name": "org/c", "language": "python", "clone_url": "url-c"},
            {"repo_name": "org/d", "language": "python", "clone_url": "url-d"},
        ]
        with patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe):
            targets = load_repos_needing_retry(db_path=db_path)

        assert {t["repo_name"] for t in targets} == {"org/a", "org/b"}
        by_name = {t["repo_name"]: t for t in targets}
        assert by_name["org/a"]["clone_url"] == "url-a"

    def test_no_matching_rows_returns_empty_list(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(_result_row("org/a", "python", "t", clone_ok=True), db_path)
        with patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=[]):
            assert load_repos_needing_retry(db_path=db_path) == []

    def test_custom_error_reasons_narrows_selection(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(_result_row("org/a", "python", "t", clone_ok=False, error_reason="clone_failed"), db_path)
        persist_result(_result_row("org/b", "python", "t", clone_ok=False, error_reason="timeout"), db_path)
        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "url-a"},
            {"repo_name": "org/b", "language": "python", "clone_url": "url-b"},
        ]
        with patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe):
            targets = load_repos_needing_retry(error_reasons=("clone_failed",), db_path=db_path)
        assert {t["repo_name"] for t in targets} == {"org/a"}


class TestRetryFailedRepos:
    def test_retries_only_selected_repos_and_upserts_results(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(_result_row("org/a", "python", "t", clone_ok=False, error_reason="clone_failed"), db_path)
        persist_result(
            _result_row(
                "org/untouched",
                "python",
                "t",
                clone_ok=True,
                counts={"num_test_files": 3, "num_fixtures": 1, "num_setup": 1, "num_teardown": 0},
            ),
            db_path,
        )

        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "url-a"},
            {"repo_name": "org/untouched", "language": "python", "clone_url": "url-u"},
        ]

        def _fake_process_repo(repo, clones_dir, **kwargs):
            return _result_row(
                repo["repo_name"],
                repo["language"],
                "t2",
                clone_ok=True,
                counts={"num_test_files": 5, "num_fixtures": 2, "num_setup": 2, "num_teardown": 1},
            )

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
        ):
            counts = retry_failed_repos(db_path=db_path, workers=1, notify=False)

        assert counts == {"attempted": 1, "recovered": 1, "still_failed": 0}
        rows = {
            r[0]: (r[1], r[2])
            for r in sqlite3.connect(db_path).execute("SELECT repo_name, clone_ok, num_test_files FROM repo_prevalence")
        }
        assert rows["org/a"] == (1, 5)
        assert rows["org/untouched"] == (1, 3)  # never touched by the retry

    def test_still_failing_repos_are_counted_correctly(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(_result_row("org/a", "python", "t", clone_ok=False, error_reason="timeout"), db_path)
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "url-a"}]

        def _fake_process_repo(repo, clones_dir, **kwargs):
            return _result_row(repo["repo_name"], repo["language"], "t2", clone_ok=False, error_reason="clone_failed")

        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
        ):
            counts = retry_failed_repos(db_path=db_path, workers=1, notify=False)

        assert counts == {"attempted": 1, "recovered": 0, "still_failed": 1}

    def test_a_stuck_repo_is_recorded_as_timeout_not_hung(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(_result_row("org/stuck", "python", "t", clone_ok=False, error_reason="clone_failed"), db_path)
        universe = [{"repo_name": "org/stuck", "language": "python", "clone_url": "url"}]
        stop_event = threading.Event()

        def _fake_process_repo(repo, clones_dir, **kwargs):
            stop_event.wait(5)
            return _result_row(repo["repo_name"], repo["language"], "never", clone_ok=True)

        try:
            with (
                patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
                patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
            ):
                counts = retry_failed_repos(
                    db_path=db_path, workers=1, notify=False, process_repo_timeout_seconds=0.05
                )
        finally:
            stop_event.set()

        assert counts == {"attempted": 1, "recovered": 0, "still_failed": 1}
        row = sqlite3.connect(db_path).execute(
            "SELECT clone_ok, error_reason FROM repo_prevalence WHERE repo_name='org/stuck'"
        ).fetchone()
        assert row == (0, "timeout")

    def test_notifies_with_a_recovery_summary(self, tmp_path):
        db_path = tmp_path / "rq1.db"
        initialise_rq1_db(db_path)
        persist_result(_result_row("org/a", "python", "t", clone_ok=False, error_reason="clone_failed"), db_path)
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "url-a"}]

        def _fake_process_repo(repo, clones_dir, **kwargs):
            return _result_row(repo["repo_name"], repo["language"], "t2", clone_ok=True)

        notify_calls = []
        with (
            patch("collection.rq1_prevalence_scan.load_raw_universe", return_value=universe),
            patch("collection.rq1_prevalence_scan.process_repo", side_effect=_fake_process_repo),
            patch("collection.rq1_prevalence_scan._notify", side_effect=lambda msg: notify_calls.append(msg)),
        ):
            retry_failed_repos(db_path=db_path, workers=1, notify=True)

        assert len(notify_calls) == 1
        assert "1/1 repos recovered" in notify_calls[0]

    def test_default_error_reasons_is_the_repairable_set(self, tmp_path):
        assert REPAIRABLE_ERROR_REASONS == ("no_commit_at_or_before_cutoff", "clone_failed", "timeout")


class TestMainCli:
    """main()'s --workers flag and auth wiring -- never actually runs a
    scan (run_scan()/write_csv_outputs()/logging setup are all mocked
    out), and github_auth_env() is mocked too so these never depend on
    whatever real GITHUB_TOKEN this environment happens to have -- just
    checks the parsed/computed values are threaded through correctly."""

    def _run_main_with_argv(self, argv, *, auth_env=None):
        with (
            patch.object(sys, "argv", ["rq1_prevalence_scan.py", *argv]),
            patch("collection.rq1_prevalence_scan.configure_logging"),
            patch("collection.rq1_prevalence_scan.add_file_logging"),
            patch("collection.rq1_prevalence_scan.write_csv_outputs"),
            patch("collection.rq1_prevalence_scan.github_auth_env", return_value=auth_env or {}),
            patch("collection.rq1_prevalence_scan.run_scan", return_value={}) as run_scan_mock,
        ):
            main()
        return run_scan_mock

    def test_defaults_to_twelve_workers(self):
        run_scan_mock = self._run_main_with_argv([])
        assert run_scan_mock.call_args.kwargs["workers"] == 12

    def test_workers_flag_is_threaded_through(self):
        run_scan_mock = self._run_main_with_argv(["--workers", "16"])
        assert run_scan_mock.call_args.kwargs["workers"] == 16

    def test_passes_github_auth_env_to_run_scan(self):
        auth = {"GIT_CONFIG_VALUE_0": "Authorization: Bearer x"}
        run_scan_mock = self._run_main_with_argv([], auth_env=auth)
        assert run_scan_mock.call_args.kwargs["extra_env"] == auth

    def test_runs_unauthenticated_when_no_token_is_available(self):
        run_scan_mock = self._run_main_with_argv([], auth_env={})
        assert run_scan_mock.call_args.kwargs["extra_env"] == {}

    def test_retry_failed_flag_calls_retry_failed_repos_instead_of_run_scan(self):
        with (
            patch.object(sys, "argv", ["rq1_prevalence_scan.py", "--retry-failed"]),
            patch("collection.rq1_prevalence_scan.configure_logging"),
            patch("collection.rq1_prevalence_scan.add_file_logging"),
            patch("collection.rq1_prevalence_scan.write_csv_outputs"),
            patch("collection.rq1_prevalence_scan.github_auth_env", return_value={}),
            patch("collection.rq1_prevalence_scan.run_scan") as run_scan_mock,
            patch("collection.rq1_prevalence_scan.retry_failed_repos", return_value={}) as retry_mock,
        ):
            main()

        retry_mock.assert_called_once()
        run_scan_mock.assert_not_called()

    def test_retry_failed_threads_workers_and_auth_through(self):
        auth = {"GIT_CONFIG_VALUE_0": "Authorization: Basic x"}
        with (
            patch.object(sys, "argv", ["rq1_prevalence_scan.py", "--retry-failed", "--workers", "16"]),
            patch("collection.rq1_prevalence_scan.configure_logging"),
            patch("collection.rq1_prevalence_scan.add_file_logging"),
            patch("collection.rq1_prevalence_scan.write_csv_outputs"),
            patch("collection.rq1_prevalence_scan.github_auth_env", return_value=auth),
            patch("collection.rq1_prevalence_scan.retry_failed_repos", return_value={}) as retry_mock,
        ):
            main()

        assert retry_mock.call_args.kwargs["workers"] == 16
        assert retry_mock.call_args.kwargs["extra_env"] == auth
