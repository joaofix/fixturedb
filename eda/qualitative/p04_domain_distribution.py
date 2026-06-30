"""
FixtureDB — Exploratory Data Analysis
======================================
Individual plot script.
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from ..eda_common import (
    DB_PATH,
    DEFAULT_OUT,
    LANG_ORDER,
    lang_display,
    load_db,
    qdf,
    save_or_show,
    setup_style,
)

# -----------
# DOMAIN DISTRIBUTION
# -----------


def plot_domain_distribution(conn, out_dir, show):
    repos = qdf(
        conn,
        """
        SELECT language, domain FROM repositories
        WHERE domain IS NOT NULL AND status NOT IN ('discovered')
    """,
    )
    if repos.empty or repos["domain"].nunique() < 2:
        print(
            "  [skip] Domain data not classified yet. Run `python pipeline.py classify`."
        )
        return

    domain_order = ["web", "library", "data", "cli", "infra", "other"]
    present_langs = [l for l in LANG_ORDER if l in repos["language"].values]
    present_domains = [d for d in domain_order if d in repos["domain"].values]

    pivot = (
        repos.groupby(["language", "domain"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=present_langs, columns=present_domains, fill_value=0)
    )
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(1, 1, figsize=(10, 5), facecolor="#FAFAFA")
    fig.suptitle("Project Domain Distribution", fontsize=14, fontweight="bold", y=1.02)

    # ── heatmap annotated with "% (abs)" ─────────────────────────────────────
    annot = np.empty(pivot_pct.shape, dtype=object)
    for i, lang in enumerate(present_langs):
        for j, dom in enumerate(present_domains):
            pct = pivot_pct.loc[lang, dom]
            raw = int(pivot.loc[lang, dom])
            annot[i, j] = f"{pct:.0f}%\n({raw})"

    sns.heatmap(
        pivot_pct,
        annot=annot,
        fmt="",
        cmap="Blues",
        linewidths=0.4,
        linecolor="#E0E0E0",
        cbar_kws={"label": "% of language repos"},
        annot_kws={"size": 9},
        ax=ax,
    )
    ax.set_title("Domain Share per Language")
    ax.set_yticklabels([lang_display(l) for l in present_langs], rotation=0)
    ax.set_xticklabels(
        [d.capitalize() for d in present_domains], rotation=30, ha="right"
    )
    ax.set_xlabel("")
    ax.set_ylabel("")

    plt.tight_layout()
    save_or_show(fig, "04_domain_distribution", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Domain Distribution")
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

    print("\n[Domain Distribution]")
    plot_domain_distribution(conn, out_dir, args.show)

    conn.close()
    print("Done\n")
