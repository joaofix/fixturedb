"""Unit tests for select_dataset_c_repos.py.

Replaces sample_proportional_repos.py's role: filters github-search-raw/ by
a fixed creation-date window, no stratification, no cap. See
internal-docs/methodology-improvements/dataset-c-repo-selection.md.
"""

from __future__ import annotations

import csv
import gzip
from pathlib import Path

from collection.select_dataset_c_repos import (
    filter_known_duplicates,
    select_repos,
    write_per_language_files,
)


def _write_gz_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class TestSelectRepos:
    def test_filters_by_creation_date_window(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {"id": "1", "name": "o/before-window", "createdAt": "2015-12-31"},
                {"id": "2", "name": "o/at-window-start", "createdAt": "2016-01-01"},
                {"id": "3", "name": "o/inside-window", "createdAt": "2018-06-15"},
                {"id": "4", "name": "o/at-window-end", "createdAt": "2020-12-31"},
                {"id": "5", "name": "o/after-window", "createdAt": "2021-01-01"},
            ],
        )

        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        names = {r["repo_name"] for r in selected}
        assert names == {
            "o/at-window-start",
            "o/inside-window",
            "o/at-window-end",
        }

    def test_boundary_dates_are_inclusive(self, tmp_path):
        """created == min_created and created == cutoff_date must both be
        kept -- an off-by-one here would silently shrink the window."""
        _write_gz_csv(
            tmp_path / "java.csv.gz",
            [
                {"id": "1", "name": "o/exact-start", "createdAt": "2016-01-01T00:00:00"},
                {"id": "2", "name": "o/exact-end", "createdAt": "2020-12-31T23:59:59"},
            ],
        )
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        names = {r["repo_name"] for r in selected}
        assert names == {"o/exact-start", "o/exact-end"}

    def test_skips_missing_or_malformed_rows(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {"id": "1", "name": "", "createdAt": "2018-01-01"},
                {"id": "2", "name": "no-slash-name", "createdAt": "2018-01-01"},
                {"id": "3", "name": "o/no-date", "createdAt": ""},
                {"id": "4", "name": "o/valid", "createdAt": "2018-01-01"},
            ],
        )
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        assert [r["repo_name"] for r in selected] == ["o/valid"]

    def test_skips_rows_with_missing_or_invalid_github_id(self, tmp_path):
        """github_id is the repositories table's UNIQUE key downstream --
        a row without a real one must be dropped here rather than silently
        defaulting to something that would collide with every other repo.
        See internal-docs/methodology-improvements/dataset-c-repo-selection.md."""
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {"id": "", "name": "o/no-id", "createdAt": "2018-01-01"},
                {"id": "not-a-number", "name": "o/bad-id", "createdAt": "2018-01-01"},
                {"id": "42", "name": "o/good-id", "createdAt": "2018-01-01"},
            ],
        )
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        assert [r["repo_name"] for r in selected] == ["o/good-id"]
        assert selected[0]["github_id"] == 42

    def test_uses_main_language_falling_back_to_filename(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {"id": "1", "name": "o/has-main-lang", "createdAt": "2018-01-01", "mainLanguage": "Python"},
                {"id": "2", "name": "o/no-lang-field", "createdAt": "2018-01-01"},
            ],
        )
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        by_name = {r["repo_name"]: r for r in selected}
        assert by_name["o/has-main-lang"]["language"] == "python"
        assert by_name["o/no-lang-field"]["language"] == "python"  # from filename

    def test_clone_url_is_constructed(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [{"id": "1", "name": "owner/repo", "createdAt": "2018-01-01"}],
        )
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        assert selected[0]["clone_url"] == "https://github.com/owner/repo.git"

    def test_aggregates_multiple_files(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [{"id": "1", "name": "o/py-repo", "createdAt": "2018-01-01"}],
        )
        _write_gz_csv(
            tmp_path / "java.csv.gz",
            [{"id": "2", "name": "o/java-repo", "createdAt": "2019-01-01"}],
        )
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        names = {r["repo_name"] for r in selected}
        assert names == {"o/py-repo", "o/java-repo"}

    def test_no_stratification_no_cap(self, tmp_path):
        """Every qualifying repo is kept -- no per-language or per-domain
        cap, unlike the deactivated sample_proportional_repos.py."""
        rows = [
            {"id": str(i), "name": f"o/repo{i}", "createdAt": "2018-01-01"}
            for i in range(50)
        ]
        _write_gz_csv(tmp_path / "python.csv.gz", rows)
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        assert len(selected) == 50

    def test_github_id_is_distinct_per_repo(self, tmp_path):
        """Regression: github_id is the repositories table's UNIQUE key.
        If this ever collapsed to a shared/default value again, every repo
        in a real collection run would silently collide onto one DB row --
        found via a real end-to-end toy collection, not a unit test, since
        every dataset_c.py unit test mocks _process_repo entirely."""
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {"id": "100", "name": "o/repo-a", "createdAt": "2018-01-01"},
                {"id": "200", "name": "o/repo-b", "createdAt": "2018-01-01"},
            ],
        )
        selected = select_repos(
            raw_dir=tmp_path, min_created="2016-01-01", cutoff_date="2020-12-31"
        )
        github_ids = {r["repo_name"]: r["github_id"] for r in selected}
        assert github_ids == {"o/repo-a": 100, "o/repo-b": 200}
        assert len(set(github_ids.values())) == 2  # no collision


