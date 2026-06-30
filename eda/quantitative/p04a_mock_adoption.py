"""
FixtureDB — Exploratory Data Analysis
======================================
Mock Adoption Rate
"""

import argparse
from datetime import datetime
from pathlib import Path

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


def plot_mock_adoption(conn, out_dir, show):
    if not has_data(conn, "mock_usages"):
        print("  [skip] No mock data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT f.id, r.language,
               (SELECT COUNT(*) FROM mock_usages m WHERE m.fixture_id = f.id) AS mock_count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#FAFAFA")

    fixtures["has_mock"] = fixtures["mock_count"] > 0
    prevalence = (
        fixtures[fixtures["language"].isin(present)]
        .groupby("language")["has_mock"]
        .mean()
        .reindex(present)
        * 100
    )
    y_pos = range(len(present))

    ax.barh(
        list(y_pos),
        prevalence.values,
        color=[LANG_PALETTE[l] for l in present],
        height=0.55,
        zorder=3,
    )

    for y, pct, lang in zip(y_pos, prevalence.values, present):
        ax.text(
            pct + 1.2,
            y,
            f"{pct:.1f}%",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=LANG_PALETTE[lang],
        )

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([lang_display(l) for l in present])
    ax.set_xlabel("Fixtures containing at least one mock call (%)")
    ax.set_xlim(0, min(100, prevalence.max() + 15))
    ax.set_title("What Share of Fixtures Use Mocking?", fontsize=14, fontweight="bold")
    ax.axvline(0, color="#ccc", linewidth=0.5)

    plt.tight_layout()
    save_or_show(fig, "04a_mock_adoption", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Mock Adoption Rate")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_mock_adoption(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
