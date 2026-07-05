import subprocess
import time
from pathlib import Path
from threading import Lock, Thread
from types import SimpleNamespace

from collection.fixture_extractor import (
    AgentFixtureExtractor,
    DiffLineMap,
    _checkout_commit,
    extract_fixtures_at_commit,
)


def test_fixture_span_requires_all_lines_added():
    diff_map = DiffLineMap(
        {
            1: "added",
            2: "added",
            3: "added",
        }
    )

    assert diff_map.fixture_is_completely_added(1, 3) is True


def test_fixture_span_with_context_line_is_not_complete():
    diff_map = DiffLineMap(
        {
            1: "added",
            2: "context",
            3: "added",
        }
    )

    assert diff_map.fixture_is_completely_added(1, 3) is False


def test_diff_parser_marks_added_and_context_lines_by_file():
    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    diff = "\n".join(
        [
            "diff --git a/tests/test_sample.py b/tests/test_sample.py",
            "index 0000000..1111111 100644",
            "--- a/tests/test_sample.py",
            "+++ b/tests/test_sample.py",
            "@@ -1,5 +1,6 @@",
            " import pytest",
            " @pytest.fixture",
            "+from foo import bar",
            " def sample_fixture():",
            "     return 42",
            "+",
        ]
    )

    diff_maps = extractor._build_diff_line_maps(diff)
    assert "tests/test_sample.py" in diff_maps

    diff_map = diff_maps["tests/test_sample.py"]
    assert diff_map.line_states[1] == "context"
    assert diff_map.line_states[2] == "context"
    assert diff_map.line_states[3] == "added"
    assert diff_map.line_states[4] == "context"
    assert diff_map.line_states[5] == "context"
    assert diff_map.line_states[6] == "added"


def test_ast_aware_completeness_ignores_blank_lines_inside_fixture_span(tmp_path):
    fixture_file = tmp_path / "test_sample.py"
    fixture_file.write_text(
        "\n".join(
            [
                "@pytest.fixture",
                "def sample_fixture():",
                "",
                "    value = 42",
                "    return value",
            ]
        )
    )

    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    fixture = SimpleNamespace(start_line=1, end_line=5)
    diff_map = DiffLineMap(
        {
            1: "added",
            2: "added",
            3: "context",
            4: "added",
            5: "added",
        }
    )

    assert (
        extractor._is_fixture_completely_added(
            full_path=fixture_file,
            fixture=fixture,
            diff_map=diff_map,
            language="python",
        )
        is True
    )


def test_ast_aware_completeness_ignores_comments_inside_python_fixture(tmp_path):
    fixture_file = tmp_path / "test_sample.py"
    fixture_file.write_text(
        "\n".join(
            [
                "@pytest.fixture",
                "def sample_fixture():",
                "    # comment line",
                "    value = 42",
                "    return value",
            ]
        )
    )

    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    fixture = SimpleNamespace(start_line=1, end_line=5)
    diff_map = DiffLineMap(
        {
            1: "added",
            2: "added",
            3: "context",
            4: "added",
            5: "added",
        }
    )

    assert (
        extractor._is_fixture_completely_added(
            full_path=fixture_file,
            fixture=fixture,
            diff_map=diff_map,
            language="python",
        )
        is True
    )


def test_ast_aware_completeness_works_for_typescript(tmp_path):
    fixture_file = tmp_path / "sample.spec.ts"
    fixture_file.write_text(
        "\n".join(
            [
                "export function sampleFixture() {",
                "  const value = 42;",
                "",
                "  return value;",
                "}",
            ]
        )
    )

    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    fixture = SimpleNamespace(start_line=1, end_line=5)
    diff_map = DiffLineMap(
        {
            1: "added",
            2: "added",
            3: "context",
            4: "added",
            5: "added",
        }
    )

    assert (
        extractor._is_fixture_completely_added(
            full_path=fixture_file,
            fixture=fixture,
            diff_map=diff_map,
            language="typescript",
        )
        is True
    )


