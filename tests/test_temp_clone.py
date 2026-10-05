"""Tests for clone_primitives.py credential detection and skip behavior."""

import pytest
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

            repo_path, temp_root = clone_to_tempdir(
                "owner/repo",
                "https://github.com/owner/repo.git",
                ["--depth", "1"],
                timeout=60,
                prefix="test-",
            )
            assert repo_path is not None
            assert mock_run.call_count == 1  # succeeded on the first attempt, no retry


class TestCloneToTempdirThrottling:
    """GitHub throttling is transient: retried, never a permanent refusal."""

    THROTTLED = "fatal: unable to access 'https://github.com/owner/repo.git/': The requested URL returned error: 429"

    def _result(self, stderr):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = stderr
        return mock_result

    def test_throttled_clone_raises_clone_unavailable_after_retries(self):
        from collection.clone_primitives import CloneUnavailable

        with patch("collection.clone_primitives.subprocess.run", return_value=self._result(self.THROTTLED)) as run, \
                patch("collection.clone_primitives.time.sleep"):
            with pytest.raises(CloneUnavailable):
                clone_to_tempdir("owner/repo", "https://github.com/owner/repo.git", [], timeout=60, prefix="test-")
        assert run.call_count == 3  # retries=2 by default: one attempt plus two retries

    def test_throttle_with_a_username_prompt_is_still_transient(self):
        """git prints a username prompt when the server refuses the request. A
        throttled response with that prompt must not count as a permanent refusal."""
        from collection.clone_primitives import CloneUnavailable

        stderr = self.THROTTLED + "\nUsername for 'https://github.com': "
        with patch("collection.clone_primitives.subprocess.run", return_value=self._result(stderr)), \
                patch("collection.clone_primitives.time.sleep"):
            with pytest.raises(CloneUnavailable):
                clone_to_tempdir("owner/repo", "https://github.com/owner/repo.git", [], timeout=60, prefix="test-")

    def test_throttled_then_success_returns_the_clone(self, tmp_path):
        ok = self._result("")
        ok.returncode = 0
        with patch("collection.clone_primitives.subprocess.run", side_effect=[self._result(self.THROTTLED), ok]), \
                patch("collection.clone_primitives.time.sleep"), \
                patch("collection.clone_primitives.tempfile.mkdtemp", return_value=str(tmp_path / "t")):
            repo_path, temp_root = clone_to_tempdir("owner/repo", "https://github.com/owner/repo.git", [], timeout=60, prefix="test-")
        assert repo_path is not None

    def test_repository_named_like_a_throttle_word_is_still_a_permanent_refusal(self):
        """The patterns are specific: a repo whose name contains 'abuse' or '429' and
        which is genuinely not found must still be a permanent refusal."""
        stderr = "fatal: repository 'https://github.com/owner/abuse-429-tool/' not found"
        with patch("collection.clone_primitives.subprocess.run", return_value=self._result(stderr)):
            repo_path, temp_root = clone_to_tempdir(
                "owner/abuse-429-tool", "https://github.com/owner/abuse-429-tool.git", [], timeout=60, prefix="test-"
            )
        assert repo_path is None and temp_root is None
