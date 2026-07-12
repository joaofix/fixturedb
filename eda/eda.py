"""
FixtureDB — Exploratory Data Analysis
======================================
Generates publication-quality plots for advisor review.

Usage:
    python eda.py                    # all available plots → output/eda/<timestamp>/
    python eda.py --out figures/     # custom base output directory
    python eda.py --show             # display interactively instead of saving

The script detects which pipeline phases have completed and only generates
plots for data that exists. Safe to run at any stage of the pipeline.
"""

import argparse
import sqlite3
import sys
import warnings
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "db" / "corpus.db"
DEFAULT_OUT = ROOT / "output" / "eda"

# ---------------------------------------------------------------------------
# Palettes
# Language colours are the single source of truth for language identity.
# They are ONLY used when color = language. Any other categorical dimension
# uses sequential single-hue shades (no independent colour vocabulary).
# ---------------------------------------------------------------------------

LANG_PALETTE = {
    "python": "#4C9BE8",
    "java": "#E8834C",
    "javascript": "#E8C94C",
    "typescript": "#C94C98",
}
LANG_ORDER = ["python", "java", "javascript", "typescript"]

STATUS_PALETTE = {
    "discovered": "#B0BEC5",
    "cloned": "#64B5F6",
    "analysed": "#81C784",
    "skipped": "#FFB74D",
    "error": "#E57373",
}

# ---------------------------------------------------------------------------
# Global style
# ---------------------------------------------------------------------------


def setup_style() -> None:
    sns.set_theme(
        style="whitegrid",
        context="paper",
        font="DejaVu Sans",
        rc={
            "figure.facecolor": "#FAFAFA",
            "axes.facecolor": "#FAFAFA",
            "grid.color": "#E8E8E8",
            "grid.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.spines.bottom": True,
            "axes.linewidth": 0.8,
            "xtick.bottom": True,
            "ytick.left": False,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "legend.frameon": False,
            "figure.dpi": 150,
        },
    )


