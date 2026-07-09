from collection.dataset_sampler import StratifiedSampler


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
