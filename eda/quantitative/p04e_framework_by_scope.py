"""
FixtureDB — Exploratory Data Analysis
======================================
Testing Framework Usage by Language and Scope
"""

import matplotlib.pyplot as plt
import numpy as np

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    LANG_ORDER,
    has_data,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)


def plot_framework_by_scope(conn, out_dir, show):
    """Distribution of testing frameworks by scope and language."""
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT r.language, f.framework, f.scope, COUNT(*) as count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed' AND f.framework IS NOT NULL AND f.scope IS NOT NULL
        GROUP BY r.language, f.framework, f.scope
    """,
    )

    if fixtures.empty:
        print("  [skip] No framework data.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].unique()]
    scope_order = ["per_test", "per_class", "per_module", "global"]

    fig, axes = plt.subplots(1, len(present), figsize=(15, 5), facecolor="#FAFAFA")
    if len(present) == 1:
        axes = [axes]

    for ax, lang in zip(axes, present):
        # Get top 4 frameworks for this language
        lang_fixtures = fixtures[fixtures["language"] == lang]
        top_frameworks = (
            lang_fixtures.groupby("framework")["count"].sum().nlargest(4).index.tolist()
        )

        # Create stacked bar chart
        framework_scope = (
            lang_fixtures[lang_fixtures["framework"].isin(top_frameworks)]
            .groupby(["framework", "scope"])["count"]
            .sum()
            .unstack(fill_value=0)
        )

        # Reorder scopes
        existing_scopes = [s for s in scope_order if s in framework_scope.columns]
        framework_scope = framework_scope[existing_scopes]

        scope_colors = {
            "per_test": "#2E86AB",
            "per_class": "#A23B72",
            "per_module": "#F18F01",
            "global": "#C73E1D",
        }

        # Normalize to percentages
        framework_pct = framework_scope.div(framework_scope.sum(axis=1), axis=0) * 100

        x_pos = np.arange(len(framework_pct))
        width = 0.6
        bottom = np.zeros(len(framework_pct))

        for scope in existing_scopes:
            values = framework_pct[scope].values
            ax.bar(
                x_pos,
                values,
                width,
                label=scope.replace("_", " ").title(),
                bottom=bottom,
                color=scope_colors.get(scope, "#999"),
                alpha=0.85,
            )
            bottom += values

        # Format x-axis
        framework_labels = [f.replace("_", "\n") for f in framework_pct.index]
        ax.set_xticks(x_pos)
        ax.set_xticklabels(framework_labels, fontsize=10)
        ax.set_ylabel("Percentage (%)" if ax == axes[0] else "", fontsize=11)
        ax.set_title(f"{lang_display(lang)}", fontsize=12, fontweight="bold")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        ax.legend(fontsize=9, loc="upper right") if ax == axes[-1] else None

    fig.suptitle(
        "Testing Frameworks and Execution Scopes",
        fontsize=14,
        fontweight="bold",
        y=1.00,
    )

    plt.tight_layout()
    save_or_show(fig, "04e_framework_by_scope", out_dir, show)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="FixtureDB Framework by Scope Distribution"
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_framework_by_scope(conn, args.out if not args.show else None, args.show)
    conn.close()
