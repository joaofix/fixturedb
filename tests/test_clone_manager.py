from pathlib import Path

from collection import clone_manager as cm
from collection.temp_clone import _output_requests_credentials


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
