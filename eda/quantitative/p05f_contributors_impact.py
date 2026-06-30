"""
FixtureDB — Exploratory Data Analysis
======================================
Project Team Size vs Fixture Quality (Phase 3)
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


def plot_contributors_impact(conn, out_dir, show):
    """
    Do projects with more team members have higher quality fixtures?
    Simple: Scatter plot of team size vs average fixture complexity.
    """
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    # Aggregate fixture metrics to repo level
    repos = qdf(
        conn,
        """
        SELECT r.id, r.num_contributors, r.language,
               AVG(f.cyclomatic_complexity) as avg_cc
        FROM repositories r
        LEFT JOIN fixtures f ON r.id = f.repo_id
        WHERE r.status = 'analysed' AND r.num_contributors > 0
        GROUP BY r.id
    """,
    )

    if repos.empty or repos["num_contributors"].isna().all():
        print("  [skip] No contributor data (run Phase 3 collection).")
        return

    present = [l for l in LANG_ORDER if l in repos["language"].values]
    repos = repos[repos["language"].isin(present)]

    fig, ax = plt.subplots(figsize=(11, 6), facecolor="#FAFAFA")

    # Scatter plot: team size vs average complexity
    for lang in present:
        data = repos[repos["language"] == lang]
        ax.scatter(
            data["num_contributors"],
            data["avg_cc"],
            alpha=0.5,
            s=40,
            color=LANG_PALETTE[lang],
            edgecolors="none",
        )

    # Trend line
    x = repos["num_contributors"].values
    y = repos["avg_cc"].values
    z = np.polyfit(np.log10(x + 1), y, 1)  # Log scale for contributors
    p = np.poly1d(z)
    x_line = np.logspace(-0.5, np.log10(x.max()), 100)
    y_line = p(np.log10(x_line + 1))
    ax.plot(x_line, y_line, "r--", alpha=0.8, linewidth=2.5, label="Trend")

    corr = repos["num_contributors"].corr(repos["avg_cc"])

    ax.set_xscale("log")
    ax.set_xlabel("Number of Contributors  (log scale)", fontsize=11)
    ax.set_ylabel("Average Fixture Cyclomatic Complexity", fontsize=11)
    ax.set_title(
        f"Team Size vs Fixture Complexity\n"
        f"Correlation:  r={corr:.2f}  (do larger teams write simpler or more complex fixtures?)",
        fontsize=12,
        fontweight="bold",
    )
    ax.grid(alpha=0.3, which="both")

    # Add color legend for languages
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor=LANG_PALETTE[l], label=lang_display(l)) for l in present
    ]
    ax.legend(
        handles=legend_elements
        + [plt.Line2D([0], [0], color="r", linestyle="--", linewidth=2)],
        fontsize=9,
        loc="best",
        title="Languages",
    )

    plt.tight_layout()
    save_or_show(fig, "05f_contributors_impact", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Contributors Impact")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_contributors_impact(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
