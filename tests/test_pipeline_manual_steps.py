from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pipeline


@dataclass
class DummyStats:
    fixtures_collected: int = 0
    repos_passed_qc: int = 0
    agent_commits_found: int = 0


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
        return DummyStats(fixtures_collected=11, repos_passed_qc=6), Path(
            "/tmp/human.db"
        )


class DummyAgentCollector:
    def __init__(
        self,
        github_token=None,
        output_db=None,
        repo_qc_dir=None,
        commit_qc_dir=None,
        clones_dir=None,
    ):
        self.github_token = github_token
        self.output_db = output_db
        self.repo_qc_dir = repo_qc_dir
        self.commit_qc_dir = commit_qc_dir
        self.clones_dir = clones_dir

    def run(self, repos_per_language=50, language=None):
        self.run_args = {
            "repos_per_language": repos_per_language,
            "language": language,
        }
        return DummyStats(
            fixtures_collected=22, repos_passed_qc=7, agent_commits_found=13
        ), Path("/tmp/agent.db")


def test_human_command_uses_repo_dataset_override(monkeypatch):
    captured = {}

    def human_factory(*args, **kwargs):
        captured["human_kwargs"] = kwargs
        return DummyHumanCollector(*args, **kwargs)

    monkeypatch.setattr(pipeline, "HumanCorpusCollector", human_factory)

    args = SimpleNamespace(
        output_db=Path("/tmp/human-out.db"),
        repos_per_language=4,
        language="python",
        repo_qc_dir=Path("/data/manual/repo-qc"),
    )

    result = pipeline.cmd_human(args)

    assert result == 0
    assert captured["human_kwargs"]["repo_qc_dir"] == Path("/data/manual/repo-qc")


def test_agent_command_uses_repo_and_commit_dataset_overrides(monkeypatch):
    captured = {}

    def agent_factory(*args, **kwargs):
        captured["agent_kwargs"] = kwargs
        return DummyAgentCollector(*args, **kwargs)

    monkeypatch.setattr(pipeline, "AgentCorpusCollector", agent_factory)

    args = SimpleNamespace(
        github_token="token-123",
        output_db=Path("/tmp/agent-out.db"),
        repos_per_language=5,
        language="typescript",
        repo_qc_dir=Path("/data/manual/repo-qc"),
        commit_qc_dir=Path("/data/manual/commit-qc"),
    )

    result = pipeline.cmd_agent(args)

    assert result == 0
    assert captured["agent_kwargs"]["repo_qc_dir"] == Path("/data/manual/repo-qc")
    assert captured["agent_kwargs"]["commit_qc_dir"] == Path("/data/manual/commit-qc")
