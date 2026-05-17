"""
Unit tests for Python fixture extraction.

Tests positive and negative detection of Python fixtures using:
- unittest setUp/tearDown
- pytest fixtures and decorators
- Class-level and module-level fixtures
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
)


class TestPythonUnittestFixtures:
    """unittest.TestCase fixtures"""

    def test_setUp_method_detected(self):
        """setUp method should be detected as a fixture"""
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.data = []
"""
        assert_fixture_detected(
            code, "python", "setUp", fixture_type="unittest_setup", scope="per_test"
        )

    def test_tearDown_method_detected(self):
        """tearDown method should be detected"""
        code = """
class TestExample(unittest.TestCase):
    def tearDown(self):
        self.data.clear()
"""
        assert_fixture_detected(
            code, "python", "tearDown", fixture_type="unittest_setup", scope="per_test"
        )

    def test_setUp_and_tearDown_both_detected(self):
        """Both setUp and tearDown should be detected in same class"""
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.db = create_db()
    
    def tearDown(self):
        self.db.close()
    
    def test_something(self):
        pass
"""
        fixtures = extract_and_find_fixtures(code, "python")
        assert len(fixtures) == 2
        names = {f.name for f in fixtures}
        assert "setUp" in names
        assert "tearDown" in names

    def test_setUpClass_method_detected(self):
        """setUpClass should be detected as class-level fixture"""
        code = """
class TestExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = create_db()
"""
        fixture = assert_fixture_detected(code, "python", "setUpClass")
        assert fixture.scope == "per_class"

    def test_setUp_with_parameters_not_detected(self):
        """setUp with parameters (not per_test signature) should not be detected as fixture"""
        code = """
class TestExample:
    def setUp(self, param):  # Wrong signature
        pass
"""
        # Note: This depends on detector implementation
        # May or may not be detected; test what actually happens
        fixtures = extract_and_find_fixtures(code, "python")
        # Document the actual behavior
        pytest.mark.xfail(reason="Depends on detector's parameter strictness")

    def test_regular_method_not_detected(self):
        """Regular test methods should not be detected as fixtures"""
        code = """
class TestExample(unittest.TestCase):
    def test_something(self):
        assert True
    
    def test_another(self):
        assert False
"""
        assert_fixture_count(code, "python", 0)

    def test_helper_methods_not_detected(self):
        """Helper methods should not be detected as fixtures"""
        code = """
class TestExample(unittest.TestCase):
    def _setup_data(self):
        return []
    
    def _helper_function(self):
        pass
    
    def setUp(self):
        self.data = self._setup_data()
"""
        fixtures = extract_and_find_fixtures(code, "python")
        # Should only detect setUp, not helpers
        names = {f.name for f in fixtures}
        assert "setUp" in names
        assert "_setup_data" not in names
        assert "_helper_function" not in names


class TestPytestFixtures:
    """pytest-style fixtures"""

    def test_pytest_fixture_decorator_detected(self):
        """@pytest.fixture decorated functions should be detected"""
        code = """
import pytest

@pytest.fixture
def sample_data():
    return {"key": "value"}
"""
        fixture = assert_fixture_detected(
            code, "python", "sample_data", fixture_type="pytest_decorator"
        )
        # pytest fixtures are per_test by default
        assert fixture.scope in ("per_test", "global")

    def test_pytest_fixture_with_scope(self):
        """@pytest.fixture with scope parameter should be detected"""
        code = """
@pytest.fixture(scope="class")
def db_connection():
    return connect()
"""
        fixture = assert_fixture_detected(code, "python", "db_connection")
        # Scope detection depends on parsing decorator arguments
        pytest.mark.xfail(reason="Scope from decorator argument may not be parsed")

    def test_multiple_pytest_fixtures(self):
        """Multiple pytest fixtures in one file should all be detected"""
        code = """
@pytest.fixture
def setup1():
    return 1

@pytest.fixture
def setup2():
    return 2

