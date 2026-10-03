"""
RQ5 -- Agent Configuration Files (Mixed -- Qualitative + Quantitative): how
often do root-level agent configuration files (AGENTS.md, CLAUDE.md) mention
test-related and fixture-related guidance, across the raw repo universe --
independent of any Dataset A/B/C filtering?

Pure reader over `db/rq5_agent_files.db` (`collection/rq5_agent_file_scan.py`'s
own output) -- same role `rq1.py` plays for `db/rq1_prevalence.db`. No
collection logic lives here; this module only aggregates and renders what
that scan already persisted.

A repo with `fetch_ok=0` in `repo_scan` (no commit at/before the snapshot
date, or the root tree/blob fetch failed) contributes zero rows to
`agent_files` by construction (`rq5_agent_file_scan.process_repo()` never
reaches the file-matching step for such a repo) -- so every count below is
already implicitly restricted to successfully-analyzed repos, with no
extra filter needed here. "Repositories skipped" is reported separately,
for transparency, not folded into any percentage's denominator.

**Every statistic here is at the repository level, not the file level**
(2026-10-02 methodology correction -- the first version of this report was
file-level throughout; see git history if that shape is ever needed again).
The denominator for every percentage is "repositories with >=1 root agent
file" (`aggregate_repo_guidance()`'s own population), never "agent files
found": a repo has test (or fixture) guidance if ANY of its root agent
files matches >=1 test (or fixture) keyword (`RepoGuidance.has_test`/
`has_fixture`, folded with logical OR across that repo's files in
`aggregate_repo_guidance()`). A pointer file (e.g. a `CLAUDE.md` that's a
symlink to `AGENTS.md`) needs no special-casing here: its own blob content
is the literal link-target text (see `rq5_agent_file_scan.
read_blob_via_api()`'s docstring), which trivially never contains a
catalog keyword on its own, so it can never manufacture a false guidance
signal for its repo -- `AGENTS.md`'s own row is what would (correctly)
carry the real signal.

`agent_files.csv` (the scan's own CSV output) stays file-level raw data --
intentionally not re-aggregated into percentages at that granularity
anywhere, including here; this module only computes percentages over the
repo-level aggregation.

python -m collection.research_questions.rq5
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..db import db_session
from ..rq5_agent_file_scan import CATALOG_PATH as _CATALOG_PATH
from ..rq5_agent_file_scan import DB_PATH as _SCAN_DB_PATH
from ..rq5_agent_file_scan import RQ5_CUTOFF_DATE, load_rq5_keyword_catalog
from ._shared import OUTPUT_DIR, pct, write_markdown_report

# Derived from rq5_agent_file_scan.DB_PATH rather than a second hardcoded
# "rq5_agent_files.db" literal -- see rq1.py's own _DB_FILENAME for why
# (a rename there must not be able to silently desync from what this
# module reads).
_DB_FILENAME = _SCAN_DB_PATH.name

# Paper's own row order -- deliberately NOT rq5_agent_file_scan.RQ5_LANGUAGES's
# alphabetical order (java, javascript, python, typescript), matching rq1.py's
# own DISPLAY_LANGUAGES convention.
DISPLAY_LANGUAGES: tuple[str, ...] = ("python", "java", "javascript", "typescript")
DISPLAY_LABELS: dict[str, str] = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
}


@dataclass
class RepoGuidance:
    """One repo's test/fixture guidance signal, folded (logical OR) across
    every root agent file it has -- the unit every statistic in this
    report is computed over. `test_keywords`/`fixture_keywords` are the
    union of keywords matched across that repo's files, for the per-
    keyword repo counts."""

    language: str
    has_test: bool = False
    has_fixture: bool = False
    test_keywords: set[str] = field(default_factory=set)
    fixture_keywords: set[str] = field(default_factory=set)


@dataclass
class RepoGroupStats:
    """One group's (overall, or one language) repo-level counts. Always
    computed directly from that group's own `RepoGuidance` subset, never
    derived from another group's numbers, so there is no pooled-vs-
    averaged ambiguity anywhere in this report."""

    n: int = 0
    n_test: int = 0
    n_fixture: int = 0
    n_test_and_fixture: int = 0


def _split_keywords(raw: str | None) -> list[str]:
    return [k.strip() for k in (raw or "").split(",") if k.strip()]


def aggregate_repo_guidance(rows: list[sqlite3.Row]) -> dict[str, RepoGuidance]:
    """Fold `agent_files` rows (one per root agent file found) into one
    `RepoGuidance` per repo. Only repos with >=1 agent file appear here at
    all -- a repo contributing zero `agent_files` rows (the common case)
    is simply absent, which is exactly "repositories with >=1 root agent
    file" as a population (`len()` of this dict's result)."""
    by_repo: dict[str, RepoGuidance] = {}
    for row in rows:
        entry = by_repo.setdefault(row["repo_name"], RepoGuidance(language=row["language"]))
        if row["has_test"]:
            entry.has_test = True
        if row["has_fixture"]:
            entry.has_fixture = True
        entry.test_keywords.update(_split_keywords(row["matched_test_keywords"]))
        entry.fixture_keywords.update(_split_keywords(row["matched_fixture_keywords"]))
    return by_repo


