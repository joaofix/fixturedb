"""
Tests for fixture type classification.

Validates that fixtures are correctly classified by fixture_type. `scope`
was dropped from FixtureResult entirely (not part of the extracted metric
set reported in the paper) -- this file used to also validate scope
classification; those assertions and the classes that existed purely for
scope (TestPytestFixtureScopes, TestScopeMapping, TestAbsentScopeFallbacks)
were removed rather than left checking a field that no longer exists.
"""

import pytest

from ..conftest import (
    assert_fixture_count,
    assert_fixture_detected,
)


class TestUnittestFixtureTypes:
    """Validate unittest framework fixture type detection"""

    def test_setUp_is_classified_correctly(self):
        """setUp method should be type='unittest_setup'"""
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.data = []
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.fixture_type == "unittest_setup"

    def test_tearDown_is_classified_correctly(self):
        """tearDown method should be type='unittest_setup'"""
        code = """
class TestExample(unittest.TestCase):
    def tearDown(self):
        self.data.clear()
"""
        fixture = assert_fixture_detected(code, "python", "tearDown")
        assert fixture.fixture_type == "unittest_setup"

    def test_setUpClass_is_classified_correctly(self):
        """setUpClass should be type='unittest_setup'"""
        code = """
class TestExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = create_db()
"""
        fixture = assert_fixture_detected(code, "python", "setUpClass")
        assert fixture.fixture_type == "unittest_setup"

    def test_tearDownClass_is_classified_correctly(self):
        """tearDownClass should be type='unittest_setup'"""
        code = """
class TestExample(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        cls.db.close()
"""
        fixture = assert_fixture_detected(code, "python", "tearDownClass")
        assert fixture.fixture_type == "unittest_setup"


class TestPytestFixtureTypes:
    """Validate pytest framework fixture type detection"""

    def test_pytest_fixture_decorator(self):
        """@pytest.fixture decorated function should be type='pytest_decorator'"""
        code = """
@pytest.fixture
def my_fixture():
    return {"data": [1, 2, 3]}
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"

    def test_pytest_fixture_with_scope_function(self):
        """@pytest.fixture(scope='function') should be type='pytest_decorator'"""
        code = """
@pytest.fixture(scope='function')
def my_fixture():
    return 42
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"

    def test_pytest_fixture_with_scope_class(self):
        """@pytest.fixture(scope='class') should still be type='pytest_decorator'"""
        code = """
@pytest.fixture(scope='class')
def my_fixture():
    return {"db": connect()}
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"

    def test_pytest_fixture_with_scope_module(self):
        """@pytest.fixture(scope='module') should still be type='pytest_decorator'"""
        code = """
@pytest.fixture(scope='module')
def my_fixture():
    return {"resource": create()}
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"

    def test_pytest_fixture_with_scope_session(self):
        """@pytest.fixture(scope='session') should still be type='pytest_decorator'"""
        code = """
@pytest.fixture(scope='session')
def my_fixture():
    return {"server": start_server()}
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"


class TestModuleLevelFixtures:
    """nose's module-level setup_module/teardown_module/setup_package are
    deliberately NOT detected -- only pytest and unittest are in scope for
    Python (see fixture_definitions.yaml's python.excluded list)."""

    def test_setup_module_not_detected(self):
        code = """
def setup_module():
    global db
    db = create_database()
"""
        assert_fixture_count(code, "python", 0)

    def test_teardown_module_not_detected(self):
        code = """
def teardown_module():
    global db
    db.close()
"""
        assert_fixture_count(code, "python", 0)

    def test_setup_package_not_detected(self):
        code = """
def setup_package():
    global resource
    resource = initialize()
"""
        assert_fixture_count(code, "python", 0)


class TestFixtureTypeFromDecorators:
    """Validate fixture type detection from decorators"""

    def test_pytest_fixture_single_line_decorator(self):
        """@pytest.fixture on single line should be detected"""
        code = """
@pytest.fixture
def my_fixture(): return 1
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"

    def test_pytest_fixture_multiline_decorator(self):
        """@pytest.fixture(...) split across lines should be detected"""
        code = """
@pytest.fixture(
    scope='module',
    autouse=False
)
def my_fixture():
    return 1
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"


class TestMultipleDecorators:
    """Validate fixtures with multiple decorators"""

    def test_fixture_with_multiple_decorators(self):
        """Fixture with multiple decorators should still be detected"""
        code = """
@pytest.fixture(scope='module')
@some_other_decorator
def my_fixture():
    return value
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"

    def test_decorated_unittest_fixture(self):
        """setUpClass with @classmethod should be detected"""
        code = """
class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x = 1
"""
        fixture = assert_fixture_detected(code, "python", "setUpClass")
        assert fixture.fixture_type == "unittest_setup"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
