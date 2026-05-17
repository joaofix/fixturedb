"""
Tests for mock detection and mock-related fixture patterns.

Validates that the extractor correctly identifies mock usage patterns
and distinguishes between fixtures and mock setup code.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
)


class TestPythonMockPatterns:
    """Validate detection of Python mock patterns"""

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
        # Should detect num_objects_instantiated > 0
        assert fixture.num_objects_instantiated >= 1

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
        # Has parameters (mocker)
        assert fixture.num_parameters >= 1

    def test_mock_as_decorator(self):
        """@patch decorator on test method (not a fixture)"""
        code = """
@patch('module.function')
def test_something(self, mock_func):
    mock_func.return_value = 42
    assert test_function() == 42
"""
        # test_something is a test method, not a fixture
        assert_fixture_not_detected(code, "python", "test_something")

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

    def test_mock_spec_fixture(self):
        """Fixture using Mock with spec parameter"""
        code = """
@pytest.fixture
def db_mock():
    from unittest.mock import Mock
    return Mock(spec=Database)
"""
        fixture = assert_fixture_detected(code, "python", "db_mock")
        assert fixture.num_objects_instantiated >= 1  # Mock() creates an object


class TestJavaMockPatterns:
    """Validate detection of Java mock patterns"""

    def test_mockito_mock_in_setup(self):
        """Mockito mock setup in @Before fixture"""
        code = """
import org.mockito.*;

public class UserServiceTest {
    @Mock
    private UserRepository repository;
    
    @Before
    public void setUp() {
        MockitoAnnotations.initMocks(this);
        Mockito.when(repository.findUser(1)).thenReturn(new User(1, "John"));
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert fixture.fixture_type == "junit4_before"

    def test_powermock_setup(self):
        """PowerMock setup in test fixture"""
        code = """
@RunWith(PowerMockRunner.class)
@PrepareForTest(StaticUtility.class)
public class TestClass {
    @Before
    public void setUp() {
        PowerMock.mockStatic(StaticUtility.class);
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert fixture.name == "setUp"

    def test_spy_pattern(self):
        """Spy/partial mock pattern in setUp"""
        code = """
public class Test extends TestCase {
    @Before
    public void setUp() {
        UserService real = new UserService();
        UserService spy = Mockito.spy(real);
        Mockito.doReturn(100).when(spy).calculate(anyInt());
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        # Only counts 'new' constructor calls, not method calls like Mockito.spy()
        assert fixture.num_objects_instantiated == 1


class TestJavaScriptMockPatterns:
    """Validate detection of JavaScript mock patterns"""

    def test_jest_mock_function(self):
        """Jest jest.fn() mock in beforeEach"""
        code = """
describe('Module', () => {
    let mockCallback;
    
    beforeEach(() => {
        mockCallback = jest.fn();
        mockCallback.mockReturnValue(42);
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.fixture_type == "before_each"

    def test_sinon_stub_setup(self):
        """Sinon stub/spy setup in beforeEach"""
        code = """
const sinon = require('sinon');

describe('Test', function() {
    let stub;
    
    beforeEach(function() {
        stub = sinon.stub(obj, 'method').returns(42);
    });
    
    afterEach(function() {
        stub.restore();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.fixture_type == "before_each"

    def test_jest_mock_module(self):
        """jest.mock() for module mocking"""
        code = """
jest.mock('./api');
const api = require('./api');

beforeEach(() => {
    api.fetch.mockResolvedValue({data: []});
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.fixture_type == "before_each"


class TestTypeScriptMockPatterns:
    """Validate detection of TypeScript mock patterns"""

    def test_ts_mockito_setup(self):
        """ts-mockito setup in @Before"""
        code = """
import { mock, instance, when } from 'ts-mockito';

export class TestClass {
    private mockRepository: UserRepository;
    
    @Before
    public setUp(): void {
        this.mockRepository = mock(UserRepository);
        when(this.mockRepository.getUser(1)).thenReturn({id: 1});
    }
}
"""
        fixture = assert_fixture_detected(code, "typescript", "setUp")
        assert fixture.name == "setUp"

    def test_jest_mock_with_types(self):
        """Jest mock with TypeScript type annotations"""
        code = """
jest.mock('./service');
import { UserService } from './service';

const mockService = UserService as jest.MockedClass<typeof UserService>;

beforeEach(() => {
    mockService.prototype.getUser.mockResolvedValue({id: 1, name: 'John'});
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.fixture_type == "before_each"


class TestGoMockPatterns:
    """Validate detection of Go mock patterns"""

    def test_gomock_interface_setup(self):
        """GoMock interface mock in setup function"""
        code = """
import "github.com/golang/mock/gomock"

func TestExample(t *testing.T) {
    ctrl := gomock.NewController(t)
    defer ctrl.Finish()
    
    mockDB := NewMockDatabase(ctrl)
    mockDB.EXPECT().Query("SELECT *").Return(rows, nil)
}
"""
        # Go uses factory pattern, not fixtures like other languages
        # Just verify no crashes
        fixtures = extract_and_find_fixtures(code, "go")
        assert isinstance(fixtures, list)

    def test_mock_assignment(self):
        """Simple mock object assignment in test"""
        code = """
func setupTest() *MockService {
    return &MockService{
        GetUserFunc: func(id int) (*User, error) {
            return &User{ID: id}, nil
        },
    }
}
"""
        # Go helper functions might be detected as fixtures
        fixtures = extract_and_find_fixtures(code, "go")
        assert isinstance(fixtures, list)


class TestMockDetectionAccuracy:
    """Validate false positive/negative rates in mock detection"""

    def test_mock_in_test_body_not_fixture(self):
        """Mock created in test body should not be detected as fixture"""
        code = """
def test_something(self):
    mock = Mock()
    mock.return_value = 42
    assert function(mock) == 42
"""
        fixtures = extract_and_find_fixtures(code, "python")
        # test_something is a test method, not a fixture
        assert not any(f.name == "test_something" for f in fixtures)

    def test_mock_factory_function_detected(self):
        """Helper function creating mocks might be detected as fixture"""
        code = """
@pytest.fixture
def mock_user_factory():
    def create_mock(name='test'):
        return Mock(spec=User, name=name)
    return create_mock
"""
        fixture = assert_fixture_detected(code, "python", "mock_user_factory")
        assert fixture.fixture_type == "pytest_decorator"

    def test_mock_config_as_fixture(self):
        """Config/setup object should be detected if it's a fixture"""
        code = """
@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.get_value.return_value = 'test_value'
    cfg.timeout = 30
    return cfg
"""
        fixture = assert_fixture_detected(code, "python", "mock_config")
        assert fixture.num_objects_instantiated >= 1


class TestMockFrameworkDetection:
    """Validate detection of mock framework types"""

    def test_unittest_mock_imports(self):
        """Code using unittest.mock should be distinguishable"""
        code = """
from unittest.mock import Mock, patch, MagicMock

def setUp(self):
    self.mock = Mock()
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Fixture uses Mock objects
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

    def test_multiple_mock_frameworks(self):
        """Code mixing mock frameworks should be handled"""
        code = """
from unittest.mock import Mock
from pytest_mock import MockerFixture

@pytest.fixture
def hybrid_mock(mocker: MockerFixture):
    m1 = Mock()
    m2 = mocker.Mock()
    return (m1, m2)
"""
        fixture = assert_fixture_detected(code, "python", "hybrid_mock")
        assert fixture.num_parameters >= 1
        assert fixture.num_objects_instantiated >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
