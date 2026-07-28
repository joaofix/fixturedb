"""
Cross-language contamination check: for each dataset's per-language fixture
CSV (`datasets/{a,b,c}/fixtures/{language}_fixtures.csv`), what fraction of
its rows carry a `language` value that does not match the file's own
nominal (filename) language?

Why this is a real check, not a tautology: a fixture's `language` column and
the CSV file it's routed into are written from the same per-fixture source
value (`fixture.get("language")`) but via two independently-coded fallback
paths when that value is falsy -- the routing decision
(`fixtures_by_language[...]` in agent_corpus.py/human_corpus.py/dataset_c.py)
falls back to the language currently being scanned, while the column value
written by `persist_repository_and_fixtures()` (corpus_utils.py) falls back
to the repository's own stored `language` field. Those two fallbacks can
diverge (e.g. a multi-language repo scanned under one language pass whose
own SEART-assigned `language` differs), so a mismatch here is evidence of a
real routing/labelling bug, not just restating already-tied-together data.

Deliberately NOT checked: file_path's extension against the `language`
column. `fixture["language"]` is itself set via
`agent_fixture_extractor.py::_get_language()`, a thin wrapper around
`language_utils.get_language_static()` -- the exact same extension-to-
language table an extension-based check would use. That comparison would
always read 0%, not because the data is clean, but because it's checking a
value against itself.

A dataset is skipped (not an error) if its `datasets/{dataset}/fixtures/`
directory doesn't exist or has no `*_fixtures.csv` files yet.

python -m collection.research_questions.language_contamination
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..logging_utils import get_logger
from ._shared import DATASET_LABELS, OUTPUT_DIR, write_markdown_report

logger = get_logger(__name__)

# raw_source can contain embedded newlines inside a quoted CSV field, which
# trips csv's default field_size_limit -- same bump used elsewhere in this
# project (e.g. dataset_summary.py) when reading fixture CSVs.
csv.field_size_limit(10**7)


@dataclass
class FileContamination:
    csv_name: str
    nominal_language: str
    total: int
    mismatched: int
    mismatched_by_language: dict[str, int] = field(default_factory=dict)

    @property
    def pct(self) -> float:
        return 100 * self.mismatched / self.total if self.total else 0.0


def _check_csv(csv_path: Path) -> FileContamination:
    nominal_language = csv_path.stem.removesuffix("_fixtures")
    total = 0
    mismatched = 0
    mismatched_by_language: dict[str, int] = {}

    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            total += 1
            actual = (row.get("language") or "").strip().lower()
            if actual != nominal_language:
                mismatched += 1
                mismatched_by_language[actual] = mismatched_by_language.get(actual, 0) + 1

    return FileContamination(
        csv_name=csv_path.name,
        nominal_language=nominal_language,
        total=total,
        mismatched=mismatched,
        mismatched_by_language=mismatched_by_language,
    )


def check_dataset(dataset: str, *, datasets_root: Path = paths.DATASETS_ROOT) -> list[FileContamination] | None:
    """Return per-CSV contamination results for `dataset`, or None if its
    fixtures/ directory doesn't exist or has no *_fixtures.csv files yet."""
    fixtures_dir = paths.stage_dir(dataset, "fixtures", root=datasets_root)
    csv_paths = sorted(fixtures_dir.glob("*_fixtures.csv")) if fixtures_dir.exists() else []
    if not csv_paths:
        logger.warning(f"{fixtures_dir} has no *_fixtures.csv files; skipping dataset {dataset!r}")
        return None
    return [_check_csv(p) for p in csv_paths]


def _render_dataset(dataset: str, results: list[FileContamination]) -> str:
    total = sum(r.total for r in results)
    mismatched = sum(r.mismatched for r in results)
    pct = 100 * mismatched / total if total else 0.0

    lines = [
        f"### {DATASET_LABELS[dataset]} -- {mismatched:,}/{total:,} fixtures mismatched ({pct:.2f}%)",
        "",
        "| CSV file | nominal language | total | mismatched | mismatched % | mismatched languages found |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        breakdown = (
            ", ".join(f"{lang}={count}" for lang, count in sorted(r.mismatched_by_language.items()))
            if r.mismatched_by_language
            else "--"
        )
        lines.append(
            f"| {r.csv_name} | {r.nominal_language} | {r.total:,} | {r.mismatched:,} | "
            f"{r.pct:.2f}% | {breakdown} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_report(*, datasets_root: Path = paths.DATASETS_ROOT) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Cross-Language Contamination Check",
        "",
        "> For each dataset's per-language fixture CSV, what fraction of rows carry a "
        "`language` value that doesn't match the file's own nominal (filename) language?",
        "",
        f"Generated: {generated_at}",
        "",
    ]

    for dataset in ("a", "b", "c"):
        results = check_dataset(dataset, datasets_root=datasets_root)
        if results is None:
            lines += [
                f"### {DATASET_LABELS[dataset]}",
                "",
                "_Not available -- no fixtures/*.csv files collected yet._",
                "",
            ]
        else:
            lines.append(_render_dataset(dataset, results))

    return "\n".join(lines)


def write_report(output_dir: Path = OUTPUT_DIR, *, datasets_root: Path = paths.DATASETS_ROOT) -> Path:
    report = generate_report(datasets_root=datasets_root)
    output_path = write_markdown_report(output_dir, "language_contamination.md", report)
    logger.info(f"Language contamination report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"Language contamination report written to {path}")


if __name__ == "__main__":
    main()
