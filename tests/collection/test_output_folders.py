"""Output folders: the RQ folders live under research_questions/, and the code creates
its output folders when they are missing (so toy-dataset/ can be deleted safely)."""

from collection import paths
from collection.csv_adapter import get_adapter
from collection.db import initialise_db
from collection.rq1_prevalence_scan import CSV_OUTPUT_DIR as RQ1_CSV_DIR
from collection.rq5_agent_file_scan import CSV_OUTPUT_DIR as RQ5_CSV_DIR


def test_rq1_csv_outputs_live_under_research_questions_RQ1():
    assert RQ1_CSV_DIR == paths.ROOT_DIR / "research_questions" / "RQ1"


def test_rq5_review_outputs_live_under_research_questions_rq5():
    assert RQ5_CSV_DIR == paths.ROOT_DIR / "research_questions" / "rq5"


def test_database_setup_creates_a_missing_toy_folder(tmp_path):
    db = tmp_path / "toy-dataset" / "db" / "c.db"
    assert not db.parent.exists()
    initialise_db(db)
    assert db.exists()


def test_csv_write_creates_a_missing_toy_folder(tmp_path):
    csv_path = tmp_path / "toy-dataset" / "c" / "repos" / "all.csv"
    get_adapter().write_dicts(csv_path, [{"repo_name": "owner/repo"}], ["repo_name"])
    assert csv_path.exists()
