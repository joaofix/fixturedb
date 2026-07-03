from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import mock_open

import collection.phase_2_extract_pre_2021 as phase2


@dataclass
class DummyStats:
    repos_scanned: int = 0
    repos_passed_qc: int = 0
    fixtures_collected: int = 0
    repos_by_language: dict[str, int] | None = None
    qc_skip_reasons: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.repos_by_language is None:
            self.repos_by_language = {"python": 1}
        if self.qc_skip_reasons is None:
            self.qc_skip_reasons = {}


class DummyHumanCollector:
    def __init__(
        self, corpus_db_path, clones_dir=None, output_db=None, repo_qc_dir=None
    ):
        self.corpus_db_path = corpus_db_path
        self.clones_dir = clones_dir
        self.output_db = output_db
        self.repo_qc_dir = repo_qc_dir

    def run(self, repos_per_language=50, language=None, seed=42):
        self.run_args = {
            "repos_per_language": repos_per_language,
            "language": language,
            "seed": seed,
        }
        return DummyStats(
            repos_scanned=2, repos_passed_qc=1, fixtures_collected=3
        ), Path("/tmp/human.db")

    def collect_inter_human(self, agent_repos=None, workers=None):
        self.inter_human_args = {
            "agent_repos": agent_repos,
            "workers": workers,
        }
        return DummyStats(
            repos_scanned=2, repos_passed_qc=1, fixtures_collected=3
        ), Path("/tmp/human.db")


def _make_dummy_dataset_c_csv(out_dir: Path) -> Path:
    csv_path = out_dir / "dataset_c_sample.csv"
    csv_path.write_text(
        "repo_name,language,domain,clone_url\nowner/repo,python,data,https://github.com/owner/repo.git\n",
        encoding="utf-8",
    )
    return csv_path


def test_phase_2_main_uses_manual_repo_dataset(monkeypatch, tmp_path):
    captured = {}
    source_db = tmp_path / "source.db"
    source_db.write_text("stub", encoding="utf-8")
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    repo_qc_dir = tmp_path / "manual-repo-qc"
    repo_qc_dir.mkdir()
    output_db = tmp_path / "human.db"

    dummy_csv = _make_dummy_dataset_c_csv(tmp_path)

    # phase_2 hardcodes project_root / "fixtures-from-agents" to detect
    # Dataset C mode. Monkeypatch Path.exists so it sees our temp CSV.
    original_exists = Path.exists
    def _fake_exists(self):
        if self.name.startswith("dataset_c_"):
            return True
        return original_exists(self)
    monkeypatch.setattr(Path, "exists", _fake_exists)

    try:

        def collector_factory(*args, **kwargs):
            captured["collector_kwargs"] = kwargs
            return DummyHumanCollector(*args, **kwargs)

        captured_c = {}

        def dataset_c_factory(*args, **kwargs):
            captured_c["kwargs"] = kwargs
            return {
                "repos_persisted": 1,
                "fixtures_persisted": 2,
                "completed_repos": 1,
            }, output_db

        monkeypatch.setattr(phase2, "HumanCorpusCollector", collector_factory)
        import collection.dataset_c as dataset_c_mod

        monkeypatch.setattr(
            dataset_c_mod, "collect_dataset_c_fixtures", dataset_c_factory
        )
        monkeypatch.setattr(
            phase2.sys,
            "argv",
            [
                "phase_2_extract_pre_2021.py",
                "--source-db",
                str(source_db),
                "--clones-dir",
                str(clones_dir),
                "--output-db",
                str(output_db),
                "--repo-dir",
                str(repo_qc_dir),
                "--language", "python",
            ],
        )
        monkeypatch.setattr("builtins.open", mock_open())

        result = phase2.main()

        assert result == 0
        assert captured_c["kwargs"]["clones_dir"] == clones_dir
        assert captured_c["kwargs"]["output_db"] == output_db
    finally:
        dummy_csv.unlink(missing_ok=True)


def test_phase_2_multi_language_does_not_skip_due_to_existing_db(tmp_path, monkeypatch):
    """
    Dataset C must not skip extraction when the output DB already contains
    fixtures from a previous language run. The old blanket
    database_has_rows guard caused this.
    """
    source_db = tmp_path / "source.db"
    source_db.write_text("stub", encoding="utf-8")
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    repo_qc_dir = tmp_path / "manual-repo-qc"
    repo_qc_dir.mkdir()
    output_db = tmp_path / "human.db"

    dummy_csv = _make_dummy_dataset_c_csv(tmp_path)

    # Same monkeypatch for the second test
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

        import collection.dataset_c as dataset_c_mod

        monkeypatch.setattr(phase2, "HumanCorpusCollector", lambda *a, **k: None)
        monkeypatch.setattr(
            dataset_c_mod, "collect_dataset_c_fixtures", dataset_c_factory
        )
        monkeypatch.setattr(
            phase2.sys,
            "argv",
            [
                "phase_2_extract_pre_2021.py",
                "--source-db",
                str(source_db),
                "--clones-dir",
                str(clones_dir),
                "--output-db",
                str(output_db),
                "--repo-dir",
                str(repo_qc_dir),
                "--language",
                "javascript",
            ],
        )
        monkeypatch.setattr("builtins.open", mock_open())

        result = phase2.main()

        assert result == 0
        assert "kw" in dataset_c_called, (
            "collect_dataset_c_fixtures was not called; the multi-language guard "
            "is still blocking extraction when the DB already has rows"
        )
        assert dataset_c_called["kw"]["language"] == "javascript"
    finally:
        dummy_csv.unlink(missing_ok=True)
