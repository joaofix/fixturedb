"""Tests for collection/research_questions/rq3.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks per-repo/per-language repo-count
bookkeeping and report rendering -- never touching the real db/ or
research-questions/ directories. rq3.py does not classify fixture_role
itself. That happens at extraction time (see detector_shared.py's
_classify_fixture_kinds() and detector_python.py's pytest body-analysis
classification, both covered by their own test files:
test_fixture_kind_classification.py and test_classify_pytest_fixture_kind.py),
so these fixture-dict literals set fixture_role directly via
_default_fixture_role() below -- a thin test-only wrapper around those
same two real functions, not a reimplementation, so this file's synthetic
data stays in sync with production classification automatically. Neither
table in this script runs a statistical test. Both are purely
descriptive, so there's no Mann-Whitney/BH-FDR machinery left here to
test at all.
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
from collection.detector_python import classify_pytest_fixture_kind_from_source
from collection.detector_shared import _classify_fixture_kind
from collection.research_questions.rq3 import (
    DatasetMetrics,
    _answerable_total,
    _pct_cell,
    _render_kind_classification_coverage_table,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _default_fixture_role(fixture_type: str, name: str, raw_source: str) -> str:
    """What extraction would have set fixture_role to, given only
    fixture_type/name/raw_source -- delegates to the same two real
    functions detector_shared._classify_fixture_kinds()/detector_python's
    _detect_python() call in production, so _make_db()/_make_multi_language_db()
    callers below can omit fixture_role and still get a realistic
    default instead of every fixture literal in this file needing one."""
    if fixture_type == "pytest_decorator":
        return classify_pytest_fixture_kind_from_source(raw_source or "")
    return _classify_fixture_kind(fixture_type, name or "")


def _make_db(root, dataset: str, repos: list[list[dict]]) -> None:
    """Create db/{dataset}.db under `root` with one repo per entry in `repos`,
    each populated with the given list of fixture-field overrides.

    Dataset "c" writes to c_sampled.db instead of the full c.db --
    research_questions/ reads Dataset C's fixture-level sample-down, see
    _shared.py::require_db_or_none()'s docstring.
    """
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for repo_idx, fixtures in enumerate(repos):
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": repo_idx + 1,
                    "full_name": f"owner/repo{repo_idx}",
                    "language": "python",
                    "stars": 1,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2020-01-01T00:00:00Z",
                    "clone_url": f"https://github.com/owner/repo{repo_idx}.git",
                    "num_contributors": 1,
                    "domain": None,
                    "repo_age_years": None,
                },
            )
            file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")
            for i, overrides in enumerate(fixtures):
                base = {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{repo_idx}_{i}",
                    "fixture_type": "before_each",
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
                base.setdefault(
                    "fixture_role",
                    _default_fixture_role(
                        base["fixture_type"], base.get("name", ""), base.get("raw_source", "")
                    ),
                )
                insert_fixture(conn, base)


def _make_multi_language_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db with one repo and one test_file per `files`
    entry -- each entry: {"language": str, "fixtures": [fixture_dict, ...]}.
    Lets a single repo contribute fixtures in more than one language, for
    testing language-stratified aggregation (kind_counts_by_repo_and_language).

    Dataset "c" writes to c_sampled.db instead of the full c.db --
    research_questions/ reads Dataset C's fixture-level sample-down, see
    _shared.py::require_db_or_none()'s docstring."""
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
                    "fixture_type": "before_each",
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
                base.setdefault(
                    "fixture_role",
                    _default_fixture_role(
                        base["fixture_type"], base.get("name", ""), base.get("raw_source", "")
                    ),
                )
                insert_fixture(conn, base)


