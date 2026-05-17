"""
Integration tests for the FixtureDB split pipeline.
"""

import sqlite3
import tempfile
from pathlib import Path

from collection.agent_detector import AgentFileScanner
from collection.dataset_exporter import HumanDatasetExporter
from collection.dataset_sampler import StratifiedSampler

from tests.human_vs_agent.test_split_dataset_exporter import _create_export_db


class TestSplitPipelineIntegration:
    def test_detector_sampler_export_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            clones_dir = root / "clones"
            clones_dir.mkdir()
            repo_dir = clones_dir / "repo_1"
            repo_dir.mkdir()
            (repo_dir / ".cursorrules").touch()

            scanner = AgentFileScanner(clones_dir=clones_dir)
            scan_result = scanner.scan_repository("repo_1")
            assert scan_result.repo_name == "repo_1"
            assert scan_result.agents_found

            sampler = StratifiedSampler(random_seed=42)
            fixtures = [
                {"id": 1, "fixture_type": "pytest.fixture"},
                {"id": 2, "fixture_type": "pytest.fixture"},
                {"id": 3, "fixture_type": "unittest.TestCase"},
                {"id": 4, "fixture_type": "unittest.TestCase"},
            ]
            sample_result = sampler.sample(fixtures, target_count=2)
            assert sample_result.sampled_count == 2

            db_path = root / "source.db"
            _create_export_db(db_path)
            exporter = HumanDatasetExporter(db_path, root / "out")
            export_result = exporter.export(sample_result.sampled_ids, version="1.0")

            assert export_result.zip_path.exists()
            assert export_result.fixture_count == 2
            assert export_result.csv_files


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
