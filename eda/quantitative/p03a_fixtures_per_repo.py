"""
FixtureDB — Exploratory Data Analysis
======================================
Fixtures per Repository
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
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


def plot_fixtures_per_repo(conn, out_dir, show):
    if not has_data(conn, "fixtures"):
        print("  [skip] No fixture data yet. Run `python pipeline.py extract`.")
        return

    fixtures = qdf(
        conn,
        """
        SELECT r.language, r.full_name
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#FAFAFA")

    per_repo = (
        fixtures.groupby(["language", "full_name"])
        .size()
        .reset_index(name="fixture_count")
    )
    per_repo = per_repo[per_repo["language"].isin(present)]
    per_repo["fixture_count"] = per_repo["fixture_count"].clip(lower=1)
    per_repo["log_count"] = np.log10(per_repo["fixture_count"])

    from scipy import stats

    x_range = np.logspace(
        np.log10(per_repo["fixture_count"].min()),
        np.log10(per_repo["fixture_count"].max()),
        200,
    )
    x_log = np.log10(x_range)

    y_offset = 0
    for i, lang in enumerate(present):
        sub = per_repo[per_repo["language"] == lang]["log_count"].values
        if len(sub) > 1:
            kde = stats.gaussian_kde(sub, bw_method=0.15)
            density = kde(x_log)
            density = density / density.max() * 0.8

            ax.fill_between(
                x_range,
                y_offset,
                y_offset + density,
                color=LANG_PALETTE[lang],
                alpha=0.7,
                label=lang_display(lang),
                zorder=len(present) - i,
            )
            ax.plot(
                x_range,
                y_offset + density,
                color=LANG_PALETTE[lang],
                linewidth=1.2,
                zorder=len(present) - i + 1,
            )
            y_offset += 1

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: str(int(v)) if v >= 1 else "")
    )
    ax.set_xlabel("Fixtures per Repository (log scale)")
    ax.set_ylabel("Language (density, offset)")
    ax.set_title(
        "How Many Fixtures Does Each Repository Have?", fontsize=14, fontweight="bold"
    )
    ax.set_yticks([])
    ax.legend(fontsize=9, loc="upper right")

    plt.tight_layout()
    save_or_show(fig, "03a_fixtures_per_repo", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Fixtures per Repository")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Base output directory")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    setup_style()
    conn = load_db(args.db)
    plot_fixtures_per_repo(
        conn, Path(args.out) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), args.show
    )
