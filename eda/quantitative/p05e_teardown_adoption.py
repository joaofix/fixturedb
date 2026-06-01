"""
FixtureDB — Exploratory Data Analysis
======================================
Cleanup/Teardown Adoption (extraction phase metrics)
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


def plot_teardown_adoption(conn, out_dir, show):
    """
    What % of fixtures have cleanup/teardown logic?
    Shows resource management discipline across languages.
    """
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.has_teardown_pair, r.language
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty or fixtures["has_teardown_pair"].isna().all():
        print("  [skip] No teardown pair data (run extraction phase collection).")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]
    fixtures = fixtures[fixtures["language"].isin(present)]

    fig, ax = plt.subplots(figsize=(11, 6), facecolor="#FAFAFA")

    # Calculate adoption % per language
    adoption_pct = []
    lang_names = []
    for lang in present:
        lang_data = fixtures[fixtures["language"] == lang]["has_teardown_pair"]
        pct = 100 * (lang_data == 1).sum() / len(lang_data) if len(lang_data) > 0 else 0
        adoption_pct.append(pct)
        lang_names.append(lang_display(lang))

    # Color bars: green if ≥50%, orange if ≥25%, red otherwise
    colors = [
        "#2ecc71" if p >= 50 else "#f39c12" if p >= 25 else "#e74c3c"
        for p in adoption_pct
    ]
    bars = ax.bar(
        lang_names,
        adoption_pct,
        color=colors,
        alpha=0.8,
        edgecolor="black",
        linewidth=0.7,
    )

    # Add percentage labels on bars
    for bar, pct in zip(bars, adoption_pct):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{pct:.0f}%",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_ylabel("Adoption Rate  (%)", fontsize=11)
    ax.set_title(
        "Fixture Cleanup/Teardown Adoption\n(% of fixtures with cleanup logic)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(50, color="gray", linestyle="--", alpha=0.4, linewidth=1)
    ax.text(len(lang_names) - 0.5, 52, "50% threshold", fontsize=9, alpha=0.6)

    # Add overall statistics
    total_with = (fixtures["has_teardown_pair"] == 1).sum()
    total_without = (fixtures["has_teardown_pair"] == 0).sum()
    overall_pct = 100 * total_with / (total_with + total_without)

    summary = f"Overall: {overall_pct:.1f}% have teardown  ({total_with:,}/{total_with + total_without:,})"
    ax.text(
        0.02,
        0.97,
        summary,
        transform=ax.transAxes,
        fontsize=9,
        va="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.3),
    )

    plt.tight_layout()
    save_or_show(fig, "05e_teardown_adoption", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Teardown Adoption")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_teardown_adoption(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
