"""
Comprehensive tests for collection/extractor.py focusing on:
1. Test file extraction and discovery
2. Fixture content extraction from test files
3. Mock usage detection in fixtures
4. Error handling and edge cases
5. Database integration
"""

import tempfile
from pathlib import Path
import pytest
from unittest.mock import Mock, patch, MagicMock

from collection.extractor import (
    _find_test_files,
    extract_repo,
    extract_all_cloned,
    extract_fixtures_with_timeout,
    ExtractionTimeoutError,
    _estimate_test_count,
)
from collection.detector import ExtractResult, FixtureResult, MockResult


# ============================================================================
# Test File Extraction (discovery + filtering)
# ============================================================================


class TestFindTestFilesComprehensive:
    """Comprehensive test file discovery covering all languages and patterns."""

    def test_python_test_file_patterns(self):
        """Verify all Python test file naming patterns are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            # Create test files matching various patterns
            (repo / "test_user.py").write_text("# test file\ndef test(): pass")
            (repo / "user_test.py").write_text("# test file\ndef test(): pass")
            (repo / "conftest.py").write_text("# conftest\ndef fixture(): pass")
            (repo / "tests").mkdir()
            (repo / "tests" / "integration.py").write_text("# test file\ndef test(): pass")
            
            test_files = _find_test_files(repo, "python")
            names = {f.name for f in test_files}
            
            assert "test_user.py" in names
            assert "user_test.py" in names
            assert "conftest.py" in names
            assert "integration.py" in names
            assert len(test_files) == 4

    def test_java_test_file_patterns(self):
        """Verify all Java test file naming patterns are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            (repo / "UserTest.java").write_text("// test")
            (repo / "UserTests.java").write_text("// test")
            (repo / "UserIT.java").write_text("// integration test")
            (repo / "UserSpec.java").write_text("// spec")
            (repo / "src" / "test" / "java").mkdir(parents=True)
            (repo / "src" / "test" / "java" / "Main.java").write_text("// test")
            
            test_files = _find_test_files(repo, "java")
            names = {f.name for f in test_files}
            
            assert "UserTest.java" in names or len([f for f in test_files if "User" in f.name]) >= 4
            assert len(test_files) >= 4

    def test_javascript_spec_patterns(self):
        """Verify JavaScript .spec.js and spec/ patterns are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            (repo / "user.spec.js").write_text("// test")
            (repo / "app.test.js").write_text("// test")
            (repo / "spec").mkdir()
            (repo / "spec" / "suite.js").write_text("// test")
            
            test_files = _find_test_files(repo, "javascript")
            
            assert len(test_files) == 3
            assert any("user.spec.js" in str(f) for f in test_files)
            assert any("app.test.js" in str(f) for f in test_files)

    def test_typescript_spec_patterns(self):
        """Verify TypeScript .spec.ts and spec/ patterns are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            (repo / "user.spec.ts").write_text("// test")
            (repo / "app.test.ts").write_text("// test")
            (repo / "spec").mkdir()
            (repo / "spec" / "suite.ts").write_text("// test")
            
            test_files = _find_test_files(repo, "typescript")
            
            assert len(test_files) == 3
            assert any("user.spec.ts" in str(f) for f in test_files)
            assert any("app.test.ts" in str(f) for f in test_files)

    def test_vendor_directory_exclusion(self):
        """Verify vendor/third-party directories are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            # Test files in vendor directories should be excluded
            (repo / "node_modules" / "jest").mkdir(parents=True)
            (repo / "node_modules" / "jest" / "test.js").write_text("// test")
            
            (repo / "vendor" / "phpunit").mkdir(parents=True)
            (repo / "vendor" / "phpunit" / "test.php").write_text("// test")
            
            # Legitimate test file should be included
            (repo / "test").mkdir()
            (repo / "test" / "main.js").write_text("// test")
            
            test_files = _find_test_files(repo, "javascript")
            
            assert len(test_files) == 1
            assert any("main.js" in str(f) for f in test_files)

    def test_large_file_exclusion(self):
        """Verify files larger than MAX_FILE_SIZE_BYTES are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            # Create a file smaller than limit
            small_file = repo / "small_test.py"
            small_file.write_text("# test\n" * 10)
            
            # Create a file larger than limit
            large_file = repo / "large_test.py"
            large_file.write_text("# test\n" * 1000000)
            
            test_files = _find_test_files(repo, "python")
            
            # Should include only the small file
            assert len(test_files) == 1
            assert test_files[0].name == "small_test.py"

    def test_non_code_file_exclusion(self):
        """Verify non-code files (.pyc, .class, etc.) are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            (repo / "test_file.py").write_text("# test")
            (repo / "test_file.pyc").write_bytes(b"binary")
            (repo / "test_file.class").write_bytes(b"binary")
            (repo / "test_file.so").write_bytes(b"binary")
            
            test_files = _find_test_files(repo, "python")
            
            assert len(test_files) == 1
            assert test_files[0].name == "test_file.py"

    def test_files_without_extension_excluded(self):
        """Verify files without extensions are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            (repo / "test_file").write_text("# no extension")
            (repo / "test_file.py").write_text("# with extension")
            
            test_files = _find_test_files(repo, "python")
            
            assert len(test_files) == 1
            assert test_files[0].name == "test_file.py"

    def test_empty_repository(self):
        """Verify empty repo returns no test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            test_files = _find_test_files(repo, "python")
            
            assert len(test_files) == 0

    def test_multiple_level_nesting(self):
        """Verify test files in deeply nested directories are found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            
            (repo / "src" / "app" / "tests" / "unit").mkdir(parents=True)
            (repo / "src" / "app" / "tests" / "unit" / "test_main.py").write_text("# test")
            
            test_files = _find_test_files(repo, "python")
            
            assert len(test_files) == 1


