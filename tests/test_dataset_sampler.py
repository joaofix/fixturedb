import pytest

from collection.config import DATASET_C_SAMPLING_SEED
from collection.dataset_sampler import StratifiedSampler, sample_fixtures_by_language


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


def _make_language_fixtures():
    """python: 100 fixtures across 10 repos (10 each); java: 50 fixtures
    across 10 repos (5 each); javascript: 50 fixtures across 10 repos (5
    each). `repo_id` is included (not just `language`, unlike
    sample_fixtures_by_language()'s minimal required shape) so tests can
    check whether fixtures from the same repo get split across the
    sample boundary -- the core new behavior fixture-level sampling adds
    over the old whole-repo approach."""
    fixtures = []
    for i in range(100):
        fixtures.append({"fixture_id": i, "language": "python", "repo_id": i // 10})
    for i in range(100, 150):
        fixtures.append({"fixture_id": i, "language": "java", "repo_id": 1000 + i // 5})
    for i in range(150, 200):
        fixtures.append(
            {"fixture_id": i, "language": "javascript", "repo_id": 2000 + i // 5}
        )
    return fixtures


class TestSampleFixturesByLanguage:
    def test_reproducible_with_same_seed(self):
        fixtures = _make_language_fixtures()
        r1 = sample_fixtures_by_language(fixtures, {"python": 40, "java": 20}, seed=7)
        r2 = sample_fixtures_by_language(fixtures, {"python": 40, "java": 20}, seed=7)
        assert r1.sampled_fixture_ids == r2.sampled_fixture_ids
        assert r1.sampled_fixture_count == r2.sampled_fixture_count

    def test_default_seed_is_the_project_wide_constant(self):
        fixtures = _make_language_fixtures()
        default = sample_fixtures_by_language(fixtures, {"python": 40})
        explicit = sample_fixtures_by_language(
            fixtures, {"python": 40}, seed=DATASET_C_SAMPLING_SEED
        )
        assert default.random_seed == DATASET_C_SAMPLING_SEED
        assert default.sampled_fixture_ids == explicit.sampled_fixture_ids

    def test_samples_exact_target_count_per_language(self):
        """Unlike whole-repo sampling (only ever approximately reaches a
        target, since repos are indivisible chunks), fixture-level
        sampling must hit each language's target exactly whenever enough
        fixtures exist for it."""
        fixtures = _make_language_fixtures()
        result = sample_fixtures_by_language(
            fixtures, {"python": 37, "java": 12, "javascript": 50}, seed=1
        )

        assert result.distribution_check["python"]["sampled_count"] == 37
        assert result.distribution_check["java"]["sampled_count"] == 12
        assert result.distribution_check["javascript"]["sampled_count"] == 50
        assert result.sampled_fixture_count == 37 + 12 + 50

    def test_can_split_fixtures_from_the_same_repo(self):
        """The whole point of the change: unlike whole-repo sampling, two
        fixtures from the same repo can land on opposite sides of the
        sample -- a repo is never all-or-nothing here."""
        fixtures = [
            {"fixture_id": 1, "language": "python", "repo_id": 5},
            {"fixture_id": 2, "language": "python", "repo_id": 5},
            {"fixture_id": 3, "language": "python", "repo_id": 5},
        ]

        result = sample_fixtures_by_language(fixtures, {"python": 2}, seed=1)

        assert result.sampled_fixture_count == 2
        assert len(set(result.sampled_fixture_ids)) == 2
        assert len(result.sampled_fixture_ids) < 3  # not the whole repo

    def test_shortfall_takes_everything_available_and_flags_it(self):
        """java only has 50 fixtures in the population -- asking for 500
        must take all 50 (never fail, never silently under-fill without
        saying so) and flag the shortfall."""
        fixtures = _make_language_fixtures()

        result = sample_fixtures_by_language(fixtures, {"java": 500}, seed=2)

        assert result.distribution_check["java"]["sampled_count"] == 50
        assert result.distribution_check["java"]["available_count"] == 50
        assert result.distribution_check["java"]["shortfall"] is True
        java_ids = {f["fixture_id"] for f in fixtures if f["language"] == "java"}
        assert set(result.sampled_fixture_ids) == java_ids

    def test_no_shortfall_flagged_when_target_exactly_met(self):
        fixtures = _make_language_fixtures()  # javascript has exactly 50

        result = sample_fixtures_by_language(fixtures, {"javascript": 50}, seed=1)

        assert result.distribution_check["javascript"]["shortfall"] is False
        assert result.distribution_check["javascript"]["sampled_count"] == 50

    def test_language_absent_from_target_gets_zero(self):
        """A language present in the population but not named in
        target_counts must contribute nothing to the sample -- matching
        another dataset's mix means not representing a language it has
        none of."""
        fixtures = _make_language_fixtures()

        result = sample_fixtures_by_language(fixtures, {"python": 10}, seed=1)

        java_ids = {f["fixture_id"] for f in fixtures if f["language"] == "java"}
        assert not (java_ids & set(result.sampled_fixture_ids))
        assert "java" not in result.distribution_check

    def test_target_language_absent_from_population_takes_all_zero_available(self):
        """target_counts naming a language the fixture pool simply doesn't
        have must not crash -- 0 available, shortfall flagged, 0
        sampled."""
        fixtures = _make_language_fixtures()

        result = sample_fixtures_by_language(fixtures, {"ruby": 10}, seed=1)

        assert result.distribution_check["ruby"] == {
            "target_count": 10,
            "available_count": 0,
            "sampled_count": 0,
            "shortfall": True,
        }
        assert result.sampled_fixture_ids == []

    def test_each_language_sampled_independently_shortfall_does_not_spread(self):
        """Unlike the old whole-repo sampler's cross-language shortfall
        redistribution, a shortfall in one language must not change
        another language's sampled count at all."""
        fixtures = _make_language_fixtures()

        result = sample_fixtures_by_language(
            fixtures, {"java": 500, "python": 40}, seed=1
        )

        assert result.distribution_check["java"]["shortfall"] is True
        assert result.distribution_check["python"]["shortfall"] is False
        assert result.distribution_check["python"]["sampled_count"] == 40

    def test_raises_on_empty_fixture_list(self):
        with pytest.raises(ValueError, match="empty"):
            sample_fixtures_by_language([], {"python": 10})

    def test_target_count_is_sum_of_all_language_targets(self):
        fixtures = _make_language_fixtures()

        result = sample_fixtures_by_language(
            fixtures, {"python": 40, "java": 20, "javascript": 10}, seed=1
        )

        assert result.target_count == 70
