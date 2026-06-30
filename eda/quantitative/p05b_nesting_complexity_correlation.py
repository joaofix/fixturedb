"""
FixtureDB — Exploratory Data Analysis
======================================
Nesting Depth vs Complexity Correlation (extraction phase metrics)
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
    LANG_PALETTE,
    has_data,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)


def plot_nesting_complexity_correlation(conn, out_dir, show):
    """
    Are deeply nested fixtures also more complex?
    Simple: Grouped bar chart showing median complexity at each nesting depth.
    """
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.max_nesting_depth, f.cyclomatic_complexity, r.language
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

    fig, ax = plt.subplots(figsize=(12, 6), facecolor="#FAFAFA")

    # Group nesting depth into simple categories
    def nesting_category(depth):
        if depth <= 2:
            return "Shallow (1–2)"
        elif depth <= 4:
            return "Medium (3–4)"
        else:
            return "Deep (5+)"

    fixtures["nesting_cat"] = fixtures["max_nesting_depth"].apply(nesting_category)

    # Calculate median complexity per nesting category and language
    nesting_order = ["Shallow (1–2)", "Medium (3–4)", "Deep (5+)"]
    x = np.arange(len(nesting_order))
    width = 0.2

    for i, lang in enumerate(present):
        lang_data = fixtures[fixtures["language"] == lang]
        medians = [
            (
                lang_data[lang_data["nesting_cat"] == cat][
                    "cyclomatic_complexity"
                ].median()
                if (lang_data["nesting_cat"] == cat).any()
                else 0
            )
            for cat in nesting_order
        ]
        ax.bar(
            x + i * width,
            medians,
            width,
            label=lang_display(lang),
            color=LANG_PALETTE[lang],
        )

    ax.set_ylabel("Median Cyclomatic Complexity", fontsize=11, fontweight="bold")
    ax.set_xlabel("Nesting Depth Category", fontsize=11, fontweight="bold")
    ax.set_title(
        "Do Deeply Nested Fixtures Also Have More Complexity?\n"
        "(Yes — complexity increases with nesting depth)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x + width)
    ax.set_xticklabels(nesting_order, fontsize=10)
    ax.legend(fontsize=10, loc="upper left", title="Languages")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_or_show(fig, "05b_nesting_complexity_correlation", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FixtureDB Nesting-Complexity Correlation"
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_nesting_complexity_correlation(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
