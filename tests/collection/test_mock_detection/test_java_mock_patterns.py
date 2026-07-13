"""
Mock detection tests for Java fixtures.

Validates that the extractor correctly identifies mock usage patterns in
Java test fixtures -- these assert on `fixture.mocks` directly, not just
that the surrounding fixture was extracted, since a fixture can be
detected correctly while its mock usage inside is silently missed (as
Mockito.spy(...) was until this file's tests were tightened -- there was
no pattern for it at all, meaning Java had zero "spy" category coverage).
"""

import pytest

from ..conftest import (
    assert_fixture_detected,
)


class TestJavaMockitoPatterns:
    """Mockito mock patterns"""

    def test_mockito_mock_static_call(self):
        """Mockito.mock(X.class) inside the fixture body should be
        detected, category "mock"."""
        code = """
public class UserServiceTest {
    @Before
    public void setUp() {
        UserRepository repository = Mockito.mock(UserRepository.class);
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "mockito"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "UserRepository"

    def test_mockito_mock_annotation_outside_fixture_body_is_invisible(self):
        """@Mock on a class field is NOT detected as a mock on the setUp()
        fixture below it -- a Java-specific instance of the same
        fixture-scoped structural limitation documented for Jest's
        module-level jest.mock() (see mock_patterns_excluded): mock
        detection only scans the fixture's own AST node text, and a field
        declaration is outside the method body."""
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
        assert fixture.mocks == []

    def test_mockito_mock_annotation_inside_fixture_body_is_detected(self):
        """The same @Mock annotation IS detected when the field/annotation
        happens to be textually inside the scanned fixture node -- confirms
        the miss above is about AST scope, not the pattern itself."""
        code = """
public class UserServiceTest {
    @Before
    public void setUp() {
        @Mock UserRepository repository;
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "mockito"
        assert fixture.mocks[0].category == "mock"

    def test_mockito_spy_pattern(self):
        """Mockito.spy(realObject) should be detected as category "spy" --
        previously not covered by any pattern at all, meaning Java had zero
        spy-category coverage despite spy being a distinct, common Mockito
        API from mock()."""
        code = """
public class Test extends TestCase {
    @Before
    public void setUp() {
        UserService real = new UserService();
        UserService spy = Mockito.spy(real);
        Mockito.doReturn(100).when(spy).calculate(1);
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        # Only counts 'new' constructor calls, not method calls like Mockito.spy()
        assert fixture.num_objects_instantiated == 1
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "mockito"
        assert fixture.mocks[0].category == "spy"
        assert fixture.mocks[0].target_identifier == "real"


class TestJavaEasyMockPatterns:
    """EasyMock mock patterns"""

    def test_easymock_create_mock(self):
        """EasyMock.createMock(X.class) should be detected, category
        "mock"."""
        code = """
public class ServiceTest {
    @Before
    public void setUp() {
        UserRepository repository = EasyMock.createMock(UserRepository.class);
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "easymock"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "UserRepository"


class TestJavaStaticImportMockitoPatterns:
    """Static-import Mockito usage (`import static
    org.mockito.Mockito.mock;` then a bare `mock(X.class)` call) -- not
    Kotlin's MockK, which was this pattern's label until a real toy
    Dataset A run showed every hit was Java code (MockK's class-literal
    syntax is `X::class`, never the Java-only `X.class` this pattern
    requires)."""

    def test_static_import_mock_call(self):
        """Bare mock(X.class) (static-import Mockito) should be detected,
        category "mock"."""
        code = """
public class ServiceTest {
    @Before
    public void setUp() {
        UserRepository repository = mock(UserRepository.class);
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "mockito"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "UserRepository"


class TestJavaPowerMockPatterns:
    """PowerMock patterns -- a documented exclusion, not detected."""

    def test_powermock_setup(self):
        """PowerMock setup in test fixture: the fixture itself is still
        correctly detected, but PowerMock is a documented exclusion (see
        feature_extraction_patterns.yaml's mock_patterns_excluded) -- no
        mock is recorded for it."""
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
        assert fixture.mocks == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
