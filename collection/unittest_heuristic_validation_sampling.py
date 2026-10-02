"""Cochran-formula manual-validation sampling for the Python unittest
name-based lifecycle heuristic: `detector_python.py` classifies a method
named `setUp`/`tearDown`/`setUpClass`/`tearDownClass`/`setUpModule`/
`tearDownModule` as a real unittest fixture by **name alone** -- it never
checks whether the enclosing class actually extends `unittest.TestCase`
(directly or transitively). A false positive here is a same-named method
on an unrelated class (or a `TestCase` subclass via a chain the reviewer
needs the class header to even see).

Supersedes an earlier informal, ad hoc 40-fixture check (predates the
formal validation protocol; that number is being dropped from the paper
entirely) with a properly Cochran-sized sample, same 95% confidence / 5%
margin-of-error defaults and stratified allocation as
`collection.validation_sampling`'s `_sample_population()` -- reused
directly here, not reimplemented, same as
`collection.detection_validation_sampling`.

Deliberately its own module and its own CLI entry point, not folded into
`detection_validation_sampling.py`'s bundled
`run_detection_validation_sampling()`: that function's mock-detection and
pytest-lifecycle CSVs already carry a completed manual review (see git
history) -- re-running that bundle regenerates both files from scratch
(same seed, same population, so identical rows, but blank rater_label/
notes), which would destroy that review. Keeping this sample independent
means it can be (re)generated without ever touching those two files.

Population: `db/a.db` + `db/c.db`, both full (not `db/c_sampled.db` --
see `detection_validation_sampling.py`'s module docstring for why: that's
a fixture-count-matched sample-down for RQ2-4's paper statistics, not the
broadest population for a detector-precision check), Python fixtures only,
`fixture_type='unittest_setup'` restricted to exactly the six name-based
methods listed above -- `asyncSetUp`/`asyncTearDown` (also matched by
`unittest_setup`, see `fixture_definitions.yaml`) are deliberately
excluded, since they weren't part of the original informal check this
sample replaces and aren't named in scope here.

Reuses the exact same reviewer-facing schema as
`detection_validation_sampling.py` (`CSV_FIELDNAMES`/`_write_sample_csv`):

    id, source_url, raw_snippet, detected_label, rater_label, notes

`raw_snippet` is richer here than a bare fixture body: it includes the
enclosing class's header line (`class Foo(Base1, Base2):`) fetched live
from GitHub's raw-content CDN at the fixture's own pinned commit and
re-parsed with the same tree-sitter Python grammar the detector itself
uses -- the reviewer's whole job is judging whether that base class chain
is really `unittest.TestCase`, which the DB's own `fixtures.raw_source`
(method body only, no class context) can't show at all. A module-level
`setUpModule`/`tearDownModule` has no enclosing class by definition, and
correctly gets no header. A fetch/parse failure (renamed repo, deleted
file, network hiccup) falls back to the bare method body -- the
reviewer's own `source_url` click-through is the real fallback for a
since-deleted file (rated 404), not this best-effort enrichment step.

Precision-only, no recall attempted -- matching every other manual-
validation sample in this project. Does not touch, read as sampled input,
or regenerate `mock_detection_sample.csv`/`pytest_lifecycle_sample.csv`.

python -m collection.unittest_heuristic_validation_sampling
"""

from __future__ import annotations

import argparse
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from . import paths
from .corpus_utils import _build_github_url
from .detection_validation_sampling import DEFAULT_SEED, _write_sample_csv
from .detector_shared import _get_parser
from .logging_utils import configure_logging, get_logger
from .validation_sampling import _sample_population

logger = get_logger(__name__)

DEFAULT_OUTPUT_ROOT = paths.ROOT_DIR / "validation-samples"
STEP = "unittest-heuristic"
FILENAME = "unittest_heuristic_sample.csv"

# Exactly the six name-based methods in scope -- see module docstring for
# why asyncSetUp/asyncTearDown (also unittest_setup) are excluded.
UNITTEST_LIFECYCLE_NAMES = (
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "setUpModule",
    "tearDownModule",
)

_FETCH_TIMEOUT_SECONDS = 10.0
_FETCH_WORKERS = 16


@dataclass(frozen=True)
class SampleResult:
    step: str
    output_file: Path
    population_size: int
    sample_size: int
    strata: list[dict[str, Any]]


def _fetch_unittest_heuristic_candidates(
    conn: sqlite3.Connection, dataset: str
) -> list[dict[str, Any]]:
    """DB-only candidate rows (no network) -- one per fixture matching the
    six name-based unittest lifecycle methods. Enrichment (the live class-
    header fetch) happens later, only for the rows Cochran sampling
    actually selects, not the whole population."""
    placeholders = ", ".join("?" for _ in UNITTEST_LIFECYCLE_NAMES)
    rows = conn.execute(
        f"""
        SELECT f.id, r.full_name, f.commit_sha, tf.relative_path,
               f.start_line, f.end_line, f.raw_source, f.name
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        JOIN repositories r ON f.repo_id = r.id
        WHERE tf.language = 'python' AND f.fixture_type = 'unittest_setup'
          AND f.name IN ({placeholders})
        """,
        UNITTEST_LIFECYCLE_NAMES,
    ).fetchall()
    return [
        {
            "id": f"{dataset}:python:{fixture_id}",
            "dataset": dataset,
            "repo_full_name": repo_full_name,
            "commit_sha": commit_sha or "",
            "relative_path": relative_path or "",
            "start_line": start_line or 0,
            "end_line": end_line or 0,
            "raw_source": raw_source or "",
            "name": name,
        }
        for (
            fixture_id,
            repo_full_name,
            commit_sha,
            relative_path,
            start_line,
            end_line,
            raw_source,
            name,
        ) in rows
    ]


