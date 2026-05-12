"""
FixtureDB — Exploratory Data Analysis
======================================
Test File Characteristics: Size vs Fixture Count
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

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


def plot_test_file_characteristics(conn, out_dir, show):
    """Relationship between test file size and fixture count."""
    if not has_data(conn, "test_files"):
        print("  [skip] No test file data yet. Run `python pipeline.py extract`.")
        return

    test_files = qdf(
        conn,
        """
        SELECT r.language, tf.file_loc, tf.num_fixtures, tf.num_test_funcs
        FROM test_files tf
        JOIN repositories r ON tf.repo_id = r.id
        WHERE r.status = 'analysed' AND tf.file_loc > 0 AND tf.num_fixtures > 0
    """,
    )

    if test_files.empty:
        print("  [skip] No test file data.")
        return

    present = [l for l in LANG_ORDER if l in test_files["language"].unique()]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="#FAFAFA")
    axes = axes.flatten()

    # Panel 1: File LOC vs Fixture Count (scatter)
    ax = axes[0]
    for lang in present:
        sub = test_files[test_files["language"] == lang]
        if len(sub) > 5000:
            sub = sub.sample(5000, random_state=42)
        ax.scatter(
            sub["file_loc"],
            sub["num_fixtures"],
            alpha=0.4,
            s=25,
            color=LANG_PALETTE[lang],
            label=lang_display(lang),
        )
    ax.set_xlabel("File Lines of Code", fontsize=11)
    ax.set_ylabel("Number of Fixtures", fontsize=11)
    ax.set_title("(a) Test File Size vs Fixture Count", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(alpha=0.3, linestyle="--")
    ax.set_xlim(0, 2000)
    ax.set_ylim(0, 100)

    # Panel 2: File LOC distribution by language
    ax = axes[1]
    box_data = [
        test_files[test_files["language"] == l]["file_loc"].values for l in present
    ]
    bp = ax.boxplot(
        box_data,
        labels=[lang_display(l) for l in present],
        patch_artist=True,
        widths=0.6,
    )
    for patch, lang in zip(bp["boxes"], present):
        patch.set_facecolor(LANG_PALETTE[lang])
        patch.set_alpha(0.7)
    ax.set_ylabel("File Lines of Code", fontsize=11)
    ax.set_title("(b) Test File Size Distribution", fontsize=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_ylim(0, 1500)

    # Panel 3: Number of fixtures per file distribution
    ax = axes[2]
    for lang in present:
        data = test_files[test_files["language"] == lang]["num_fixtures"].values
        ax.hist(
            data,
            bins=25,
            alpha=0.6,
            label=lang_display(lang),
            color=LANG_PALETTE[lang],
            edgecolor="black",
            linewidth=0.5,
        )
    ax.set_xlabel("Fixtures per File", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("(c) Fixtures per Test File", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_xlim(0, 50)

    # Panel 4: Statistics table
    ax = axes[3]
    ax.axis("off")

    stats_data = []
    for lang in present:
        sub = test_files[test_files["language"] == lang]
        stats_data.append(
            [
                lang_display(lang),
                f"{len(sub):,}",
                f"{sub['file_loc'].mean():.0f}",
                f"{sub['num_fixtures'].mean():.2f}",
                f"{sub['num_test_funcs'].mean():.1f}",
            ]
        )

    table = ax.table(
        cellText=stats_data,
        colLabels=[
            "Language",
            "Test Files",
            "Avg LOC",
            "Avg Fixtures",
            "Avg Test Funcs",
        ],
        cellLoc="center",
        loc="center",
        colWidths=[0.18, 0.18, 0.18, 0.18, 0.18],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2.5)

    for i in range(len(present) + 1):
        table[(i, 0)].set_facecolor("#E8E8E8" if i == 0 else "#F5F5F5")
        for j in range(5):
            table[(i, j)].set_edgecolor("#CCCCCC")

    fig.suptitle(
        "Test File Characteristics: Size, Fixtures, and Test Functions",
        fontsize=14,
        fontweight="bold",
        y=0.995,
    )

    plt.tight_layout()
    save_or_show(fig, "05g_test_file_characteristics", out_dir, show)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FixtureDB Test File Characteristics")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_test_file_characteristics(conn, args.out if not args.show else None, args.show)
    conn.close()
