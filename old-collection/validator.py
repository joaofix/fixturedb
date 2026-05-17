"""
Manual validation scaffold.

Samples N fixtures per language from the database and exports them to a CSV
that you fill in manually (column: `is_true_fixture`, values: 1 or 0).

The CSV includes a 'github_url' column with clickable links to the actual code
on GitHub (at the specific commit and line range), making verification easier.

After filling in the CSV, run with --compute to calculate precision/recall.

Usage:
    # Step 1 — generate the sample (includes github_url column)
    python pipeline.py validate --sample 50

    # Step 2 — open validation/sample_<timestamp>.csv in a spreadsheet,
    #           click github_url to see code, read raw_source,
    #           and set is_true_fixture to 1 or 0

    # Step 3 — compute precision/recall
    python pipeline.py validate --compute validation/sample_<timestamp>.csv
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from collection.config import DB_PATH, ROOT_DIR
from collection.db import db_session

logger = logging.getLogger(__name__)

VALIDATION_DIR = ROOT_DIR / "validation"
VALIDATION_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def generate_sample(n_per_language: int = 50) -> Path:
    """
    Draw a stratified random sample of n_per_language fixtures per language.
    Exports to a CSV with an empty `is_true_fixture` column for manual review.
    Returns the CSV path.

    Raises:
        ValueError: If no analysed repositories are found in the database.
    """
    with db_session() as conn:
        languages = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT language FROM repositories WHERE status='analysed'"
            ).fetchall()
        ]

        if not languages:
            raise ValueError(
                "No analysed repositories found in database. Run extraction phase first: "
                "python pipeline.py search && python pipeline.py clone && python pipeline.py extract"
            )

        frames = []
        for lang in languages:
            rows = conn.execute(
                """
                SELECT
                    f.id            AS fixture_id,
                    r.language,
                    r.full_name     AS repo,
                    r.clone_url,
                    r.pinned_commit,
                    tf.relative_path AS file_path,
                    f.fixture_type,
                    f.name          AS fixture_name,
                    f.start_line,
                    f.end_line,
                    f.loc,
                    f.raw_source
                FROM fixtures f
                JOIN test_files tf   ON f.file_id  = tf.id
                JOIN repositories r  ON f.repo_id  = r.id
                WHERE r.language = ? AND r.status = 'analysed'
                ORDER BY RANDOM()
                LIMIT ?
            """,
                (lang, n_per_language),
            ).fetchall()

            if not rows:
                logger.warning(f"No fixtures found for language: {lang}")
                continue

            df = pd.DataFrame([dict(r) for r in rows])

            # Construct GitHub URLs for each fixture
            def build_github_url(row):
                """Build clickable GitHub URL pointing to fixture code."""
                clone_url = row["clone_url"]
                commit = row["pinned_commit"] or "HEAD"
                file_path = row["file_path"]
                start_line = row["start_line"]
                end_line = row["end_line"]

                # Convert clone_url from https://github.com/owner/repo.git to https://github.com/owner/repo
                github_base = clone_url.rstrip("/")
                if github_base.endswith(".git"):
                    github_base = github_base[:-4]

                # Build URL with line range: https://github.com/owner/repo/blob/commit/path#L10-L20
                url = (
                    f"{github_base}/blob/{commit}/{file_path}#L{start_line}-L{end_line}"
                )
                return url

            df["github_url"] = df.apply(build_github_url, axis=1)
            frames.append(df)
            logger.info(f"  {lang}: sampled {len(df)} fixtures")

    if not frames:
        raise ValueError(
            "No fixtures available to sample. Ensure corpus has been extracted: "
            "python pipeline.py search && python pipeline.py clone && python pipeline.py extract"
        )

    sample = pd.concat(frames, ignore_index=True)

    # Add the manual labeling column
    sample["is_true_fixture"] = ""  # reviewer fills: 1 = correct, 0 = false positive
    sample["reviewer_notes"] = ""  # optional free-text notes

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = VALIDATION_DIR / f"sample_{timestamp}.csv"
    sample.to_csv(out_path, index=False)

    logger.info(f"\nValidation sample written to: {out_path}")
    logger.info(
        "Instructions:\n"
        "  1. Open the CSV in a spreadsheet editor.\n"
        "  2. For each row, click the 'github_url' link to see the code in context.\n"
        "  3. Read the 'raw_source' and verify it's a real fixture.\n"
        "  4. Set 'is_true_fixture' to 1 (true fixture) or 0 (false positive).\n"
        "  5. Run: python pipeline.py validate --compute <path_to_csv>"
    )
    return out_path


# ---------------------------------------------------------------------------
# Precision / recall computation
# ---------------------------------------------------------------------------


def compute_metrics(csv_path: Path) -> dict:
    """
    Read a completed validation CSV and compute precision per language.

    Note: We compute precision (TP / (TP + FP)) from the sample.
    Recall requires knowing the false negatives, which requires a separate
    manual pass over raw test files to count missed fixtures.
    Report precision from this function; note recall limitation in the paper.
    """
    df = pd.read_csv(csv_path)

    required_cols = {"language", "is_true_fixture"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    # Drop rows not yet labelled
    labelled = df[df["is_true_fixture"].isin([0, 1, "0", "1"])]
    labelled = labelled.copy()
    labelled["is_true_fixture"] = labelled["is_true_fixture"].astype(int)

    total_labelled = len(labelled)
    if total_labelled == 0:
        logger.error(
            "No labelled rows found. Fill in is_true_fixture before computing."
        )
        return {}

    results = {}
    print(f"\nValidation results from: {csv_path.name}")
    print(f"Total labelled: {total_labelled}\n")
    print(
        f"{'Language':<14} {'Sampled':>8} {'True':>8} {'False+':>8} {'Precision':>10}"
    )
    print("-" * 52)

    for lang, group in labelled.groupby("language"):
        tp = (group["is_true_fixture"] == 1).sum()
        fp = (group["is_true_fixture"] == 0).sum()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        results[lang] = {
            "sampled": len(group),
            "true_positives": int(tp),
            "false_positives": int(fp),
            "precision": round(precision, 3),
        }
        print(f"{lang:<14} {len(group):>8} {tp:>8} {fp:>8} {precision:>9.1%}")

    overall_tp = sum(r["true_positives"] for r in results.values())
    overall_fp = sum(r["false_positives"] for r in results.values())
    overall_p = (
        overall_tp / (overall_tp + overall_fp) if (overall_tp + overall_fp) > 0 else 0.0
    )
    print("-" * 52)
    print(
        f"{'Overall':<14} {total_labelled:>8} {overall_tp:>8} {overall_fp:>8} "
        f"{overall_p:>9.1%}"
    )

    print(
        "\nNote: This script measures precision only. "
        "Recall requires a separate manual pass to count missed fixtures.\n"
        "For the paper, report precision here and note the recall limitation."
    )
    return results
