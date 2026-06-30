import csv

from collection.test_commit_filter import build_pre2021_candidate_pool


def test_build_pre2021_candidate_pool(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    csv_path = raw_dir / "sample_commit_rows.csv"
    rows = [
        {"repo_name": "owner/repo1", "commit_sha": "a1", "commit_date": "2020-01-01"},
        {"repo_name": "owner/repo1", "commit_sha": "a2", "commit_date": "2021-06-01"},
        {"repo_name": "owner/repo2", "commit_sha": "b1", "commit_date": "2019-12-31"},
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["repo_name", "commit_sha", "commit_date"]
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    pool = build_pre2021_candidate_pool(raw_dir, cutoff_date="2020-12-31")

    # repo1 should include only the 2020-01-01 commit, repo2 the 2019-12-31 commit
    assert "owner/repo1" in pool
    assert any(r["commit_sha"] == "a1" for r in pool["owner/repo1"])
    assert not any(r["commit_sha"] == "a2" for r in pool["owner/repo1"])
    assert "owner/repo2" in pool
    assert any(r["commit_sha"] == "b1" for r in pool["owner/repo2"])
