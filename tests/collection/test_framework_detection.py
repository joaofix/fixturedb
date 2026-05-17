"""
Unit tests for framework detection across all supported languages.

Tests verify that fixtures are correctly identified with their respective
testing frameworks (pytest, unittest, junit, nunit, mstest, xunit, testify,
golang_testing, ava, etc.).
"""

import pytest
from .conftest import extract_and_find_fixtures, assert_fixture_detected


class TestPythonFrameworkDetection:
    """Test Python framework detection (pytest and unittest)"""

    def test_pytest_decorator_framework(self):
        """Pytest fixtures with @pytest.fixture decorator should have framework='pytest'"""
        code = """
import pytest

@pytest.fixture
def db_connection():
    conn = create_connection()
    yield conn
    conn.close()

@pytest.fixture(scope='session')
def config():
    return load_config()
"""
        # Check first fixture
        fixtures = extract_and_find_fixtures(code, "python", "db_connection")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "pytest"

        # Check second fixture
        fixtures = extract_and_find_fixtures(code, "python", "config")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "pytest"

    def test_unittest_setUp_framework(self):
        """unittest setUp/tearDown should have framework='unittest'"""
        code = """
import unittest

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = Database(':memory:')
    
    def tearDown(self):
        self.db.close()
    
    def test_query(self):
        result = self.db.query('SELECT 1')
        self.assertEqual(result, [1])
"""
        # Check setUp
        fixtures = extract_and_find_fixtures(code, "python", "setUp")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "unittest"

        # Check tearDown
        fixtures = extract_and_find_fixtures(code, "python", "tearDown")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "unittest"

    def test_unittest_classmethod_fixtures(self):
        """unittest setUpClass/tearDownClass should have framework='unittest'"""
        code = """
import unittest

class TestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = setup_resources()
    
    @classmethod
    def tearDownClass(cls):
        cleanup_resources(cls.resources)
"""
        # Check setUpClass
        fixtures = extract_and_find_fixtures(code, "python", "setUpClass")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "unittest"

        # Check tearDownClass
        fixtures = extract_and_find_fixtures(code, "python", "tearDownClass")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "unittest"


class TestJavaFrameworkDetection:
    """Test Java framework detection (JUnit)"""

    def test_junit_before_after_annotations(self):
        """JUnit @Before/@After annotations should have framework='junit'"""
        code = """
import org.junit.Before;
import org.junit.After;

public class TestCalculator {
    private Calculator calc;
    
    @Before
    public void setUp() {
        calc = new Calculator();
    }
    
    @After
    public void tearDown() {
        calc = null;
    }
    
    @Test
    public void testAdd() {
        assertEquals(4, calc.add(2, 2));
    }
}
"""
        # Check @Before
        fixtures = extract_and_find_fixtures(code, "java", "setUp")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "junit"

        # Check @After
        fixtures = extract_and_find_fixtures(code, "java", "tearDown")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "junit"

    def test_junit_class_annotations(self):
        """JUnit @BeforeClass/@AfterClass should have framework='junit'"""
        code = """
import org.junit.BeforeClass;
import org.junit.AfterClass;

public class ExpensiveResourceTest {
    private static ExpensiveResource resource;
    
    @BeforeClass
    public static void setUpClass() {
        resource = new ExpensiveResource();
    }
    
    @AfterClass
    public static void tearDownClass() {
        resource.cleanup();
    }
}
"""
        # Check @BeforeClass
        fixtures = extract_and_find_fixtures(code, "java", "setUpClass")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "junit"

        # Check @AfterClass
        fixtures = extract_and_find_fixtures(code, "java", "tearDownClass")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "junit"

    def test_junit_rule_annotations(self):
        """JUnit @Rule/@ClassRule should have framework='junit'"""
        code = """
import org.junit.Rule;
import org.junit.ClassRule;

public class TemporaryFolderTest {
    @Rule
    public TemporaryFolder temporaryFolder = new TemporaryFolder();
    
    @ClassRule
    public static ExternalResource database = new ExternalResource();
}
"""
        # @Rule/@ClassRule fields are detected as anonymous fixtures with specific types
        all_fixtures = extract_and_find_fixtures(code, "java")

        # Check for junit_rule type
        rule_fixtures = [f for f in all_fixtures if f.fixture_type == "junit_rule"]
        assert len(rule_fixtures) > 0, "@Rule fixture should be detected"
        assert rule_fixtures[0].framework == "junit"

        # Check for junit_class_rule type
        class_rule_fixtures = [
            f for f in all_fixtures if f.fixture_type == "junit_class_rule"
        ]
        assert len(class_rule_fixtures) > 0, "@ClassRule fixture should be detected"
        assert class_rule_fixtures[0].framework == "junit"


