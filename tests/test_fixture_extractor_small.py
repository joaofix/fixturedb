import shutil
from unittest.mock import MagicMock, PropertyMock

from collection.config import MAX_FILE_SIZE_BYTES
from collection.fixture_extractor import (
    DiffLineMap,
    Pre2021FixtureExtractor,
    _raw_diff_commit_is_pure_addition,
    _raw_diff_file_is_pure_addition,
    _resolve_repo_path,
    commit_is_pure_addition,
    is_pure_addition,
)


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


# ──────────────────────────────────────────────────────────────
# is_pure_addition() — PyDriller-based purity gate
# ──────────────────────────────────────────────────────────────


def _make_mock_modified_file(change_type, diff_parsed_deleted):
    """Build a mock PyDriller ModifiedFile with change_type and diff_parsed."""
    mf = MagicMock()
    type(mf).change_type = PropertyMock(return_value=change_type)
    type(mf).diff_parsed = PropertyMock(
        return_value={"added": [], "deleted": diff_parsed_deleted}
    )
    return mf


def _make_mock_modified_file_no_deleted_key(change_type):
    """diff_parsed without a 'deleted' key at all."""
    mf = MagicMock()
    type(mf).change_type = PropertyMock(return_value=change_type)
    type(mf).diff_parsed = PropertyMock(return_value={"added": []})
    return mf


class TestIsPureAddition:
    """Exhaustive tests for is_pure_addition()."""

    def test_add_no_deletions(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(_make_mock_modified_file(ModificationType.ADD, [])) is True
        )

    def test_add_with_deletions(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(_make_mock_modified_file(ModificationType.ADD, [(1, "x")]))
            is False
        )

    def test_modify_no_deletions(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(_make_mock_modified_file(ModificationType.MODIFY, []))
            is True
        )

    def test_modify_with_deletions(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(
                _make_mock_modified_file(ModificationType.MODIFY, [(5, "old")])
            )
            is False
        )

    def test_rename(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(_make_mock_modified_file(ModificationType.RENAME, []))
            is False
        )

    def test_delete(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(_make_mock_modified_file(ModificationType.DELETE, []))
            is False
        )

    def test_copy(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(_make_mock_modified_file(ModificationType.COPY, []))
            is False
        )

    def test_unknown_no_deletions(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(_make_mock_modified_file(ModificationType.UNKNOWN, []))
            is True
        )

    def test_missing_deleted_key(self):
        from pydriller.domain.commit import ModificationType

        assert (
            is_pure_addition(
                _make_mock_modified_file_no_deleted_key(ModificationType.ADD)
            )
            is True
        )


# ──────────────────────────────────────────────────────────────
# _raw_diff_file_is_pure_addition() — raw diff text purity gate
# ──────────────────────────────────────────────────────────────


