"""
FixtureDB — Exploratory Data Analysis
======================================
Individual plot script.
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    LANG_ORDER,
    LANG_PALETTE,
    has_data,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)

# -----------
# FIXTURE OVERVIEW
# -----------


def plot_fixture_overview(conn, out_dir, show):
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.fixture_type, f.scope, r.language, r.full_name
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, axes = plt.subplots(1, 2, figsize=(15, 5), facecolor="#FAFAFA")
    fig.suptitle("Fixture Overview", fontsize=14, fontweight="bold", y=1.02)

    # ── 6a: fixture count per repo — ridge plot (log scale) ───────────────────
    ax = axes[0]
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
    ax.set_title("How Many Fixtures Does Each Repo Have?\n(ridge plot, log scale)")
    ax.set_yticks([])
    ax.legend(fontsize=9, loc="upper right")

    # ── 6b: fixture scope distribution — grouped bar chart ──────────────────
    ax2 = axes[1]
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
        bars = ax2.bar(
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
                ax2.text(
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

    ax2.set_ylabel("Share of Fixtures (%)")
    ax2.set_xlabel("")
    ax2.set_title(
        "Fixture Scope Distribution per Language\n"
        "(per_test vs per_class vs per_module vs global)"
    )
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels([lang_display(l) for l in present])
    ax2.set_ylim(0, 105)
    ax2.legend(loc="upper right", fontsize=8, ncol=2)
    ax2.axhline(50, color="#ddd", linewidth=0.5, linestyle=":", alpha=0.5)

    plt.tight_layout()
    save_or_show(fig, "06_fixture_overview", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Fixture Overview")
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

    conn = load_db(Path(args.db))
    setup_style()

    print("\n[Fixture Overview]")
    plot_fixture_overview(conn, out_dir, args.show)

    conn.close()
    print("Done\n")
