"""
FixtureDB — Exploratory Data Analysis
======================================
Individual plot script.
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

# -----------
# MOCKING PRACTICES
# -----------


def plot_mock_prevalence(conn, out_dir, show):
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
    mocks = qdf(
        conn,
        """
        SELECT m.framework, r.language
        FROM mock_usages m
        JOIN repositories r ON m.repo_id = r.id
        WHERE r.status = 'analysed'
    """,
    )
    if fixtures.empty:
        print("  [skip] Fixture table is empty.")
        return

    present = [l for l in LANG_ORDER if l in fixtures["language"].values]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor="#FAFAFA")
    fig.suptitle(
        "Mocking Practices Inside Fixtures (CSV-Exported Metrics)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )

    # ── 7a: mock prevalence — lollipop chart ─────────────────────────────────
    ax = axes[0]
    fixtures["has_mock"] = fixtures["mock_count"] > 0
    prevalence = (
        fixtures[fixtures["language"].isin(present)]
        .groupby("language")["has_mock"]
        .mean()
        .reindex(present)
        * 100
    )
    y_pos = range(len(present))

    # Thick horizontal bars (barh behaves exactly like what was requested)
    ax.barh(
        list(y_pos),
        prevalence.values,
        color=[LANG_PALETTE[l] for l in present],
        height=0.55,
        zorder=3,
    )
    ax.scatter([], [])  # dummy so legend works if needed
    for y, pct, lang in zip(y_pos, prevalence.values, present):
        ax.text(
            pct + 1.2,
            y,
            f"{pct:.1f}%",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=LANG_PALETTE[lang],
        )

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([lang_display(l) for l in present])
    ax.set_xlabel("Fixtures containing at least one mock call (%)")
    ax.set_xlim(0, min(100, prevalence.max() + 15))
    ax.set_title(
        "What Share of Fixtures Use Mocking?\n"
        "(% of fixture definitions with at least one mock call)"
    )
    ax.axvline(0, color="#ccc", linewidth=0.5)

    # ── 7b: framework usage — stacked horizontal bar, single-hue per language ─
    ax2 = axes[1]
    if not mocks.empty:
        fw_counts = (
            mocks[mocks["language"].isin(present)]
            .groupby(["language", "framework"])
            .size()
            .reset_index(name="n")
        )
        pivot = (
            fw_counts.pivot(index="language", columns="framework", values="n")
            .reindex(present)
            .fillna(0)
        )
        pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
        fws = list(pivot_pct.columns)

        # Single-hue per language: shades from light to dark
        import matplotlib.colors as mcolors

        y_pos2 = range(len(present))
        for i, lang in enumerate(present):
            base = LANG_PALETTE[lang]
            base_rgb = mcolors.to_rgb(base)
            shades = [
                tuple(c * (0.4 + 0.6 * j / max(len(fws) - 1, 1)) for c in base_rgb)
                for j in range(len(fws))
            ]
            left = 0.0
            for j, (fw, shade) in enumerate(zip(fws, shades)):
                w = pivot_pct.loc[lang, fw]
                if w > 0:
                    ax2.barh(i, w, left=left, color=shade, height=0.55, zorder=3)
                    if w > 6:
                        ax2.text(
                            left + w / 2,
                            i,
                            fw.replace("_", "\n"),
                            ha="center",
                            va="center",
                            fontsize=6,
                            color="white",
                            fontweight="bold",
                        )
                left += w

        ax2.set_yticks(list(y_pos2))
        ax2.set_yticklabels([lang_display(l) for l in present])
        ax2.set_xlabel("Share of mock calls using each framework (%)")
        ax2.set_xlim(0, 105)
        ax2.set_title("Which Mocking Frameworks Do Developers Use?")
    else:
        ax2.text(
            0.5,
            0.5,
            "No framework data available",
            ha="center",
            va="center",
            transform=ax2.transAxes,
            fontsize=10,
            color="#999",
        )
        ax2.set_xticks([])
        ax2.set_yticks([])

    plt.tight_layout()
    save_or_show(fig, "07_mock_prevalence", out_dir, show)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixtureDB Mocking Practices")
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

    print("\n[Mocking Practices]")
    plot_mock_prevalence(conn, out_dir, args.show)

    conn.close()
    print("Done\n")