class TestWritePerLanguageFiles:
    def test_writes_per_language_and_combined(self, tmp_path):
        selected = [
            {"repo_name": "o/py1", "language": "python", "clone_url": "u1", "github_id": 1},
            {"repo_name": "o/py2", "language": "python", "clone_url": "u2", "github_id": 2},
            {"repo_name": "o/java1", "language": "java", "clone_url": "u3", "github_id": 3},
        ]
        out_dir = tmp_path / "out"
        counts = write_per_language_files(selected, out_dir)

        assert counts == {"python": 2, "java": 1}
        assert (out_dir / "python_repo.csv").exists()
        assert (out_dir / "java_repo.csv").exists()
        assert (out_dir / "all.csv").exists()

    def test_output_schema_includes_github_id(self, tmp_path):
        """No domain classification step happens here (unlike
        sample_proportional_repos.py's output), but github_id is required
        -- see test_github_id_is_distinct_per_repo for why. created_at/
        topics/stars are carried through as raw inputs for
        compute_repo_metadata(), which dataset_c.py calls downstream at
        fixture-persist time -- see agent_repository_counter.py's identical
        fix (and dataset_c.py's) for why they can't be dropped here."""
        selected = [
            {"repo_name": "o/r", "language": "python", "clone_url": "u", "github_id": 1}
        ]
        out_dir = tmp_path / "out"
        write_per_language_files(selected, out_dir)

        with (out_dir / "all.csv").open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        assert header == [
            "repo_name",
            "language",
            "clone_url",
            "github_id",
            "created_at",
            "topics",
            "stars",
        ]

    def test_empty_selection(self, tmp_path):
        out_dir = tmp_path / "out"
        counts = write_per_language_files([], out_dir)
        assert counts == {}
        assert (out_dir / "all.csv").exists()


class TestFilterKnownDuplicates:
    """Consult-only dedup: reads the static lookup table built by
    `python -m collection.dedupe_dataset_c_repos`, drops known duplicates.
    Pure CSV filtering -- no API calls, no cloning, at build time."""

    def _write_duplicates_csv(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "repo_to_remove",
            "repo_to_keep",
            "shared_commit_sha",
            "cluster_size",
            "language",
            "stars_removed",
            "stars_kept",
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_drops_repo_to_remove_entries(self, tmp_path):
        selected = [
            {"repo_name": "openjdk/loom", "language": "java", "stars": 100},
            {"repo_name": "openjdk/jdk", "language": "java", "stars": 500},
            {"repo_name": "other/unrelated", "language": "python", "stars": 10},
        ]
        dup_csv = tmp_path / "duplicate_repos.csv"
        self._write_duplicates_csv(
            dup_csv,
            [
                {
                    "repo_to_remove": "openjdk/loom",
                    "repo_to_keep": "openjdk/jdk",
                    "shared_commit_sha": "abc123",
                    "cluster_size": 2,
                    "language": "java",
                    "stars_removed": 100,
                    "stars_kept": 500,
                }
            ],
        )

        filtered = filter_known_duplicates(selected, duplicate_repos_csv=dup_csv)

        names = {r["repo_name"] for r in filtered}
        assert names == {"openjdk/jdk", "other/unrelated"}

    def test_missing_duplicates_csv_returns_unfiltered(self, tmp_path):
        selected = [{"repo_name": "o/r", "language": "python", "stars": 1}]
        filtered = filter_known_duplicates(
            selected, duplicate_repos_csv=tmp_path / "does-not-exist.csv"
        )
        assert filtered == selected

    def test_empty_duplicates_csv_returns_unfiltered(self, tmp_path):
        selected = [{"repo_name": "o/r", "language": "python", "stars": 1}]
        dup_csv = tmp_path / "duplicate_repos.csv"
        self._write_duplicates_csv(dup_csv, [])
        filtered = filter_known_duplicates(selected, duplicate_repos_csv=dup_csv)
        assert filtered == selected
