"""
Dataset findings that support paper claims but don't belong to any single
RQ1-3 comparison -- they don't pit Dataset A against B/C, they describe a
dataset's own collection process or composition. New findings of this kind
get their own `##` section and render function in this file rather than a
new script per finding (unlike rq1.py/rq2.py/rq3.py/balance.py/
language_contamination.py, which each answer one specific, separately-named
question). See docs/data/dataset-card.md's "About the datasets" section for
how these are meant to be cited -- as caveats/characterisation alongside the
RQ1-3 comparisons, not folded into any RQ's own statistical tests.

Every section here reads data collection already computes and persists --
`db/*.db`, or (for the newest section below) the raw SEART export and
Dataset A's commit-discovery CSVs; this script adds no new *collection-side*
instrumentation of its own, though a couple of rows are newly-derived
queries over existing columns rather than previously-reported numbers.

Currently covers:

- **Diff-purity gate** (Dataset A): of the agent commits that touched >=1
  test file, how many got rejected for mixing test-file additions with
  edits/deletions (`diff_purity.py`'s "only pure-addition test-file commits
  count" rule), vs accepted? Reads `agent_commits_touching_tests`/
  `agent_commits_rejected_mixed_test_diff`/`agent_commits_accepted`,
  persisted per-repo by `agent_corpus.py` (`update_agent_commit_stats()`,
  db.py) on every Dataset A collection run. Dataset B/C are out of scope by
  construction, not by missing data: the pure-addition gate only governs
  which agent commits are accepted into Dataset A in the first place --
  Dataset B/C never run agent commits through it, so their `repositories`
  rows keep these columns at their 0 default.

  Known limitation (not fixed here): these counters are accumulated
  per-repo across every agent commit in that repo, regardless of which
  agent authored it -- a per-(repo, agent_type) breakdown isn't possible
  from data already persisted (the per-commit purity outcome isn't itself
  stored, only the repo-level running totals). Adding that would need new
  instrumentation in agent_corpus.py.

- **Agent adoption intensity** (Dataset A repo pool): how many/what % of
  Dataset A's scanned repos fall into each `agent_adoption_intensity`
  bucket (`no_commits`/`experimental`/`limited`/`consistent`/`pervasive` --
  see `tiered_agent_corpus_scanner.py::compute_adoption_intensity()`'s
  docstring for the exact ratio thresholds). A different question from the
  purity-gate's "by agent adoption intensity" table: that one asks whether
  the *rejection rate* varies by bucket; this asks how many repos *are* in
  each bucket -- i.e. how representative Dataset A's repo pool is of
  heavy vs. token agent usage. Reported overall, and per language as a
  funnel (Config -> No commits -> adoption tiers) -- the latter is the
  exact shape of the paper's funnel/adoption table
  (`\ref{tab:adoption-intensity}`).

  Known limitation (not fixed here): only the bucket label is persisted,
  not the underlying numeric ratio (agent commits / total commits since
  AGENT_CORPUS_START_DATE) that produced it -- that ratio is a local
  variable inside `compute_adoption_intensity()`, never written to the DB.
  This section can report bucket membership, not a continuous distribution
  or a mean ratio, without adding new instrumentation there.

- **Commits and repositories summary** (Dataset A, Dataset C): a compact,
  per-language funnel of how many commits/repos survived each stage of
  collection -- Dataset A's "how many candidate repos existed, how many had
  an agent config file, how many had an agent commit at all, how many of
  those touched tests, how many involved mocks", and Dataset C's "how many
  candidate repos existed, how many were within the 2016-2020 creation
  window, how many actually contributed fixtures/mocks". The exact shape of
  the paper's two summary tables -- row/column names match so this can be
  copied over without relabeling.

  Sourced from three places, not just db/*.db like the rest of this file:
  db/a.db and db/c.db (repository/fixture counts), the raw SEART
  search export (`github-search-raw/*.csv.gz` -- the "Candidate repos" row,
  identical for A and C since both draw from the same export, see
  `paths.py::default_repo_source()`), and Dataset A's own commit-discovery
  CSVs (`datasets/a/commits/*.csv`, the only place a couple of these counts
  exist at all -- `db/a.db` only stores counts of commits *touching tests*,
  not every agent commit found). "Mock commits"/"With mock commits" are a
  newly-*derived* concept (a commit/repo counts if it introduced >=1
  fixture with `num_mocks > 0`) -- nothing tracked this before, but it's a
  plain query over already-persisted columns, not new instrumentation.

  "All commits" is DB-sourced too (`repositories.total_commits_since_
  agent_start`, `SUM(...)` grouped by language) -- not full repository
  lifetime history, but non-merge commits since AGENT_CORPUS_START_DATE,
  the same window/repo population as the rows below it in the table.
  `agent_corpus.py`'s `analyze` stage already computed this number live (to
  derive `agent_adoption_intensity`) but discarded it before this change;
  it's now persisted going forward, and repos collected before this column
  existed needed a one-time backfill (re-clone + re-derive via the exact
  same `count_total_commits_since()` call, so backfilled and freshly
  collected rows mean the same thing) -- see
  `repository_quality_control/backfill_total_commits.py`. Any repo still
  missing the column (backfill not run, or its re-clone failed) is simply
  excluded from the sum rather than counted as 0.

  Dataset C's "With any fixtures"/"With any mocks" rows read the full
  `db/c.db`, same as every other "c" reference in `research_questions/`
  now that Dataset C sampling is deactivated (see
  `_shared.py::require_db_or_none()`'s docstring) -- "Candidate repos"/
  "Created within 2016-2020" read the original collection CSVs either way,
  since sampling was always a later, analysis-time step that never
  touched those.

- **Fixture counts by language**: total extracted fixtures per language,
  per dataset (A and C), straight from `db/*.db`, grouped by each
  fixture's own detected language (`test_files.language`) rather than its
  repo's tagged language. Deliberately a different grouping from rq1.py's
  "Cross-language fixture leakage" table, which groups by repo language
  instead -- that table's per-language totals include leaked fixtures
  written in a different language than their repo's tag, so it isn't a
  clean "how many fixtures exist per language" answer. This section is.

- **Dataset C sampling-down summary**: how `sample-c-repos --match-dataset
  a` actually stratified the sample -- per-language "Dataset C's own mix"
  vs. the match dataset's mix it targeted vs. what was actually achieved,
  plus repos/fixtures sampled per language. No `db/*.db` involved: reads
  `output/sample_c_repos.json` directly (`dataset_pipeline.py::
  sample_dataset_c_repos()`'s own summary artifact), since the sampled
  repo IDs are one specific historical draw, not something generically
  recomputable from current DB state. Makes a language-stratum shortfall
  (Dataset C doesn't have enough repos of some language to hit the match
  dataset's share) visible -- "Repos sampled" hitting its available count
  means that language's shortfall was redistributed elsewhere, not
  silently dropped (see `dataset_sampler.py::
  _allocate_quotas_with_shortfall_reallocation()`).

- **JS/TS hook fixture complexity (Lizard `function_list` selection)**: a
  side note, not a comparison -- exact (not sampled) count of
  `before_each`/`after_each` fixtures whose recorded
  `cyclomatic_complexity` disagrees with the true outer hook function's
  own complexity. Lizard orders `function_list` by parse-completion, not
  source position, so a nested closure inside the hook body (a
  `.catch(() => {})`, a mock callback) that finishes parsing before the
  outer hook does can end up at `function_list[0]` -- the entry
  `analyze_function_complexity()` unconditionally reads -- silently
  displacing the outer hook's own complexity. See
  `internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md`
  for the full investigation (an 80-fixture manual/sampled check found
  this in ~16% of Dataset A's at-risk subset, ~0% of Dataset C's). This
  re-runs Lizard directly against every already-stored `raw_source` that
  contains a likely nested construct (no network, no re-collection --
  cheap enough to check exactly rather than sample) and reports the real
  mismatch count/rate.

- **Mocha bare `before()`/`after()` detection (member-expression false
  positives)**: a side note and regression guard, not a comparison --
  count of `mocha_before`/`mocha_after` fixtures whose `raw_source`
  does *not* start with a bare `before(`/`after(` call, i.e. would
  indicate the `page.after()`/`browser.before()` false-positive shape
  investigated in
  `internal-docs/methodology-improvements/mocha-before-after-detection.md`.
  That investigation found this is structurally impossible given the
  detector's exact full-text-equality matching (confirmed 0/80 in a
  manual sample) -- tracked here as an ongoing regression guard: this
  should always read 0, and a nonzero value on some future re-collection
  would mean the detector's matching logic changed in a way that broke
  that guarantee.

- **Aliased mock import detection (Python)**: a side note, not a
  comparison -- count of Python fixtures whose `raw_source` contains a
  direct class/function-level mock alias (`from unittest.mock import
  patch as p`, etc.), the one pattern that actually breaks the
  regex-based mock detector (aliasing the `unittest.mock` *module*
  itself, e.g. `import unittest.mock as mock`, does not -- the patterns
  match on the bare `Mock`/`MagicMock`/`AsyncMock`/`patch` token
  regardless of what precedes it). See
  `internal-docs/methodology-improvements/aliased-mock-import-prevalence.md`.
  This DB-only check can only ever catch an alias declared *inside* a
  fixture body (a local import) -- the far more common top-of-file form
  is invisible to it by construction, since `raw_source` is
  function-body-only (see that same doc's §3). A 0 here does not mean
  zero true prevalence, only zero *detectable-from-this-DB* prevalence
  -- the investigation doc's real-file sampling is what actually
  calibrates the true rate (found ~0% there too, but via a different,
  network-dependent method this script deliberately doesn't replicate).

- **Mock-category fallback rate**: a side note, not a comparison --
  `mock_usages.category='mock'` is both a real, specific test-double
  category (a "mock" keyword literally found in the fixture body) *and*
  the classifier's catch-all fallback when none of the 5 category terms
  (`dummy`/`stub`/`spy`/`fake`/`mock`) appear anywhere at all
  (`_classify_mock_category()`, `detector_shared.py`) -- nothing in the
  schema distinguishes which happened for a given row. This exactly
  reconstructs that split (checking whether the fixture's own
  `raw_source` contains "mock" is exact, not approximate, for
  `category='mock'` rows specifically -- see
  `internal-docs/methodology-improvements/mock-category-fallback-analysis.md`
  for why), plus a finer 3-way split (framework-API-name match vs.
  naming-only positive match vs. true fallback) and the same split per
  language -- the per-language view matters here specifically because
  the pooled Dataset A vs. C fallback-rate difference turned out to be
  almost entirely a Python/`monkeypatch`-adoption artifact that *reverses
  direction* for JS/TS, a nuance a pooled-only number would hide.

- **JUnit 3 fallback detection (Java)**: a side note, not a comparison --
  raw counts of `junit3_setup`/`junit3_teardown` fixtures (Java's only
  unannotated fixture_types, matched by method name plus a plain substring
  check on the enclosing class's superclass -- see
  `internal-docs/methodology-improvements/junit3-fallback-detection.md`
  for the full investigation of exactly what that check does and does
  not verify). Tracked here purely so the count is visible on every future
  re-collection -- a large jump would be worth re-checking by hand the way
  the investigation above did, since the check's imprecision (a substring
  match, not exact-name or recursive type resolution) means it's a
  plausible place for a re-collection to quietly pick up a false positive.
  Reports Dataset A and Dataset C (the full `db/c.db`, same as every
  other "c" reference in `research_questions/` now that Dataset C
  sampling is deactivated -- see `_shared.py::require_db_or_none()`'s
  docstring).

python -m collection.research_questions.dataset_findings
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lizard import analyze_file as lizard_analyze_file

from .. import paths
from ..complexity_provider import _get_extension
from ..dataset_pipeline import _sample_repos_output_path
from ..db import db_session
from ..logging_utils import get_logger
from ._shared import (
    OUTPUT_DIR,
    fmt,
    require_db_or_none,
    summarize_continuous,
    write_markdown_report,
)

logger = get_logger(__name__)

_UNSET_LABEL = "(not set)"


@dataclass
class RepoPurityStats:
    repo_id: int
    full_name: str
    language: str
    adoption_intensity: str | None
    touching_tests: int
    rejected: int
    accepted: int

    @property
    def unclassified(self) -> int:
        """Commits counted in `touching_tests` that ended up in neither
        bucket -- `agent_corpus.py` swallows per-commit extraction
        exceptions (network/parse errors) without classifying the commit as
        accepted or rejected. Usually 0; a nonzero value here is itself a
        data-quality signal, not a bug in this script."""
        return self.touching_tests - self.accepted - self.rejected

    @property
    def rejection_rate(self) -> float | None:
        return self.rejected / self.touching_tests if self.touching_tests else None


def load_repo_purity_stats(*, db_root: Path = paths.DB_ROOT) -> list[RepoPurityStats] | None:
    """Per-repo purity-gate counters for every Dataset A repo, or None if
    db/a.db doesn't exist yet. Includes repos with 0 touching_tests (e.g. no
    agent commits found at all) -- callers that need rates should filter on
    `touching_tests > 0` themselves, since a 0/0 rate is undefined, not 0%."""
    db_file = require_db_or_none("a", db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        rows = conn.execute(
            "SELECT id, full_name, language, agent_adoption_intensity, "
            "agent_commits_touching_tests, agent_commits_rejected_mixed_test_diff, "
            "agent_commits_accepted FROM repositories"
        ).fetchall()

    return [
        RepoPurityStats(
            repo_id=row[0],
            full_name=row[1],
            language=row[2],
            adoption_intensity=row[3],
            touching_tests=row[4] or 0,
            rejected=row[5] or 0,
            accepted=row[6] or 0,
        )
        for row in rows
    ]


def _aggregate(stats: list[RepoPurityStats]) -> dict:
    touching = sum(s.touching_tests for s in stats)
    rejected = sum(s.rejected for s in stats)
    accepted = sum(s.accepted for s in stats)
    return {
        "n_repos": len(stats),
        "touching": touching,
        "rejected": rejected,
        "accepted": accepted,
        "unclassified": touching - accepted - rejected,
        "rejection_rate": rejected / touching if touching else None,
    }


def _group_by(stats: list[RepoPurityStats], key: str) -> dict[str, list[RepoPurityStats]]:
    groups: dict[str, list[RepoPurityStats]] = {}
    for s in stats:
        label = getattr(s, key) or _UNSET_LABEL
        groups.setdefault(label, []).append(s)
    return groups


def _render_totals(stats: list[RepoPurityStats]) -> str:
    active = [s for s in stats if s.touching_tests > 0]
    agg = _aggregate(stats)
    rate = agg["rejection_rate"]
    lines = [
        f"{len(active):,}/{agg['n_repos']:,} repos had >=1 agent commit touching a test file.",
        "",
        "| Touching tests | Accepted (pure addition) | Rejected (mixed diff) | Unclassified "
        "(extraction error) | Rejection rate |",
        "|---|---|---|---|---|",
        f"| {agg['touching']:,} | {agg['accepted']:,} | {agg['rejected']:,} | "
        f"{agg['unclassified']:,} | {fmt(100 * rate, 2) + '%' if rate is not None else '--'} |",
        "",
    ]
    return "\n".join(lines)


def _render_group_table(title: str, groups: dict[str, list[RepoPurityStats]]) -> str:
    lines = [f"**{title}**", "", "| Group | Repos | Touching tests | Rejected | Rejection rate |", "|---|---|---|---|---|"]
    for label, group_stats in sorted(groups.items(), key=lambda kv: -_aggregate(kv[1])["touching"]):
        agg = _aggregate(group_stats)
        rate = agg["rejection_rate"]
        lines.append(
            f"| {label} | {agg['n_repos']:,} | {agg['touching']:,} | {agg['rejected']:,} | "
            f"{fmt(100 * rate, 2) + '%' if rate is not None else '--'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_repo_distribution(stats: list[RepoPurityStats]) -> str:
    """Per-repo rejection-rate distribution -- distinguishes "every repo
    rejects about a third of its test-touching commits" from "most repos
    reject 0%, a handful reject 100%", which the corpus-wide aggregate rate
    alone can't tell apart."""
    active = [s for s in stats if s.touching_tests > 0]
    rates = [s.rejection_rate for s in active]
    summary = summarize_continuous(rates)
    fully_rejected = sum(1 for r in rates if r == 1.0)
    fully_accepted_only = sum(1 for r in rates if r == 0.0)

    lines = [
        "**Per-repo rejection-rate distribution** (one rate per repo with "
        ">=1 test-touching commit -- each repo counted once, not weighted "
        "by its commit volume)",
        "",
        "| N repos | Median | Mean | Stdev | Min | Max | Repos at 0% rejected | "
        "Repos at 100% rejected |",
        "|---|---|---|---|---|---|---|---|",
        f"| {summary['n']:,} | {fmt(summary['median'], 3)} | {fmt(summary['mean'], 3)} | "
        f"{fmt(summary['stdev'], 3)} | {fmt(summary['min'], 3)} | {fmt(summary['max'], 3)} | "
        f"{fully_accepted_only:,} | {fully_rejected:,} |",
        "",
    ]
    return "\n".join(lines)


