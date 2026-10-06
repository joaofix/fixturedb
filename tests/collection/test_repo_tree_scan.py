"""discover-repos checks a repository's config files from HEAD's tree, not from a
checkout. These tests cover the tree listing, the match, the empty repository,
and agreement with the working-tree scan."""

import os
import subprocess
from pathlib import Path

import pytest

from collection import ephemeral_clone
from collection.agent_patterns import (
    scan_cloned_repo_for_agent_configs,
    scan_repo_tree_for_agent_configs,
)
from collection.clone_primitives import list_tree_entries


def _git(cwd: Path, *args: str) -> None:
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
    )
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def _repo_with_files(path: Path, files: dict[str, str]) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    for rel, content in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    return path


def test_empty_repository_has_no_tree_entries_and_no_config(tmp_path):
    repo = tmp_path / "empty"
    _git(tmp_path, "init", "-q", str(repo))

    assert list_tree_entries(repo) == []
    assert scan_repo_tree_for_agent_configs(repo) is None


def test_tree_entries_mark_directories(tmp_path):
    repo = _repo_with_files(tmp_path / "r", {"src/app.py": "x", "README.md": "y"})

    entries = dict(list_tree_entries(repo))

    assert entries["src"] is True
    assert entries["src/app.py"] is False
    assert entries["README.md"] is False


def test_root_agent_file_is_found(tmp_path):
    repo = _repo_with_files(tmp_path / "r", {"CLAUDE.md": "guidance"})
    assert scan_repo_tree_for_agent_configs(repo) == "CLAUDE.md"


def test_agent_directory_is_found(tmp_path):
    repo = _repo_with_files(tmp_path / "r", {".claude/settings.json": "{}"})
    assert scan_repo_tree_for_agent_configs(repo) == ".claude/"


def test_config_inside_an_excluded_directory_does_not_count(tmp_path):
    repo = _repo_with_files(tmp_path / "r", {"node_modules/pkg/CLAUDE.md": "vendored"})
    assert scan_repo_tree_for_agent_configs(repo) is None


def test_repository_without_config_files_returns_none(tmp_path):
    repo = _repo_with_files(tmp_path / "r", {"app.py": "print(1)"})
    assert scan_repo_tree_for_agent_configs(repo) is None


@pytest.mark.parametrize(
    "files",
    [
        {"CLAUDE.md": "x"},
        {".claude/settings.json": "{}"},
        {"AGENTS.md": "x", "src/a.py": "y"},
        {"zzz/.claude/settings.json": "{}", "AGENTS.md": "x"},
        {"src/CLAUDE.md": "x", "AGENTS.md": "y", ".cursor/rules.md": "z"},
        {"node_modules/pkg/CLAUDE.md": "x", "app.py": "y"},
        {"app.py": "y"},
    ],
)
def test_tree_scan_agrees_with_the_working_tree_scan(tmp_path, files):
    """The tree scan is the same test as the checkout scan, without the checkout."""
    repo = _repo_with_files(tmp_path / "r", files)
    assert scan_repo_tree_for_agent_configs(repo) == scan_cloned_repo_for_agent_configs(repo)


def test_tree_clone_uses_depth_one_no_blobs_and_no_checkout(monkeypatch):
    seen = {}

    def fake_clone(repo_full_name, clone_url, clone_args, **_):
        seen["args"] = list(clone_args)
        return None, None

    monkeypatch.setattr(ephemeral_clone, "clone_to_tempdir", fake_clone)
    with ephemeral_clone.temp_clone_tree("https://example.invalid/o/r.git", "o/r") as path:
        assert path is None

    assert "--depth=1" in seen["args"]
    assert "--filter=blob:none" in seen["args"]
    assert "--no-checkout" in seen["args"]


def test_real_partial_clone_of_a_local_repository_finds_the_config(tmp_path):
    """End to end on a real partial clone (file:// so that --depth is honoured)."""
    source = _repo_with_files(tmp_path / "src", {"AGENTS.md": "guidance", "app.py": "x"})
    _git(source, "config", "uploadpack.allowFilter", "true")
    _git(source, "config", "uploadpack.allowAnySHA1InWant", "true")

    with ephemeral_clone.temp_clone_tree(source.as_uri(), "o/src") as path:
        assert path is not None
        assert scan_repo_tree_for_agent_configs(path) == "AGENTS.md"


def test_discover_repos_records_an_empty_repository_as_no_agent_config(tmp_path, monkeypatch):
    """A repository with no commits is not a failed clone: it has no config file, so
    it is a row with has_agent_config=0 and qc_reason no_agent_config."""
    from collection.repository_quality_control import agent_repository_counter as qc

    empty = tmp_path / "empty"
    _git(tmp_path, "init", "-q", str(empty))

    @__import__("contextlib").contextmanager
    def fake_tree_clone(clone_url, full_name, prefix="", timeout=60):
        yield empty

    monkeypatch.setattr(qc, "temp_clone_tree", fake_tree_clone)
    row = qc._process_single(
        {"full_name": "owner/empty", "language": "python", "clone_url": empty.as_uri(), "stars": 1},
        "2025-01-01",
    )

    assert row is not None
    assert row["has_agent_config"] == 0
    assert row["qc_reason"] == "no_agent_config"


def test_tree_listing_survives_a_file_name_that_is_not_utf8(tmp_path):
    """Git stores file names as raw bytes. A Latin-1 name used to make the listing
    raise UnicodeDecodeError, which discover-repos then recorded as a clone failure.
    The listing must keep every name, and the config match must still be found."""
    repo = _repo_with_files(tmp_path / "r", {"CLAUDE.md": "guidance"})
    raw_path = os.path.join(os.fsencode(repo), b"caf\xe9.txt")
    with open(raw_path, "wb") as fh:
        fh.write(b"x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "latin-1 name")

    paths = {path for path, _ in list_tree_entries(repo)}

    assert "CLAUDE.md" in paths
    assert scan_repo_tree_for_agent_configs(repo) == "CLAUDE.md"
