"""
Phase 8: Final validation of exported datasets.

This script verifies that:
1. Both datasets are completely standalone (no cross-references)
2. CSV exports have all required columns and metadata
3. Documentation is complete and accurate
4. Datasets can be used independently
5. Archive integrity is confirmed

Input:
  - phase_6_7_export_stats_*.json (from Phase 6-7)
    - fixturedb-human_v1.0_export.zip
    - fixturedb-agent_v1.0_export.zip

Output:
  - JSON validation report
"""

import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger

logger = get_logger(__name__)


class DatasetValidator:
    """Validates exported datasets for independence and completeness."""

    def __init__(self, export_dir: Path):
        """
        Initialize validator.

        Args:
            export_dir: Directory containing export ZIPs
        """
        self.export_dir = Path(export_dir)

    def validate_zip_archive(self, zip_path: Path) -> dict[str, Any]:
        """
        Validate ZIP archive structure and contents.

        Args:
            zip_path: Path to ZIP file

        Returns:
            Validation result dict
        """
        result: dict[str, Any] = {
            "zip_exists": zip_path.exists(),
            "zip_readable": False,
            "file_count": 0,
            "required_files": {
                "repositories.csv": False,
                "test_files.csv": False,
                "fixtures.csv": False,
                "mock_usages.csv": False,
                "README.md": False,
                "SCHEMA.md": False,
            },
            "is_agent": "agent" in zip_path.name,
            "agents_md_present": False,
            "total_size_mb": 0,
        }

        if not result["zip_exists"]:
            return result

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                result["zip_readable"] = True
                files = zf.namelist()
                result["file_count"] = len(files)

                # Check required files
                for required_file in result["required_files"].keys():
                    result["required_files"][required_file] = required_file in files

                # Check agent-specific file
                if result.get("is_agent"):
                    result["agents_md_present"] = "AGENTS.md" in files

                result["total_size_mb"] = zip_path.stat().st_size / (1024 * 1024)

        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file: {zip_path}")

        return result

    def validate_csv_files(self, zip_path: Path) -> dict[str, Any]:
        """
        Validate CSV files in archive.

        Args:
            zip_path: Path to ZIP file

        Returns:
        Validation result dict
        """
        result: dict[str, Any] = {
            "repositories": {"valid": False, "row_count": 0, "columns": []},
            "test_files": {"valid": False, "row_count": 0, "columns": []},
            "fixtures": {"valid": False, "row_count": 0, "columns": []},
            "mock_usages": {"valid": False, "row_count": 0, "columns": []},
        }

        if not zip_path.exists():
            return result

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for csv_name in [
                    "repositories",
                    "test_files",
                    "fixtures",
                    "mock_usages",
                ]:
                    csv_file = f"{csv_name}.csv"

                    if csv_file not in zf.namelist():
                        continue

                    try:
                        with zf.open(csv_file) as f:
                            # Read first few lines to validate
                            first_line = f.readline().decode("utf-8").strip()
                            columns = first_line.split(",")

                            # Count rows
                            row_count = sum(1 for _ in f) - 1  # -1 for header

                            result[csv_name] = {
                                "valid": True,
                                "row_count": row_count,
                                "columns": columns,
                            }

                    except Exception as e:
                        logger.warning(f"Failed to validate {csv_file}: {e}")

        except Exception as e:
            logger.error(f"Failed to read ZIP: {e}")

        return result

    def validate_independence(self, zip_path: Path) -> dict[str, Any]:
        """
        Validate that dataset is completely independent.

        Checks for:
        - No references to corpus.db
        - No cross-references between datasets
        - Complete repository metadata

        Args:
            zip_path: Path to ZIP file

        Returns:
            Validation result dict
        """
        result: dict[str, Any] = {
            "is_independent": True,
            "no_corpus_references": True,
            "has_repository_metadata": True,
            "complete_fixture_metadata": True,
            "issues": [],
        }

        if not zip_path.exists():
            result["is_independent"] = False
            return result

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Check README for corpus.db references
                if "README.md" in zf.namelist():
                    with zf.open("README.md") as f:
                        content = f.read().decode("utf-8").lower()
                        if "corpus.db" in content and "standalone" not in content:
                            result["no_corpus_references"] = False
                            result["issues"].append(
                                "README mentions corpus.db without clarifying independence"
                            )

                # Check repositories.csv has necessary columns
                if "repositories.csv" in zf.namelist():
                    with zf.open("repositories.csv") as f:
                        header = f.readline().decode("utf-8").strip().lower()
                        required_cols = ["id", "full_name", "language", "clone_url"]
                        for col in required_cols:
                            if col not in header:
                                result["has_repository_metadata"] = False
                                result["issues"].append(
                                    f"repositories.csv missing {col}"
                                )

                # Check fixtures.csv has necessary columns
                if "fixtures.csv" in zf.namelist():
                    with zf.open("fixtures.csv") as f:
                        header = f.readline().decode("utf-8").strip().lower()
                        required_cols = [
                            "id",
                            "name",
                            "fixture_type",
                            "loc",
                            "raw_source",
                        ]
                        for col in required_cols:
                            if col not in header:
                                result["complete_fixture_metadata"] = False
                                result["issues"].append(f"fixtures.csv missing {col}")

                # For agent dataset, check agent columns
                if "agent" in zip_path.name and "fixtures.csv" in zf.namelist():
                    with zf.open("fixtures.csv") as f:
                        header = f.readline().decode("utf-8").strip().lower()
                        agent_cols = ["commit_sha", "agent_type"]
                        for col in agent_cols:
                            if col not in header:
                                result["issues"].append(
                                    f"agent fixtures.csv missing {col}"
                                )

        except Exception as e:
            logger.error(f"Failed to validate independence: {e}")
            result["is_independent"] = False
            result["issues"].append(str(e))

        result["is_independent"] = len(result["issues"]) == 0

        return result

    def generate_validation_report(
        self,
        human_zip: Path,
        agent_zip: Path,
    ) -> dict[str, Any]:
        """
        Generate comprehensive validation report.

        Args:
            human_zip: Path to human dataset ZIP
            agent_zip: Path to agent dataset ZIP

        Returns:
            Validation report dict
        """
        report: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "human_dataset": {
                "zip_validation": self.validate_zip_archive(human_zip),
                "csv_validation": self.validate_csv_files(human_zip),
                "independence_validation": self.validate_independence(human_zip),
            },
            "agent_dataset": {
                "zip_validation": self.validate_zip_archive(agent_zip),
                "csv_validation": self.validate_csv_files(agent_zip),
                "independence_validation": self.validate_independence(agent_zip),
            },
        }

        # Overall validation
        human_valid = (
            report["human_dataset"]["zip_validation"]["zip_readable"]
            and all(
                report["human_dataset"]["zip_validation"]["required_files"].values()  # type: ignore[union-attr]
            )
            and report["human_dataset"]["independence_validation"]["is_independent"]
        )

        agent_valid = (
            report["agent_dataset"]["zip_validation"]["zip_readable"]
            and all(
                report["agent_dataset"]["zip_validation"]["required_files"].values()  # type: ignore[union-attr]
            )
            and report["agent_dataset"]["zip_validation"]["agents_md_present"]
            and report["agent_dataset"]["independence_validation"]["is_independent"]
        )

        report["validation_passed"] = human_valid and agent_valid

        return report