_ADOPTION_INTENSITY_ORDER = [
    "no_commits",
    "experimental",
    "limited",
    "consistent",
    "pervasive",
    _UNSET_LABEL,
]


def _render_adoption_intensity_distribution(stats: list[RepoPurityStats]) -> str:
    """How Dataset A's whole repo pool -- every repo that reached the
    agent-commit scan, not just the ones with test-touching commits --
    splits across agent_adoption_intensity buckets. `(not set)` covers repos
    that never reached the adoption-intensity computation at all (e.g. clone
    failed before the scan ran)."""
    groups = _group_by(stats, "adoption_intensity")
    total = len(stats)
    ordered_labels = [label for label in _ADOPTION_INTENSITY_ORDER if label in groups]
    ordered_labels += sorted(label for label in groups if label not in _ADOPTION_INTENSITY_ORDER)

    lines = [
        "| Bucket | Repos | % of Dataset A repos |",
        "|---|---|---|",
    ]
    for label in ordered_labels:
        n = len(groups[label])
        lines.append(f"| {label} | {n:,} | {100 * n / total:.2f}% |")
    lines.append("")
    return "\n".join(lines)


def _cell(count: int, row_total: int) -> str:
    pct = 100 * count / row_total if row_total else 0.0
    return f"{count:,} ({pct:.2f}%)"


