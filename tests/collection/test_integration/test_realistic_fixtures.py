"""
Integration tests for fixture extraction on realistic code samples.

Tests extraction on actual test files with multiple fixtures, inheritance,
complex hierarchies, and real-world patterns from popular projects.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
)


class TestRealWorldPythonFixtures:
    """Integration tests using realistic Python test code"""

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

        # Verify each fixture is detected
        assert_fixture_detected(code, "python", "setUpClass")
        assert_fixture_detected(code, "python", "tearDownClass")
        assert_fixture_detected(code, "python", "setUp")
        assert_fixture_detected(code, "python", "tearDown")

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


class TestRealWorldJavaFixtures:
    """Integration tests using realistic Java test code"""

    def test_junit5_complex_hierarchy(self):
        """JUnit 5 test with multiple lifecycle methods"""
        code = """
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;

@ExtendWith(SpringExtension.class)
@SpringBootTest
public class UserServiceTest {
    private UserRepository repository;
    private UserService service;
    
    @BeforeAll
    public static void setUpAll() {
        System.out.println("Setting up all tests");
    }
    
    @BeforeEach
    public void setUp() {
        repository = mock(UserRepository.class);
        service = new UserService(repository);
    }
    
    @AfterEach
    public void tearDown() {
        repository = null;
        service = null;
    }
    
    @AfterAll
    public static void tearDownAll() {
        System.out.println("Tearing down all tests");
    }
    
    @Nested
    class UserCreationTests {
        @BeforeEach
        void setUp() {
            when(repository.save(any())).thenReturn(new User());
        }
        
        @Test
        void testCreateUser() {
            assert service != null;
        }
    }
}
"""
        # Should detect all lifecycle methods
        assert_fixture_detected(code, "java", "setUpAll")
        assert_fixture_detected(code, "java", "setUp")
        assert_fixture_detected(code, "java", "tearDown")
        assert_fixture_detected(code, "java", "tearDownAll")

    def test_testng_dataprovider_setup(self):
        """TestNG with DataProvider and setup methods"""
        code = """
import org.testng.annotations.*;

@Test
public class DataProviderTests {
    private WebDriver driver;
    
    @BeforeClass
    public void setUpClass() {
        System.setProperty("webdriver.chrome.driver", "/path/to/chromedriver");
    }
    
    @BeforeMethod
    public void setUp() {
        driver = new ChromeDriver();
        driver.manage().timeouts().implicitlyWait(10, TimeUnit.SECONDS);
    }
    
    @AfterMethod
    public void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }
    
    @DataProvider(name = "testData")
    public Object[][] provideTestData() {
        return new Object[][] {
            {"user1", "pass1"},
            {"user2", "pass2"}
        };
    }
}
"""
        assert_fixture_detected(code, "java", "setUpClass")
        assert_fixture_detected(code, "java", "setUp")
        assert_fixture_detected(code, "java", "tearDown")


class TestRealWorldJavaScriptFixtures:
    """Integration tests using realistic JavaScript test code"""

    def test_jest_complex_setup(self):
        """Jest test file with multiple setup methods and fixtures"""
        code = """
const { setupDatabase, teardownDatabase } = require('./db-setup');

describe('User API', () => {
    let app;
    let request;
    
    beforeAll(async () => {
        await setupDatabase();
        app = require('./app');
        request = require('supertest')(app);
    });
    
    beforeEach(() => {
        jest.clearAllMocks();
    });
    
    afterEach(async () => {
        await User.deleteMany({});
    });
    
    afterAll(async () => {
        await teardownDatabase();
    });
    
    describe('POST /users', () => {
        beforeEach(() => {
            jest.spyOn(console, 'log').mockImplementation();
        });
        
        afterEach(() => {
            console.log.mockRestore();
        });
        
        test('should create user', async () => {
            const response = await request.post('/users');
        });
    });
});
"""
        assert_fixture_with_type_detected(code, "javascript", "before_all")
        assert_fixture_with_type_detected(code, "javascript", "before_each", count=2)
        assert_fixture_with_type_detected(code, "javascript", "after_each", count=2)
        assert_fixture_with_type_detected(code, "javascript", "after_all")

    def test_mocha_with_context(self):
        """Mocha test with describe/context blocks"""
        code = """
