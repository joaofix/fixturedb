"""
Integration tests for TypeScript fixture extraction on realistic code.

Tests extraction on actual test files with multiple fixtures,
complex patterns, and real-world code from popular TypeScript frameworks.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
)


class TestTypeScriptJestFixtures:
    """Integration tests using Jest with TypeScript"""

    def test_jest_with_type_annotations(self):
        """Jest TypeScript with proper type annotations"""
        code = """
import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { Database } from './database';

describe('UserRepository', () => {
    let db: Database;
    let repository: UserRepository;
    
    beforeEach(async () => {
        db = new Database();
        await db.connect();
        repository = new UserRepository(db);
    });
    
    afterEach(async () => {
        await db.disconnect();
    });
    
    describe('when user exists', () => {
        let userId: string;
        
        beforeEach(async () => {
            const user = await repository.create({
                username: 'test',
                email: 'test@example.com'
            });
            userId = user.id;
        });
        
        it('should return user', async () => {
            const user = await repository.findById(userId);
            expect(user).toBeDefined();
        });
    });
});
"""
        assert_fixture_with_type_detected(code, "typescript", "before_each", count=2)
        assert_fixture_with_type_detected(code, "typescript", "after_each")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