class TestRawDiffFileIsPureAddition:
    """Exhaustive tests for _raw_diff_file_is_pure_addition()."""

    # ── happy path ──

    def test_fully_added_file(self):
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "new file mode 100644",
                "index 0000000..abc1234",
                "--- /dev/null",
                "+++ b/tests/test_foo.py",
                "@@ -0,0 +1,3 @@",
                "+@pytest.fixture",
                "+def my_fixture():",
                "+    return 42",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/test_foo.py") is True

    def test_context_only_no_deletions(self):
        """File with only context lines (no +/-) — no deletions, so pure."""
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- a/tests/test_foo.py",
                "+++ b/tests/test_foo.py",
                "@@ -1,2 +1,2 @@",
                " unchanged line 1",
                " unchanged line 2",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/test_foo.py") is True

    # ── deletion in hunk ──

    def test_deletion_line_present(self):
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- a/tests/test_foo.py",
                "+++ b/tests/test_foo.py",
                "@@ -1,4 +1,5 @@",
                " @pytest.fixture",
                " def my_fixture():",
                "-    old_value = 1",
                "+    new_value = 42",
                "     return new_value",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/test_foo.py") is False

    def test_deletion_line_starting_with_double_dash_not_mistaken_for_header(self):
        """A deleted line whose own content starts with "--" (no space at
        position 4, e.g. a CLI-flag example string "--verbose") renders as a
        "---"-prefixed hunk line. Regression test: this must still be
        detected as a deletion, not silently skipped as if it were the
        "--- a/path" file header."""
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- a/tests/test_foo.py",
                "+++ b/tests/test_foo.py",
                "@@ -1,2 +1,2 @@",
                " import pytest",
                "---verbose flag",
                "+def new_helper():",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/test_foo.py") is False

    def test_deletion_line_looking_like_sql_comment_not_mistaken_for_header(self):
        """A deleted line whose content is a SQL/Lua-style "-- comment"
        renders as "--- comment" -- three dashes plus a space, textually
        identical in shape to a real "--- a/path" file header. Regression
        test: must still be detected as a deletion."""
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- a/tests/test_foo.py",
                "+++ b/tests/test_foo.py",
                "@@ -1,2 +1,2 @@",
                " import pytest",
                "--- comment",
                "+def new_helper():",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/test_foo.py") is False

    def test_space_in_path_pure_addition(self):
        """Regression test: "diff --git a/<path> b/<path>" packs both paths
        into one whitespace-split line, ambiguous when <path> contains a
        space -- a backreference-based header match resolves this without
        space-splitting."""
        diff = "\n".join(
            [
                "diff --git a/tests/my test.py b/tests/my test.py",
                "--- /dev/null",
                "+++ b/tests/my test.py",
                "@@ -0,0 +1,2 @@",
                "+def test_thing():",
                "+    pass",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/my test.py") is True

    def test_space_in_path_with_deletion(self):
        """Regression test: a real deletion in a file whose path contains a
        space must still be detected."""
        diff = "\n".join(
            [
                "diff --git a/tests/my test.py b/tests/my test.py",
                "--- a/tests/my test.py",
                "+++ b/tests/my test.py",
                "@@ -1,2 +1,2 @@",
                "-def old():",
                "+def new():",
                " pass",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/my test.py") is False

    # ── rename ──

    def test_old_and_new_paths_differ(self):
        diff = "\n".join(
            [
                "diff --git a/tests/old_name.py b/tests/new_name.py",
                "--- a/tests/old_name.py",
                "+++ b/tests/new_name.py",
                "@@ -0,0 +1,3 @@",
                "+def test_thing():",
                "+    pass",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/new_name.py") is False

    def test_rename_from_to_lines(self):
        diff = "\n".join(
            [
                "diff --git a/tests/old.py b/tests/new.py",
                "rename from tests/old.py",
                "rename to tests/new.py",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/new.py") is False

    # ── copy ──

    def test_copy_from_to_lines(self):
        diff = "\n".join(
            [
                "diff --git a/tests/orig.py b/tests/copied.py",
                "copy from tests/orig.py",
                "copy to tests/copied.py",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/copied.py") is False

    # ── deleted file ──

    def test_deleted_file_mode(self):
        diff = "\n".join(
            [
                "diff --git a/tests/gone.py b/tests/gone.py",
                "deleted file mode 100644",
                "--- a/tests/gone.py",
                "+++ /dev/null",
                "@@ -1,3 +0,0 @@",
                "-def test_gone():",
                "-    pass",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/gone.py") is False

    # ── file not in diff ──

    def test_file_not_in_diff(self):
        diff = "\n".join(
            [
                "diff --git a/src/main.py b/src/main.py",
                "--- a/src/main.py",
                "+++ b/src/main.py",
                "@@ -0,0 +1,1 @@",
                "+print('hello')",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/missing.py") is False

    def test_empty_diff(self):
        assert _raw_diff_file_is_pure_addition("", "tests/any.py") is False

    # ── matched by a_path (old path) ──

    def test_matched_by_a_path(self):
        """File matched via old path (a/) when b/ differs."""
        diff = "\n".join(
            [
                "diff --git a/tests/old.py b/tests/new.py",
                "--- a/tests/old.py",
                "+++ b/tests/new.py",
                "@@ -0,0 +1,1 @@",
                "+def test(): pass",
            ]
        )
        # old_path != new_path → rename → False
        assert _raw_diff_file_is_pure_addition(diff, "tests/old.py") is False

    # ── multi-file diffs ──

    def test_multi_file_both_pure(self):
        diff = "\n".join(
            [
                "diff --git a/tests/test_a.py b/tests/test_a.py",
                "--- /dev/null",
                "+++ b/tests/test_a.py",
                "@@ -0,0 +1,3 @@",
                "+def fixture_a():",
                "+    pass",
                "diff --git a/tests/test_b.py b/tests/test_b.py",
                "--- a/tests/test_b.py",
                "+++ b/tests/test_b.py",
                "@@ -1,1 +1,2 @@",
                " existing line",
                "+new line",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/test_a.py") is True
        assert _raw_diff_file_is_pure_addition(diff, "tests/test_b.py") is True

    def test_multi_file_one_has_deletion(self):
        diff = "\n".join(
            [
                "diff --git a/tests/good.py b/tests/good.py",
                "--- /dev/null",
                "+++ b/tests/good.py",
                "@@ -0,0 +1,2 @@",
                "+def fixture_a():",
                "+    pass",
                "diff --git a/tests/bad.py b/tests/bad.py",
                "--- a/tests/bad.py",
                "+++ b/tests/bad.py",
                "@@ -1,3 +1,3 @@",
                " unchanged",
                "-deleted line",
                "+added line",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/good.py") is True
        assert _raw_diff_file_is_pure_addition(diff, "tests/bad.py") is False

    # ── malformed header ──

    def test_malformed_diff_git_header(self):
        """diff --git with fewer than 4 parts — file not matched."""
        diff = "\n".join(
            [
                "diff --git a/tests/x.py",
                "--- /dev/null",
                "+++ b/tests/x.py",
                "@@ -0,0 +1,1 @@",
                "+pass",
            ]
        )
        assert _raw_diff_file_is_pure_addition(diff, "tests/x.py") is False


# ──────────────────────────────────────────────────────────────
# commit_is_pure_addition() — PyDriller-based commit-level gate
# ──────────────────────────────────────────────────────────────


def _make_mock_commit(modified_files):
    """Build a mock PyDriller commit with a given list of mock modified files."""
    c = MagicMock()
    type(c).modified_files = PropertyMock(return_value=modified_files)
    return c


class TestCommitIsPureAddition:
    """Exhaustive tests for commit_is_pure_addition()."""

    def test_all_test_files_clean(self):
        from pydriller.domain.commit import ModificationType

        mf1 = _make_mock_modified_file(ModificationType.ADD, [])
        type(mf1).new_path = PropertyMock(return_value="tests/test_a.py")
        type(mf1).old_path = PropertyMock(return_value=None)
        mf2 = _make_mock_modified_file(ModificationType.ADD, [])
        type(mf2).new_path = PropertyMock(return_value="tests/test_b.py")
        type(mf2).old_path = PropertyMock(return_value=None)
        assert commit_is_pure_addition(_make_mock_commit([mf1, mf2])) is True

    def test_test_file_with_deletions(self):
        from pydriller.domain.commit import ModificationType

        mf = _make_mock_modified_file(ModificationType.MODIFY, [(3, "deleted")])
        type(mf).new_path = PropertyMock(return_value="tests/test_foo.py")
        type(mf).old_path = PropertyMock(return_value="tests/test_foo.py")
        assert commit_is_pure_addition(_make_mock_commit([mf])) is False

    def test_test_file_rename(self):
        from pydriller.domain.commit import ModificationType

        mf = _make_mock_modified_file(ModificationType.RENAME, [])
        type(mf).new_path = PropertyMock(return_value="tests/test_new.py")
        type(mf).old_path = PropertyMock(return_value="tests/test_old.py")
        assert commit_is_pure_addition(_make_mock_commit([mf])) is False

    def test_test_file_delete(self):
        from pydriller.domain.commit import ModificationType

        mf = _make_mock_modified_file(ModificationType.DELETE, [])
        type(mf).new_path = PropertyMock(return_value=None)
        type(mf).old_path = PropertyMock(return_value="tests/test_deleted.py")
        assert commit_is_pure_addition(_make_mock_commit([mf])) is False

    def test_test_file_copy(self):
        from pydriller.domain.commit import ModificationType

        mf = _make_mock_modified_file(ModificationType.COPY, [])
        type(mf).new_path = PropertyMock(return_value="tests/test_copied.py")
        type(mf).old_path = PropertyMock(return_value="tests/test_orig.py")
        assert commit_is_pure_addition(_make_mock_commit([mf])) is False

    def test_ignores_non_test_files(self):
        from pydriller.domain.commit import ModificationType

        non_test = _make_mock_modified_file(ModificationType.MODIFY, [(1, "old")])
        type(non_test).new_path = PropertyMock(return_value="src/main.py")
        type(non_test).old_path = PropertyMock(return_value="src/main.py")
        test_file = _make_mock_modified_file(ModificationType.ADD, [])
        type(test_file).new_path = PropertyMock(return_value="tests/test_x.py")
        type(test_file).old_path = PropertyMock(return_value=None)
        assert commit_is_pure_addition(_make_mock_commit([non_test, test_file])) is True

    def test_mixed_clean_and_dirty(self):
        from pydriller.domain.commit import ModificationType

        clean = _make_mock_modified_file(ModificationType.ADD, [])
        type(clean).new_path = PropertyMock(return_value="tests/clean.py")
        type(clean).old_path = PropertyMock(return_value=None)
        dirty = _make_mock_modified_file(ModificationType.MODIFY, [(1, "old")])
        type(dirty).new_path = PropertyMock(return_value="tests/dirty.py")
        type(dirty).old_path = PropertyMock(return_value="tests/dirty.py")
        assert commit_is_pure_addition(_make_mock_commit([clean, dirty])) is False

    def test_unknown_extension_ignored(self):
        from pydriller.domain.commit import ModificationType

        mf = _make_mock_modified_file(ModificationType.MODIFY, [(1, "old")])
        type(mf).new_path = PropertyMock(return_value="docs/readme.txt")
        type(mf).old_path = PropertyMock(return_value="docs/readme.txt")
        assert commit_is_pure_addition(_make_mock_commit([mf])) is True

    def test_empty_modified_files(self):
        assert commit_is_pure_addition(_make_mock_commit([])) is True

    def test_only_non_test_files(self):
        from pydriller.domain.commit import ModificationType

        mf = _make_mock_modified_file(ModificationType.MODIFY, [(1, "old")])
        type(mf).new_path = PropertyMock(return_value="src/main.py")
        type(mf).old_path = PropertyMock(return_value="src/main.py")
        assert commit_is_pure_addition(_make_mock_commit([mf])) is True

    def test_modify_no_deletions_is_clean(self):
        from pydriller.domain.commit import ModificationType

        mf = _make_mock_modified_file(ModificationType.MODIFY, [])
        type(mf).new_path = PropertyMock(return_value="tests/test_foo.py")
        type(mf).old_path = PropertyMock(return_value="tests/test_foo.py")
        assert commit_is_pure_addition(_make_mock_commit([mf])) is True

    def test_js_and_ts_extensions(self):
        from pydriller.domain.commit import ModificationType

        for ext, _lang in [
            (".mjs", "javascript"),
            (".cjs", "javascript"),
            (".mts", "typescript"),
            (".cts", "typescript"),
            (".jsx", "javascript"),
            (".tsx", "typescript"),
        ]:
            mf = _make_mock_modified_file(ModificationType.ADD, [])
            type(mf).new_path = PropertyMock(return_value=f"tests/test_foo{ext}")
            type(mf).old_path = PropertyMock(return_value=None)
            assert (
                commit_is_pure_addition(_make_mock_commit([mf])) is True
            ), f"failed for {ext}"


# ──────────────────────────────────────────────────────────────
# _raw_diff_commit_is_pure_addition() — raw diff commit-level gate
# ──────────────────────────────────────────────────────────────


class TestRawDiffCommitIsPureAddition:
    """Exhaustive tests for _raw_diff_commit_is_pure_addition()."""

    # ── happy path ──

    def test_all_test_files_clean(self):
        diff = "\n".join(
            [
                "diff --git a/tests/test_a.py b/tests/test_a.py",
                "--- /dev/null",
                "+++ b/tests/test_a.py",
                "@@ -0,0 +1,3 @@",
                "+@pytest.fixture",
                "+def fix_a():",
                "+    return 1",
                "diff --git a/tests/test_b.py b/tests/test_b.py",
                "--- /dev/null",
                "+++ b/tests/test_b.py",
                "@@ -0,0 +1,3 @@",
                "+@pytest.fixture",
                "+def fix_b():",
                "+    return 2",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is True

    def test_empty_string(self):
        assert _raw_diff_commit_is_pure_addition("") is True

    def test_no_test_files_at_all(self):
        diff = "\n".join(
            [
                "diff --git a/src/main.py b/src/main.py",
                "--- /dev/null",
                "+++ b/src/main.py",
                "@@ -0,0 +1,1 @@",
                "+print('hello')",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is True

    def test_only_non_test_files(self):
        diff = "\n".join(
            [
                "diff --git a/src/main.py b/src/main.py",
                "--- a/src/main.py",
                "+++ b/src/main.py",
                "@@ -1,1 +1,1 @@",
                "-old",
                "+new",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is True

    def test_non_test_modifications_with_pure_add_test_files(self):
        """Non-test files can have deletions; only test-file purity matters."""
        diff = "\n".join(
            [
                "diff --git a/src/main.py b/src/main.py",
                "--- a/src/main.py",
                "+++ b/src/main.py",
                "@@ -1,2 +1,2 @@",
                "-old_line",
                "+new_line",
                " context",
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- /dev/null",
                "+++ b/tests/test_foo.py",
                "@@ -0,0 +1,3 @@",
                "+import pytest",
                "+",
                "+def test_foo():",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is True

    def test_test_file_context_only(self):
        """Test file with only context lines — no deletions, so pure."""
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- a/tests/test_foo.py",
                "+++ b/tests/test_foo.py",
                "@@ -1,2 +1,2 @@",
                " unchanged 1",
                " unchanged 2",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is True

    # ── deletion in hunk ──

    def test_one_test_file_has_deletion(self):
        diff = "\n".join(
            [
                "diff --git a/tests/clean.py b/tests/clean.py",
                "--- /dev/null",
                "+++ b/tests/clean.py",
                "@@ -0,0 +1,2 @@",
                "+def fix():",
                "+    pass",
                "diff --git a/tests/dirty.py b/tests/dirty.py",
                "--- a/tests/dirty.py",
                "+++ b/tests/dirty.py",
                "@@ -1,2 +1,2 @@",
                " def test():",
                "-    old = 1",
                "+    new = 2",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    def test_deletion_line_starting_with_double_dash_not_mistaken_for_header(self):
        """Regression test (commit-level): a deleted line starting with "--"
        renders as a "---"-prefixed hunk line and must still count as a
        deletion, not be mistaken for the "--- a/path" file header."""
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- a/tests/test_foo.py",
                "+++ b/tests/test_foo.py",
                "@@ -1,2 +1,2 @@",
                " import pytest",
                "---verbose flag",
                "+def new_helper():",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    def test_deletion_line_looking_like_sql_comment_not_mistaken_for_header(self):
        """Regression test (commit-level): a deleted SQL/Lua-style "--
        comment" renders as "--- comment", textually identical in shape to a
        real file header, and must still count as a deletion."""
        diff = "\n".join(
            [
                "diff --git a/tests/test_foo.py b/tests/test_foo.py",
                "--- a/tests/test_foo.py",
                "+++ b/tests/test_foo.py",
                "@@ -1,2 +1,2 @@",
                " import pytest",
                "--- comment",
                "+def new_helper():",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    def test_dirty_file_appears_first(self):
        """Dirty test file before clean — should still return False."""
        diff = "\n".join(
            [
                "diff --git a/tests/dirty.py b/tests/dirty.py",
                "--- a/tests/dirty.py",
                "+++ b/tests/dirty.py",
                "@@ -1,1 +1,1 @@",
                "-old",
                "+new",
                "diff --git a/tests/clean.py b/tests/clean.py",
                "--- /dev/null",
                "+++ b/tests/clean.py",
                "@@ -0,0 +1,1 @@",
                "+pass",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    def test_clean_file_appears_first_then_dirty(self):
        """Clean test file first, then dirty — should return False."""
        diff = "\n".join(
            [
                "diff --git a/tests/clean.py b/tests/clean.py",
                "--- /dev/null",
                "+++ b/tests/clean.py",
                "@@ -0,0 +1,1 @@",
                "+pass",
                "diff --git a/tests/dirty.py b/tests/dirty.py",
                "--- a/tests/dirty.py",
                "+++ b/tests/dirty.py",
                "@@ -1,1 +1,1 @@",
                "-old",
                "+new",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    # ── rename ──

    def test_rename_is_tainted(self):
        diff = "\n".join(
            [
                "diff --git a/tests/old.py b/tests/new.py",
                "rename from tests/old.py",
                "rename to tests/new.py",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    # ── copy ──

    def test_copy_is_tainted(self):
        diff = "\n".join(
            [
                "diff --git a/tests/orig.py b/tests/copied.py",
                "copy from tests/orig.py",
                "copy to tests/copied.py",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    # ── deleted file ──

    def test_deleted_file_is_tainted(self):
        diff = "\n".join(
            [
                "diff --git a/tests/gone.py b/tests/gone.py",
                "deleted file mode 100644",
                "--- a/tests/gone.py",
                "+++ /dev/null",
                "@@ -1,3 +0,0 @@",
                "-def test_gone():",
                "-    pass",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    # ── non-test files ignored ──

    def test_ignores_non_test_files(self):
        diff = "\n".join(
            [
                "diff --git a/src/main.py b/src/main.py",
                "--- a/src/main.py",
                "+++ b/src/main.py",
                "@@ -1,1 +1,1 @@",
                "-old",
                "+new",
                "diff --git a/tests/clean.py b/tests/clean.py",
                "--- /dev/null",
                "+++ b/tests/clean.py",
                "@@ -0,0 +1,2 @@",
                "+def fix():",
                "+    pass",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is True

    # ── js/ts extensions ──

    def test_js_and_ts_extensions(self):
        for ext in [".mjs", ".cjs", ".mts", ".cts", ".jsx", ".tsx"]:
            diff = "\n".join(
                [
                    f"diff --git a/tests/test_foo{ext} b/tests/test_foo{ext}",
                    "--- /dev/null",
                    f"+++ b/tests/test_foo{ext}",
                    "@@ -0,0 +1,1 @@",
                    "+pass",
                ]
            )
            assert _raw_diff_commit_is_pure_addition(diff) is True, f"failed for {ext}"

    # ── malformed header ──

    def test_malformed_diff_git_header(self):
        """diff --git with fewer than 4 parts — file not identified as test."""
        diff = "\n".join(
            [
                "diff --git a/tests/x.py",
                "--- /dev/null",
                "+++ b/tests/x.py",
                "@@ -0,0 +1,1 @@",
                "+pass",
            ]
        )
        # File not recognized → treated as non-test → commit is pure
        assert _raw_diff_commit_is_pure_addition(diff) is True

    # ── paths containing spaces ──

    def test_space_in_path_pure_addition(self):
        """Regression test: the "diff --git a/<path> b/<path>" header packs
        both paths into one whitespace-split line, ambiguous when <path>
        contains a space. A pure addition of such a file must still be
        recognized as pure."""
        diff = "\n".join(
            [
                "diff --git a/tests/my test.py b/tests/my test.py",
                "--- /dev/null",
                "+++ b/tests/my test.py",
                "@@ -0,0 +1,2 @@",
                "+def test_thing():",
                "+    pass",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is True

    def test_space_in_path_with_deletion_is_tainted(self):
        """Regression test: a real deletion in a file whose path contains a
        space must still be detected (not lost to header-parsing ambiguity)."""
        diff = "\n".join(
            [
                "diff --git a/tests/my test.py b/tests/my test.py",
                "--- a/tests/my test.py",
                "+++ b/tests/my test.py",
                "@@ -1,2 +1,2 @@",
                "-def old():",
                "+def new():",
                " pass",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False

    def test_space_in_path_renamed_test_file_is_tainted(self):
        """Regression test: a renamed test file whose *new* path contains a
        space must still be recognized as a test file and rejected as a
        rename, via the unambiguous "rename to " marker line correcting any
        misparse from the "diff --git" header's fallback split."""
        diff = "\n".join(
            [
                "diff --git a/tests/old.py b/tests/my new test.py",
                "rename from tests/old.py",
                "rename to tests/my new test.py",
            ]
        )
        assert _raw_diff_commit_is_pure_addition(diff) is False