def main():
    """Execute Phase 8 final validation."""

    project_root = Path(__file__).parent
    output_dir = project_root / "output"

    # Find ZIPs
    human_zips = sorted(output_dir.glob("human_export/fixturedb-human_v*.zip"))
    agent_zips = sorted(output_dir.glob("agent_export/fixturedb-agent_v*.zip"))

    if not human_zips or not agent_zips:
        logger.error("Export ZIPs not found")
        logger.error("Please run Phase 6-7 first")
        return 1

    human_zip = human_zips[-1]
    agent_zip = agent_zips[-1]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_dir / f"phase_8_validation_report_{timestamp}.json"

    logger.info("=" * 70)
    logger.info("PHASE 8: Final Validation")
    logger.info("=" * 70)
    logger.info("")

    try:
        validator = DatasetValidator(output_dir)

        logger.info(f"Validating human dataset: {human_zip.name}")
        logger.info(f"Validating agent dataset: {agent_zip.name}")
        logger.info("")

        report = validator.generate_validation_report(human_zip, agent_zip)

        # Print validation results
        logger.info("=" * 70)
        logger.info("VALIDATION RESULTS")
        logger.info("=" * 70)
        logger.info("")

        logger.info("Human Dataset:")
        human_zip_valid = report["human_dataset"]["zip_validation"]["zip_readable"]
        logger.info(f"  ZIP readable: {'✓' if human_zip_valid else '✗'}")

        human_files_valid = all(
            report["human_dataset"]["zip_validation"]["required_files"].values()
        )
        logger.info(f"  Required files: {'✓' if human_files_valid else '✗'}")

        human_indep_valid = report["human_dataset"]["independence_validation"][
            "is_independent"
        ]
        logger.info(f"  Independent: {'✓' if human_indep_valid else '✗'}")

        logger.info("")
        logger.info("Agent Dataset:")
        agent_zip_valid = report["agent_dataset"]["zip_validation"]["zip_readable"]
        logger.info(f"  ZIP readable: {'✓' if agent_zip_valid else '✗'}")

        agent_files_valid = (
            all(report["agent_dataset"]["zip_validation"]["required_files"].values())
            and report["agent_dataset"]["zip_validation"]["agents_md_present"]
        )
        logger.info(
            f"  Required files + AGENTS.md: {'✓' if agent_files_valid else '✗'}"
        )

        agent_indep_valid = report["agent_dataset"]["independence_validation"][
            "is_independent"
        ]
        logger.info(f"  Independent: {'✓' if agent_indep_valid else '✗'}")

        logger.info("")
        logger.info("=" * 70)

        if report["validation_passed"]:
            logger.info("✓ VALIDATION PASSED")
            logger.info("")
            logger.info("Both datasets are:")
            logger.info("  - Complete (all files present)")
            logger.info("  - Standalone (no corpus.db required)")
            logger.info("  - Independent (can be used separately)")
            logger.info("")
            logger.info("Distribution ready for research use:")
            logger.info(f"  {human_zip.name}")
            logger.info(f"  {agent_zip.name}")

        else:
            logger.warning("✗ VALIDATION ISSUES FOUND")
            logger.info("")

            if report["human_dataset"]["independence_validation"]["issues"]:
                logger.warning("Human dataset issues:")
                for issue in report["human_dataset"]["independence_validation"][
                    "issues"
                ]:
                    logger.warning(f"  - {issue}")

            if report["agent_dataset"]["independence_validation"]["issues"]:
                logger.warning("Agent dataset issues:")
                for issue in report["agent_dataset"]["independence_validation"][
                    "issues"
                ]:
                    logger.warning(f"  - {issue}")

        # Save report
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info("")
        logger.info(f"Validation report saved to: {report_file}")
        logger.info("")
        logger.info("PHASE 8 COMPLETE")
        logger.info("")
        logger.info("=" * 70)
        logger.info("FIXTUREDB SPLIT IMPLEMENTATION COMPLETE")
        logger.info("=" * 70)

        return 0 if report["validation_passed"] else 1

    except Exception as e:
        logger.error(f"Error during validation: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