def _repo_group_stats(guidances: list[RepoGuidance]) -> RepoGroupStats:
    n_test = sum(1 for g in guidances if g.has_test)
    n_fixture = sum(1 for g in guidances if g.has_fixture)
    n_both = sum(1 for g in guidances if g.has_test and g.has_fixture)
    return RepoGroupStats(n=len(guidances), n_test=n_test, n_fixture=n_fixture, n_test_and_fixture=n_both)


def _pct_or_none(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def load_agent_files(db_root: Path = paths.DB_ROOT) -> list[sqlite3.Row] | None:
    """Every row of `agent_files` -- every root-level AGENTS.md/CLAUDE.md
    (or case-variant) found across the whole scanned universe. `None` if
    `db/rq5_agent_files.db` doesn't exist yet (not collected), as distinct
    from an empty list (collected, but zero agent files found so far --
    e.g. mid-run, or a toy run). This is raw, file-level input --
    `aggregate_repo_guidance()` is what turns it into the repo-level
    population every statistic in this report actually uses."""
    db_path = db_root / _DB_FILENAME
    if not db_path.exists():
        return None
    with db_session(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM agent_files").fetchall()


def load_repo_counts(db_root: Path = paths.DB_ROOT) -> dict[str, int] | None:
    """How many repos were attempted vs. successfully analyzed
    (`fetch_ok=1`) vs. skipped (`fetch_ok=0`, any reason) -- `None` if the
    db doesn't exist yet. Reported for transparency only -- "analyzed"
    includes every successfully-scanned repo regardless of whether it had
    any agent file, so it is NOT the denominator any percentage in this
    report uses (see `aggregate_repo_guidance()`'s docstring)."""
    db_path = db_root / _DB_FILENAME
    if not db_path.exists():
        return None
    with db_session(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM repo_scan").fetchone()[0]
        analyzed = conn.execute("SELECT COUNT(*) FROM repo_scan WHERE fetch_ok = 1").fetchone()[0]
    return {"total": total, "analyzed": analyzed, "skipped": total - analyzed}


def _keyword_repo_counts(guidances: list[RepoGuidance], attr: str, catalog_keywords: list[str]) -> Counter:
    """How many repos have >=1 root agent file containing each catalog
    keyword -- `attr` is `"test_keywords"` or `"fixture_keywords"`, the
    per-repo union already built by `aggregate_repo_guidance()`. Every
    catalog keyword is present in the result even at 0, so a report
    reader sees the full list searched for, not just the ones that
    happened to fire."""
    counts: Counter = Counter(dict.fromkeys(catalog_keywords, 0))
    for guidance in guidances:
        for keyword in getattr(guidance, attr):
            counts[keyword] += 1
    return counts


def render_overall_table(guidances: list[RepoGuidance]) -> str:
    stats = _repo_group_stats(guidances)
    secondary = pct(_pct_or_none(stats.n_test_and_fixture, stats.n_test))
    lines = [
        "| Metric | Value |",
        "|---|---|",
        f"| Repositories with >=1 root agent file | {stats.n:,} |",
        f"| ... with >=1 test keyword | {stats.n_test:,} ({pct(_pct_or_none(stats.n_test, stats.n))}) |",
        f"| ... with >=1 fixture keyword | {stats.n_fixture:,} ({pct(_pct_or_none(stats.n_fixture, stats.n))}) |",
        f"| Test-guidance repos that also have fixture guidance | {stats.n_test_and_fixture:,} ({secondary}) |",
    ]
    return "\n".join(lines)


def render_by_language_table(guidances: list[RepoGuidance]) -> str:
    lines = [
        "| Language | Repositories with >=1 agent file | Test keyword (%) | Fixture keyword (%) |",
        "|---|---|---|---|",
    ]
    for language in DISPLAY_LANGUAGES:
        group = _repo_group_stats([g for g in guidances if g.language == language])
        lines.append(
            f"| {DISPLAY_LABELS[language]} | {group.n:,} | {pct(_pct_or_none(group.n_test, group.n))} | "
            f"{pct(_pct_or_none(group.n_fixture, group.n))} |"
        )
    return "\n".join(lines)


def render_keyword_table(counts: Counter, *, header: str) -> str:
    lines = [f"| {header} | Repositories containing it |", "|---|---|"]
    for keyword, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {keyword} | {count:,} |")
    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT, catalog_path: Path = _CATALOG_PATH) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows = load_agent_files(db_root)
    repo_counts = load_repo_counts(db_root)
    catalog = load_rq5_keyword_catalog(catalog_path)

    lines = [
        "# RQ5 -- Agent Configuration Files",
        "",
        "> How often do root-level agent configuration files mention "
        "test-related and fixture-related guidance?",
        "",
        f"Generated: {generated_at}",
        "",
        "See [docs/research-questions.md](../docs/research-questions.md) for "
        "the full RQ5 definition.",
        "",
    ]

    if rows is None or repo_counts is None:
        lines += ["_Not available -- db/rq5_agent_files.db not collected yet._", ""]
        return "\n".join(lines)

    by_repo = aggregate_repo_guidance(rows)

    lines += [
        f"Snapshot date: {RQ5_CUTOFF_DATE} (same commit-pinning policy as RQ1 -- see "
        "`collection/rq5_agent_file_scan.py`'s module docstring).",
        f"Target files searched (repository root only, case-insensitive, catalog "
        f"version {catalog['version']}): {', '.join(catalog['target_files'])}.",
        f"Repositories analyzed (commit found at/before the "
        f"snapshot date, root tree/blob fetch succeeded): {repo_counts['analyzed']:,}.",
        f"Repositories skipped (no commit at/before the snapshot date, or a "
        f"fetch failed): {repo_counts['skipped']:,}.",
        "Every statistic below is at the repository level -- a repo counts as "
        "having test (or fixture) guidance if ANY of its root agent files "
        "matches >=1 test (or fixture) keyword. The denominator throughout is "
        '"repositories with >=1 root agent file", not "repositories '
        'analyzed" (most analyzed repos have none).',
        "",
    ]

    if not by_repo:
        lines += ["_No agent files found yet in the collected data._", ""]
        return "\n".join(lines)

    guidances = list(by_repo.values())

    lines += [
        "## Overall",
        "",
        render_overall_table(guidances),
        "",
        "## By repository language",
        "",
        render_by_language_table(guidances),
        "",
        "## Keyword frequency -- test keywords",
        "",
        render_keyword_table(
            _keyword_repo_counts(guidances, "test_keywords", catalog["test_keywords"]),
            header="Test keyword",
        ),
        "",
        "## Keyword frequency -- fixture keywords",
        "",
        render_keyword_table(
            _keyword_repo_counts(guidances, "fixture_keywords", catalog["fixture_keywords"]),
            header="Fixture keyword",
        ),
        "",
        "## Keyword lists used (catalog version "
        f"{catalog['version']}, `collection/heuristics/rq5_agent_file_keywords.yaml`)",
        "",
        f"- Test keywords: {', '.join(catalog['test_keywords'])}",
        f"- Fixture keywords: {', '.join(catalog['fixture_keywords'])}",
        "",
    ]

    return "\n".join(lines)


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
