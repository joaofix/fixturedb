"""
FixtureDB — Exploratory Data Analysis
======================================
Pipeline Status Breakdown
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    STATUS_PALETTE,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)


def plot_pipeline_status(conn, out_dir, show):
    repos = qdf(conn, "SELECT status, skip_reason FROM repositories")
    if repos.empty:
        print("  [skip] No repositories in DB yet.")
        return

    fig, ax = plt.subplots(figsize=(14, 7), facecolor="#FAFAFA")

    # For skipped repos, break down by skip reason
    status_counts = {}
    for status in ["analysed", "error", "discovered", "cloned"]:
        count = (repos["status"] == status).sum()
        if count > 0:
            status_counts[status] = count

    # For skipped repos, group by skip_reason
    skipped = repos[repos["status"] == "skipped"]
    if len(skipped) > 0:
        skip_reason_counts = (
            skipped["skip_reason"].fillna("unknown").value_counts().to_dict()
        )
        status_counts.update(
            {
                f"skipped: {reason}": count
                for reason, count in skip_reason_counts.items()
            }
        )

    # Organize pie chart: "analysed" first, then "error"/"discovered"/"cloned", then skip reasons
    pie_order = ["analysed"]
    if "error" in status_counts:
        pie_order.append("error")
    if "discovered" in status_counts:
        pie_order.append("discovered")
    if "cloned" in status_counts:
        pie_order.append("cloned")
    # Add skip reasons in order of frequency
    pie_order.extend([k for k in status_counts.keys() if k.startswith("skipped:")])

    pie_data = [status_counts[s] for s in pie_order if s in status_counts]
    pie_labels = []
    pie_colors = []

    for label in pie_order:
        if label in status_counts:
            if label.startswith("skipped:"):
                skip_reason = label.replace("skipped: ", "")
                pie_labels.append(f"Skipped\n({skip_reason})")
                pie_colors.append(STATUS_PALETTE.get("skipped", "#FFB74D"))
            else:
                pie_labels.append(label.capitalize())
                pie_colors.append(STATUS_PALETTE.get(label, "#CCCCCC"))

    total = sum(pie_data)
    wedges, texts, autotexts = ax.pie(
        pie_data,
        labels=pie_labels,
        colors=pie_colors,
        autopct="%1.1f%%",
        startangle=90,
        textprops={"fontsize": 9, "fontweight": "bold"},
    )

    # Make percentage text white and readable
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(9)
        autotext.set_fontweight("bold")

    # Create legend with counts
    legend_labels = [
        f"{pie_labels[i].replace(chr(10), ' ')}: {pie_data[i]:,}"
        for i in range(len(pie_labels))
    ]

    ax.legend(legend_labels, fontsize=10, loc="center left", bbox_to_anchor=(1, 0.5))

    # Add total text
    fig.text(0.72, 0.05, f"Total: {total:,} repos", fontsize=11, fontweight="bold")

    ax.set_title(
        "Pipeline Status Breakdown (with Skip Reasons)",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    plt.tight_layout()
    save_or_show(fig, "01b_pipeline_status", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Pipeline Status Breakdown")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_pipeline_status(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