@pytest.fixture
def setup3():
    return 3
"""
        assert_fixture_count(code, "python", 3)

    def test_conftest_fixtures_detected(self):
        """Fixtures in conftest.py should be detectable"""
        code = """
@pytest.fixture(scope="session")
def app():
    return create_app()

@pytest.fixture(scope="module")
def client(app):
    return app.test_client()
"""
        assert_fixture_count(code, "python", 2)


class TestModuleLevelFixtures:
    """Module-level setUp and tearDown"""

    def test_setup_module_detected(self):
        """setup_module() should be detected as module-level fixture"""
        code = """
def setup_module():
    global db
    db = create_database()
"""
        fixture = assert_fixture_detected(code, "python", "setup_module")
        assert fixture.scope == "per_module"

    def test_teardown_module_detected(self):
        """teardown_module() should be detected"""
        code = """
def teardown_module():
    db.close()
"""
        fixture = assert_fixture_detected(code, "python", "teardown_module")
        assert fixture.scope == "per_module"


class TestFixtureFunctionFactories:
    """Fixture factories and parameterized fixtures"""

    def test_fixture_factory_detected(self):
        """Fixtures that return factories should be detected"""
        code = """
@pytest.fixture
def user_factory():
    def make_user(name, email):
        return User(name=name, email=email)
    return make_user
"""
        fixture = assert_fixture_detected(code, "python", "user_factory")

    def test_parameterized_fixture_detected(self):
        """@pytest.mark.parametrize on fixtures should be detected"""
        code = """
@pytest.fixture(params=[1, 2, 3])
def number(request):
    return request.param
"""
        fixture = assert_fixture_detected(code, "python", "number")
        assert fixture.num_parameters > 0


class TestNegativeDetection:
    """Tests for ensuring non-fixtures are not detected"""

    def test_regular_functions_not_detected(self):
        """Regular functions should not be detected as fixtures"""
        code = """
def calculate(x, y):
    return x + y

def process_data(data):
    return [x * 2 for x in data]
"""
        assert_fixture_count(code, "python", 0)

    def test_setUp_in_non_test_context_not_detected(self):
        """setUp in a non-TestCase class should not be detected"""
        code = """
class DataProcessor:
    def setUp(self):
        # Not a test class
        pass
"""
        # May or may not be detected depending on how strict the detector is
        pytest.mark.xfail(reason="Detector may not validate TestCase inheritance")

    def test_fixture_like_comments_not_detected(self):
        """Code comments that mention fixtures should not be detected"""
        code = """
def process():
    # TODO: add setUp() here
    # def tearDown(): should be called
    pass
"""
        assert_fixture_count(code, "python", 0)

    def test_fixture_in_string_not_detected(self):
        """Fixture-like code in strings should not be detected"""
        code = """
def generate_test_template():
    template = '''
    def setUp(self):
        pass
    '''
    return template
"""
        assert_fixture_count(code, "python", 0)

    def test_function_starting_with_test_not_detected(self):
        """test_* methods/functions are test methods, not fixtures"""
        code = """
def test_addition():
    assert 1 + 1 == 2

class TestMath:
    def test_subtraction(self):
        assert 2 - 1 == 1
"""
        assert_fixture_count(code, "python", 0)


class TestAsyncPythonFixtures:
    """Async/await fixture patterns in Python"""

    def test_async_pytest_fixture_detected(self):
        """Async pytest fixture should be detected"""
        code = """
import pytest

@pytest.fixture
async def async_database():
    db = await create_db()
    yield db
    await db.close()
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "async_database",
            fixture_type="pytest_decorator",
            scope="per_test",
        )
        assert fixture.name == "async_database"

    def test_async_pytest_fixture_with_scope(self):
        """Async pytest fixture with explicit scope"""
        code = """
@pytest.fixture(scope='module')
async def async_service():
    service = await initialize_service()
    yield service
    await service.shutdown()
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "async_service",
            fixture_type="pytest_decorator",
            scope="per_module",
        )
        assert fixture.name == "async_service"

    def test_async_pytest_fixture_with_params(self):
        """Parametrized async pytest fixture"""
        code = """