def test_ast_aware_completeness_ignores_comments_inside_typescript_fixture(tmp_path):
    fixture_file = tmp_path / "sample.spec.ts"
    fixture_file.write_text(
        "\n".join(
            [
                "export function sampleFixture() {",
                "  // comment line",
                "  const value = 42;",
                "",
                "  return value;",
                "}",
            ]
        )
    )

    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    fixture = SimpleNamespace(start_line=1, end_line=6)
    diff_map = DiffLineMap(
        {
            1: "added",
            2: "context",
            3: "added",
            4: "context",
            5: "added",
            6: "added",
        }
    )

    assert (
        extractor._is_fixture_completely_added(
            full_path=fixture_file,
            fixture=fixture,
            diff_map=diff_map,
            language="typescript",
        )
        is True
    )


def test_ast_aware_completeness_works_for_java(tmp_path):
    fixture_file = tmp_path / "SampleTest.java"
    fixture_file.write_text(
        "\n".join(
            [
                "import org.junit.Before;",
                "",
                "public class SampleTest {",
                "    @Before",
                "    public void setUp() {",
                "        int value = 42;",
                "",
                "        System.out.println(value);",
                "    }",
                "}",
            ]
        )
    )

    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    fixture = SimpleNamespace(start_line=4, end_line=9)
    diff_map = DiffLineMap(
        {
            4: "added",
            5: "added",
            6: "added",
            7: "context",
            8: "added",
            9: "added",
        }
    )

    assert (
        extractor._is_fixture_completely_added(
            full_path=fixture_file,
            fixture=fixture,
            diff_map=diff_map,
            language="java",
        )
        is True
    )


def test_added_test_file_detection_ignores_go_paths():
    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    diff = "\n".join(
        [
            "diff --git a/connect-go/gen/proto/wg/cosmo/platform/v1/platform.pb.go b/connect-go/gen/proto/wg/cosmo/platform/v1/platform.pb.go",
            "diff --git a/pkg/example_test.go b/pkg/example_test.go",
            "diff --git a/tests/sample.spec.ts b/tests/sample.spec.ts",
        ]
    )

    files = extractor._find_added_test_files(diff)

    assert "tests/sample.spec.ts" in files
    assert "pkg/example_test.go" not in files
    assert "connect-go/gen/proto/wg/cosmo/platform/v1/platform.pb.go" not in files


def test_checkout_commit_removes_stale_index_lock_and_retries(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    git_dir = repo_path / ".git"
    git_dir.mkdir(parents=True)
    lock_path = git_dir / "index.lock"
    lock_path.write_text("stale lock")

    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=args[0],
                output="",
                stderr="fatal: Unable to create '.git/index.lock': File exists.",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    sleep_calls = []

    monkeypatch.setattr("collection.commit_checkout.subprocess.run", fake_run)
    monkeypatch.setattr(
        "collection.commit_checkout.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    _checkout_commit(repo_path, "abc1234")

    assert calls["count"] == 2
    assert sleep_calls == [0.5]
    assert not lock_path.exists()


def test_repo_worktree_lock_serializes_concurrent_extractions(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    git_dir = repo_path / ".git"
    git_dir.mkdir(parents=True)

    active = 0
    max_active = 0
    state_lock = Lock()

    def fake_checkout(*args, **kwargs):
        return None

    class DummyExtractor:
        def __init__(self, *args, **kwargs):
            pass

        def _find_test_files(self, *args, **kwargs):
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.15)
                return []
            finally:
                with state_lock:
                    active -= 1

    monkeypatch.setattr("collection.fixture_extractor._checkout_commit", fake_checkout)
    monkeypatch.setattr(
        "collection.fixture_extractor.Pre2021FixtureExtractor", DummyExtractor
    )

    results = []

    def worker(commit_sha):
        results.append(extract_fixtures_at_commit(repo_path, commit_sha, "python"))

    thread_one = Thread(target=worker, args=("commit-one",))
    thread_two = Thread(target=worker, args=("commit-two",))

    thread_one.start()
    time.sleep(0.03)
    thread_two.start()

    thread_one.join(timeout=5)
    thread_two.join(timeout=5)

    assert not thread_one.is_alive()
    assert not thread_two.is_alive()
    assert max_active <= 1
    assert len(results) == 2


# ──────────────────────────────────────────────────────────────
# Integration tests: purity gate inside _extract_from_diff()
# ──────────────────────────────────────────────────────────────


def test_extract_from_diff_skips_file_with_deletions(tmp_path, monkeypatch):
    """When a test file's diff contains deletions, the purity gate blocks extraction."""
    extractor = AgentFixtureExtractor(clones_dir=tmp_path)

    # Write a test file on disk so full_path.exists() is True
    test_file = tmp_path / "tests" / "test_skip_me.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "\n".join(
            [
                "import pytest",
                "",
                "@pytest.fixture",
                "def my_fixture():",
                "    return 42",
            ]
        )
    )

    diff = "\n".join(
        [
            "diff --git a/tests/test_skip_me.py b/tests/test_skip_me.py",
            "--- a/tests/test_skip_me.py",
            "+++ b/tests/test_skip_me.py",
            "@@ -1,3 +1,3 @@",
            " import pytest",
            "-from old_module import thing",
            "+from new_module import thing",
            " @pytest.fixture",
            " def my_fixture():",
            "     return 42",
        ]
    )

    fixtures = extractor._extract_from_diff(
        repo_path=tmp_path,
        repo_name="test/repo",
        diff_info=diff,
        commit_sha="abc123456789",
        agent_type="copilot",
    )

    # The file has a deletion line (-from old_module) → purity gate skips it
    assert len(fixtures) == 0


