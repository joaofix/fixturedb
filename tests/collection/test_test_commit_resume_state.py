"""Direct unit tests for test_commit_resume_state.py's save/load round-trip.

This module had no direct test coverage before -- a real gap that let a real
bug slip through: commits_scanned_by_language was being silently dropped on
save because _save_test_commit_resume_state built its checkpoint dict from a
fixed, hardcoded key list that didn't include it. Every human_test_commit_
filter.py test that exercised this indirectly used a single process_fn call
(no restart), so the drop was invisible -- these tests specifically exercise
the save-then-load round-trip a real resumed run depends on.
"""

from pathlib import Path

from collection.test_commit_resume_state import (
    _load_test_commit_resume_state,
    _save_test_commit_resume_state,
)


def test_round_trip_preserves_commits_scanned_by_language(tmp_path: Path):
    counts = {
        "repos_processed": 5,
        "commits_scanned": 42,
        "repos_with_test_commits": 3,
        "test_commits_found": 7,
        "commits_scanned_by_language": {"python": 30, "java": 12},
    }
    _save_test_commit_resume_state(
        tmp_path, counts, {"owner/repo-a", "owner/repo-b"}, role="human"
    )

    _, _, completed_repos, loaded_counts = _load_test_commit_resume_state(
        tmp_path, role="human"
    )

    assert loaded_counts["commits_scanned_by_language"] == {"python": 30, "java": 12}
    assert loaded_counts["commits_scanned"] == 42
    assert loaded_counts["repos_processed"] == 5
    assert completed_repos == {"owner/repo-a", "owner/repo-b"}


def test_load_defaults_to_empty_dict_when_checkpoint_missing(tmp_path: Path):
    _, _, completed_repos, counts = _load_test_commit_resume_state(
        tmp_path, role="human"
    )
    assert counts["commits_scanned_by_language"] == {}
    assert completed_repos == set()


def test_load_defaults_to_empty_dict_for_old_checkpoint_without_the_key(
    tmp_path: Path,
):
    """A checkpoint written before this field existed (e.g. an in-progress
    remote collection resumed with old code) must still load cleanly."""
    old_style_counts = {
        "repos_processed": 2,
        "commits_scanned": 10,
        "repos_with_test_commits": 1,
        "test_commits_found": 3,
        # no commits_scanned_by_language key at all
    }
    _save_test_commit_resume_state(tmp_path, old_style_counts, {"owner/repo"}, role="human")

    # Simulate an even older on-disk file that never had the key at all by
    # writing the checkpoint directly (save now always includes it -- this
    # confirms load() doesn't choke if it's genuinely absent).
    checkpoint_path = tmp_path / "human_test_commits.checkpoint.json"
    import json

    data = json.loads(checkpoint_path.read_text())
    del data["commits_scanned_by_language"]
    checkpoint_path.write_text(json.dumps(data))

    _, _, _, counts = _load_test_commit_resume_state(tmp_path, role="human")
    assert counts["commits_scanned_by_language"] == {}
    assert counts["commits_scanned"] == 10


def test_agent_role_round_trip_also_supports_the_key(tmp_path: Path):
    """The function is shared with Dataset A's agent-role checkpointing --
    confirm the new key doesn't break that path, even though Dataset A's
    test-commit-filter doesn't populate it today."""
    counts = {
        "repos_processed": 1,
        "commits_scanned": 5,
        "repos_with_test_commits": 1,
        "test_commits_found": 2,
    }
    _save_test_commit_resume_state(tmp_path, counts, {"owner/repo"}, role="agent")
    _, _, _, loaded_counts = _load_test_commit_resume_state(tmp_path, role="agent")
    assert loaded_counts["commits_scanned_by_language"] == {}
    assert loaded_counts["commits_scanned"] == 5
