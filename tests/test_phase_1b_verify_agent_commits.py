import json

from collection.phase_1b_verify_agent_commits import _load_phase1a_candidates


def test_loads_candidates_from_real_phase1a_output_filename(tmp_path):
    """Regression: the glob pattern used to look for "phase_1a_agent_files_*.json",
    but Phase 1A actually writes "phase_1a_agent_commits_tier1_*.json" -- the
    glob never matched, so Phase 1B always silently fell back to scanning
    every cloned repo instead of Phase 1A's filtered candidate list."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "phase_1a_agent_commits_tier1_20260101_000000.json").write_text(
        json.dumps(
            {
                "tier": 1,
                "repo_details": {
                    "owner/repo1": {"repo_id": 1, "commits": []},
                    "owner/repo2": {"repo_id": 2, "commits": []},
                },
            }
        )
    )

    candidates = _load_phase1a_candidates(output_dir)

    assert candidates is not None
    assert sorted(candidates) == ["owner/repo1", "owner/repo2"]


def test_returns_none_when_no_phase1a_output_exists(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    assert _load_phase1a_candidates(output_dir) is None


def test_returns_none_when_phase1a_output_is_malformed(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "phase_1a_agent_commits_tier1_20260101_000000.json").write_text(
        "not valid json"
    )

    assert _load_phase1a_candidates(output_dir) is None


def test_uses_latest_file_when_multiple_exist(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "phase_1a_agent_commits_tier1_20260101_000000.json").write_text(
        json.dumps({"repo_details": {"owner/old": {}}})
    )
    (output_dir / "phase_1a_agent_commits_tier1_20260102_000000.json").write_text(
        json.dumps({"repo_details": {"owner/new": {}}})
    )

    candidates = _load_phase1a_candidates(output_dir)

    assert candidates == ["owner/new"]
