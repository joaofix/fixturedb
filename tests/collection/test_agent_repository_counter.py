from __future__ import annotations

import csv
import gzip
from pathlib import Path

import collection.repository_quality_control.agent_repository_counter as qc


def _write_raw_csv(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_read_repo_list_can_filter_multiple_languages(monkeypatch, tmp_path):
    raw_dir = tmp_path / "github-search-raw"
    raw_dir.mkdir()

    _write_raw_csv(
        raw_dir / "java.csv.gz",
        [
            {
                "name": "owner/java-repo",
                "mainLanguage": "java",
                "stargazers": "10",
                "contributors": "2",
            }
        ],
    )
    _write_raw_csv(
        raw_dir / "javascript.csv.gz",
        [
            {
                "name": "owner/javascript-repo",
                "mainLanguage": "javascript",
                "stargazers": "20",
                "contributors": "3",
            }
        ],
    )
    _write_raw_csv(
        raw_dir / "python.csv.gz",
        [
            {
                "name": "owner/python-repo",
                "mainLanguage": "python",
                "stargazers": "30",
                "contributors": "4",
            }
        ],
    )

    monkeypatch.setattr(qc, "GITHUB_SEARCH_RAW_DIR", raw_dir)

    repos = qc.read_repo_list(languages=["java", "javascript"])

    assert [repo["full_name"] for repo in repos] == [
        "owner/java-repo",
        "owner/javascript-repo",
    ]
    assert {repo["language"] for repo in repos} == {"java", "javascript"}
