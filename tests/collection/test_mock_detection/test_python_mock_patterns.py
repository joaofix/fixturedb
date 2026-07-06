"""
Mock detection tests for Python fixtures.

Validates that the extractor correctly identifies mock usage patterns
in Python test fixtures -- these assert on `fixture.mocks` directly, not
just that the surrounding fixture was extracted, since a fixture can be
detected correctly while its mock usage inside is silently missed (as
mocker.patch.object(...) was until this file's tests were tightened).
"""

import pytest

from ..conftest import (
    assert_fixture_detected,
)


class TestPythonUnittestMockPatterns:
    """Python unittest.mock patterns"""

    def test_unittest_mock_patch_dotted_path(self):
        """mock.patch('dotted.path') should be detected with the dotted
        path as target_identifier."""
        code = """
@pytest.fixture
def svc():
    with mock.patch('module.function') as m:
        yield m
"""
        fixture = assert_fixture_detected(code, "python", "svc")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "unittest_mock"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "module.function"

    def test_unittest_mock_bare_patch(self):
        """`from unittest.mock import patch` then calling it unqualified
        (patch('dotted.path'), no "mock." prefix) is at least as common an
        idiom as mock.patch(...) -- previously not covered at all."""
        code = """
import unittest
from unittest.mock import Mock, patch

class Test(unittest.TestCase):
    def setUp(self):
        self.mock = Mock()
        self.patcher = patch('module.function')
        self.mock_func = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        frameworks = {m.framework for m in fixture.mocks}
        assert frameworks == {"unittest_mock"}
        targets = {m.target_identifier for m in fixture.mocks}
        assert "module.function" in targets

    def test_unittest_mock_bare_patch_does_not_double_count_qualified_form(self):
        """The bare-patch pattern must not also match mock.patch(...)/
        mocker.patch(...) -- that would double-count a single call site as
        two separate MockResult entries."""
        code = """
@pytest.fixture
def svc():
    with mock.patch('module.function') as m:
        yield m
"""
        fixture = assert_fixture_detected(code, "python", "svc")
        assert len(fixture.mocks) == 1

    def test_unittest_mock_bare_patch_object(self):
        """Bare patch.object(...) (no "mock." prefix) should be detected."""
        code = """
@pytest.fixture
def svc():
    with patch.object(Service, 'call') as m:
        yield m
"""
        fixture = assert_fixture_detected(code, "python", "svc")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "unittest_mock"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "Service"

    def test_unittest_mock_patch_object(self):
        """mock.patch.object(target, 'attr') is a distinct call shape from
        mock.patch('dotted.path') -- previously missed entirely since the
        plain .patch( pattern requires an opening paren immediately after
        "patch", which .object( breaks."""
        code = """
@pytest.fixture
def svc():
    with mock.patch.object(Service, 'call') as m:
        m.return_value = 1
        yield m
"""
        fixture = assert_fixture_detected(code, "python", "svc")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "unittest_mock"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "Service"

    def test_create_autospec(self):
        """create_autospec(RealClass) should be detected as unittest_mock,
        category "mock" -- a documented override since "create_autospec"
        contains no category keyword itself (see category_override_reason
        in feature_extraction_patterns.yaml)."""
        code = """
@pytest.fixture
def api():
    return create_autospec(RealApi)
"""
        fixture = assert_fixture_detected(code, "python", "api")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "unittest_mock"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "RealApi"

    def test_magicmock_usage(self):
        """MagicMock in setUp fixture"""
        code = """
from unittest.mock import MagicMock

def setUp(self):
    self.magic = MagicMock()
    self.magic.method.return_value = 42
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.num_objects_instantiated >= 1
        assert any(m.framework == "unittest_mock" for m in fixture.mocks)


class TestPytestMockPatterns:
    """Python pytest-mock patterns"""

    def test_pytest_mock_patch_object(self):
        """mocker.patch.object(...) is pytest-mock's equivalent of
        mock.patch.object(...) -- same previously-missed call shape."""
        code = """
@pytest.fixture
def user_service(mocker):
    service = UserService()
    mocker.patch.object(service, 'get_user', return_value={'id': 1})
    return service
"""
        fixture = assert_fixture_detected(code, "python", "user_service")
        assert fixture.fixture_type == "pytest_decorator"
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "pytest_mock"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "service"
        # return_value= is one configured interaction
        assert fixture.mocks[0].num_interactions_configured >= 1

    def test_pytest_mock_patch_string_target(self):
        """mocker.patch('dotted.path') should be detected as pytest_mock."""
        code = """
@pytest.fixture
def patched(mocker):
    mocker.patch('module.function')
"""
        fixture = assert_fixture_detected(code, "python", "patched")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "pytest_mock"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "module.function"

    def test_monkeypatch_fixture(self):
        """pytest's built-in monkeypatch fixture (setattr/setenv/etc.) is a
        different concept from a mock *library*, but the same
        test-isolation-via-patching idea num_mocks is meant to capture --
        previously not covered at all. Category is "stub" (a documented
        override): monkeypatch substitutes predetermined behavior with no
        built-in call-verification API, unlike a mock."""
        code = """
@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv('ENV', 'test')
    return {'key': 'value'}
"""
        fixture = assert_fixture_detected(code, "python", "config")
        assert fixture.num_parameters >= 1
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "pytest_monkeypatch"
        assert fixture.mocks[0].category == "stub"
        assert fixture.mocks[0].target_identifier == "setenv"


class TestPythonMockFrameworkDetection:
    """Validate detection of mock framework types"""

    def test_unittest_mock_imports(self):
        """Code using unittest.mock should be distinguishable"""
        code = """
from unittest.mock import Mock, patch, MagicMock

def setUp(self):
    self.mock = Mock()
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.num_objects_instantiated >= 1
        assert fixture.mocks and fixture.mocks[0].framework == "unittest_mock"

    def test_pytest_mock_imports(self):
        """Code using pytest-mock's mocker.Mock() proxy should still be
        detected (it forwards to the same unittest.mock.Mock class, so the
        framework is recorded as unittest_mock -- there is no separate
        pytest-mock Mock class to distinguish it by)."""
        code = """
@pytest.fixture
def my_test(mocker):
    mock = mocker.Mock()
    return mock
"""
        fixture = assert_fixture_detected(code, "python", "my_test")
        assert fixture.num_parameters >= 1
        assert fixture.mocks and fixture.mocks[0].framework == "unittest_mock"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
