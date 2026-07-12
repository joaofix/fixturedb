"""Validate an exported dataset ZIP for completeness and independence.

Moved from the old phase_8_final_validation.py, which only ever validated
a hardcoded pair (human + agent) via `generate_validation_report()`. That
method is kept for backward compatibility; new code (`validate --dataset X`)
should use `validate_single()`, which validates exactly one ZIP and accepts
an explicit `is_agent` flag instead of sniffing the word "agent" out of the
zip filename -- the new per-dataset zip names (`export/a.zip`, `b.zip`,
`c.zip`) don't carry that substring for Dataset A.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging_utils import get_logger

logger = get_logger(__name__)


class DatasetValidator:
    """Validates exported datasets for independence and completeness."""

    def __init__(self, export_dir: Path):
        self.export_dir = Path(export_dir)

    def validate_zip_archive(
        self, zip_path: Path, is_agent: bool | None = None
    ) -> dict[str, Any]:
        """Validate ZIP archive structure and contents.

        `is_agent` defaults to sniffing "agent" in the filename when not
        given explicitly (backward-compatible with the old human/agent-only
        naming); pass it explicitly for the new a/b/c.zip naming.
        """
        if is_agent is None:
            is_agent = "agent" in zip_path.name

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
            "is_agent": is_agent,
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

                for required_file in result["required_files"].keys():
                    result["required_files"][required_file] = required_file in files

                if is_agent:
                    result["agents_md_present"] = "AGENTS.md" in files

                result["total_size_mb"] = zip_path.stat().st_size / (1024 * 1024)

        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file: {zip_path}")

        return result

    def validate_csv_files(self, zip_path: Path) -> dict[str, Any]:
        """Validate CSV files in archive."""
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

                            # Count remaining (data) rows. readline() above
                            # already consumed the header line, so the
                            # iterator below only sees data rows -- do NOT
                            # subtract 1 again here, or a header-only CSV
                            # (0 data rows) reports row_count=-1 and every
                            # other CSV undercounts by one row.
                            row_count = sum(1 for _ in f)

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

    def validate_independence(
        self, zip_path: Path, is_agent: bool | None = None
    ) -> dict[str, Any]:
        """Validate that dataset is completely independent.

        Checks for no references to corpus.db, no cross-references between
        datasets, and complete repository/fixture metadata.
        """
        if is_agent is None:
            is_agent = "agent" in zip_path.name

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
                if "README.md" in zf.namelist():
                    with zf.open("README.md") as f:
                        content = f.read().decode("utf-8").lower()
                        if "corpus.db" in content and "standalone" not in content:
                            result["no_corpus_references"] = False
                            result["issues"].append(
                                "README mentions corpus.db without clarifying independence"
                            )

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

                if is_agent and "fixtures.csv" in zf.namelist():
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

    @staticmethod
    def _csv_content_valid(csv_validation: dict[str, Any]) -> bool:
        """Gate validity on the CSV content checks that validate_csv_files()
        already computes: no CSV is unreadable, and the three core CSVs
        (repositories/test_files/fixtures) are never empty. mock_usages.csv
        may legitimately have zero rows.
        """
        if not all(csv["valid"] for csv in csv_validation.values()):
            return False
        return all(
            csv_validation[name]["row_count"] > 0
            for name in ("repositories", "test_files", "fixtures")
        )

    def validate_single(
        self, zip_path: Path, is_agent: bool = False
    ) -> dict[str, Any]:
        """Validate exactly one dataset ZIP. Used by `validate --dataset X`."""
        zip_validation = self.validate_zip_archive(zip_path, is_agent=is_agent)
        csv_validation = self.validate_csv_files(zip_path)
        independence_validation = self.validate_independence(
            zip_path, is_agent=is_agent
        )

        required_files_ok = all(zip_validation["required_files"].values())
        agents_md_ok = (not is_agent) or zip_validation["agents_md_present"]

        valid = (
            zip_validation["zip_readable"]
            and required_files_ok
            and agents_md_ok
            and independence_validation["is_independent"]
            and self._csv_content_valid(csv_validation)
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "zip_path": str(zip_path),
            "zip_validation": zip_validation,
            "csv_validation": csv_validation,
            "independence_validation": independence_validation,
            "valid": valid,
        }

    def generate_validation_report(
        self,
        human_zip: Path,
        agent_zip: Path,
    ) -> dict[str, Any]:
        """Pairwise report over a hardcoded (human, agent) pair. Kept for
        backward compatibility; new code should use validate_single()."""
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

        human_valid = (
            report["human_dataset"]["zip_validation"]["zip_readable"]
            and all(
                report["human_dataset"]["zip_validation"]["required_files"].values()  # type: ignore[union-attr]
            )
            and report["human_dataset"]["independence_validation"]["is_independent"]
            and self._csv_content_valid(report["human_dataset"]["csv_validation"])
        )

        agent_valid = (
            report["agent_dataset"]["zip_validation"]["zip_readable"]
            and all(
                report["agent_dataset"]["zip_validation"]["required_files"].values()  # type: ignore[union-attr]
            )
            and report["agent_dataset"]["zip_validation"]["agents_md_present"]
            and report["agent_dataset"]["independence_validation"]["is_independent"]
            and self._csv_content_valid(report["agent_dataset"]["csv_validation"])
        )

        report["validation_passed"] = human_valid and agent_valid

        return report
