"""Tests for collection/detector_shared.py's generic (non-pytest_decorator)
fixture_type_kind classification: _classify_fixture_kind() and the
_classify_fixture_kinds() post-processing pass that sets FixtureResult.
fixture_type_kind for every fixture except pytest_decorator (which
detector_python.py's _detect_python() classifies directly via body
analysis -- see test_classify_pytest_fixture_kind.py, and
test_extractor_unit/test_python_fixtures.py::TestPytestFixtureTypeKindWiring
for the end-to-end extraction check).
"""

from __future__ import annotations

from collection.detector_shared import (
    FixtureResult,
    _classify_fixture_kind,
    _classify_fixture_kinds,
)


def _fixture(fixture_type: str, name: str = "f", **overrides) -> FixtureResult:
    base = {
        "name": name,
        "fixture_type": fixture_type,
        "framework": None,
        "scope": "per_test",
        "start_line": 1,
        "end_line": 2,
        "loc": 1,
        "cyclomatic_complexity": 1,
        "max_nesting_depth": 1,
        "num_objects_instantiated": 0,
        "num_external_calls": 0,
        "num_comment_lines": 0,
        "comment_density": 0.0,
        "num_parameters": 0,
    }
    base.update(overrides)
    return FixtureResult(**base)


class TestClassifyFixtureKind:
    def test_unambiguous_setup_type(self):
        assert _classify_fixture_kind("before_each", "f") == "setup"
        assert _classify_fixture_kind("junit5_before_each", "f") == "setup"

    def test_unambiguous_teardown_type(self):
        assert _classify_fixture_kind("after_each", "f") == "teardown"
        assert _classify_fixture_kind("junit5_after_each", "f") == "teardown"

    def test_genuinely_ambiguous_types_are_other(self):
        # junit_rule/vitest_around_* (inherently both at once);
        # testng_data_provider (not a lifecycle hook at all) -- none of
        # these can be split by type OR name, and (unlike pytest_decorator)
        # there's no body-analysis mechanism for them either.
        for fixture_type in (
            "junit_rule",
            "junit_class_rule",
            "vitest_around_each",
            "vitest_around_all",
            "testng_data_provider",
        ):
            assert _classify_fixture_kind(fixture_type, "f") == "other"

    def test_name_based_type_with_unrecognized_name_is_other(self):
        assert _classify_fixture_kind("unittest_setup", "some_helper_method") == "other"

    def test_name_based_setup_names(self):
        assert _classify_fixture_kind("unittest_setup", "setUp") == "setup"
        assert _classify_fixture_kind("unittest_setup", "setUpClass") == "setup"
        assert _classify_fixture_kind("unittest_setup", "setUpModule") == "setup"
        assert _classify_fixture_kind("pytest_class_method", "setup_method") == "setup"
        assert _classify_fixture_kind("pytest_class_method", "setup_class") == "setup"

    def test_name_based_teardown_names(self):
        assert _classify_fixture_kind("unittest_setup", "tearDown") == "teardown"
        assert _classify_fixture_kind("unittest_setup", "tearDownClass") == "teardown"
        assert _classify_fixture_kind("unittest_setup", "tearDownModule") == "teardown"
        assert _classify_fixture_kind("pytest_class_method", "teardown_method") == "teardown"
        assert _classify_fixture_kind("pytest_class_method", "teardown_class") == "teardown"

    def test_pytest_decorator_is_not_this_functions_job(self):
        """_classify_fixture_kind() has no pytest_decorator special-casing
        at all -- it's not in TYPE_BASED_*/NAME_BASED_TEARDOWN_PAIRS, so it
        falls through to 'other' here. That's fine: _classify_fixture_kinds()
        (below) never calls this for pytest_decorator fixtures in the first
        place -- detector_python.py classifies those directly."""
        assert _classify_fixture_kind("pytest_decorator", "whatever") == "other"


class TestClassifyFixtureKinds:
    """The post-processing pass: sets .fixture_type_kind in place for every
    fixture except pytest_decorator."""

    def test_sets_kind_for_type_based_fixtures(self):
        setup = _fixture("before_each")
        teardown = _fixture("after_each")
        _classify_fixture_kinds([setup, teardown])
        assert setup.fixture_type_kind == "setup"
        assert teardown.fixture_type_kind == "teardown"

    def test_sets_kind_for_name_based_fixtures(self):
        setup = _fixture("unittest_setup", name="setUp")
        teardown = _fixture("unittest_setup", name="tearDown")
        _classify_fixture_kinds([setup, teardown])
        assert setup.fixture_type_kind == "setup"
        assert teardown.fixture_type_kind == "teardown"

    def test_ambiguous_type_defaults_to_other(self):
        rule = _fixture("junit_rule")
        _classify_fixture_kinds([rule])
        assert rule.fixture_type_kind == "other"

    def test_skips_pytest_decorator_entirely(self):
        """pytest_decorator fixtures are left untouched by this pass --
        detector_python.py's _detect_python() already classified them
        directly (body analysis) before this ever runs. Simulated here by
        pre-setting an arbitrary fixture_type_kind and confirming this pass
        doesn't overwrite it."""
        pytest_fixture = _fixture("pytest_decorator", fixture_type_kind="setup_and_teardown")
        _classify_fixture_kinds([pytest_fixture])
        assert pytest_fixture.fixture_type_kind == "setup_and_teardown"

    def test_default_kind_before_classification_is_other(self):
        """FixtureResult's own default (before any post-processing pass
        runs) is 'other' -- the same safe fallback _classify_fixture_kind()
        itself returns for anything it can't place."""
        assert _fixture("before_each").fixture_type_kind == "other"
