"""Small end-to-end integration harness for collection on a tiny repo.

Creates a temporary git repo with one test file, extracts fixtures, and
persists them into a temporary DB for quick validation of the extraction
and persistence pipeline.
"""

import subprocess
import tempfile
from pathlib import Path
from collection.fixture_extractor import extract_fixtures_at_commit
from collection.corpus_utils import persist_repository_and_fixtures, construct_repo_dict
from collection.db import initialise_db


def create_sample_repo(root: Path) -> Path:
    repo_dir = root / "sample_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    (repo_dir / "tests").mkdir()
    tf = repo_dir / "tests" / "test_sample.py"
    tf.write_text("""
def test_example():
    assert 1 + 1 == 2

import pytest

@pytest.fixture
def sample_fixture():
    return 42
""")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add test", "--quiet"], cwd=repo_dir, check=True
    )
    return repo_dir


def run():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = create_sample_repo(td)
        # Use the current HEAD commit
        commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo)
            .decode()
            .strip()
        )

        fixtures = extract_fixtures_at_commit(repo, commit, "python")

        db_path = td / "small.db"
        initialise_db(db_path)

        repo_meta = construct_repo_dict(
            "owner/sample_repo", "python", stars=0, clone_url=str(repo)
        )
        count = persist_repository_and_fixtures(db_path, repo_meta, fixtures)
        print(f"Persisted {count} fixtures into {db_path}")


if __name__ == "__main__":
    run()
