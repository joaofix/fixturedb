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

    def to_dict(self) -> dict:
        return {
            "fixtures_collected": self.fixtures_collected,
            "repos_passed_qc": self.repos_passed_qc,
            "agent_commits_found": self.agent_commits_found,
        }


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
        return DummyStats(fixtures_collected=3, repos_passed_qc=2), Path(
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
            fixtures_collected=5, repos_passed_qc=4, agent_commits_found=9
        ), Path("/tmp/agent.db")


class DummyComparison:
    def __init__(self):
        self.control_variable_summary = {
            "total_tests": 2,
            "balanced_count": 2,
            "imbalanced_count": 0,
        }
        self.limitations = []


class DummyComparator:
    def __init__(self, db_path):
        self.db_path = db_path

    def run(self, human_stats=None, agent_stats=None):
        self.human_stats = human_stats
        self.agent_stats = agent_stats
        return DummyComparison()

    def save_report(self, comparison):
        self.comparison = comparison
        return Path("/tmp/between-group-report.json")


def test_full_command_uses_manual_dataset_inputs(monkeypatch):
    captured = {}

    def human_factory(*args, **kwargs):
        captured["human_kwargs"] = kwargs
        return DummyHumanCollector(*args, **kwargs)

    def agent_factory(*args, **kwargs):
        captured["agent_kwargs"] = kwargs
        return DummyAgentCollector(*args, **kwargs)

    def comparator_factory(*args, **kwargs):
        captured["comparator_kwargs"] = kwargs
        return DummyComparator(*args, **kwargs)

    monkeypatch.setattr(pipeline, "HumanCorpusCollector", human_factory)
    monkeypatch.setattr(pipeline, "AgentCorpusCollector", agent_factory)
    monkeypatch.setattr(pipeline, "BetweenGroupComparator", comparator_factory)

    args = SimpleNamespace(
        output_db=Path("/tmp/between-group.db"),
        github_token="token-123",
        repos_per_language=7,
        language="python",
        repo_qc_dir=Path("/data/manual/repo-qc"),
        commit_qc_dir=Path("/data/manual/commit-qc"),
        log_file=None,
    )

    result = pipeline.cmd_full(args)

    assert result == 0
    assert captured["human_kwargs"]["repo_qc_dir"] == Path("/data/manual/repo-qc")
    assert captured["agent_kwargs"]["repo_qc_dir"] == Path("/data/manual/repo-qc")
    assert captured["agent_kwargs"]["commit_qc_dir"] == Path("/data/manual/commit-qc")
    assert captured["comparator_kwargs"]["db_path"] == Path("/tmp/between-group.db")