class TestGoFrameworkDetection:
    """Test Go framework detection (golang_testing and testify)"""

    def test_golang_testing_testmain(self):
        """Go TestMain() should have framework='golang_testing'"""
        code = """
package mypackage

import (
    "testing"
)

func TestMain(m *testing.M) int {
    setup()
    code := m.Run()
    teardown()
    return code
}

func TestSomething(t *testing.T) {
    t.Log("test")
}
"""
        # Check TestMain
        fixtures = extract_and_find_fixtures(code, "go", "TestMain")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "golang_testing"

    def test_testify_suite_methods(self):
        """testify SetupSuite/SetupTest should have framework='testify'"""
        code = """
package models

import (
    "testing"
    "github.com/stretchr/testify/suite"
)

type DatabaseTestSuite struct {
    suite.Suite
    db *Database
}

func (suite *DatabaseTestSuite) SetupSuite() {
    suite.db = setupDatabase()
}

func (suite *DatabaseTestSuite) TeardownSuite() {
    suite.db.Close()
}

func (suite *DatabaseTestSuite) SetupTest() {
    suite.db.ClearData()
}

func (suite *DatabaseTestSuite) TeardownTest() {
    // cleanup
}

func (suite *DatabaseTestSuite) TestQuery() {
    result := suite.db.Query("SELECT 1")
    suite.Equal(1, result)
}

func TestDatabaseTestSuite(t *testing.T) {
    suite.Run(t, new(DatabaseTestSuite))
}
"""
        # Check SetupSuite
        fixtures = extract_and_find_fixtures(code, "go", "SetupSuite")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "testify"

        # Check SetupTest
        fixtures = extract_and_find_fixtures(code, "go", "SetupTest")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "testify"

        # Check TeardownSuite
        fixtures = extract_and_find_fixtures(code, "go", "TeardownSuite")
        assert len(fixtures) > 0
        assert fixtures[0].framework == "testify"


class TestJavaScriptTypeScriptFrameworkDetection:
    """Test JavaScript/TypeScript framework detection (AVA, Jest/Mocha ambiguous)"""

    def test_ava_before_after_framework(self):
        """AVA test.before/test.after should have framework='ava'"""
        code = """
import test from 'ava';

test.before(t => {
  t.context.db = setupDatabase();
});

test.after(t => {
  t.context.db.close();
});

test.serial.before(t => {
  t.context.lock = acquireLock();
});

test('query test', t => {
  t.assert.is(t.context.db.query('SELECT 1'), 1);
});
"""
        # All AVA fixtures should have framework='ava'
        all_fixtures = extract_and_find_fixtures(code, "typescript")
        ava_fixtures = [f for f in all_fixtures if "ava" in f.fixture_type.lower()]

        assert len(ava_fixtures) > 0, "AVA fixtures should be detected"
        for fixture in ava_fixtures:
            assert (
                fixture.framework == "ava"
            ), f"AVA fixture {fixture.name} should have framework='ava', got {fixture.framework}"

    def test_jest_mocha_ambiguous_framework(self):
        """Jest/Mocha beforeEach should have framework=None (ambiguous)"""
        code = """
describe('Database', () => {
    let db;
    
    beforeEach(() => {
        db = new Database(':memory:');
    });
    
    afterEach(() => {
        db.close();
    });
    
    it('should query data', () => {
        expect(db.query('SELECT 1')).toBe(1);
    });
});
"""
        # Jest/Mocha fixtures should have framework=None (ambiguous)
        all_fixtures = extract_and_find_fixtures(code, "javascript")
        hook_fixtures = [
            f for f in all_fixtures if f.fixture_type in ["before_each", "after_each"]
        ]

        assert len(hook_fixtures) > 0, "beforeEach/afterEach hooks should be detected"
        for fixture in hook_fixtures:
            assert (
                fixture.framework is None
            ), f"Jest/Mocha hook {fixture.name} should have framework=None (ambiguous), got {fixture.framework}"

    def test_ava_javascript(self):
        """AVA in JavaScript should also have framework='ava'"""
        code = """
import test from 'ava';

test.before(t => {
  t.context.setup = true;
});

test('main', t => {
  t.assert(t.context.setup);
});
"""
        all_fixtures = extract_and_find_fixtures(code, "javascript")
        ava_fixtures = [f for f in all_fixtures if f.framework == "ava"]

        assert len(ava_fixtures) > 0, "AVA fixtures should be detected in JavaScript"


class TestFrameworkDetectionConsistency:
    """Cross-language consistency tests for framework detection"""

    def test_framework_field_always_string_or_none(self):
        """Framework field should always be string or None, never empty string"""
        # Test across multiple languages
        test_cases = [
            (
                "python",
                """
@pytest.fixture
def fix():
    pass
""",
            ),
            (
                "java",
                """
import org.junit.Before;
public class T {
    @Before public void f() {}
}
""",
            ),
            (
                "javascript",
                """
describe('s', () => {
    beforeEach(() => {});
});
""",
            ),
            (
                "typescript",
                """
import test from 'ava';
test.before(t => {});
""",
            ),
        ]

        for language, code in test_cases:
            fixtures = extract_and_find_fixtures(code, language)
            for fixture in fixtures:
                assert fixture.framework is None or isinstance(
                    fixture.framework, str
                ), f"Framework must be None or str, got {type(fixture.framework)} for {language}"
                assert (
                    fixture.framework != ""
                ), f"Framework should be None, not empty string for {language}"

    def test_framework_detection_doesnt_affect_other_fields(self):
        """Framework detection should not affect other fixture properties"""
        code = """
import pytest

@pytest.fixture
def setup():
    return [1, 2, 3]

def test_use(setup):
    assert len(setup) == 3
"""
        fixtures = extract_and_find_fixtures(code, "python", "setup")
        assert len(fixtures) > 0

        fixture = fixtures[0]
        # Verify other fields are still present
        assert hasattr(fixture, "name")
        assert hasattr(fixture, "fixture_type")
        assert hasattr(fixture, "loc")
        assert hasattr(fixture, "start_line")
        assert hasattr(fixture, "end_line")
        # And framework is now also present
        assert hasattr(fixture, "framework")
        assert fixture.framework == "pytest"
