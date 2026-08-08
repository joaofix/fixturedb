import pytest

from collection.config import DATASET_C_SAMPLING_SEED
from collection.dataset_sampler import StratifiedSampler, sample_repos_by_language


def _make_fixtures():
    return [
        {"id": 0, "fixture_type": "pytest"},
        {"id": 1, "fixture_type": "pytest"},
        {"id": 10, "fixture_type": "unittest"},
        {"id": 11, "fixture_type": "unittest"},
        {"id": 20, "fixture_type": "doctest"},
        {"id": 21, "fixture_type": "doctest"},
    ]


def test_sample_reaches_exact_target_count():
    fixtures = _make_fixtures()
    result = StratifiedSampler(random_seed=42).sample(fixtures, target_count=4)

    assert result.sampled_count == 4
    assert len(result.sampled_ids) == 4


def test_sample_does_not_silently_return_empty_when_target_smaller_than_strata_count():
    """Regression: the backfill loop was guarded by `while ... and sampled`,
    so when every stratum's proportional share rounded down to 0 (small
    target_count relative to the number of strata), `sampled` stayed empty
    and the loop never ran -- sample() returned 0 rows for a nonzero
    target_count instead of backfilling to the requested size."""
    fixtures = _make_fixtures()

    result = StratifiedSampler(random_seed=42).sample(fixtures, target_count=1)

    assert result.sampled_count == 1
    assert len(result.sampled_ids) == 1


def test_sample_full_population_returns_everything():
    fixtures = _make_fixtures()
    result = StratifiedSampler(random_seed=42).sample(
        fixtures, target_count=len(fixtures)
    )

    assert result.sampled_count == len(fixtures)
    assert set(result.sampled_ids) == {f["id"] for f in fixtures}


def _make_repos():
    """python: 100 repos x 10 fixtures = 1000 (50%); java: 50 x 10 = 500
    (25%); javascript: 25 x 20 = 500 (25%). Total 2000 fixtures across 175
    repos, 3 languages with distinct proportions and repo-size shapes."""
    repos = [{"repo_id": i, "language": "python", "fixture_count": 10} for i in range(100)]
    repos += [{"repo_id": i, "language": "java", "fixture_count": 10} for i in range(100, 150)]
    repos += [
        {"repo_id": i, "language": "javascript", "fixture_count": 20} for i in range(150, 175)
    ]
    return repos


class TestSampleReposByLanguage:
    def test_reproducible_with_same_seed(self):
        repos = _make_repos()
        r1 = sample_repos_by_language(repos, target_count=200, seed=7)
        r2 = sample_repos_by_language(repos, target_count=200, seed=7)
        assert r1.sampled_repo_ids == r2.sampled_repo_ids
        assert r1.sampled_fixture_count == r2.sampled_fixture_count

    def test_default_seed_is_the_project_wide_constant(self):
        repos = _make_repos()
        default = sample_repos_by_language(repos, target_count=200)
        explicit = sample_repos_by_language(
            repos, target_count=200, seed=DATASET_C_SAMPLING_SEED
        )
        assert default.random_seed == DATASET_C_SAMPLING_SEED
        assert default.sampled_repo_ids == explicit.sampled_repo_ids

    def test_preserves_original_language_proportions(self):
        repos = _make_repos()
        # tolerance=0.05, not the 0.02 default: whole-repo sampling is
        # inherently chunkier than fixture-level sampling (10-20 fixtures
        # per repo here), so exact-proportion quantization noise at a small
        # target_count is expected, not a bug -- a real Dataset C run's
        # chunks are tiny relative to its ~50k target, so this is a
        # worst-case-shaped test population, not a realistic one.
        result = sample_repos_by_language(repos, target_count=200, seed=1, tolerance=0.05)

        assert result.distribution_check["python"]["original_ratio"] == 0.5
        assert result.distribution_check["java"]["original_ratio"] == 0.25
        assert result.distribution_check["javascript"]["original_ratio"] == 0.25
        for lang, check in result.distribution_check.items():
            assert check["tolerance_met"], f"{lang}: {check}"

    def test_never_splits_a_repo(self):
        """A repo's presence in sampled_repo_ids must be all-or-nothing --
        sampled_fixture_count must equal the exact sum of fixture_count over
        only the sampled repos, never a partial count."""
        repos = _make_repos()
        result = sample_repos_by_language(repos, target_count=333, seed=3)

        by_id = {r["repo_id"]: r["fixture_count"] for r in repos}
        expected = sum(by_id[rid] for rid in result.sampled_repo_ids)
        assert result.sampled_fixture_count == expected

    def test_sampled_count_close_to_but_not_necessarily_exact_target(self):
        repos = _make_repos()
        result = sample_repos_by_language(repos, target_count=200, seed=5)

        # Repos are indivisible chunks of 10-20 fixtures each -- allow a
        # generous margin rather than asserting an exact match.
        assert abs(result.sampled_fixture_count - 200) <= 40

    def test_raises_on_empty_repo_list(self):
        with pytest.raises(ValueError, match="empty"):
            sample_repos_by_language([], target_count=10)

    def test_raises_when_every_repo_has_zero_fixtures(self):
        repos = [{"repo_id": 1, "language": "python", "fixture_count": 0}]
        with pytest.raises(ValueError, match="fixture_count 0"):
            sample_repos_by_language(repos, target_count=1)
