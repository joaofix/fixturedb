"""
FixtureDB — Exploratory Data Analysis
======================================
Fixture Scope Distribution
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    LANG_ORDER,
    has_data,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)


def plot_fixture_scope(conn, out_dir, show):
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.scope, r.language
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#FAFAFA")

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

    scope_order = ["per_test", "per_class", "per_module", "global"]
    scope_order = [s for s in scope_order if s in pivot_scope_pct.columns]
    pivot_scope_pct = pivot_scope_pct[scope_order]

    scope_colors = {
        "per_test": "#4ECDC4",
        "per_class": "#FFE66D",
        "per_module": "#FF6B6B",
        "global": "#95B8D1",
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

        for i, (bar, val) in enumerate(zip(bars, vals)):
            if val > 5:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bottom[i] + val / 2,
                    f"{val:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                    fontweight="bold",
                    color="white" if scope != "per_class" else "#333",
                )
        bottom += vals

    ax.set_ylabel("Share of Fixtures (%)")
    ax.set_xlabel("")
    ax.set_title(
        "Fixture Scope Distribution per Language", fontsize=14, fontweight="bold"
    )
    ax.set_xticks(x_pos)
    ax.set_xticklabels([lang_display(l) for l in present])
    ax.set_ylim(0, 105)
    ax.legend(loc="upper left", fontsize=9, ncol=2, bbox_to_anchor=(1, 1))
    ax.axhline(50, color="#ddd", linewidth=0.5, linestyle=":", alpha=0.5)

    plt.tight_layout()
    save_or_show(fig, "03b_fixture_scope", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Fixture Scope Distribution")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_fixture_scope(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
