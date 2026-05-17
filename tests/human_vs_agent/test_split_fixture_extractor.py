"""
Unit tests for FixtureDB split fixture extraction.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from collection.fixture_extractor import (
    LLMFixtureExtractor,
    Pre2021FixtureExtractor,
)
from collection.config import AGENT_DATASET_START_DATE


class TestPre2021FixtureExtractor:
    def test_constructor_uses_real_arguments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = Pre2021FixtureExtractor(
                clones_dir=Path(tmpdir),
                source_db=Path(tmpdir) / "corpus.db",
            )

            assert extractor.clones_dir == Path(tmpdir)
            assert extractor.source_db == Path(tmpdir) / "corpus.db"
            assert hasattr(extractor, "extract_all")


class TestLLMFixtureExtractor:
    def test_constructor_uses_real_arguments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = LLMFixtureExtractor(
                clones_dir=Path(tmpdir),
                source_db=Path(tmpdir) / "llm.db",
                start_date=AGENT_DATASET_START_DATE,
            )

            assert extractor.clones_dir == Path(tmpdir)
            assert extractor.source_db == Path(tmpdir) / "llm.db"
            assert extractor.start_date == AGENT_DATASET_START_DATE

    def test_find_added_test_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = LLMFixtureExtractor(
                clones_dir=Path(tmpdir),
                source_db=Path(tmpdir) / "llm.db",
            )

            diff = (
                "diff --git a/tests/conftest.py b/tests/conftest.py\n"
                "--- a/tests/conftest.py\n"
                "+++ b/tests/conftest.py\n"
                "+@pytest.fixture\n"
                "+def new_fixture():\n"
                "+    return 1\n"
            )

            assert extractor._find_added_test_files(diff) == ["tests/conftest.py"]

    def test_is_completely_added_fixture_detects_deletions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = LLMFixtureExtractor(
                clones_dir=Path(tmpdir),
                source_db=Path(tmpdir) / "llm.db",
            )

            complete_diff = (
                "diff --git a/tests/conftest.py b/tests/conftest.py\n"
                "+++ b/tests/conftest.py\n"
                "+@pytest.fixture\n"
                "+def new_fixture():\n"
                "+    return 1\n"
            )
            partial_diff = (
                "diff --git a/tests/conftest.py b/tests/conftest.py\n"
                "+++ b/tests/conftest.py\n"
                "-@pytest.fixture\n"
                "+@pytest.fixture\n"
                "+def new_fixture():\n"
                "+    return 1\n"
            )

            assert extractor._is_completely_added_fixture(
                complete_diff, "tests/conftest.py", "new_fixture"
            ) is True
            assert extractor._is_completely_added_fixture(
                partial_diff, "tests/conftest.py", "new_fixture"
            ) is False

    def test_get_commit_info_handles_git_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = LLMFixtureExtractor(
                clones_dir=Path(tmpdir),
                source_db=Path(tmpdir) / "llm.db",
            )
            repo_path = Path(tmpdir) / "repo"
            repo_path.mkdir()

            mocked = type("R", (), {"stdout": "2023-05-01 12:00:00 +0000|Dev|dev@example.com|Message"})
            with patch("subprocess.run", return_value=mocked):
                info = extractor._get_commit_info(repo_path, "abc123")

            assert info is not None
            assert info["date"] == "2023-05-01"
            assert info["author_name"] == "Dev"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
