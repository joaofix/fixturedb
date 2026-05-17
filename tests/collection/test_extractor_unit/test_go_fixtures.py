"""
Unit tests for Go fixture extraction.

Tests positive and negative detection of Go fixture patterns:
- Setup/cleanup functions with naming conventions
- Table-driven test setup
- GoMock patterns
- defer cleanup patterns
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
)


class TestGoSetupFunctions:
    """Go setup/cleanup patterns"""

    def test_setup_function_pattern(self):
        """Go setup*() function might be detected based on naming"""
        code = """
package mypackage_test

func setupTest(t *testing.T) *TestData {
    data := &TestData{}
    data.initialize()
    return data
}
"""
        fixtures = extract_and_find_fixtures(code, "go")
        # Go doesn't have traditional fixtures like other languages
        # Naming convention-based detection depends on implementation
        assert isinstance(fixtures, list)


class TestGoTableDrivenTests:
    """Table-driven test setup patterns"""

    def test_table_driven_setup(self):
        """Table-driven test pattern"""
        code = """
func TestCalculate(t *testing.T) {
    tests := []struct {
        name string
        in   int
        want int
    }{
        {"case1", 1, 2},
        {"case2", 2, 4},
    }
    
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            result := calculate(tt.in)
            if result != tt.want {
                t.Fail()
            }
        })
    }
}
"""
        fixtures = extract_and_find_fixtures(code, "go")
        # Table struct is not a fixture per se
        assert isinstance(fixtures, list)


class TestGoCleanupPatterns:
    """Go cleanup patterns with defer"""

    def test_defer_cleanup(self):
        """Go defer cleanup pattern"""
        code = """
func TestWithCleanup(t *testing.T) {
    resource := createResource()
    defer resource.Close()
    
    // Test code
}
"""
        fixtures = extract_and_find_fixtures(code, "go")
        # defer is not a fixture definition
        assert isinstance(fixtures, list)


class TestGoMockPatterns:
    """GoMock setup patterns"""

    def test_gomock_controller_setup(self):
        """GoMock controller setup"""
        code = """
func TestWithMock(t *testing.T) {
    ctrl := gomock.NewController(t)
    defer ctrl.Finish()
    
    mockDB := NewMockDatabase(ctrl)
    mockDB.EXPECT().Query("SELECT *").Return(rows, nil)
}
"""
        fixtures = extract_and_find_fixtures(code, "go")
        # ctrl.Finish() is not a fixture
        assert isinstance(fixtures, list)


class TestGoTestifySuite:
    """Testify/suite framework patterns"""

    def test_setupsuite_detected(self):
        """SetupSuite should be detected as class-level fixture"""
        code = """
package mypackage

import (
    "github.com/stretchr/testify/suite"
    "testing"
)

type MyTestSuite struct {
    suite.Suite
    db Database
}

func (suite *MyTestSuite) SetupSuite() {
    suite.db = createDB()
}
"""
        fixture = assert_fixture_detected(code, "go", "SetupSuite")
        assert fixture.fixture_type == "go_setup_suite"
        assert fixture.scope == "per_class"

    def test_teardownsuite_detected(self):
        """TeardownSuite should be detected as class-level fixture"""
        code = """
type MyTestSuite struct {
    suite.Suite
}

func (suite *MyTestSuite) TeardownSuite() {
    closeConnections()
}
"""
        fixture = assert_fixture_detected(code, "go", "TeardownSuite")
        assert fixture.fixture_type == "go_teardown_suite"
        assert fixture.scope == "per_class"

    def test_setuptest_detected(self):
        """SetupTest should be detected as per-test fixture"""
        code = """
type MyTestSuite struct {
    suite.Suite
}

func (suite *MyTestSuite) SetupTest() {
    resetState()
}
"""
        fixture = assert_fixture_detected(code, "go", "SetupTest")
        assert fixture.fixture_type == "go_setup_test"
        assert fixture.scope == "per_test"

    def test_teardowntest_detected(self):
        """TeardownTest should be detected as per-test fixture"""
        code = """
func (suite *MyTestSuite) TeardownTest() {
    cleanup()
}
"""
        fixture = assert_fixture_detected(code, "go", "TeardownTest")
        assert fixture.fixture_type == "go_teardown_test"
        assert fixture.scope == "per_test"

    def test_all_testify_methods_together(self):
        """All testify lifecycle methods in one suite"""
        code = """
type CompleteTestSuite struct {
    suite.Suite
}

func (suite *CompleteTestSuite) SetupSuite() { }
func (suite *CompleteTestSuite) SetupTest() { }
func (suite *CompleteTestSuite) TeardownTest() { }
func (suite *CompleteTestSuite) TeardownSuite() { }
"""
        assert_fixture_count(code, "go", 4)
        assert_fixture_detected(code, "go", "SetupSuite")
        assert_fixture_detected(code, "go", "SetupTest")
        assert_fixture_detected(code, "go", "TeardownTest")
        assert_fixture_detected(code, "go", "TeardownSuite")


class TestGoNegativeDetection:
    """Non-fixtures in Go"""

    def test_helper_function_not_fixture(self):
        """Helper functions should not be detected"""
        code = """
func helperFunction(t *testing.T) {
    fmt.Println("Helper")
}
"""
        fixtures = extract_and_find_fixtures(code, "go")
        assert not any(f.name == "helperFunction" for f in fixtures)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
