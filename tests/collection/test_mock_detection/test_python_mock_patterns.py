"""
Mock detection tests for Python fixtures.

Validates that the extractor correctly identifies mock usage patterns
in Python test fixtures.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
)


class TestPythonUnittestMockPatterns:
    """Python unittest.mock patterns"""

    def test_unittest_mock_detection(self):
        """unittest.mock usage in setUp should be detected as part of fixture"""
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
        assert fixture.name == "setUp"

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


class TestPytestMockPatterns:
    """Python pytest-mock patterns"""

    def test_pytest_mock_fixture(self):
        """pytest-mock mocker fixture should be detected"""
        code = """
@pytest.fixture
def user_service(mocker):
    service = UserService()
    mocker.patch.object(service, 'get_user', return_value={'id': 1})
    return service
"""
        fixture = assert_fixture_detected(code, "python", "user_service")
        assert fixture.fixture_type == "pytest_decorator"
        assert fixture.num_parameters >= 1

    def test_monkeypatch_fixture(self):
        """pytest monkeypatch built-in fixture parameter"""
        code = """
@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv('ENV', 'test')
    return {'key': 'value'}
"""
        fixture = assert_fixture_detected(code, "python", "config")
        assert fixture.num_parameters >= 1


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

    def test_pytest_mock_imports(self):
        """Code using pytest-mock should be distinguishable"""
        code = """
@pytest.fixture
def my_test(mocker):
    mock = mocker.Mock()
    return mock
"""
        fixture = assert_fixture_detected(code, "python", "my_test")
        assert fixture.num_parameters >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
