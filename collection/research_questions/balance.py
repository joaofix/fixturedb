"""
Control-variable balance check: language, domain, repo_age_years -- are the
repo samples behind two datasets actually comparable before attributing an
RQ1-3 metric difference to authorship (A vs B) or era (A vs C)?

This exists because the methodology described in docs/data/dataset-card.md's
"Balance Tests" section and docs/reference/limitations.md's "Control
Variable Balance" section was never actually wired up against the current
db/{a,b,c}.db files. `BetweenGroupComparator` (collection/
between_group_comparison.py) implements the right test functions, but reads
from a `between-group.db` that doesn't exist and isn't referenced anywhere
in collection/__main__.py's CLI -- it's leftover from an earlier
architecture, before the Dataset A/B/C split. The docs claimed a balance
report exists (`between_group_comparison_*.json`); that file has never
existed in this repo's history.

Run for real (2026-07-31) against the current corpora: domain and
repo_age_years are NOT balanced, A vs B or A vs C (all four p < 1e-7). See
this module's generate_report() output for current numbers -- every RQ1-3
comparison should be read with this in mind until it's addressed (stratify,
regression-adjust, or at minimum explicitly disclose the confound).

Repo-level, not fixture-weighted: each repo counts once, restricted to
repos with >=1 fixture (matching the intent of the original, orphaned
get_human_fixtures_by_variable()/get_agent_fixtures_by_variable(), which
counted repos this way too -- despite their names, they never counted
"fixtures", the query has no GROUP BY that would double-count a repo with
many fixtures). Fixture-weighting would conflate "are the repo samples
comparable" with "did some repos happen to yield more fixtures than
others", which is a different question RQ1-3's own fixture-level tests
already cover.

python -m collection.research_questions.balance
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
from ..logging_utils import get_logger
from ._shared import (
    COMPARISONS,
    DATASET_LABELS,
    OUTPUT_DIR,
    apply_fdr_correction,
    categorical_effect_size_cell,
    continuous_effect_size_cell,
    fdr_cell,
    fmt,
    require_db_or_none,
    write_markdown_report,
)

logger = get_logger(__name__)

CATEGORICAL_VARIABLES = ["language", "domain"]
CONTINUOUS_VARIABLES = ["repo_age_years"]


@dataclass
class RepoControlVariables:
    dataset: str
    n_repos: int
    categorical: dict[str, dict[str, int]] = field(default_factory=dict)
    continuous: dict[str, list[float]] = field(default_factory=dict)


def load_repo_control_variables(
    dataset: str, *, db_root: Path = paths.DB_ROOT
) -> RepoControlVariables | None:
    """Load repo-level control variables for `dataset`'s fixture-yielding
    repos, or None if its db doesn't exist yet."""
    db_file = require_db_or_none(dataset, db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        n_repos = conn.execute(
            "SELECT COUNT(*) FROM repositories r "
            "WHERE EXISTS (SELECT 1 FROM fixtures f WHERE f.repo_id = r.id)"
        ).fetchone()[0]

        categorical: dict[str, dict[str, int]] = {}
        for variable in CATEGORICAL_VARIABLES:
            rows = conn.execute(
                f"SELECT r.{variable}, COUNT(*) FROM repositories r "
                f"WHERE EXISTS (SELECT 1 FROM fixtures f WHERE f.repo_id = r.id) "
                f"AND r.{variable} IS NOT NULL "
                f"GROUP BY r.{variable}"
            ).fetchall()
            categorical[variable] = {row[0]: row[1] for row in rows}

        continuous: dict[str, list[float]] = {}
        for variable in CONTINUOUS_VARIABLES:
            try:
                rows = conn.execute(
                    f"SELECT r.{variable} FROM repositories r "
                    f"WHERE EXISTS (SELECT 1 FROM fixtures f WHERE f.repo_id = r.id) "
                    f"AND r.{variable} IS NOT NULL"
                ).fetchall()
                continuous[variable] = [row[0] for row in rows]
            except sqlite3.OperationalError as exc:
                # A schema addition (e.g. repo_age_at_collection_years) not
                # yet present in an older, not-yet-re-extracted db -- report
                # as unavailable rather than crashing the whole balance
                # check for every dataset.
                logger.warning(
                    f"{db_file}: column {variable!r} unavailable ({exc}); "
                    "treating as no data for this dataset"
                )
                continuous[variable] = []

    return RepoControlVariables(
        dataset=dataset, n_repos=n_repos, categorical=categorical, continuous=continuous
    )


def compare_datasets(
    a: RepoControlVariables, other: RepoControlVariables
) -> dict[str, BalanceTest]:
    """A vs `other`: chi-square per categorical control variable,
    Mann-Whitney U per continuous one."""
    results: dict[str, BalanceTest] = {}
    for variable in CATEGORICAL_VARIABLES:
        results[variable] = compute_categorical_balance(
            human_dist=other.categorical.get(variable, {}),
            agent_dist=a.categorical.get(variable, {}),
            variable=variable,
        )
    for variable in CONTINUOUS_VARIABLES:
        results[variable] = compute_continuous_balance(
            human_values=other.continuous.get(variable, []),
            agent_values=a.continuous.get(variable, []),
            variable=variable,
        )
    return results


def _render_dataset_summary(metrics: RepoControlVariables) -> str:
    lines = [
        f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_repos:,} fixture-yielding repos",
        "",
    ]
    for variable in CATEGORICAL_VARIABLES:
        dist = metrics.categorical.get(variable, {})
        total = sum(dist.values())
        lines += [f"**{variable} distribution**", "", "| Value | Count | % |", "|---|---|---|"]
        if total == 0:
            lines.append("| _(no data)_ | -- | -- |")
        else:
            for value, count in sorted(dist.items(), key=lambda kv: -kv[1]):
                lines.append(f"| {value} | {count:,} | {100 * count / total:.1f}% |")
        lines.append("")
    return "\n".join(lines)