_LANGUAGE_DISPLAY_NAMES = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
}

_BUCKET_DISPLAY_NAMES = {
    "no_commits": "No commits",
    "experimental": "Experimental",
    "limited": "Limited",
    "consistent": "Consistent",
    "pervasive": "Pervasive",
}


def _render_adoption_intensity_funnel_by_language(stats: list[RepoPurityStats]) -> str:
    """Combines the agent-config funnel with the adoption-intensity
    breakdown into one row per language -- the exact shape of the paper's
    funnel/adoption table (`\\ref{tab:adoption-intensity}`); column/row
    names match that table's wording exactly so this can be copied over
    without relabeling.

    Agent Configuration Present is every repo with an agent_adoption_
    intensity value at all (that field is only ever computed for repos
    already known to have an agent config file, so it's just that row's
    full count -- the funnel's entry point). No commits and the adoption
    tiers (Experimental/Limited/Consistent/Pervasive) each report their
    share of Agent Configuration Present, so those percentages sum to 100%
    per row (barring any "(not set)" repos, see below). Agent Active Total
    is Agent Configuration Present minus No commits: the repos that
    actually had >=1 detectable agent commit.

    "(not set)" -- adoption_intensity never computed at all, e.g. a failed
    clone before the scan ran -- only gets its own column if at least one
    repo actually has it (none do in the current corpus); that case means
    "unknown," not "confirmed zero," so it's excluded from Agent Active
    Total same as No commits would be, not folded into either bucket."""
    by_language = _group_by(stats, "language")
    buckets = [
        label
        for label in _ADOPTION_INTENSITY_ORDER
        if any(s.adoption_intensity == label for s in stats)
        or (label == _UNSET_LABEL and any(s.adoption_intensity is None for s in stats))
    ]
    bucket_headers = [_BUCKET_DISPLAY_NAMES.get(b, b) for b in buckets]
    non_adopted = {"no_commits", _UNSET_LABEL}

    header = (
        ["Language", "Agent Configuration Present"]
        + bucket_headers
        + ["Agent Active Total"]
    )
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    column_totals = dict.fromkeys(buckets, 0)
    grand_config = 0
    grand_total = 0
    for lang in sorted(by_language):
        lang_groups = _group_by(by_language[lang], "adoption_intensity")
        counts = [len(lang_groups.get(label, [])) for label in buckets]
        config = sum(counts)
        adopted_total = config - sum(
            c for label, c in zip(buckets, counts) if label in non_adopted
        )
        cells = [_cell(c, config) for c in counts]
        lang_display = _LANGUAGE_DISPLAY_NAMES.get(lang, lang)
        lines.append(
            f"| {lang_display} | {config:,} | "
            + " | ".join(cells)
            + f" | {adopted_total:,} |"
        )
        for label, c in zip(buckets, counts):
            column_totals[label] += c
        grand_config += config
        grand_total += adopted_total
    total_cells = [_cell(column_totals[label], grand_config) for label in buckets]
    lines.append(
        "| **Total (All Languages)** | "
        + f"{grand_config:,} | "
        + " | ".join(total_cells)
        + f" | {grand_total:,} |"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commits and repositories summary (Dataset A, Dataset C)
# ---------------------------------------------------------------------------

_SUMMARY_TABLE_LANGUAGES = ["java", "javascript", "python", "typescript"]


def _fetch_raw_seart_repo_counts(
    raw_search_dir: Path = paths.RAW_SEARCH_DIR,
) -> dict[str, int] | None:
    """Row count per raw SEART search export file (github-search-raw/
    {language}.csv.gz) -- the "Candidate repos" row: the pool BEFORE any
    date-window/agent-config filtering, identical for Dataset A and Dataset
    C since both draw from this same raw export (see
    paths.py::default_repo_source()). None if the directory doesn't exist
    (e.g. not collected in this environment) -- callers render that as an
    "N/A" row rather than a false zero."""
    if not raw_search_dir.exists():
        return None
    counts: dict[str, int] = {}
    for csv_path in sorted(raw_search_dir.glob("*.csv.gz")):
        language = csv_path.name.removesuffix(".csv.gz").lower()
        with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
            counts[language] = sum(1 for _ in csv.reader(fh)) - 1
    return counts or None


def _fetch_csv_row_counts(csv_dir: Path, suffix: str) -> dict[str, int] | None:
    """Row count per per-language CSV file matching `*{suffix}` in
    `csv_dir`, language = filename with `suffix` stripped. None if
    `csv_dir` doesn't exist. Used for "Agent commits"
    (datasets/a/commits/, suffix "_commit.csv") and "Created within
    2016-2020" (datasets/c/repos/, suffix "_repo.csv")."""
    if not csv_dir.exists():
        return None
    counts: dict[str, int] = {}
    for csv_path in sorted(csv_dir.glob(f"*{suffix}")):
        language = csv_path.name[: -len(suffix)].lower()
        with csv_path.open(encoding="utf-8", newline="") as fh:
            counts[language] = sum(1 for _ in csv.reader(fh)) - 1
    return counts or None


def _fetch_csv_unique_repo_counts(csv_dir: Path, suffix: str) -> dict[str, int] | None:
    """Unique `repo_name` count per per-language CSV file matching
    `*{suffix}` in `csv_dir`. None if `csv_dir` doesn't exist. Used for
    "With agent commits" -- no db/a.db equivalent exists, since
    `agent_commits_accepted`/`agent_commits_touching_tests` are both
    test-touching-scoped only, not "any agent commit at all"."""
    if not csv_dir.exists():
        return None
    counts: dict[str, int] = {}
    for csv_path in sorted(csv_dir.glob(f"*{suffix}")):
        language = csv_path.name[: -len(suffix)].lower()
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            counts[language] = len({row["repo_name"] for row in reader})
    return counts or None


def _fetch_repos_with_agent_config(conn: sqlite3.Connection) -> dict[str, int]:
    """"With agent files or directories" -- same query already backing the
    funnel table's "Agent Configuration Present" (agent_adoption_intensity
    is only ever computed for repos already known to have an agent config
    file)."""
    rows = conn.execute(
        "SELECT language, COUNT(*) FROM repositories "
        "WHERE agent_adoption_intensity IS NOT NULL GROUP BY language"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _fetch_agent_commits_touching_tests(conn: sqlite3.Connection) -> dict[str, int]:
    """"Test commits" -- SUM(agent_commits_touching_tests), not the
    datasets/a/test-commits/*.csv row count: those CSVs were found to be
    stale relative to db/a.db (older mtime, lower counts) -- the DB is
    refreshed on every extract-fixtures run and is the more current source
    of truth."""
    rows = conn.execute(
        "SELECT language, SUM(agent_commits_touching_tests) FROM repositories GROUP BY language"
    ).fetchall()
    return {row[0]: row[1] or 0 for row in rows}


def _fetch_total_commits_since_agent_start(conn: sqlite3.Connection) -> dict[str, int] | None:
    """"All commits" -- SUM(total_commits_since_agent_start), live from
    db/a.db. Non-merge commits (agent, human, and bot alike) since
    AGENT_CORPUS_START_DATE, on HEAD -- agent_corpus.py's `analyze` stage
    already computes this per repo (count_total_commits_since()) to derive
    agent_adoption_intensity, and now persists it too. Repos collected
    before that column existed (or that failed to re-clone during the
    one-time backfill, see repository_quality_control/backfill_total_commits.py)
    have it NULL -- excluded here (not counted as 0), so a partial backfill
    under-counts rather than producing a misleadingly-precise-looking wrong
    number.

    Returns None (renders as the table's usual "N/A" row, not a crash) if
    the column doesn't exist at all yet -- a db/a.db collected before this
    column was added, and not yet self-healed by running
    `backfill_total_commits.py` (its `run()` calls `initialise_db()`, which
    adds the column; this script never does, deliberately -- a read-only
    report generator shouldn't mutate the DB it's reading as a side effect)."""
    try:
        rows = conn.execute(
            "SELECT language, SUM(total_commits_since_agent_start) FROM repositories "
            "WHERE total_commits_since_agent_start IS NOT NULL GROUP BY language"
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    return {row[0]: row[1] or 0 for row in rows}


def _fetch_repos_with_test_commits(conn: sqlite3.Connection) -> dict[str, int]:
    """"With test commits" -- DB-sourced, same authority reasoning as
    _fetch_agent_commits_touching_tests()."""
    rows = conn.execute(
        "SELECT language, COUNT(*) FROM repositories "
        "WHERE agent_commits_touching_tests > 0 GROUP BY language"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _fetch_mock_commit_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """"Mock commits" -- distinct commits that introduced >=1 fixture with
    num_mocks > 0. Dataset A only -- Dataset C's own summary table has no
    "Mock commits" row (commit-level granularity doesn't apply to a
    cross-repo snapshot collection the way it does to Dataset A's
    per-commit scan)."""
    rows = conn.execute(
        "SELECT r.language, COUNT(DISTINCT f.commit_sha) FROM fixtures f "
        "JOIN repositories r ON f.repo_id = r.id "
        "WHERE f.num_mocks > 0 AND f.commit_sha != '' GROUP BY r.language"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _fetch_repos_with_mocks(conn: sqlite3.Connection) -> dict[str, int]:
    """"With mock commits" / "With any mocks" -- distinct repos with >=1
    fixture using a mock. Reused as-is for both Dataset A's and Dataset C's
    tables."""
    rows = conn.execute(
        "SELECT r.language, COUNT(DISTINCT f.repo_id) FROM fixtures f "
        "JOIN repositories r ON f.repo_id = r.id "
        "WHERE f.num_mocks > 0 GROUP BY r.language"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _fetch_repos_with_fixtures(conn: sqlite3.Connection) -> dict[str, int]:
    """"With any fixtures" (Dataset C only)."""
    rows = conn.execute(
        "SELECT language, COUNT(*) FROM repositories WHERE num_fixtures > 0 GROUP BY language"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _fetch_fixture_counts_by_own_language(conn: sqlite3.Connection) -> dict[str, int]:
    """Total fixture count grouped by each fixture's OWN detected language
    (`test_files.language`) -- not its repo's tagged language
    (`repositories.language`). Deliberately a different grouping than
    rq1.py's "Cross-language fixture leakage" table, which groups by repo
    language: there, a repo tagged `python` with some leaked JavaScript
    test files still has all of those fixtures counted under `python`'s
    "Total fixtures" row, since that table is about *how much* leakage a
    repo-language bucket contains. Here, every fixture is counted under
    the language it's actually written in, so leakage doesn't inflate any
    bucket -- a leaked JavaScript fixture found inside a Python-tagged
    repo counts under `javascript`, not `python`. Both groupings sum to
    the same dataset-wide total; only the per-language split differs.
    """
    rows = conn.execute(
        """
        SELECT tf.language, COUNT(*)
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        GROUP BY tf.language
        """
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _render_language_count_table(
    row_label_header: str, rows: list[tuple[str, dict[str, int] | None]]
) -> str:
    """Markdown table: `{row_label_header} | Java | JavaScript | Python |
    TypeScript | Total` -- the shared shape behind both the Commits and
    Repositories summary tables (Dataset A and Dataset C). A row whose
    dict is None renders "N/A" across every column -- used when a row's
    source directory doesn't exist in this environment, so a missing input
    degrades one row, not the whole table."""
    header = (
        [row_label_header]
        + [_LANGUAGE_DISPLAY_NAMES[lang] for lang in _SUMMARY_TABLE_LANGUAGES]
        + ["Total"]
    )
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for label, counts in rows:
        if counts is None:
            lines.append(f"| {label} | " + " | ".join(["N/A"] * (len(_SUMMARY_TABLE_LANGUAGES) + 1)) + " |")
            continue
        cells = [counts.get(lang, 0) for lang in _SUMMARY_TABLE_LANGUAGES]
        total = sum(cells)
        lines.append(f"| {label} | " + " | ".join(f"{c:,}" for c in cells) + f" | {total:,} |")
    lines.append("")
    return "\n".join(lines)


def _render_dataset_a_commit_repo_summary(
    *,
    db_root: Path = paths.DB_ROOT,
    datasets_root: Path = paths.DATASETS_ROOT,
    raw_search_dir: Path = paths.RAW_SEARCH_DIR,
) -> list[str]:
    """## Dataset A: Commits and Repositories Summary -- see this module's
    docstring for the full per-row data-source breakdown. Independently
    gated on db/a.db (most rows need it); the CSV/raw-SEART-sourced rows
    each degrade to their own "N/A" row if their source directory is
    missing, rather than failing the whole section."""
    db_file = require_db_or_none("a", db_root)
    if db_file is None:
        return [
            "## Dataset A: Commits and Repositories Summary",
            "",
            "_Not available -- db/a.db not collected yet._",
            "",
        ]

    with db_session(db_file) as conn:
        total_commits_since_agent_start = _fetch_total_commits_since_agent_start(conn)
        agent_commits_touching_tests = _fetch_agent_commits_touching_tests(conn)
        repos_with_test_commits = _fetch_repos_with_test_commits(conn)
        mock_commit_counts = _fetch_mock_commit_counts(conn)
        repos_with_mocks = _fetch_repos_with_mocks(conn)
        repos_with_agent_config = _fetch_repos_with_agent_config(conn)

    commits_dir = datasets_root / "a" / "commits"
    agent_commits = _fetch_csv_row_counts(commits_dir, "_commit.csv")
    repos_with_agent_commits = _fetch_csv_unique_repo_counts(commits_dir, "_commit.csv")
    candidate_repos = _fetch_raw_seart_repo_counts(raw_search_dir)

    return [
        "## Dataset A: Commits and Repositories Summary",
        "",
        '"All commits" counts non-merge commits (agent, human, and bot '
        "alike) since AGENT_CORPUS_START_DATE -- not full repository "
        "lifetime history -- among repos with an agent config file present; "
        "the same window and repo population as the rows below it, not an "
        "independent measure.",
        "",
        "### Commits",
        "",
        _render_language_count_table(
            "Commits",
            [
                ("All commits", total_commits_since_agent_start),
                ("Agent commits", agent_commits),
                ("Test commits", agent_commits_touching_tests),
                ("Mock commits", mock_commit_counts),
            ],
        ),
        "### Repositories",
        "",
        _render_language_count_table(
            "Repositories",
            [
                ("Candidate repos", candidate_repos),
                ("With agent files or directories", repos_with_agent_config),
                ("With agent commits", repos_with_agent_commits),
                ("With test commits", repos_with_test_commits),
                ("With mock commits", repos_with_mocks),
            ],
        ),
    ]


def _render_dataset_c_repo_summary(
    *,
    db_root: Path = paths.DB_ROOT,
    datasets_root: Path = paths.DATASETS_ROOT,
    raw_search_dir: Path = paths.RAW_SEARCH_DIR,
) -> list[str]:
    """## Dataset C: Repository Summary -- reads the full db/c.db (via
    require_db_or_none("c", ...), same as every other dataset now that
    Dataset C sampling is deactivated -- see that function's docstring).
    "Candidate repos"/"Created within 2016-2020" are unaffected either way
    -- they describe the original collection funnel, which sampling (a
    later, analysis-time step) never touched even when it was active."""
    candidate_repos = _fetch_raw_seart_repo_counts(raw_search_dir)
    created_in_window = _fetch_csv_row_counts(datasets_root / "c" / "repos", "_repo.csv")

    db_file = require_db_or_none("c", db_root)
    if db_file is None:
        with_fixtures: dict[str, int] | None = None
        with_mocks: dict[str, int] | None = None
    else:
        with db_session(db_file) as conn:
            with_fixtures = _fetch_repos_with_fixtures(conn)
            with_mocks = _fetch_repos_with_mocks(conn)

    return [
        "## Dataset C: Repository Summary",
        "",
        _render_language_count_table(
            "Repositories",
            [
                ("Candidate repos", candidate_repos),
                ("Created within 2016-2020", created_in_window),
                ("With any fixtures", with_fixtures),
                ("With any mocks", with_mocks),
            ],
        ),
    ]


def _render_fixture_counts_by_language_summary(
    *, db_root: Path = paths.DB_ROOT
) -> list[str]:
    """## Fixture Counts by Language -- total extracted fixtures per
    language, per dataset, from `db/a.db`/`db/c.db` directly. Counts each
    fixture under its own detected language
    (`_fetch_fixture_counts_by_own_language()`), not its repo's tagged
    language -- a different grouping than rq1.py's "Cross-language
    fixture leakage" table, whose "Total fixtures" column groups by repo
    language instead (so that table's per-language totals include leaked
    fixtures written in a different language). Each dataset degrades to
    its own "N/A" row if its db isn't collected yet, rather than failing
    the whole section."""
    a_db = require_db_or_none("a", db_root)
    a_counts: dict[str, int] | None = None
    if a_db is not None:
        with db_session(a_db) as conn:
            a_counts = _fetch_fixture_counts_by_own_language(conn)

    c_db = require_db_or_none("c", db_root)
    c_counts: dict[str, int] | None = None
    if c_db is not None:
        with db_session(c_db) as conn:
            c_counts = _fetch_fixture_counts_by_own_language(conn)

    return [
        "## Fixture Counts by Language",
        "",
        "Total extracted fixtures per language, per dataset, counted by "
        "each fixture's own detected language -- not its repo's tagged "
        "language. This is a different grouping than the "
        '"Cross-language fixture leakage" table in rq1.md\'s per-dataset '
        "summaries, which groups by repo language instead, so a repo's "
        "language bucket there includes any fixtures written in a "
        "different language that were found inside it. The numbers here "
        "are the clean per-language totals -- a leaked fixture counts "
        "under the language it's actually written in, not its repo's "
        "tag.",
        "",
        _render_language_count_table(
            "Dataset",
            [
                ("Dataset A (agent-authored)", a_counts),
                ("Dataset C (human-authored, pre-LLM)", c_counts),
            ],
        ),
    ]


def _render_dataset_c_sampling_summary(*, output_dir: Path | None = None) -> list[str]:
    """## Dataset C: Sampling-Down Summary -- reads output/sample_c_repos.json,
    the artifact `sample-c-repos`/`sample_dataset_c_repos()` writes on every
    run (dataset_pipeline.py). Not derived from db/c_sampled.db: the actual
    sampled repo IDs are one specific historical draw (seeded, but tied to
    whatever db/c.db and the match dataset looked like at that call time),
    not something generically recomputable from current DB state.

    "Not available" if the file doesn't exist yet -- same degrade-gracefully
    convention as every other section in this module."""
    summary_path = _sample_repos_output_path(output_dir)
    if not summary_path.exists():
        return [
            "## Dataset C: Sampling-Down Summary",
            "",
            "_Not available -- run `python -m collection sample-c-repos "
            "--match-dataset a` first._",
            "",
        ]

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    match_dataset = data.get("match_dataset")
    distribution_check: dict[str, dict] = data.get("distribution_check", {})

    header = [
        "Language",
        "Dataset C's own mix",
        f"Target ({match_dataset or 'n/a'}'s mix)",
        "Sampled mix",
        "Repos sampled",
        "Fixtures sampled",
    ]
    lines = [
        "## Dataset C: Sampling-Down Summary",
        "",
        f"Matched against Dataset {match_dataset}: "
        f"{data.get('sampled_fixture_count', 0):,}/{data.get('target_count', 0):,} "
        f"fixtures, {data.get('sampled_repo_count', 0):,} repos, "
        f"seed={data.get('random_seed')}.",
        "",
        'A language whose "Repos sampled" hits its full available count '
        "took everything Dataset C had for it and still fell short of the "
        "target mix -- the shortfall was redistributed to the other "
        "languages, not discarded (see `_allocate_quotas_with_shortfall_"
        "reallocation()` in `dataset_sampler.py`).",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for language in _SUMMARY_TABLE_LANGUAGES:
        check = distribution_check.get(language)
        display = _LANGUAGE_DISPLAY_NAMES[language]
        if check is None:
            lines.append(f"| {display} | N/A | N/A | N/A | N/A | N/A |")
            continue
        available_repos = check.get("dataset_c_available_repo_count", 0)
        sampled_repos = check.get("sampled_repo_count", 0)
        exhausted = " (all)" if available_repos and sampled_repos >= available_repos else ""
        lines.append(
            f"| {display} "
            f"| {check['original_ratio'] * 100:.1f}% "
            f"| {check['target_ratio'] * 100:.1f}% "
            f"| {check['sampled_ratio'] * 100:.1f}% "
            f"| {sampled_repos:,}/{available_repos:,}{exhausted} "
            f"| {check.get('sampled_fixture_count', 0):,}/{check.get('dataset_c_available_fixture_count', 0):,} |"
        )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# JUnit 3 fallback detection (Java) -- side note
# ---------------------------------------------------------------------------

_JUNIT3_FALLBACK_TYPES = ("junit3_setup", "junit3_teardown")


def _fetch_junit3_fallback_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Counts of junit3_setup/junit3_teardown in one already-open DB --
    Java's only fixture_types matched by an unannotated method name plus a
    substring check on the enclosing class's superclass
    (detector_java.py::_enclosing_class_extends_test_case()), rather than
    an annotation. Missing fixture_types (0 rows) are simply absent from
    the returned dict, same convention as this file's other _fetch_*
    helpers."""
    rows = conn.execute(
        "SELECT fixture_type, COUNT(*) FROM fixtures "
        "WHERE fixture_type IN (?, ?) GROUP BY fixture_type",
        _JUNIT3_FALLBACK_TYPES,
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _render_junit3_fallback_side_note(*, db_root: Path = paths.DB_ROOT) -> list[str]:
    """## JUnit 3 Fallback Detection (Java) -- see this module's docstring
    for why this is tracked. Dataset C reads the full db/c.db (via
    require_db_or_none()) now that Dataset C sampling is deactivated --
    see _shared.py::require_db_or_none()'s docstring."""
    header = ["Dataset", "junit3_setup", "junit3_teardown", "Total"]
    lines = [
        "## JUnit 3 Fallback Detection (Java)",
        "",
        "Side note, not a comparison: raw counts of `junit3_setup`/"
        "`junit3_teardown`, Java's only fixture_types identified without an "
        "annotation -- by method name plus a substring check on the "
        "enclosing class's superclass, which is not an exact-name or "
        "recursive type-resolution check. See "
        "`internal-docs/methodology-improvements/junit3-fallback-detection.md` "
        "for the full investigation (manual review of every instance found "
        "in both datasets at time of writing; all genuine, one only via "
        "substring coincidence). Tracked here so a re-collection that picks "
        "up a materially different count is easy to notice.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]

    def _row(label: str, counts: dict[str, int] | None) -> str:
        if counts is None:
            return f"| {label} | N/A | N/A | N/A |"
        setup = counts.get("junit3_setup", 0)
        teardown = counts.get("junit3_teardown", 0)
        return f"| {label} | {setup:,} | {teardown:,} | {setup + teardown:,} |"

    a_db = require_db_or_none("a", db_root)
    a_counts = None
    if a_db is not None:
        with db_session(a_db) as conn:
            a_counts = _fetch_junit3_fallback_counts(conn)
    lines.append(_row("Dataset A", a_counts))

    c_db = require_db_or_none("c", db_root)
    c_counts = None
    if c_db is not None:
        with db_session(c_db) as conn:
            c_counts = _fetch_junit3_fallback_counts(conn)
    lines.append(_row("Dataset C", c_counts))

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# JS/TS hook fixture complexity (Lizard function_list selection) -- side note
# ---------------------------------------------------------------------------

_JS_HOOK_FIXTURE_TYPES = ("before_each", "after_each")


def _has_nested_js_construct(raw_source: str) -> bool:
    """Crude heuristic: an extra '=>'/'function' token beyond the hook's
    own outer wrapper (`beforeEach(() => {...})` already accounts for
    exactly one) suggests a nested closure inside the fixture body -- the
    precondition for Lizard's function_list ordering issue (see
    js-ts-hook-fixture-complexity.md). False positives/negatives both
    possible (string literals containing "=>", a nested construct with no
    braces of its own); good enough to bound which fixtures are worth an
    actual Lizard re-run, not a precise parse."""
    arrow_count = raw_source.count("=>")
    func_kw_count = len(re.findall(r"\bfunction\b", raw_source))
    return (arrow_count - 1) + func_kw_count > 0


def _true_outer_hook_complexity(raw_source: str, language: str) -> int | None:
    """Re-run Lizard directly on one fixture's already-stored raw_source
    and return the cyclomatic_complexity of the function that actually
    starts at (or near) line 1 -- the hook's own outer wrapper, always the
    first token in a JS/TS hook's raw_source (`beforeEach(...)`/
    `afterEach(...)`). This is the complexity
    analyze_function_complexity() *should* report but doesn't whenever a
    nested closure closes first and lands at function_list[0] instead --
    see js-ts-hook-fixture-complexity.md §5. None if Lizard finds no
    function starting there (parse failure, or an empty function_list)."""
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=f".{_get_extension(language)}", delete=False, mode="w", encoding="utf-8"
        ) as fh:
            fh.write(raw_source)
            temp_file = Path(fh.name)
        result = lizard_analyze_file(str(temp_file))
        outer_candidates = [f for f in result.function_list if f.start_line <= 2]
        if not outer_candidates:
            return None
        outer = max(outer_candidates, key=lambda f: f.end_line)
        return outer.cyclomatic_complexity
    except Exception as e:
        logger.debug(f"Lizard re-run failed for JS/TS hook re-check: {type(e).__name__}: {e}")
        return None
    finally:
        if temp_file is not None:
            temp_file.unlink(missing_ok=True)


def _fetch_js_hook_complexity_mismatch(
    conn: sqlite3.Connection, *, fixture_types: tuple[str, ...] = _JS_HOOK_FIXTURE_TYPES
) -> dict:
    """Exact (not sampled) count of before_each/after_each fixtures whose
    recorded cyclomatic_complexity -- computed at collection time via
    function_list[0] -- disagrees with the true outer hook function's own
    complexity, re-derived by re-running Lizard directly against the
    already-stored raw_source. No network, no re-collection -- this reads
    data collection already persisted, same as every other section in
    this file -- so it's cheap enough to check every nested-construct
    fixture exactly rather than sample (~0.5ms/fixture; the full corpus
    across both datasets is a few seconds, not minutes)."""
    placeholders = ",".join("?" * len(fixture_types))
    rows = conn.execute(
        f"SELECT f.raw_source, f.cyclomatic_complexity, tf.language "
        f"FROM fixtures f JOIN test_files tf ON f.file_id = tf.id "
        f"WHERE f.fixture_type IN ({placeholders})",
        fixture_types,
    ).fetchall()

    total = len(rows)
    nested_construct = 0
    checked = 0
    mismatched = 0
    for raw_source, recorded_cc, language in rows:
        if not raw_source or not _has_nested_js_construct(raw_source):
            continue
        nested_construct += 1
        true_cc = _true_outer_hook_complexity(raw_source, language)
        if true_cc is None:
            continue
        checked += 1
        if true_cc != recorded_cc:
            mismatched += 1

    return {
        "total": total,
        "nested_construct": nested_construct,
        "checked": checked,
        "mismatched": mismatched,
    }


def _render_js_hook_complexity_side_note(*, db_root: Path = paths.DB_ROOT) -> list[str]:
    """## JS/TS Hook Fixture Complexity (Lizard function_list Selection)."""
    header = ["Dataset", "before_each/after_each", "Nested construct", "Re-checked", "Mismatched", "Mismatch rate"]
    lines = [
        "## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)",
        "",
        "Side note, not a comparison: exact re-check, not a sample, of "
        "whether each `before_each`/`after_each` fixture's recorded "
        "`cyclomatic_complexity` matches the true outer hook function's "
        "own complexity. Lizard orders `function_list` by parse-completion, "
        "not source position -- a nested closure (a `.catch(() => {})`, a "
        "mock callback) that finishes parsing before the outer hook does "
        "can land at `function_list[0]`, which "
        "`analyze_function_complexity()` unconditionally reads, silently "
        "displacing the outer hook's own complexity. Only fixtures whose "
        "`raw_source` contains a likely nested construct are re-checked "
        "(\"Nested construct\" column) -- that's the precondition for the "
        "issue at all. See "
        "`internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md` "
        "for the full investigation.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]

    def _row(label: str, result: dict | None) -> str:
        if result is None:
            return f"| {label} | N/A | N/A | N/A | N/A | N/A |"
        rate = 100 * result["mismatched"] / result["checked"] if result["checked"] else 0.0
        return (
            f"| {label} | {result['total']:,} | {result['nested_construct']:,} | "
            f"{result['checked']:,} | {result['mismatched']:,} | {rate:.2f}% |"
        )

    a_db = require_db_or_none("a", db_root)
    a_result = None
    if a_db is not None:
        with db_session(a_db) as conn:
            a_result = _fetch_js_hook_complexity_mismatch(conn)
    lines.append(_row("Dataset A", a_result))

    c_db = require_db_or_none("c", db_root)
    c_result = None
    if c_db is not None:
        with db_session(c_db) as conn:
            c_result = _fetch_js_hook_complexity_mismatch(conn)
    lines.append(_row("Dataset C", c_result))

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Mocha bare before()/after() detection -- regression guard, side note
# ---------------------------------------------------------------------------

_MOCHA_BARE_HOOK_TYPES = ("mocha_before", "mocha_after")
_MOCHA_BARE_CALL_RE = re.compile(r"^\s*(before|after)\s*\(")


def _fetch_mocha_bare_hook_non_bare_count(
    conn: sqlite3.Connection, *, fixture_types: tuple[str, ...] = _MOCHA_BARE_HOOK_TYPES
) -> dict:
    """Count of mocha_before/mocha_after fixtures whose raw_source does
    *not* start with a bare before(/after( call -- the shape a
    member-expression false positive (page.after(), browser.before())
    would have, per mocha-before-after-detection.md. Expected to always
    be 0 -- the detector's exact full-text-equality check makes that
    false-positive shape structurally impossible, not merely unobserved
    -- so this is a regression guard, not a live risk estimate: a nonzero
    value here on some future re-collection would mean the detector's own
    matching logic changed, not that this check found a real edge case it
    was designed to look for."""
    placeholders = ",".join("?" * len(fixture_types))
    rows = conn.execute(
        f"SELECT raw_source FROM fixtures WHERE fixture_type IN ({placeholders})",
        fixture_types,
    ).fetchall()
    total = len(rows)
    non_bare = sum(1 for (raw,) in rows if not raw or not _MOCHA_BARE_CALL_RE.match(raw))
    return {"total": total, "non_bare": non_bare}


def _render_mocha_bare_hook_side_note(*, db_root: Path = paths.DB_ROOT) -> list[str]:
    """## Mocha Bare before()/after() Detection (Regression Guard)."""
    header = ["Dataset", "mocha_before/mocha_after", "Non-bare-call shape"]
    lines = [
        "## Mocha Bare `before()`/`after()` Detection (Regression Guard)",
        "",
        "Side note, not a comparison, and not a live risk estimate -- "
        "count of `mocha_before`/`mocha_after` fixtures whose "
        "`raw_source` does not start with a bare `before(`/`after(` "
        "call, i.e. would indicate the `page.after()`/`browser.before()` "
        "false-positive shape investigated in "
        "`internal-docs/methodology-improvements/mocha-before-after-detection.md`. "
        "That investigation found this is structurally impossible given "
        "the detector's exact full-text-equality matching (confirmed 0/80 "
        "in a manual sample) -- this should always read 0; a nonzero value "
        "would mean the detector's matching logic regressed, not that a "
        "real edge case was found.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]

    def _row(label: str, result: dict | None) -> str:
        if result is None:
            return f"| {label} | N/A | N/A |"
        return f"| {label} | {result['total']:,} | {result['non_bare']:,} |"

    a_db = require_db_or_none("a", db_root)
    a_result = None
    if a_db is not None:
        with db_session(a_db) as conn:
            a_result = _fetch_mocha_bare_hook_non_bare_count(conn)
    lines.append(_row("Dataset A", a_result))

    c_db = require_db_or_none("c", db_root)
    c_result = None
    if c_db is not None:
        with db_session(c_db) as conn:
            c_result = _fetch_mocha_bare_hook_non_bare_count(conn)
    lines.append(_row("Dataset C", c_result))

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Aliased mock import detection (Python) -- side note
# ---------------------------------------------------------------------------

_ALIASED_MOCK_IMPORT_LIKE_PATTERNS = (
    "%import patch as%",
    "%import Mock as%",
    "%import MagicMock as%",
    "%import AsyncMock as%",
)


def _fetch_aliased_mock_import_counts(conn: sqlite3.Connection) -> dict:
    """Count of Python fixtures whose raw_source contains a direct
    class/function-level mock alias (`from unittest.mock import patch as
    p`, etc.) -- the one pattern that actually breaks the regex-based
    mock detector (aliasing the unittest.mock *module* itself, e.g.
    `import unittest.mock as mock`, does not -- MOCK_PATTERNS match the
    bare Mock/MagicMock/AsyncMock/patch token regardless of what precedes
    it). See aliased-mock-import-prevalence.md.

    This can only ever catch an alias declared *inside* a fixture body (a
    local import) -- the far more common top-of-file form is invisible to
    a DB-only check by construction, since raw_source is
    function-body-only. A 0 here does not mean zero true prevalence, only
    zero *detectable-from-this-DB* prevalence -- see that doc's real-file
    sampling for what actually calibrates the true rate."""
    total = conn.execute(
        "SELECT COUNT(*) FROM fixtures f JOIN test_files tf ON f.file_id = tf.id "
        "WHERE tf.language = 'python'"
    ).fetchone()[0]
    clauses = " OR ".join("f.raw_source LIKE ?" for _ in _ALIASED_MOCK_IMPORT_LIKE_PATTERNS)
    aliased = conn.execute(
        "SELECT COUNT(*) FROM fixtures f JOIN test_files tf ON f.file_id = tf.id "
        f"WHERE tf.language = 'python' AND ({clauses})",
        _ALIASED_MOCK_IMPORT_LIKE_PATTERNS,
    ).fetchone()[0]
    return {"total_python_fixtures": total, "aliased_in_body": aliased}


def _render_aliased_mock_import_side_note(*, db_root: Path = paths.DB_ROOT) -> list[str]:
    """## Aliased Mock Import Detection (Python)."""
    header = ["Dataset", "Python fixtures", "Class/function-level alias in body"]
    lines = [
        "## Aliased Mock Import Detection (Python)",
        "",
        "Side note, not a comparison, and a lower bound, not a live risk "
        "estimate -- count of Python fixtures whose `raw_source` contains "
        "a direct class/function-level mock alias (`from unittest.mock "
        "import patch as p`, etc.), the one pattern that actually breaks "
        "mock detection. This DB-only check can only catch an alias "
        "declared *inside* a fixture body -- the far more common "
        "top-of-file form is invisible to it by construction (`raw_source` "
        "is function-body-only). See "
        "`internal-docs/methodology-improvements/aliased-mock-import-prevalence.md` "
        "for the real-file sampling that actually calibrates the true "
        "rate (found ~0% there too, via a different, network-dependent "
        "method this script deliberately doesn't replicate).",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]

    def _row(label: str, result: dict | None) -> str:
        if result is None:
            return f"| {label} | N/A | N/A |"
        return f"| {label} | {result['total_python_fixtures']:,} | {result['aliased_in_body']:,} |"

    a_db = require_db_or_none("a", db_root)
    a_result = None
    if a_db is not None:
        with db_session(a_db) as conn:
            a_result = _fetch_aliased_mock_import_counts(conn)
    lines.append(_row("Dataset A", a_result))

    c_db = require_db_or_none("c", db_root)
    c_result = None
    if c_db is not None:
        with db_session(c_db) as conn:
            c_result = _fetch_aliased_mock_import_counts(conn)
    lines.append(_row("Dataset C", c_result))

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Mock-category fallback rate -- side note
# ---------------------------------------------------------------------------

def _empty_mock_classification_bucket() -> dict:
    return {"total": 0, "api_name": 0, "naming_only": 0, "fallback": 0}


def _fetch_mock_category_classification_breakdown(conn: sqlite3.Connection) -> dict:
    """For every mock_usages row already classified category='mock',
    reconstruct whether that classification came from a positive keyword
    match or the classifier's fallback (see this module's docstring and
    internal-docs/methodology-improvements/mock-category-fallback-analysis.md).
    "mock" is both a real category term and the catch-all -- so, for
    category='mock' rows specifically (dummy/stub/spy/fake already ruled
    out by construction), checking the fixture's own raw_source for
    "mock" (case-insensitive) exactly separates a positive match from a
    true fallback -- not an approximation.

    Splits positive matches further into api_name (the matched call site
    itself -- mock_usages.raw_snippet -- contains "mock", e.g.
    MagicMock(/mock.patch(/jest.mock() vs. naming_only (raw_snippet
    doesn't, but the fixture's wider raw_source does -- e.g. a
    keyword-free jest.fn()/vi.fn()/monkeypatch.setattr() call sitting
    next to a mockClient-named variable elsewhere in the same body).

    Returns {"total", "api_name", "naming_only", "fallback",
    "by_language": {language: {same 4 keys}}} -- one pass over
    mock_usages, both the pooled and per-language views come from the
    same rows so they can't disagree."""
    rows = conn.execute(
        "SELECT mu.raw_snippet, f.raw_source, tf.language FROM mock_usages mu "
        "JOIN fixtures f ON mu.fixture_id = f.id "
        "JOIN test_files tf ON f.file_id = tf.id "
        "WHERE mu.category = 'mock'"
    ).fetchall()

    result = _empty_mock_classification_bucket()
    by_language: dict[str, dict] = {}
    for raw_snippet, raw_source, language in rows:
        snippet_l = (raw_snippet or "").lower()
        raw_l = (raw_source or "").lower()
        if "mock" in snippet_l:
            bucket = "api_name"
        elif "mock" in raw_l:
            bucket = "naming_only"
        else:
            bucket = "fallback"

        result["total"] += 1
        result[bucket] += 1

        lang_bucket = by_language.setdefault(language, _empty_mock_classification_bucket())
        lang_bucket["total"] += 1
        lang_bucket[bucket] += 1

    result["by_language"] = by_language
    return result


def _render_mock_category_fallback_pct(positive: int, fallback: int, total: int) -> str:
    """'{positive}% positive / {fallback}% fallback' at one decimal place
    -- the exact format the paper wants to cite (e.g. "72.0% ... 28.0%
    from the fallback")."""
    if total == 0:
        return "N/A / N/A"
    return f"{100 * positive / total:.1f}% / {100 * fallback / total:.1f}%"


def _render_mock_category_fallback_side_note(*, db_root: Path = paths.DB_ROOT) -> list[str]:
    """## Mock-Category Fallback Rate."""
    lines = [
        "## Mock-Category Fallback Rate",
        "",
        "Side note, not a comparison: `category='mock'` "
        "(`mock_usages.category`) is both a real, specific test-double "
        'category (the literal word "mock" found in the fixture body) '
        "*and* the classifier's catch-all fallback when none of the 5 "
        "category terms (dummy/stub/spy/fake/mock) appear anywhere at all "
        "-- nothing in the schema distinguishes which happened for a given "
        "row. This reconstructs that split exactly (not an estimate -- see "
        "`internal-docs/methodology-improvements/mock-category-fallback-analysis.md`), "
        'in the shape the paper cites it: "X% of mock-type classifications '
        'result from a positive keyword match, Y% from the fallback."',
        "",
    ]

    a_db = require_db_or_none("a", db_root)
    a_result = None
    if a_db is not None:
        with db_session(a_db) as conn:
            a_result = _fetch_mock_category_classification_breakdown(conn)

    c_db = require_db_or_none("c", db_root)
    c_result = None
    if c_db is not None:
        with db_session(c_db) as conn:
            c_result = _fetch_mock_category_classification_breakdown(conn)

    # --- Headline: positive vs fallback, the exact number the paper cites ---
    header = ["Dataset", "category='mock' rows", "Positive match", "Fallback (no keyword)", "Positive % / Fallback %"]
    lines += ["### Positive match vs. fallback", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]

    def _headline_row(label: str, result: dict | None) -> str:
        if result is None or result["total"] == 0:
            return f"| {label} | N/A | N/A | N/A | N/A |"
        positive = result["api_name"] + result["naming_only"]
        fallback = result["fallback"]
        pct = _render_mock_category_fallback_pct(positive, fallback, result["total"])
        return f"| {label} | {result['total']:,} | {positive:,} | {fallback:,} | {pct} |"

    lines.append(_headline_row("Dataset A", a_result))
    lines.append(_headline_row("Dataset C", c_result))
    lines.append("")

    # --- Finer split: which kind of positive match ---
    header2 = ["Dataset", "n", "Framework API name", "Naming-only", "Fallback"]
    lines += [
        "### Positive matches split further: framework API name vs. naming-only",
        "",
        '"Framework API name" -- the matched call site itself '
        '(`mock_usages.raw_snippet`) contains "mock" (`MagicMock(`, '
        '`mock.patch(`, `jest.mock(`, ...). "Naming-only" -- the matched '
        "call is keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`, "
        "`monkeypatch.setattr()`, ...) but some other identifier in the "
        'same fixture body supplied "mock".',
        "",
        "| " + " | ".join(header2) + " |",
        "|" + "---|" * len(header2),
    ]

    def _split_row(label: str, result: dict | None) -> str:
        if result is None or result["total"] == 0:
            return f"| {label} | N/A | N/A | N/A | N/A |"
        total = result["total"]

        def cell(n: int) -> str:
            return f"{n:,} ({100 * n / total:.1f}%)"

        return (
            f"| {label} | {total:,} | {cell(result['api_name'])} | "
            f"{cell(result['naming_only'])} | {cell(result['fallback'])} |"
        )

    lines.append(_split_row("Dataset A", a_result))
    lines.append(_split_row("Dataset C", c_result))
    lines.append("")

    # --- Per language: the pooled number's real driver is language-specific ---
    lines += [
        "### Per language",
        "",
        "The pooled split above can hide a language-specific reversal --",
        "checking per language matters here specifically because it does:",
        "",
    ]
    header3 = ["Language", "n", "Framework API name", "Naming-only", "Fallback"]
    for label, result in (("Dataset A", a_result), ("Dataset C", c_result)):
        lines += [f"**{label}**", "", "| " + " | ".join(header3) + " |", "|" + "---|" * len(header3)]
        if result is None or not result.get("by_language"):
            lines.append("| _(no data)_ | -- | -- | -- | -- |")
            lines.append("")
            continue
        for language in sorted(result["by_language"]):
            lang_result = result["by_language"][language]
            lines.append(_split_row(language, lang_result))
        lines.append("")

    return lines


def generate_report(
    *,
    db_root: Path = paths.DB_ROOT,
    datasets_root: Path = paths.DATASETS_ROOT,
    raw_search_dir: Path = paths.RAW_SEARCH_DIR,
    sample_output_dir: Path | None = None,
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Dataset Findings (outside RQ1-3)",
        "",
        "> Descriptive statistics about the datasets themselves -- collection "
        "process, composition -- that support paper claims but don't belong "
        "to any single RQ1-3 comparison. See this module's docstring for what "
        "each section below covers and why it lives here instead of its own "
        "script.",
        "",
        f"Generated: {generated_at}",
        "",
    ]

    stats = load_repo_purity_stats(db_root=db_root)
    if stats is None:
        lines += ["_Not available -- db/a.db not collected yet._", ""]
    elif not stats:
        lines += ["_Dataset A has no repositories recorded yet._", ""]
    else:
        lines += [
            "## Diff-Purity Gate (Dataset A)",
            "",
            "Of Dataset A's agent commits that touched >=1 test file, how many "
            "were rejected for mixing test-file additions with edits/deletions, "
            "vs accepted as pure additions?",
            "",
            "### Overall",
            "",
            _render_totals(stats),
            "### By language",
            "",
            _render_group_table("Rejection rate by repo language", _group_by(stats, "language")),
            "### By agent adoption intensity",
            "",
            _render_group_table(
                "Rejection rate by agent_adoption_intensity", _group_by(stats, "adoption_intensity")
            ),
            "### Per-repo distribution",
            "",
            _render_repo_distribution(stats),
            "## Agent Adoption Intensity (Dataset A repo pool)",
            "",
            "How Dataset A's whole repo pool splits across agent_adoption_intensity "
            "buckets -- bucket *membership*, not the rejection-rate-by-bucket view "
            "above. See this module's docstring for the known limitation (bucket "
            "label only, no underlying numeric ratio persisted).",
            "",
            "### Overall",
            "",
            _render_adoption_intensity_distribution(stats),
            "### Funnel and adoption intensity by language",
            "",
            "Config -> No commits -> adoption tiers, per language -- the exact "
            "shape used for the paper's funnel/adoption table. See this "
            "function's docstring for exactly what Config/Total mean and how "
            "the percentages are computed.",
            "",
            _render_adoption_intensity_funnel_by_language(stats),
        ]

    # Independent of the Diff-Purity Gate/Adoption-Intensity sections above
    # (own prerequisite checks, own "not available" fallbacks) -- Dataset
    # C's summary in particular must still be attempted even when db/a.db
    # is missing.
    lines += _render_dataset_a_commit_repo_summary(
        db_root=db_root, datasets_root=datasets_root, raw_search_dir=raw_search_dir
    )
    lines += _render_dataset_c_repo_summary(
        db_root=db_root, datasets_root=datasets_root, raw_search_dir=raw_search_dir
    )
    lines += _render_fixture_counts_by_language_summary(db_root=db_root)
    lines += _render_dataset_c_sampling_summary(output_dir=sample_output_dir)
    lines += _render_junit3_fallback_side_note(db_root=db_root)
    lines += _render_js_hook_complexity_side_note(db_root=db_root)
    lines += _render_mocha_bare_hook_side_note(db_root=db_root)
    lines += _render_aliased_mock_import_side_note(db_root=db_root)
    lines += _render_mock_category_fallback_side_note(db_root=db_root)

    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR,
    *,
    db_root: Path = paths.DB_ROOT,
    datasets_root: Path = paths.DATASETS_ROOT,
    raw_search_dir: Path = paths.RAW_SEARCH_DIR,
    sample_output_dir: Path | None = None,
) -> Path:
    report = generate_report(
        db_root=db_root,
        datasets_root=datasets_root,
        raw_search_dir=raw_search_dir,
        sample_output_dir=sample_output_dir,
    )
    output_path = write_markdown_report(output_dir, "dataset_findings.md", report)
    logger.info(f"Dataset findings report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"Dataset findings report written to {path}")


if __name__ == "__main__":
    main()
