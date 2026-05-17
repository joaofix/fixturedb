"""
Mock detection tests for Java fixtures.

Validates that the extractor correctly identifies mock usage patterns
in Java test fixtures.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
)


class TestJavaMockitoPatterns:
    """Mockito mock patterns"""

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


class TestJavaPowerMockPatterns:
    """PowerMock patterns"""

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
