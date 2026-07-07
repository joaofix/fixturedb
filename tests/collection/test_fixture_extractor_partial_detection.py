import subprocess
import time
from pathlib import Path
from threading import Lock, Thread
from types import SimpleNamespace

from pydriller import Git

from collection.fixture_extractor import (
    AgentFixtureExtractor,
    DiffLineMap,
    _checkout_commit,
    extract_fixtures_at_commit,
)


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


def _get_commit(tmp_path: Path, commits: list[dict]):
    """Build a real repo via _init_repo_with_commits() and return (repo_path,
    PyDriller Commit) for the resulting HEAD commit -- used by tests that
    exercise _build_diff_line_maps()/_find_added_test_files() directly
    against a real PyDriller Commit object, rather than hand-typed diff text."""
    sha = _init_repo_with_commits(tmp_path, commits)
    repo_path = tmp_path / "owner__repo"
    commit = Git(str(repo_path)).get_commit(sha)
    return repo_path, commit


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


def test_diff_parser_marks_added_and_context_lines_by_file(tmp_path):
    """_build_diff_line_maps() sources its per-line added/not-added state
    directly from PyDriller's own ModifiedFile.diff_parsed -- built against
    a real two-commit repo here, rather than hand-typed diff text, so this
    is exercising the actual PyDriller integration, not an assumption about
    its output shape."""
    repo_path, commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/test_sample.py",
                "content": "import pytest\n@pytest.fixture\ndef sample_fixture():\n    return 42\n",
                "msg": "base",
            },
            {
                "path": "tests/test_sample.py",
                "content": (
                    "import pytest\n@pytest.fixture\nfrom foo import bar\n"
                    "def sample_fixture():\n    return 42\n\n"
                ),
                "msg": "add import and trailing blank line",
            },
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    diff_maps = extractor._build_diff_line_maps(commit)
    assert "tests/test_sample.py" in diff_maps

    diff_map = diff_maps["tests/test_sample.py"]
    assert diff_map.line_states.get(1) != "added"  # import pytest (context)
    assert diff_map.line_states.get(2) != "added"  # @pytest.fixture (context)
    assert diff_map.line_states[3] == "added"  # from foo import bar
    assert diff_map.line_states.get(4) != "added"  # def sample_fixture(): (context)
    assert diff_map.line_states.get(5) != "added"  # return 42 (context)
    assert diff_map.line_states[6] == "added"  # trailing blank line


def test_diff_parser_added_line_starting_with_plus_plus(tmp_path):
    """An *added* line whose own content starts with "++" (e.g. `++counter;`)
    used to render as a "+++"-prefixed hunk line that a hand-rolled parser
    could mistake for a file header, corrupting the line map. PyDriller's
    diff_parsed gives structured (line_no, text) tuples directly, so this
    can no longer happen -- verified here against a real repo with exactly
    that content."""
    repo_path, commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/test_real.py",
                "content": "int preexisting;\n",
                "msg": "base",
            },
            {
                "path": "tests/test_real.py",
                "content": "int addedA;\n++weird;\nint preexisting;\nint addedD;\n",
                "msg": "add lines around preexisting content",
            },
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    diff_map = extractor._build_diff_line_maps(commit)["tests/test_real.py"]
    assert diff_map.line_states[1] == "added"
    assert diff_map.line_states[2] == "added"
    # The critical assertion: the truly unmodified preexisting line must not
    # be mismarked "added".
    assert diff_map.line_states.get(3) != "added"
    assert diff_map.line_states[4] == "added"


def test_diff_parser_added_line_looking_like_file_header(tmp_path):
    """An added line whose content happens to read like "+++ b/<path>" used
    to risk being misparsed by a hand-rolled parser as a bogus file-header
    line. _build_diff_line_maps() no longer parses header lines from text
    at all -- file identity comes from ModifiedFile.new_path directly -- so
    this is structurally no longer possible; verified here against a real
    repo with exactly that content, confirming only the one real file is
    present and its lines are attributed correctly."""
    repo_path, commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/test_real.py",
                "content": "import pytest\n",
                "msg": "base",
            },
            {
                "path": "tests/test_real.py",
                "content": "import pytest\n++ b/tests/decoy.py\ndef new_helper(): pass\n",
                "msg": "add lines including a file-header-shaped one",
            },
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    diff_maps = extractor._build_diff_line_maps(commit)
    assert list(diff_maps.keys()) == ["tests/test_real.py"]
    diff_map = diff_maps["tests/test_real.py"]
    assert diff_map.line_states.get(1) != "added"
    assert diff_map.line_states[2] == "added"
    assert diff_map.line_states[3] == "added"


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


