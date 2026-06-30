"""
FixtureDB — Qualitative EDA
===========================
Subjective and interpretive analyses for internal exploration only.

These analyses depend on semantic classification and subjective interpretation,
and are NOT suitable for publication without extensive explanation and justification.

Examples:
  - Domain distribution (requires domain categorization)
  - Fixture categorization (requires RQ1 taxonomy interpretation)

Usage:
    python qualitative_eda.py                    # all plots → output/eda/qualitative/<timestamp>/
    python qualitative_eda.py --out figures/     # custom base output directory
    python qualitative_eda.py --show             # display interactively instead of saving
"""

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from .eda_common import load_db, setup_style

# Import plot functions from qualitative submodule
from .qualitative.p04_domain_distribution import plot_domain_distribution
from .qualitative.p08_fixture_categories import plot_fixture_categories

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "corpus.db"
DEFAULT_OUT = ROOT / "output" / "eda" / "qualitative"


def main():
    parser = argparse.ArgumentParser(
        description="FixtureDB Qualitative EDA — Internal Analysis Only"
    )
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
        latest = Path(args.out) / "latest"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        try:
            latest.symlink_to(ts)
        except (OSError, NotImplementedError):
            pass

    conn = load_db(Path(args.db))
    setup_style()

    total = pd.read_sql_query("SELECT COUNT(*) n FROM repositories", conn).iloc[0]["n"]
    analysed = pd.read_sql_query(
        "SELECT COUNT(*) n FROM repositories WHERE status='analysed'", conn
    ).iloc[0]["n"]

    print(
        f"\nFixtureDB Qualitative EDA — {int(total):,} repos  ({int(analysed):,} analysed)"
    )
    print("⚠ WARNING: Internal analysis only (subjective interpretation)")
    print(f"Output → {out_dir or 'screen'}\n")

    # Qualitative plots (may contain subjective bias)
    plots = [
        ("Domain Distribution", plot_domain_distribution),
        ("Fixture Categories", plot_fixture_categories),
    ]

    for name, fn in plots:
        print(f"[{name}]")
        fn(conn, out_dir, args.show)

    conn.close()
    print("\n✓ Done")


if __name__ == "__main__":
    main()
