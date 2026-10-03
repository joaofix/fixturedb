"""Tests for collection/rq5_agent_file_scan.py.

Same standard as tests/collection/test_rq1_prevalence_scan.py: this scan
runs exactly once over ~24.7k repos, so every piece of real business logic
(keyword-pattern construction, per-line matching + code-fence tracking,
root-only case-insensitive file lookup, symlink-not-followed, DB upsert/
resume, CSV output) is exercised directly against real git repos/objects
built in `tmp_path` -- no real cloning or network access anywhere in this
file. Only `process_repo()`'s `clone_with_function()` call is mocked out,
handing back an already-built local repo instead of doing a real network
clone, the same pattern test_rq1_prevalence_scan.py uses.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
from contextlib import contextmanager
from unittest.mock import patch

from collection.rq5_agent_file_scan import (
    RQ5_LANGUAGES,
    _build_keyword_pattern,
    _build_patterns,
    _repo_row,
    _scan_result,
    find_keyword_matches,
    find_target_files_at_commit,
    initialise_rq5_db,
    list_root_tree_entries,
    load_rq5_keyword_catalog,
    load_scanned_repo_names,
    main,
    persist_result,
    process_repo,
    read_file_at_commit,
    run_scan,
    scan_file_content,
    write_csv_outputs,
)


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


def _head_sha(repo_path):
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@contextmanager
def _fake_clone_result(path_or_none):
    """Stand-in for clone_with_function -- yields an already-built local
    repo (or None, for a simulated clone failure) instead of a real
    network clone."""
    yield path_or_none


_TEST_CATALOG = {
    "version": 1,
    "target_files": ["AGENTS.md", "CLAUDE.md"],
    "test_keywords": ["test", "pytest"],
    "fixture_keywords": ["fixture", "fixtures", "teardown", "before each", "beforeEach"],
}


class TestLoadRq5KeywordCatalog:
    def test_real_catalog_has_expected_shape(self):
        catalog = load_rq5_keyword_catalog()
        assert catalog["target_files"] == ["AGENTS.md", "CLAUDE.md"]
        assert "test" in catalog["test_keywords"]
        assert "fixture" in catalog["fixture_keywords"]
        assert isinstance(catalog["version"], int)

    def test_bare_setup_is_never_a_standalone_keyword(self):
        """Explicit project requirement: the bare word "setup" matches
        generic environment-setup instructions, not fixture setup -- it
        must only ever appear inside a phrase."""
        catalog = load_rq5_keyword_catalog()
        assert "setup" not in catalog["test_keywords"]
        assert "setup" not in catalog["fixture_keywords"]


class TestBuildKeywordPattern:
    def test_single_word_respects_word_boundaries(self):
        pattern = _build_keyword_pattern("test")
        assert pattern.search("a test here")
        assert not pattern.search("latest")
        assert not pattern.search("contest")
        assert not pattern.search("attestation")

    def test_case_insensitive(self):
        pattern = _build_keyword_pattern("test")
        assert pattern.search("This is a TEST.")

    def test_multi_word_accepts_space_hyphen_or_no_separator(self):
        pattern = _build_keyword_pattern("before each")
        assert pattern.search("before each")
        assert pattern.search("before-each")
        assert pattern.search("beforeeach")
        assert pattern.search("BEFOREEACH")

    def test_multi_word_still_respects_outer_word_boundaries(self):
        pattern = _build_keyword_pattern("before each")
        assert not pattern.search("beforeeachx")
        assert not pattern.search("xbeforeeach")

    def test_camel_case_keyword_matched_literally(self):
        pattern = _build_keyword_pattern("beforeEach")
        assert pattern.search("call beforeEach now")
        assert pattern.search("BEFOREEACH")  # case-insensitive

    def test_internal_hyphen_in_a_word_is_preserved_literally(self):
        """"end-to-end test" -- the hyphen inside "end-to-end" is part of
        that token, not the variable multi-word separator; only the gap
        between "end-to-end" and "test" should vary."""
        pattern = _build_keyword_pattern("end-to-end test")
        assert pattern.search("end-to-end test")
        assert pattern.search("end-to-end-test")
        assert pattern.search("end-to-endtest")
        assert not pattern.search("endtoend test")


class TestBuildPatterns:
    def test_builds_one_pattern_per_keyword(self):
        patterns = _build_patterns(["test", "fixture"])
        assert set(patterns.keys()) == {"test", "fixture"}


class TestFindKeywordMatches:
    def test_records_every_occurrence_with_line_number_and_context(self):
        patterns = _build_patterns(["test"])
        content = "line one\na test and another test here\nline three"
        matches = find_keyword_matches(content, patterns)
        assert len(matches) == 2
        assert all(m["keyword"] == "test" for m in matches)
        assert all(m["line_number"] == 2 for m in matches)
        assert all(m["line_context"] == "a test and another test here" for m in matches)

    def test_line_context_is_stripped_of_surrounding_whitespace(self):
        patterns = _build_patterns(["test"])
        matches = find_keyword_matches("   a test line   \n", patterns)
        assert matches[0]["line_context"] == "a test line"

    def test_no_matches_on_content_without_any_keyword(self):
        patterns = _build_patterns(["test"])
        assert find_keyword_matches("nothing relevant here", patterns) == []

    def test_lines_inside_fenced_code_block_are_flagged(self):
        patterns = _build_patterns(["teardown"])
        content = "intro teardown\n```\nfenced teardown\n```\noutro teardown"
        matches = find_keyword_matches(content, patterns)
        by_context = {m["line_context"]: m["in_code_block"] for m in matches}
        assert by_context["intro teardown"] is False
        assert by_context["fenced teardown"] is True
        assert by_context["outro teardown"] is False

    def test_tilde_fences_also_toggle_code_block_state(self):
        patterns = _build_patterns(["teardown"])
        content = "~~~\nfenced teardown\n~~~"
        matches = find_keyword_matches(content, patterns)
        assert matches[0]["in_code_block"] is True

    def test_two_separate_fenced_blocks_each_toggle_correctly(self):
        patterns = _build_patterns(["teardown"])
        content = (
            "```\nfirst teardown\n```\n"
            "between teardown\n"
            "```\nsecond teardown\n```"
        )
        matches = find_keyword_matches(content, patterns)
        by_context = {m["line_context"]: m["in_code_block"] for m in matches}
        assert by_context["first teardown"] is True
        assert by_context["between teardown"] is False
        assert by_context["second teardown"] is True


class TestScanFileContent:
    def test_separates_test_and_fixture_matches(self):
        test_patterns = _build_patterns(["test"])
        fixture_patterns = _build_patterns(["fixture"])
        result = scan_file_content(
            "a test and a fixture", test_patterns=test_patterns, fixture_patterns=fixture_patterns
        )
        assert len(result["test_matches"]) == 1
        assert len(result["fixture_matches"]) == 1


class TestListRootTreeEntries:
    def test_lists_only_root_level_entries(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        (repo_path / "sub").mkdir()
        (repo_path / "sub" / "AGENTS.md").write_text("nested, must be ignored")
        _commit(repo_path, "AGENTS.md", "root file", "2026-08-01T00:00:00")
        _git(repo_path, "add", "sub/AGENTS.md")
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = "2026-08-01T00:00:01"
        env["GIT_COMMITTER_DATE"] = "2026-08-01T00:00:01"
        _git(repo_path, "commit", "-m", "add nested", env=env)

        sha = _head_sha(repo_path)
        entries = list_root_tree_entries(repo_path, sha)
        names = {name for name, _ in entries}
        assert "AGENTS.md" in names
        assert "sub" in names
        # The nested AGENTS.md must not appear as a root-level entry.
        assert names == {"AGENTS.md", "sub"}

    def test_distinguishes_blob_from_tree_type(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        (repo_path / "sub").mkdir()
        (repo_path / "sub" / "x.txt").write_text("x")
        _commit(repo_path, "AGENTS.md", "root file", "2026-08-01T00:00:00")
        _git(repo_path, "add", "sub/x.txt")
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = "2026-08-01T00:00:01"
        env["GIT_COMMITTER_DATE"] = "2026-08-01T00:00:01"
        _git(repo_path, "commit", "-m", "add sub", env=env)

        sha = _head_sha(repo_path)
        entries = dict(list_root_tree_entries(repo_path, sha))
        assert entries["AGENTS.md"] == "blob"
        assert entries["sub"] == "tree"

    def test_raises_on_git_failure(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        try:
            list_root_tree_entries(repo_path, "0" * 40)
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError")


class TestReadFileAtCommit:
    def test_reads_real_content_at_commit(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "AGENTS.md", "hello world", "2026-08-01T00:00:00")
        sha = _head_sha(repo_path)
        assert read_file_at_commit(repo_path, sha, "AGENTS.md") == "hello world"

    def test_returns_none_for_missing_path(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "AGENTS.md", "hello", "2026-08-01T00:00:00")
        sha = _head_sha(repo_path)
        assert read_file_at_commit(repo_path, sha, "DOES_NOT_EXIST.md") is None

    def test_symlink_returns_its_own_link_text_not_the_target_content(self, tmp_path):
        """Explicit project requirement: a symlinked agent file is searched
        as its own file -- its literal blob content (the link-target
        text), never the content it points to."""
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "AGENTS.md", "real content with a test keyword", "2026-08-01T00:00:00")
        (repo_path / "CLAUDE.md").symlink_to("AGENTS.md")
        _git(repo_path, "add", "CLAUDE.md")
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = "2026-08-01T00:00:01"
        env["GIT_COMMITTER_DATE"] = "2026-08-01T00:00:01"
        _git(repo_path, "commit", "-m", "symlink", env=env)
        sha = _head_sha(repo_path)

        content = read_file_at_commit(repo_path, sha, "CLAUDE.md")
        assert content == "AGENTS.md"


class TestFindTargetFilesAtCommit:
    def test_matches_case_insensitively(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "agents.md", "content", "2026-08-01T00:00:00")
        sha = _head_sha(repo_path)
        found = find_target_files_at_commit(repo_path, sha, ["AGENTS.md", "CLAUDE.md"])
        assert found == [("agents.md", "AGENTS.md")]

    def test_excludes_a_directory_with_a_matching_name(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        (repo_path / "AGENTS.md").mkdir()
        (repo_path / "AGENTS.md" / "inner.txt").write_text("x")
        _git(repo_path, "add", "AGENTS.md/inner.txt")
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = "2026-08-01T00:00:00"
        env["GIT_COMMITTER_DATE"] = "2026-08-01T00:00:00"
        _git(repo_path, "commit", "-m", "dir named like a target file", env=env)
        sha = _head_sha(repo_path)
        found = find_target_files_at_commit(repo_path, sha, ["AGENTS.md", "CLAUDE.md"])
        assert found == []

    def test_finds_both_target_files_independently(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        (repo_path / "AGENTS.md").write_text("a")
        (repo_path / "CLAUDE.md").write_text("b")
        _git(repo_path, "add", "AGENTS.md", "CLAUDE.md")
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = "2026-08-01T00:00:00"
        env["GIT_COMMITTER_DATE"] = "2026-08-01T00:00:00"
        _git(repo_path, "commit", "-m", "both", env=env)
        sha = _head_sha(repo_path)
        found = sorted(find_target_files_at_commit(repo_path, sha, ["AGENTS.md", "CLAUDE.md"]))
        assert found == [("AGENTS.md", "AGENTS.md"), ("CLAUDE.md", "CLAUDE.md")]

    def test_no_match_returns_empty_list(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "README.md", "content", "2026-08-01T00:00:00")
        sha = _head_sha(repo_path)
        assert find_target_files_at_commit(repo_path, sha, ["AGENTS.md", "CLAUDE.md"]) == []


class TestRepoRowAndScanResult:
    def test_repo_row_coerces_clone_ok_to_int(self):
        row = _repo_row("o/r", "python", "t", 1, clone_ok=True)
        assert row["clone_ok"] == 1
        row = _repo_row("o/r", "python", "t", 1, clone_ok=False)
        assert row["clone_ok"] == 0

    def test_repo_row_defaults(self):
        row = _repo_row("o/r", "python", "t", 1, clone_ok=False, error_reason="clone_failed")
        assert row["commit_sha"] is None
        assert row["num_agent_files"] == 0
        assert row["error_reason"] == "clone_failed"

    def test_scan_result_defaults_files_and_matches_to_empty_lists(self):
        row = _repo_row("o/r", "python", "t", 1, clone_ok=False)
        result = _scan_result(row)
        assert result == {"repo": row, "files": [], "matches": []}


class TestProcessRepo:
    def _repo_dict(self, name="owner/repo", language="python"):
        return {"repo_name": name, "language": language, "clone_url": "https://example.com/owner/repo.git"}

    def test_successful_scan_with_one_matching_file(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(
            repo_path,
            "AGENTS.md",
            "Run `pytest` and check the fixture setup.\nUse beforeEach for fixtures.",
            "2026-08-01T00:00:00",
        )

        with patch(
            "collection.rq5_agent_file_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(
                self._repo_dict(), tmp_path, cutoff_date="2026-09-08", catalog=_TEST_CATALOG
            )

        assert result["repo"]["clone_ok"] == 1
        assert result["repo"]["error_reason"] is None
        assert result["repo"]["num_agent_files"] == 1
        assert result["repo"]["catalog_version"] == 1
        assert result["repo"]["commit_sha"]

        assert len(result["files"]) == 1
        file_row = result["files"][0]
        assert file_row["file_name"] == "AGENTS.md"
        assert file_row["file_type"] == "AGENTS.md"
        assert file_row["has_test"] is True
        assert file_row["has_fixture"] is True
        assert file_row["test_match_count"] == 1  # "pytest" only -- "test" alone doesn't appear
        # "fixture" (line 1) + "beforeEach" and "before each" (both legitimately fire on
        # the same text -- a camelCase keyword and a spaced keyword are independent
        # catalog entries) + "fixtures" (line 2).
        assert file_row["fixture_match_count"] == 4
        assert "pytest" in file_row["matched_test_keywords"]
        assert file_row["github_url"] == (
            f"https://github.com/owner/repo/blob/{result['repo']['commit_sha']}/AGENTS.md"
        )

        assert len(result["matches"]) == file_row["test_match_count"] + file_row["fixture_match_count"]
        assert all(m["repo_name"] == "owner/repo" for m in result["matches"])
        assert all(m["file_name"] == "AGENTS.md" for m in result["matches"])

    def test_repo_with_no_target_files_is_clone_ok_with_zero_files(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "README.md", "nothing relevant", "2026-08-01T00:00:00")

        with patch(
            "collection.rq5_agent_file_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(
                self._repo_dict(), tmp_path, cutoff_date="2026-09-08", catalog=_TEST_CATALOG
            )

        assert result["repo"]["clone_ok"] == 1
        assert result["repo"]["error_reason"] is None
        assert result["repo"]["num_agent_files"] == 0
        assert result["files"] == []
        assert result["matches"] == []

    def test_clone_failure_returns_zero_row(self, tmp_path):
        with patch(
            "collection.rq5_agent_file_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(None),
        ):
            result = process_repo(self._repo_dict(), tmp_path, catalog=_TEST_CATALOG)

        assert result["repo"]["clone_ok"] == 0
        assert result["repo"]["error_reason"] == "clone_failed"
        assert result["files"] == []
        assert result["matches"] == []

    def test_no_commit_before_cutoff_returns_zero_row(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "AGENTS.md", "x", "2026-09-10T00:00:00")  # after cutoff

        with patch(
            "collection.rq5_agent_file_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(
                self._repo_dict(), tmp_path, cutoff_date="2026-09-08", catalog=_TEST_CATALOG
            )

        assert result["repo"]["clone_ok"] == 0
        assert result["repo"]["error_reason"] == "no_commit_at_or_before_cutoff"

    def test_ls_tree_failure_returns_zero_row(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "AGENTS.md", "x", "2026-08-01T00:00:00")

        with (
            patch(
                "collection.rq5_agent_file_scan.clone_with_function",
                side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
            ),
            patch(
                "collection.rq5_agent_file_scan.find_target_files_at_commit",
                side_effect=RuntimeError("git ls-tree failed: boom"),
            ),
        ):
            result = process_repo(
                self._repo_dict(), tmp_path, cutoff_date="2026-09-08", catalog=_TEST_CATALOG
            )

        assert result["repo"]["clone_ok"] == 0
        assert result["repo"]["error_reason"].startswith("ls_tree_failed")

    def test_one_unreadable_file_does_not_block_the_other(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        (repo_path / "AGENTS.md").write_text("a test file")
        (repo_path / "CLAUDE.md").write_text("a fixture file")
        _git(repo_path, "add", "AGENTS.md", "CLAUDE.md")
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = "2026-08-01T00:00:00"
        env["GIT_COMMITTER_DATE"] = "2026-08-01T00:00:00"
        _git(repo_path, "commit", "-m", "both", env=env)

        real_read = read_file_at_commit

        def _flaky_read(repo_path_arg, sha, file_name, **kwargs):
            if file_name == "AGENTS.md":
                raise RuntimeError("simulated read failure")
            return real_read(repo_path_arg, sha, file_name, **kwargs)

        with (
            patch(
                "collection.rq5_agent_file_scan.clone_with_function",
                side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
            ),
            patch("collection.rq5_agent_file_scan.read_file_at_commit", side_effect=_flaky_read),
        ):
            result = process_repo(
                self._repo_dict(), tmp_path, cutoff_date="2026-09-08", catalog=_TEST_CATALOG
            )

        assert result["repo"]["clone_ok"] == 1
        assert [f["file_name"] for f in result["files"]] == ["CLAUDE.md"]

    def test_symlinked_claude_md_is_scanned_as_its_own_literal_content(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        (repo_path / "AGENTS.md").write_text("a test mention and a fixture mention")
        (repo_path / "CLAUDE.md").symlink_to("AGENTS.md")
        _git(repo_path, "add", "AGENTS.md", "CLAUDE.md")
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = "2026-08-01T00:00:00"
        env["GIT_COMMITTER_DATE"] = "2026-08-01T00:00:00"
        _git(repo_path, "commit", "-m", "symlink", env=env)

        with patch(
            "collection.rq5_agent_file_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(
                self._repo_dict(), tmp_path, cutoff_date="2026-09-08", catalog=_TEST_CATALOG
            )

        by_name = {f["file_name"]: f for f in result["files"]}
        assert by_name["AGENTS.md"]["has_test"] is True
        assert by_name["AGENTS.md"]["has_fixture"] is True
        # CLAUDE.md's blob content is literally "AGENTS.md" -- no keyword in that string.
        assert by_name["CLAUDE.md"]["has_test"] is False
        assert by_name["CLAUDE.md"]["has_fixture"] is False

    def test_uses_resolve_cutoff_commit_not_the_raw_dataset_c_helper(self, tmp_path):
        """Regression guard: this scan must go through
        rq1_prevalence_scan._resolve_cutoff_commit() (the fix for the
        2026-10-02 "shallow clone hides the true cutoff commit" bug), not
        call dataset_c.find_cutoff_commit() directly -- a direct call
        would silently reintroduce that bug here."""
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "AGENTS.md", "x", "2026-08-01T00:00:00")
        real_sha = _head_sha(repo_path)  # must resolve for real in repo_path, or downstream git calls fail

        with (
            patch(
                "collection.rq5_agent_file_scan.clone_with_function",
                side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
            ),
            patch(
                "collection.rq5_agent_file_scan._resolve_cutoff_commit",
                return_value={"sha": real_sha, "date": "2026-08-01"},
            ) as resolve_mock,
        ):
            result = process_repo(
                self._repo_dict(), tmp_path, cutoff_date="2026-09-08", catalog=_TEST_CATALOG
            )

        resolve_mock.assert_called_once()
        assert resolve_mock.call_args.args[0] == repo_path
        assert resolve_mock.call_args.args[2] == "2026-09-08"
        assert result["repo"]["commit_sha"] == real_sha

    def test_default_catalog_is_loaded_when_none_is_passed(self, tmp_path):
        repo_path = _make_git_repo(tmp_path)
        _commit(repo_path, "AGENTS.md", "mentions conftest for fixtures", "2026-08-01T00:00:00")

        with patch(
            "collection.rq5_agent_file_scan.clone_with_function",
            side_effect=lambda fn, url, path: _fake_clone_result(repo_path),
        ):
            result = process_repo(self._repo_dict(), tmp_path, cutoff_date="2026-09-08")

        assert result["files"][0]["has_fixture"] is True


class TestLoadScannedRepoNames:
    def test_missing_db_returns_empty_set(self, tmp_path):
        assert load_scanned_repo_names(tmp_path / "missing.db") == set()

    def test_returns_persisted_repo_names(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(_scan_result(_repo_row("o/a", "python", "t", 1, clone_ok=True)), db_path)
        assert load_scanned_repo_names(db_path) == {"o/a"}


class TestPersistResult:
    def test_upserts_repo_row_by_name(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("o/a", "python", "t1", 1, clone_ok=False, error_reason="clone_failed")),
            db_path,
        )
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t2", 1, clone_ok=True, commit_sha="abc", num_agent_files=1)
            ),
            db_path,
        )

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT clone_ok, commit_sha FROM repo_scan WHERE repo_name='o/a'").fetchall()
        assert rows == [(1, "abc")]

    def test_re_persisting_replaces_file_and_match_rows_not_duplicates_them(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)

        file1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "file_type": "AGENTS.md",
            "language": "python",
            "commit_sha": "sha1",
            "has_test": True,
            "has_fixture": False,
            "test_match_count": 1,
            "fixture_match_count": 0,
            "matched_test_keywords": "test",
            "matched_fixture_keywords": "",
            "github_url": "https://github.com/o/a/blob/sha1/AGENTS.md",
        }
        match1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "keyword_list": "test",
            "keyword": "test",
            "line_number": 1,
            "line_context": "a test",
            "in_code_block": False,
        }
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t1", 1, clone_ok=True, commit_sha="sha1", num_agent_files=1),
                files=[file1],
                matches=[match1, match1],
            ),
            db_path,
        )

        # Re-process the same repo -- now with zero matching files.
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t2", 1, clone_ok=True, commit_sha="sha2", num_agent_files=0)
            ),
            db_path,
        )

        with sqlite3.connect(db_path) as conn:
            file_count = conn.execute("SELECT COUNT(*) FROM agent_files WHERE repo_name='o/a'").fetchone()[0]
            match_count = conn.execute(
                "SELECT COUNT(*) FROM agent_file_matches WHERE repo_name='o/a'"
            ).fetchone()[0]
        assert file_count == 0
        assert match_count == 0

    def test_persists_files_and_matches(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        file1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "file_type": "AGENTS.md",
            "language": "python",
            "commit_sha": "sha1",
            "has_test": True,
            "has_fixture": True,
            "test_match_count": 1,
            "fixture_match_count": 1,
            "matched_test_keywords": "test",
            "matched_fixture_keywords": "fixture",
            "github_url": "https://github.com/o/a/blob/sha1/AGENTS.md",
        }
        match_test = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "keyword_list": "test",
            "keyword": "test",
            "line_number": 1,
            "line_context": "a test",
            "in_code_block": False,
        }
        match_fixture = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "keyword_list": "fixture",
            "keyword": "fixture",
            "line_number": 2,
            "line_context": "a fixture",
            "in_code_block": True,
        }
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t", 1, clone_ok=True, commit_sha="sha1", num_agent_files=1),
                files=[file1],
                matches=[match_test, match_fixture],
            ),
            db_path,
        )

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            file_row = conn.execute("SELECT * FROM agent_files WHERE repo_name='o/a'").fetchone()
            match_rows = conn.execute(
                "SELECT * FROM agent_file_matches WHERE repo_name='o/a' ORDER BY line_number"
            ).fetchall()

        assert file_row["has_test"] == 1
        assert file_row["has_fixture"] == 1
        assert len(match_rows) == 2
        assert match_rows[1]["in_code_block"] == 1


class TestWriteCsvOutputs:
    def test_writes_three_csvs_with_headers_and_rows(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        file1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "file_type": "AGENTS.md",
            "language": "python",
            "commit_sha": "sha1",
            "has_test": True,
            "has_fixture": False,
            "test_match_count": 1,
            "fixture_match_count": 0,
            "matched_test_keywords": "test",
            "matched_fixture_keywords": "",
            "github_url": "https://github.com/o/a/blob/sha1/AGENTS.md",
        }
        match1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "keyword_list": "test",
            "keyword": "test",
            "line_number": 1,
            "line_context": "a test",
            "in_code_block": False,
        }
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t", 1, clone_ok=True, commit_sha="sha1", num_agent_files=1),
                files=[file1],
                matches=[match1],
            ),
            db_path,
        )

        out_dir = tmp_path / "csvs"
        written = write_csv_outputs(db_path, out_dir)

        assert set(written.keys()) == {"repo_scan", "agent_files", "agent_file_matches"}
        for path in written.values():
            assert path.exists()

        agent_files_csv = (out_dir / "agent_files.csv").read_text()
        assert "AGENTS.md" in agent_files_csv
        matches_csv = (out_dir / "agent_file_matches.csv").read_text()
        assert "a test" in matches_csv


class TestRunScan:
    def test_run_scan_skips_already_scanned_repos(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("org/already", "python", "t", 1, clone_ok=True)), db_path
        )

        universe = [
            {"repo_name": "org/already", "language": "python", "clone_url": "x"},
            {"repo_name": "org/new", "language": "python", "clone_url": "y"},
        ]
        processed = []

        def _fake_process_repo(repo, clones_dir, **kwargs):
            processed.append(repo["repo_name"])
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t2", 1, clone_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_raw_universe", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
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
        db_path = tmp_path / "rq5.db"
        stop_event = threading.Event()
        universe = [
            {"repo_name": "org/stuck", "language": "python", "clone_url": "x"},
            {"repo_name": "org/fine", "language": "python", "clone_url": "y"},
        ]

        def _fake_process_repo(repo, clones_dir, **kwargs):
            if repo["repo_name"] == "org/stuck":
                stop_event.wait(5)
                return _scan_result(_repo_row(repo["repo_name"], repo["language"], "never", 1, clone_ok=True))
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", 1, clone_ok=True))

        try:
            with (
                patch("collection.rq5_agent_file_scan.load_raw_universe", return_value=universe),
                patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
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
            stop_event.set()

        assert counts == {"total": 2, "already_done": 0, "scanned_this_run": 2}
        rows = {
            row[0]: (row[1], row[2])
            for row in sqlite3.connect(db_path).execute(
                "SELECT repo_name, clone_ok, error_reason FROM repo_scan"
            )
        }
        assert rows["org/stuck"] == (0, "timeout")
        assert rows["org/fine"] == (1, None)

    def test_run_scan_threads_extra_env_through_to_process_repo(self, tmp_path):
        auth = {"GIT_CONFIG_VALUE_0": "Authorization: Basic x"}
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "x"}]
        seen_kwargs = {}

        def _fake_process_repo(repo, clones_dir, **kwargs):
            seen_kwargs.update(kwargs)
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", 1, clone_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_raw_universe", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
        ):
            run_scan(
                db_path=tmp_path / "rq5.db",
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=False,
                extra_env=auth,
            )

        assert seen_kwargs["extra_env"] == auth

    def test_run_scan_passes_the_same_loaded_catalog_to_every_repo(self, tmp_path):
        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "x"},
            {"repo_name": "org/b", "language": "python", "clone_url": "y"},
        ]
        seen_catalogs = []

        def _fake_process_repo(repo, clones_dir, **kwargs):
            seen_catalogs.append(kwargs["catalog"])
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", 1, clone_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_raw_universe", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
        ):
            run_scan(
                db_path=tmp_path / "rq5.db",
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        assert seen_catalogs[0] is seen_catalogs[1]
        assert seen_catalogs[0]["target_files"] == ["AGENTS.md", "CLAUDE.md"]

    def test_run_scan_writes_progress_file_with_correct_tallies(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        progress_path = tmp_path / "progress.json"
        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "x"},
            {"repo_name": "org/b", "language": "python", "clone_url": "y"},
        ]

        def _fake_process_repo(repo, clones_dir, **kwargs):
            ok = repo["repo_name"] == "org/a"
            row = _repo_row(
                repo["repo_name"],
                repo["language"],
                "t",
                1,
                clone_ok=ok,
                error_reason=None if ok else "clone_failed",
                num_agent_files=1 if ok else 0,
            )
            files = (
                [
                    {
                        "repo_name": repo["repo_name"],
                        "file_name": "AGENTS.md",
                        "file_type": "AGENTS.md",
                        "language": repo["language"],
                        "commit_sha": "sha1",
                        "has_test": True,
                        "has_fixture": False,
                        "test_match_count": 1,
                        "fixture_match_count": 0,
                        "matched_test_keywords": "test",
                        "matched_fixture_keywords": "",
                        "github_url": "https://github.com/org/a/blob/sha1/AGENTS.md",
                    }
                ]
                if ok
                else []
            )
            return {"repo": row, "files": files, "matches": []}

        with (
            patch("collection.rq5_agent_file_scan.load_raw_universe", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
        ):
            run_scan(
                db_path=db_path,
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=progress_path,
                log_every=1,
                notify=False,
            )

        state = json.loads(progress_path.read_text())
        assert state["total_repos"] == 2
        assert state["completed_this_run"] == 2
        assert state["clone_ok"] == 1
        assert state["clone_failed"] == 1
        assert state["agent_files_found"] == 1


class TestRunScanNotifications:
    def _fake_process_repo(self, repo, clones_dir, **kwargs):
        return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", 1, clone_ok=True))

    def test_notifies_once_per_language_plus_one_final_push(self, tmp_path):
        universe = [
            {"repo_name": "org/py", "language": "python", "clone_url": "x"},
            {"repo_name": "org/js", "language": "javascript", "clone_url": "y"},
        ]
        notify_calls = []

        with (
            patch("collection.rq5_agent_file_scan.load_raw_universe", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=self._fake_process_repo),
            patch("collection.rq5_agent_file_scan._notify", side_effect=lambda msg: notify_calls.append(msg)),
        ):
            run_scan(
                db_path=tmp_path / "rq5.db",
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=True,
            )

        assert len(notify_calls) == len(RQ5_LANGUAGES) + 1
        assert "all done" in notify_calls[-1]

    def test_no_notifications_when_notify_is_false(self, tmp_path):
        universe = [{"repo_name": "org/py", "language": "python", "clone_url": "x"}]

        with (
            patch("collection.rq5_agent_file_scan.load_raw_universe", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=self._fake_process_repo),
            patch("collection.rq5_agent_file_scan._notify") as notify_mock,
        ):
            run_scan(
                db_path=tmp_path / "rq5.db",
                workers=1,
                clones_dir=tmp_path / "clones",
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        notify_mock.assert_not_called()


class TestMainCli:
    def _run_main_with_argv(self, argv, *, auth_env=None):
        with (
            patch.object(sys, "argv", ["rq5_agent_file_scan.py", *argv]),
            patch("collection.rq5_agent_file_scan.configure_logging"),
            patch("collection.rq5_agent_file_scan.add_file_logging"),
            patch("collection.rq5_agent_file_scan.write_csv_outputs"),
            patch("collection.rq5_agent_file_scan.github_auth_env", return_value=auth_env or {}),
            patch("collection.rq5_agent_file_scan.run_scan", return_value={}) as run_scan_mock,
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
        auth = {"GIT_CONFIG_VALUE_0": "Authorization: Basic x"}
        run_scan_mock = self._run_main_with_argv([], auth_env=auth)
        assert run_scan_mock.call_args.kwargs["extra_env"] == auth

    def test_runs_unauthenticated_when_no_token_is_available(self):
        run_scan_mock = self._run_main_with_argv([], auth_env={})
        assert run_scan_mock.call_args.kwargs["extra_env"] == {}
