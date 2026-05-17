"""
Integration tests for Python fixture extraction on realistic code.

Tests extraction on actual test files with multiple fixtures, complex
patterns, and real-world code from popular Python frameworks.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_count,
)


class TestPythonDjangoFixtures:
    """Integration tests using Django test code"""

    def test_django_test_case_hierarchy(self):
        """Realistic Django test case with multiple fixtures"""
        code = """
from django.test import TestCase, TransactionTestCase, Client

class UserModelTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slow_db_setup_called = True
    
    @classmethod
    def tearDownClass(cls):
        cls.slow_db_teardown_called = True
        super().tearDownClass()
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='pass123'
        )
    
    def tearDown(self):
        User.objects.all().delete()
        self.user = None
"""
        assert_fixture_count(code, "python", 4)

        assert_fixture_detected(code, "python", "setUpClass")
        assert_fixture_detected(code, "python", "tearDownClass")
        assert_fixture_detected(code, "python", "setUp")
        assert_fixture_detected(code, "python", "tearDown")


class TestPythonPytestFixtures:
    """Integration tests using pytest patterns"""

    def test_pytest_parametrized_fixture(self):
        """Pytest with parametrized fixtures"""
        code = """
import pytest

@pytest.fixture(params=['db', 'cache', 'memory'])
def backend(request):
    if request.param == 'db':
        return Database(':memory:')
    elif request.param == 'cache':
        return MemoryCache()
    else:
        return InMemoryBackend()

@pytest.fixture
def cleanup(backend):
    yield backend
    backend.close()

class TestBackends:
    def test_all_backends(self, cleanup):
        assert cleanup is not None
"""
        assert_fixture_count(code, "python", 2)
        assert_fixture_detected(code, "python", "backend")
        assert_fixture_detected(code, "python", "cleanup")


class TestPythonSQLAlchemyFixtures:
    """Integration tests using SQLAlchemy patterns"""

    def test_sqlalchemy_session_fixture(self):
        """Real SQLAlchemy session fixture pattern"""
        code = """
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

@pytest.fixture(scope='session')
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture(scope='function')
def session(db):
    connection = db.connect()
    transaction = connection.begin()
    Session = scoped_session(sessionmaker(bind=connection))
    
    yield Session
    
    transaction.rollback()
    connection.close()
    Session.remove()

@pytest.fixture
def populated_session(session):
    user = User(username='test')
    session.add(user)
    session.commit()
    return session
"""
        assert_fixture_count(code, "python", 3)


class TestPythonLargeTestModule:
    """Integration test on larger, more complex test module"""

    def test_large_python_test_module(self):
        """Integration test on 200+ line fixture-heavy module"""
        code = """
import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

class TestBaseFixture:
    @pytest.fixture(scope='class')
    def base_setup(self):
        return {'config': 'test'}

@pytest.fixture(scope='session')
def session_db():
    db = Database(':memory:')
    db.init()
    yield db
    db.close()

@pytest.fixture(scope='module')
def module_cache(session_db):
    cache = Cache(session_db)
    cache.initialize()
    return cache

@pytest.fixture
def temp_dir():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    import shutil
    shutil.rmtree(tmpdir)

@pytest.fixture
def mock_api():
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = {'status': 'ok'}
        yield mock_get

class TestModule(TestBaseFixture):
    @pytest.fixture
    def instance(self, module_cache, temp_dir):
        return TestClass(cache=module_cache, tmpdir=temp_dir)
    
    def test_something(self, instance):
        assert instance is not None

@pytest.fixture(autouse=True)
def reset_state():
    yield
    cleanup_state()

def setup_module():
    global MODULE_SETUP_DONE
    MODULE_SETUP_DONE = True

def teardown_module():
    global MODULE_SETUP_DONE
    MODULE_SETUP_DONE = False
"""
        # Should detect all fixtures
        assert_fixture_count(code, "python", 9)


class TestPythonFixtureDependencies:
    """Integration tests for fixtures with dependencies"""

    def test_pytest_fixture_dependency_chain(self):
        """Fixtures depending on other fixtures"""
        code = """
@pytest.fixture
def user_data():
    return {'id': 1, 'name': 'John'}

@pytest.fixture
def user(user_data):
    return User(**user_data)

@pytest.fixture
def authenticated_user(user):
    user.authenticate()
    return user

def test_auth(authenticated_user):
    assert authenticated_user.is_authenticated
"""
        fixtures = extract_and_find_fixtures(code, "python")
        user_data = [f for f in fixtures if f.name == "user_data"][0]
        user = [f for f in fixtures if f.name == "user"][0]
        auth_user = [f for f in fixtures if f.name == "authenticated_user"][0]

        # All should have correct parameters
        assert user_data.num_parameters == 0
        assert user.num_parameters == 1
        assert auth_user.num_parameters == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
