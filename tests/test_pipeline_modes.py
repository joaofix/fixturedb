from types import SimpleNamespace
from pathlib import Path

import pipeline


class FakeCollector:
    def __init__(self, *args, **kwargs):
        self.run_called = False
        self.collect_inter_called = False

    def run(self, repos_per_language=None, language=None, **kwargs):
        self.run_called = True
        return SimpleNamespace(fixtures_collected=0, repos_passed_qc=0), Path("/tmp/db")

    def collect_inter_human(self, agent_repos=None, targets=None, **kwargs):
        self.collect_inter_called = True
        return SimpleNamespace(fixtures_collected=0, repos_passed_qc=0), Path("/tmp/db")


def make_args(mode="within"):
    return SimpleNamespace(
        repos_per_language=1,
        language=None,
        output_db=None,
        repo_qc_dir=Path("./"),
        test_commits_csv=None,
        mode=mode,
        workers=None,
    )


def test_cmd_human_within(monkeypatch):
    fake = FakeCollector()
    monkeypatch.setattr(pipeline, "HumanCorpusCollector", lambda **kwargs: fake)

    args = make_args(mode="within")
    rc = pipeline.cmd_human(args)
    assert rc == 0
    assert fake.run_called


def test_cmd_human_inter(monkeypatch):
    fake = FakeCollector()
    monkeypatch.setattr(pipeline, "HumanCorpusCollector", lambda **kwargs: fake)

    # stub select_human_corpus_repositories to return a dummy list
    monkeypatch.setattr(
        pipeline,
        "select_human_corpus_repositories",
        lambda repo_qc_dir, repos_per_language, language: [
            {"full_name": "owner/repo", "language": "py"}
        ],
    )

    args = make_args(mode="inter")
    rc = pipeline.cmd_human(args)
    assert rc == 0
    assert fake.collect_inter_called


def test_human_parser_default_test_commits_dir():
    args = pipeline.build_parser().parse_args(["human"])
    expected = pipeline.PROJECT_ROOT / "github-search-human" / "2025_test_commits"
    assert args.test_commits_csv == expected