def test_extract_from_diff_skips_renamed_file(tmp_path):
    """When a test file is renamed, the purity gate blocks extraction."""
    extractor = AgentFixtureExtractor(clones_dir=tmp_path)

    test_file = tmp_path / "tests" / "test_renamed.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "\n".join(
            [
                "import pytest",
                "",
                "@pytest.fixture",
                "def my_fixture():",
                "    return 42",
            ]
        )
    )

    diff = "\n".join(
        [
            "diff --git a/tests/test_old_name.py b/tests/test_renamed.py",
            "rename from tests/test_old_name.py",
            "rename to tests/test_renamed.py",
        ]
    )

    fixtures = extractor._extract_from_diff(
        repo_path=tmp_path,
        repo_name="test/repo",
        diff_info=diff,
        commit_sha="abc123456789",
        agent_type="copilot",
    )

    assert len(fixtures) == 0


def test_extract_from_diff_keeps_pure_addition_file(tmp_path):
    """When a test file has only added lines, extraction proceeds normally."""
    extractor = AgentFixtureExtractor(clones_dir=tmp_path)

    test_file = tmp_path / "tests" / "test_pure.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "\n".join(
            [
                "import pytest",
                "",
                "@pytest.fixture",
                "def my_fixture():",
                "    return 42",
            ]
        )
    )

    diff = "\n".join(
        [
            "diff --git a/tests/test_pure.py b/tests/test_pure.py",
            "new file mode 100644",
            "index 0000000..abc1234",
            "--- /dev/null",
            "+++ b/tests/test_pure.py",
            "@@ -0,0 +1,5 @@",
            "+import pytest",
            "+",
            "+@pytest.fixture",
            "+def my_fixture():",
            "+    return 42",
        ]
    )

    fixtures = extractor._extract_from_diff(
        repo_path=tmp_path,
        repo_name="test/repo",
        diff_info=diff,
        commit_sha="abc123456789",
        agent_type="copilot",
    )

    # At least one fixture should be extracted (pytest fixture in a pure-add file)
    assert len(fixtures) >= 1
    fixture_names = {f["name"] for f in fixtures}
    assert "my_fixture" in fixture_names


