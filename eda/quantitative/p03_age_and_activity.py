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
import pandas as pd
import seaborn as sns

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

# -----------
# REPOSITORY AGE & ACTIVITY
# -----------


def plot_age_and_activity(conn, out_dir, show):
    repos = qdf(
        conn,
        """
        SELECT language, created_at, pushed_at
        FROM repositories WHERE created_at IS NOT NULL
    """,
    )
    if repos.empty:
        print("  [skip] No date data.")
        return

    repos["created_year"] = pd.to_datetime(repos["created_at"], errors="coerce").dt.year
    repos["days_since_push"] = (
        pd.Timestamp.now("UTC") - pd.to_datetime(repos["pushed_at"], errors="coerce")
    ).dt.days.clip(lower=0)

    present = [l for l in LANG_ORDER if l in repos["language"].values]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor="#FAFAFA")
    fig.suptitle("Repository Age & Activity", fontsize=14, fontweight="bold", y=1.02)

    # ── 3a: repo count per creation year (stacked bar by language) ───────────
    ax = axes[0]
    all_years = sorted(repos["created_year"].dropna().unique().astype(int))
    year_range = list(range(min(all_years), max(all_years) + 1))

    # Build matrix: rows = languages, columns = years
    year_counts = {}
    for lang in present:
        sub = repos[repos["language"] == lang]["created_year"].dropna().astype(int)
        yearly = sub.value_counts().reindex(year_range, fill_value=0).sort_index()
        year_counts[lang] = yearly.values

    # Stacked bar chart
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
    ax.set_title("When Were Repositories Created?\n(distribution across 2015–2017)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in year_range])
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.legend(loc="upper left", fontsize=8, framealpha=0.95)
    ax.set_ylim(0, bottom.max() * 1.1)

    # Add count labels on each segment
    bottom = np.zeros(len(year_range))
    for lang in present:
        heights = year_counts[lang]
        for i, h in enumerate(heights):
            if h > 20:  # Only label segments larger than 20 repos
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

    # ── 3b: years since last push — remove single worst outlier per language ──
    ax2 = axes[1]
    plot_data = repos[repos["language"].isin(present)].copy()
    plot_data["years_since_push"] = plot_data["days_since_push"] / 365.25

    # Drop the single maximum value per language — enough to fix stretched whiskers
    worst_idx = plot_data.groupby("language")["years_since_push"].idxmax()
    plot_data = plot_data.drop(index=worst_idx).reset_index(drop=True)

    sns.boxplot(
        data=plot_data,
        x="language",
        y="years_since_push",
        order=present,
        palette={l: LANG_PALETTE[l] for l in present},
        showfliers=False,
        linewidth=0.9,
        width=0.5,
        ax=ax2,
    )
    ax2.set_xticklabels([lang_display(l) for l in present])
    ax2.set_xlabel("")
    ax2.set_ylabel("Years Since Last Commit Push")
    ax2.set_title("How Recently Were Repos Active?")
    ax2.axhline(
        1.0, color="#888", linewidth=0.8, linestyle="--", alpha=0.7, label="1 year ago"
    )
    ax2.legend(fontsize=8)

    plt.tight_layout()
    save_or_show(fig, "03_age_and_activity", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Repository Age & Activity")
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

    print("\n[Repository Age & Activity]")
    plot_age_and_activity(conn, out_dir, args.show)

    conn.close()
    print("Done\n")
