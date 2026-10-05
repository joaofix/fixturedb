import pytest
from pathlib import Path

from collection import ephemeral_clone as cm
from collection.clone_primitives import _output_requests_credentials


def test_output_requests_credentials():
    """Test that credential prompt patterns are correctly detected."""
    assert _output_requests_credentials("Username for 'https://github.com':")
    assert _output_requests_credentials("Password for 'https://github.com':")
    assert _output_requests_credentials(
        "Personal access token for 'https://github.com':"
    )
    assert _output_requests_credentials("repository not found")
    assert _output_requests_credentials("Repository not found")
    assert _output_requests_credentials("Remote: Repository not found")
    assert _output_requests_credentials("fatal: could not read Username")
    assert _output_requests_credentials(
        "Authentication failed for 'https://github.com':"
    )
    assert _output_requests_credentials("PERMISSION_DENIED")
    assert _output_requests_credentials("does not exist")

    assert not _output_requests_credentials(
        "fatal: unable to access 'https://github.com': The requested URL returned error: 404"
    )
    assert not _output_requests_credentials("fatal: not a git repository")
    assert not _output_requests_credentials("")
    assert not _output_requests_credentials("Successfully cloned repository")


def test_clone_with_function_success(tmp_path):
    target = tmp_path / "owner__repo"

    def fake_clone(url, td: Path):
        td.mkdir(parents=True, exist_ok=True)
        (td / "dummy.txt").write_text("ok")
        return True

    with cm.clone_with_function(
        fake_clone, "https://example.com/repo.git", target
    ) as repo_path:
        assert repo_path is not None
        assert repo_path.exists()
        assert (repo_path / "dummy.txt").read_text() == "ok"

    # cleanup should have removed the directory
    assert not target.exists()


def test_clone_with_function_failure(tmp_path):
    target = tmp_path / "owner__repo"

    def fake_clone_fail(url, td: Path):
        return False

    with cm.clone_with_function(fake_clone_fail, "url", target) as repo_path:
        assert repo_path is None

    assert not target.exists()


def test_clone_with_function_cleans_up_partial_dir_on_failure(tmp_path):
    """Regression: clone_repo_for_commit_scan (the real clone_fn used
    everywhere) calls target_dir.mkdir() before running `git clone`, then
    returns False on failure (timeout, 404, etc). The old code only ran
    rmtree in the success branch, so this partial directory was left behind
    permanently -- and since callers reuse a fixed, non-tempdir path keyed
    by repo name (not a fresh tempdir), the next attempt's `git clone`
    would then fail with "destination path already exists", permanently
    blocking that repo from ever cloning successfully again."""
    target = tmp_path / "owner__repo"

    def fake_clone_fail_after_mkdir(url, td: Path):
        td.mkdir(parents=True, exist_ok=True)
        (td / ".git").mkdir()  # partial clone state, like an interrupted git clone
        return False

    with cm.clone_with_function(
        fake_clone_fail_after_mkdir, "url", target
    ) as repo_path:
        assert repo_path is None

    assert not target.exists()


def test_clone_with_function_disk_guard(monkeypatch, tmp_path):
    target = tmp_path / "owner__repo"

    def fake_clone(url, td: Path):
        td.mkdir(parents=True)
        return True

    # force the internal free-space check to fail
    monkeypatch.setattr(cm, "ensure_free_space", lambda path, n: False)

    with cm.clone_with_function(
        fake_clone, "url", target, min_free_bytes=10**12
    ) as repo_path:
        assert repo_path is None

    assert not target.exists()


def test_temp_clone_commit_history_success(monkeypatch, tmp_path):
    # simulate clone_to_tempdir creating a repo under a temp root
    temp_root = tmp_path / "tmproot"
    repo_path = temp_root / "owner__repo"
    temp_root.mkdir()
    repo_path.mkdir()

    def fake_clone_to_tempdir(
        repo_full_name, clone_url, clone_args, *, timeout, prefix
    ):
        return repo_path, temp_root

    monkeypatch.setattr(cm, "clone_to_tempdir", fake_clone_to_tempdir)

    with cm.temp_clone_commit_history(
        "https://example.com/repo.git", "owner/repo", prefix="x", timeout=1
    ) as rp:
        assert rp == repo_path
        assert rp.exists()

    # cleanup should remove the temp root
    assert not temp_root.exists()


