"""Tests for collection/research_questions/rq5.py.

RQ5 (Agent Configuration Files) isn't implemented yet -- see that module's
docstring. These tests just lock down the placeholder's contract: it
renders a stub report (rather than erroring) and writes it to the
conventional `rq5.md` path, so a future real implementation has a known
baseline to replace.
"""

from collection.research_questions.rq5 import generate_report, write_report


class TestGenerateReport:
    def test_renders_not_yet_implemented_stub(self):
        report = generate_report()
        assert "# RQ5 -- Agent Configuration Files" in report
        assert "Not yet implemented" in report


class TestWriteReport:
    def test_writes_to_rq5_md(self, tmp_path):
        out_dir = tmp_path / "out"
        path = write_report(out_dir)
        assert path == out_dir / "rq5.md"
        assert path.read_text() == generate_report()
