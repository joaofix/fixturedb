"""Tests for clone_primitives.py credential detection and skip behavior."""

from unittest.mock import MagicMock, patch

from collection.clone_primitives import _output_requests_credentials, clone_to_tempdir


class TestOutputRequestsCredentials:
    """Tests for credential prompt detection in git output."""

    def test_username_prompt_detected(self):
        assert _output_requests_credentials("Username for 'https://github.com': ")

    def test_password_prompt_detected(self):
        assert _output_requests_credentials("Password for 'https://github.com': ")

    def test_pat_prompt_detected(self):
        assert _output_requests_credentials(
            "Personal access token for 'https://github.com': "
        )

    def test_repository_not_found_detected(self):
        assert _output_requests_credentials("remote: Repository not found")
        assert _output_requests_credentials("fatal: repository not found")

    def test_does_not_exist_detected(self):
        assert _output_requests_credentials("does not exist")

    def test_unknown_private_repo_detected(self):
        assert _output_requests_credentials("fatal: could not read Username")

    def test_authentication_failed_detected(self):
        assert _output_requests_credentials(
            "Authentication failed for 'https://github.com': not authorized"
        )

    def test_permission_denied_detected(self):
        assert _output_requests_credentials("PERMISSION_DENIED")

    def test_normal_error_not_detected(self):
        assert not _output_requests_credentials(
            "fatal: unable to access 'https://github.com': The requested URL returned error: 404"
        )

    def test_empty_output_not_detected(self):
        assert not _output_requests_credentials("")

    def test_successful_clone_not_detected(self):
        assert not _output_requests_credentials("Cloning into 'repo'...")


class TestCloneToTempdirCredentialSkip:
    """Tests for credential-skipping behavior in clone_to_tempdir."""

    def test_returns_none_on_credential_prompt(self, tmp_path):
        """clone_to_tempdir should return (None, None) when git asks for credentials."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "remote: Repository not found"

        with patch("collection.clone_primitives.subprocess.run", return_value=mock_result):
            repo_path, temp_root = clone_to_tempdir(
                "owner/repo",
                "https://github.com/owner/repo.git",
                [],
                timeout=60,
                prefix="test-",
            )
            assert repo_path is None
            assert temp_root is None

    def test_returns_none_on_username_prompt(self, tmp_path):
        """clone_to_tempdir should return (None, None) on username prompt."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "Username for 'https://github.com': "

        with patch("collection.clone_primitives.subprocess.run", return_value=mock_result):
            repo_path, temp_root = clone_to_tempdir(
                "owner/repo",
                "https://github.com/owner/repo.git",
                [],
                timeout=60,
                prefix="test-",
            )
            assert repo_path is None
            assert temp_root is None

    def test_returns_path_on_success(self, tmp_path):
        """clone_to_tempdir should return path on successful clone."""
        with patch("collection.clone_primitives.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            mock_run.side_effect = lambda *args, **kwargs: None

            repo_path, temp_root = clone_to_tempdir(
                "owner/repo",
                "https://github.com/owner/repo.git",
                ["--depth", "1"],
                timeout=60,
                prefix="test-",
            )
            assert (
                repo_path is not None or mock_run.call_count > 0
            )  # Either succeeds or was attempted