def save_or_show(fig, name, out_dir, show):
    if show:
        plt.show()
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.png"
        fig.savefig(path, bbox_inches="tight", dpi=180, facecolor=fig.get_facecolor())
        try:
            display = path.relative_to(ROOT)
        except ValueError:
            display = path
        print(f"  ✓ {display}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def load_db(db_path):
    if not db_path.exists():
        print(f"[error] Database not found at {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def has_data(conn, table, condition="1=1"):
    try:
        r = conn.execute(f"SELECT COUNT(*) n FROM {table} WHERE {condition}").fetchone()
        return r["n"] > 0
    except Exception:
        return False


def qdf(conn, query):
    df = pd.read_sql_query(query, conn)
    # Normalize language names: combine typescript with javascript
    if "language" in df.columns:
        df["language"] = df["language"].replace("typescript", "javascript")
    return df


def lang_display(lang):
    """Convert language internal name to display name (capitalize + JS+TS)."""
    if lang == "javascript":
        return "JS+TS"
    return lang.capitalize()


# ---------------------------------------------------------------------------
# PLOT 1 — Corpus Composition
# Fix: language colours with tier as opacity; log-scale funnel with labels
# ---------------------------------------------------------------------------


def plot_corpus_by_tier(conn, out_dir, show):
    """Plot 1a: Repos by language (corpus composition)"""
    repos = qdf(conn, "SELECT language FROM repositories")
    if repos.empty:
        print("  [skip] No repositories in DB yet.")
        return

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#FAFAFA")
    fig.suptitle("Repositories by Language", fontsize=14, fontweight="bold", y=1.02)

    present = [l for l in LANG_ORDER if l in repos["language"].values]

    vals = [int(repos.query("language==@lang").shape[0]) for lang in present]
    for i, (lang, v) in enumerate(zip(present, vals)):
        colour = LANG_PALETTE[lang]
        bar = ax.bar(
            i,
            v,
            width=0.6,
            color=colour,
            alpha=0.85,
            zorder=3,
        )
        if v > 0:
            ax.text(
                i,
                v / 2,
                str(v),
                ha="center",
                va="center",
                fontsize=10,
                color="white",
                fontweight="bold",
            )

    # Colour patches for language legend
    import matplotlib.patches as mpatches

    lang_handles = [
        mpatches.Patch(color=LANG_PALETTE[l], label=lang_display(l)) for l in present
    ]
    ax.legend(
        handles=lang_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=4,
        fontsize=8,
    )
    ax.set_xticks(range(len(present)))
    ax.set_xticklabels([lang_display(l) for l in present])
    ax.set_ylabel("Repositories")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    plt.tight_layout()
    save_or_show(fig, "01a_repos_by_tier", out_dir, show)


def plot_pipeline_status(conn, out_dir, show):
    """Plot 1b: Pipeline status breakdown per language (stacked bars)"""
    repos = qdf(conn, "SELECT language, status FROM repositories")
    if repos.empty:
        print("  [skip] No repositories in DB yet.")
        return

    present = [l for l in LANG_ORDER if l in repos["language"].values]

    fig, ax = plt.subplots(figsize=(10, 6), facecolor="#FAFAFA")
    fig.suptitle("Pipeline Status Breakdown", fontsize=14, fontweight="bold", y=0.98)

    # Get status counts per language
    status_order = ["analysed", "skipped", "error", "cloned", "discovered"]
    status_data = (
        repos[repos["language"].isin(present)]
        .groupby(["language", "status"])
        .size()
        .reset_index(name="count")
    )

    # Pivot to wide format
    pivot = status_data.pivot(
        index="language", columns="status", values="count"
    ).fillna(0)
    pivot = pivot.reindex(present)
    pivot = pivot[[s for s in status_order if s in pivot.columns]]

    colours = [STATUS_PALETTE[s] for s in pivot.columns]
    pivot.plot(
        kind="barh",
        stacked=True,
        ax=ax,
        color=colours,
        edgecolor="white",
        linewidth=0.5,
    )

    # Format x-axis
    ax.set_xlabel("Repositories")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))

    # Format labels
    ax.set_ylabel("")
    ax.set_yticklabels([lang_display(l) for l in present])

    # Legend
    ax.legend(
        title="Status",
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=5,
        frameon=False,
        fontsize=8,
    )

    # Add total count at end of each bar
    for i, lang in enumerate(present):
        total = pivot.iloc[i].sum()
        ax.text(
            total,
            i,
            f"  {int(total):,}",
            va="center",
            fontsize=8,
            fontweight="bold",
        )

    # Add analysis criteria as text box
    criteria_text = (
        "Analysis Criteria for 'analysed' status:\n"
        "• ≥ 5 test files in repository\n"
        "• ≥ 50 commits in history\n"
        "• ≥ 1 fixture definition detected"
    )
    ax.text(
        0.98,
        0.02,
        criteria_text,
        transform=ax.transAxes,
        fontsize=7,
        verticalalignment="bottom",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5, edgecolor="none"),
        family="monospace",
    )

    plt.tight_layout()
    save_or_show(fig, "01b_pipeline_status", out_dir, show)


def plot_corpus_composition(conn, out_dir, show):
    """Plot 1: Corpus Composition (calls both 1a and 1b)"""
    plot_corpus_by_tier(conn, out_dir, show)
    plot_pipeline_status(conn, out_dir, show)


# ---------------------------------------------------------------------------
# PLOT 2 — Star Distribution
# Fix: replace violin with overlapping log-scale histograms — immediately legible
# ---------------------------------------------------------------------------


