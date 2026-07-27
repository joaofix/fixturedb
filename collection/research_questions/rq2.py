"""
RQ2 -- Setup and Teardown Characterization (Quantitative): how do
agent-generated fixtures compare to human-written ones in setup and
teardown provision?

Three metrics, computed per dataset (A/B/C):

1. **fixture_type "kind" distribution** -- setup / teardown / other.
   `fixture_type` alone can't cleanly split into setup vs teardown for
   every type, so classification reuses two existing tables from
   detector_shared.py -- the exact same ones `has_teardown_pair` itself is
   computed from -- rather than a duplicate, drifting lookup:
     - `TYPE_BASED_TEARDOWN_PAIRS`: types where setup/teardown are
       different fixture_types (before_each/after_each,
       junit5_before_each/junit5_after_each, ...) -- classified by type
       alone.
     - `NAME_BASED_TEARDOWN_PAIRS`: types where setup and teardown share
       ONE fixture_type, distinguished only by fixture name
       (unittest_setup's setUp/tearDown, pytest_class_method's
       setup_method/teardown_method) -- classified by (type, name).
   Everything else (pytest_decorator -- setup with an *optional* teardown
   via `yield`, captured by metric 3 instead, not by type or name;
   junit_rule/junit_class_rule/vitest_around_each/vitest_around_all --
   inherently both at once, see ALWAYS_HAS_TEARDOWN_TYPES;
   testng_data_provider -- neither, it's not a lifecycle hook) buckets as
   "other" instead of forcing a fake split.

2. **Per-repo setup-to-teardown ratio** -- counts only the setup/teardown
   fixtures from (1) (both the type-based and name-based ones), matching
   the RQ's literal "ratio of setup fixtures to teardown fixtures". A repo
   with setup fixtures but zero teardown ones has an undefined ratio (not
   0, not infinity) -- reported separately as a repo count/percentage, not
   silently dropped from or forced into the ratio distribution.

3. **has_teardown_pair rate, per fixture_type** -- reported per type, not
   lumped into (1)'s "other" bucket, since lumping would mix real
   provisioning signal (e.g. how often a pytest_decorator fixture actually
   yields) with fixture_types that are architecturally always 0 (a
   teardown-named unittest_setup/pytest_class_method row can never be
   flagged -- see detector_shared.py's _calculate_teardown_pairs
   docstring: "only the setup-side fixture of a pair is flagged").
   Descriptive only, not run through a significance test.

A vs B and A vs C only (see rq1.py's rationale -- B vs C deferred until
those datasets exist).

A dataset is skipped (not an error) if its db/{dataset}.db does not exist
yet.

python -m collection.research_questions.rq2
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..between_group_comparison import (
    BalanceTest,
    compute_categorical_balance,
    compute_continuous_balance,
)
from ..db import db_session
from ..detector_shared import NAME_BASED_TEARDOWN_PAIRS, TYPE_BASED_TEARDOWN_PAIRS
from ..logging_utils import get_logger
from ._shared import (
    COMPARISONS,
    DATASET_LABELS,
    OUTPUT_DIR,
    fmt,
    require_db_or_none,
    summarize_continuous,
)

logger = get_logger(__name__)

TYPE_BASED_SETUP_TYPES: set[str] = set(TYPE_BASED_TEARDOWN_PAIRS.keys())
TYPE_BASED_TEARDOWN_TYPES: set[str] = set(TYPE_BASED_TEARDOWN_PAIRS.values())

# fixture_type -> {setup names} / {teardown names}, for the fixture_types
# where type alone is ambiguous and the fixture's own name disambiguates.
NAME_BASED_SETUP_NAMES: dict[str, set[str]] = {
    ft: set(names.keys()) for ft, names in NAME_BASED_TEARDOWN_PAIRS.items()
}
NAME_BASED_TEARDOWN_NAMES: dict[str, set[str]] = {
    ft: set(names.values()) for ft, names in NAME_BASED_TEARDOWN_PAIRS.items()
}


def _kind(fixture_type: str, name: str | None = None) -> str:
    if fixture_type in TYPE_BASED_SETUP_TYPES:
        return "setup"
    if fixture_type in TYPE_BASED_TEARDOWN_TYPES:
        return "teardown"
    if fixture_type in NAME_BASED_TEARDOWN_PAIRS and name is not None:
        if name in NAME_BASED_SETUP_NAMES[fixture_type]:
            return "setup"
        if name in NAME_BASED_TEARDOWN_NAMES[fixture_type]:
            return "teardown"
    return "other"


@dataclass
class DatasetMetrics:
    dataset: str
    n_fixtures: int
    kind_distribution: dict[str, int] = field(default_factory=dict)
    per_repo_ratios: list[float] = field(default_factory=list)
    n_repos_with_setup: int = 0
    n_repos_zero_teardown: int = 0
    teardown_rate_by_type: dict[str, dict] = field(default_factory=dict)


def load_dataset_metrics(
    dataset: str, *, db_root: Path = paths.DB_ROOT
) -> DatasetMetrics | None:
    """Load RQ2 metrics for `dataset`, or None if its db doesn't exist yet."""
    db_file = require_db_or_none(dataset, db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        n_fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        kind_distribution, per_repo_counts = _fetch_kinds_and_repo_counts(conn)
        teardown_rate_by_type = _fetch_teardown_rate_by_type(conn)

    per_repo_ratios: list[float] = []
    n_with_setup = 0
    n_zero_teardown = 0
    for setup_count, teardown_count in per_repo_counts.values():
        if not setup_count:
            continue
        n_with_setup += 1
        if teardown_count:
            per_repo_ratios.append(setup_count / teardown_count)
        else:
            n_zero_teardown += 1

    return DatasetMetrics(
        dataset=dataset,
        n_fixtures=n_fixtures,
        kind_distribution=kind_distribution,
        per_repo_ratios=per_repo_ratios,
        n_repos_with_setup=n_with_setup,
        n_repos_zero_teardown=n_zero_teardown,
        teardown_rate_by_type=teardown_rate_by_type,
    )


def _fetch_kinds_and_repo_counts(
    conn: sqlite3.Connection,
) -> tuple[dict[str, int], dict[int, tuple[int, int]]]:
    """Single pass over every fixture: dataset-level kind distribution, plus
    per-repo (setup_count, teardown_count) -- classified once via `_kind()`
    so the dataset-level and per-repo views can never disagree with each
    other (a second, SQL-side classification would just be `_kind()`
    duplicated in a different language)."""
    kind_distribution = {"setup": 0, "teardown": 0, "other": 0}
    per_repo: dict[int, list[int]] = {}

    rows = conn.execute(
        "SELECT repo_id, fixture_type, name FROM fixtures WHERE fixture_type IS NOT NULL"
    ).fetchall()
    for repo_id, fixture_type, name in rows:
        kind = _kind(fixture_type, name)
        kind_distribution[kind] += 1
        counts = per_repo.setdefault(repo_id, [0, 0])
        if kind == "setup":
            counts[0] += 1
        elif kind == "teardown":
            counts[1] += 1

    per_repo_counts = {repo_id: (c[0], c[1]) for repo_id, c in per_repo.items()}
    return kind_distribution, per_repo_counts


def _fetch_teardown_rate_by_type(conn: sqlite3.Connection) -> dict[str, dict]:
    rates: dict[str, dict] = {}
    for fixture_type, has_pair, count in conn.execute(
        "SELECT fixture_type, has_teardown_pair, COUNT(*) FROM fixtures "
        "WHERE fixture_type IS NOT NULL GROUP BY fixture_type, has_teardown_pair"
    ).fetchall():
        entry = rates.setdefault(fixture_type, {"n": 0, "n_with_pair": 0})
        entry["n"] += count
        if has_pair:
            entry["n_with_pair"] += count
    return rates


def compare_datasets(a: DatasetMetrics, other: DatasetMetrics) -> dict[str, BalanceTest]:
    """A vs `other`: Mann-Whitney U on per-repo ratios, chi-square on kind
    distribution and on zero-teardown-repo rate."""
    ratio_test = compute_continuous_balance(
        human_values=other.per_repo_ratios,
        agent_values=a.per_repo_ratios,
        variable="setup_to_teardown_ratio",
    )
    kind_test = compute_categorical_balance(
        human_dist=other.kind_distribution,
        agent_dist=a.kind_distribution,
        variable="fixture_type_kind",
    )
    zero_teardown_test = compute_categorical_balance(
        human_dist={
            "zero_teardown_type": other.n_repos_zero_teardown,
            "has_teardown_type": other.n_repos_with_setup - other.n_repos_zero_teardown,
        },
        agent_dist={
            "zero_teardown_type": a.n_repos_zero_teardown,
            "has_teardown_type": a.n_repos_with_setup - a.n_repos_zero_teardown,
        },
        variable="repo_zero_teardown_rate",
    )
    return {
        "setup_to_teardown_ratio": ratio_test,
        "fixture_type_kind": kind_test,
        "repo_zero_teardown_rate": zero_teardown_test,
    }


def _render_dataset_summary(metrics: DatasetMetrics) -> str:
    lines = [f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures", ""]

    total_kind = sum(metrics.kind_distribution.values())
    lines += ["**fixture_type kind distribution**", "", "| Kind | Count | % |", "|---|---|---|"]
    for kind in ("setup", "teardown", "other"):
        count = metrics.kind_distribution.get(kind, 0)
        pct = 100 * count / total_kind if total_kind else 0.0
        lines.append(f"| {kind} | {count:,} | {pct:.1f}% |")
    lines.append("")

    s = summarize_continuous(metrics.per_repo_ratios)
    zero_pct = (
        100 * metrics.n_repos_zero_teardown / metrics.n_repos_with_setup
        if metrics.n_repos_with_setup
        else 0.0
    )
    lines += [
        "**Per-repo setup-to-teardown ratio** (repos with >=1 setup fixture)",
        "",
        f"- Repos with >=1 setup fixture: {metrics.n_repos_with_setup:,}",
        f"- Of those, with zero teardown fixtures (ratio undefined): "
        f"{metrics.n_repos_zero_teardown:,} ({zero_pct:.1f}%)",
        f"- Ratio distribution over the remaining {s['n']:,} repos: "
        f"mean={fmt(s['mean'])}, median={fmt(s['median'])}, "
        f"min={fmt(s['min'], 1)}, max={fmt(s['max'], 1)}",
        "",
    ]

    lines += [
        "**has_teardown_pair rate by fixture_type**",
        "",
        "| fixture_type | n | n with teardown pair | rate |",
        "|---|---|---|---|",
    ]
    for fixture_type, entry in sorted(
        metrics.teardown_rate_by_type.items(), key=lambda kv: -kv[1]["n"]
    ):
        rate = 100 * entry["n_with_pair"] / entry["n"] if entry["n"] else 0.0
        lines.append(f"| {fixture_type} | {entry['n']:,} | {entry['n_with_pair']:,} | {rate:.1f}% |")
    lines.append("")

    return "\n".join(lines)


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    result = compare_datasets(a, other)
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    t = result["setup_to_teardown_ratio"]
    d = t.details
    lines += ["**Per-repo setup-to-teardown ratio (Mann-Whitney U, two-sided)**", ""]
    if d.get("reason") == "insufficient_data":
        lines.append("_insufficient data_")
    else:
        sig = "yes" if t.p_value < 0.05 else "no"
        lines.append(
            f"A mean={fmt(d.get('agent_mean'))}, median={fmt(d.get('agent_median'))} | "
            f"{other.dataset.upper()} mean={fmt(d.get('human_mean'))}, "
            f"median={fmt(d.get('human_median'))} | U={fmt(t.statistic, 1)} | "
            f"p={t.p_value:.4g} | significant (p<0.05): {sig}"
        )
    lines.append("")

    lines += [
        "**Categorical comparisons (chi-square)**",
        "",
        "| Metric | chi2 | dof | p-value | significant (p<0.05) |",
        "|---|---|---|---|---|",
    ]
    for metric in ("fixture_type_kind", "repo_zero_teardown_rate"):
        t = result[metric]
        d = t.details
        if d.get("reason") == "insufficient_data":
            lines.append(f"| {metric} | -- | -- | -- | _insufficient data_ |")
            continue
        sig = "yes" if t.p_value < 0.05 else "no"
        dof = d.get("degrees_of_freedom", "--")
        lines.append(f"| {metric} | {fmt(t.statistic, 1)} | {dof} | {t.p_value:.4g} | {sig} |")
    lines.append("")

    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "b", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ2 -- Setup and Teardown Characterization",
        "",
        "> How do agent-generated fixtures compare to human-written ones in setup "
        "and teardown provision?",
        "",
        f"Generated: {generated_at}",
        "",
        "See [docs/research-questions.md](../docs/research-questions.md) for "
        "the full RQ2 definition.",
        "",
        "## Per-dataset summary",
        "",
    ]

    for ds in ("a", "b", "c"):
        metrics = loaded[ds]
        if metrics is None:
            lines += [f"### {DATASET_LABELS[ds]}", "", "_Not available -- db not collected yet._", ""]
        else:
            lines.append(_render_dataset_summary(metrics))

    a_metrics = loaded["a"]
    if a_metrics is None:
        lines.append("_Dataset A not available -- no A vs B / A vs C comparisons computed._")
    else:
        for other_ds, label in COMPARISONS:
            other_metrics = loaded[other_ds]
            if other_metrics is None:
                lines += [
                    f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other_ds]}",
                    "",
                    "_Not available -- db not collected yet._",
                    "",
                ]
            else:
                lines.append(_render_comparison(label, a_metrics, other_metrics))

    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = generate_report(db_root=db_root)
    output_path = output_dir / "rq2.md"
    output_path.write_text(report)
    logger.info(f"RQ2 report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"RQ2 report written to {path}")


if __name__ == "__main__":
    main()