def test_ast_aware_completeness_ignores_comments_inside_java_fixture(tmp_path):
    """Regression test: Java's tree-sitter grammar names comment nodes
    "line_comment"/"block_comment", not "comment" (unlike Python/JS/TS) --
    a check for the literal string "comment" silently never excluded Java
    comments, so a comment line landing on "context" in the diff (e.g. a
    generic comment the diff algorithm matched elsewhere) rejected an
    otherwise-100%-added Java fixture that the identical Python/JS/TS case
    would have accepted."""
    fixture_file = tmp_path / "SampleTest.java"
    fixture_file.write_text(
        "\n".join(
            [
                "import org.junit.Before;",
                "",
                "public class SampleTest {",
                "    @Before",
                "    public void setUp() {",
                "        // comment line",
                "        int value = 42;",
                "    }",
                "}",
            ]
        )
    )

    extractor = AgentFixtureExtractor(clones_dir=Path("/tmp"))
    fixture = SimpleNamespace(start_line=4, end_line=8)
    diff_map = DiffLineMap(
        {
            4: "added",
            5: "added",
            6: "context",
            7: "added",
            8: "added",
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


def test_added_test_file_detection_ignores_go_paths(tmp_path):
    repo_path, commit = _get_commit(
        tmp_path,
        [
            {
                "path": "connect-go/gen/proto/wg/cosmo/platform/v1/platform.pb.go",
                "content": "package v1\n",
                "msg": "base",
            },
        ],
    )
    # Add the remaining files in a second commit alongside the base file's repo.
    repo = tmp_path / "owner__repo"
    (repo / "pkg").mkdir(parents=True, exist_ok=True)
    (repo / "pkg" / "example_test.go").write_text("package pkg\n", encoding="utf-8")
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "tests" / "sample.spec.ts").write_text("test('x', () => {});\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "add go test and ts spec"],
        check=True,
        capture_output=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    commit = Git(str(repo_path)).get_commit(sha)

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    files = extractor._find_added_test_files(commit)

    assert "tests/sample.spec.ts" in files
    assert "pkg/example_test.go" not in files


def test_added_test_file_detection_handles_paths_with_spaces(tmp_path):
    """Regression test: the "diff --git a/<path> b/<path>" header packs both
    paths into one whitespace-split line, which is ambiguous when a path
    contains a space. Detection now reads the path from PyDriller's
    ModifiedFile.new_path directly (never parses the header line at all)."""
    repo_path, commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/my test.py",
                "content": "def test_thing():\n    pass\n",
                "msg": "add test file with a space in its path",
            },
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    files = extractor._find_added_test_files(commit)

    assert "tests/my test.py" in files


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
# Integration tests: purity gate inside _extract_from_commit()
# ──────────────────────────────────────────────────────────────


def test_extract_from_commit_skips_file_with_deletions(tmp_path):
    """When a test file's diff contains deletions, the purity gate blocks extraction."""
    repo_path, commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/test_skip_me.py",
                "content": "import pytest\nfrom old_module import thing\n\n@pytest.fixture\ndef my_fixture():\n    return 42\n",
                "msg": "base",
            },
            {
                "path": "tests/test_skip_me.py",
                "content": "import pytest\nfrom new_module import thing\n\n@pytest.fixture\ndef my_fixture():\n    return 42\n",
                "msg": "swap import",
            },
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_commit(
        repo_path=repo_path,
        repo_name="test/repo",
        commit=commit,
        commit_sha=commit.hash,
        agent_type="copilot",
    )

    # The file has a deletion line (the old import) → purity gate skips it
    assert len(fixtures) == 0


def test_extract_from_commit_skips_renamed_file(tmp_path):
    """When a test file is renamed, the purity gate blocks extraction."""
    repo_path, _first_commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/test_old_name.py",
                "content": "import pytest\n\n@pytest.fixture\ndef my_fixture():\n    return 42\n",
                "msg": "base",
            },
        ],
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "mv", "tests/test_old_name.py", "tests/test_renamed.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", "rename test file"],
        check=True,
        capture_output=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(repo_path), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    commit = Git(str(repo_path)).get_commit(sha)

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_commit(
        repo_path=repo_path,
        repo_name="test/repo",
        commit=commit,
        commit_sha=commit.hash,
        agent_type="copilot",
    )

    assert len(fixtures) == 0


def test_extract_from_commit_keeps_pure_addition_file(tmp_path):
    """When a test file has only added lines, extraction proceeds normally."""
    repo_path, commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef my_fixture():\n    return 42\n",
                "msg": "add pure test file",
            },
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_commit(
        repo_path=repo_path,
        repo_name="test/repo",
        commit=commit,
        commit_sha=commit.hash,
        agent_type="copilot",
    )

    # At least one fixture should be extracted (pytest fixture in a pure-add file)
    assert len(fixtures) >= 1
    fixture_names = {f["name"] for f in fixtures}
    assert "my_fixture" in fixture_names