def plot_star_distribution(conn, out_dir, show):
    repos = qdf(
        conn, "SELECT language, stars FROM repositories WHERE stars IS NOT NULL"
    )
    if repos.empty:
        print("  [skip] No star data.")
        return

    present = [l for l in LANG_ORDER if l in repos["language"].values]

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#FAFAFA")

    # Ridge plot: one density curve per language
    from scipy import stats

    repos_clipped = repos.copy()
    repos_clipped["stars"] = repos_clipped["stars"].clip(lower=1)
    repos_clipped["log_stars"] = np.log10(repos_clipped["stars"])

    x_range = np.logspace(
        np.log10(repos_clipped["stars"].min()),
        np.log10(repos_clipped["stars"].max()),
        200,
    )
    x_log = np.log10(x_range)

    y_offset = 0
    for i, lang in enumerate(present):
        sub = repos_clipped[repos_clipped["language"] == lang]["log_stars"].values
        if len(sub) > 1:
            kde = stats.gaussian_kde(sub, bw_method=0.15)
            density = kde(x_log)
            # Normalize density for stacking
            density = density / density.max() * 0.8

            # Fill area under curve
            ax.fill_between(
                x_range,
                y_offset,
                y_offset + density,
                color=LANG_PALETTE[lang],
                alpha=0.7,
                label=lang_display(lang),
                zorder=len(present) - i,
            )
            # Edge line
            ax.plot(
                x_range,
                y_offset + density,
                color=LANG_PALETTE[lang],
                linewidth=1.2,
                zorder=len(present) - i + 1,
            )
            y_offset += 1

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.axvline(
        500,
        color="#333",
        linewidth=1.0,
        linestyle="--",
        alpha=0.7,
        label="500 ★  core threshold",
        zorder=100,
    )
    ax.axvline(
        100,
        color="#888",
        linewidth=0.8,
        linestyle=":",
        alpha=0.7,
        label="100 ★  minimum",
        zorder=100,
    )
    ax.set_xlabel("Stars (log scale)")
    ax.set_ylabel("Language (density, offset)")
    ax.set_title("How Popular Are the Repos We Collected?\n(ridge plot, log scale)")
    ax.set_yticks([])
    ax.legend(fontsize=9, loc="upper right")

    plt.tight_layout()
    save_or_show(fig, "02_star_distribution", out_dir, show)


# ---------------------------------------------------------------------------
# PLOT 3 — Repository Age & Activity
# Fix 3a: stacked area cumulative chart — beautiful, shows growth over time
# Fix 3b: boxplot of days-since-push with clean integer y-axis
# ---------------------------------------------------------------------------


def plot_repos_creation_timeline(conn, out_dir, show):
    """Plot 3a: Repository creation timeline"""
    repos = qdf(
        conn,
        """
        SELECT language, created_at
        FROM repositories WHERE created_at IS NOT NULL
    """,
    )
    if repos.empty:
        print("  [skip] No date data.")
        return

    repos["created_year"] = pd.to_datetime(repos["created_at"], errors="coerce").dt.year
    present = [l for l in LANG_ORDER if l in repos["language"].values]

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#FAFAFA")
    fig.suptitle(
        "When Were Repositories Created?", fontsize=14, fontweight="bold", y=1.02
    )

    all_years = sorted(repos["created_year"].dropna().unique().astype(int))
    year_range = list(range(min(all_years), max(all_years) + 1))

    # Build matrix: rows = languages, columns = years
    year_counts = {}
    for lang in present:
        sub = repos[repos["language"] == lang]["created_year"].dropna().astype(int)
        yearly = sub.value_counts().reindex(year_range, fill_value=0).sort_index()
        year_counts[lang] = yearly.values

    # Stacked bar chart
    x = np.arange(len(year_range))
    width = 0.6
    bottom = np.zeros(len(year_range))

    for lang in present:
        ax.bar(
            x,
            year_counts[lang],
            width,
            label=lang_display(lang),
            bottom=bottom,
            color=LANG_PALETTE[lang],
            alpha=0.85,
            edgecolor="white",
            linewidth=0.5,
        )
        bottom += year_counts[lang]

    ax.set_xlabel("Year")
    ax.set_ylabel("Number of Repositories")
    ax.set_title("Distribution across 2015–2017")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in year_range])
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.legend(loc="upper right", fontsize=8, framealpha=0.95)
    ax.set_ylim(0, bottom.max() * 1.1)

    # Add count labels on each segment
    bottom = np.zeros(len(year_range))
    for lang in present:
        heights = year_counts[lang]
        for i, h in enumerate(heights):
            if h > 20:  # Only label segments larger than 20 repos
                ax.text(
                    i,
                    bottom[i] + h / 2,
                    str(int(h)),
                    ha="center",
                    va="center",
                    fontsize=7,
                    fontweight="bold",
                    color="white",
                )
        bottom += heights

    plt.tight_layout()
    save_or_show(fig, "03a_repos_creation_timeline", out_dir, show)


