"""
FixtureDB — Exploratory Data Analysis
======================================
Repository Creation Timeline
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    LANG_ORDER,
    LANG_PALETTE,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)


def plot_creation_timeline(conn, out_dir, show):
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

    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#FAFAFA")

    all_years = sorted(repos["created_year"].dropna().unique().astype(int))
    year_range = list(range(min(all_years), max(all_years) + 1))

    year_counts = {}
    for lang in present:
        sub = repos[repos["language"] == lang]["created_year"].dropna().astype(int)
        yearly = sub.value_counts().reindex(year_range, fill_value=0).sort_index()
        year_counts[lang] = yearly.values

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
    ax.set_title("When Were Repositories Created?", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in year_range])
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax.set_ylim(0, bottom.max() * 1.1)

    bottom = np.zeros(len(year_range))
    for lang in present:
        heights = year_counts[lang]
        for i, h in enumerate(heights):
            if h > 20:
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
    save_or_show(fig, "02a_creation_timeline", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FixtureDB Repository Creation Timeline"
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_creation_timeline(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