def _render_comparison(
    label: str, a: RepoControlVariables, other: RepoControlVariables
) -> str:
    result = compare_datasets(a, other)
    # One family of 3 (language, domain, repo_age_years) -- see
    # apply_fdr_correction()'s docstring.
    corrected = apply_fdr_correction(result)
    lines = [
        f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        "**p >= 0.05 means balanced** (no evidence of a difference); Cliff's "
        "delta/Cramer's V say how big any difference actually is, independent "
        "of sample size (thresholds: negligible/small/medium/large). BH-FDR "
        "corrects for running all 3 of these tests together.",
        "",
        "| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | "
        "BH-FDR adjusted p (sig?) |",
        "|---|---|---|---|---|---|---|",
    ]
    for variable in CATEGORICAL_VARIABLES + CONTINUOUS_VARIABLES:
        t = corrected[variable]
        d = t.details
        if d.get("reason") == "insufficient_data" or "error" in d:
            reason = d.get("reason", d.get("error", "unknown"))
            lines.append(f"| {variable} | {t.test_type} | -- | -- | _{reason}_ | -- | -- |")
            continue
        balanced = "yes" if t.p_value >= 0.05 else "**no**"
        effect = (
            categorical_effect_size_cell(t)
            if variable in CATEGORICAL_VARIABLES
            else continuous_effect_size_cell(t)
        )
        lines.append(
            f"| {variable} | {t.test_type} | {fmt(t.statistic, 1)} | {t.p_value:.4g} | "
            f"{balanced} | {effect} | {fdr_cell(t)} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_repo_control_variables(ds, db_root=db_root) for ds in ("a", "b", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# Control-Variable Balance Check",
        "",
        "> Are the repo samples behind two datasets comparable on language, "
        "domain, and repo age -- before attributing an RQ1-3 fixture-metric "
        "difference to authorship or era? See this module's docstring for why "
        "this check didn't previously run against the current data.",
        "",
        f"Generated: {generated_at}",
        "",
        "Repo-level (each fixture-yielding repo counted once), not "
        "fixture-weighted -- see this module's docstring for why.",
        "",
        "## Per-dataset repo distributions",
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
        lines.append("_Dataset A not available -- no A vs B / A vs C balance checks computed._")
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
    report = generate_report(db_root=db_root)
    output_path = write_markdown_report(output_dir, "balance.md", report)
    logger.info(f"Control-variable balance report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"Control-variable balance report written to {path}")


if __name__ == "__main__":
    main()
