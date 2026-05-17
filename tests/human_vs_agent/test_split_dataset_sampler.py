"""
Unit tests for FixtureDB split stratified sampling.
"""

from collection.dataset_sampler import StratifiedSampler


class TestStratifiedSampler:
    def test_sample_preserves_ids_and_size(self):
        sampler = StratifiedSampler(random_seed=42)
        fixtures = [
            {"id": 1, "fixture_type": "pytest.fixture"},
            {"id": 2, "fixture_type": "pytest.fixture"},
            {"id": 3, "fixture_type": "unittest.TestCase"},
            {"id": 4, "fixture_type": "unittest.TestCase"},
        ]

        result = sampler.sample(fixtures, target_count=2)

        assert result.sampled_count == 2
        assert len(result.sampled_ids) == 2
        assert result.target_count == 2
        assert result.random_seed == 42

    def test_validate_distribution_reports_tolerance(self):
        sampler = StratifiedSampler(random_seed=42)
        original = [
            {"id": 1, "fixture_type": "pytest.fixture"},
            {"id": 2, "fixture_type": "pytest.fixture"},
            {"id": 3, "fixture_type": "unittest.TestCase"},
            {"id": 4, "fixture_type": "unittest.TestCase"},
        ]
        sampled = [
            {"id": 1, "fixture_type": "pytest.fixture"},
            {"id": 3, "fixture_type": "unittest.TestCase"},
        ]

        stats = sampler._validate_distribution(original, sampled, "fixture_type", 0.02)

        assert set(stats.keys()) == {"pytest.fixture", "unittest.TestCase"}
        assert all("tolerance_met" in value for value in stats.values())

    def test_get_sample_statistics(self):
        sampler = StratifiedSampler(random_seed=42)
        result = sampler.sample(
            [
                {"id": 1, "fixture_type": "pytest.fixture"},
                {"id": 2, "fixture_type": "pytest.fixture"},
                {"id": 3, "fixture_type": "unittest.TestCase"},
                {"id": 4, "fixture_type": "unittest.TestCase"},
            ],
            target_count=2,
        )

        stats = sampler.get_sample_statistics(result)

        assert stats["target_count"] == 2
        assert stats["sampled_count"] == 2
        assert stats["random_seed"] == 42


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
