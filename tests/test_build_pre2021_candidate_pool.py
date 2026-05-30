import csv
from pathlib import Path

from collection.test_commit_filter import build_pre2021_candidate_pool


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        if not rows:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def test_build_pre2021_candidate_pool_basic(tmp_path):
    raw_dir = tmp_path / "raw"

    rows1 = [
        {"repo_name": "owner/repo1", "commit_date": "2020-01-01", "commit_sha": "a1"},
        {"repo_name": "owner/repo1", "commit_date": "2021-01-02", "commit_sha": "a2"},
        {"repo_name": "owner/repo2", "commit_date": "2019-12-31", "commit_sha": "b1"},
        {"repo_name": "", "commit_date": "2020-01-01", "commit_sha": "x"},
        {"repo_name": "owner/repo3", "commit_date": "", "commit_sha": "y"},
    ]

    write_csv(raw_dir / "part1_commit.csv", rows1)

    # Nested file to exercise globbing
    rows2 = [
        {"full_name": "owner/repo4", "commit_date": "2020-12-31", "commit_sha": "c1"}
    ]
    write_csv(raw_dir / "sub" / "more_commit.csv", rows2)

    candidates = build_pre2021_candidate_pool(raw_dir, cutoff_date="2020-12-31")

    # owner/repo1 has only a1 included (a2 is after cutoff)
    assert "owner/repo1" in candidates
    assert any(r["commit_sha"] == "a1" for r in candidates["owner/repo1"])
    assert not any(r["commit_sha"] == "a2" for r in candidates["owner/repo1"])

    # owner/repo2 included
    assert "owner/repo2" in candidates
    assert candidates["owner/repo2"][0]["commit_sha"] == "b1"

    # owner/repo3 missing commit_date -> excluded
    assert "owner/repo3" not in candidates

    # owner/repo4 from nested file with key full_name should be present
    assert "owner/repo4" in candidates
    assert candidates["owner/repo4"][0]["commit_sha"] == "c1"
