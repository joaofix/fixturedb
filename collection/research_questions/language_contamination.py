"""
Cross-language contamination check: for each dataset, what fraction of
fixtures have their OWN detected language (test_files.language, set from
the fixture's own file extension at persist time) differ from their
repo's SEART-assigned tag (repositories.language)?

Dataset "c" reads `db/c_sampled.db` (the fixture-level sample-down), not
the full `db/c.db` -- same redirect every other `research_questions/`
script uses for dataset "c", see `require_db_or_none()`'s docstring.

Reuses `_shared.py`'s `compute_language_leakage()`/
`render_language_leakage_table()` -- the exact same computation already
driving RQ2/RQ4's "Cross-language fixture leakage" table -- rather than
recomputing it a second way. This file exists as a dedicated, standalone
place to check contamination on its own (not buried inside RQ2's larger
structural-metrics report), not to define a second notion of it.

Previous version of this check (before this rewrite) compared a fixture's
CSV row `language` column against the CSV *filename* it was routed into.
That was a tautology, not a real check: both the routing decision
(`fixtures_by_language[...]` in agent_corpus.py/
dataset_c.py) and the persisted column value
(`persist_repository_and_fixtures()` in corpus_utils.py) read the exact
same `fixture.get("language")` value with the exact same repo-language
fallback -- so they can never disagree under the current pipeline, and
the check always read 0.00% for every dataset regardless of how much
real contamination existed. Confirmed on live data: a fixture from
`FujiwaraChoki/supoclip` (a Dataset A repo tagged `python`) is itself a
`typescript` file -- real leakage -- yet it lands in
`typescript_fixtures.csv` with `language=typescript`, filename and column
in perfect agreement, so the old check counted it as clean. The real
signal was always test_files.language vs repositories.language, which is
what this version checks.

python -m collection.research_questions.language_contamination
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..db import db_session
from ..logging_utils import get_logger
from ._shared import (
    DATASET_LABELS,
    OUTPUT_DIR,
    compute_language_leakage,
    render_language_leakage_table,
    require_db_or_none,
    write_markdown_report,
)

logger = get_logger(__name__)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Cross-Language Contamination Check",
        "",
        "> For each dataset, what fraction of fixtures have their own "
        "detected language (from the fixture's own file) differ from "
        "their repo's tagged language?",
        "",
        "Dataset C is checked against its fixture-level sample-down "
        "(`db/c_sampled.db`), not the full `db/c.db` -- see this module's "
        "docstring.",
        "",
        f"Generated: {generated_at}",
        "",
    ]

    for dataset in ("a", "c"):
        db_file = require_db_or_none(dataset, db_root)
        if db_file is None:
            not_available = (
                "_Not available -- run `sample-c-repos` first "
                "(`db/c_sampled.db` not found)._"
                if dataset == "c"
                else "_Not available -- no db/a.db collected yet._"
            )
            lines += [
                f"### {DATASET_LABELS[dataset]}",
                "",
                not_available,
                "",
            ]
            continue

        with db_session(db_file) as conn:
            leakage = compute_language_leakage(conn)

        lines.append(f"### {DATASET_LABELS[dataset]}")
        lines.append("")
        lines.append(render_language_leakage_table(leakage))

    return "\n".join(lines)


def write_report(output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT) -> Path:
    report = generate_report(db_root=db_root)
    output_path = write_markdown_report(output_dir, "language_contamination.md", report)
    logger.info(f"Language contamination report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"Language contamination report written to {path}")


if __name__ == "__main__":
    main()
