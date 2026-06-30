"""
Plot 8: Fixture categorization by usage pattern

Shows the distribution of fixtures across the 8-category taxonomy:
  - data_builder: constructs/initializes test data
  - hybrid: combines multiple patterns
  - mock_setup: creates mocks/stubs/spies
  - resource_management: handles resource allocation/cleanup
  - service_setup: wires dependencies and services
  - state_reset: resets global/shared state
  - configuration_setup: configures settings/env vars
  - environment: manages environment, files, databases
"""

import matplotlib.pyplot as plt

from ..eda_common import qdf, save_or_show

# Color palette for categories (semantic: primary patterns first)
CATEGORY_COLORS = {
    "data_builder": "#2E86AB",  # Blue - most common, primary pattern
    "hybrid": "#A23B72",  # Purple - multi-purpose
    "mock_setup": "#F18F01",  # Orange - test isolation
    "resource_management": "#C73E1D",  # Rust - resource handling
    "service_setup": "#6A994E",  # Green - dependency management
    "state_reset": "#BC4749",  # Red - state management
    "configuration_setup": "#D4A574",  # Tan - configuration
    "environment": "#5A189A",  # Dark purple - environment
}

# Order by frequency (for better visual hierarchy)
CATEGORY_ORDER = [
    "data_builder",
    "hybrid",
    "mock_setup",
    "resource_management",
    "service_setup",
    "state_reset",
    "configuration_setup",
    "environment",
]


def plot_fixture_categories(conn, out_dir, show):
    """Plot 8: Fixture categorization by usage pattern (horizontal bar chart)"""
    fixtures = qdf(
        conn,
        """
        SELECT category
        FROM fixtures
        WHERE category IS NOT NULL
    """,
    )
    if fixtures.empty or fixtures["category"].isna().all():
        print(
            "  [skip] No fixture categories yet. Run `python pipeline.py categorize`."
        )
        return

    # Count by category
    cat_counts = (
        fixtures[fixtures["category"].notna()]
        .groupby("category")
        .size()
        .reset_index(name="count")
    )
    cat_counts["pct"] = cat_counts["count"] / cat_counts["count"].sum() * 100

    # Sort by count descending
    cat_counts = cat_counts.sort_values("count", ascending=True)

    fig, ax = plt.subplots(1, 1, figsize=(10, 6), facecolor="#FAFAFA")
    fig.suptitle("Fixture Categorization", fontsize=14, fontweight="bold", y=0.98)

    # Create horizontal bar chart
    colors = [CATEGORY_COLORS.get(cat, "#CCCCCC") for cat in cat_counts["category"]]
    bars = ax.barh(
        cat_counts["category"],
        cat_counts["count"],
        color=colors,
        alpha=0.85,
        edgecolor="white",
        linewidth=1,
    )

    # Add count and percentage labels
    for i, (bar, count, pct) in enumerate(
        zip(bars, cat_counts["count"], cat_counts["pct"])
    ):
        ax.text(
            count,
            bar.get_y() + bar.get_height() / 2,
            f"  {count:,} ({pct:.1f}%)",
            va="center",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_xlabel("Number of Fixtures")
    ax.set_ylabel("")
    ax.set_title(
        "Test Fixtures by Category\n(RQ1 Taxonomy — Usage Patterns)",
        fontsize=11,
        pad=10,
    )

    # Format y-axis labels to be more readable
    labels = [label.replace("_", " ").title() for label in cat_counts["category"]]
    ax.set_yticklabels(labels)

    # Grid for readability
    ax.grid(axis="x", alpha=0.3, linestyle=":", linewidth=0.5)
    ax.set_axisbelow(True)

    # Format x-axis to show thousands separator
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x):,}"))

    plt.tight_layout()
    save_or_show(fig, "08_fixture_categories", out_dir, show)
