"""
FixtureDB — Exploratory Data Analysis
======================================
Nesting Depth Distribution (extraction phase metric)
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
    SEQUENTIAL_BLUE,
    has_data,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)


def plot_nesting_depth(conn, out_dir, show):
    """
    Visualize max_nesting_depth distribution across languages.
    Shows what proportion of fixtures are shallow vs deeply nested.
    """
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.max_nesting_depth, r.language
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty or fixtures["max_nesting_depth"].isna().all():
        print("  [skip] No nesting depth data (run Phase 3 collection).")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]
    fixtures = fixtures[fixtures["language"].isin(present)]

    fig, ax = plt.subplots(figsize=(11, 6), facecolor="#FAFAFA")

    # Categorize fixtures by nesting depth
    def categorize_depth(depth):
        if depth <= 1:
            return "Flat (1)"
        elif depth <= 2:
            return "Shallow (2)"
        elif depth <= 3:
            return "Medium (3)"
        elif depth <= 4:
            return "Deep (4)"
        else:
            return "Very Deep (5+)"

    fixtures["depth_cat"] = fixtures["max_nesting_depth"].apply(categorize_depth)

    # Calculate percentages per language
    depth_order = [
        "Flat (1)",
        "Shallow (2)",
        "Medium (3)",
        "Deep (4)",
        "Very Deep (5+)",
    ]

    lang_labels = [lang_display(l) for l in present]
    x = np.arange(len(present))
    width = 0.6
    bottom = np.zeros(len(present))

    for i, depth_cat in enumerate(depth_order):
        percentages = []
        for lang in present:
            lang_data = fixtures[fixtures["language"] == lang]
            pct = (lang_data["depth_cat"] == depth_cat).sum() / len(lang_data) * 100
            percentages.append(pct)

        ax.bar(
            x,
            percentages,
            width,
            label=depth_cat,
            bottom=bottom,
            color=SEQUENTIAL_BLUE[i],
            edgecolor="white",
            linewidth=1.5,
        )

        # Add percentage labels in the middle of each segment if large enough
        for j, pct in enumerate(percentages):
            if pct > 5:  # Only label if segment is large enough to read
                ax.text(
                    j,
                    bottom[j] + pct / 2,
                    f"{pct:.0f}%",
                    ha="center",
                    va="center",
                    fontweight="bold",
                    fontsize=9,
                    color="white",
                )

        bottom += percentages

    ax.set_ylabel("% of Fixtures", fontsize=11, fontweight="bold")
    ax.set_title(
        "Fixture Nesting Depth Distribution\n"
        "(What proportion of fixtures have deeply nested control flow?)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(lang_labels, fontsize=10)
    ax.set_ylim(0, 105)
    ax.legend(
        fontsize=10,
        loc="upper left",
        bbox_to_anchor=(1, 1),
        title="Nesting Depth Level",
    )
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_or_show(fig, "05a_nesting_depth", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Nesting Depth Analysis")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_nesting_depth(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
