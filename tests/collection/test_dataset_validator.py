import zipfile
from pathlib import Path

from collection.dataset_validator import DatasetValidator

REPO_CSV = "id,full_name,language,clone_url\n1,owner/repo,python,https://x.git\n"
TEST_FILES_CSV = "id,repo_id,relative_path\n1,1,tests/test_foo.py\n"
FIXTURES_CSV = (
    "id,name,fixture_type,loc,raw_source\n1,my_fixture,pytest_decorator,5,code\n"
)
AGENT_FIXTURES_CSV = (
    "id,name,fixture_type,loc,raw_source,commit_sha,agent_type\n"
    "1,my_fixture,pytest_decorator,5,code,deadbeef,claude\n"
)
MOCK_USAGES_CSV = "id,fixture_id,framework\n"  # legitimately empty
README = "This dataset is standalone and does not require corpus.db.\n"
SCHEMA = "schema docs\n"


def _write_zip(path: Path, *, fixtures_csv: str | None = None, agent: bool = False) -> None:
    if fixtures_csv is None:
        fixtures_csv = AGENT_FIXTURES_CSV if agent else FIXTURES_CSV
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("repositories.csv", REPO_CSV)
        zf.writestr("test_files.csv", TEST_FILES_CSV)
        zf.writestr("fixtures.csv", fixtures_csv)
        zf.writestr("mock_usages.csv", MOCK_USAGES_CSV)
        zf.writestr("README.md", README)
        zf.writestr("SCHEMA.md", SCHEMA)
        if agent:
            zf.writestr("AGENTS.md", "agent docs\n")


def test_validation_passes_for_well_formed_datasets(tmp_path):
    human_zip = tmp_path / "fixturedb-human_v1.0_export.zip"
    agent_zip = tmp_path / "fixturedb-agent_v1.0_export.zip"
    _write_zip(human_zip)
    _write_zip(agent_zip, agent=True)

    validator = DatasetValidator(tmp_path)
    report = validator.generate_validation_report(human_zip, agent_zip)

    assert report["validation_passed"] is True


def test_validation_fails_when_fixtures_csv_is_empty(tmp_path):
    """Regression: csv_validation (row_count/columns/valid per CSV) was
    computed but never read again by validation_passed -- only filename
    presence and a few header columns were checked. An empty (header-only)
    fixtures.csv previously still reported VALIDATION PASSED."""
    human_zip = tmp_path / "fixturedb-human_v1.0_export.zip"
    agent_zip = tmp_path / "fixturedb-agent_v1.0_export.zip"
    empty_fixtures_csv = "id,name,fixture_type,loc,raw_source\n"  # header only
    _write_zip(human_zip, fixtures_csv=empty_fixtures_csv, agent=False)
    _write_zip(agent_zip, agent=True)

    validator = DatasetValidator(tmp_path)
    report = validator.generate_validation_report(human_zip, agent_zip)

    assert report["human_dataset"]["csv_validation"]["fixtures"]["row_count"] == 0
    assert report["validation_passed"] is False


def test_validate_csv_files_row_count_is_not_off_by_one(tmp_path):
    """Regression: row_count was computed as
    `sum(1 for _ in f) - 1  # -1 for header`, but f.readline() had already
    consumed the header line before that loop ran, so every CSV's row_count
    was undercounted by one -- and a header-only (truly empty) CSV reported
    row_count=-1 instead of 0."""
    zip_path = tmp_path / "fixturedb-human_v1.0_export.zip"
    _write_zip(zip_path)

    validator = DatasetValidator(tmp_path)
    result = validator.validate_csv_files(zip_path)

    # FIXTURES_CSV has exactly one data row.
    assert result["fixtures"]["row_count"] == 1
    # MOCK_USAGES_CSV is header-only: zero data rows, not -1.
    assert result["mock_usages"]["row_count"] == 0


def test_validation_passes_when_only_mock_usages_csv_is_empty(tmp_path):
    """mock_usages.csv legitimately having zero rows must not fail
    validation -- only the three core CSVs (repositories/test_files/
    fixtures) are required to be non-empty."""
    human_zip = tmp_path / "fixturedb-human_v1.0_export.zip"
    agent_zip = tmp_path / "fixturedb-agent_v1.0_export.zip"
    _write_zip(human_zip)
    _write_zip(agent_zip, agent=True)

    validator = DatasetValidator(tmp_path)
    report = validator.generate_validation_report(human_zip, agent_zip)

    assert report["human_dataset"]["csv_validation"]["mock_usages"]["row_count"] == 0
    assert report["validation_passed"] is True