def plot_repos_activity(conn, out_dir, show):
    """Plot 3b: Repository recent activity"""
    repos = qdf(
        conn,
        """
        SELECT language, pushed_at
        FROM repositories WHERE pushed_at IS NOT NULL
    """,
    )
    if repos.empty:
        print("  [skip] No date data.")
        return

    repos["days_since_push"] = (
        pd.Timestamp.now("UTC") - pd.to_datetime(repos["pushed_at"], errors="coerce")
    ).dt.days.clip(lower=0)

    present = [l for l in LANG_ORDER if l in repos["language"].values]

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#FAFAFA")
    fig.suptitle(
        "How Recently Were Repos Active?", fontsize=14, fontweight="bold", y=1.02
    )

    plot_data = repos[repos["language"].isin(present)].copy()
    plot_data["years_since_push"] = plot_data["days_since_push"] / 365.25

    # Drop the single maximum value per language — enough to fix stretched whiskers
    worst_idx = plot_data.groupby("language")["years_since_push"].idxmax()
    plot_data = plot_data.drop(index=worst_idx).reset_index(drop=True)

    sns.boxplot(
        data=plot_data,
        x="language",
        y="years_since_push",
        order=present,
        palette={l: LANG_PALETTE[l] for l in present},
        showfliers=False,
        linewidth=0.9,
        width=0.5,
        ax=ax,
    )
    ax.set_xticklabels([lang_display(l) for l in present])
    ax.set_xlabel("")
    ax.set_ylabel("Years Since Last Commit Push")
    ax.axhline(
        1.0, color="#888", linewidth=0.8, linestyle="--", alpha=0.7, label="1 year ago"
    )
    ax.legend(fontsize=8)

    plt.tight_layout()
    save_or_show(fig, "03b_repos_activity", out_dir, show)


def plot_age_and_activity(conn, out_dir, show):
    """Plot 3: Repository Age & Activity (calls both 3a and 3b)"""
    plot_repos_creation_timeline(conn, out_dir, show)
    plot_repos_activity(conn, out_dir, show)


# ---------------------------------------------------------------------------
# PLOT 4 — Domain Distribution
# Fix left: annotate heatmap with both % and absolute count (removes need for right)
# Fix right: replace colour-coded stacked bar with dot plot (no colour conflict)
# ---------------------------------------------------------------------------


