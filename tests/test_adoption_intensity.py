"""Unit tests for agent adoption intensity computation."""

import subprocess

from collection.tiered_agent_corpus_scanner import (
    compute_adoption_intensity,
    count_total_commits_since,
)

# ---------------------------------------------------------------------------
# count_total_commits_since
# ---------------------------------------------------------------------------


class TestCountTotalCommitsSince:
    """Tests for count_total_commits_since using temporary git repos."""

    def test_counts_commits_in_range(self, tmp_path):
        """Should count only commits after the given date."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(repo)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "a@b.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "A"],
            check=True, capture_output=True,
        )

        # Commit 1: dated 2024-01-01 (before adoption window)
        (repo / "f1.txt").write_text("a")
        subprocess.run(
            ["git", "-C", str(repo), "add", "f1.txt"],
            check=True, capture_output=True,
        )
        env_2024 = {"GIT_AUTHOR_DATE": "2024-01-01T00:00:00",
                     "GIT_COMMITTER_DATE": "2024-01-01T00:00:00"}
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "old"],
            check=True, capture_output=True,
            env={**__import__("os").environ, **env_2024},
        )

        # Commit 2: dated 2025-02-01 (in window)
        (repo / "f2.txt").write_text("b")
        subprocess.run(
            ["git", "-C", str(repo), "add", "f2.txt"],
            check=True, capture_output=True,
        )
        env_2025a = {"GIT_AUTHOR_DATE": "2025-02-01T00:00:00",
                      "GIT_COMMITTER_DATE": "2025-02-01T00:00:00"}
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "new"],
            check=True, capture_output=True,
            env={**__import__("os").environ, **env_2025a},
        )

        # Commit 3: dated 2025-03-01 (in window)
        (repo / "f3.txt").write_text("c")
        subprocess.run(
            ["git", "-C", str(repo), "add", "f3.txt"],
            check=True, capture_output=True,
        )
        env_2025b = {"GIT_AUTHOR_DATE": "2025-03-01T00:00:00",
                      "GIT_COMMITTER_DATE": "2025-03-01T00:00:00"}
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "newer"],
            check=True, capture_output=True,
            env={**__import__("os").environ, **env_2025b},
        )

        count = count_total_commits_since(repo, "2025-01-01")
        assert count == 2

    def test_no_commits_in_window(self, tmp_path):
        """Should return 0 when no commits exist after the date."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(repo)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "a@b.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "A"],
            check=True, capture_output=True,
        )

        (repo / "f.txt").write_text("a")
        subprocess.run(
            ["git", "-C", str(repo), "add", "f.txt"],
            check=True, capture_output=True,
        )
        env_old = {"GIT_AUTHOR_DATE": "2024-06-01T00:00:00",
                    "GIT_COMMITTER_DATE": "2024-06-01T00:00:00"}
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "old"],
            check=True, capture_output=True,
            env={**__import__("os").environ, **env_old},
        )

        count = count_total_commits_since(repo, "2025-01-01")
        assert count == 0

    def test_non_existent_repo_returns_zero(self, tmp_path):
        """Should return 0 for a non-existent path."""
        count = count_total_commits_since(tmp_path / "nope", "2025-01-01")
        assert count == 0

    def test_not_a_git_repo_returns_zero(self, tmp_path):
        """Should return 0 for a directory that is not a git repo."""
        d = tmp_path / "not_git"
        d.mkdir()
        count = count_total_commits_since(d, "2025-01-01")
        assert count == 0


# ---------------------------------------------------------------------------
# compute_adoption_intensity
# ---------------------------------------------------------------------------


