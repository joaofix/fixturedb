"""
FixtureDB — Exploratory Data Analysis
======================================
Repository Activity Recency
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    LANG_ORDER,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)


def plot_activity_recency(conn, out_dir, show):
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
        pd.Timestamp.now("UTC")
        - pd.to_datetime(repos["pushed_at"], errors="coerce", utc=True)
    ).dt.days.clip(lower=0)

    present = [l for l in LANG_ORDER if l in repos["language"].values]
    repos = repos[repos["language"].isin(present)]

    fig, ax = plt.subplots(figsize=(10, 6), facecolor="#FAFAFA")

    # Calculate median days since push for each language
    stats = []
    for lang in present:
        lang_data = repos[repos["language"] == lang]["days_since_push"]
        median_days = lang_data.median()
        mean_days = lang_data.mean()
        stats.append(
            {
                "language": lang,
                "median": median_days,
                "mean": mean_days,
            }
        )

    stats_df = pd.DataFrame(stats).set_index("language")
    stats_df = stats_df.reindex(present)

    # Simple grouped bar chart: median and mean days since push
    x = np.arange(len(present))
    width = 0.35

    bars1 = ax.bar(
        x - width / 2,
        stats_df["median"],
        width,
        label="Median",
        color="#3498db",
        alpha=0.85,
        edgecolor="black",
        linewidth=1,
    )
    bars2 = ax.bar(
        x + width / 2,
        stats_df["mean"],
        width,
        label="Mean",
        color="#e74c3c",
        alpha=0.85,
        edgecolor="black",
        linewidth=1,
    )

    # Add value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{int(height)}d",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

    ax.set_ylabel("Days Since Last Push", fontsize=11, fontweight="bold")
    ax.set_title(
        "Repository Activity: How Long Since Last Commit?\n"
        "(Shorter bars = more recently active repositories)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([lang_display(l) for l in present], fontsize=10)
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, stats_df.max().max() * 1.15)

    plt.tight_layout()
    save_or_show(fig, "02b_activity_recency", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FixtureDB Repository Activity Recency"
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_activity_recency(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
