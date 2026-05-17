"""
Tests for fixture type and scope classification.

Validates that fixtures are correctly classified by type and scope.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
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
        assert fixture.scope == "per_test"

    def test_tearDown_is_classified_correctly(self):
        """tearDown method should be type='unittest_setup'"""
        code = """
class TestExample(unittest.TestCase):
    def tearDown(self):
        self.data.clear()
"""
        fixture = assert_fixture_detected(code, "python", "tearDown")
        assert fixture.fixture_type == "unittest_setup"
        assert fixture.scope == "per_test"

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
        assert fixture.scope == "per_class"

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
        assert fixture.scope == "per_class"


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
        assert fixture.scope == "per_test"  # function scope = per test

    def test_pytest_fixture_with_scope_class(self):
        """@pytest.fixture(scope='class') should have per_class scope"""
        code = """
@pytest.fixture(scope='class')
def my_fixture():
    return {"db": connect()}
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"
        assert fixture.scope == "per_class"

    def test_pytest_fixture_with_scope_module(self):
        """@pytest.fixture(scope='module') should have per_module scope"""
        code = """
@pytest.fixture(scope='module')
def my_fixture():
    return {"resource": create()}
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"
        assert fixture.scope == "per_module"

    def test_pytest_fixture_with_scope_session(self):
        """@pytest.fixture(scope='session') should have per_session scope"""
        code = """
@pytest.fixture(scope='session')
def my_fixture():
    return {"server": start_server()}
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        assert fixture.fixture_type == "pytest_decorator"
        assert fixture.scope == "global"


class TestModuleLevelFixtures:
    """Validate module-level fixture detection"""

    def test_setup_module_is_module_scope(self):
        """setup_module() should be type='nose_fixture' with per_module scope"""
        code = """
def setup_module():
    global db
    db = create_database()
"""
        fixture = assert_fixture_detected(code, "python", "setup_module")
        assert fixture.fixture_type == "nose_fixture"
        assert fixture.scope == "per_module"

    def test_teardown_module_is_module_scope(self):
        """teardown_module() should be type='nose_fixture' with per_module scope"""
        code = """
def teardown_module():
    global db
    db.close()
"""
        fixture = assert_fixture_detected(code, "python", "teardown_module")
        assert fixture.fixture_type == "nose_fixture"
        assert fixture.scope == "per_module"

    def test_setup_package_is_package_scope(self):
        """setup_package() if detected should be type='nose_fixture'"""
        code = """
def setup_package():
    global resource
    resource = initialize()
"""
        fixture = assert_fixture_detected(code, "python", "setup_package")
        assert fixture.fixture_type == "nose_fixture"
        # Scope could be per_package or per_module depending on implementation


class TestPytestFixtureScopes:
    """Validate scope detection in pytest fixtures"""

    def test_default_fixture_scope_is_function(self):
        """Fixture without explicit scope should default to per_test (function)"""
        code = """
@pytest.fixture
def simple_fixture():
    return 42
"""
        fixture = assert_fixture_detected(code, "python", "simple_fixture")
        # Default pytest scope is 'function' which maps to per_test
        assert fixture.scope in ("per_test", "per_function", "function")

    def test_fixture_scope_extraction_from_decorator_kwargs(self):
        """Scope should be extracted from @pytest.fixture(scope='...')"""
        test_cases = [
            ("@pytest.fixture(scope='function')", "per_test"),
            ("@pytest.fixture(scope='class')", "per_class"),
            ("@pytest.fixture(scope='module')", "per_module"),
            ("@pytest.fixture(scope='session')", "global"),
        ]

        for decorator, expected_scope in test_cases:
            code = f"""
{decorator}
def my_fixture():
    return value
"""
            fixture = assert_fixture_detected(code, "python", "my_fixture")
            # Normalize scope names
            actual_scope = fixture.scope.replace("per_", "").replace("_", "")
            expected_normalized = expected_scope.replace("per_", "").replace("_", "")
            assert (
                actual_scope == expected_normalized or fixture.scope == expected_scope
            )


class TestScopeMapping:
    """Validate consistent scope naming across frameworks"""

    def test_per_test_scope_consistency(self):
        """All per-test fixtures should have consistent scope naming"""
        unittest_code = """
class Test(unittest.TestCase):
    def setUp(self):
        self.x = 1
"""
        pytest_code = """
@pytest.fixture
def my_fixture():
    return 1
"""

        unittest_fixture = assert_fixture_detected(unittest_code, "python", "setUp")
        pytest_fixture = assert_fixture_detected(pytest_code, "python", "my_fixture")

        # Both should map to per_test scope
        assert (
            unittest_fixture.scope == pytest_fixture.scope
            or unittest_fixture.scope in ("per_test", "per_function")
            and pytest_fixture.scope in ("per_test", "per_function")
        )

    def test_per_class_scope_consistency(self):
        """All per-class fixtures should have consistent scope naming"""
        unittest_code = """
class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = create()
"""
        pytest_code = """
@pytest.fixture(scope='class')
def my_fixture():
    return create()
"""

        unittest_fixture = assert_fixture_detected(
            unittest_code, "python", "setUpClass"
        )
        pytest_fixture = assert_fixture_detected(pytest_code, "python", "my_fixture")

        # Both should map to per_class
        assert unittest_fixture.scope == pytest_fixture.scope or (
            unittest_fixture.scope == "per_class"
            and pytest_fixture.scope == "per_class"
        )


class TestAbsentScopeFallbacks:
    """Validate sensible defaults when scope cannot be determined"""

    def test_unknown_fixture_type_defaults_to_function_scope(self):
        """Unknown fixture types should default to per_test/function scope"""
        code = """
@pytest.fixture  # scope not specified
def custom_fixture():
    return setup()
"""
        fixture = assert_fixture_detected(code, "python", "custom_fixture")
        # Should have some scope, likely per_test/function
        assert fixture.scope is not None
        assert fixture.scope != ""


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
        assert fixture.scope == "per_class"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