def _fetch_file_content(
    repo_full_name: str, commit_sha: str, relative_path: str
) -> str | None:
    """Best-effort fetch of a file's content at a specific commit via
    GitHub's raw-content CDN. None on any failure (404, network error,
    timeout) -- the reviewer's own source_url click-through, not this, is
    the real check for a since-deleted/renamed file (rated 404)."""
    if not (repo_full_name and commit_sha and relative_path):
        return None
    url = f"https://raw.githubusercontent.com/{repo_full_name}/{commit_sha}/{relative_path}"
    try:
        response = requests.get(url, timeout=_FETCH_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return response.text
    except requests.RequestException:
        pass
    return None


def _find_enclosing_class_header(
    file_content: str, method_name: str, method_start_line: int
) -> str | None:
    """The enclosing class's header text (`class Foo(Base1, Base2):`) for
    the function named `method_name` starting at `method_start_line`
    (1-indexed), re-parsed from `file_content` with the same tree-sitter
    Python grammar the detector itself uses. None if the function can't
    be re-located (file drifted since extraction) or has no enclosing
    class at all (a genuine module-level setUpModule/tearDownModule, or a
    class-definition ancestor that can't be found)."""
    parser = _get_parser("python")
    src_bytes = file_content.encode("utf-8")
    tree = parser.parse(src_bytes)

    target = None

    def visit(node) -> None:
        nonlocal target
        if target is not None:
            return
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if (
                name_node is not None
                and src_bytes[name_node.start_byte : name_node.end_byte].decode(
                    "utf-8", errors="replace"
                )
                == method_name
                and node.start_point[0] + 1 == method_start_line
            ):
                target = node
                return
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    if target is None:
        return None

    node = target.parent
    while node is not None and node.type != "class_definition":
        node = node.parent
    if node is None:
        return None  # module-level function -- no enclosing class

    body = node.child_by_field_name("body")
    header_end = body.start_byte if body is not None else node.end_byte
    return src_bytes[node.start_byte : header_end].decode("utf-8", errors="replace").rstrip()


def _build_raw_snippet(candidate: dict[str, Any]) -> str:
    """Class header (if fetchable/locatable) + the method body -- the
    method body always comes from the DB's own raw_source (identical
    content to a successful fetch, since both are the same pinned commit;
    simpler than re-slicing from the fetched file), so this degrades
    gracefully to just the bare method on any fetch/parse failure."""
    file_content = _fetch_file_content(
        candidate["repo_full_name"], candidate["commit_sha"], candidate["relative_path"]
    )
    header = None
    if file_content is not None:
        header = _find_enclosing_class_header(
            file_content, candidate["name"], candidate["start_line"]
        )
    if header:
        return f"{header}\n    ...\n{candidate['raw_source']}"
    return candidate["raw_source"]


def _enrich_sampled_rows(sampled: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch+build raw_snippet for the sampled rows only (not the whole
    population) -- concurrent, since this is network-bound."""
    with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as executor:
        snippets = list(executor.map(_build_raw_snippet, sampled))

    enriched = []
    for candidate, snippet in zip(sampled, snippets):
        enriched.append(
            {
                "id": candidate["id"],
                "source_url": _build_github_url(
                    candidate["repo_full_name"],
                    candidate["commit_sha"],
                    candidate["relative_path"],
                    candidate["start_line"],
                    candidate["end_line"],
                ),
                "raw_snippet": snippet,
                "detected_label": candidate["name"],
            }
        )
    return enriched


def run_unittest_heuristic_sampling(
    *,
    db_a: Path,
    db_c: Path,
    confidence_level: float = 0.95,
    margin_of_error: float = 0.05,
    proportion: float = 0.5,
    seed: int = DEFAULT_SEED,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> SampleResult:
    logger.info("[Unittest Heuristic Sampling] seed=%d", seed)

    conn_a = sqlite3.connect(db_a)
    conn_c = sqlite3.connect(db_c)
    try:
        candidates = _fetch_unittest_heuristic_candidates(
            conn_a, "A"
        ) + _fetch_unittest_heuristic_candidates(conn_c, "C")
    finally:
        conn_a.close()
        conn_c.close()

    sampled, strata_metadata = _sample_population(
        candidates, ("dataset",), confidence_level, margin_of_error, proportion, seed
    )
    enriched = _enrich_sampled_rows(sampled)

    step_dir = output_root / STEP
    out_path = _write_sample_csv(step_dir, FILENAME, enriched)

    result = SampleResult(
        step=STEP,
        output_file=out_path,
        population_size=len(candidates),
        sample_size=len(sampled),
        strata=strata_metadata,
    )
    logger.info(
        "[Unittest Heuristic Sampling] N=%d -> n=%d -> %s",
        result.population_size,
        result.sample_size,
        result.output_file,
    )
    for stratum in strata_metadata:
        logger.info("[Unittest Heuristic Sampling] stratum %s", stratum)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Draw a Cochran-sized manual-validation sample for the Python "
            "unittest name-based lifecycle heuristic (setUp/tearDown/"
            "setUpClass/tearDownClass/setUpModule/tearDownModule)."
        )
    )
    parser.add_argument("--db-a", type=Path, default=paths.db_path("a"))
    parser.add_argument("--db-c", type=Path, default=paths.db_path("c"))
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--margin-error", type=float, default=0.05)
    parser.add_argument("--proportion", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(fmt="%(message)s")
    args = build_parser().parse_args(argv)
    run_unittest_heuristic_sampling(
        db_a=args.db_a,
        db_c=args.db_c,
        confidence_level=args.confidence_level,
        margin_of_error=args.margin_error,
        proportion=args.proportion,
        seed=args.seed,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
