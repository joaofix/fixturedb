import re
from pathlib import Path

import subprocess

from types import SimpleNamespace

from collection.agent_commit_detector import (
    _is_test_file_path,
    Tier1RepositoryScanner,
    COAUTHOR_TRAILER_RE,
    _collect_test_files_for_commit,
)


def test_is_test_file_path_python_cases():
    # typical test paths
    assert _is_test_file_path("tests/test_foo.py", "python")
    assert _is_test_file_path("test_utils.py", "python")
    assert _is_test_file_path("conftest.py", "python")
    assert _is_test_file_path("some/dir/tests/test_bar.py", "python")

    # non-test files
    assert not _is_test_file_path("src/main.py", "python")
    assert not _is_test_file_path("", "python")


def test_detect_agent_in_commit_author_and_coauthor():
    scanner = Tier1RepositoryScanner(Path("/tmp"))

    # author email containing keyword
    agent = scanner._detect_agent_in_commit("Alice", "alice@anthropic.com", "")
    assert agent == "claude"

    # author name containing keyword
    agent2 = scanner._detect_agent_in_commit("GitHub Copilot", "bot@example.com", "")
    assert agent2 == "copilot"

    # co-authored-by trailer detection
    body = "Some message\nCo-authored-by: GitHub Copilot <copilot@github.com>\n"
    # verify regex finds the trailer
    matches = COAUTHOR_TRAILER_RE.findall(body)
    assert any("copilot" in m.lower() for m in matches)


def test_detect_agent_no_match():
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert (
        scanner._detect_agent_in_commit("Bob", "bob@example.com", "no agents here")
        is None
    )


def test_detect_agent_multiple_coauthors():
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    body = (
        "Fixes\nCo-authored-by: GitHub Copilot <copilot@github.com>\n"
        "Co-authored-by: Anthropic Claude <claude@anthropic.com>\n"
    )
    # Should detect the first matching agent in coauthor scanning order
    agent = scanner._detect_agent_in_commit("Someone", "someone@example.com", body)
    assert agent in {"copilot", "claude"}


def test_collect_test_files_for_commit_parsing(monkeypatch, tmp_path):
    # Simulate git show output with added/modified/rename/copied entries
    stdout = (
        "A\ttests/test_foo.py\n"
        "M\tsrc/main.py\n"
        "R100\told.py\ttests/test_renamed.py\n"
        "C100\told.py\ttests/test_copy.py\n"
    )

    def fake_run(cmd, cwd, capture_output, text, timeout):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    files = _collect_test_files_for_commit(tmp_path, "deadbeef", "python")
    assert "tests/test_foo.py" in files
    assert "tests/test_renamed.py" in files
    assert "tests/test_copy.py" in files


def test_scan_repo_commit_roles_parses_multiline_git_log(monkeypatch, tmp_path):
    stdout = (
        "abc123\x1fAlice\x1falice@example.com\x1f2026-05-01T10:00:00+00:00\x1fFix pipes | in body\n"
        "Second line\n"
        "Co-authored-by: Claude <claude@example.com>\x1e"
        "def456\x1fBob\x1fbob@example.com\x1f2026-05-02T11:00:00+00:00\x1fRegular commit\x1e"
    )

    def fake_run(cmd, cwd, capture_output, text, timeout):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    scanner = Tier1RepositoryScanner(Path("/tmp"))
    commits = scanner.scan_repo_commit_roles(tmp_path, start_date="2026-05-01")

    assert [c.commit_sha for c in commits] == ["abc123", "def456"]
    assert commits[0].commit_date == "2026-05-01T10:00:00+00:00"
    assert commits[1].commit_date == "2026-05-02T11:00:00+00:00"


def test_is_test_file_path_javascript():
    assert _is_test_file_path("__tests__/my.test.js", "javascript")
    assert _is_test_file_path("spec/my.spec.js", "javascript")
    assert not _is_test_file_path("lib/foo.js", "javascript")
