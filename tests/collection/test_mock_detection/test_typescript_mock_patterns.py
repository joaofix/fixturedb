"""
Mock detection tests for TypeScript fixtures.

Validates that the extractor correctly identifies mock usage patterns
in TypeScript test fixtures.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
)


class TestTypeScriptMockitoPatterns:
    """ts-mockito patterns"""

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


class TestTypeScriptJestMockPatterns:
    """Jest mock patterns with TypeScript"""

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
