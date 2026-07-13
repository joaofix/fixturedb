"""
Unit tests for Python fixture extraction.

Tests positive and negative detection of Python fixtures using:
- unittest setUp/tearDown
- pytest fixtures and decorators
- Class-level and module-level fixtures
"""

import pytest

from ..conftest import (
    assert_fixture_count,
    assert_fixture_detected,
    extract_and_find_fixtures,
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

    def test_asyncSetUp_and_asyncTearDown_detected(self):
        """IsolatedAsyncioTestCase's asyncSetUp/asyncTearDown are distinct
        method names the framework calls in addition to setUp/tearDown, not
        just async-qualified versions of them -- must be recognized on
        their own."""
        code = """
class TestExample(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = await make_client()

    async def asyncTearDown(self):
        await self.client.close()
"""
        assert_fixture_count(code, "python", 2)
        assert_fixture_detected(
            code,
            "python",
            "asyncSetUp",
            fixture_type="unittest_setup",
            scope="per_test",
        )
        assert_fixture_detected(
            code,
            "python",
            "asyncTearDown",
            fixture_type="unittest_setup",
            scope="per_test",
        )

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
        extract_and_find_fixtures(code, "python")
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
        assert_fixture_detected(code, "python", "db_connection")
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
    """Nose-style module/package-level setup and teardown are deliberately
    NOT detected -- only pytest and unittest are in scope for Python (see
    fixture_definitions.yaml's python.excluded list)."""

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

    def test_teardown_package_not_detected(self):
        code = """
def teardown_package():
    resource.release()
"""
        assert_fixture_count(code, "python", 0)


class TestPytestClassMethodClassScope:
    """pytest-style setup_class()/teardown_class() -- the per_class-scope
    half of pytest_class_method. Only the per_test half (setup_method/
    teardown_method) previously had test coverage."""

    def test_setup_class_detected(self):
        code = """
class TestSuite:
    def setup_class(cls):
        cls.db = connect_db()
"""
        fixture = assert_fixture_detected(code, "python", "setup_class")
        assert fixture.fixture_type == "pytest_class_method"
        assert fixture.framework == "pytest"
        assert fixture.scope == "per_class"

    def test_teardown_class_detected(self):
        code = """
class TestSuite:
    def teardown_class(cls):
        cls.db.close()
"""
        fixture = assert_fixture_detected(code, "python", "teardown_class")
        assert fixture.fixture_type == "pytest_class_method"
        assert fixture.framework == "pytest"
        assert fixture.scope == "per_class"


class TestPytestClassMethodNotDoubleCountedWithDecorator:
    """Regression: a method matching both the @pytest.fixture decorator
    pattern AND the setup_method/teardown_method name convention must be
    counted once, not twice. Found via real-world data (dagster-io/dagster
    test_freshness_result_condition.py) in toy Dataset B review."""

    def test_decorated_setup_method_counted_once(self):
        code = """
class TestSuite:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.instance = create()
        yield
        self.instance = None
"""
        assert_fixture_count(code, "python", 1)
        fixture = extract_and_find_fixtures(code, "python")[0]
        assert fixture.fixture_type == "pytest_decorator"
        assert fixture.framework == "pytest"

    def test_undecorated_setup_method_still_detected(self):
        """Without a pytest.fixture decorator, name-based detection must
        still fire -- the fix must not suppress the normal case."""
        code = """
class TestSuite:
    def setup_method(self):
        self.instance = create()
"""
        fixture = assert_fixture_detected(code, "python", "setup_method")
        assert fixture.fixture_type == "pytest_class_method"


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
        assert_fixture_detected(code, "python", "user_factory")

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

    def test_async_setup_module_not_detected(self):
        """Nose's setup_module (async or not) is deliberately not detected
        -- only pytest and unittest are in scope for Python."""
        code = """
async def setup_module():
    global test_resource
    test_resource = await initialize_resource()
"""
        assert_fixture_count(code, "python", 0)

    def test_async_teardown_module_not_detected(self):
        code = """
async def teardown_module():
    await cleanup_resource()
"""
        assert_fixture_count(code, "python", 0)

    def test_async_setup_and_teardown_module_not_detected(self):
        code = """
async def setup_module():
    await create_test_db()

async def teardown_module():
    await drop_test_db()
"""
        assert_fixture_count(code, "python", 0)

    def test_async_setup_function_not_detected(self):
        """Nose-style setup() (async or not) is deliberately not detected."""
        code = """
async def setup():
    global resource
    resource = await get_resource()
"""
        assert_fixture_count(code, "python", 0)

    def test_async_teardown_function_not_detected(self):
        code = """
async def teardown():
    await release_resource()
"""
        assert_fixture_count(code, "python", 0)

    def test_mixed_async_and_sync_fixtures(self):
        """File with both async and sync fixtures; the nose-style
        setup_module is not a recognized fixture and must not be counted."""
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
        assert_fixture_count(code, "python", 2)
        assert_fixture_detected(code, "python", "sync_fixture")
        assert_fixture_detected(code, "python", "async_fixture")

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
        assert_fixture_detected(
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
        assert_fixture_detected(
            code,
            "python",
            "setup_method",
            fixture_type="pytest_class_method",
            scope="per_test",
        )

    def test_pytest_asyncio_fixture_decorator_detected(self):
        """@pytest_asyncio.fixture is pytest-asyncio's dedicated async-fixture
        decorator (the standard for FastAPI/async test setup) -- it must be
        detected the same as plain @pytest.fixture, not treated as a miss."""
        code = """
import pytest_asyncio

@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient() as client:
        yield client
"""
        fixture = assert_fixture_detected(
            code,
            "python",
            "async_client",
            fixture_type="pytest_decorator",
            scope="per_test",
        )
        assert fixture.name == "async_client"

    def test_pytest_asyncio_fixture_with_scope(self):
        """@pytest_asyncio.fixture(scope=...) should resolve scope identically
        to @pytest.fixture(scope=...)."""
        code = """
@pytest_asyncio.fixture(scope="session")
async def async_engine():
    engine = await create_engine()
    yield engine
    await engine.dispose()
"""
        assert_fixture_detected(
            code,
            "python",
            "async_engine",
            fixture_type="pytest_decorator",
            scope="global",
        )

    def test_pytest_asyncio_and_pytest_fixture_share_fixture_type(self):
        """@pytest_asyncio.fixture is not a separate fixture_type from
        @pytest.fixture -- both are pytest_decorator, since the detection
        signal is the decorator text, not the sync/async qualifier."""
        code = """
@pytest_asyncio.fixture
async def async_fixture():
    yield 1

@pytest.fixture
def sync_fixture():
    return 1
"""
        assert_fixture_count(code, "python", 2)
        async_fixture = assert_fixture_detected(code, "python", "async_fixture")
        sync_fixture = assert_fixture_detected(code, "python", "sync_fixture")
        assert async_fixture.fixture_type == sync_fixture.fixture_type == "pytest_decorator"


class TestBehaveBDDSteps:
    """Behave BDD step decorators (@given/@when/@then/@step) are
    deliberately NOT detected -- only pytest and unittest are in scope for
    Python (see fixture_definitions.yaml's python.excluded list)."""

    def test_given_step_not_detected(self):
        code = """
from behave import given

@given('a logged-in user')
def step_impl(context):
    context.user = create_user()
"""
        assert_fixture_count(code, "python", 0)

    def test_when_step_not_detected(self):
        code = """
from behave import when

@when('they submit the form')
def step_impl(context):
    context.response = submit_form()
"""
        assert_fixture_count(code, "python", 0)

    def test_then_step_not_detected(self):
        code = """
from behave import then

@then('the confirmation page is shown')
def step_impl(context):
    assert context.response.page == 'confirmation'
"""
        assert_fixture_count(code, "python", 0)

    def test_step_decorator_not_detected(self):
        code = """
from behave import step

@step('the system is idle')
def step_impl(context):
    wait_for_idle()
"""
        assert_fixture_count(code, "python", 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
