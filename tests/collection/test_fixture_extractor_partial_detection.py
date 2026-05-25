from pathlib import Path
from types import SimpleNamespace
from threading import Lock, Thread
import time
import subprocess

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

    monkeypatch.setattr("collection.fixture_extractor.subprocess.run", fake_run)
    monkeypatch.setattr(
        "collection.fixture_extractor.sleep",
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