class TestAnswerableTotal:
    def test_excludes_other_from_the_sum(self):
        assert _answerable_total({"setup": 3, "teardown": 2, "setup_and_teardown": 1, "other": 10}) == 6

    def test_missing_keys_default_to_zero(self):
        assert _answerable_total({}) == 0
        assert _answerable_total({"other": 5}) == 0

    def test_setup_and_teardown_counted_once_not_double_counted(self):
        """_answerable_total is a single sum over the three kinds, unlike
        _effective_setup_count/_effective_teardown_count which each add
        setup_and_teardown separately -- it must not be double-counted
        here just because it feeds both effective counts elsewhere."""
        assert _answerable_total({"setup": 1, "teardown": 1, "setup_and_teardown": 1}) == 3


class TestPctCell:
    def test_known_percentage_rounds_to_one_decimal(self):
        assert _pct_cell(3, 5) == "3 (60.0%)"

    def test_zero_total_renders_bare_count_no_percentage(self):
        """Avoids a ZeroDivisionError for a language absent from a
        dataset -- the zero-filled-row case elsewhere in this table."""
        assert _pct_cell(0, 0) == "0"

    def test_count_can_exceed_total_for_setup_and_teardown_double_counting(self):
        """Not a real total>100% bug -- a setup_and_teardown fixture
        legitimately counts toward both the setup and teardown numerators
        against the same denominator, so a single-kind total (e.g. every
        fixture is setup_and_teardown) renders exactly 100%, not capped
        or an error."""
        assert _pct_cell(4, 4) == "4 (100.0%)"

    def test_large_counts_keep_thousands_separator(self):
        assert _pct_cell(18619, 20148) == "18,619 (92.4%)"