const assert = require('assert');

describe('Array', () => {
    let array;
    
    beforeEach(() => {
        array = [1, 2, 3];
    });
    
    describe('methods', () => {
        let length;
        
        beforeEach(function() {
            length = array.length;
        });
        
        it('should have correct length', () => {
            assert.equal(length, 3);
        });
    });
});
"""
        # Should detect nested beforeEach fixtures
        assert_fixture_count(code, "javascript", 2)


class TestRealWorldTypeScriptFixtures:
    """Integration tests using realistic TypeScript test code"""

    def test_jest_with_type_annotations(self):
        """Jest TypeScript with proper type annotations"""
        code = """
import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { Database } from './database';

describe('UserRepository', () => {
    let db: Database;
    let repository: UserRepository;
    
    beforeEach(async () => {
        db = new Database();
        await db.connect();
        repository = new UserRepository(db);
    });
    
    afterEach(async () => {
        await db.disconnect();
    });
    
    describe('when user exists', () => {
        let userId: string;
        
        beforeEach(async () => {
            const user = await repository.create({
                username: 'test',
                email: 'test@example.com'
            });
            userId = user.id;
        });
        
        it('should return user', async () => {
            const user = await repository.findById(userId);
            expect(user).toBeDefined();
        });
    });
});
"""
        assert_fixture_with_type_detected(code, "typescript", "before_each", count=2)
        assert_fixture_with_type_detected(code, "typescript", "after_each")


class TestRealWorldGoFixtures:
    """Integration tests using realistic Go test code"""

    def test_go_table_driven_tests(self):
        """Go table-driven test pattern"""
        code = """
package user_test

import (
    "testing"
    "github.com/golang/mock/gomock"
)

func TestUserService(t *testing.T) {
    ctrl := gomock.NewController(t)
    defer ctrl.Finish()
    
    mockRepo := NewMockRepository(ctrl)
    mockRepo.EXPECT().GetUser(1).Return(&User{ID: 1}, nil)
    
    service := NewUserService(mockRepo)
    
    tests := []struct {
        name string
        id   int
        want *User
    }{
        {"valid id", 1, &User{ID: 1}},
        {"invalid id", 0, nil},
    }
    
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            user, err := service.GetUser(tt.id)
        })
    }
}

func setupTestDB(t *testing.T) *Database {
    db := NewDatabase()
    t.Cleanup(func() { db.Close() })
    return db
}
"""
        # Go doesn't have traditional fixtures, but verify no crashes
        fixtures = extract_and_find_fixtures(code, "go")
        assert isinstance(fixtures, list)


class TestMultiLanguageConsistency:
    """Validate consistent detection across multiple languages in one test"""

    def test_equivalent_fixtures_all_languages(self):
        """Same fixture pattern should be detected across all languages"""

        # Per-test setup pattern in each language
        examples = {
            "python": """
class Test(unittest.TestCase):
    def setUp(self):
        self.resource = create_resource()
""",
            "java": """
public class Test {
    @Before
    public void setUp() {
        resource = createResource();
    }
}
""",
            "javascript": """
describe('Test', () => {
    let resource;
    
    beforeEach(() => {
        resource = createResource();
    });
});
""",
        }

        for language, code in examples.items():
            fixtures = extract_and_find_fixtures(code, language)
            assert len(fixtures) > 0, f"No fixtures detected in {language}"
            assert (
                fixtures[0].scope == "per_test"
            ), f"Wrong scope for {language}: {fixtures[0].scope}"


class TestLargeComplexTestFiles:
    """Integration tests on larger, more complex test files"""

    def test_large_python_test_module(self):
        """Integration test on 200+ line fixture-heavy Python module"""
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


class TestFixtureDependencies:
    """Test extraction of fixtures with dependencies"""

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
