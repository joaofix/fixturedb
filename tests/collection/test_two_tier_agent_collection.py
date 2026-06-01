"""
Unit tests for two_tier agent collection and detection.

Tests agent commit detection including:
- Co-authored-by trailer parsing (case-insensitive)
- Agent signature matching in trailers and author metadata
- Edge cases in commit detection
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import subprocess

import pytest

from collection.agent_commit_detector import (
    Tier1RepositoryScanner,
    COAUTHOR_TRAILER_RE,
)
from collection.config import AGENT_CORPUS_START_DATE


class TestCoauthoredByTrailerDetection:
    """Test co-authored-by trailer regex and parsing."""

    def test_coauthor_trailer_regex_basic(self):
        """Should extract co-authored-by trailer value."""
        body = "Fix bug\n\nCo-authored-by: Claude <claude@anthropic.com>"
        matches = COAUTHOR_TRAILER_RE.findall(body)
        assert len(matches) == 1
        assert "Claude" in matches[0]
        assert "claude@anthropic.com" in matches[0]

    def test_coauthor_trailer_regex_lowercase(self):
        """Should match lowercase co-authored-by."""
        body = "Fix bug\n\nco-authored-by: GitHub Copilot <copilot@github.com>"
        matches = COAUTHOR_TRAILER_RE.findall(body)
        assert len(matches) == 1
        assert "GitHub Copilot" in matches[0]

    def test_coauthor_trailer_regex_uppercase(self):
        """Should match uppercase CO-AUTHORED-BY."""
        body = "Fix bug\n\nCO-AUTHORED-BY: Cursor <cursor@anysoftware.io>"
        matches = COAUTHOR_TRAILER_RE.findall(body)
        assert len(matches) == 1
        assert "Cursor" in matches[0]

    def test_coauthor_trailer_regex_multiple(self):
        """Should extract multiple co-authored-by trailers."""
        body = """Refactor usability tests.

