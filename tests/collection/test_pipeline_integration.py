"""Integration tests for the Dataset C proportional sampling pipeline.

Tests the end-to-end flow: proportions → sampling → CSV loading → format validation.
Uses real fixtures-from-agents and github-search-classified data to verify correctness.

IMPORTANT: fixtures-from-agents/ is real research data. Tests MUST NOT write to it.
All test outputs go to temporary directories.
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

from collection.compute_agent_proportions import compute_proportions
from collection.human_corpus import load_dataset_c_repos
from collection.sample_proportional_repos import (
    sample_proportional,
    write_per_language_files,
)

# ---------------------------------------------------------------------------
# Full pipeline integration: real data
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end integration tests using real project data."""

    @classmethod
    def _project_root(cls) -> Path:
        return _PROJECT_ROOT

    def test_compute_proportions_from_real_data(self):
        """Proportions computed from real Dataset A repos are valid."""
        self._project_root()
        result = compute_proportions()

        # Global
        gl = result["global"]
        assert gl["total_repos"] > 0
        assert abs(sum(gl["proportions"].values()) - 1.0) < 0.01
        assert all(0 <= p <= 1 for p in gl["proportions"].values())
        assert set(gl["domain_counts"].keys()) == set(gl["proportions"].keys())

        # Per-language
        for _lang, info in result["per_language"].items():
            assert info["total_repos"] > 0
            assert info["classified"] + info["unknown"] == info["total_repos"]
            if info["classified"] > 0:
                assert abs(sum(info["proportions"].values()) - 1.0) < 0.01

    def test_json_output_is_valid(self):
        """category_proportions.json is valid."""
        pr = self._project_root()
        json_path = pr / "fixtures-from-agents" / "category_proportions.json"
        assert json_path.exists(), "Run compute_agent_proportions first"

        with open(json_path) as f:
            data = json.load(f)

        assert "global" in data
        assert "per_language" in data
        assert len(data["per_language"]) == 4  # java, javascript, python, typescript

        for lang in ["java", "javascript", "python", "typescript"]:
            assert lang in data["per_language"]
            assert data["per_language"][lang]["total_repos"] > 0

    def test_dataset_c_sample_is_valid(self):
        """dataset_c_sample.csv has correct format and content."""
        pr = self._project_root()
        prop_path = pr / "fixtures-from-agents" / "category_proportions.json"
        if not prop_path.exists():
            pytest.skip("category_proportions.json not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sampled = sample_proportional(
                proportions_path=prop_path, target_per_language=5, seed=42
            )
            write_per_language_files(sampled, out_dir)
            csv_path = out_dir / "dataset_c_sample.csv"
            assert csv_path.exists()

            with open(csv_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) > 0

            for row in rows:
                assert "repo_name" in row
                assert "language" in row
                assert "domain" in row
                assert "clone_url" in row
                assert "/" in row["repo_name"]
                assert " " not in row["repo_name"]
                assert row["language"].lower() in {
                    "python", "java", "javascript", "typescript",
                }
                assert row["domain"] in {"web", "library", "data", "infra", "cli", "other"}
                if row["clone_url"]:
                    assert row["clone_url"].startswith("https://github.com/")
                    assert row["clone_url"].endswith(".git")

    def test_load_dataset_c_repos_format(self):
        """load_dataset_c_repos produces correct format for collect_dataset_c_fixtures()."""
        pr = self._project_root()
        prop_path = pr / "fixtures-from-agents" / "category_proportions.json"
        if not prop_path.exists():
            pytest.skip("category_proportions.json not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sampled = sample_proportional(
                proportions_path=prop_path, target_per_language=5, seed=42
            )
            write_per_language_files(sampled, out_dir)
            csv_path = out_dir / "dataset_c_sample.csv"

            repos = load_dataset_c_repos(csv_path)
            assert len(repos) > 0

            for repo in repos:
                assert "full_name" in repo
                assert "language" in repo
                assert "clone_url" in repo
                assert "/" in repo["full_name"]
                assert repo["clone_url"].endswith(".git")

    def test_proportions_match_dataset_c_domains(self):
        """Dataset C domain proportions approximate Dataset A proportions."""
        pr = self._project_root()
        json_path = pr / "fixtures-from-agents" / "category_proportions.json"

        if not json_path.exists():
            pytest.skip("category_proportions.json not found")

        with open(json_path) as f:
            proportions = json.load(f)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sampled = sample_proportional(
                proportions_path=json_path, target_per_language=10, seed=42
            )
            write_per_language_files(sampled, out_dir)
            csv_path = out_dir / "dataset_c_sample.csv"

            with open(csv_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            dc_counts: dict[str, int] = {}
            for row in rows:
                d = row["domain"]
                dc_counts[d] = dc_counts.get(d, 0) + 1

            total = sum(dc_counts.values())
            da_props = proportions["global"]["proportions"]

            for domain, target in da_props.items():
                actual = dc_counts.get(domain, 0) / total
                assert (
                    abs(actual - target) < 0.10
                ), f"Domain {domain}: target={target:.1%}, actual={actual:.1%}"

    def test_all_dataset_c_repos_have_classification(self):
        """Every repo in dataset_c_sample.csv has a domain classification."""
        pr = self._project_root()
        prop_path = pr / "fixtures-from-agents" / "category_proportions.json"
        labeled_dir = pr / "github-search-classified" / "openai_gpt-4o-mini"

        if not prop_path.exists():
            pytest.skip("category_proportions.json not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sampled = sample_proportional(
                proportions_path=prop_path, target_per_language=5, seed=42
            )
            write_per_language_files(sampled, out_dir)
            csv_path = out_dir / "dataset_c_sample.csv"

            class_map: dict[str, str] = {}
            for lcsv in labeled_dir.glob("*.csv"):
                with open(lcsv, encoding="utf-8", newline="") as f:
                    for row in csv.DictReader(f):
                        name = (row.get("name") or "").strip()
                        domain = (row.get("domain") or "").strip()
                        if name and domain:
                            class_map[name] = domain

            with open(csv_path, encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            missing = 0
            for row in rows:
                name = row["repo_name"]
                if name not in class_map:
                    missing += 1

            assert (
                missing < len(rows) * 0.02
            ), f"{missing}/{len(rows)} repos missing classification"

    def test_no_overlap_dataset_a_and_c(self):
        """Dataset A and Dataset C should have no overlapping repos."""
        pr = self._project_root()
        prop_path = pr / "fixtures-from-agents" / "category_proportions.json"
        repos_dir = pr / "fixtures-from-agents" / "repos"

        if not prop_path.exists():
            pytest.skip("category_proportions.json not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sampled = sample_proportional(
                proportions_path=prop_path, target_per_language=5, seed=42
            )
            write_per_language_files(sampled, out_dir)
            csv_c = out_dir / "dataset_c_sample.csv"

            a_names: set[str] = set()
            for repo_csv in repos_dir.glob("*_agent_fixture_repos.csv"):
                with open(repo_csv, encoding="utf-8", newline="") as f:
                    for row in csv.DictReader(f):
                        name = (row.get("repo_name") or "").strip()
                        if name:
                            a_names.add(name)

            c_names: set[str] = set()
            with open(csv_c, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    name = (row.get("repo_name") or "").strip()
                    if name:
                        c_names.add(name)

            overlap = a_names & c_names
            assert (
                len(overlap) < 20
            ), f"Unexpectedly large overlap between Dataset A and C: {overlap}"


# ---------------------------------------------------------------------------
# Integration with pre-cutoff filtering
# ---------------------------------------------------------------------------


class TestPreCutoffIntegration:
    """Tests that pre-2021 filtering works with real data."""

    @classmethod
    def _project_root(cls) -> Path:
        return _PROJECT_ROOT

    def test_all_dataset_c_repos_are_pre_cutoff(self):
        """Every repo in dataset_c_sample.csv should be created before 2021."""
        import gzip

        pr = self._project_root()
        prop_path = pr / "fixtures-from-agents" / "category_proportions.json"
        raw_dir = pr / "github-search-raw"
        cutoff = "2020-12-31"

        if not prop_path.exists():
            pytest.skip("category_proportions.json not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sampled = sample_proportional(
                proportions_path=prop_path, target_per_language=5, seed=42
            )
            write_per_language_files(sampled, out_dir)
            csv_path = out_dir / "dataset_c_sample.csv"

            created_map: dict[str, str] = {}
            for gz_path in raw_dir.glob("*.csv.gz"):
                with gzip.open(gz_path, "rt", encoding="utf-8", newline="") as f:
                    for row in csv.DictReader(f):
                        name = (row.get("name") or "").strip()
                        created = (row.get("createdAt") or "").strip()
                        if name and created:
                            created_map[name] = created[:10]

            with open(csv_path, encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            post_cutoff = []
            for row in rows:
                name = row["repo_name"]
                created = created_map.get(name, "")
                if created and created > cutoff:
                    post_cutoff.append(f"{name} ({created})")

            assert len(post_cutoff) == 0, f"Repos created after cutoff: {post_cutoff}"
            name = row["repo_name"]
            created = created_map.get(name, "")
            if created and created > cutoff:
                post_cutoff.append(f"{name} ({created})")

        assert len(post_cutoff) == 0, f"Repos created after cutoff: {post_cutoff}"


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


class TestReproducibility:
    """Sampling is reproducible with the same seed."""

    @classmethod
    def _project_root(cls) -> Path:
        return _PROJECT_ROOT

    def test_sampling_reproducible(self):
        """Same seed produces identical samples from real data."""
        pr = self._project_root()
        prop_path = pr / "fixtures-from-agents" / "category_proportions.json"
        if not prop_path.exists():
            pytest.skip("category_proportions.json not found")

        s1 = sample_proportional(
            proportions_path=prop_path, target_per_language=10, seed=42
        )
        s2 = sample_proportional(
            proportions_path=prop_path, target_per_language=10, seed=42
        )

        names1 = {r["repo_name"] for r in s1}
        names2 = {r["repo_name"] for r in s2}
        assert names1 == names2
        assert len(names1) >= 30  # ~10 per language × 4 languages, minus missing pools

    def test_different_seeds_different(self):
        """Different seeds produce different samples."""
        pr = self._project_root()
        prop_path = pr / "fixtures-from-agents" / "category_proportions.json"
        if not prop_path.exists():
            pytest.skip("category_proportions.json not found")

        s1 = sample_proportional(
            proportions_path=prop_path, target_per_language=10, seed=42
        )
        s2 = sample_proportional(
            proportions_path=prop_path, target_per_language=10, seed=99
        )

        names1 = {r["repo_name"] for r in s1}
        names2 = {r["repo_name"] for r in s2}
        assert names1 != names2