def plot_domain_distribution(conn, out_dir, show):
    repos = qdf(
        conn,
        """
        SELECT language, domain FROM repositories
        WHERE domain IS NOT NULL AND status NOT IN ('discovered')
    """,
    )
    if repos.empty or repos["domain"].nunique() < 2:
        print(
            "  [skip] Domain data not classified yet. Run `python -m collection` domain classification (not yet migrated)."
        )
        return

    domain_order = ["web", "library", "data", "cli", "infra", "other"]
    present_langs = [l for l in LANG_ORDER if l in repos["language"].values]
    present_domains = [d for d in domain_order if d in repos["domain"].values]

    pivot = (
        repos.groupby(["language", "domain"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=present_langs, columns=present_domains, fill_value=0)
    )
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(1, 1, figsize=(10, 5), facecolor="#FAFAFA")
    fig.suptitle("Project Domain Distribution", fontsize=14, fontweight="bold", y=1.02)

    # ── heatmap annotated with "% (abs)" ─────────────────────────────────────
    annot = np.empty(pivot_pct.shape, dtype=object)
    for i, lang in enumerate(present_langs):
        for j, dom in enumerate(present_domains):
            pct = pivot_pct.loc[lang, dom]
            raw = int(pivot.loc[lang, dom])
            annot[i, j] = f"{pct:.0f}%\n({raw})"

    sns.heatmap(
        pivot_pct,
        annot=annot,
        fmt="",
        cmap="Blues",
        linewidths=0.4,
        linecolor="#E0E0E0",
        cbar_kws={"label": "% of language repos"},
        annot_kws={"size": 9},
        ax=ax,
    )
    ax.set_title("Domain Share per Language")
    ax.set_yticklabels([lang_display(l) for l in present_langs], rotation=0)
    ax.set_xticklabels(
        [d.capitalize() for d in present_domains], rotation=30, ha="right"
    )
    ax.set_xlabel("")
    ax.set_ylabel("")

    plt.tight_layout()
    save_or_show(fig, "04_domain_distribution", out_dir, show)


# ---------------------------------------------------------------------------
# PLOT 5 — Stars vs Forks (log-log scatter)
# Fix: replace confusing boxplot of ratio with direct log-log scatter
#      showing stars on x, forks on y, colour by language
# ---------------------------------------------------------------------------


def plot_fork_star_ratio(conn, out_dir, show):
    repos = qdf(
        conn,
        """
        SELECT language, stars, forks
        FROM repositories
        WHERE stars > 0 AND forks > 0
    """,
    )
    if repos.empty:
        print("  [skip] No fork/star data.")
        return

    present = [l for l in LANG_ORDER if l in repos["language"].values]

    fig, ax = plt.subplots(figsize=(9, 6), facecolor="#FAFAFA")

    for lang in present:
        sub = repos[repos["language"] == lang]
        ax.scatter(
            sub["stars"],
            sub["forks"],
            color=LANG_PALETTE[lang],
            label=lang_display(lang),
            alpha=0.35,
            s=18,
            linewidths=0,
            zorder=3,
        )

    # Diagonal: forks == stars
    lim_max = repos[["stars", "forks"]].max().max() * 2
    lim_min = 1
    ax.plot(
        [lim_min, lim_max],
        [lim_min, lim_max],
        color="#555",
        linewidth=0.9,
        linestyle="--",
        alpha=0.6,
        label="forks = stars",
        zorder=2,
    )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_xlabel("Stars (log scale)")
    ax.set_ylabel("Forks (log scale)")
    ax.set_title(
        "Stars vs. Forks per Repository\n"
        "Points above the diagonal are forked more than starred"
    )
    ax.legend(fontsize=9, markerscale=1.5)

    plt.tight_layout()
    save_or_show(fig, "05_stars_vs_forks", out_dir, show)


# ---------------------------------------------------------------------------
# PLOT 6 — Fixture Overview
# Fix 6a: cut=0 on violin (kills negatives), log y-scale (tames outliers)
# Fix 6b: single-hue heatmap (language × fixture type) — no colour conflict
# ---------------------------------------------------------------------------


def plot_fixture_distribution(conn, out_dir, show):
    """Plot 6a: Fixture distribution per repository (ridge plot)"""
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python -m collection extract-fixtures --dataset a/b/c`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.fixture_type, r.language, r.full_name
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(1, 1, figsize=(8, 5), facecolor="#FAFAFA")
    fig.suptitle(
        "How Many Fixtures Does Each Repo Have?", fontsize=14, fontweight="bold", y=1.00
    )

    per_repo = (
        fixtures.groupby(["language", "full_name"])
        .size()
        .reset_index(name="fixture_count")
    )
    per_repo = per_repo[per_repo["language"].isin(present)]
    per_repo["fixture_count"] = per_repo["fixture_count"].clip(lower=1)
    per_repo["log_count"] = np.log10(per_repo["fixture_count"])

    # Ridge plot: one density curve per language
    from scipy import stats

    x_range = np.logspace(
        np.log10(per_repo["fixture_count"].min()),
        np.log10(per_repo["fixture_count"].max()),
        200,
    )
    x_log = np.log10(x_range)

    y_offset = 0
    for i, lang in enumerate(present):
        sub = per_repo[per_repo["language"] == lang]["log_count"].values
        if len(sub) > 1:
            kde = stats.gaussian_kde(sub, bw_method=0.15)
            density = kde(x_log)
            # Normalize density for stacking
            density = density / density.max() * 0.8

            # Fill area under curve
            ax.fill_between(
                x_range,
                y_offset,
                y_offset + density,
                color=LANG_PALETTE[lang],
                alpha=0.7,
                label=lang_display(lang),
                zorder=len(present) - i,
            )
            # Edge line
            ax.plot(
                x_range,
                y_offset + density,
                color=LANG_PALETTE[lang],
                linewidth=1.2,
                zorder=len(present) - i + 1,
            )
            y_offset += 1

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: str(int(v)) if v >= 1 else "")
    )
    ax.set_xlabel("Fixtures per Repository (log scale)")
    ax.set_ylabel("Language (density, offset)")
    ax.set_title("Ridge Plot - Log Scale Distribution", fontsize=11, pad=10)
    ax.set_yticks([])
    ax.legend(fontsize=9, loc="upper right")

    plt.tight_layout()
    save_or_show(fig, "06a_fixture_distribution", out_dir, show)


def plot_fixture_types(conn, out_dir, show):
    """Plot 6b: Fixture scope distribution per language (stacked bar)"""
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python -m collection extract-fixtures --dataset a/b/c`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.scope, r.language, r.full_name
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(1, 1, figsize=(8, 5), facecolor="#FAFAFA")
    fig.suptitle("Fixture Scope Distribution", fontsize=14, fontweight="bold", y=1.00)

    scope_counts = (
        fixtures[fixtures["language"].isin(present)]
        .groupby(["language", "scope"])
        .size()
        .reset_index(name="n")
    )
    pivot_scope = (
        scope_counts.pivot(index="language", columns="scope", values="n")
        .reindex(present)
        .fillna(0)
    )
    pivot_scope_pct = pivot_scope.div(pivot_scope.sum(axis=1), axis=0) * 100

    # Order scopes from most to least common
    scope_order = ["per_test", "per_class", "per_module", "global"]
    scope_order = [s for s in scope_order if s in pivot_scope_pct.columns]
    pivot_scope_pct = pivot_scope_pct[scope_order]

    # Color palette for scopes (semantic: light=frequent, dark=rare)
    scope_colors = {
        "per_test": "#4ECDC4",  # Teal - most common, lightweight
        "per_class": "#FFE66D",  # Yellow - moderate
        "per_module": "#FF6B6B",  # Red - less common
        "global": "#95B8D1",  # Blue - rare
    }

    x_pos = np.arange(len(present))
    width = 0.55
    bottom = np.zeros(len(present))

    for scope in scope_order:
        vals = pivot_scope_pct[scope].values
        color = scope_colors.get(scope, "#CCCCCC")
        bars = ax.bar(
            x_pos,
            vals,
            width,
            label=scope.replace("_", " ").title(),
            bottom=bottom,
            color=color,
            alpha=0.85,
            edgecolor="white",
            linewidth=0.5,
        )

        # Add percentage labels for segments > 5%
        for i, (bar, val) in enumerate(zip(bars, vals)):
            if val > 5:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bottom[i] + val / 2,
                    f"{val:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=7,
                    fontweight="bold",
                    color="white" if scope != "per_class" else "#333",
                )
        bottom += vals

    ax.set_ylabel("Share of Fixtures (%)")
    ax.set_xlabel("")
    ax.set_title(
        "Which Fixture Scopes Do Developers Prefer?\n"
        "(Per-test fixtures run before each test; per-class fixtures run once per class)",
        fontsize=11,
        pad=10,
    )
    ax.set_xticks(x_pos)
    ax.set_xticklabels([lang_display(l) for l in present])
    ax.set_ylim(0, 105)
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.axhline(50, color="#ddd", linewidth=0.5, linestyle=":", alpha=0.5)

    plt.tight_layout()
    save_or_show(fig, "06b_fixture_types", out_dir, show)


