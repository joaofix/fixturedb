from __future__ import annotations

import subprocess
from pathlib import Path

from collection.test_commit_utils import (
    collect_test_files_for_commit,
    is_test_file_path,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_is_test_file_path_uses_language_heuristics() -> None:
    assert is_test_file_path("tests/test_widget.py", "python")
    assert is_test_file_path("src/test/java/com/example/WidgetTest.java", "java")
    assert is_test_file_path("src/__tests__/widget.spec.ts", "typescript")
    assert not is_test_file_path("src/widget.py", "python")


def test_collect_test_files_for_commit_detects_modified_test_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "widget.py").write_text(
        "def value():\n    return 1\n", encoding="utf-8"
    )
    (tests_dir / "test_widget.py").write_text(
        "def test_value():\n    assert value() == 1\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    (tests_dir / "test_widget.py").write_text(
        "def test_value():\n    assert value() == 2\n", encoding="utf-8"
    )
    (repo / "src" / "widget.py").write_text(
        "def value():\n    return 2\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "update test and source")

    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    test_files = collect_test_files_for_commit(repo, commit_sha, "python")
    assert test_files == ["tests/test_widget.py"]
