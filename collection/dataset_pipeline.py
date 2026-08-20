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
from .dataset_sampler import StratifiedSampler, sample_fixtures_by_language
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
# Dataset C sample-down (fixture-level, language-stratified, exact-count-
# matched to another dataset -- e.g. Dataset A)
#
# db/c.db and datasets/c/fixtures/*.csv (the full, ~3.3x-Dataset-A-sized
# originals) are never modified here -- read-only source. This builds a
# separate, standalone db/c_sampled.db + datasets/c/fixtures-sampled/*.csv
# alongside them. research_questions/_shared.py::require_db_or_none() and
# language_contamination.py::check_dataset() are the enforcement points that
# make every research_questions/ script read c_sampled.db/fixtures-sampled/
# instead of the full originals -- see those modules, not this one, for why
# that's mandatory rather than opt-in.
#
# Fixture-level, not whole-repo: each language is sampled independently,
# down to an *exact* target fixture count (the match dataset's real count
# for that language), with individual fixtures drawn without replacement
# regardless of which repo they come from -- see
# sample_dataset_c_repos()'s docstring for why this replaced the earlier
# whole-repo approach (which could only ever land close to a target, never
# on it, since a repo is an indivisible chunk of fixtures).
# ---------------------------------------------------------------------------


def _sample_repos_output_path(output_dir: Path | None = None) -> Path:
    output_dir = output_dir or (paths.ROOT_DIR / "output")
    return output_dir / "sample_c_repos.json"


