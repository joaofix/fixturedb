"""Unit tests for compute_agent_proportions and sample_proportional_repos."""

from __future__ import annotations

import csv
import gzip
import json
import random
from pathlib import Path

import pytest

from collection.compute_agent_proportions import (
    _load_agent_repos,
    _load_classification_map,
    compute_proportions,
)
from collection.config import DATASET_C_SAMPLING_SEED
from collection.sample_proportional_repos import (
    _assign_domains,
    _load_pre_cutoff_repos,
    sample_proportional,
    write_per_language_files,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_gz_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# compute_agent_proportions tests
# ---------------------------------------------------------------------------


class TestLoadClassificationMap:
    def test_single_file(self, tmp_path):
        _write_csv(
            tmp_path / "python.csv",
            [
                {
                    "name": "owner/a",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                },
                {
                    "name": "owner/b",
                    "mainLanguage": "Python",
                    "domain": "library",
                    "confidence": "high",
                    "reasoning": "x",
                },
            ],
        )
        mapping = _load_classification_map(tmp_path)
        assert mapping == {"owner/a": "web", "owner/b": "library"}

    def test_multiple_files(self, tmp_path):
        _write_csv(
            tmp_path / "python.csv",
            [
                {
                    "name": "owner/py",
                    "mainLanguage": "Python",
                    "domain": "data",
                    "confidence": "high",
                    "reasoning": "x",
                }
            ],
        )
        _write_csv(
            tmp_path / "java.csv",
            [
                {
                    "name": "owner/jv",
                    "mainLanguage": "Java",
                    "domain": "library",
                    "confidence": "high",
                    "reasoning": "x",
                }
            ],
        )
        mapping = _load_classification_map(tmp_path)
        assert mapping == {"owner/py": "data", "owner/jv": "library"}

    def test_skips_empty_name(self, tmp_path):
        _write_csv(
            tmp_path / "python.csv",
            [
                {
                    "name": "",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                },
                {
                    "name": "owner/valid",
                    "mainLanguage": "Python",
                    "domain": "cli",
                    "confidence": "high",
                    "reasoning": "x",
                },
            ],
        )
        mapping = _load_classification_map(tmp_path)
        assert mapping == {"owner/valid": "cli"}


class TestLoadAgentRepos:
    def test_single_language(self, tmp_path):
        _write_csv(
            tmp_path / "python_agent_fixture_repos.csv",
            [
                {
                    "repo_name": "owner/a",
                    "language": "python",
                    "fixture_count": "5",
                    "commit_count_with_fixtures": "2",
                    "first_fixture_commit": "abc",
                    "last_fixture_commit": "def",
                    "clone_url": "url",
                },
                {
                    "repo_name": "owner/b",
                    "language": "python",
                    "fixture_count": "3",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "abc",
                    "last_fixture_commit": "def",
                    "clone_url": "url",
                },
            ],
        )
        by_lang = _load_agent_repos(tmp_path)
        assert by_lang == {"python": ["owner/a", "owner/b"]}

    def test_multiple_languages(self, tmp_path):
        _write_csv(
            tmp_path / "python_agent_fixture_repos.csv",
            [
                {
                    "repo_name": "owner/py",
                    "language": "python",
                    "fixture_count": "1",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                }
            ],
        )
        _write_csv(
            tmp_path / "java_agent_fixture_repos.csv",
            [
                {
                    "repo_name": "owner/jv",
                    "language": "java",
                    "fixture_count": "1",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                }
            ],
        )
        by_lang = _load_agent_repos(tmp_path)
        assert set(by_lang.keys()) == {"python", "java"}
        assert by_lang["python"] == ["owner/py"]
        assert by_lang["java"] == ["owner/jv"]

    def test_skips_empty_name(self, tmp_path):
        _write_csv(
            tmp_path / "python_agent_fixture_repos.csv",
            [
                {
                    "repo_name": "",
                    "language": "python",
                    "fixture_count": "1",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
                {
                    "repo_name": "owner/valid",
                    "language": "python",
                    "fixture_count": "1",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
            ],
        )
        by_lang = _load_agent_repos(tmp_path)
        assert by_lang == {"python": ["owner/valid"]}


class TestComputeProportions:
    def test_basic(self, tmp_path):
        repos_dir = tmp_path / "repos"
        classified_dir = tmp_path / "classified"

        _write_csv(
            repos_dir / "python_agent_fixture_repos.csv",
            [
                {
                    "repo_name": "owner/a",
                    "language": "python",
                    "fixture_count": "5",
                    "commit_count_with_fixtures": "2",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
                {
                    "repo_name": "owner/b",
                    "language": "python",
                    "fixture_count": "3",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
                {
                    "repo_name": "owner/c",
                    "language": "python",
                    "fixture_count": "2",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
            ],
        )
        _write_csv(
            repos_dir / "java_agent_fixture_repos.csv",
            [
                {
                    "repo_name": "owner/d",
                    "language": "java",
                    "fixture_count": "4",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
            ],
        )

        _write_csv(
            classified_dir / "python.csv",
            [
                {
                    "name": "owner/a",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                },
                {
                    "name": "owner/b",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                },
                {
                    "name": "owner/c",
                    "mainLanguage": "Python",
                    "domain": "data",
                    "confidence": "high",
                    "reasoning": "x",
                },
            ],
        )
        _write_csv(
            classified_dir / "java.csv",
            [
                {
                    "name": "owner/d",
                    "mainLanguage": "Java",
                    "domain": "library",
                    "confidence": "high",
                    "reasoning": "x",
                },
            ],
        )

        result = compute_proportions(repos_dir, classified_dir)

        # Python: 2 web, 1 data → 0.6667 web, 0.3333 data
        py = result["per_language"]["python"]
        assert py["total_repos"] == 3
        assert py["proportions"]["web"] == pytest.approx(2 / 3, abs=0.01)
        assert py["proportions"]["data"] == pytest.approx(1 / 3, abs=0.01)

        # Java: 1 library → 1.0 library
        jv = result["per_language"]["java"]
        assert jv["total_repos"] == 1
        assert jv["proportions"]["library"] == 1.0

        # Global: 2 web, 1 data, 1 library
        gl = result["global"]
        assert gl["total_repos"] == 4
        assert gl["proportions"]["web"] == 0.5
        assert gl["proportions"]["data"] == 0.25
        assert gl["proportions"]["library"] == 0.25

    def test_unknown_domain_handled(self, tmp_path):
        """Repos not in classification map should be counted as unknown."""
        repos_dir = tmp_path / "repos"
        classified_dir = tmp_path / "classified"

        _write_csv(
            repos_dir / "python_agent_fixture_repos.csv",
            [
                {
                    "repo_name": "owner/known",
                    "language": "python",
                    "fixture_count": "1",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
                {
                    "repo_name": "owner/unknown",
                    "language": "python",
                    "fixture_count": "1",
                    "commit_count_with_fixtures": "1",
                    "first_fixture_commit": "a",
                    "last_fixture_commit": "b",
                    "clone_url": "url",
                },
            ],
        )
        _write_csv(
            classified_dir / "python.csv",
            [
                {
                    "name": "owner/known",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                },
            ],
        )

        result = compute_proportions(repos_dir, classified_dir)
        py = result["per_language"]["python"]
        assert py["total_repos"] == 2
        assert py["classified"] == 1
        assert py["unknown"] == 1
        # Proportions are computed from total repos (2), so web = 1/2 = 0.5
        assert py["proportions"]["web"] == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# sample_proportional_repos tests
# ---------------------------------------------------------------------------


class TestLoadPreCutoffRepos:
    def test_filters_by_date(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "owner/old",
                    "mainLanguage": "Python",
                    "createdAt": "2019-06-15T00:00:00",
                    "clone_url": "url1",
                },
                {
                    "name": "owner/new",
                    "mainLanguage": "Python",
                    "createdAt": "2022-03-01T00:00:00",
                    "clone_url": "url2",
                },
            ],
        )

        by_lang = _load_pre_cutoff_repos(tmp_path, "2020-12-31")
        repos = by_lang["python"]["__all__"]
        names = {r["repo_name"] for r in repos}
        assert names == {"owner/old"}
        assert "owner/new" not in names

    def test_no_date_skipped(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "owner/nodate",
                    "mainLanguage": "Python",
                    "createdAt": "",
                    "clone_url": "url",
                },
                {
                    "name": "owner/hasdate",
                    "mainLanguage": "Python",
                    "createdAt": "2018-01-01T00:00:00",
                    "clone_url": "url",
                },
            ],
        )

        by_lang = _load_pre_cutoff_repos(tmp_path, "2020-12-31")
        repos = by_lang["python"]["__all__"]
        names = {r["repo_name"] for r in repos}
        assert names == {"owner/hasdate"}

    def test_invalid_name_skipped(self, tmp_path):
        _write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "",
                    "mainLanguage": "Python",
                    "createdAt": "2019-01-01T00:00:00",
                    "clone_url": "url",
                },
                {
                    "name": "no-slash",
                    "mainLanguage": "Python",
                    "createdAt": "2019-01-01T00:00:00",
                    "clone_url": "url",
                },
                {
                    "name": "owner/valid",
                    "mainLanguage": "Python",
                    "createdAt": "2019-01-01T00:00:00",
                    "clone_url": "url",
                },
            ],
        )

        by_lang = _load_pre_cutoff_repos(tmp_path, "2020-12-31")
        repos = by_lang["python"]["__all__"]
        assert len(repos) == 1
        assert repos[0]["repo_name"] == "owner/valid"


class TestAssignDomains:
    def test_groups_by_domain(self, tmp_path):
        by_lang = {
            "python": {
                "__all__": [
                    {"repo_name": "owner/a", "language": "python", "clone_url": "url1"},
                    {"repo_name": "owner/b", "language": "python", "clone_url": "url2"},
                    {"repo_name": "owner/c", "language": "python", "clone_url": "url3"},
                ]
            }
        }
        classification = {"owner/a": "web", "owner/b": "web", "owner/c": "data"}

        result = _assign_domains(by_lang, classification)
        assert len(result["python"]["web"]) == 2
        assert len(result["python"]["data"]) == 1

    def test_unknown_domain_defaults_to_other(self, tmp_path):
        by_lang = {
            "python": {
                "__all__": [
                    {"repo_name": "owner/x", "language": "python", "clone_url": "url"},
                ]
            }
        }
        classification = {}  # empty

        result = _assign_domains(by_lang, classification)
        assert len(result["python"]["other"]) == 1


class TestSampleProportional:
    def _setup_fixtures(self, tmp_path):
        """Create minimal proportions, raw data, and classification files."""
        proportions_dir = tmp_path / "proportions"
        raw_dir = tmp_path / "raw"
        classified_dir = tmp_path / "classified"

        # Proportions: python = 60% web, 40% data
        proportions = {
            "global": {
                "total_repos": 5,
                "domain_counts": {"web": 3, "data": 2},
                "proportions": {"web": 0.6, "data": 0.4},
            },
            "per_language": {
                "python": {
                    "total_repos": 5,
                    "classified": 5,
                    "unknown": 0,
                    "domain_counts": {"web": 3, "data": 2},
                    "proportions": {"web": 0.6, "data": 0.4},
                }
            },
        }
        proportions_dir.mkdir(parents=True)
        with open(proportions_dir / "category_proportions.json", "w") as f:
            json.dump(proportions, f)

        # Raw repos: 50 web, 50 data, all pre-2021
        web_rows = [
            {
                "name": f"owner/web{i}",
                "mainLanguage": "Python",
                "createdAt": "2019-01-01T00:00:00",
                "clone_url": f"url_w{i}",
            }
            for i in range(50)
        ]
        data_rows = [
            {
                "name": f"owner/data{i}",
                "mainLanguage": "Python",
                "createdAt": "2019-01-01T00:00:00",
                "clone_url": f"url_d{i}",
            }
            for i in range(50)
        ]
        _write_gz_csv(raw_dir / "python.csv.gz", web_rows + data_rows)

        # Classification: all web repos → web, all data repos → data
        class_rows = []
        for i in range(50):
            class_rows.append(
                {
                    "name": f"owner/web{i}",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                }
            )
            class_rows.append(
                {
                    "name": f"owner/data{i}",
                    "mainLanguage": "Python",
                    "domain": "data",
                    "confidence": "high",
                    "reasoning": "x",
                }
            )
        _write_csv(classified_dir / "python.csv", class_rows)

        return proportions_dir / "category_proportions.json", raw_dir, classified_dir

    def test_proportional_sampling(self, tmp_path):
        prop_path, raw_dir, classified_dir = self._setup_fixtures(tmp_path)

        sampled = sample_proportional(
            proportions_path=prop_path,
            raw_dir=raw_dir,
            classified_dir=classified_dir,
            target_per_language=10,
            seed=42,
        )

        # target=10, over-sample=1.2 → 12. web=0.6*12=7.2→7, data=0.4*12=4.8→5
        web_count = sum(1 for r in sampled if r["domain"] == "web")
        data_count = sum(1 for r in sampled if r["domain"] == "data")

        assert web_count + data_count == len(sampled)
        # With over-sample, should be around 12
        assert 10 <= len(sampled) <= 14
        # Proportions should be roughly 60/40
        assert web_count >= data_count

    def test_reproducible_with_seed(self, tmp_path):
        prop_path, raw_dir, classified_dir = self._setup_fixtures(tmp_path)

        s1 = sample_proportional(
            prop_path, raw_dir, classified_dir, target_per_language=10, seed=42
        )
        s2 = sample_proportional(
            prop_path, raw_dir, classified_dir, target_per_language=10, seed=42
        )

        names1 = {r["repo_name"] for r in s1}
        names2 = {r["repo_name"] for r in s2}
        assert names1 == names2

    def test_different_seeds_different_samples(self, tmp_path):
        prop_path, raw_dir, classified_dir = self._setup_fixtures(tmp_path)

        s1 = sample_proportional(
            prop_path, raw_dir, classified_dir, target_per_language=10, seed=42
        )
        s2 = sample_proportional(
            prop_path, raw_dir, classified_dir, target_per_language=10, seed=99
        )

        names1 = {r["repo_name"] for r in s1}
        names2 = {r["repo_name"] for r in s2}
        # Very unlikely to be identical with 50+ repos per domain
        assert names1 != names2

    def test_output_has_required_fields(self, tmp_path):
        prop_path, raw_dir, classified_dir = self._setup_fixtures(tmp_path)

        sampled = sample_proportional(
            prop_path, raw_dir, classified_dir, target_per_language=5, seed=42
        )

        for repo in sampled:
            assert "repo_name" in repo
            assert "language" in repo
            assert "domain" in repo
            assert "clone_url" in repo
            assert "/" in repo["repo_name"]

    def test_handles_missing_domain_pool(self, tmp_path):
        """If a domain has no available repos, it gets 0 for that domain."""
        proportions_dir = tmp_path / "proportions"
        raw_dir = tmp_path / "raw"
        classified_dir = tmp_path / "classified"

        proportions = {
            "global": {
                "total_repos": 1,
                "domain_counts": {"web": 1},
                "proportions": {"web": 1.0},
            },
            "per_language": {
                "python": {
                    "total_repos": 1,
                    "classified": 1,
                    "unknown": 0,
                    "domain_counts": {"web": 1},
                    "proportions": {"web": 1.0},
                }
            },
        }
        proportions_dir.mkdir(parents=True)
        with open(proportions_dir / "category_proportions.json", "w") as f:
            json.dump(proportions, f)

        # Only data repos available, no web repos
        _write_gz_csv(
            raw_dir / "python.csv.gz",
            [
                {
                    "name": f"owner/data{i}",
                    "mainLanguage": "Python",
                    "createdAt": "2019-01-01T00:00:00",
                    "clone_url": f"url{i}",
                }
                for i in range(5)
            ],
        )
        _write_csv(
            classified_dir / "python.csv",
            [
                {
                    "name": f"owner/data{i}",
                    "mainLanguage": "Python",
                    "domain": "data",
                    "confidence": "high",
                    "reasoning": "x",
                }
                for i in range(5)
            ],
        )

        sampled = sample_proportional(
            proportions_path=proportions_dir / "category_proportions.json",
            raw_dir=raw_dir,
            classified_dir=classified_dir,
            target_per_language=10,
            seed=42,
        )

        # No web repos available → 0 sampled. This is expected — the warning
        # is logged and the script continues without crashing.
        assert len(sampled) == 0


# ---------------------------------------------------------------------------
# write_per_language_files
# ---------------------------------------------------------------------------


class TestWritePerLanguageFiles:
    def test_writes_per_language_and_combined(self, tmp_path):
        sampled = [
            {
                "repo_name": "owner/py1",
                "language": "python",
                "domain": "data",
                "clone_url": "url1",
            },
            {
                "repo_name": "owner/py2",
                "language": "python",
                "domain": "web",
                "clone_url": "url2",
            },
            {
                "repo_name": "owner/jv1",
                "language": "java",
                "domain": "library",
                "clone_url": "url3",
            },
        ]

        counts = write_per_language_files(sampled, tmp_path)

        assert counts == {"java": 1, "python": 2}

        py_csv = tmp_path / "dataset_c_python.csv"
        jv_csv = tmp_path / "dataset_c_java.csv"
        combined = tmp_path / "dataset_c_sample.csv"

        assert py_csv.exists()
        assert jv_csv.exists()
        assert combined.exists()

        py_lines = py_csv.read_text().strip().split("\n")
        assert len(py_lines) == 3  # header + 2

        jv_lines = jv_csv.read_text().strip().split("\n")
        assert len(jv_lines) == 2  # header + 1

        comb_lines = combined.read_text().strip().split("\n")
        assert len(comb_lines) == 4  # header + 3

    def test_empty_sampled(self, tmp_path):
        counts = write_per_language_files([], tmp_path)
        assert counts == {}
        assert (tmp_path / "dataset_c_sample.csv").exists()


# ---------------------------------------------------------------------------
# Seed configuration
# ---------------------------------------------------------------------------


class TestSeedConfiguration:
    def test_config_seed_is_integer(self):
        """DATASET_C_SAMPLING_SEED should be an integer."""
        assert isinstance(DATASET_C_SAMPLING_SEED, int)
        assert DATASET_C_SAMPLING_SEED > 0

    def test_default_seed_matches_hardcoded_default(self):
        """Config default should match original hardcoded values (42)."""
        assert DATASET_C_SAMPLING_SEED == 42

    def test_uses_local_rng_not_global(self, tmp_path):
        """sample_proportional should use local RNG to avoid global state pollution."""
        prop_path, raw_dir, classified_dir = TestSampleProportional()._setup_fixtures(
            tmp_path
        )

        # Set a known global seed
        random.seed(12345)
        state_before = random.getstate()

        sampled = sample_proportional(
            proportions_path=prop_path,
            raw_dir=raw_dir,
            classified_dir=classified_dir,
            target_per_language=5,
            seed=999,
        )

        # Global state should be unchanged
        state_after = random.getstate()
        assert state_before == state_after

        # But sampling should still work
        assert len(sampled) >= 0

    def test_seed_propagates_to_cli_default(self, tmp_path):
        """CLI --seed default should come from config."""
        prop_path, raw_dir, classified_dir = TestSampleProportional()._setup_fixtures(
            tmp_path
        )

        # Run without explicit seed - should use DATASET_C_SAMPLING_SEED
        s1 = sample_proportional(
            prop_path, raw_dir, classified_dir, target_per_language=10
        )

        # Run with explicit seed matching config
        s2 = sample_proportional(
            prop_path,
            raw_dir,
            classified_dir,
            target_per_language=10,
            seed=DATASET_C_SAMPLING_SEED,
        )

        # Should produce identical results
        names1 = {r["repo_name"] for r in s1}
        names2 = {r["repo_name"] for r in s2}
        assert names1 == names2


class TestSamplingEdgeCases:
    """Edge case tests for proportional sampling robustness."""

    def _setup_fixtures(self, tmp_path):
        """Create minimal proportions, raw data, and classification files."""
        proportions_dir = tmp_path / "proportions"
        raw_dir = tmp_path / "raw"
        classified_dir = tmp_path / "classified"

        proportions = {
            "global": {
                "total_repos": 5,
                "domain_counts": {"web": 3, "data": 2},
                "proportions": {"web": 0.6, "data": 0.4},
            },
            "per_language": {
                "python": {
                    "total_repos": 5,
                    "classified": 5,
                    "unknown": 0,
                    "domain_counts": {"web": 3, "data": 2},
                    "proportions": {"web": 0.6, "data": 0.4},
                }
            },
        }
        proportions_dir.mkdir(parents=True)
        with open(proportions_dir / "category_proportions.json", "w") as f:
            json.dump(proportions, f)

        web_rows = [
            {
                "name": f"owner/web{i}",
                "mainLanguage": "Python",
                "createdAt": "2019-01-01T00:00:00",
                "clone_url": f"url_w{i}",
            }
            for i in range(50)
        ]
        data_rows = [
            {
                "name": f"owner/data{i}",
                "mainLanguage": "Python",
                "createdAt": "2019-01-01T00:00:00",
                "clone_url": f"url_d{i}",
            }
            for i in range(50)
        ]
        _write_gz_csv(raw_dir / "python.csv.gz", web_rows + data_rows)

        class_rows = []
        for i in range(50):
            class_rows.append(
                {
                    "name": f"owner/web{i}",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                }
            )
            class_rows.append(
                {
                    "name": f"owner/data{i}",
                    "mainLanguage": "Python",
                    "domain": "data",
                    "confidence": "high",
                    "reasoning": "x",
                }
            )
        _write_csv(classified_dir / "python.csv", class_rows)

        return proportions_dir / "category_proportions.json", raw_dir, classified_dir

    def test_zero_target_returns_minimum_one_per_domain(self, tmp_path):
        """Zero target still returns minimum 1 per domain due to max(1, ...) guarantee."""
        prop_path, raw_dir, classified_dir = self._setup_fixtures(tmp_path)

        sampled = sample_proportional(
            proportions_path=prop_path,
            raw_dir=raw_dir,
            classified_dir=classified_dir,
            target_per_language=0,
            seed=42,
        )
        # With target=0, effective=0, but max(1, ...) ensures at least 1 per domain
        assert len(sampled) >= 2  # web + data domains

    def test_small_pool_still_samples(self, tmp_path):
        """When only 1 repo available in a domain, should still sample it."""
        proportions_dir = tmp_path / "proportions"
        raw_dir = tmp_path / "raw"
        classified_dir = tmp_path / "classified"

        proportions = {
            "global": {
                "total_repos": 1,
                "domain_counts": {"web": 1},
                "proportions": {"web": 1.0},
            },
            "per_language": {
                "python": {
                    "total_repos": 1,
                    "classified": 1,
                    "unknown": 0,
                    "domain_counts": {"web": 1},
                    "proportions": {"web": 1.0},
                }
            },
        }
        proportions_dir.mkdir(parents=True)
        with open(proportions_dir / "category_proportions.json", "w") as f:
            json.dump(proportions, f)

        _write_gz_csv(
            raw_dir / "python.csv.gz",
            [
                {
                    "name": "owner/web1",
                    "mainLanguage": "Python",
                    "createdAt": "2019-01-01T00:00:00",
                    "clone_url": "url1",
                }
            ],
        )
        _write_csv(
            classified_dir / "python.csv",
            [
                {
                    "name": "owner/web1",
                    "mainLanguage": "Python",
                    "domain": "web",
                    "confidence": "high",
                    "reasoning": "x",
                }
            ],
        )

        sampled = sample_proportional(
            proportions_path=proportions_dir / "category_proportions.json",
            raw_dir=raw_dir,
            classified_dir=classified_dir,
            target_per_language=1,
            seed=42,
        )
        assert len(sampled) == 1
        assert sampled[0]["repo_name"] == "owner/web1"

    def test_proportion_rounding_respects_over_sample(self, tmp_path):
        """Verify over-sample factor (1.2x) is applied correctly before rounding."""
        prop_path, raw_dir, classified_dir = TestSampleProportional()._setup_fixtures(
            tmp_path
        )

        sampled = sample_proportional(
            prop_path, raw_dir, classified_dir, target_per_language=10, seed=42
        )

        # target=10, over-sample=1.2 → 12. web=0.6*12=7.2→7, data=0.4*12=4.8→5
        assert len(sampled) == 12


# ---------------------------------------------------------------------------
# Classification output directory tests
# ---------------------------------------------------------------------------


class TestClassificationOutputDir:
    """Tests for model-specific classification output structure."""

    def test_classify_output_dir_uses_model_subfolder(self):
        """CLASSIFY_OUTPUT_DIR should point to model-specific subfolder."""
        from collection.config import (
            CLASSIFY_CLASSIFIED_DIR,
            CLASSIFY_MODEL_NAME,
            CLASSIFY_OUTPUT_DIR,
        )

        assert CLASSIFY_CLASSIFIED_DIR.name == "github-search-classified"
        assert CLASSIFY_MODEL_NAME == "openai_gpt-4o-mini"
        assert CLASSIFY_OUTPUT_DIR.name == CLASSIFY_MODEL_NAME

    def test_classification_model_env_override(self, monkeypatch):
        """CLASSIFICATION_MODEL should be overridable via environment."""
        monkeypatch.setenv("CLASSIFICATION_MODEL", "test-model")
        # Need to re-import to pick up env var
        import importlib

        import collection.config

        importlib.reload(collection.config)
        assert collection.config.CLASSIFICATION_MODEL == "test-model"

    def test_classify_model_name_env_override(self, monkeypatch):
        """CLASSIFY_MODEL_NAME should be overridable via environment."""
        monkeypatch.setenv("CLASSIFY_MODEL_NAME", "ollama_qwen3-14b")
        import importlib

        import collection.config

        importlib.reload(collection.config)
        assert collection.config.CLASSIFY_OUTPUT_DIR.name == "ollama_qwen3-14b"