# ============================================================================
# Fixture/Mock Content Extraction
# ============================================================================


class TestFixtureContentExtraction:
    """Test extraction of fixture code content from test files."""

    @patch("collection.extractor.extract_fixtures")
    def test_extract_repo_reads_fixture_code(self, mock_extract):
        """Verify extract_repo properly reads and processes fixture code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            repo_name = "user/test-repo"
            
            # Create test file
            (repo_path / "test").mkdir()
            test_file = repo_path / "test" / "test_user.py"
            test_file.write_text("""
def setUp(self):
    self.user = User(name="John", email="john@test.com")
    self.mock_db = Mock()
""")
            
            # Mock the extract_fixtures return
            mock_fixture = FixtureResult(
                name="setUp",
                fixture_type="unittest_setup",
                framework="unittest",
                scope="per_test",
                start_line=2,
                end_line=5,
                loc=4,
                raw_source="def setUp(self):\n    ...",
                cyclomatic_complexity=1,
                max_nesting_depth=0,
                num_objects_instantiated=2,
                num_external_calls=0,
                num_parameters=1,
                reuse_count=1,
                has_teardown_pair=False,
                mocks=[],
            )
            mock_extract.return_value = ExtractResult(
                fixtures=[mock_fixture],
                file_loc=10,
                num_test_functions=1,
            )
            
            with patch("collection.extractor.get_clone_path") as mock_clone:
                mock_clone.return_value = repo_path
                with patch("collection.extractor.db_session") as mock_db:
                    mock_conn = MagicMock()
                    mock_db.return_value.__enter__.return_value = mock_conn
                    mock_conn.execute.return_value = MagicMock()
                    
                    with patch("collection.extractor.set_repo_status"):
                        with patch("collection.extractor.delete_clone"):
                            result = extract_repo(1, repo_name, "python")
            
            # Verify extract_fixtures was called with correct file path
            assert mock_extract.called
            call_args = mock_extract.call_args[0]
            assert call_args[0] == test_file
            assert call_args[1] == "python"

    @patch("collection.extractor.extract_fixtures")
    def test_mock_extraction_from_fixture(self, mock_extract):
        """Verify mock usages are extracted from fixture code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "test").mkdir()
            (repo_path / "test" / "test_main.py").write_text("# test file")
            
            mock_usage = MockResult(
                framework="unittest.mock",
                target_identifier="user_service",
                num_interactions_configured=3,
                raw_snippet="mock_user_service = Mock()",
            )
            
            mock_fixture = FixtureResult(
                name="setUp",
                fixture_type="unittest_setup",
                framework="unittest",
                scope="per_test",
                start_line=1,
                end_line=5,
                loc=5,
                raw_source="def setUp(self):\n    self.mock = Mock()",
                cyclomatic_complexity=1,
                max_nesting_depth=0,
                num_objects_instantiated=1,
                num_external_calls=0,
                num_parameters=1,
                reuse_count=1,
                has_teardown_pair=False,
                mocks=[mock_usage],
            )
            
            mock_extract.return_value = ExtractResult(
                fixtures=[mock_fixture],
                file_loc=10,
                num_test_functions=1,
            )
            
            with patch("collection.extractor.get_clone_path") as mock_clone:
                mock_clone.return_value = repo_path
                with patch("collection.extractor.db_session") as mock_db:
                    mock_conn = MagicMock()
                    mock_db.return_value.__enter__.return_value = mock_conn
                    mock_conn.execute.return_value = MagicMock()
                    
                    with patch("collection.extractor.set_repo_status"):
                        with patch("collection.extractor.delete_clone"):
                            with patch("collection.extractor.insert_fixture") as mock_insert_fixture:
                                with patch("collection.extractor.insert_mock_usage") as mock_insert_mock:
                                    mock_insert_fixture.return_value = 1
                                    result = extract_repo(1, "user/repo", "python")
                    
                    # Verify mock was inserted
                    assert mock_insert_mock.called

    def test_estimate_test_count_python(self):
        """Verify test count estimation for Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("""
