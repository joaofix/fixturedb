"""
Integration tests for Java fixture extraction on realistic code.

Tests extraction on actual test files with multiple fixtures,
complex hierarchies, and real-world patterns from popular Java frameworks.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_count,
)


class TestJavaJUnit5Hierarchy:
    """Integration tests using JUnit 5 patterns"""

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


class TestJavaTestNGHierarchy:
    """Integration tests using TestNG patterns"""

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
