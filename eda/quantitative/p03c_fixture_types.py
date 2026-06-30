"""
FixtureDB — Exploratory Data Analysis
======================================
Fixture Type Distribution (Detection Patterns)
"""

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


def plot_fixture_types(conn, out_dir, show):
    """Distribution of fixture detection types across languages."""
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    # Get all fixtures with their types
    fixtures = qdf(
        conn,
        """
        SELECT r.language, f.fixture_type, COUNT(*) as count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed' AND f.fixture_type IS NOT NULL
        GROUP BY r.language, f.fixture_type
        ORDER BY r.language, count DESC
    """,
    )

    if fixtures.empty:
        print("  [skip] No fixture type data.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].unique()]

    # Get top 5 types overall
    top_types = qdf(
        conn,
        """
            SELECT f.fixture_type, COUNT(*) as count
            FROM fixtures f
            JOIN repositories r ON f.repo_id = r.id
            WHERE r.status = 'analysed' AND f.fixture_type IS NOT NULL
            GROUP BY f.fixture_type
            ORDER BY count DESC
            LIMIT 5
        """,
    )["fixture_type"].tolist()

    fig, axes = plt.subplots(1, len(present), figsize=(14, 4), facecolor="#FAFAFA")
    if len(present) == 1:
        axes = [axes]

    for ax, lang in zip(axes, present):
        sub = fixtures[fixtures["language"] == lang].copy()
        sub = sub[sub["fixture_type"].isin(top_types)].copy()
        sub = sub.sort_values("count", ascending=True)

        colors = [LANG_PALETTE[lang]] * len(sub)
        ax.barh(range(len(sub)), sub["count"].values, color=colors, alpha=0.8)

        ax.set_yticks(range(len(sub)))
        type_labels = [t.replace("_", "\n") for t in sub["fixture_type"].values]
        ax.set_yticklabels(type_labels, fontsize=9)
        ax.set_xlabel("Count", fontsize=10)
        ax.set_title(lang_display(lang), fontsize=12, fontweight="bold")
        ax.grid(axis="x", alpha=0.3, linestyle="--")

        for i, (val, ftype) in enumerate(
            zip(sub["count"].values, sub["fixture_type"].values)
        ):
            ax.text(
                val + 2, i, f"{int(val)}", va="center", fontsize=9, fontweight="bold"
            )

    fig.suptitle(
        "Top Fixture Detection Patterns by Language (Top 5 Globally)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )

    plt.tight_layout()
    save_or_show(fig, "03c_fixture_types", out_dir, show)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FixtureDB Fixture Type Distribution")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_fixture_types(conn, args.out if not args.show else None, args.show)
    conn.close()