def plot_fixture_overview(conn, out_dir, show):
    """Wrapper: calls fixture distribution plot (scope-based, CSV-exported)"""
    plot_fixture_distribution(conn, out_dir, show)


# ---------------------------------------------------------------------------
# PLOT 7 — Mocking Practices
# Fix 7a: lollipop chart — cleaner, language colours used correctly
#         title and axis made clear
# Fix 7b: rename title and y-axis to be self-explanatory
# ---------------------------------------------------------------------------


def plot_mock_prevalence_chart(conn, out_dir, show):
    """Plot 7a: Mock prevalence (bar chart)"""
    if not has_data(conn, "mock_usages"):
        print("  [skip] No mock data yet. Run `python -m collection extract-fixtures --dataset a/b/c`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.id, r.language,
               (SELECT COUNT(*) FROM mock_usages m WHERE m.fixture_id = f.id) AS mock_count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(1, 1, figsize=(8, 5), facecolor="#FAFAFA")
    fig.suptitle("Mock Usage in Fixtures", fontsize=14, fontweight="bold", y=1.00)

    fixtures["has_mock"] = fixtures["mock_count"] > 0
    prevalence = (
        fixtures[fixtures["language"].isin(present)]
        .groupby("language")["has_mock"]
        .mean()
        .reindex(present)
        * 100
    )
    y_pos = range(len(present))

    ax.barh(
        list(y_pos),
        prevalence.values,
        color=[LANG_PALETTE[l] for l in present],
        height=0.55,
        zorder=3,
    )
    for y, pct, lang in zip(y_pos, prevalence.values, present):
        ax.text(
            pct + 1.2,
            y,
            f"{pct:.1f}%",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=LANG_PALETTE[lang],
        )

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([lang_display(l) for l in present])
    ax.set_xlabel("Fixtures with at least one mock call (%)")
    ax.set_xlim(0, min(100, prevalence.max() + 15))
    ax.set_title("What Share of Fixtures Use Mocking?", fontsize=11, pad=10)
    ax.axvline(0, color="#ccc", linewidth=0.5)

    plt.tight_layout()
    save_or_show(fig, "07a_mock_prevalence", out_dir, show)


def plot_framework_usage(conn, out_dir, show):
    """Plot 7b: Framework usage (stacked bar chart)"""
    if not has_data(conn, "mock_usages"):
        print("  [skip] No mock data yet. Run `python -m collection extract-fixtures --dataset a/b/c`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.id, r.language,
               (SELECT COUNT(*) FROM mock_usages m WHERE m.fixture_id = f.id) AS mock_count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    mocks = qdf(
        conn,
        """
        SELECT m.framework, r.language
        FROM mock_usages m
        JOIN repositories r ON m.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(1, 1, figsize=(8, 5), facecolor="#FAFAFA")
    fig.suptitle("Mocking Frameworks", fontsize=14, fontweight="bold", y=1.00)

    if not mocks.empty:
        fw_counts = (
            mocks[mocks["language"].isin(present)]
            .groupby(["language", "framework"])
            .size()
            .reset_index(name="n")
        )
        pivot = (
            fw_counts.pivot(index="language", columns="framework", values="n")
            .reindex(present)
            .fillna(0)
        )
        pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
        fws = list(pivot_pct.columns)

        # Single-hue per language: shades from light to dark
        import matplotlib.colors as mcolors

        y_pos = range(len(present))
        for i, lang in enumerate(present):
            base = LANG_PALETTE[lang]
            base_rgb = mcolors.to_rgb(base)
            shades = [
                tuple(c * (0.4 + 0.6 * j / max(len(fws) - 1, 1)) for c in base_rgb)
                for j in range(len(fws))
            ]
            left = 0.0
            for j, (fw, shade) in enumerate(zip(fws, shades)):
                w = pivot_pct.loc[lang, fw]
                if w > 0:
                    ax.barh(i, w, left=left, color=shade, height=0.55, zorder=3)
                    if w > 6:
                        ax.text(
                            left + w / 2,
                            i,
                            fw.replace("_", "\n"),
                            ha="center",
                            va="center",
                            fontsize=6,
                            color="white",
                            fontweight="bold",
                        )
                left += w

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels([lang_display(l) for l in present])
        ax.set_xlabel("Share of mock calls using each framework (%)")
        ax.set_xlim(0, 105)
        ax.set_title("Which Frameworks Do Developers Use?", fontsize=11, pad=10)

    plt.tight_layout()
    save_or_show(fig, "07b_framework_usage", out_dir, show)


def plot_mock_prevalence(conn, out_dir, show):
    """Wrapper: calls all mocking practice plots"""
    plot_mock_prevalence_chart(conn, out_dir, show)
    plot_framework_usage(conn, out_dir, show)


def plot_fixture_categories(conn, out_dir, show):
    """Plot 8: Fixture categorization by usage pattern (horizontal bar chart)"""
    fixtures = qdf(
        conn,
        """
        SELECT category
        FROM fixtures
        WHERE category IS NOT NULL
    """,
    )
    if fixtures.empty or fixtures["category"].isna().all():
        print(
            "  [skip] No fixture categories yet. Run `python -m collection` domain classification (not yet migrated)."
        )
        return

    # Count by category
    cat_counts = (
        fixtures[fixtures["category"].notna()]
        .groupby("category")
        .size()
        .reset_index(name="count")
    )
    cat_counts["pct"] = cat_counts["count"] / cat_counts["count"].sum() * 100

    # Sort by count descending
    cat_counts = cat_counts.sort_values("count", ascending=True)

    # Color palette for categories (semantic: primary patterns first)
    category_colors = {
        "data_builder": "#2E86AB",  # Blue - most common, primary pattern
        "hybrid": "#A23B72",  # Purple - multi-purpose
        "mock_setup": "#F18F01",  # Orange - test isolation
        "resource_management": "#C73E1D",  # Rust - resource handling
        "service_setup": "#6A994E",  # Green - dependency management
        "state_reset": "#BC4749",  # Red - state management
        "configuration_setup": "#D4A574",  # Tan - configuration
        "environment": "#5A189A",  # Dark purple - environment
    }

    fig, ax = plt.subplots(1, 1, figsize=(10, 6), facecolor="#FAFAFA")
    fig.suptitle("Fixture Categorization", fontsize=14, fontweight="bold", y=0.98)

    # Create horizontal bar chart
    colors = [category_colors.get(cat, "#CCCCCC") for cat in cat_counts["category"]]
    bars = ax.barh(
        cat_counts["category"],
        cat_counts["count"],
        color=colors,
        alpha=0.85,
        edgecolor="white",
        linewidth=1,
    )

    # Add count and percentage labels
    for i, (bar, count, pct) in enumerate(
        zip(bars, cat_counts["count"], cat_counts["pct"])
    ):
        ax.text(
            count,
            bar.get_y() + bar.get_height() / 2,
            f"  {count:,} ({pct:.1f}%)",
            va="center",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_xlabel("Number of Fixtures")
    ax.set_ylabel("")
    ax.set_title(
        "Test Fixtures by Category\n(RQ1 Taxonomy — Usage Patterns)",
        fontsize=11,
        pad=10,
    )

    # Format y-axis labels to be more readable
    labels = [label.replace("_", " ").title() for label in cat_counts["category"]]
    ax.set_yticklabels(labels)

    # Grid for readability
    ax.grid(axis="x", alpha=0.3, linestyle=":", linewidth=0.5)
    ax.set_axisbelow(True)

    # Format x-axis to show thousands separator
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x):,}"))

    plt.tight_layout()
    save_or_show(fig, "08_fixture_categories", out_dir, show)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="FixtureDB EDA plots")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    if args.show:
        out_dir = None
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_dir = Path(args.out) / ts
        out_dir.mkdir(parents=True, exist_ok=True)
        latest = Path(args.out) / "latest"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        try:
            latest.symlink_to(ts)
        except (OSError, NotImplementedError):
            pass

    conn = load_db(Path(args.db))
    setup_style()

    total = pd.read_sql_query("SELECT COUNT(*) n FROM repositories", conn).iloc[0]["n"]
    analysed = pd.read_sql_query(
        "SELECT COUNT(*) n FROM repositories WHERE status='analysed'", conn
    ).iloc[0]["n"]
    print(f"\nFixtureDB EDA — {int(total):,} repos  ({int(analysed):,} analysed)")
    print(f"Output → {out_dir or 'screen'}\n")

    for name, fn in [
        ("Corpus Composition", plot_corpus_composition),
        ("Star Distribution", plot_star_distribution),
        ("Age & Activity", plot_age_and_activity),
        ("Domain Distribution", plot_domain_distribution),
        ("Stars vs Forks", plot_fork_star_ratio),
        ("Fixture Overview", plot_fixture_overview),
        ("Mock Prevalence", plot_mock_prevalence),
    ]:
        print(f"[{name}]")
        fn(conn, out_dir, args.show)

    conn.close()
    print("\nDone")


if __name__ == "__main__":
    main()
