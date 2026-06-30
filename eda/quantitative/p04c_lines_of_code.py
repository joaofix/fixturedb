"""
FixtureDB — Exploratory Data Analysis
======================================
Fixture Lines of Code Distribution
"""

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


def plot_lines_of_code(conn, out_dir, show):
    """Distribution of fixture lines of code (LOC) by language."""
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT r.language, f.loc
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed' AND f.loc > 0
    """,
    )

    if fixtures.empty:
        print("  [skip] No LOC data.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].unique()]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="#FAFAFA")
    axes = axes.flatten()

    # Panel 1: Box plots
    ax = axes[0]
    box_data = [fixtures[fixtures["language"] == l]["loc"].values for l in present]
    bp = ax.boxplot(
        box_data,
        labels=[lang_display(l) for l in present],
        patch_artist=True,
        widths=0.6,
    )
    for patch, lang in zip(bp["boxes"], present):
        patch.set_facecolor(LANG_PALETTE[lang])
        patch.set_alpha(0.7)
    ax.set_ylabel("Lines of Code", fontsize=11)
    ax.set_title("(a) Fixture LOC: Box Plot", fontsize=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_ylim(0, 50)  # Focus on main distribution, outliers will appear

    # Panel 2: Violin plots (log scale)
    ax = axes[1]
    parts = ax.violinplot(
        [
            np.log10(fixtures[fixtures["language"] == l]["loc"].values + 1)
            for l in present
        ],
        positions=range(len(present)),
        widths=0.7,
        showmeans=True,
        showmedians=True,
    )
    for pc in parts["bodies"]:
        pc.set_facecolor("#888")
        pc.set_alpha(0.5)
    ax.set_xticks(range(len(present)))
    ax.set_xticklabels([lang_display(l) for l in present])
    ax.set_ylabel("Lines of Code (log10 scale)", fontsize=11)
    ax.set_title(
        "(b) Fixture LOC: Distribution (log scale)", fontsize=12, fontweight="bold"
    )
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    # Panel 3: Histogram with KDE
    ax = axes[2]
    for lang in present:
        data = fixtures[fixtures["language"] == lang]["loc"].values
        ax.hist(
            data,
            bins=30,
            alpha=0.5,
            label=lang_display(lang),
            color=LANG_PALETTE[lang],
            edgecolor="black",
            linewidth=0.5,
        )
    ax.set_xlabel("Lines of Code", fontsize=11)
    ax.set_ylabel("Frequency", fontsize=11)
    ax.set_title("(c) Fixture LOC: Histogram", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_xlim(0, 100)

    # Panel 4: Summary statistics table
    ax = axes[3]
    ax.axis("off")

    stats_data = []
    for lang in present:
        data = fixtures[fixtures["language"] == lang]["loc"].values
        stats_data.append(
            [
                lang_display(lang),
                f"{len(data):,}",
                f"{data.mean():.1f}",
                f"{np.median(data):.0f}",
                f"{data.std():.1f}",
                f"{data.min()}",
                f"{data.max()}",
            ]
        )

    table = ax.table(
        cellText=stats_data,
        colLabels=["Language", "Count", "Mean", "Median", "Std Dev", "Min", "Max"],
        cellLoc="center",
        loc="center",
        colWidths=[0.15, 0.13, 0.13, 0.13, 0.13, 0.1, 0.1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)

    for i in range(len(present) + 1):
        table[(i, 0)].set_facecolor("#E8E8E8" if i == 0 else "#F5F5F5")
        for j in range(7):
            table[(i, j)].set_edgecolor("#CCCCCC")

    fig.suptitle(
        "Fixture Complexity: Lines of Code (LOC)",
        fontsize=14,
        fontweight="bold",
        y=0.995,
    )

    plt.tight_layout()
    save_or_show(fig, "04c_lines_of_code", out_dir, show)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FixtureDB Lines of Code Distribution")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_lines_of_code(conn, args.out if not args.show else None, args.show)
    conn.close()