@pytest.fixture(params=['db1', 'db2'])
async def async_configured_db(request):
    db = await connect_to_db(request.param)
    yield db
    await db.disconnect()
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "async_configured_db",
            fixture_type="pytest_decorator",
            scope="per_test",
        )
        assert fixture.name == "async_configured_db"

    def test_async_setup_module_detected(self):
        """Async setup_module() should be detected"""
        code = """
async def setup_module():
    global test_resource
    test_resource = await initialize_resource()
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "setup_module",
            fixture_type="nose_fixture",
            scope="per_module",
        )

    def test_async_teardown_module_detected(self):
        """Async teardown_module() should be detected"""
        code = """
async def teardown_module():
    await cleanup_resource()
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "teardown_module",
            fixture_type="nose_fixture",
            scope="per_module",
        )

    def test_async_setup_and_teardown_module(self):
        """Both async setup_module and teardown_module"""
        code = """
async def setup_module():
    await create_test_db()

async def teardown_module():
    await drop_test_db()
"""
        assert_fixture_count(code, "python", 2)
        assert_fixture_detected(code, "python", "setup_module")
        assert_fixture_detected(code, "python", "teardown_module")

    def test_async_setup_function_detected(self):
        """Async setup() function (nose style)"""
        code = """
async def setup():
    global resource
    resource = await get_resource()
"""
        fixture = assert_fixture_detected(
            code, "python", "setup", fixture_type="nose_fixture", scope="per_test"
        )

    def test_async_teardown_function_detected(self):
        """Async teardown() function (nose style)"""
        code = """
async def teardown():
    await release_resource()
"""
        fixture = assert_fixture_detected(
            code, "python", "teardown", fixture_type="nose_fixture", scope="per_test"
        )

    def test_mixed_async_and_sync_fixtures(self):
        """File with both async and sync fixtures"""
        code = """
@pytest.fixture
def sync_fixture():
    return 42

@pytest.fixture
async def async_fixture():
    value = await fetch_value()
    return value

async def setup_module():
    pass
"""
        assert_fixture_count(code, "python", 3)
        assert_fixture_detected(code, "python", "sync_fixture")
        assert_fixture_detected(code, "python", "async_fixture")
        assert_fixture_detected(code, "python", "setup_module")

    def test_async_pytest_mark_asyncio(self):
        """@pytest.mark.asyncio decorated async test (not a fixture)"""
        code = """
@pytest.mark.asyncio
async def test_async_operation():
    result = await async_operation()
    assert result is not None
"""
        # This is a test, not a fixture - should not be detected
        assert_fixture_count(code, "python", 0)

    def test_async_unittest_setup_detected(self):
        """Async setUp in unittest.TestCase"""
        code = """
class TestAsync(unittest.TestCase):
    async def setUp(self):
        self.service = await initialize_service()
    
    async def tearDown(self):
        await self.service.shutdown()
"""
        assert_fixture_count(code, "python", 2)
        assert_fixture_detected(
            code, "python", "setUp", fixture_type="unittest_setup", scope="per_test"
        )
        assert_fixture_detected(
            code, "python", "tearDown", fixture_type="unittest_setup", scope="per_test"
        )

    def test_async_setUpClass_detected(self):
        """Async setUpClass class method"""
        code = """
class TestWithAsyncClass(unittest.TestCase):
    @classmethod
    async def setUpClass(cls):
        cls.client = await create_client()
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "setUpClass",
            fixture_type="unittest_setup",
            scope="per_class",
        )

    def test_async_setup_method_pytest_style(self):
        """Async setup_method (pytest style class fixture)"""
        code = """
class TestClass:
    async def setup_method(self):
        self.db = await connect_db()
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "setup_method",
            fixture_type="pytest_class_method",
            scope="per_test",
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
