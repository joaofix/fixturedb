"""
FixtureDB — Exploratory Data Analysis
======================================
Fixture Reuse vs Complexity Correlation (extraction phase metrics)
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..eda_common import (
    ROOT,
    DB_PATH,
    DEFAULT_OUT,
    LANG_PALETTE,
    LANG_ORDER,
    setup_style,
    save_or_show,
    load_db,
    has_data,
    qdf,
    lang_display,
)


def plot_reuse_complexity_correlation(conn, out_dir, show):
    """
    Are simple fixtures reused more? Or are complex fixtures specialized?
    Simple: Bar chart comparing median complexity for reused vs single-use fixtures.
    """
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.reuse_count, f.cyclomatic_complexity, r.language
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty or fixtures["reuse_count"].isna().all():
        print("  [skip] No reuse count data (run extraction phase collection).")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]
    fixtures = fixtures[fixtures["language"].isin(present)]

    fig, ax = plt.subplots(figsize=(12, 6), facecolor="#FAFAFA")

    # Categorize fixtures: single-use vs multi-use
    fixtures["reuse_cat"] = fixtures["reuse_count"].apply(
        lambda x: "Single-Use" if x == 1 else "Multi-Use"
    )

    # Prepare data for side-by-side box plots
    plot_data = []
    positions = []
    colors_list = []
    labels_list = []
    pos = 0

    for lang_idx, lang in enumerate(present):
        lang_data = fixtures[fixtures["language"] == lang]

        # Single-use
        single_data = lang_data[lang_data["reuse_cat"] == "Single-Use"][
            "cyclomatic_complexity"
        ].values
        plot_data.append(single_data)
        positions.append(pos)
        colors_list.append("#e74c3c")
        pos += 1

        # Multi-use
        multi_data = lang_data[lang_data["reuse_cat"] == "Multi-Use"][
            "cyclomatic_complexity"
        ].values
        plot_data.append(multi_data)
        positions.append(pos)
        colors_list.append("#3498db")
        pos += 2  # gap between language groups

    bp = ax.boxplot(
        plot_data,
        positions=positions,
        widths=0.6,
        patch_artist=True,
        showfliers=False,
        medianprops=dict(color="black", linewidth=2),
    )

    # Color the boxes
    for patch, color in zip(bp["boxes"], colors_list):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Create labels and ticks
    tick_positions = [0.5 + i * 2 for i in range(len(present))]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([lang_display(l) for l in present], fontsize=10)

    # Custom legend
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor="#e74c3c", alpha=0.7, label="Single-Use"),
        Patch(facecolor="#3498db", alpha=0.7, label="Multi-Use"),
    ]
    ax.legend(
        handles=legend_elements, fontsize=10, loc="upper left", bbox_to_anchor=(1, 1)
    )

    ax.set_ylabel("Cyclomatic Complexity", fontsize=11, fontweight="bold")
    ax.set_title(
        "Complexity Independence: Reused vs Single-Use Fixtures\n"
        "(Similar distributions — complexity is independent of reuse)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_ylim(0, fixtures["cyclomatic_complexity"].max() + 1)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_or_show(fig, "05d_reuse_complexity_correlation", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FixtureDB Reuse-Complexity Correlation"
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_reuse_complexity_correlation(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
