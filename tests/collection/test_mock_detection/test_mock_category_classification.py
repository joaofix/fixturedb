"""Tests for the identifier-keyword mock category classification mechanism
itself (`_classify_mock_category()`), as distinct from the per-framework
pattern coverage tests (test_{python,java,javascript,typescript}_mock_patterns.py).

Detection (is there a mock, which framework) and categorization (which
test-double category) are separate concerns since the category rework:
this file exercises categorization directly via `_classify_mock_category()`
(pure, no parsing needed) plus a couple of end-to-end fixture-extraction
checks confirming the two are actually wired together correctly.
"""

from __future__ import annotations

import pytest

from collection.detector_shared import _classify_mock_category

from ..conftest import assert_fixture_detected


class TestClassifyMockCategoryUnit:
    """Direct tests of the priority-order substring scan."""

    def test_dummy_identifier_wins_over_generic_mock_call(self):
        assert _classify_mock_category("dummy_request = Mock()") == "dummy"

    def test_dummies_plural_matches(self):
        assert _classify_mock_category("dummies_list = [Mock()]") == "dummy"

    def test_stub_identifier(self):
        assert _classify_mock_category("user_stub = Mock()") == "stub"

    def test_spy_identifier(self):
        assert _classify_mock_category("logger_spy = Mock()") == "spy"

    def test_spies_plural_matches(self):
        assert _classify_mock_category("logger_spies = Mock()") == "spy"

    def test_fake_identifier(self):
        assert _classify_mock_category("fake_db = Mock()") == "fake"

    def test_no_keyword_falls_back_to_mock(self):
        """No category keyword anywhere -- falls back to "mock", the
        generic/least-specific term, not an error or empty string."""
        assert _classify_mock_category("service = Mock()") == "mock"

    def test_case_insensitive(self):
        assert _classify_mock_category("DUMMY_REQUEST = Mock()") == "dummy"
        assert _classify_mock_category("Stub_Service = Mock()") == "stub"

    def test_priority_order_dummy_beats_everything(self):
        assert _classify_mock_category("dummy_stub_spy_fake_mock") == "dummy"

    def test_priority_order_stub_beats_spy_fake_mock(self):
        assert _classify_mock_category("stub_spy_fake_mock") == "stub"

    def test_priority_order_spy_beats_fake_mock(self):
        assert _classify_mock_category("spy_fake_mock") == "spy"

    def test_priority_order_fake_beats_mock(self):
        assert _classify_mock_category("fake_mock") == "fake"

    def test_stubs_plural_matches_via_substring(self):
        """Not one of the advisor's explicitly-listed plurals (only
        dummy/dummies and spy/spies are), but "stub" is a substring of
        "stubs" -- caught for free by substring (not word-boundary)
        matching, same as "mocks"/"fakes"."""
        assert _classify_mock_category("pending_stubs = []") == "stub"


class TestMockCategoryEndToEnd:
    """Confirm classification is actually wired into real fixture
    extraction, not just correct in isolation."""

    def test_dummy_named_mock_in_real_fixture(self):
        code = """
@pytest.fixture
def dummy_request():
    return Mock()
"""
        fixture = assert_fixture_detected(code, "python", "dummy_request")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].category == "dummy"

    def test_keyword_free_mock_falls_back_in_real_fixture(self):
        code = """
@pytest.fixture
def service():
    return Mock()
"""
        fixture = assert_fixture_detected(code, "python", "service")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].category == "mock"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
