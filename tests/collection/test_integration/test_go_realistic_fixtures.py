"""
Integration tests for Go fixture extraction on realistic code.

Tests extraction on actual test files with table-driven patterns,
setup functions, and real-world code from popular Go testing patterns.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_count,
)


class TestGoTableDrivenPatterns:
    """Integration tests using Go table-driven patterns"""

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
