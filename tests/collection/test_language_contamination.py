"""Tests for collection/research_questions/language_contamination.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks generate_report()/write_report()'s
wiring -- missing-db handling and markdown rendering. The leakage
computation itself (compute_language_leakage()/render_language_leakage_
table()) is already covered by tests/collection/test_research_questions_
shared.py; these tests focus on this module's own job: resolving each
dataset's db (including "c" -> c_sampled.db) and assembling the report.

This module used to check something different -- a fixture's CSV row
`language` column against the CSV filename it was routed into. That was a
tautology (both values are derived from the exact same source field with
the exact same fallback, so they can never disagree under the current
pipeline) and always read 0.00% regardless of how much real contamination
existed. It now reuses the same repo-tag-vs-fixture's-own-language
computation RQ1/RQ3's "Cross-language fixture leakage" table already
uses, which is the real signal.
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
from collection.research_questions.language_contamination import (
    generate_report,
    write_report,
)


def _make_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db (c_sampled.db for "c") with one repo tagged
    `python` and one test_file per `files` entry: {"language": str,
    "fixtures": [fixture_dict, ...]}. A file's language differing from the
    repo's own "python" tag is what makes a fixture "leaked"."""
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
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
                "domain": None,
                "repo_age_years": None,
            },
        )
        for file_idx, file_spec in enumerate(files):
            language = file_spec["language"]
            file_id = upsert_test_file(
                conn, repo_id, f"tests/test_{file_idx}.{language}", language
            )
            for i, overrides in enumerate(file_spec["fixtures"]):
                base = {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{file_idx}_{i}",
                    "fixture_type": "pytest_decorator",
                    "scope": "per_test",
                    "start_line": i,
                    "end_line": i + 1,
                    "loc": 5,
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 1,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_comment_lines": 0,
                    "comment_density": 0.0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "raw_source": "",
                    "framework": "pytest",
                    "num_mocks": 0,
                }
                base.update(overrides)
                insert_fixture(conn, base)


class TestGenerateReport:
    def test_missing_dataset_a_notes_unavailable(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Not available -- no db/a.db collected yet." in report

    def test_missing_dataset_c_notes_unavailable_with_sample_c_repos_hint(self, tmp_path):
        """Dataset C's not-available message is its own, distinct from A's
        -- it points at running sample-c-repos, since db/c_sampled.db is
        what's actually being checked, not the full db/c.db."""
        report = generate_report(db_root=tmp_path)
        assert (
            "_Not available -- run `sample-c-repos` first "
            "(`db/c_sampled.db` not found)._" in report
        )

    def test_no_leakage_reports_zero_percent(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{}, {}]}],
        )
        report = generate_report(db_root=tmp_path)
        assert "0/2 fixtures (0.00%) leaked." in report

    def test_real_leakage_is_reported_not_hidden(self, tmp_path):
        """The regression this rewrite exists for: a fixture whose own
        file language differs from its repo's tag must show up as leaked,
        not read 0% just because the fixture's language is internally
        consistent with wherever it got routed/persisted."""
        _make_db(
            tmp_path,
            "a",
            [
                {"language": "python", "fixtures": [{}]},
                {"language": "typescript", "fixtures": [{}]},
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "1/2 fixtures (50.00%) leaked." in report
        assert "typescript=1" in report

    def test_dataset_c_reads_sampled_db_not_full_db(self, tmp_path):
        """db/c.db existing (the full, unsampled corpus) must not be read
        here -- only db/c_sampled.db, matching require_db_or_none()'s
        redirect for dataset "c"."""
        initialise_db(paths.db_path("c", root=tmp_path))  # full db/c.db: present but unused
        _make_db(
            tmp_path,
            "c",
            [{"language": "python", "fixtures": [{}]}],
        )
        report = generate_report(db_root=tmp_path)
        assert "0/1 fixtures (0.00%) leaked." in report

    def test_dataset_headers_present_for_both_datasets(self, tmp_path):
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{}]}])
        _make_db(tmp_path, "c", [{"language": "python", "fixtures": [{}]}])
        report = generate_report(db_root=tmp_path)
        assert "### Dataset A (agent-authored)" in report
        assert "### Dataset C (human-authored, pre-LLM)" in report


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{}]}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "language_contamination.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
