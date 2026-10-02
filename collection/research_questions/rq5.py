"""
RQ5 -- Agent Configuration Files (Mixed -- Qualitative + Quantitative): what
instructions, if any, do humans give coding agents about test fixtures via
agent configuration files (e.g. CLAUDE.md, .cursor/rules, AGENTS.md)?

Not yet implemented. This module exists as a placeholder so the package's
RQ numbering (RQ1 fixture prevalence, RQ2 general metrics, RQ3 setup/
teardown, RQ4 mocking, RQ5 agent configuration files) is reflected in the
file layout ahead of the actual coding scheme and computation -- see
docs/research-questions.md for the current definition of each RQ.
`write_report()` writes a stub `research_questions/rq5.md` noting this,
rather than erroring, so the rest of the research_questions/ pipeline
(e.g. any script that regenerates every report in one pass) doesn't need
to special-case an unimplemented RQ.

python -m collection.research_questions.rq5
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ._shared import OUTPUT_DIR, write_markdown_report


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    del db_root  # unused -- no computation yet, see module docstring
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return "\n".join(
        [
            "# RQ5 -- Agent Configuration Files",
            "",
            "> What instructions, if any, do humans give coding agents "
            "about test fixtures via agent configuration files?",
            "",
            f"Generated: {generated_at}",
            "",
            "_Not yet implemented -- see this module's docstring._",
            "",
        ]
    )


def write_report(
    output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT
) -> Path:
    report = generate_report(db_root=db_root)
    return write_markdown_report(output_dir, "rq5.md", report)


def main() -> None:
    path = write_report()
    print(f"RQ5 report written to {path}")


if __name__ == "__main__":
    main()
