from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import collection.phase_3_extract_agent as phase3


@dataclass
class DummyStats:
    repos_scanned: int = 0
    repos_passed_qc: int = 0
    fixtures_collected: int = 0
    agent_commits_found: int = 0


class DummyAgentCollector:
    def __init__(
        self, output_db=None, repo_qc_dir=None, commit_qc_dir=None, github_token=None
    ):
        self.output_db = output_db
        self.repo_qc_dir = repo_qc_dir
        self.commit_qc_dir = commit_qc_dir
        self.github_token = github_token

    def run(self, repos_per_language=50, languages=None, language=None):
        self.run_args = {
            "repos_per_language": repos_per_language,
            "languages": languages,
            "language": language,
        }
        return DummyStats(
            repos_scanned=4,
            repos_passed_qc=2,
            fixtures_collected=8,
            agent_commits_found=6,
        ), Path("/tmp/agent.db")


def test_phase_3_main_uses_manual_repo_and_commit_datasets(monkeypatch, tmp_path):
    captured = {}
    repo_qc_dir = tmp_path / "manual-repo-qc"
    repo_qc_dir.mkdir()
    commit_qc_dir = tmp_path / "manual-commit-qc"
    commit_qc_dir.mkdir()
    output_db = tmp_path / "agent.db"

    def collector_factory(*args, **kwargs):
        captured["collector_kwargs"] = kwargs
        collector = DummyAgentCollector(*args, **kwargs)
        captured["collector"] = collector
        return collector

    monkeypatch.setattr(phase3, "AgentCorpusCollector", collector_factory)
    monkeypatch.setattr(phase3, "database_has_rows", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        phase3.sys,
        "argv",
        [
            "phase_3_extract_agent.py",
            "--output-db",
            str(output_db),
            "--repo-qc-dir",
            str(repo_qc_dir),
            "--commit-qc-dir",
            str(commit_qc_dir),
            "--languages",
            "java",
            "javascript",
        ],
    )

    result = phase3.main()

    assert result == 0
    assert captured["collector_kwargs"]["output_db"] == output_db
    assert captured["collector_kwargs"]["repo_qc_dir"] == repo_qc_dir
    assert captured["collector_kwargs"]["commit_qc_dir"] == commit_qc_dir
    assert captured["collector"].run_args["languages"] == ["java", "javascript"]
