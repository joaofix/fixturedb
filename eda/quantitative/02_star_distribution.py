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

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#FAFAFA")

    # Ridge plot: one density curve per language
    from scipy import stats

    repos_clipped = repos.copy()
    repos_clipped["stars"] = repos_clipped["stars"].clip(lower=1)
    repos_clipped["log_stars"] = np.log10(repos_clipped["stars"])

    x_range = np.logspace(
        np.log10(repos_clipped["stars"].min()),
        np.log10(repos_clipped["stars"].max()),
        200,
    )
    x_log = np.log10(x_range)

    y_offset = 0
    for i, lang in enumerate(present):
        sub = repos_clipped[repos_clipped["language"] == lang]["log_stars"].values
        if len(sub) > 1:
            kde = stats.gaussian_kde(sub, bw_method=0.15)
            density = kde(x_log)
            # Normalize density for stacking
            density = density / density.max() * 0.8

            # Fill area under curve
            ax.fill_between(
                x_range,
                y_offset,
                y_offset + density,
                color=LANG_PALETTE[lang],
                alpha=0.7,
                label=lang_display(lang),
                zorder=len(present) - i,
            )
            # Edge line
            ax.plot(
                x_range,
                y_offset + density,
                color=LANG_PALETTE[lang],
                linewidth=1.2,
                zorder=len(present) - i + 1,
            )
            y_offset += 1

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.axvline(
        500,
        color="#333",
        linewidth=1.0,
        linestyle="--",
        alpha=0.7,
        label="500 ★  core threshold",
        zorder=100,
    )
    ax.axvline(
        100,
        color="#888",
        linewidth=0.8,
        linestyle=":",
        alpha=0.7,
        label="100 ★  minimum",
        zorder=100,
    )
    ax.set_xlabel("Stars (log scale)")
    ax.set_ylabel("Language (density, offset)")
    ax.set_title("How Popular Are the Repos We Collected?\n(ridge plot, log scale)")
    ax.set_yticks([])
    ax.legend(fontsize=9, loc="upper right")

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
