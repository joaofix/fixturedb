import json

from collection.phase_1d_discover_matched_repos import _tier2_exclude_repo_names


def test_excludes_repos_already_counted_in_tier1(tmp_path):
    """Regression: Phase 1D always called collect_matched_agent_commits with
    exclude_repo_names=set(), so Tier 2 discovery could re-select/re-verify
    repos Tier 1 already counted, double-counting them across both tiers'
    yield. This wires the exclusion up using Phase 1A's own repo list (the
    same source Phase 1B uses), since Phase 1C's assessment only stores
    aggregate counts, not repo names."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "phase_1a_agent_commits_tier1_20260101_000000.json").write_text(
        json.dumps(
            {
                "repo_details": {
                    "owner/repo1": {"repo_id": 1, "commits": []},
                    "owner/repo2": {"repo_id": 2, "commits": []},
                }
            }
        )
    )

    excluded = _tier2_exclude_repo_names(output_dir)

    assert excluded == {"owner/repo1", "owner/repo2"}


def test_excludes_nothing_when_no_phase1a_output_exists(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    assert _tier2_exclude_repo_names(output_dir) == set()
