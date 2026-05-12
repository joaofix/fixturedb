"""
FixtureDB — Exploratory Data Analysis
======================================
Fixture Scope Distribution
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


def plot_fixture_scopes(conn, out_dir, show):
    """Distribution of fixture execution scopes (per_test, per_class, etc.)."""
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    # Get fixtures by scope and language
    scopes_data = qdf(
        conn,
        """
        SELECT r.language, f.scope, COUNT(*) as count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed' AND f.scope IS NOT NULL
        GROUP BY r.language, f.scope
    """,
    )

    if scopes_data.empty:
        print("  [skip] No scope data.")
        return

    present = [l for l in LANG_ORDER if l in scopes_data["language"].unique()]
    scope_order = ["per_test", "per_class", "per_module", "global"]

    # Create stacked bar chart by language
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="#FAFAFA")

    scopes_pivot = (
        scopes_data[scopes_data["language"].isin(present)]
        .pivot_table(
            index="language",
            columns="scope",
            values="count",
            fill_value=0,
            aggfunc="sum",
        )
        .reindex(present)
    )

    # Reorder columns to scope_order
    existing_scopes = [s for s in scope_order if s in scopes_pivot.columns]
    scopes_pivot = scopes_pivot[existing_scopes]

    scope_colors = {
        "per_test": "#2E86AB",
        "per_class": "#A23B72",
        "per_module": "#F18F01",
        "global": "#C73E1D",
    }

    # Normalize to percentages
    scopes_pct = scopes_pivot.div(scopes_pivot.sum(axis=1), axis=0) * 100

    x_pos = np.arange(len(present))
    width = 0.6
    bottom = np.zeros(len(present))

    for scope in existing_scopes:
        values = scopes_pct[scope].values
        ax.bar(
            x_pos,
            values,
            width,
            label=scope.replace("_", " ").title(),
            bottom=bottom,
            color=scope_colors.get(scope, "#999"),
            alpha=0.85,
        )

        # Add percentage labels
        for i, (v, b) in enumerate(zip(values, bottom)):
            if v > 3:  # Only show labels if segment is large enough
                ax.text(
                    i,
                    b + v / 2,
                    f"{v:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color="white",
                )

        bottom += values

    ax.set_xticks(x_pos)
    ax.set_xticklabels([lang_display(l) for l in present])
    ax.set_ylabel("Percentage (%)", fontsize=11)
    ax.set_title(
        "Fixture Execution Scope: When Are Fixtures Created?",
        fontsize=14,
        fontweight="bold",
    )
    ax.legend(loc="upper right", fontsize=10, framealpha=0.95)
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    plt.tight_layout()
    save_or_show(fig, "03d_fixture_scopes", out_dir, show)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FixtureDB Fixture Scope Distribution")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_fixture_scopes(conn, args.out if not args.show else None, args.show)
    conn.close()
