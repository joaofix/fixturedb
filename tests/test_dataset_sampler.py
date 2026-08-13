import pytest

from collection.config import DATASET_C_SAMPLING_SEED
from collection.dataset_sampler import (
    StratifiedSampler,
    _allocate_quotas_with_shortfall_reallocation,
    sample_repos_by_language,
)


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


class TestAllocateQuotasWithShortfallReallocation:
    def test_even_split_no_shortfall(self):
        result = _allocate_quotas_with_shortfall_reallocation(
            lang_caps={"python": 1000, "java": 1000},
            target_weights={"python": 0.5, "java": 0.5},
            target_count=200,
        )
        assert result == {"python": 100.0, "java": 100.0}

    def test_single_language_short_redistributes_to_the_rest(self):
        """Matches the plan's worked example: typescript can't cover its
        51% target share (only 200 fixtures available), so it's capped at
        200 and the other three languages absorb the shortfall,
        proportional to their own target shares."""
        result = _allocate_quotas_with_shortfall_reallocation(
            lang_caps={"ts": 200, "py": 5000, "java": 500, "js": 400},
            target_weights={"ts": 0.51, "py": 0.36, "java": 0.07, "js": 0.06},
            target_count=1000,
        )
        assert result["ts"] == 200
        assert result["py"] == pytest.approx(587.755, abs=0.01)
        assert result["java"] == pytest.approx(114.286, abs=0.01)
        assert result["js"] == pytest.approx(97.959, abs=0.01)
        assert sum(result.values()) == pytest.approx(1000)

    def test_cascading_double_shortfall(self):
        """Capping the first short language can push a second language over
        its own cap too -- must keep reallocating, not stop after one pass."""
        result = _allocate_quotas_with_shortfall_reallocation(
            lang_caps={"ts": 50, "js": 50, "py": 5000, "java": 500},
            target_weights={"ts": 0.51, "py": 0.36, "java": 0.07, "js": 0.06},
            target_count=1000,
        )
        assert result["ts"] == 50
        assert result["js"] == 50
        assert sum(result.values()) == pytest.approx(1000)
        # Remaining 900 split between python/java proportional to 0.36:0.07.
        assert result["py"] == pytest.approx(900 * 0.36 / 0.43, abs=0.01)
        assert result["java"] == pytest.approx(900 * 0.07 / 0.43, abs=0.01)

    def test_target_language_absent_from_population_is_ignored(self):
        """target_weights can list a language Dataset C simply has no repos
        of at all -- its share cascades into the other languages, nothing
        crashes or gets silently dropped."""
        result = _allocate_quotas_with_shortfall_reallocation(
            lang_caps={"py": 100, "java": 100},
            target_weights={"ts": 0.51, "py": 0.36, "java": 0.07, "js": 0.06},
            target_count=200,
        )
        assert set(result.keys()) == {"py", "java"}
        assert sum(result.values()) == pytest.approx(200)

    def test_population_language_absent_from_target_gets_zero(self):
        """A language Dataset C has but the match dataset doesn't must get
        zero quota -- matching the other dataset's mix means not
        representing a language it has none of."""
        result = _allocate_quotas_with_shortfall_reallocation(
            lang_caps={"python": 100, "ruby": 50},
            target_weights={"python": 1.0},
            target_count=100,
        )
        assert result == {"python": 100.0, "ruby": 0.0}

    def test_accepts_raw_counts_not_just_normalized_fractions(self):
        """target_weights is ratio-based -- raw counts (not summing to 1)
        must produce the same allocation as their normalized equivalent."""
        raw = _allocate_quotas_with_shortfall_reallocation(
            lang_caps={"python": 1000, "java": 1000},
            target_weights={"python": 30, "java": 10},
            target_count=200,
        )
        normalized = _allocate_quotas_with_shortfall_reallocation(
            lang_caps={"python": 1000, "java": 1000},
            target_weights={"python": 0.75, "java": 0.25},
            target_count=200,
        )
        assert raw == normalized


class TestSampleReposByLanguageWithTargetProportions:
    def test_matches_target_proportions_not_populations_own_mix(self):
        """_make_repos()'s own mix is 50% python / 25% java / 25%
        javascript -- with an external target of 80% java / 20% python,
        the sample must follow the target, not the population's own split."""
        repos = _make_repos()
        result = sample_repos_by_language(
            repos,
            target_count=200,
            seed=1,
            target_proportions={"java": 0.8, "python": 0.2, "javascript": 0.0},
        )
        assert result.distribution_check["java"]["target_ratio"] == 0.8
        assert result.distribution_check["python"]["target_ratio"] == 0.2
        assert result.distribution_check["javascript"]["target_ratio"] == 0.0
        # javascript's own repos exist but get no quota -- none sampled.
        js_repo_ids = {r["repo_id"] for r in repos if r["language"] == "javascript"}
        assert not (js_repo_ids & set(result.sampled_repo_ids))

    def test_shortfall_stratum_takes_everything_it_has(self):
        """java only has 500 fixtures total -- asking for an (unreachable)
        90% of a 1000 target must cap java at its whole population (500,
        all 50 repos) rather than raising or under-filling silently."""
        repos = _make_repos()
        result = sample_repos_by_language(
            repos,
            target_count=1000,
            seed=2,
            target_proportions={"java": 0.9, "python": 0.05, "javascript": 0.05},
        )
        java_repo_ids = {r["repo_id"] for r in repos if r["language"] == "java"}
        sampled_java_ids = java_repo_ids & set(result.sampled_repo_ids)
        assert sampled_java_ids == java_repo_ids  # every java repo included
        assert result.distribution_check["java"]["sampled_fixture_count"] == 500
        assert result.distribution_check["java"]["dataset_c_available_fixture_count"] == 500

    def test_none_preserves_original_self_derived_behavior(self):
        """Passing target_proportions=None (the default) must produce
        exactly the same allocation as before this parameter existed."""
        repos = _make_repos()
        with_none = sample_repos_by_language(repos, target_count=200, seed=1)
        omitted = sample_repos_by_language(repos, target_count=200, seed=1)
        assert with_none.sampled_repo_ids == omitted.sampled_repo_ids
        assert (
            with_none.distribution_check["python"]["original_ratio"]
            == with_none.distribution_check["python"]["target_ratio"]
            == 0.5
        )
