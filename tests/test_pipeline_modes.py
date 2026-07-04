from pathlib import Path
from types import SimpleNamespace

import pipeline


class FakeCollector:
    def __init__(self, *args, **kwargs):
        self.run_called = False

    def run(self, repos_per_language=None, language=None, **kwargs):
        self.run_called = True
        return SimpleNamespace(fixtures_collected=0, repos_passed_qc=0), Path("/tmp/db")


def make_args():
    return SimpleNamespace(
        repos_per_language=1,
        language=None,
        output_db=None,
        repo_qc_dir=Path("./"),
        test_commits_csv=None,
        workers=None,
    )


def test_cmd_human_fixtures_within(monkeypatch):
    fake = FakeCollector()
    monkeypatch.setattr(pipeline, "HumanCorpusCollector", lambda **kwargs: fake)
    monkeypatch.setattr(pipeline, "_truncate_human_output_csvs", lambda: None)

    args = make_args()
    rc = pipeline.cmd_human_fixtures(args)
    assert rc == 0
    assert fake.run_called


def test_human_fixtures_parser_default_test_commits_dir():
    args = pipeline.build_parser().parse_args(["human-fixtures"])
    expected = pipeline.PROJECT_ROOT / "github-search-human" / "2025_test_commits"
    assert args.test_commits_csv == expected
