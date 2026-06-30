from pathlib import Path

from collection import clone_manager as cm


def test_clone_with_throttle_success(tmp_path: Path):
    target = tmp_path / "owner__repo"

    def fake_clone(url, td: Path):
        td.mkdir(parents=True, exist_ok=True)
        (td / "dummy.txt").write_text("ok")
        return True

    with cm.clone_with_throttle(fake_clone, "url", target) as repo_path:
        assert repo_path is not None
        assert (repo_path / "dummy.txt").read_text() == "ok"


def test_clone_with_throttle_disk_guard(monkeypatch, tmp_path: Path):
    target = tmp_path / "owner__repo"

    def fake_clone(url, td: Path):
        td.mkdir(parents=True)
        return True

    monkeypatch.setattr(cm, "ensure_free_space", lambda path, n: False)

    with cm.clone_with_throttle(
        fake_clone, "url", target, min_free_bytes=10**12
    ) as repo_path:
        assert repo_path is None
