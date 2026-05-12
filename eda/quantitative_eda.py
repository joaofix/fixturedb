"""
FixtureDB — Quantitative EDA
============================
Analysis-ready statistical plots for publication in ICSME Data Showcase track.

Only includes purely quantitative and statistical results that do not depend
on subjective interpretation of the data.

Usage:
    python quantitative_eda.py                    # all plots → output/eda/<timestamp>/
    python quantitative_eda.py --out figures/     # custom base output directory
    python quantitative_eda.py --show             # display interactively instead of saving
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path for relative imports to work
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from eda.eda_common import load_db, setup_style

# Import plot functions from quantitative submodule
from eda.quantitative.p01a_corpus_by_tier import plot_corpus_by_tier
from eda.quantitative.p01b_pipeline_status import plot_pipeline_status
from eda.quantitative.p02a_creation_timeline import plot_creation_timeline
from eda.quantitative.p02b_activity_recency import plot_activity_recency
from eda.quantitative.p03a_fixtures_per_repo import plot_fixtures_per_repo
from eda.quantitative.p03b_fixture_scope import plot_fixture_scope
from eda.quantitative.p03c_fixture_types import plot_fixture_types
from eda.quantitative.p03e_fixture_scopes import plot_fixture_scopes
from eda.quantitative.p04a_mock_adoption import plot_mock_adoption
from eda.quantitative.p04b_framework_diversity import plot_framework_diversity
from eda.quantitative.p04c_lines_of_code import plot_lines_of_code
from eda.quantitative.p04d_complexity_metrics import plot_complexity_metrics
from eda.quantitative.p04e_framework_by_scope import plot_framework_by_scope

# NOTE: plot_mock_styles removed (mock_style column no longer exists in DB as of 2026-04-25)
from eda.quantitative.p05a_nesting_depth import plot_nesting_depth
from eda.quantitative.p05b_nesting_complexity_correlation import (
    plot_nesting_complexity_correlation,
)
from eda.quantitative.p05c_fixture_reuse_distribution import (
    plot_fixture_reuse_distribution,
)
from eda.quantitative.p05d_reuse_complexity_correlation import (
    plot_reuse_complexity_correlation,
)
from eda.quantitative.p05e_teardown_adoption import plot_teardown_adoption
from eda.quantitative.p05f_contributors_impact import plot_contributors_impact
from eda.quantitative.p05g_test_file_characteristics import (
    plot_test_file_characteristics,
)
from eda.quantitative.p05h_design_patterns import plot_fixture_design_patterns
from eda.quantitative.p05i_repo_maturity import plot_repo_maturity_vs_fixture_quality

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "corpus.db"
DEFAULT_OUT = ROOT / "output" / "eda" / "quantitative"


def main():
    parser = argparse.ArgumentParser(
        description="FixtureDB Quantitative EDA — ICSME Data Showcase Track"
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
        f"\nFixtureDB Quantitative EDA — {int(total):,} repos  ({int(analysed):,} analysed)"
    )
    print(f"Track: ICSME Data Showcase (no subjective interpretation)")
    print(f"Output → {out_dir or 'screen'}\n")

    # Quantitative plots only (no subjectivity bias)
    plots = [
        ("Corpus by Tier", plot_corpus_by_tier),
        ("Pipeline Status", plot_pipeline_status),
        ("Creation Timeline", plot_creation_timeline),
        ("Activity Recency", plot_activity_recency),
        ("Fixtures per Repo", plot_fixtures_per_repo),
        ("Fixture Scope", plot_fixture_scope),
        ("Fixture Types (Detection Patterns)", plot_fixture_types),
        ("Fixture Scopes (Stacked)", plot_fixture_scopes),
        ("Mock Adoption", plot_mock_adoption),
        ("Framework Diversity", plot_framework_diversity),
        ("Lines of Code Distribution", plot_lines_of_code),
        ("Complexity Metrics", plot_complexity_metrics),
        ("Framework by Execution Scope", plot_framework_by_scope),
        ("Nesting Depth Distribution", plot_nesting_depth),
        ("Nesting Depth vs Complexity", plot_nesting_complexity_correlation),
        ("Fixture Reuse Distribution", plot_fixture_reuse_distribution),
        ("Reuse vs Complexity", plot_reuse_complexity_correlation),
        ("Teardown Adoption", plot_teardown_adoption),
        ("Contributors Impact", plot_contributors_impact),
        ("Test File Characteristics", plot_test_file_characteristics),
        ("Fixture Design Patterns", plot_fixture_design_patterns),
        ("Repository Maturity vs Quality", plot_repo_maturity_vs_fixture_quality),
    ]

    for name, fn in plots:
        print(f"[{name}]")
        fn(conn, out_dir, args.show)

    conn.close()
    print("\n✓ Done")


if __name__ == "__main__":
    main()
