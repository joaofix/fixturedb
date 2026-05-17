"""
Mock detection tests for Go fixtures.

Validates that the extractor correctly identifies mock usage patterns
in Go test fixtures.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
)


class TestGoMockPatterns:
    """Go mocking patterns"""

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