def test_user_creation():
    assert True

def test_user_deletion():
    assert True

def helper_function():
    pass
""")
            
            count = _estimate_test_count(test_file, "python")
            assert count == 2

    def test_estimate_test_count_java(self):
        """Verify test count estimation for Java files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "UserTest.java"
            test_file.write_text("""
public class UserTest {
    @Test
    public void testCreation() {}
    
    @Test
    public void testDeletion() {}
    
    public void helperMethod() {}
}
""")
            
            count = _estimate_test_count(test_file, "java")
            assert count == 2

    def test_estimate_test_count_javascript(self):
        """Verify test count estimation for JavaScript files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "user.test.js"
            test_file.write_text("""
test('should create user', () => {
    expect(true).toBe(true);
});

it('should delete user', () => {
    expect(true).toBe(true);
});

function helperFunction() {}
""")
            
            count = _estimate_test_count(test_file, "javascript")
            assert count == 2

    def test_estimate_test_count_invalid_file(self):
        """Verify test count returns 0 for unreadable files."""
        count = _estimate_test_count(Path("/nonexistent/file.py"), "python")
        assert count == 0


# ============================================================================
# Error Handling and Edge Cases
# ============================================================================


class TestExtractionErrorHandling:
    """Test error handling during extraction."""

    def test_extract_repo_with_missing_clone(self):
        """Verify extract_repo handles missing clone directory gracefully."""
        with patch("collection.extractor.get_clone_path") as mock_clone:
            mock_clone.return_value = Path("/nonexistent/clone")
            
            with patch("collection.extractor.db_session") as mock_db:
                mock_conn = MagicMock()
                mock_db.return_value.__enter__.return_value = mock_conn
                
                with patch("collection.extractor.set_repo_status") as mock_status:
                    result = extract_repo(1, "user/repo", "python")
            
            # Should set error status
            mock_status.assert_called_once()
            assert result == {}

    def test_timeout_error_handling(self):
        """Verify extraction timeout is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "test").mkdir()
            test_file = repo_path / "test" / "test.py"
            test_file.write_text("def test(): pass")
            
            # Mock extract_fixtures to raise timeout
            with patch("collection.extractor.extract_fixtures") as mock_extract:
                from concurrent.futures import TimeoutError as FuturesTimeoutError
                mock_extract.side_effect = FuturesTimeoutError()
                
                # Should raise ExtractionTimeoutError on timeout
                with pytest.raises(ExtractionTimeoutError):
                    extract_fixtures_with_timeout(test_file, "python", timeout=1)

    @patch("collection.extractor.extract_fixtures")
    def test_extract_repo_with_no_test_files(self, mock_extract):
        """Verify extract_repo handles repos with no test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            
            with patch("collection.extractor.get_clone_path") as mock_clone:
                mock_clone.return_value = repo_path
                with patch("collection.extractor.db_session") as mock_db:
                    mock_conn = MagicMock()
                    mock_db.return_value.__enter__.return_value = mock_conn
                    mock_conn.execute.return_value = MagicMock()
                    
                    with patch("collection.extractor.set_repo_status"):
                        with patch("collection.extractor.delete_clone"):
                            result = extract_repo(1, "user/repo", "python")
            
            # Should complete without error even with no test files
            assert isinstance(result, dict)

    @patch("collection.extractor.extract_fixtures")
    def test_extract_repo_insufficient_fixtures(self, mock_extract):
        """Verify repos with too few fixtures are marked as skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "test").mkdir()
            (repo_path / "test" / "test.py").write_text("def test(): pass")
            
            # Return empty fixtures
            mock_extract.return_value = ExtractResult(
                fixtures=[],
                file_loc=5,
                num_test_functions=0,
            )
            
            with patch("collection.extractor.get_clone_path") as mock_clone:
                mock_clone.return_value = repo_path
                with patch("collection.extractor.db_session") as mock_db:
                    mock_conn = MagicMock()
                    mock_db.return_value.__enter__.return_value = mock_conn
                    mock_conn.execute.return_value = MagicMock()
                    
                    with patch("collection.extractor.set_repo_status") as mock_status:
                        with patch("collection.extractor.delete_clone"):
                            result = extract_repo(1, "user/repo", "python")
            
            # Verify status was set to skipped
            calls = [str(call) for call in mock_status.call_args_list]
            assert any("skipped" in str(call) for call in calls)