def _fetch_fixture_language_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Total fixture count per each fixture's OWN detected language
    (test_files.language) -- not the fixture's repo's tagged language.
    Used both to read another dataset's real per-language fixture counts
    (the sampling target) and Dataset C's own per-language totals (for
    ratio/shortfall reporting). Same grouping as
    research_questions/dataset_findings.py's "Fixture Counts by
    Language" table: a leaked fixture (whose own language differs from
    its repo's tag) is counted/sampled as the language it's actually
    written in, not whichever language its repo happens to be filed
    under."""
    rows = conn.execute(
        """
        SELECT tf.language AS language, COUNT(*) AS n
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        GROUP BY tf.language
        """
    ).fetchall()
    return {row["language"]: row["n"] for row in rows}


def _fetch_repo_counts_by_fixture_language(conn: sqlite3.Connection) -> dict[str, int]:
    """Distinct repo count per fixture's own language -- "how many repos
    have at least one fixture written in this language". Purely
    descriptive under fixture-level sampling (a repo is no longer a
    sampling unit, so this isn't a quota) -- exists for the
    sampling-summary report's "repos touched" figures, which
    research_questions/dataset_findings.py still reads from the output
    JSON this module writes."""
    rows = conn.execute(
        """
        SELECT tf.language AS language, COUNT(DISTINCT f.repo_id) AS n
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        GROUP BY tf.language
        """
    ).fetchall()
    return {row["language"]: row["n"] for row in rows}


def _fetch_dataset_c_fixtures_by_own_language(conn: sqlite3.Connection) -> list[dict]:
    """One row per fixture: {"fixture_id": int, "language": str} -- the
    population sample_fixtures_by_language() samples from. `language` is
    the fixture's own detected language (test_files.language), matching
    _fetch_fixture_language_counts() above."""
    rows = conn.execute(
        """
        SELECT f.id AS fixture_id, tf.language AS language
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _build_sampled_db_from_fixtures(
    source_db: Path, output_db: Path, fixture_ids: list[int]
) -> int:
    """Build a fresh, standalone SQLite DB at `output_db` containing only
    the given *fixtures* (not whole repos) copied from `source_db`, plus
    each fixture's own repo/test_file rows (foreign-key dependencies) and
    any mock_usages rows belonging to a copied fixture.

    A repo/test_file can be partially represented here -- two fixtures
    from the same repo can land on opposite sides of the sample -- so
    repositories.num_fixtures/num_test_files/num_mock_usages and
    test_files.num_fixtures/total_fixture_loc are *recomputed* from what
    was actually copied, never carried over from the source row
    unchanged (unlike a whole-repo sample, where a repo is never
    partially included and the source's own aggregate counts are already
    correct as-is).

    `source_db` is opened read-only for this whole call, never written
    to. `output_db` is always fully rebuilt (removed first, not updated
    incrementally). Reuses collection/db.py's own conflict-safe writers
    (upsert_repository, upsert_test_file, insert_fixture,
    insert_mock_usage) rather than raw SQL INSERT, so the exact column
    set/handling can't drift from the real schema.

    Returns the total number of fixtures copied.
    """
    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()
    initialise_db(output_db)

    if not fixture_ids:
        return 0

    with db_session(source_db) as src, db_session(output_db) as dst:
        placeholders = ",".join("?" for _ in fixture_ids)
        fixture_rows = [
            dict(row)
            for row in src.execute(
                f"SELECT * FROM fixtures WHERE id IN ({placeholders})",
                fixture_ids,
            ).fetchall()
        ]
        if not fixture_rows:
            return 0

        fixtures_by_repo: dict[int, list[dict]] = {}
        for fx in fixture_rows:
            fixtures_by_repo.setdefault(fx["repo_id"], []).append(fx)

        repo_id_map: dict[int, int] = {}
        fixture_id_map: dict[int, int] = {}
        total_fixtures = 0

        for old_repo_id, repo_fixtures in fixtures_by_repo.items():
            repo_row = dict(
                src.execute(
                    "SELECT * FROM repositories WHERE id = ?", (old_repo_id,)
                ).fetchone()
            )
            new_repo_id, _ = upsert_repository(dst, repo_row)
            repo_id_map[old_repo_id] = new_repo_id

            fixtures_by_file: dict[int, list[dict]] = {}
            for fx in repo_fixtures:
                fixtures_by_file.setdefault(fx["file_id"], []).append(fx)

            for old_file_id, file_fixtures in fixtures_by_file.items():
                tf_row = dict(
                    src.execute(
                        "SELECT * FROM test_files WHERE id = ?", (old_file_id,)
                    ).fetchone()
                )
                new_file_id = upsert_test_file(
                    dst, new_repo_id, tf_row["relative_path"], tf_row["language"]
                )

                file_fixture_loc = 0
                for fx_row in file_fixtures:
                    old_fixture_id = fx_row["id"]
                    fx_row = dict(fx_row)
                    fx_row["file_id"] = new_file_id
                    fx_row["repo_id"] = new_repo_id
                    new_fixture_id = insert_fixture(dst, fx_row)
                    fixture_id_map[old_fixture_id] = new_fixture_id
                    total_fixtures += 1
                    file_fixture_loc += fx_row.get("loc") or 0

                # file_loc/num_test_funcs describe the whole source file,
                # unaffected by how many of its fixtures got sampled --
                # only the fixture-derived aggregates need recomputing.
                update_test_file_counts(
                    dst,
                    new_file_id,
                    tf_row["num_test_funcs"],
                    len(file_fixtures),
                    tf_row["file_loc"],
                    file_fixture_loc,
                )

        # One pass over mock_usages after every fixture is inserted, not
        # per-repo/per-file above -- simpler than threading partial
        # fixture_id_map state through the loop, and this table is small
        # enough that a second query over the full old-id set costs
        # nothing meaningful.
        old_fixture_ids = list(fixture_id_map.keys())
        mu_placeholders = ",".join("?" for _ in old_fixture_ids)
        for mu_row in src.execute(
            f"SELECT * FROM mock_usages WHERE fixture_id IN ({mu_placeholders})",
            old_fixture_ids,
        ).fetchall():
            mu_row = dict(mu_row)
            mu_row["fixture_id"] = fixture_id_map[mu_row["fixture_id"]]
            mu_row["repo_id"] = repo_id_map[mu_row["repo_id"]]
            insert_mock_usage(dst, mu_row)

        # Recompute each touched repo's aggregate counts from what was
        # actually copied -- see docstring above for why these can't be
        # carried over from the source unchanged anymore.
        for old_repo_id, new_repo_id in repo_id_map.items():
            repo_fixtures = fixtures_by_repo[old_repo_id]
            num_test_files = len({fx["file_id"] for fx in repo_fixtures})
            num_mock_usages = dst.execute(
                "SELECT COUNT(*) FROM mock_usages WHERE repo_id = ?", (new_repo_id,)
            ).fetchone()[0]
            set_repo_analysed(
                dst,
                new_repo_id,
                num_test_files=num_test_files,
                num_fixtures=len(repo_fixtures),
                num_mock_usages=num_mock_usages,
                num_contributors=None,
            )

    logger.info(
        f"[sample-c-fixtures] Built {output_db} from {len(fixture_ids)} "
        f"requested fixtures ({total_fixtures} copied), "
        f"{len(repo_id_map)} distinct repos touched"
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
    """Sample Dataset C down to `match_dataset`'s exact per-language
    fixture count (or an explicit `target_count`, split across languages
    by Dataset C's own mix), fixture-level -- each language sampled
    independently, individual fixtures drawn without replacement
    regardless of which repo they come from. Writes db/c_sampled.db and
    datasets/c/fixtures-sampled/*.csv; db/c.db and
    datasets/c/fixtures/*.csv are read-only inputs, never modified.

    Fixture-level rather than whole-repo (the previous approach here) so
    the sample can hit `match_dataset`'s per-language counts *exactly*
    instead of only approximately -- a whole repo is an indivisible
    chunk of fixtures, so repo-level sampling could only ever land close
    to a target, never on it. This is deliberately at the cost of no
    longer guaranteeing a sampled repo's fixtures are all present
    together: two fixtures from the same repo can land on opposite sides
    of the sample, maximizing the number of distinct repos represented
    (breadth) over keeping any one sampled repo "whole". **Do not compute
    repo-level statistics (e.g. RQ2's setup/teardown pairing) against
    db/c_sampled.db for this reason** -- research_questions/ scripts
    already read the full, unsampled db/c.db for those (Dataset C
    sampling is deactivated there -- see
    research_questions/_shared.py::require_db_or_none()'s docstring);
    this sampled DB was never meant to support that kind of analysis.

    Exactly one of `target_count`/`match_dataset` must be given.
    `match_dataset` reads that dataset's CURRENT live per-language
    fixture counts from its own db/{match_dataset}.db at call time (not
    hardcoded numbers, since both A and C get re-extracted
    independently), grouped by each fixture's own detected language
    (test_files.language) -- see _fetch_fixture_language_counts()'s
    docstring for why that's the right grouping, not the repo's tagged
    language. `target_count` given directly (no match_dataset) has no
    other dataset's per-language mix to match, so it's split across
    languages by Dataset C's own mix instead (same fallback spirit as
    the old repo-level sampler's).

    When a language's target exceeds what Dataset C actually has
    available, every available fixture for that language is taken
    instead (see sample_fixtures_by_language()) and a warning is
    logged -- unlike the old whole-repo approach, there's no
    cross-language shortfall redistribution anymore: each language is
    sampled fully independently, so a shortfall in one language never
    affects another's target.

    `tolerance` is accepted for CLI-signature/backward-compatibility but
    no longer affects sampling: a fixture-level sample either hits a
    language's target exactly or (on shortfall) takes everything
    available -- there's no probabilistic deviation left to tolerate the
    way whole-repo chunking had.
    """
    if (target_count is None) == (match_dataset is None):
        raise ValueError("Pass exactly one of target_count or match_dataset")

    source_db = paths.db_path("c", root=db_root)
    if not source_db.exists():
        raise FileNotFoundError(
            f"{source_db} not found; run `extract-fixtures --dataset c` first"
        )

    with db_session(source_db) as conn:
        c_language_counts = _fetch_fixture_language_counts(conn)
        c_repo_counts_by_language = _fetch_repo_counts_by_fixture_language(conn)
        fixtures_pool = _fetch_dataset_c_fixtures_by_own_language(conn)

    total_c_fixtures = sum(c_language_counts.values())
    if total_c_fixtures == 0:
        raise ValueError(f"Cannot sample: {source_db} has no fixtures")

    if match_dataset is not None:
        match_db = paths.db_path(match_dataset, root=db_root)
        if not match_db.exists():
            raise FileNotFoundError(
                f"{match_db} not found; run `extract-fixtures --dataset "
                f"{match_dataset}` first"
            )
        with db_session(match_db) as conn:
            target_counts = _fetch_fixture_language_counts(conn)
    else:
        # No other dataset to match -- split target_count across
        # languages by Dataset C's own mix, same fallback the old
        # repo-level sampler used for this case.
        target_counts = {
            language: round(target_count * (n / total_c_fixtures))
            for language, n in c_language_counts.items()
        }

    result = sample_fixtures_by_language(fixtures_pool, target_counts, seed=seed)

    sampled_db = db_root / "c_sampled.db"
    total_fixtures = _build_sampled_db_from_fixtures(
        source_db, sampled_db, result.sampled_fixture_ids
    )

    fixtures_sampled_dir = datasets_root / "c" / "fixtures-sampled"
    _write_sampled_fixture_csvs(sampled_db, fixtures_sampled_dir)

    with db_session(sampled_db) as conn:
        sampled_repo_counts_by_language = _fetch_repo_counts_by_fixture_language(conn)
        sampled_repo_count = conn.execute(
            "SELECT COUNT(*) FROM repositories"
        ).fetchone()[0]

    # distribution_check keeps the same key shape the old whole-repo
    # sampler produced -- research_questions/dataset_findings.py's
    # sampling-summary section reads these exact keys and must not be
    # modified (see this function's docstring). "Repos" figures here are
    # descriptive breadth, not a quota, under fixture-level sampling.
    target_weight_sum = sum(target_counts.values()) or 1
    distribution_check: dict[str, dict] = {}
    for language in sorted(set(c_language_counts) | set(target_counts)):
        available = c_language_counts.get(language, 0)
        target = target_counts.get(language, 0)
        sampled = result.distribution_check.get(language, {}).get("sampled_count", 0)
        distribution_check[language] = {
            "original_ratio": round(available / total_c_fixtures, 4),
            "target_ratio": round(target / target_weight_sum, 4),
            "sampled_ratio": round(sampled / result.sampled_fixture_count, 4)
            if result.sampled_fixture_count
            else 0.0,
            "dataset_c_available_fixture_count": available,
            "dataset_c_available_repo_count": c_repo_counts_by_language.get(language, 0),
            "sampled_fixture_count": sampled,
            "sampled_repo_count": sampled_repo_counts_by_language.get(language, 0),
            "shortfall": result.distribution_check.get(language, {}).get(
                "shortfall", False
            ),
        }

    output = {
        "match_dataset": match_dataset,
        "target_count": result.target_count,
        "sampled_fixture_count": result.sampled_fixture_count,
        "sampled_repo_count": sampled_repo_count,
        "random_seed": result.random_seed,
        "distribution_check": distribution_check,
        "sampled_fixture_ids": result.sampled_fixture_ids,
        "output_db": str(sampled_db),
        "output_csv_dir": str(fixtures_sampled_dir),
    }

    out_path = _sample_repos_output_path(output_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(output, f, indent=2)

    logger.info(
        f"[sample-c-repos] {result.sampled_fixture_count}/{result.target_count} "
        f"fixtures ({sampled_repo_count} repos touched) -> {sampled_db}, "
        f"{fixtures_sampled_dir} -- summary at {out_path}"
    )
    assert total_fixtures == result.sampled_fixture_count, (
        f"_build_sampled_db_from_fixtures copied {total_fixtures} fixtures but "
        f"sample_fixtures_by_language() expected {result.sampled_fixture_count} "
        "-- population/sample mismatch, investigate before trusting this DB"
    )
    return output
