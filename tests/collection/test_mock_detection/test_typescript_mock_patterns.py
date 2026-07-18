"""
Mock detection tests for TypeScript fixtures.

Validates that the extractor correctly identifies mock usage patterns
in TypeScript test fixtures.
"""

import pytest

from ..conftest import (
    assert_fixture_with_type_detected,
)


class TestTypeScriptMockitoPatterns:
    """ts-mockito patterns"""

    def test_ts_mockito_setup(self):
        """ts-mockito setup in beforeEach"""
        code = """
import { mock, instance, when } from 'ts-mockito';

let mockRepository: UserRepository;

beforeEach(() => {
    mockRepository = mock(UserRepository);
    when(mockRepository.getUser(1)).thenReturn({id: 1});
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.fixture_type == "before_each"


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


class TestTypeScriptVitestPatterns:
    """Vitest mock patterns (previously had no dedicated test coverage)"""

    def test_vi_fn(self):
        """vi.fn() -- "fn" itself contains no category keyword, but the
        trailing "callback.mockReturnValue(42)" falls inside the scanned
        snippet's after-window, so category resolves to "mock" from
        there."""
        code = """
beforeEach(() => {
    const callback = vi.fn();
    callback.mockReturnValue(42);
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.mocks
        assert fixture.mocks[0].framework == "vitest"
        assert fixture.mocks[0].category == "mock"

    def test_vi_mock(self):
        """vi.mock('./module') -- category "mock" is a substring of
        "vi.mock(" itself."""
        code = """
beforeEach(() => {
    vi.mock('./service');
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.mocks
        assert fixture.mocks[0].framework == "vitest"
        assert fixture.mocks[0].category == "mock"
        assert fixture.mocks[0].target_identifier == "./service"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