def test_extract_from_diff_mixed_files_one_skipped_one_kept(tmp_path):
    """One file with deletions is skipped; a pure-addition file in the same commit is kept."""
    extractor = AgentFixtureExtractor(clones_dir=tmp_path)

    # Pure-add test file
    pure_file = tmp_path / "tests" / "test_pure.py"
    pure_file.parent.mkdir(parents=True, exist_ok=True)
    pure_file.write_text(
        "\n".join(
            [
                "@pytest.fixture",
                "def pure_fixture():",
                "    return 1",
            ]
        )
    )

    # Modified test file (has deletions)
    modified_file = tmp_path / "tests" / "test_modified.py"
    modified_file.parent.mkdir(parents=True, exist_ok=True)
    modified_file.write_text(
        "\n".join(
            [
                "import pytest",
                "@pytest.fixture",
                "def mod_fixture():",
                "    return 99",
            ]
        )
    )

    diff = "\n".join(
        [
            "diff --git a/tests/test_modified.py b/tests/test_modified.py",
            "--- a/tests/test_modified.py",
            "+++ b/tests/test_modified.py",
            "@@ -1,4 +1,4 @@",
            " import pytest",
            "-from old_dep import helper",
            "+from new_dep import helper",
            " @pytest.fixture",
            " def mod_fixture():",
            "     return 99",
            "diff --git a/tests/test_pure.py b/tests/test_pure.py",
            "new file mode 100644",
            "--- /dev/null",
            "+++ b/tests/test_pure.py",
            "@@ -0,0 +1,3 @@",
            "+@pytest.fixture",
            "+def pure_fixture():",
            "+    return 1",
        ]
    )

    fixtures = extractor._extract_from_diff(
        repo_path=tmp_path,
        repo_name="test/repo",
        diff_info=diff,
        commit_sha="abc123456789",
        agent_type="copilot",
    )

    # mod_fixture should be skipped (file had deletions), pure_fixture kept
    fixture_names = {f["name"] for f in fixtures}
    assert "pure_fixture" in fixture_names
    assert "mod_fixture" not in fixture_names


def test_extract_from_diff_empty_diff_returns_nothing():
    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    fixtures = extractor._extract_from_diff(
        repo_path=Path("/tmp"),
        repo_name="test/repo",
        diff_info="",
        commit_sha="abc123456789",
        agent_type="copilot",
    )
    assert fixtures == []


# ──────────────────────────────────────────────────────────────
# Integration tests: commit-level purity gate in _extract_from_agent_commits
# ──────────────────────────────────────────────────────────────


def test_agent_commits_skipped_when_commit_level_impure(tmp_path, monkeypatch):
    """If a test file in the commit has deletions, the whole commit is skipped."""
    extractor = AgentFixtureExtractor(clones_dir=tmp_path)

    repo_path = tmp_path / "repos" / "test__repo"
    (repo_path / ".git").mkdir(parents=True, exist_ok=True)

    # Prepare test files on disk
    clean_file = repo_path / "tests" / "clean.py"
    clean_file.parent.mkdir(parents=True, exist_ok=True)
    clean_file.write_text("@pytest.fixture\ndef fix(): return 1\n")

    dirty_file = repo_path / "tests" / "dirty.py"
    dirty_file.parent.mkdir(parents=True, exist_ok=True)
    dirty_file.write_text("def test(): pass\n")

    diff = "\n".join(
        [
            "diff --git a/tests/clean.py b/tests/clean.py",
            "--- /dev/null",
            "+++ b/tests/clean.py",
            "@@ -0,0 +1,2 @@",
            "+@pytest.fixture",
            "+def fix(): return 1",
            "diff --git a/tests/dirty.py b/tests/dirty.py",
            "--- a/tests/dirty.py",
            "+++ b/tests/dirty.py",
            "@@ -1,1 +1,1 @@",
            "-def old(): pass",
            "+def test(): pass",
        ]
    )

    # Monkeypatch module-level helpers
    monkeypatch.setattr(
        "collection.agent_fixture_extractor._checkout_commit",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        extractor,
        "_get_commit_info",
        lambda *a, **kw: {"date": "2025-06-01"},
    )
    monkeypatch.setattr(
        extractor,
        "_get_commit_diff",
        lambda *a, **kw: diff,
    )

    # The actual extraction code path we are testing

    monkeypatch.setattr(
        "collection.agent_fixture_extractor._resolve_repo_path",
        lambda *a, **kw: repo_path,
    )
    monkeypatch.setattr(
        "collection.agent_fixture_extractor._repo_worktree_lock",
        lambda *a, **kw: __import__("contextlib").nullcontext(),
    )

    fixtures = extractor._extract_from_agent_commits(
        repo_name="test/repo",
        commits={"abc12345": "copilot"},
    )

    # Commit-level gate should block extraction — dirty.py has a deletion
    assert len(fixtures) == 0