class TestLoadDatasetMetrics:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_dataset_metrics("a", db_root=tmp_path) is None

    def test_kind_distribution(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                [
                    {"fixture_type": "before_each"},
                    {"fixture_type": "before_each"},
                    {"fixture_type": "after_each"},
                    {"fixture_type": "pytest_decorator"},
                ]
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert isinstance(metrics, DatasetMetrics)
        assert metrics.n_fixtures == 4
        assert metrics.kind_distribution == {
            "setup": 2,
            "teardown": 1,
            "setup_and_teardown": 0,
            "other": 1,
        }

    def test_kind_distribution_splits_name_based_types(self, tmp_path):
        """unittest_setup/pytest_class_method rows must be classified by
        name, not dumped wholesale into 'other' -- the fix this test file
        exists to cover."""
        _make_db(
            tmp_path,
            "a",
            [
                [
                    {"fixture_type": "unittest_setup", "name": "setUp"},
                    {"fixture_type": "unittest_setup", "name": "tearDown"},
                    {"fixture_type": "pytest_class_method", "name": "setup_method"},
                    {"fixture_type": "junit_rule", "name": "tempFolder"},
                ]
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.kind_distribution == {
            "setup": 2,
            "teardown": 1,
            "setup_and_teardown": 0,
            "other": 1,
        }

    def test_kind_counts_by_repo_groups_all_three_kinds_by_repo_id(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                # repo 0: 2 setup, 1 teardown, 1 other
                [
                    {"fixture_type": "before_each"},
                    {"fixture_type": "before_each"},
                    {"fixture_type": "after_each"},
                    {"fixture_type": "pytest_decorator"},
                ],
                # repo 1: 1 setup only
                [{"fixture_type": "before_each"}],
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert len(metrics.kind_counts_by_repo) == 2
        assert {
            "setup": 2,
            "teardown": 1,
            "setup_and_teardown": 0,
            "other": 1,
        } in metrics.kind_counts_by_repo.values()
        assert {
            "setup": 1,
            "teardown": 0,
            "setup_and_teardown": 0,
            "other": 0,
        } in metrics.kind_counts_by_repo.values()

    def test_kind_counts_by_repo_and_language_splits_by_fixtures_own_language(self, tmp_path):
        """One repo contributing fixtures in two languages must get its own
        {setup/teardown/setup_and_teardown/other: count} entry under EACH
        language, keyed by that fixture's own test_files.language (not the
        repo's tag) -- the per-language rows' population."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [{"fixture_type": "before_each"}, {"fixture_type": "after_each"}],
                },
                {"language": "typescript", "fixtures": [{"fixture_type": "before_each"}]},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        by_lang = metrics.kind_counts_by_repo_and_language
        assert set(by_lang) == {"python", "typescript"}
        # Same repo_id under both languages (one repo, two languages).
        python_repo_id = next(iter(by_lang["python"]))
        typescript_repo_id = next(iter(by_lang["typescript"]))
        assert python_repo_id == typescript_repo_id
        assert by_lang["python"][python_repo_id] == {
            "setup": 1,
            "teardown": 1,
            "setup_and_teardown": 0,
            "other": 0,
        }
        assert by_lang["typescript"][typescript_repo_id] == {
            "setup": 1,
            "teardown": 0,
            "setup_and_teardown": 0,
            "other": 0,
        }


class TestGenerateReport:
    def test_missing_all_dbs_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Dataset A not available" in report
        assert "Not available -- db not collected yet." in report

    def test_dataset_a_only_renders_summary_and_skips_comparisons(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}, {"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        assert "Dataset A (agent-authored) -- 2 fixtures" in report
        assert "## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)" in report
        # C summary, A-vs-C comparison: 2 total (no separate repo-level
        # section anymore -- the one table below IS the repo-level result).
        assert report.count("Not available -- db not collected yet.") == 2

    def test_dataset_summary_includes_language_leakage_table(self, tmp_path):
        """_make_db's repo and its one test_file both use "python", so this
        is a no-leakage wiring check -- compute_language_leakage() itself is
        covered against real leaked data in
        test_research_questions_shared.py."""
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        report = generate_report(db_root=tmp_path)
        assert "Cross-language fixture leakage" in report
        assert "0/1 fixtures (0.00%) leaked." in report

    def test_removed_metrics_no_longer_appear(self, tmp_path):
        """Ratio/no-teardown-rate/teardown-pair-rate/median-proportion
        table were dropped from the paper's reported output entirely --
        not just de-pooled."""
        _make_db(
            tmp_path,
            "a",
            [[{"fixture_type": "before_each"}, {"fixture_type": "before_each"}]],
        )
        _make_db(
            tmp_path,
            "c",
            [[{"fixture_type": "before_each"}, {"fixture_type": "after_each"}]],
        )
        report = generate_report(db_root=tmp_path)
        assert "setup_to_teardown_ratio" not in report
        assert "repo_zero_teardown_rate" not in report
        assert "has_teardown_pair rate by fixture_type" not in report
        assert "## Repo-level aggregates" not in report
        assert "ratio undefined" not in report
        # The old median setup_pct/teardown_pct proportion table -- fully
        # replaced by Table 1 (counts) + Table 2 (coverage).
        assert "V (A↔C)" not in report
        assert "Setup A (%) | Setup C (%)" not in report

    def test_kind_counts_table_renders_absolute_counts_per_language(self, tmp_path):
        """Table 1: purely descriptive setup/teardown counts, "other"
        excluded, fixed four-language row order with zero-filled rows for
        languages absent from the data."""
        _make_db(
            tmp_path,
            "a",
            [[{"fixture_type": "before_each"}] * 3 + [{"fixture_type": "after_each"}] * 2],
        )
        _make_db(
            tmp_path,
            "c",
            [[{"fixture_type": "before_each"}] + [{"fixture_type": "after_each"}] * 4],
        )
        report = generate_report(db_root=tmp_path)
        assert "### Table 1: Fixture Counts by Type (tab:rq3-counts)" in report
        assert "| Language | Setup A | Setup C | Teardown A | Teardown C |" in report
        comparison_section = report.split("## A vs C:")[1]
        # A: 3 setup + 2 teardown = 5 total -> 60.0%/40.0%.
        # C: 1 setup + 4 teardown = 5 total -> 20.0%/80.0%.
        assert "| Total | 3 (60.0%) | 1 (20.0%) | 2 (40.0%) | 4 (80.0%) |" in comparison_section
        assert "| python | 3 (60.0%) | 1 (20.0%) | 2 (40.0%) | 4 (80.0%) |" in comparison_section
        # java/javascript/typescript have no data on either side -- zero,
        # not omitted, and no percentage (would be a division by zero).
        assert "| java | 0 | 0 | 0 | 0 |" in comparison_section
        assert "| javascript | 0 | 0 | 0 | 0 |" in comparison_section
        assert "| typescript | 0 | 0 | 0 | 0 |" in comparison_section

    def test_kind_counts_table_excludes_other_classified_fixtures(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [[{"fixture_type": "before_each"}, {"fixture_type": "pytest_decorator"}]],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("## A vs C:")[1]
        # A: 1 setup + 1 other -- the "other" fixture is excluded from
        # BOTH the counts AND the percentage denominator (answerable
        # total = 1, the "other" fixture doesn't count) -> setup
        # 1/1=100.0%, teardown 0/1=0.0%.
        # C: 1 teardown = 1 answerable total -> setup 0/1=0.0%,
        # teardown 1/1=100.0%.
        assert "| Total | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 1 (100.0%) |" in comparison_section

    def test_kind_counts_table_other_fixtures_dont_dilute_the_percentage_denominator(
        self, tmp_path
    ):
        """A language with a large 'other' share must not show a lower
        Setup%/Teardown% purely because of how much of it is
        unclassifiable -- the denominator is the *answerable* count only
        (setup+teardown+setup_and_teardown), not the whole classified
        count including 'other'. 3 setup + 6 other (junit_rule) -> without
        this behavior the naive whole-count denominator (9) would report
        setup at 33.3%; the correct answerable denominator (3) reports
        100.0%."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "java",
                    "fixtures": (
                        [{"fixture_type": "before_each"}] * 3
                        + [{"fixture_type": "junit_rule", "name": "tempFolder"}] * 6
                    ),
                }
            ],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("## A vs C:")[1]
        java_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| java |")
        )
        # C's fixture is "python" (the _make_db default language), so C's
        # java row is entirely zero-filled -- "0" not "0 (0.0%)".
        assert "| java | 3 (100.0%) | 0 | 0 (0.0%) | 0 |" == java_line

    def test_kind_counts_table_counts_setup_and_teardown_fixture_in_both_columns(
        self, tmp_path
    ):
        """A pytest_decorator fixture classified 'setup_and_teardown'
        (real yield-after-setup raw_source) is not "other" -- it counts
        toward both the Setup and Teardown columns, since it genuinely
        provides both."""
        _make_db(
            tmp_path,
            "a",
            [
                [
                    {
                        "fixture_type": "pytest_decorator",
                        "raw_source": (
                            "def db():\n    conn = connect()\n"
                            "    yield conn\n    conn.close()\n"
                        ),
                    }
                ]
            ],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("## A vs C:")[1]
        # Setup A=1, Setup C=0, Teardown A=1, Teardown C=1 -- the single A
        # fixture counted in both the Setup and Teardown A columns, each
        # against a 1-fixture total -> 100.0% in both A columns (percentages
        # summing past 100% is expected here, see this table's docstring).
        assert "| Total | 1 (100.0%) | 0 (0.0%) | 1 (100.0%) | 1 (100.0%) |" in comparison_section

    def test_kind_counts_table_total_includes_languages_outside_the_fixed_four(self, tmp_path):
        """The Total row is the dataset-wide sum across every language
        present, not just the four canonical rows shown -- a 5th language
        still counts toward Total even though it gets no row of its own."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [{"language": "rust", "fixtures": [{"fixture_type": "before_each"}]}],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("## A vs C:")[1]
        assert "| Total | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 1 (100.0%) |" in comparison_section
        assert "| rust |" not in comparison_section

    def test_teardown_coverage_table_renders_percentages_no_statistical_test(self, tmp_path):
        """Table 2: A has 1 of 2 repos with any teardown (50%); C has 2 of
        2 (100%). Purely descriptive -- no statistic/effect-size/p-value
        columns at all."""
        _make_db(
            tmp_path,
            "a",
            [
                [{"fixture_type": "before_each"}, {"fixture_type": "after_each"}],
                [{"fixture_type": "before_each"}],
            ],
        )
        _make_db(
            tmp_path,
            "c",
            [
                [{"fixture_type": "after_each"}],
                [{"fixture_type": "after_each"}],
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "### Table 2: Teardown Coverage by Repository (tab:rq3-coverage)" in report
        assert (
            "| Language | n_A | n_C | Coverage A (%) | Coverage C (%) |"
            in report
        )
        # "python" also appears as a row label in Table 1 (counts), above
        # Table 2 in the same comparison section -- scope past the Table 2
        # heading so we don't match that row instead.
        coverage_section = report.split("### Table 2: Teardown Coverage by Repository")[1]
        overall_line = next(
            line for line in coverage_section.splitlines() if line.startswith("| Overall |")
        )
        python_line = next(
            line for line in coverage_section.splitlines() if line.startswith("| python |")
        )
        for line in (overall_line, python_line):
            assert "| 2 | 2 |" in line
            assert "50.0% | 100.0%" in line  # Coverage A (%) | Coverage C (%)
            # No statistic/effect-size/p-value columns at all.
            assert line.count("|") == 6
        assert "delta" not in report
        assert "p (BH)" not in report
        assert "significant (p<0.05)" not in report

    def test_teardown_coverage_repo_with_only_setup_counts_as_zero_coverage(self, tmp_path):
        """A repo whose only classified fixtures are setup (no teardown at
        all) contributes 0 to the coverage indicator -- not skipped, not
        1."""
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        _make_db(tmp_path, "c", [[{"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("## A vs C:")[1]
        overall_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| Overall |")
        )
        assert "0.0% | 100.0%" in overall_line

    def test_teardown_coverage_counts_setup_and_teardown_classified_repo_as_covered(
        self, tmp_path
    ):
        """A repo whose only classified fixture is a pytest_decorator
        classified 'setup_and_teardown' (real yield-after-setup
        raw_source) counts as covered (1), the same as a repo with a
        plain 'teardown'-classified fixture."""
        _make_db(
            tmp_path,
            "a",
            [
                [
                    {
                        "fixture_type": "pytest_decorator",
                        "raw_source": (
                            "def db():\n    conn = connect()\n"
                            "    yield conn\n    conn.close()\n"
                        ),
                    }
                ]
            ],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "before_each"}]])
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("## A vs C:")[1]
        overall_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| Overall |")
        )
        assert "100.0% | 0.0%" in overall_line

    def test_teardown_coverage_declusters_a_prolific_repo(self, tmp_path):
        """A is one repo with 100 setup-only fixtures (0 teardown ->
        coverage 0) plus one repo with a single teardown-only fixture
        (coverage 1) -- fixture-weighted, "teardown coverage" would look
        ~1% (1 of 101 fixtures). Per-repo (what's actually reported), A is
        50% (1 of 2 repos has any teardown at all), same as C's much
        smaller but proportionally identical repos."""
        _make_db(
            tmp_path,
            "a",
            [
                [{"fixture_type": "before_each"}] * 100,
                [{"fixture_type": "after_each"}],
            ],
        )
        _make_db(
            tmp_path,
            "c",
            [
                [{"fixture_type": "before_each"}],
                [{"fixture_type": "after_each"}],
            ],
        )
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("## A vs C:")[1]
        overall_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| Overall |")
        )
        # Per-repo, both A and C are 1-of-2 repos with any teardown (50%) --
        # nowhere near a ~1%-teardown fixture-weighted figure.
        assert "50.0% | 50.0%" in overall_line

    def test_teardown_coverage_language_absent_from_both_sides_shows_empty_population(
        self, tmp_path
    ):
        """java/javascript/typescript have zero repos on either side (both
        _make_db calls default to "python" test files) -- must degrade to
        '--' cells, not crash or divide by zero."""
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        _make_db(tmp_path, "c", [[{"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        coverage_section = report.split("### Table 2: Teardown Coverage by Repository")[1]
        java_line = next(
            line for line in coverage_section.splitlines() if line.startswith("| java |")
        )
        assert "| java | 0 | 0 | -- | -- |" == java_line


class TestRenderKindClassificationCoverageTable:
    def test_header_and_section_title_present(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        _make_db(tmp_path, "c", [[{"fixture_type": "before_each"}]])
        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)
        report = _render_kind_classification_coverage_table(a_metrics, c_metrics)
        assert "### Fixture Kind Classification Coverage by Language" in report
        assert (
            "| Dataset | Language | Total fixtures | setup | teardown | "
            "setup_and_teardown | other (count) | other (%) |" in report
        )

    def test_renders_one_row_per_language_per_dataset_with_zero_filled_absent_languages(
        self, tmp_path
    ):
        """Every RQ3_LANGUAGES row must render for both datasets, even a
        language with zero fixtures on one side -- 0 rows, not omitted,
        matching Table 1's own zero-filled-row convention."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [{"language": "java", "fixtures": [{"fixture_type": "junit_rule", "name": "tempFolder"}]}],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "before_each"}]])
        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)
        report = _render_kind_classification_coverage_table(a_metrics, c_metrics)
        lines = report.splitlines()

        # java is 100% "other" in A (junit_rule) -- a real java row, not
        # omitted just because setup/teardown are both 0.
        assert "| A | java | 1 | 0 | 0 | 0 | 1 | 100.0% |" in lines
        # javascript has zero fixtures in A at all -- still a zero-filled
        # row, not omitted, and no ZeroDivisionError.
        assert "| A | javascript | 0 | 0 | 0 | 0 | 0 | 0.0% |" in lines
        # python is the only language populated in C, all "setup"
        # (before_each), 0% other.
        assert "| C | python | 1 | 1 | 0 | 0 | 0 | 0.0% |" in lines
        assert "| C | java | 0 | 0 | 0 | 0 | 0 | 0.0% |" in lines

    def test_setup_and_teardown_counted_in_its_own_column_not_folded_into_setup_or_teardown(
        self, tmp_path
    ):
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {
                            "fixture_type": "pytest_decorator",
                            "raw_source": (
                                "def db():\n    conn = connect()\n"
                                "    yield conn\n    conn.close()\n"
                            ),
                        }
                    ],
                }
            ],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "before_each"}]])
        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)
        report = _render_kind_classification_coverage_table(a_metrics, c_metrics)
        assert "| A | python | 1 | 0 | 0 | 1 | 0 | 0.0% |" in report.splitlines()

    def test_other_percentage_matches_hand_computed_value(self, tmp_path):
        # java: 3 setup, 1 other -> other% = 1/4 = 25.0%
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "java",
                    "fixtures": [
                        {"fixture_type": "before_each"},
                        {"fixture_type": "before_each"},
                        {"fixture_type": "before_each"},
                        {"fixture_type": "junit_rule", "name": "tempFolder"},
                    ],
                }
            ],
        )
        _make_db(tmp_path, "c", [[{"fixture_type": "before_each"}]])
        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)
        report = _render_kind_classification_coverage_table(a_metrics, c_metrics)
        assert "| A | java | 4 | 3 | 0 | 0 | 1 | 25.0% |" in report.splitlines()

    def test_generate_report_includes_kind_classification_coverage_section(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "unittest_setup", "name": "setUp"}]])
        _make_db(tmp_path, "c", [[{"fixture_type": "unittest_setup", "name": "setUp"}]])
        report = generate_report(db_root=tmp_path)
        assert "### Fixture Kind Classification Coverage by Language" in report
        # Under Supplementary Analyses.
        assert (
            report.index("## Supplementary Analyses")
            < report.index("### Fixture Kind Classification Coverage by Language")
        )


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq3.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
