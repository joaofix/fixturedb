"""
FixtureDB — Exploratory Data Analysis
======================================
Fixture Design Patterns: Parameters, External Calls, Object Instantiation
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


def plot_fixture_design_patterns(conn, out_dir, show):
    """Distribution of fixture design patterns across languages."""
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT r.language, f.num_parameters, f.num_objects_instantiated,
               f.num_external_calls, f.has_teardown_pair
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )

    if fixtures.empty:
        print("  [skip] No fixture design data.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].unique()]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="#FAFAFA")
    axes = axes.flatten()

    # Panel 1: Number of Parameters Distribution
    ax = axes[0]
    for lang in present:
        data = fixtures[fixtures["language"] == lang]["num_parameters"].values
        data_clipped = np.clip(data, 0, np.percentile(data, 95))
        ax.hist(
            data_clipped,
            bins=20,
            alpha=0.6,
            label=lang_display(lang),
            color=LANG_PALETTE[lang],
            edgecolor="black",
            linewidth=0.5,
        )
    ax.set_xlabel("Number of Parameters", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("(a) Fixture Parameters", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_xlim(0, 10)

    # Panel 2: Number of External Calls Distribution
    ax = axes[1]
    for lang in present:
        data = fixtures[fixtures["language"] == lang]["num_external_calls"].values
        data_clipped = np.clip(data, 0, np.percentile(data, 95))
        ax.hist(
            data_clipped,
            bins=20,
            alpha=0.6,
            label=lang_display(lang),
            color=LANG_PALETTE[lang],
            edgecolor="black",
            linewidth=0.5,
        )
    ax.set_xlabel("Number of External Calls", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("(b) External I/O and API Calls", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_xlim(0, 15)

    # Panel 3: Number of Objects Instantiated Distribution
    ax = axes[2]
    for lang in present:
        data = fixtures[fixtures["language"] == lang]["num_objects_instantiated"].values
        data_clipped = np.clip(data, 0, np.percentile(data, 95))
        ax.hist(
            data_clipped,
            bins=20,
            alpha=0.6,
            label=lang_display(lang),
            color=LANG_PALETTE[lang],
            edgecolor="black",
            linewidth=0.5,
        )
    ax.set_xlabel("Objects Instantiated", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("(c) Object Instantiations", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_xlim(0, 15)

    # Panel 4: Teardown Adoption by Language
    ax = axes[3]
    teardown_stats = qdf(
        conn,
        """
        SELECT r.language, 
               CAST(SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS teardown_pct
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
        GROUP BY r.language
        ORDER BY teardown_pct DESC
    """,
    )

    teardown_stats = teardown_stats[
        teardown_stats["language"].isin(present)
    ].sort_values("language")
    teardown_stats = teardown_stats.set_index("language").loc[present]

    y_pos = np.arange(len(teardown_stats))
    colors = [LANG_PALETTE[l] for l in teardown_stats.index]

    bars = ax.barh(
        y_pos, teardown_stats["teardown_pct"].values, color=colors, alpha=0.8
    )

    ax.set_yticks(y_pos)
    ax.set_yticklabels([lang_display(l) for l in teardown_stats.index])
    ax.set_xlabel("Adoption Rate (%)", fontsize=11)
    ax.set_title(
        "(d) Fixtures with Teardown/Cleanup Code", fontsize=12, fontweight="bold"
    )
    ax.set_xlim(0, 50)
    ax.grid(axis="x", alpha=0.3, linestyle="--")

    for bar, val in zip(bars, teardown_stats["teardown_pct"].values):
        ax.text(
            val + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%",
            va="center",
            fontweight="bold",
            fontsize=10,
        )

    fig.suptitle(
        "Fixture Design Patterns: Dependencies and Cleanup",
        fontsize=14,
        fontweight="bold",
        y=0.995,
    )

    plt.tight_layout()
    save_or_show(fig, "05h_design_patterns", out_dir, show)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FixtureDB Fixture Design Patterns")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_fixture_design_patterns(conn, args.out if not args.show else None, args.show)
    conn.close()