def test_agent_commits_proceeds_when_commit_level_pure(tmp_path, monkeypatch):
    """When all test files are pure additions, extraction proceeds."""
    extractor = AgentFixtureExtractor(clones_dir=tmp_path)

    repo_path = tmp_path / "repos" / "test__repo"
    (repo_path / ".git").mkdir(parents=True, exist_ok=True)

    pure_file = repo_path / "tests" / "pure.py"
    pure_file.parent.mkdir(parents=True, exist_ok=True)
    pure_file.write_text("@pytest.fixture\ndef fix(): return 1\n")

    diff = "\n".join(
        [
            "diff --git a/tests/pure.py b/tests/pure.py",
            "--- /dev/null",
            "+++ b/tests/pure.py",
            "@@ -0,0 +1,2 @@",
            "+@pytest.fixture",
            "+def fix(): return 1",
        ]
    )

    monkeypatch.setattr(
        "collection.agent_fixture_extractor._checkout_commit",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        extractor,
        "_get_commit_info",
        lambda *a, **kw: {"date": "2025-06-01"},
    )
    monkeypatch.setattr(
        extractor,
        "_get_commit_diff",
        lambda *a, **kw: diff,
    )
    monkeypatch.setattr(
        "collection.agent_fixture_extractor._resolve_repo_path",
        lambda *a, **kw: repo_path,
    )
    monkeypatch.setattr(
        "collection.agent_fixture_extractor._repo_worktree_lock",
        lambda *a, **kw: __import__("contextlib").nullcontext(),
    )

    fixtures = extractor._extract_from_agent_commits(
        repo_name="test/repo",
        commits={"abc12345": "copilot"},
    )

    # Pure addition commit should yield fixtures
    assert len(fixtures) >= 1
    fixture_names = {f["name"] for f in fixtures}
    assert "fix" in fixture_names


# ──────────────────────────────────────────────────────────────
# Integration tests: purity gate inside _extract_from_agent_commits()
# ──────────────────────────────────────────────────────────────


def _init_repo_with_commits(tmp_path: Path, commits: list[dict]) -> str:
    """Create a real git repo under tmp_path/owner__repo and return HEAD commit SHA."""
    repo = tmp_path / "owner__repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )

    for c in commits:
        (repo / c["path"]).parent.mkdir(parents=True, exist_ok=True)
        (repo / c["path"]).write_text(c.get("content", ""), encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo), "add", c["path"]], check=True, capture_output=True
        )
        msg = c.get("msg", "commit")
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", msg],
            check=True,
            capture_output=True,
        )

    return (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )


def test_extract_from_agent_commits_skips_commit_with_deletions(tmp_path):
    """A commit whose test files contain deletions is skipped entirely."""
    repo = tmp_path / "owner__repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )

    # Base commit: add a test file
    (repo / "tests").mkdir()
    (repo / "tests" / "test_foo.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef foo():\n    return 1\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "tests/test_foo.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "base"],
        check=True,
        capture_output=True,
    )

    # Second commit: modify the test file (introducing a deletion line)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test2@example.com"],
        check=True,
        capture_output=True,
    )
    (repo / "tests" / "test_foo.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef foo():\n    return 2\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "tests/test_foo.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            "modify test\n\nCo-authored-by: GitHub Copilot <copilot@example.com>",
        ],
        check=True,
        capture_output=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "copilot"},
    )
    assert fixtures == []


def test_extract_from_agent_commits_keeps_pure_addition_commit(tmp_path):
    """A commit whose test files are pure additions yields fixtures."""
    sha = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 42\n",
                "msg": "add pure test\n\nCo-authored-by: Claude <claude@anthropic.com>",
            }
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
    )
    assert len(fixtures) >= 1
    names = {f["name"] for f in fixtures}
    assert "pure_fixture" in names