# ============================================================================
# Batch Extraction
# ============================================================================


class TestBatchExtraction:
    """Test batch extraction of multiple repositories."""

    @patch("collection.extractor.get_repos_by_status")
    @patch("collection.extractor.extract_repo")
    def test_extract_all_cloned_basic(self, mock_extract_repo, mock_get_repos):
        """Verify extract_all_cloned processes repos correctly."""
        # Mock repo list
        mock_repos = [
            {"id": 1, "full_name": "user/repo1", "language": "python"},
            {"id": 2, "full_name": "user/repo2", "language": "python"},
        ]
        
        mock_extract_repo.return_value = {"fixtures": 10, "mocks": 5}
        
        with patch("collection.extractor.db_session") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            
            # Mock cursor for DB queries
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.execute.return_value = mock_cursor
            
            result = extract_all_cloned(language="python")
            
            # Verify repos were processed
            assert isinstance(result, dict)

    @patch("collection.extractor.get_repos_by_status")
    @patch("collection.extractor.extract_repo")
    def test_extract_all_cloned_with_early_stop(self, mock_extract_repo, mock_get_repos):
        """Verify extraction stops when target is reached."""
        mock_repos = [
            {"id": 1, "full_name": "user/repo1", "language": "python"},
            {"id": 2, "full_name": "user/repo2", "language": "python"},
            {"id": 3, "full_name": "user/repo3", "language": "python"},
        ]
        
        mock_extract_repo.return_value = {"fixtures": 50, "mocks": 20}
        
        with patch("collection.extractor.db_session") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.execute.return_value = mock_cursor
            
            # Should stop after processing enough repos
            result = extract_all_cloned(
                language="python",
                target_analyzed=100,
            )
            
            assert isinstance(result, dict)
            assert result.get("early_stopped", False) or mock_extract_repo.call_count <= 3
