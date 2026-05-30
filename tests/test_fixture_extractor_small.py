import shutil
from pathlib import Path

import pytest

from collection.fixture_extractor import (
    _resolve_repo_path,
    DiffLineMap,
    Pre2021FixtureExtractor,
)
from collection.config import MAX_FILE_SIZE_BYTES


def test_resolve_repo_path_prefers_slash(tmp_path):
    clones = tmp_path / "clones"
    # create both naming variants
    (clones / "owner" / "repo").mkdir(parents=True)
    (clones / "owner__repo").mkdir(parents=True)

    # should return the slash variant when present
    p = _resolve_repo_path(clones, "owner/repo")
    assert p == clones / "owner" / "repo"

    # remove slash variant, should return double-underscore variant
    shutil.rmtree(clones / "owner")
    p2 = _resolve_repo_path(clones, "owner/repo")
    assert p2 == clones / "owner__repo"


def test_diff_line_map_completely_added_and_edge_cases():
    # all added
    dlm = DiffLineMap({10: "added", 11: "added", 12: "added"})
    assert dlm.fixture_is_completely_added(10, 12)

    # one line not added
    dlm2 = DiffLineMap({10: "added", 11: "context", 12: "added"})
    assert not dlm2.fixture_is_completely_added(10, 12)

    # invalid ranges
    assert not dlm.fixture_is_completely_added(0, 5)
    assert not dlm.fixture_is_completely_added(5, 4)


def test_should_process_file_extension_and_size(tmp_path):
    extractor = Pre2021FixtureExtractor(clones_dir=tmp_path)

    repo = tmp_path / "repo"
    repo.mkdir()

    # small python file should be processed
    fpy = repo / "tests" / "test_foo.py"
    fpy.parent.mkdir()
    fpy.write_text("print(1)\n")
    assert extractor._should_process_file(fpy, "python")

    # wrong extension should be rejected
    ftxt = repo / "README.txt"
    ftxt.write_text("hello")
    assert not extractor._should_process_file(ftxt, "python")

    # oversized file should be rejected
    flarge = repo / "tests" / "huge_test.py"
    flarge.write_text("a" * (MAX_FILE_SIZE_BYTES + 1))
    assert not extractor._should_process_file(flarge, "python")
