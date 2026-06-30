"""
FixtureDB — Exploratory Data Analysis
======================================
Individual plot script.
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    LANG_ORDER,
    LANG_PALETTE,
    STATUS_PALETTE,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)

# -----------
# CORPUS COMPOSITION
# -----------


def plot_corpus_composition(conn, out_dir, show):
    repos = qdf(conn, "SELECT language, star_tier, status FROM repositories")
    if repos.empty:
        print("  [skip] No repositories in DB yet.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor="#FAFAFA")
    fig.suptitle("Corpus Composition", fontsize=14, fontweight="bold", y=1.02)

    # ── 1a: repos per language, tier as opacity ──────────────────────────────
    ax = axes[0]
    present = [l for l in LANG_ORDER if l in repos["language"].values]

    tier_alpha = {"core": 1.0, "extended": 0.40}
    tier_label = {"core": "≥500 stars (core)", "extended": "100–499 stars (extended)"}
    tier_order = ["core", "extended"]

    bottoms = [0] * len(present)
    for tier in tier_order:
        vals = [
            int(repos.query("language==@lang and star_tier==@tier").shape[0])
            for lang in present
        ]
        for i, (lang, v) in enumerate(zip(present, vals)):
            colour = LANG_PALETTE[lang]
            bar = ax.bar(
                i,
                v,
                bottom=bottoms[i],
                width=0.6,
                color=colour,
                alpha=tier_alpha[tier],
                zorder=3,
                label=tier_label[tier] if i == 0 else "_nolegend_",
            )
            if v > 0:
                ax.text(
                    i,
                    bottoms[i] + v / 2,
                    str(v),
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white",
                    fontweight="bold",
                )
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    # Colour patches for language legend
    import matplotlib.patches as mpatches

    lang_handles = [
        mpatches.Patch(color=LANG_PALETTE[l], label=lang_display(l)) for l in present
    ]
    tier_handles = [
        mpatches.Patch(color="#888888", alpha=tier_alpha[t], label=tier_label[t])
        for t in tier_order
    ]
    ax.legend(
        handles=lang_handles + tier_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=4,
        fontsize=8,
    )
    ax.set_xticks(range(len(present)))
    ax.set_xticklabels([lang_display(l) for l in present])
    ax.set_ylabel("Repositories")
    ax.set_title("Repos by Language & Star Tier")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    # ── 1b: pipeline status breakdown — linear scale, count labels ──────────
    ax2 = axes[1]
    status_order = ["analysed", "skipped", "error", "cloned", "discovered"]
    status_counts = repos["status"].value_counts().reindex(status_order, fill_value=0)
    colours = [STATUS_PALETTE[s] for s in status_order]
    raw = [int(status_counts[s]) for s in status_order]

    bars = ax2.barh(status_order, raw, color=colours, zorder=3, height=0.55)

    x_max = max(raw) if max(raw) > 0 else 1
    for bar, v in zip(bars, raw):
        label = f"{v:,}" if v > 0 else "—"
        # Put label inside bar if bar is wide enough, outside otherwise
        if v > x_max * 0.08:
            ax2.text(
                bar.get_width() * 0.97,
                bar.get_y() + bar.get_height() / 2,
                label,
                va="center",
                ha="right",
                fontsize=9,
                fontweight="bold",
                color="white",
            )
        else:
            ax2.text(
                x_max * 0.02,
                bar.get_y() + bar.get_height() / 2,
                label,
                va="center",
                ha="left",
                fontsize=9,
                fontweight="bold",
                color="#555",
            )

    ax2.set_xlim(0, x_max * 1.05)
    ax2.set_xlabel("Repositories")
    ax2.set_title("Pipeline Status Breakdown")
    ax2.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))

    plt.tight_layout()
    save_or_show(fig, "01_corpus_composition", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Corpus Composition")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    if args.show:
        out_dir = None
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_dir = Path(args.out) / ts
        out_dir.mkdir(parents=True, exist_ok=True)

    conn = load_db(Path(args.db))
    setup_style()

    print("\n[Corpus Composition]")
    plot_corpus_composition(conn, out_dir, args.show)

    conn.close()
    print("Done\n")