class TestComputeAdoptionIntensity:
    """Tests for compute_adoption_intensity category assignment."""

    def test_no_commits_zero_total(self, tmp_path):
        """0 total commits → no_commits."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=0, total_commit_count=0,
        )
        assert result == "no_commits"

    def test_no_commits_zero_agent(self, tmp_path):
        """0 agent commits but some total → no_commits."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=0, total_commit_count=100,
        )
        assert result == "no_commits"

    def test_experimental_below_1_percent(self, tmp_path):
        """0.5% → experimental."""
        # 1 agent / 200 total = 0.5%
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=1, total_commit_count=200,
        )
        assert result == "experimental"

    def test_experimental_at_boundary_below_1(self, tmp_path):
        """0.99% → experimental (just below 1% threshold)."""
        # 99 agent / 10000 total = 0.99%
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=99, total_commit_count=10000,
        )
        assert result == "experimental"

    def test_limited_at_1_percent(self, tmp_path):
        """Exactly 1% → limited."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=1, total_commit_count=100,
        )
        assert result == "limited"

    def test_limited_mid_range(self, tmp_path):
        """3% → limited."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=3, total_commit_count=100,
        )
        assert result == "limited"

    def test_limited_below_5_percent(self, tmp_path):
        """4.9% → limited (just below 5% threshold)."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=49, total_commit_count=1000,
        )
        assert result == "limited"

    def test_consistent_at_5_percent(self, tmp_path):
        """Exactly 5% → consistent."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=5, total_commit_count=100,
        )
        assert result == "consistent"

    def test_consistent_mid_range(self, tmp_path):
        """10% → consistent."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=10, total_commit_count=100,
        )
        assert result == "consistent"

    def test_consistent_at_20_percent(self, tmp_path):
        """Exactly 20% → consistent."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=20, total_commit_count=100,
        )
        assert result == "consistent"

    def test_pervasive_above_20_percent(self, tmp_path):
        """25% → pervasive."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=25, total_commit_count=100,
        )
        assert result == "pervasive"

    def test_pervasive_all_agent(self, tmp_path):
        """100% agent → pervasive."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=100, total_commit_count=100,
        )
        assert result == "pervasive"

    def test_pervasive_just_above_20(self, tmp_path):
        """20.1% → pervasive (just above threshold)."""
        result = compute_adoption_intensity(
            tmp_path, "2025-01-01",
            agent_commit_count=201, total_commit_count=1000,
        )
        assert result == "pervasive"

    def test_uses_git_count_when_total_is_none(self, tmp_path):
        """When total_commit_count is None, should fall back to git rev-list."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(repo)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "a@b.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "A"],
            check=True, capture_output=True,
        )

        # 10 commits in window
        for i in range(10):
            (repo / f"f{i}.txt").write_text(str(i))
            subprocess.run(
                ["git", "-C", str(repo), "add", f"f{i}.txt"],
                check=True, capture_output=True,
            )
            env = {"GIT_AUTHOR_DATE": "2025-02-01T00:00:00",
                   "GIT_COMMITTER_DATE": "2025-02-01T00:00:00"}
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-m", f"c{i}"],
                check=True, capture_output=True,
                env={**__import__("os").environ, **env},
            )

        # 2 agent out of 10 = 20% → consistent
        result = compute_adoption_intensity(
            repo, "2025-01-01",
            agent_commit_count=2, total_commit_count=None,
        )
        assert result == "consistent"

    def test_all_categories_span(self, tmp_path):
        """Verify all five categories are reachable."""
        categories = set()
        # no_commits
        categories.add(compute_adoption_intensity(
            tmp_path, "2025-01-01", agent_commit_count=0, total_commit_count=0,
        ))
        # experimental: 0.5%
        categories.add(compute_adoption_intensity(
            tmp_path, "2025-01-01", agent_commit_count=1, total_commit_count=200,
        ))
        # limited: 3%
        categories.add(compute_adoption_intensity(
            tmp_path, "2025-01-01", agent_commit_count=3, total_commit_count=100,
        ))
        # consistent: 10%
        categories.add(compute_adoption_intensity(
            tmp_path, "2025-01-01", agent_commit_count=10, total_commit_count=100,
        ))
        # pervasive: 30%
        categories.add(compute_adoption_intensity(
            tmp_path, "2025-01-01", agent_commit_count=30, total_commit_count=100,
        ))

        expected = {"no_commits", "experimental", "limited", "consistent", "pervasive"}
        assert categories == expected