def test_extract_from_agent_commits_mixed_files_skips_entire_commit(tmp_path):
    """If any test file in a commit has deletions, the whole commit is skipped."""
    # First commit: pure-add test file
    sha_pure = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 1\n",
                "msg": "add pure test\n\nCo-authored-by: Claude <claude@anthropic.com>",
            }
        ],
    )

    # Second commit: modify the same file (introducing a deletion) plus add another test
    repo = tmp_path / "owner__repo"
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test2@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test2"],
        check=True,
        capture_output=True,
    )
    (repo / "tests/test_pure.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 2\n",
        encoding="utf-8",
    )
    (repo / "tests/test_extra.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef extra_fixture():\n    return 3\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            "modify and add\n\nCo-authored-by: Claude <claude@anthropic.com>",
        ],
        check=True,
        capture_output=True,
    )
    sha_dirty = (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha_pure: "claude", sha_dirty: "claude"},
    )

    names = {f["name"] for f in fixtures}
    assert "pure_fixture" in names
    assert "extra_fixture" not in names


def test_extract_from_agent_commits_accepts_non_test_modifications_with_pure_add_tests(
    tmp_path,
):
    """Commit modifying non-test files + pure-add test files is accepted."""
    repo = tmp_path / "owner__repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )

    # Base: source file + test file
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_main.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef main_fixture():\n    return 1\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "base"],
        check=True,
        capture_output=True,
    )

    # Second commit: modify source file (with deletion) + add new test file
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test2@example.com"],
        check=True,
        capture_output=True,
    )
    (repo / "src" / "main.py").write_text(
        "def main():\n    return 1\n", encoding="utf-8"
    )
    (repo / "tests" / "test_new.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef new_fixture():\n    return 2\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            "modify source, add test\n\nCo-authored-by: Claude <claude@anthropic.com>",
        ],
        check=True,
        capture_output=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
    )

    names = {f["name"] for f in fixtures}
    assert "new_fixture" in names


# ──────────────────────────────────────────────────────────────
# Unit tests: optional `stats` param on _extract_from_agent_commits()
# (feeds Dataset A's per-repo agent_commits_touching_tests /
# rejected_mixed_test_diff / accepted counters in agent_corpus.py)
# ──────────────────────────────────────────────────────────────


def test_extract_from_agent_commits_stats_none_by_default(tmp_path):
    """Omitting `stats` must not change behaviour (backward compatible)."""
    sha = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 42\n",
                "msg": "add pure test\n\nCo-authored-by: Claude <claude@anthropic.com>",
            }
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
    )
    assert len(fixtures) >= 1


def test_extract_from_agent_commits_stats_records_rejected_for_mixed_diff(tmp_path):
    """A commit skipped for a mixed (non-pure-addition) test diff increments
    commits_skipped_commit_level in the caller-supplied stats dict."""
    repo = tmp_path / "owner__repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )

    (repo / "tests").mkdir()
    (repo / "tests" / "test_foo.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef foo():\n    return 1\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "tests/test_foo.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "base"],
        check=True,
        capture_output=True,
    )

    (repo / "tests" / "test_foo.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef foo():\n    return 2\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "tests/test_foo.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            "modify test\n\nCo-authored-by: GitHub Copilot <copilot@example.com>",
        ],
        check=True,
        capture_output=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    stats: dict = {}
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "copilot"},
        stats=stats,
    )
    assert fixtures == []
    assert stats == {"commits_skipped_commit_level": 1}


def test_extract_from_agent_commits_stats_records_accepted_with_fixtures(tmp_path):
    """A pure-addition commit that yields fixtures increments commits_proceeded."""
    sha = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 42\n",
                "msg": "add pure test\n\nCo-authored-by: Claude <claude@anthropic.com>",
            }
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    stats: dict = {}
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
        stats=stats,
    )
    assert len(fixtures) >= 1
    assert stats == {"commits_proceeded": 1}


def test_extract_from_agent_commits_stats_records_accepted_without_fixtures(tmp_path):
    """A pure-addition commit whose added test file has no fixture pattern still
    passes the commit-level purity gate: commits_skipped_file_level, not
    commits_skipped_commit_level."""
    sha = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_plain.py",
                "content": "def test_plain():\n    assert True\n",
                "msg": "add plain test\n\nCo-authored-by: Claude <claude@anthropic.com>",
            }
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    stats: dict = {}
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
        stats=stats,
    )
    assert fixtures == []
    assert stats == {"commits_skipped_file_level": 1}
