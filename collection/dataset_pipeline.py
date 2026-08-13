"""Cross-cutting dataset stages: analyze-distribution, sample, export, validate.

Replaces the old phase_4/5/6_7/8 scripts, which relayed state between each
other through timestamped JSON files under output/ (glob for the latest
`phase_N_*.json`) and hardcoded exactly two datasets (human, agent). Each
function here operates on one dataset at a time, identified by 'a'/'b'/'c',
resolving DB/export paths through collection.paths.

`sample_dataset()` still persists its result to a JSON file (there is a real
CLI-invocation boundary between `sample` and `export`), but at a fixed path
(`output/sample_{dataset}.json`) rather than a timestamped one -- `export`
reads that one file directly instead of globbing for "latest".
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from . import paths
from .config import DATASET_C_SAMPLING_SEED
from .corpus_utils import write_fixture_csv_row
from .dataset_exporter import AgentDatasetExporter, HumanDatasetExporter
from .dataset_sampler import StratifiedSampler, sample_repos_by_language
from .dataset_validator import DatasetValidator
from .db import (
    db_session,
    initialise_db,
    insert_fixture,
    insert_mock_usage,
    set_repo_analysed,
    update_test_file_counts,
    upsert_repository,
    upsert_test_file,
)
from .logging_utils import get_logger

logger = get_logger(__name__)

_EXPORTER_CLASSES = {
    "a": AgentDatasetExporter,
    "b": HumanDatasetExporter,
    "c": HumanDatasetExporter,
}


def _sample_output_path(dataset: str, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or (paths.ROOT_DIR / "output")
    return output_dir / f"sample_{dataset}.json"


def analyze_database_distribution(db_path: Path) -> dict:
    """Fixture/repo/test-file counts and fixture_type/scope breakdowns for one DB."""
    stats = {
        "total_fixtures": 0,
        "by_type": {},
        "by_scope": {},
        "repositories": 0,
        "test_files": 0,
    }

    with db_session(db_path) as conn:
        result = conn.execute("SELECT COUNT(*) as count FROM fixtures").fetchone()
        stats["total_fixtures"] = result["count"]

        rows = conn.execute(
            "SELECT fixture_type, COUNT(*) as count FROM fixtures "
            "GROUP BY fixture_type ORDER BY count DESC"
        ).fetchall()
        stats["by_type"] = {row["fixture_type"]: row["count"] for row in rows}

        rows = conn.execute(
            "SELECT scope, COUNT(*) as count FROM fixtures "
            "GROUP BY scope ORDER BY count DESC"
        ).fetchall()
        stats["by_scope"] = {row["scope"]: row["count"] for row in rows}

        result = conn.execute("SELECT COUNT(*) as count FROM repositories").fetchone()
        stats["repositories"] = result["count"]

        result = conn.execute("SELECT COUNT(*) as count FROM test_files").fetchone()
        stats["test_files"] = result["count"]

    return stats


def analyze_distribution(
    dataset: str, against: str, db_root: Path = paths.DB_ROOT
) -> dict:
    """Compare `dataset`'s and `against`'s fixture distributions and
    recommend a balanced sample target (the smaller dataset's total)."""
    db_paths = {
        dataset: paths.db_path(dataset, root=db_root),
        against: paths.db_path(against, root=db_root),
    }
    for name, db_path in db_paths.items():
        if not db_path.exists():
            raise FileNotFoundError(
                f"{db_path} not found; run `extract-fixtures --dataset {name}` first"
            )

    stats = {name: analyze_database_distribution(p) for name, p in db_paths.items()}
    target_count = min(stats[dataset]["total_fixtures"], stats[against]["total_fixtures"])

    return {
        "dataset": dataset,
        "against": against,
        dataset: {"path": str(db_paths[dataset]), "statistics": stats[dataset]},
        against: {"path": str(db_paths[against]), "statistics": stats[against]},
        "sampling_recommendation": {
            "target_count": target_count,
            "stratify_by": "fixture_type",
            "tolerance": 0.02,
            "random_seed": 42,
        },
    }


def sample_dataset(
    dataset: str,
    target_count: int | None = None,
    stratify_by: str = "fixture_type",
    tolerance: float = 0.02,
    seed: int = 42,
    db_root: Path = paths.DB_ROOT,
    output_dir: Path | None = None,
) -> dict:
    """Stratified-sample fixtures from `dataset`'s DB and persist the result.

    `target_count=None` means "sample everything" (no reduction) -- pass an
    explicit value (e.g. from `analyze_distribution()`'s recommendation) to
    balance against another dataset.
    """
    db_path = paths.db_path(dataset, root=db_root)
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} not found; run `extract-fixtures --dataset {dataset}` first"
        )

    with db_session(db_path) as conn:
        rows = conn.execute(
            "SELECT id, fixture_type, scope, loc, name FROM fixtures ORDER BY id"
        ).fetchall()
    fixtures = [dict(row) for row in rows]
    if not fixtures:
        raise ValueError(f"No fixtures found in {db_path}")

    if target_count is None:
        target_count = len(fixtures)

    sampler = StratifiedSampler(random_seed=seed)
    result = sampler.sample(
        fixtures, target_count=target_count, stratify_by=stratify_by, tolerance=tolerance
    )
    stats = sampler.get_sample_statistics(result)

    output = {
        "dataset": dataset,
        "sampled_count": result.sampled_count,
        "target_count": result.target_count,
        "stratify_by": result.stratify_by,
        "random_seed": seed,
        "all_strata_within_tolerance": stats["all_strata_within_tolerance"],
        "distribution_check": result.distribution_check,
        "sampled_fixture_ids": result.sampled_ids,
    }

    out_path = _sample_output_path(dataset, output_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(output, f, indent=2)

    logger.info(
        f"[sample {dataset}] {result.sampled_count}/{len(fixtures)} fixtures "
        f"sampled -> {out_path}"
    )
    return output


def export_dataset(
    dataset: str,
    version: str = "1.0",
    db_root: Path = paths.DB_ROOT,
    export_root: Path = paths.EXPORT_ROOT,
    sample_output_dir: Path | None = None,
) -> Path:
    """Export `dataset`'s sampled fixtures to export/{dataset}.zip.

    Requires `sample --dataset {dataset}` to have run first.
    """
    sample_path = _sample_output_path(dataset, sample_output_dir)
    if not sample_path.exists():
        raise FileNotFoundError(
            f"No sample results at {sample_path}; run `sample --dataset {dataset}` first"
        )
    with sample_path.open() as f:
        sample_data = json.load(f)
    sampled_ids = sample_data["sampled_fixture_ids"]

    db_path = paths.db_path(dataset, root=db_root)
    work_dir = export_root / f"_{dataset}_work"
    exporter_cls = _EXPORTER_CLASSES[dataset]
    exporter = exporter_cls(db_path, work_dir)
    result = exporter.export(sampled_ids, version=version)

    final_zip = paths.export_path(dataset, root=export_root)
    final_zip.parent.mkdir(parents=True, exist_ok=True)
    result.zip_path.replace(final_zip)

    logger.info(
        f"[export {dataset}] {result.fixture_count} fixtures, "
        f"{result.total_size_mb:.1f} MB -> {final_zip}"
    )
    return final_zip


def validate_dataset(dataset: str, export_root: Path = paths.EXPORT_ROOT) -> dict:
    """Validate export/{dataset}.zip for completeness and independence."""
    zip_path = paths.export_path(dataset, root=export_root)
    validator = DatasetValidator(zip_path.parent)
    return validator.validate_single(zip_path, is_agent=(dataset == "a"))


# ---------------------------------------------------------------------------
# Dataset C sample-down (repo-level, language-stratified, size-matched to A)
#
# db/c.db and datasets/c/fixtures/*.csv (the full, ~3.3x-Dataset-A-sized
# originals) are never modified here -- read-only source. This builds a
# separate, standalone db/c_sampled.db + datasets/c/fixtures-sampled/*.csv
# alongside them. research_questions/_shared.py::require_db_or_none() and
# language_contamination.py::check_dataset() are the enforcement points that
# make every research_questions/ script read c_sampled.db/fixtures-sampled/
# instead of the full originals -- see those modules, not this one, for why
# that's mandatory rather than opt-in.
# ---------------------------------------------------------------------------


def _sample_repos_output_path(output_dir: Path | None = None) -> Path:
    output_dir = output_dir or (paths.ROOT_DIR / "output")
    return output_dir / "sample_c_repos.json"


def _fetch_dataset_c_repo_fixture_counts(conn: sqlite3.Connection) -> list[dict]:
    """One row per repo with >=1 fixture: {repo_id, language, fixture_count}
    -- the population sample_repos_by_language() samples from. Language is
    the repo's own tagged language (repositories.language), not each
    fixture's individually-detected one -- a repo is sampled as a whole
    unit, so it needs exactly one language bucket to belong to."""
    rows = conn.execute(
        """
        SELECT r.id AS repo_id, r.language AS language, COUNT(f.id) AS fixture_count
        FROM repositories r
        JOIN fixtures f ON f.repo_id = r.id
        GROUP BY r.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_repo_language_counts_with_fixtures(conn: sqlite3.Connection) -> dict[str, int]:
    """Repo count per language among repos with >=1 fixture, for whichever
    dataset `conn` points at -- same population as
    _fetch_dataset_c_repo_fixture_counts() above, just counting repos
    instead of fixtures. Used as sample_dataset_c_repos()'s
    target_proportions when matching another dataset (e.g. Dataset A):
    Dataset C's sample should mirror that dataset's real, final,
    fixture-contributing repo mix, not an earlier candidate pool that
    includes repos contributing zero data."""
    rows = conn.execute(
        """
        SELECT r.language AS language, COUNT(DISTINCT r.id) AS n
        FROM repositories r
        JOIN fixtures f ON f.repo_id = r.id
        GROUP BY r.language
        """
    ).fetchall()
    return {row["language"]: row["n"] for row in rows}


def _build_sampled_db(source_db: Path, output_db: Path, repo_ids: list[int]) -> int:
    """Build a fresh, standalone SQLite DB at `output_db` containing only
    the given repos (and their test_files/fixtures/mock_usages) copied from
    `source_db`. `source_db` is opened read-only for this whole call --
    never written to. `output_db` is always fully rebuilt (removed first,
    not updated incrementally).

    Reuses collection/db.py's own conflict-safe writers (upsert_repository,
    upsert_test_file, insert_fixture, insert_mock_usage) rather than raw SQL
    INSERT/SELECT, so the exact column set/handling can't drift from the
    real schema -- those functions already read whichever columns are
    present in the dict passed to them, so a plain `SELECT * FROM <table>`
    row (converted to a dict) is exactly the right shape to pass through
    unchanged, aside from the id remapping below.

    Autoincrement ids differ between source and dest DBs, so every foreign
    key (test_files.repo_id, fixtures.file_id/repo_id,
    mock_usages.fixture_id/repo_id) is remapped via old-id -> new-id maps
    built as rows are inserted, in FK order: repositories -> test_files ->
    fixtures -> mock_usages.

    Returns the total number of fixtures copied.
    """
    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()
    initialise_db(output_db)

    total_fixtures = 0
    with db_session(source_db) as src, db_session(output_db) as dst:
        for old_repo_id in repo_ids:
            repo_row = dict(
                src.execute(
                    "SELECT * FROM repositories WHERE id = ?", (old_repo_id,)
                ).fetchone()
            )
            new_repo_id, _ = upsert_repository(dst, repo_row)

            file_id_map: dict[int, int] = {}
            for tf_row in src.execute(
                "SELECT * FROM test_files WHERE repo_id = ?", (old_repo_id,)
            ).fetchall():
                tf_row = dict(tf_row)
                new_file_id = upsert_test_file(
                    dst, new_repo_id, tf_row["relative_path"], tf_row["language"]
                )
                file_id_map[tf_row["id"]] = new_file_id
                update_test_file_counts(
                    dst,
                    new_file_id,
                    tf_row["num_test_funcs"],
                    tf_row["num_fixtures"],
                    tf_row["file_loc"],
                    tf_row["total_fixture_loc"],
                )

            fixture_id_map: dict[int, int] = {}
            for fx_row in src.execute(
                "SELECT * FROM fixtures WHERE repo_id = ?", (old_repo_id,)
            ).fetchall():
                fx_row = dict(fx_row)
                old_fixture_id = fx_row["id"]
                fx_row["file_id"] = file_id_map[fx_row["file_id"]]
                fx_row["repo_id"] = new_repo_id
                new_fixture_id = insert_fixture(dst, fx_row)
                fixture_id_map[old_fixture_id] = new_fixture_id
                total_fixtures += 1

            for mu_row in src.execute(
                "SELECT * FROM mock_usages WHERE repo_id = ?", (old_repo_id,)
            ).fetchall():
                mu_row = dict(mu_row)
                mu_row["fixture_id"] = fixture_id_map[mu_row["fixture_id"]]
                mu_row["repo_id"] = new_repo_id
                insert_mock_usage(dst, mu_row)

            # A repo is never partially included, so its aggregate counts
            # carry over unchanged from the source -- no recomputation
            # needed (unlike a fixture-level sample, which would invalidate
            # these).
            set_repo_analysed(
                dst,
                new_repo_id,
                num_test_files=repo_row["num_test_files"],
                num_fixtures=repo_row["num_fixtures"],
                num_mock_usages=repo_row["num_mock_usages"],
                num_contributors=None,
            )

    logger.info(
        f"[sample-c-repos] Built {output_db} from {len(repo_ids)} repos, "
        f"{total_fixtures} fixtures"
    )
    return total_fixtures


def _write_sampled_fixture_csvs(sampled_db: Path, output_dir: Path) -> None:
    """Write datasets/c/fixtures-sampled/{language}_fixtures.csv from the
    freshly-built `sampled_db` -- purely an audit-trail artifact matching
    every other collection stage's CSV-per-language convention; nothing
    downstream reads these. Reuses corpus_utils.write_fixture_csv_row()
    directly so the column set/GitHub-URL construction can't drift from
    datasets/c/fixtures/*.csv's own real writer.

    Always fully rebuilt: `output_dir` is removed and recreated first, same
    "regenerate on demand" convention as research_questions/'s reports.
    """
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    with db_session(sampled_db) as conn:
        rows = conn.execute(
            """
            SELECT f.*, tf.relative_path AS file_path, tf.language AS fixture_language,
                   r.full_name AS repo_name
            FROM fixtures f
            JOIN test_files tf ON f.file_id = tf.id
            JOIN repositories r ON f.repo_id = r.id
            """
        ).fetchall()

    for row in rows:
        row = dict(row)
        language = row["fixture_language"]
        out_path = output_dir / f"{language}_fixtures.csv"
        fixture = {
            **row,
            "mocks": [None] * (row.get("num_mocks") or 0),
        }
        write_fixture_csv_row(out_path, row["repo_name"], language, fixture)


def sample_dataset_c_repos(
    target_count: int | None = None,
    match_dataset: str | None = None,
    tolerance: float = 0.02,
    seed: int = DATASET_C_SAMPLING_SEED,
    db_root: Path = paths.DB_ROOT,
    datasets_root: Path = paths.DATASETS_ROOT,
    output_dir: Path | None = None,
) -> dict:
    """Sample Dataset C down to `target_count` fixtures (or `match_dataset`'s
    live fixture count *and* language-by-repo-count mix), stratified by
    language, whole repos only. Writes db/c_sampled.db and
    datasets/c/fixtures-sampled/*.csv; db/c.db and datasets/c/fixtures/*.csv
    are read-only inputs, never modified.

    Exactly one of `target_count`/`match_dataset` must be given.
    `match_dataset` reads that dataset's CURRENT live fixture count *and*
    per-language repo-with-fixtures count from its own db/{match_dataset}.db
    at call time (not hardcoded numbers) -- both A and C get re-extracted
    independently, so this must stay dynamic. The sample's language mix
    then targets `match_dataset`'s mix instead of Dataset C's own (see
    sample_repos_by_language()'s target_proportions) -- when a language
    stratum in Dataset C can't reach its target share, it's capped at
    everything available and the shortfall redistributes to the other
    languages, never silently dropped. `target_count` given directly (no
    match_dataset) has no "other dataset" to match composition against, so
    it falls back to Dataset C's own mix, unchanged from before.
    """
    if (target_count is None) == (match_dataset is None):
        raise ValueError("Pass exactly one of target_count or match_dataset")

    source_db = paths.db_path("c", root=db_root)
    if not source_db.exists():
        raise FileNotFoundError(
            f"{source_db} not found; run `extract-fixtures --dataset c` first"
        )

    target_proportions: dict[str, int] | None = None
    if match_dataset is not None:
        match_db = paths.db_path(match_dataset, root=db_root)
        if not match_db.exists():
            raise FileNotFoundError(
                f"{match_db} not found; run `extract-fixtures --dataset "
                f"{match_dataset}` first"
            )
        with db_session(match_db) as conn:
            target_count = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
            target_proportions = _fetch_repo_language_counts_with_fixtures(conn)

    with db_session(source_db) as conn:
        repos = _fetch_dataset_c_repo_fixture_counts(conn)

    result = sample_repos_by_language(
        repos,
        target_count=target_count,
        tolerance=tolerance,
        seed=seed,
        target_proportions=target_proportions,
    )

    sampled_db = db_root / "c_sampled.db"
    total_fixtures = _build_sampled_db(source_db, sampled_db, result.sampled_repo_ids)

    fixtures_sampled_dir = datasets_root / "c" / "fixtures-sampled"
    _write_sampled_fixture_csvs(sampled_db, fixtures_sampled_dir)

    output = {
        "match_dataset": match_dataset,
        "target_count": result.target_count,
        "sampled_fixture_count": result.sampled_fixture_count,
        "sampled_repo_count": len(result.sampled_repo_ids),
        "random_seed": result.random_seed,
        "distribution_check": result.distribution_check,
        "sampled_repo_ids": result.sampled_repo_ids,
        "output_db": str(sampled_db),
        "output_csv_dir": str(fixtures_sampled_dir),
    }

    out_path = _sample_repos_output_path(output_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(output, f, indent=2)

    logger.info(
        f"[sample-c-repos] {result.sampled_fixture_count}/{result.target_count} "
        f"fixtures ({len(result.sampled_repo_ids)} repos) -> {sampled_db}, "
        f"{fixtures_sampled_dir} -- summary at {out_path}"
    )
    assert total_fixtures == result.sampled_fixture_count, (
        f"_build_sampled_db copied {total_fixtures} fixtures but "
        f"sample_repos_by_language() expected {result.sampled_fixture_count} "
        "-- population/sample mismatch, investigate before trusting this DB"
    )
    return output
