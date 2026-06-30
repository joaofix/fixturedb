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
# STARS VS FORKS
# -----------


def plot_fork_star_ratio(conn, out_dir, show):
    repos = qdf(
        conn,
        """
        SELECT language, stars, forks
        FROM repositories
        WHERE stars > 0 AND forks > 0
    """,
    )
    if repos.empty:
        print("  [skip] No fork/star data.")
        return

    present = [l for l in LANG_ORDER if l in repos["language"].values]

    fig, ax = plt.subplots(figsize=(9, 6), facecolor="#FAFAFA")

    for lang in present:
        sub = repos[repos["language"] == lang]
        ax.scatter(
            sub["stars"],
            sub["forks"],
            color=LANG_PALETTE[lang],
            label=lang_display(lang),
            alpha=0.35,
            s=18,
            linewidths=0,
            zorder=3,
        )

    # Diagonal: forks == stars
    lim_max = repos[["stars", "forks"]].max().max() * 2
    lim_min = 1
    ax.plot(
        [lim_min, lim_max],
        [lim_min, lim_max],
        color="#555",
        linewidth=0.9,
        linestyle="--",
        alpha=0.6,
        label="forks = stars",
        zorder=2,
    )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_xlabel("Stars (log scale)")
    ax.set_ylabel("Forks (log scale)")
    ax.set_title(
        "Stars vs. Forks per Repository\n"
        "Points above the diagonal are forked more than starred"
    )
    ax.legend(fontsize=9, markerscale=1.5)

    plt.tight_layout()
    save_or_show(fig, "05_stars_vs_forks", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Stars vs Forks")
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

    print("\n[Stars vs Forks]")
    plot_fork_star_ratio(conn, out_dir, args.show)

    conn.close()
    print("Done\n")