def test_extract_from_commit_mixed_files_one_skipped_one_kept(tmp_path):
    """One file with deletions is skipped; a pure-addition file in the same commit is kept."""
    repo_path, _first_commit = _get_commit(
        tmp_path,
        [
            {
                "path": "tests/test_modified.py",
                "content": "import pytest\nfrom old_dep import helper\n@pytest.fixture\ndef mod_fixture():\n    return 99\n",
                "msg": "base",
            },
        ],
    )
    repo = repo_path
    (repo / "tests" / "test_modified.py").write_text(
        "import pytest\nfrom new_dep import helper\n@pytest.fixture\ndef mod_fixture():\n    return 99\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_pure.py").write_text(
        "@pytest.fixture\ndef pure_fixture():\n    return 1\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "modify one file, add another"],
        check=True,
        capture_output=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    commit = Git(str(repo)).get_commit(sha)

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_commit(
        repo_path=repo_path,
        repo_name="test/repo",
        commit=commit,
        commit_sha=commit.hash,
        agent_type="copilot",
    )

    # mod_fixture should be skipped (file had deletions), pure_fixture kept
    fixture_names = {f["name"] for f in fixtures}
    assert "pure_fixture" in fixture_names
    assert "mod_fixture" not in fixture_names


def test_extract_from_commit_empty_commit_returns_nothing(tmp_path):
    """A commit that touches no files (git commit --allow-empty) has no
    modified_files, so no test files can be found."""
    repo_path, _first_commit = _get_commit(
        tmp_path,
        [
            {"path": "tests/test_base.py", "content": "def test_x(): pass\n", "msg": "base"},
        ],
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "--allow-empty", "-m", "empty commit"],
        check=True,
        capture_output=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(repo_path), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    commit = Git(str(repo_path)).get_commit(sha)

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_commit(
        repo_path=repo_path,
        repo_name="test/repo",
        commit=commit,
        commit_sha=commit.hash,
        agent_type="copilot",
    )
    assert fixtures == []


def test_extract_from_agent_commits_filters_commits_before_start_date(tmp_path):
    """Commits older than start_date are excluded, using the real
    commit.author_date (a timezone-aware datetime from PyDriller), not a
    mocked/hand-parsed date string."""
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

    # A start_date far in the future must exclude every commit, regardless
    # of when the test actually ran.
    extractor = AgentFixtureExtractor(clones_dir=tmp_path, start_date="2999-01-01")
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
    )
    assert fixtures == []

    # A start_date far in the past must include it.
    extractor = AgentFixtureExtractor(clones_dir=tmp_path, start_date="1970-01-01")
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
    )
    assert len(fixtures) >= 1


# ──────────────────────────────────────────────────────────────
# Integration tests: purity gate inside _extract_from_agent_commits()
# ──────────────────────────────────────────────────────────────


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


# ──────────────────────────────────────────────────────────────
# Unit tests: commit_type classification (agent and human commits alike)
# attached by _extract_from_agent_commits()
# ──────────────────────────────────────────────────────────────


def test_extract_from_agent_commits_attaches_commit_type_for_agent_commit(tmp_path):
    """Fixtures from a real agent commit carry the classified commit_type."""
    sha = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 42\n",
                "msg": "test: add pure_fixture\n\nCo-authored-by: Claude <claude@anthropic.com>",
            }
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "claude"},
    )
    assert len(fixtures) >= 1
    assert all(f["commit_type"] == "test" for f in fixtures)


def test_extract_from_agent_commits_attaches_commit_type_for_human_commit_too(
    tmp_path,
):
    """human_corpus.py routes human commits through this method with
    agent_type='human' — Dataset B fixtures get commit_type classified the
    same way as Dataset A, so agent vs. human Conventional Commits adherence
    can be compared."""
    sha = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 42\n",
                "msg": "test: add pure_fixture",
            }
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "human"},
    )
    assert len(fixtures) >= 1
    assert all(f["commit_type"] == "test" for f in fixtures)


def test_extract_from_agent_commits_classifies_non_conventional_human_commit(
    tmp_path,
):
    """A human commit whose message doesn't follow Conventional Commits still
    gets classified — as 'none', not left unset."""
    sha = _init_repo_with_commits(
        tmp_path,
        [
            {
                "path": "tests/test_pure.py",
                "content": "import pytest\n\n@pytest.fixture\ndef pure_fixture():\n    return 42\n",
                "msg": "Added a new fixture for the parser",
            }
        ],
    )

    extractor = AgentFixtureExtractor(clones_dir=tmp_path)
    fixtures = extractor._extract_from_agent_commits(
        repo_name="owner__repo",
        commits={sha: "human"},
    )
    assert len(fixtures) >= 1
    assert all(f["commit_type"] == "none" for f in fixtures)