def test_temp_clone_commit_history_failure(monkeypatch):
    monkeypatch.setattr(cm, "clone_to_tempdir", lambda *a, **k: (None, None))

    with cm.temp_clone_commit_history(
        "https://example.com/repo.git", "owner/repo"
    ) as rp:
        assert rp is None


class TestSetMaxConcurrentClones:
    """The clone limit is a run-time setting, not only the environment variable."""

    def test_limit_is_the_number_of_clones_allowed_in_flight(self):
        from collection import ephemeral_clone

        original = ephemeral_clone._CLONE_SEMAPHORE
        try:
            ephemeral_clone.set_max_concurrent_clones(3)
            sem = ephemeral_clone._CLONE_SEMAPHORE
            assert [sem.acquire(blocking=False) for _ in range(4)] == [True, True, True, False]
        finally:
            ephemeral_clone._CLONE_SEMAPHORE = original

    def test_rejects_a_limit_below_one(self):
        from collection import ephemeral_clone

        with pytest.raises(ValueError):
            ephemeral_clone.set_max_concurrent_clones(0)

    def test_discover_commits_run_applies_the_limit(self, tmp_path, monkeypatch):
        from collection.repository_quality_control import agent_commit_counter

        applied = []
        monkeypatch.setattr(agent_commit_counter, "set_max_concurrent_clones", applied.append)
        monkeypatch.setattr(agent_commit_counter, "read_config_positive_rows", lambda input_dir: [])

        agent_commit_counter.run(
            input_dir=tmp_path,
            output_dir=tmp_path / "out",
            progress_db_path=tmp_path / "p.db",
            max_concurrent_clones=7,
        )
        assert applied == [7]

    def test_discover_commits_run_keeps_the_environment_default_when_not_given(self, tmp_path, monkeypatch):
        from collection.repository_quality_control import agent_commit_counter

        applied = []
        monkeypatch.setattr(agent_commit_counter, "set_max_concurrent_clones", applied.append)
        monkeypatch.setattr(agent_commit_counter, "read_config_positive_rows", lambda input_dir: [])

        agent_commit_counter.run(input_dir=tmp_path, output_dir=tmp_path / "out", progress_db_path=tmp_path / "p.db")
        assert applied == []


class TestCloneFilterArgument:
    """The partial-clone filter is a parameter. The default keeps file contents,
    and a commit-only step can ask for no blobs."""

    def _captured_args(self, **kwargs):
        from unittest.mock import patch

        seen = []

        def fake_clone(repo_full_name, clone_url, clone_args, **_):
            seen.append(list(clone_args))
            return None, None

        with patch.object(cm, "clone_to_tempdir", side_effect=fake_clone):
            with cm.temp_clone_commit_history("https://example.invalid/o/r.git", "o/r", **kwargs) as path:
                assert path is None
        return seen[0]

    def test_default_keeps_blobs_under_ten_megabytes(self):
        assert "--filter=blob:limit=10m" in self._captured_args()

    def test_commit_only_clone_passes_blob_none(self):
        args = self._captured_args(clone_filter="--filter=blob:none")
        assert "--filter=blob:none" in args
        assert "--filter=blob:limit=10m" not in args


class TestDiscoverCommitsCloneFilter:
    def test_discover_commits_clones_without_blobs(self, monkeypatch):
        from contextlib import contextmanager

        from collection.repository_quality_control import agent_commit_counter as acc

        captured = {}

        @contextmanager
        def fake_temp_clone(clone_url, repo_full_name, **kwargs):
            captured.update(kwargs)
            yield None

        monkeypatch.setattr(acc, "temp_clone_commit_history", fake_temp_clone)
        with pytest.raises(acc.RepoUnavailable):
            acc.process_repo_for_commits(
                {"repo_name": "o/r", "clone_url": "https://example.invalid/o/r.git", "language": "python"},
                "2025-01-01",
            )
        assert captured["clone_filter"] == "--filter=blob:none"
