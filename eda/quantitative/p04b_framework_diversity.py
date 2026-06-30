"""
FixtureDB — Exploratory Data Analysis
======================================
Mock Framework Diversity
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt

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


def plot_framework_diversity(conn, out_dir, show):
    if not has_data(conn, "mock_usages"):
        print("  [skip] No mock data yet. Run `python pipeline.py extract`.")
        return

    mocks = qdf(
        conn,
        """
        SELECT m.framework, r.language
        FROM mock_usages m
        JOIN repositories r ON m.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if mocks.empty:
        print("  [skip] No mocking data.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT r.language
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#FAFAFA")

    fw_counts = (
        mocks[mocks["language"].isin(present)]
        .groupby(["language", "framework"])
        .size()
        .reset_index(name="n")
    )
    pivot = (
        fw_counts.pivot(index="language", columns="framework", values="n")
        .reindex(present)
        .fillna(0)
    )
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
    fws = list(pivot_pct.columns)

    y_pos = range(len(present))
    for i, lang in enumerate(present):
        base = LANG_PALETTE[lang]
        base_rgb = mcolors.to_rgb(base)
        shades = [
            tuple(c * (0.4 + 0.6 * j / max(len(fws) - 1, 1)) for c in base_rgb)
            for j in range(len(fws))
        ]
        left = 0.0
        for j, (fw, shade) in enumerate(zip(fws, shades)):
            w = pivot_pct.loc[lang, fw]
            if w > 0:
                ax.barh(i, w, left=left, color=shade, height=0.55, zorder=3)
                if w > 6:
                    ax.text(
                        left + w / 2,
                        i,
                        fw.replace("_", "\n"),
                        ha="center",
                        va="center",
                        fontsize=7,
                        color="white",
                        fontweight="bold",
                    )
            left += w

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([lang_display(l) for l in present])
    ax.set_xlabel("Share of mock calls using each framework (%)")
    ax.set_xlim(0, 105)
    ax.set_title(
        "Which Mocking Frameworks Do Developers Use?", fontsize=14, fontweight="bold"
    )

    plt.tight_layout()
    save_or_show(fig, "04b_framework_diversity", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Mock Framework Diversity")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_framework_diversity(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
