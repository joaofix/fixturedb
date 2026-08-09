"""Tests for collection/research_questions/balance.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks the repo-level loading, comparison, and
report-rendering logic -- never touching the real db/ or research_questions/
directories. The chi-square/Mann-Whitney/effect-size math itself is already
covered by tests/between_group/test_between_group_comparison.py; these
tests focus on balance.py's own wiring: repo-level (not fixture-weighted)
SQL aggregation, missing-db/missing-column handling, and markdown rendering.
"""

from __future__ import annotations

from collection import paths
from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions.balance import (
    RepoControlVariables,
    generate_report,
    load_repo_control_variables,
    write_report,
)


def _make_db(root, dataset: str, repos: list[dict]) -> None:
    """Create db/{dataset}.db under `root` with one repo per entry in
    `repos`. Each dict may set "language"/"domain"/"repo_age_years"
    (defaults: python/other/None) and "with_fixture" (default True -- a
    repo with with_fixture=False is inserted but gets no fixture row, to
    exercise the "repos without any fixture are excluded" behavior).

    Dataset "c" writes to c_sampled.db, not c.db -- require_db_or_none()
    resolves "c" there exclusively (see _shared.py), so a test DB built at
    the full c.db path would be invisible to load_repo_control_variables()/
    generate_report() and silently look like "not collected yet."
    """
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for i, repo_spec in enumerate(repos):
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": i + 1,
                    "full_name": f"owner/repo{i}",
                    "language": repo_spec.get("language", "python"),
                    "stars": 1,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2020-01-01T00:00:00Z",
                    "clone_url": f"https://github.com/owner/repo{i}.git",
                    "num_contributors": 1,
                    "domain": repo_spec.get("domain", "other"),
                    "repo_age_years": repo_spec.get("repo_age_years"),
                },
            )
            if repo_spec.get("with_fixture", True):
                file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")
                insert_fixture(
                    conn,
                    {
                        "file_id": file_id,
                        "repo_id": repo_id,
                        "name": "fx",
                        "fixture_type": "pytest_decorator",
                        "scope": "per_test",
                        "start_line": 1,
                        "end_line": 2,
                        "loc": 3,
                        "cyclomatic_complexity": 1,
                        "max_nesting_depth": 1,
                        "num_objects_instantiated": 0,
                        "num_external_calls": 0,
                        "num_parameters": 0,
                        "has_teardown_pair": 0,
                        "raw_source": "",
                        "framework": "pytest",
                        "num_mocks": 0,
                    },
                )


class TestLoadRepoControlVariables:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_repo_control_variables("a", db_root=tmp_path) is None

    def test_counts_only_fixture_yielding_repos(self, tmp_path):
        """Regression: this must be repo-level and restricted to repos with
        >=1 fixture, not every discovered repo -- matching the intent of
        the original (orphaned) balance-check code, which never counted a
        repo that yielded zero fixtures."""
        _make_db(
            tmp_path,
            "a",
            [
                {"language": "python", "with_fixture": True},
                {"language": "java", "with_fixture": False},
            ],
        )
        metrics = load_repo_control_variables("a", db_root=tmp_path)
        assert isinstance(metrics, RepoControlVariables)
        assert metrics.n_repos == 1
        assert metrics.categorical["language"] == {"python": 1}

    def test_repo_level_not_fixture_weighted(self, tmp_path):
        """A repo with many fixtures must still count once, not once per
        fixture -- this is what distinguishes a control-variable balance
        check (are the repo SAMPLES comparable) from a fixture-level metric
        test (RQ1-3's own job)."""
        db_file = paths.db_path("a", root=tmp_path)
        initialise_db(db_file)
        with db_session(db_file) as conn:
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": 1,
                    "full_name": "owner/repo",
                    "language": "python",
                    "stars": 1,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2020-01-01T00:00:00Z",
                    "clone_url": "https://github.com/owner/repo.git",
                    "num_contributors": 1,
                    "domain": "web",
                    "repo_age_years": 3.0,
                },
            )
            file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")
            for i in range(5):
                insert_fixture(
                    conn,
                    {
                        "file_id": file_id,
                        "repo_id": repo_id,
                        "name": f"fx{i}",
                        "fixture_type": "pytest_decorator",
                        "scope": "per_test",
                        "start_line": i,
                        "end_line": i + 1,
                        "loc": 3,
                        "cyclomatic_complexity": 1,
                        "max_nesting_depth": 1,
                        "num_objects_instantiated": 0,
                        "num_external_calls": 0,
                        "num_parameters": 0,
                        "has_teardown_pair": 0,
                        "raw_source": "",
                        "framework": "pytest",
                        "num_mocks": 0,
                    },
                )
        metrics = load_repo_control_variables("a", db_root=tmp_path)
        assert metrics.n_repos == 1
        assert metrics.categorical["language"] == {"python": 1}
        assert metrics.continuous["repo_age_years"] == [3.0]

    def test_missing_column_treated_as_no_data_not_a_crash(self, tmp_path):
        """A db predating a schema column addition must degrade gracefully
        (real case: db/a.db lacks repo_age_at_collection_years, collected
        before that column existed) -- not crash the whole balance check.
        Insert while the column still exists, then drop it, so this
        exercises load_repo_control_variables() hitting a genuinely missing
        column rather than failing at data setup time."""
        _make_db(tmp_path, "a", [{"language": "python"}])
        db_file = paths.db_path("a", root=tmp_path)
        with db_session(db_file) as conn:
            conn.execute("ALTER TABLE repositories DROP COLUMN repo_age_years")
        metrics = load_repo_control_variables("a", db_root=tmp_path)
        assert metrics.continuous["repo_age_years"] == []


class TestGenerateReport:
    def test_missing_all_dbs_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Dataset A not available" in report
        assert "Not available -- db not collected yet." in report

    def test_balanced_domain_reports_yes(self, tmp_path):
        _make_db(tmp_path, "a", [{"domain": "web"}, {"domain": "ml"}] * 20)
        _make_db(tmp_path, "c", [{"domain": "web"}, {"domain": "ml"}] * 20)
        report = generate_report(db_root=tmp_path)
        domain_line = next(
            line for line in report.splitlines() if line.startswith("| domain |")
        )
        assert domain_line.strip().endswith("yes |") or "yes |" in domain_line

    def test_imbalanced_domain_flagged_as_not_balanced(self, tmp_path):
        _make_db(tmp_path, "a", [{"domain": "web"}] * 20)
        _make_db(tmp_path, "c", [{"domain": "ml"}] * 20)
        report = generate_report(db_root=tmp_path)
        domain_line = next(
            line for line in report.splitlines() if line.startswith("| domain |")
        )
        assert "**no**" in domain_line
        assert "large" in domain_line  # Cramer's V magnitude for total separation

    def test_repo_age_years_balance_uses_mann_whitney(self, tmp_path):
        _make_db(tmp_path, "a", [{"repo_age_years": v} for v in [1.0, 1.5, 2.0, 2.5, 3.0]])
        _make_db(tmp_path, "c", [{"repo_age_years": v} for v in [10.0, 10.5, 11.0, 11.5, 12.0]])
        report = generate_report(db_root=tmp_path)
        age_line = next(
            line for line in report.splitlines() if line.startswith("| repo_age_years |")
        )
        assert "mann-whitney-u" in age_line
        assert "**no**" in age_line


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"language": "python"}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "balance.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
