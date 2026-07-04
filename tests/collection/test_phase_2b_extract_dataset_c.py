from __future__ import annotations

from pathlib import Path
from unittest.mock import mock_open

import collection.phase_2b_extract_dataset_c as phase2b


def _make_dummy_dataset_c_csv(out_dir: Path) -> Path:
    csv_path = out_dir / "dataset_c_sample.csv"
    csv_path.write_text(
        "repo_name,language,domain,clone_url\nowner/repo,python,data,https://github.com/owner/repo.git\n",
        encoding="utf-8",
    )
    return csv_path


def test_phase_2b_main_uses_manual_repo_dataset(monkeypatch, tmp_path):
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    output_db = tmp_path / "human.db"

    dummy_csv = _make_dummy_dataset_c_csv(tmp_path)

    # phase_2b hardcodes project_root / "fixtures-from-agents" to locate
    # dataset_c_*.csv samples. Monkeypatch Path.exists so it sees our temp CSV.
    original_exists = Path.exists

    def _fake_exists(self):
        if self.name.startswith("dataset_c_"):
            return True
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", _fake_exists)

    try:
        captured_c = {}

        def dataset_c_factory(*args, **kwargs):
            captured_c["kwargs"] = kwargs
            return {
                "repos_persisted": 1,
                "fixtures_persisted": 2,
                "completed_repos": 1,
            }, output_db

        monkeypatch.setattr(phase2b, "collect_dataset_c_fixtures", dataset_c_factory)
        monkeypatch.setattr(
            phase2b.sys,
            "argv",
            [
                "phase_2b_extract_dataset_c.py",
                "--clones-dir",
                str(clones_dir),
                "--output-db",
                str(output_db),
                "--language",
                "python",
            ],
        )
        monkeypatch.setattr("builtins.open", mock_open())

        result = phase2b.main()

        assert result == 0
        assert captured_c["kwargs"]["clones_dir"] == clones_dir
        assert captured_c["kwargs"]["output_db"] == output_db
    finally:
        dummy_csv.unlink(missing_ok=True)


def test_phase_2b_multi_language_does_not_skip_due_to_existing_db(
    tmp_path, monkeypatch
):
    """
    Dataset C must not skip extraction when the output DB already contains
    fixtures from a previous language run. The old blanket
    database_has_rows guard caused this.
    """
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    output_db = tmp_path / "human.db"

    dummy_csv = _make_dummy_dataset_c_csv(tmp_path)

    original_exists = Path.exists

    def _fake_exists2(self):
        if self.name.startswith("dataset_c_"):
            return True
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", _fake_exists2)
    try:
        import sqlite3

        conn = sqlite3.connect(str(output_db))
        conn.execute("CREATE TABLE IF NOT EXISTS fixtures (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO fixtures (id) VALUES (1)")
        conn.execute("INSERT INTO fixtures (id) VALUES (2)")
        conn.commit()
        conn.close()

        dataset_c_called = {}

        def dataset_c_factory(*args, **kwargs):
            dataset_c_called["kw"] = kwargs
            return {
                "repos_persisted": 0,
                "fixtures_persisted": 0,
                "completed_repos": 0,
            }, output_db

        monkeypatch.setattr(phase2b, "collect_dataset_c_fixtures", dataset_c_factory)
        monkeypatch.setattr(
            phase2b.sys,
            "argv",
            [
                "phase_2b_extract_dataset_c.py",
                "--clones-dir",
                str(clones_dir),
                "--output-db",
                str(output_db),
                "--language",
                "javascript",
            ],
        )
        monkeypatch.setattr("builtins.open", mock_open())

        result = phase2b.main()

        assert result == 0
        assert "kw" in dataset_c_called, (
            "collect_dataset_c_fixtures was not called; the multi-language guard "
            "is still blocking extraction when the DB already has rows"
        )
        assert dataset_c_called["kw"]["language"] == "javascript"
    finally:
        dummy_csv.unlink(missing_ok=True)
