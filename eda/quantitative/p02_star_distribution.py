"""
FixtureDB — Exploratory Data Analysis
======================================
Individual plot script.
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
    SEQUENTIAL_PALETTE,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)

# -----------
# STAR DISTRIBUTION
# -----------


def plot_star_distribution(conn, out_dir, show):
    repos = qdf(
        conn, "SELECT language, stars FROM repositories WHERE stars IS NOT NULL"
    )
    if repos.empty:
        print("  [skip] No star data.")
        return

    present = [l for l in LANG_ORDER if l in repos["language"].values]
    repos = repos[repos["language"].isin(present)]

    fig, ax = plt.subplots(figsize=(11, 6), facecolor="#FAFAFA")

    # Define star tiers (simple and intuitive)
    def assign_tier(stars):
        if stars < 100:
            return "0–100 ★"
        elif stars < 500:
            return "100–500 ★"
        elif stars < 1000:
            return "500–1k ★"
        elif stars < 5000:
            return "1k–5k ★"
        else:
            return "5k+ ★"

    repos["tier"] = repos["stars"].apply(assign_tier)

    # Get tier counts per language
    tier_order = ["0–100 ★", "100–500 ★", "500–1k ★", "1k–5k ★", "5k+ ★"]

    data = []
    for lang in present:
        lang_repos = repos[repos["language"] == lang]
        tier_counts = {}
        for tier in tier_order:
            tier_counts[tier] = (lang_repos["tier"] == tier).sum()
        data.append(tier_counts)

    # Create stacked bar chart
    x = np.arange(len(present))
    width = 0.6
    bottom = np.zeros(len(present))

    for i, tier in enumerate(tier_order):
        counts = [data[j].get(tier, 0) for j in range(len(present))]
        ax.bar(
            x,
            counts,
            width,
            label=tier,
            bottom=bottom,
            color=SEQUENTIAL_PALETTE[i],
            edgecolor="white",
            linewidth=1.5,
        )
        bottom += counts

    ax.set_ylabel("# Repositories", fontsize=11, fontweight="bold")
    ax.set_title(
        "Repository Corpus by Star Popularity\n"
        "(Stacked by star tier — shows heavily star-sorted collection)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([lang_display(l) for l in present], fontsize=10)
    ax.legend(fontsize=10, loc="upper left", title="Star Tier", title_fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_or_show(fig, "02_star_distribution", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Star Distribution")
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

    print("\n[Star Distribution]")
    plot_star_distribution(conn, out_dir, args.show)

    conn.close()
    print("Done\n")
