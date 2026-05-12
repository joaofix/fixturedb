"""
FixtureDB — Exploratory Data Analysis
======================================
Repository Maturity vs Fixture Quality
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from ..eda_common import (
    LANG_PALETTE,
    LANG_ORDER,
    setup_style,
    save_or_show,
    load_db,
    has_data,
    qdf,
    lang_display,
    DB_PATH,
    DEFAULT_OUT,
)


def plot_repo_maturity_vs_fixture_quality(conn, out_dir, show):
    """Relationship between repository maturity and fixture quality."""
    if not has_data(conn, "repositories") or not has_data(conn, "fixtures"):
        print("  [skip] Missing repository or fixture data.")
        return

    # Get repository-level metrics
    repo_metrics = qdf(
        conn,
        """
        SELECT r.id, r.language, r.stars, r.forks, r.num_contributors,
               COUNT(f.id) as num_fixtures,
               AVG(f.cyclomatic_complexity) as avg_complexity,
               AVG(f.loc) as avg_loc,
               AVG(f.reuse_count) as avg_reuse
        FROM repositories r
        LEFT JOIN fixtures f ON r.id = f.repo_id
        WHERE r.status = 'analysed'
        GROUP BY r.id, r.language, r.stars, r.forks, r.num_contributors
    """,
    )

    if repo_metrics.empty:
        print("  [skip] No repository metrics.")
        return

    repo_metrics = repo_metrics[repo_metrics["num_fixtures"] > 0].copy()
    present = [l for l in LANG_ORDER if l in repo_metrics["language"].unique()]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="#FAFAFA")
    axes = axes.flatten()

    # Panel 1: Stars vs Avg Fixture Complexity
    ax = axes[0]
    for lang in present:
        sub = repo_metrics[repo_metrics["language"] == lang]
        ax.scatter(
            sub["stars"],
            sub["avg_complexity"],
            alpha=0.5,
            s=40,
            color=LANG_PALETTE[lang],
            label=lang_display(lang),
        )
    ax.set_xlabel("GitHub Stars", fontsize=11)
    ax.set_ylabel("Avg Cyclomatic Complexity", fontsize=11)
    ax.set_title("(a) Popularity vs Fixture Complexity", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(alpha=0.3, linestyle="--")
    ax.set_xscale("log")
    ax.set_xlim(500, 100000)

    # Panel 2: Contributors vs Avg Fixture LOC
    ax = axes[1]
    for lang in present:
        sub = repo_metrics[repo_metrics["language"] == lang]
        ax.scatter(
            sub["num_contributors"],
            sub["avg_loc"],
            alpha=0.5,
            s=40,
            color=LANG_PALETTE[lang],
            label=lang_display(lang),
        )
    ax.set_xlabel("Number of Contributors", fontsize=11)
    ax.set_ylabel("Avg Fixture Lines of Code", fontsize=11)
    ax.set_title("(b) Team Size vs Fixture Size", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(alpha=0.3, linestyle="--")
    ax.set_xscale("log")

    # Panel 3: Forks vs Avg Fixture Reuse
    ax = axes[2]
    for lang in present:
        sub = repo_metrics[repo_metrics["language"] == lang]
        sub = sub[sub["avg_reuse"] > 0]  # Only repos with reuse data
        ax.scatter(
            sub["forks"],
            sub["avg_reuse"],
            alpha=0.5,
            s=40,
            color=LANG_PALETTE[lang],
            label=lang_display(lang),
        )
    ax.set_xlabel("GitHub Forks", fontsize=11)
    ax.set_ylabel("Avg Fixture Reuse Count", fontsize=11)
    ax.set_title("(c) Forks vs Fixture Reuse", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(alpha=0.3, linestyle="--")
    ax.set_xscale("log")

    # Panel 4: Repository characteristics table
    ax = axes[3]
    ax.axis("off")

    stats_data = []
    for lang in present:
        sub = repo_metrics[repo_metrics["language"] == lang]
        stats_data.append(
            [
                lang_display(lang),
                f"{len(sub)}",
                f"{sub['stars'].mean():.0f}",
                f"{sub['num_contributors'].median():.0f}",
                f"{sub['avg_complexity'].mean():.2f}",
                f"{sub['avg_loc'].mean():.1f}",
            ]
        )

    table = ax.table(
        cellText=stats_data,
        colLabels=[
            "Lang",
            "Repos",
            "Avg Stars",
            "Med Contributors",
            "Avg Complexity",
            "Avg LOC",
        ],
        cellLoc="center",
        loc="center",
        colWidths=[0.12, 0.12, 0.18, 0.2, 0.18, 0.12],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2.5)

    for i in range(len(present) + 1):
        table[(i, 0)].set_facecolor("#E8E8E8" if i == 0 else "#F5F5F5")
        for j in range(6):
            table[(i, j)].set_edgecolor("#CCCCCC")

    fig.suptitle(
        "Repository Maturity vs Fixture Quality",
        fontsize=14,
        fontweight="bold",
        y=0.995,
    )

    plt.tight_layout()
    save_or_show(fig, "05i_repo_maturity", out_dir, show)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="FixtureDB Repository Maturity vs Fixture Quality"
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_repo_maturity_vs_fixture_quality(
        conn, args.out if not args.show else None, args.show
    )
    conn.close()
