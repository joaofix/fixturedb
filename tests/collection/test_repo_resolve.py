"""Unit tests for collection.repo_resolve.resolve_dataset_b_repos().

This is the one explicit, deterministic place Dataset B's repo list gets
resolved from Dataset A's already-collected repos -- it replaces the old
multi-directory fallback-glob guessing that used to live inside
human_corpus.select_human_corpus_repositories() (four different guesses,
three different folder-name spellings). See that function's current
docstring and the CLI-redesign plan for context.
"""

from __future__ import annotations

import csv

from collection.repo_resolve import resolve_dataset_b_repos


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class TestResolveFromRepoCsvs:
    def test_reads_positive_repos_only(self, tmp_path):
        source = tmp_path / "a-repos"
        _write_csv(
            source / "python_repo.csv",
            [
                {
                    "repo_name": "owner/positive",
                    "has_agent_config": "1",
                    "language": "python",
                    "stars": "10",
                    "clone_url": "https://github.com/owner/positive.git",
                    "num_contributors": "2",
                },
                {
                    "repo_name": "owner/negative",
                    "has_agent_config": "0",
                    "language": "python",
                    "stars": "5",
                    "clone_url": "",
                    "num_contributors": "1",
                },
            ],
        )
        out_dir = tmp_path / "b-repos"

        counts = resolve_dataset_b_repos(source_dir=source, output_dir=out_dir)

        assert counts == {"python": 1}
        with (out_dir / "python_repo.csv").open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert [r["repo_name"] for r in rows] == ["owner/positive"]

    def test_language_filter(self, tmp_path):
        source = tmp_path / "a-repos"
        _write_csv(
            source / "python_repo.csv",
            [{"repo_name": "o/py", "has_agent_config": "1", "language": "python"}],
        )
        _write_csv(
            source / "java_repo.csv",
            [{"repo_name": "o/java", "has_agent_config": "1", "language": "java"}],
        )
        out_dir = tmp_path / "b-repos"

        counts = resolve_dataset_b_repos(
            source_dir=source, output_dir=out_dir, language="python"
        )

        assert counts == {"python": 1}
        assert not (out_dir / "java_repo.csv").exists()

    def test_dedups_by_repo_name_across_files(self, tmp_path):
        source = tmp_path / "a-repos"
        _write_csv(
            source / "python_repo.csv",
            [{"repo_name": "o/dup", "has_agent_config": "1", "language": "python"}],
        )
        _write_csv(
            source / "python_repo_2.csv",
            [{"repo_name": "o/dup", "has_agent_config": "1", "language": "python"}],
        )
        out_dir = tmp_path / "b-repos"

        counts = resolve_dataset_b_repos(source_dir=source, output_dir=out_dir)

        assert counts == {"python": 1}


class TestResolveFromFixtureReposCsvs:
    def test_fixture_repos_source_is_implicitly_positive(self, tmp_path):
        """datasets/a/fixtures/repos/*_fixture_repos.csv has no
        has_agent_config column -- every row there already yielded an
        accepted fixture, so it's accepted without that column."""
        source = tmp_path / "a-fixtures-repos"
        _write_csv(
            source / "python_fixture_repos.csv",
            [
                {
                    "repo_name": "owner/yielded-fixture",
                    "language": "python",
                    "fixture_count": "3",
                    "clone_url": "https://github.com/owner/yielded-fixture.git",
                }
            ],
        )
        out_dir = tmp_path / "b-repos"

        counts = resolve_dataset_b_repos(source_dir=source, output_dir=out_dir)

        assert counts == {"python": 1}
        with (out_dir / "python_repo.csv").open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["repo_name"] == "owner/yielded-fixture"
        assert rows[0]["has_agent_config"] == "1"


class TestDefaultSourcePriority:
    def test_prefers_fixtures_repos_when_populated(self, tmp_path, monkeypatch):
        """Mirrors collection.paths.default_repo_source('b')'s priority: prefer
        datasets/a/fixtures/repos/ over datasets/a/repos/ when populated."""
        from collection import paths

        root = tmp_path / "datasets"
        fixture_repos_dir = paths.stage_dir("a", "fixtures", root=root) / "repos"
        _write_csv(
            fixture_repos_dir / "python_fixture_repos.csv",
            [{"repo_name": "owner/from-fixtures", "language": "python"}],
        )
        _write_csv(
            paths.stage_dir("a", "repos", root=root) / "python_repo.csv",
            [
                {
                    "repo_name": "owner/from-raw-repos",
                    "has_agent_config": "1",
                    "language": "python",
                }
            ],
        )

        source = paths.default_repo_source("b", root=root)
        out_dir = tmp_path / "b-repos"
        resolve_dataset_b_repos(source_dir=source, output_dir=out_dir)

        with (out_dir / "python_repo.csv").open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert [r["repo_name"] for r in rows] == ["owner/from-fixtures"]
