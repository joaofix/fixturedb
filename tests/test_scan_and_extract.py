from pathlib import Path
from types import SimpleNamespace

from collection.human_corpus import HumanCorpusCollector


def test_scan_and_extract_filters_and_formats(tmp_path, monkeypatch):
    # Setup minimal collector
    collector = HumanCorpusCollector(
        corpus_db_path=tmp_path / "c.db", clones_dir=tmp_path / "clones"
    )

    # Fake commit role objects
    commits = [
        SimpleNamespace(
            commit_sha="a1",
            commit_role="human",
            is_test_commit=True,
            commit_date="2020-01-01",
            agent_type=None,
            test_files=["tests/test_a.py"],
        ),
        SimpleNamespace(
            commit_sha="b2",
            commit_role="bot",
            is_test_commit=True,
            commit_date="2020-01-02",
            agent_type="paper_agent",
            test_files=["tests/test_b.py"],
        ),
    ]

    class FakeScanner:
        def scan_repo_commit_roles(
            self, repo_path, start_date, language, detect_test_files=True
        ):
            return commits

    class FakeExtractor:
        def _extract_from_agent_commits(self, repo_name, commits, stats=None):
            # Only produce fixtures for the human commit
            return [
                {
                    "name": "f1",
                    "file_path": "tests/test_a.py",
                    "start_line": 1,
                    "end_line": 5,
                    "is_complete_addition": 1,
                    "commit_sha": "a1",
                },
                {
                    "name": "f2",
                    "file_path": "tests/test_a.py",
                    "start_line": 10,
                    "end_line": 15,
                    "is_complete_addition": 0,
                    "commit_sha": "a1",
                },
            ]

    scanner = FakeScanner()
    extractor = FakeExtractor()

    test_rows, fixtures, adoption, _accepted, _rejected = collector._scan_and_extract(
        Path("/tmp"), "python", "owner/repo", scanner, extractor
    )

    # Only one test_row (human) should be included
    assert len(test_rows) == 1
    assert test_rows[0]["commit_sha"] == "a1"

    # Fixtures should include only the complete addition
    assert len(fixtures) == 1
    assert fixtures[0]["name"] == "f1"

    # Adoption intensity should be computed (no_commits for non-git path)
    assert adoption == "no_commits"
