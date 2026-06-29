from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
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


def test_phase_2_main_uses_manual_repo_dataset(monkeypatch, tmp_path):
    captured = {}
    source_db = tmp_path / "source.db"
    source_db.write_text("stub", encoding="utf-8")
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    repo_qc_dir = tmp_path / "manual-repo-qc"
    repo_qc_dir.mkdir()
    output_db = tmp_path / "human.db"

    def collector_factory(*args, **kwargs):
        captured["collector_kwargs"] = kwargs
        return DummyHumanCollector(*args, **kwargs)

    monkeypatch.setattr(phase2, "HumanCorpusCollector", collector_factory)
    monkeypatch.setattr(phase2, "database_has_rows", lambda *args, **kwargs: False)
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
        ],
    )
    monkeypatch.setattr("builtins.open", mock_open())

    result = phase2.main()

    assert result == 0
    assert captured["collector_kwargs"]["corpus_db_path"] == source_db
    assert captured["collector_kwargs"]["clones_dir"] == clones_dir
    assert captured["collector_kwargs"]["output_db"] == output_db
    assert captured["collector_kwargs"]["repo_qc_dir"] == repo_qc_dir
