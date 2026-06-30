"""
FixtureDB — Exploratory Data Analysis
======================================
Fixture Reuse Distribution Analysis (Phase 3)
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


def plot_fixture_reuse_distribution(conn, out_dir, show):
    """
    Analyze fixture reuse patterns - how many tests share individual fixtures?
    Simple: Percentage of single-use (reuse=1) vs multi-use (reuse>1) fixtures per language.
    """
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.reuse_count, r.language
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty or fixtures["reuse_count"].isna().all():
        print("  [skip] No reuse count data (run Phase 3 collection).")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]
    fixtures = fixtures[fixtures["language"].isin(present)]

    fig, ax = plt.subplots(figsize=(11, 6), facecolor="#FAFAFA")

    # Calculate single-use vs multi-use percentages per language
    single_use_pcts = []
    multi_use_pcts = []
    labels = []

    for lang in present:
        lang_data = fixtures[fixtures["language"] == lang]["reuse_count"]
        single_use = (lang_data == 1).sum()
        multi_use = (lang_data > 1).sum()
        total = len(lang_data)

        single_use_pcts.append(single_use / total * 100)
        multi_use_pcts.append(multi_use / total * 100)
        labels.append(lang_display(lang))

    # Stacked bar chart
    x = np.arange(len(present))
    width = 0.6

    p1 = ax.bar(
        x,
        single_use_pcts,
        width,
        label="Single-Use (reuse=1)",
        color="#e74c3c",
        edgecolor="black",
        linewidth=1,
    )
    p2 = ax.bar(
        x,
        multi_use_pcts,
        width,
        bottom=single_use_pcts,
        label="Multi-Use (reuse>1)",
        color="#2ecc71",
        edgecolor="black",
        linewidth=1,
    )

    # Add percentage labels
    for i, (single, multi) in enumerate(zip(single_use_pcts, multi_use_pcts)):
        ax.text(
            i,
            single / 2,
            f"{single:.1f}%",
            ha="center",
            va="center",
            fontweight="bold",
            fontsize=10,
            color="white",
        )
        ax.text(
            i,
            single + multi / 2,
            f"{multi:.1f}%",
            ha="center",
            va="center",
            fontweight="bold",
            fontsize=10,
            color="white",
        )

    ax.set_ylabel("% of Fixtures", fontsize=11, fontweight="bold")
    ax.set_title(
        "Fixture Reuse Patterns: Single-Use vs Shared\n"
        "(Most fixtures are single-use, few are shared across tests)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=10, loc="upper left", bbox_to_anchor=(1, 1))
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_or_show(fig, "05c_fixture_reuse_distribution", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Fixture Reuse Distribution")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_fixture_reuse_distribution(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
