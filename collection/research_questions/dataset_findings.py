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

Every section here reads data that collection already computes and
persists; this script adds no new instrumentation of its own.

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

python -m collection.research_questions.dataset_findings
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
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


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
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
        return "\n".join(lines)

    if not stats:
        lines += ["_Dataset A has no repositories recorded yet._", ""]
        return "\n".join(lines)

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

    return "\n".join(lines)


def write_report(output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT) -> Path:
    report = generate_report(db_root=db_root)
    output_path = write_markdown_report(output_dir, "dataset_findings.md", report)
    logger.info(f"Dataset findings report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"Dataset findings report written to {path}")


if __name__ == "__main__":
    main()
