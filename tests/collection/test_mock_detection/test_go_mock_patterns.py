"""
Mock detection tests for Go fixtures.

Validates that the extractor correctly identifies mock usage patterns
in Go test fixtures.

Go isn't wired into DETECTORS (see collection/detector.py's module
docstring), so extract_fixtures(code, "go") never returns fixtures for any
mocks to attach to -- the gomock/testify_mock patterns in
feature_extraction_patterns.yaml exist only for parity in case Go
detection is ever enabled. Those patterns are still verified at the regex
level (proven to match real Go mock syntax, not dead/broken data) in
test_mock_pattern_catalog_coverage.py, which is why this file's tests only
assert "no crash" rather than mock detection.
"""

import pytest

from ..conftest import (
    extract_and_find_fixtures,
)

pytestmark = pytest.mark.skip(reason="Go is not supported")


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