Co-authored-by: Claude <claude@anthropic.com>
Co-authored-by: Another-name <another-name@example.com>"""
        matches = COAUTHOR_TRAILER_RE.findall(body)
        assert len(matches) == 2
        assert "Claude" in matches[0]
        assert "Another-name" in matches[1]

    def test_coauthor_trailer_regex_mixed_case(self):
        """Should match mixed case variations."""
        body = "Fix\n\nCo-Authored-By: Aider <aider@paul.pub>"
        matches = COAUTHOR_TRAILER_RE.findall(body)
        assert len(matches) == 1
        assert "Aider" in matches[0]


class TestTier1RepositoryScannerDetection:
    """Test Tier1RepositoryScanner agent detection with co-authored-by."""

    @pytest.fixture
    def scanner(self):
        """Create a scanner instance for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Tier1RepositoryScanner(Path(tmpdir))

    def test_detect_claude_in_coauthored_by(self, scanner):
        """Should detect Claude from co-authored-by trailer."""
        body = """Refactor usability tests.

Co-authored-by: Claude <claude@anthropic.com>"""
        agent = scanner._detect_agent_in_commit("John", "john@example.com", body)
        assert agent == "claude"

    def test_detect_copilot_in_coauthored_by(self, scanner):
        """Should detect GitHub Copilot from co-authored-by trailer."""
        body = """Add feature.

Co-authored-by: GitHub Copilot <copilot@github.com>"""
        agent = scanner._detect_agent_in_commit("Jane", "jane@example.com", body)
        assert agent == "copilot"

    def test_detect_cursor_in_coauthored_by(self, scanner):
        """Should detect Cursor from co-authored-by trailer."""
        body = """Refactor code.

Co-authored-by: Cursor <cursor@anysoftware.io>"""
        agent = scanner._detect_agent_in_commit("Bob", "bob@example.com", body)
        assert agent == "cursor"

    def test_detect_aider_in_coauthored_by(self, scanner):
        """Should detect Aider from co-authored-by trailer (classified as 'other')."""
        body = """Update tests.

Co-authored-by: Aider <aider@paul.pub>"""
        agent = scanner._detect_agent_in_commit("Alice", "alice@example.com", body)
        assert agent == "other"  # Aider is grouped as "other" in config signatures

    def test_detect_openhands_in_coauthored_by(self, scanner):
        """Should detect OpenHands from co-authored-by trailer (classified as 'other')."""
        body = """Implement feature.

Co-authored-by: OpenHands <openhands@example.com>"""
        agent = scanner._detect_agent_in_commit("Charlie", "charlie@example.com", body)
        assert agent == "other"  # OpenHands is grouped as "other" in config signatures

    def test_detect_case_insensitive_coauthored_by(self, scanner):
        """Should detect agents with various case styles in co-authored-by."""
        # lowercase keyword
        body1 = "Fix\n\nco-authored-by: Claude <claude@anthropic.com>"
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body1) == "claude"

        # UPPERCASE keyword
        body2 = "Fix\n\nCO-AUTHORED-BY: Copilot <copilot@github.com>"
        assert (
            scanner._detect_agent_in_commit("User", "user@ex.com", body2) == "copilot"
        )

        # MixedCase keyword
        body3 = "Fix\n\nCo-Authored-By: Cursor <cursor@anysoftware.io>"
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body3) == "cursor"

    def test_detect_agent_in_author_takes_precedence(self, scanner):
        """Should detect from author name if present (checked first)."""
        body = "Regular commit"
        agent = scanner._detect_agent_in_commit("Claude", "claude@anthropic.com", body)
        assert agent == "claude"

    def test_detect_agent_in_multiple_coauthors(self, scanner):
        """Should detect agent when multiple co-authors present."""
        body = """Add feature.

Co-authored-by: John Doe <john@example.com>
Co-authored-by: Claude <claude@anthropic.com>
Co-authored-by: Jane Smith <jane@example.com>"""
        agent = scanner._detect_agent_in_commit("Bob", "bob@example.com", body)
        assert agent == "claude"

    def test_detect_no_agent_present(self, scanner):
        """Should return None when no agent detected."""
        body = """Regular commit by human.

Co-authored-by: Alice <alice@example.com>
Co-authored-by: Bob <bob@example.com>"""
        agent = scanner._detect_agent_in_commit("Charlie", "charlie@example.com", body)
        assert agent is None

    def test_detect_agent_in_email_anthropic(self, scanner):
        """Should detect agent from email domain (anthropic)."""
        body = "Regular commit"
        agent = scanner._detect_agent_in_commit("User", "user@anthropic.com", body)
        assert agent == "claude"

    def test_detect_agent_with_whitespace_variations(self, scanner):
        """Should handle co-authored-by with various whitespace."""
        # Extra spaces
        body1 = "Fix\n\nCo-authored-by:   Claude   <claude@anthropic.com>  "
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body1) == "claude"

        # No space after colon
        body2 = "Fix\n\nCo-authored-by:Claude <claude@anthropic.com>"
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body2) == "claude"

    def test_detect_agent_without_email_in_coauthor(self, scanner):
        """Should detect agents from co-authored-by trailer without email address."""
        # Just agent name
        body1 = "Fix\n\nCo-Authored-By: Claude Sonnet"
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body1) == "claude"

        # Agent name with descriptive text
        body2 = "Fix\n\nco-authored-by: Claude"
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body2) == "claude"

        # Another agent
        body3 = "Fix\n\nCo-authored-by: GitHub Copilot"
        assert (
            scanner._detect_agent_in_commit("User", "user@ex.com", body3) == "copilot"
        )

        # Cursor without email
        body4 = "Fix\n\nCo-authored-by: Cursor IDE"
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body4) == "cursor"

        # Agent grouped as "other"
        body5 = "Fix\n\nCo-authored-by: Aider Assistant"
        assert scanner._detect_agent_in_commit("User", "user@ex.com", body5) == "other"

    def test_detect_only_validates_coauthor_signature(self, scanner):
        """Co-authored-by should only match known agents, not random names."""
        body = """Fix.

Co-authored-by: RandomDeveloper <random@example.com>"""
        agent = scanner._detect_agent_in_commit("User", "user@example.com", body)
        assert agent is None

    def test_detect_anthropic_keyword_in_coauthor(self, scanner):
        """Should detect Claude via 'anthropic' keyword in co-authored-by."""
        body = """Fix.

Co-authored-by: AI Assistant <ai@anthropic.com>"""
        agent = scanner._detect_agent_in_commit("User", "user@example.com", body)
        assert agent == "claude"

    def test_detect_github_apps_copilot_in_coauthor(self, scanner):
        """Should detect Copilot via GitHub app path in co-authored-by."""
        body = """Fix.

Co-authored-by: github.com/apps/github-copilot <copilot@example.com>"""
        agent = scanner._detect_agent_in_commit("User", "user@example.com", body)
        assert agent == "copilot"

    def test_detect_all_known_agents_in_coauthors(self, scanner):
        """Should detect all known agent types in co-authored-by."""
        # Note: config.py groups aider, openhands, devin, etc. under "other"
        # while agent_patterns.py has fine-grained types. Using config.py here.
        test_cases = [
            ("Claude <claude@anthropic.com>", "claude"),
            ("GitHub Copilot <copilot@github.com>", "copilot"),
            ("Cursor <cursor@anysoftware.io>", "cursor"),
            ("Aider <aider@paul.pub>", "other"),  # Grouped under "other"
            ("OpenHands <openhands@example.com>", "other"),  # Grouped under "other"
            ("Devin AI <devin@example.com>", "other"),  # Grouped under "other"
            ("Google Jules <jules@example.com>", "other"),  # Grouped under "other"
            ("Cline <cline@example.com>", "other"),  # Grouped under "other"
            ("Junie <junie@example.com>", "other"),  # Grouped under "other"
            ("Gemini <gemini@example.com>", "other"),  # Grouped under "other"
            ("CodeRabbit <coderabbit@example.com>", "other"),  # Grouped under "other"
            ("Windsurf <windsurf@example.com>", "other"),  # Grouped under "other"
        ]

        for coauthor_str, expected_agent in test_cases:
            body = f"Fix.\n\nCo-authored-by: {coauthor_str}"
            agent = scanner._detect_agent_in_commit("User", "user@example.com", body)
            assert agent == expected_agent, (
                f"Failed to detect {expected_agent} from {coauthor_str}, got {agent}"
            )
