"""Fixed-n=100 manual-validation sampling for detector precision.

Supersedes `validation_v1/` (see that folder's README for why): the
earlier Cochran-sized samples (376/380/378 fixtures) were drawn from
`db/a.db` + `db/c.db` (the full, pre-sampling Dataset C pool) and, for the
pytest case, included the plain `setup` stratum, which is a fixed-rule
assignment (no `yield`/`addfinalizer` analysis -- nothing to validate).
This module instead draws exactly 100 fixtures per case from the **final**
datasets the paper cites (`db/a.db` + `db/c_sampled.db`), restricts the
pytest case to the `teardown`/`setup_and_teardown` roles only (the ones a
body-analysis judgment call actually produced), widens the unittest case
to all eight lifecycle names (including `asyncSetUp`/`asyncTearDown`,
excluded from v1), and adds a fourth case (bare `before`/`after` in
JS/TS) that v1 never covered at all.

The four cases
---------------
1. mock_detection    -- fixtures with num_mocks > 0, all 4 languages.
2. pytest_scope      -- Python pytest_decorator fixtures whose role was
                        assigned by yield/addfinalizer body analysis
                        (fixture_role IN ('teardown', 'setup_and_teardown')
                        -- plain 'setup' is a fixed rule, not a judgment
                        call, so it is excluded from this population).
3. unittest_detection -- Python fixtures with fixture_type='unittest_setup'
                        (all 8 name-based methods, no name restriction).
4. before_after      -- JavaScript/TypeScript fixtures with fixture_type
                        IN ('mocha_before', 'mocha_after') (bare `before(`/
                        `after(` calls).

Sampling
--------
Reuses `collection.validation_sampling`'s `_allocate_stratified()`
(largest-remainder proportional allocation) and `sample_rows()`
(content-hash-sorted, `Random(seed).sample(...)`) rather than
reimplementing either -- same determinism guarantee as every other
sampling step in this project: a fresh `Random(seed)` per stratum/call,
so cases and strata never share RNG state (unlike
`dataset_sampler.py::sample_fixtures_by_language()`'s single shared
`Random` instance advanced across languages in sequence -- see
`internal-docs/` for why that one's cross-language RNG-stream coupling
matters there; it does not apply here).

Target sample size is a fixed 100 per case (not Cochran-sized). When a
case's population is below 100, every fixture in it is included instead
(`_allocate_stratified()` already does this: `target = min(total_n,
population)`), and `run_detector_precision_sampling()` logs/records the
shortfall rather than treating it as an error.

One seed for all four cases: 42, reused from
`detection_validation_sampling.DEFAULT_SEED` (the project default for
every validation-sampling step found during Phase 1 exploration) --
not a new seed, since one already existed.

Context and "what the detector reported"
------------------------------------------
Every sampled row needs the surrounding file fetched once (reuses
`unittest_heuristic_validation_sampling._fetch_file_content()`, a GitHub
raw-content CDN fetch at the fixture's own pinned commit) to build:

- `source_with_context`: the fixture body plus 5 lines before/after,
  line-numbered. Falls back to the fixture's own `raw_source` (no
  context) on any fetch failure.
- `detector_reported`, case-specific:
    - mock_detection: each mock's framework + target, from `mock_usages`.
    - pytest_scope: the assigned `fixture_role` (teardown / setup and
      teardown) -- no file fetch needed for this value itself, but the
      row still gets `source_with_context` like every other case.
    - unittest_detection: the enclosing class declaration (reused,
      unmodified, from `unittest_heuristic_validation_sampling`'s own
      tree-sitter re-parse) plus the file's test-related import lines.
    - before_after: the file's test-related import lines only.

A GitHub permalink is built with `?plain=1` inserted before the `#L`
anchor (so GitHub renders the raw file as plain text, not a rendered
Markdown/syntax view) -- no existing code in this project did this
before; every prior sample used a plain blob URL.

Coding sheet schema (identical across all four CSVs)
-----------------------------------------------------
    case, dataset, language, repository, file_path, line_number,
    github_url, source_with_context, detector_reported, label, notes

`label` is empty here -- the (single) reviewer fills in exactly one of
`true_positive` / `false_positive` / `unsure` (no `404` category this
time, unlike v1's TP/FP/Unsure/404: every sampled row is still reachable
on GitHub by construction, since the fixture came from the live final
datasets, not an aged-out Cochran sample).

python -m collection.detector_precision_sampling
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .logging_utils import configure_logging, get_logger
from .unittest_heuristic_validation_sampling import (
    _fetch_file_content,
    _find_enclosing_class_header,
)
from .validation_sampling import _allocate_stratified, sample_rows

logger = get_logger(__name__)

DEFAULT_OUTPUT_ROOT = paths.ROOT_DIR / "validation-samples"
SEED = 42  # reused from detection_validation_sampling.DEFAULT_SEED -- see module docstring
SAMPLE_SIZE_PER_CASE = 100
CONTEXT_LINES = 5
_FETCH_WORKERS = 16

CSV_FIELDNAMES = [
    "case",
    "dataset",
    "language",
    "repository",
    "file_path",
    "line_number",
    "github_url",
    "source_with_context",
    "detector_reported",
    "label",
    "notes",
]

# Deliberately modest keyword lists -- the goal is to surface the import
# line(s) that identify the governing test framework, not to reproduce
# the whole file; the reviewer's own github_url click-through is the
# fallback for anything this misses.
PYTHON_TEST_IMPORT_KEYWORDS = ("unittest", "pytest", "mock", "nose", "testtools")
JS_TEST_IMPORT_KEYWORDS = (
    "mocha",
    "jest",
    "vitest",
    "jasmine",
    "chai",
    "sinon",
    "cypress",
    "ava",
    "tape",
    "qunit",
    "playwright",
    "karma",
)

CASE_NAMES = ("mock_detection", "pytest_scope", "unittest_detection", "before_after")

# (case, folder, filename) -- folder/filename reuse v1's names where a
# case existed in v1, so the new samples land in the same place the old
# ones used to (now moved to validation_v1/); before_after is new.
CASE_OUTPUT_PATHS: dict[str, tuple[str, str]] = {
    "mock_detection": ("mock-detection", "mock_detection_sample.csv"),
    "pytest_scope": ("pytest-lifecycle", "pytest_lifecycle_sample.csv"),
    "unittest_detection": ("unittest-heuristic", "unittest_heuristic_sample.csv"),
    "before_after": ("before-after", "before_after_sample.csv"),
}

README_TEXT = """# Detector Precision Validation Samples

Four fixed-n=100, stratified, precision-only samples for manual
single-rater review, generated by `python -m
collection.detector_precision_sampling` on the **final** datasets (`db/a.db` +
`db/c_sampled.db` -- the ones reported in the paper), seed 42. See
`collection/detector_precision_sampling.py`'s module docstring for the full
population definitions and why they changed from `validation_v1/`.

| File | Population | Stratified by |
|---|---|---|
| `mock-detection/mock_detection_sample.csv` | Fixtures with `num_mocks > 0` (A+C sampled, all 4 languages) | dataset, language |
| `pytest-lifecycle/pytest_lifecycle_sample.csv` | Python `pytest_decorator` fixtures with `fixture_role IN ('teardown', 'setup_and_teardown')` (A+C sampled) | dataset |
| `unittest-heuristic/unittest_heuristic_sample.csv` | Python `unittest_setup` fixtures, all 8 lifecycle names (A+C sampled) | dataset |
| `before-after/before_after_sample.csv` | JS/TS fixtures with `fixture_type IN ('mocha_before', 'mocha_after')` (A+C sampled) | dataset, language |

## Columns

| Column | Meaning |
|---|---|
| `case` | One of `mock_detection` / `pytest_scope` / `unittest_detection` / `before_after` |
| `dataset` | `A` (agent-created) or `C` (human-created, sampled) |
| `language` | The fixture's own detected language |
| `repository` | `owner/repo` |
| `file_path` | Path of the file containing the fixture, relative to the repo root |
| `line_number` | The fixture's start line in that file |
| `github_url` | Permalink to the fixture at its analyzed commit, `?plain=1` before the `#L` anchor |
| `source_with_context` | The fixture's source, with 5 lines of context before and after, line-numbered |
| `detector_reported` | What the detector claims -- see the module docstring for the per-case definition |
| `label` | Empty -- reviewer fills in: `true_positive` \\| `false_positive` \\| `unsure` |
| `notes` | Empty -- reviewer fills in optional free text |

No `404` category this time -- every row comes from the live final
datasets, so the artifact is expected to still be reachable.

Precision-only: these samples check whether a positive detection is
correct, not whether the detector missed anything (no recall sampling).
"""


@dataclass(frozen=True)
class CaseResult:
    case: str
    output_file: Path
    population_size: int
    sample_size: int
    shortfall: bool
    strata: list[dict[str, Any]]


@dataclass
class _Candidate:
    """Internal, pre-enrichment row -- one per candidate fixture."""

    case: str
    dataset: str
    language: str
    repo_full_name: str
    commit_sha: str
    relative_path: str
    start_line: int
    end_line: int
    raw_source: str
    detector_reported: str = ""  # filled in now (DB-only) or during enrichment
    extra: dict[str, Any] = field(default_factory=dict)

    def strata_key(self, stratify_by: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(getattr(self, field_name) for field_name in stratify_by)


def _fetch_mock_detection_candidates(conn: sqlite3.Connection, dataset: str) -> list[_Candidate]:
    rows = conn.execute(
        """
        SELECT f.id, tf.language, r.full_name, f.commit_sha, tf.relative_path,
               f.start_line, f.end_line, f.raw_source
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        JOIN repositories r ON f.repo_id = r.id
        WHERE f.num_mocks > 0
        """
    ).fetchall()
    candidates = []
    for fixture_id, language, repo, sha, path, start, end, raw_source in rows:
        mocks = conn.execute(
            "SELECT framework, target_identifier FROM mock_usages WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchall()
        mock_desc = "; ".join(
            f"{framework or 'unknown'}: {target or '?'}" for framework, target in mocks
        )
        candidates.append(
            _Candidate(
                case="mock_detection",
                dataset=dataset,
                language=language,
                repo_full_name=repo or "",
                commit_sha=sha or "",
                relative_path=path or "",
                start_line=start or 0,
                end_line=end or 0,
                raw_source=raw_source or "",
                detector_reported=mock_desc or "(no mock_usages row found)",
            )
        )
    return candidates


def _fetch_pytest_scope_candidates(conn: sqlite3.Connection, dataset: str) -> list[_Candidate]:
    rows = conn.execute(
        """
        SELECT r.full_name, f.commit_sha, tf.relative_path,
               f.start_line, f.end_line, f.raw_source, f.fixture_role
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        JOIN repositories r ON f.repo_id = r.id
        WHERE tf.language = 'python' AND f.fixture_type = 'pytest_decorator'
          AND f.fixture_role IN ('teardown', 'setup_and_teardown')
        """
    ).fetchall()
    return [
        _Candidate(
            case="pytest_scope",
            dataset=dataset,
            language="python",
            repo_full_name=repo or "",
            commit_sha=sha or "",
            relative_path=path or "",
            start_line=start or 0,
            end_line=end or 0,
            raw_source=raw_source or "",
            detector_reported=role.replace("_", " "),
        )
        for (repo, sha, path, start, end, raw_source, role) in rows
    ]


def _fetch_unittest_detection_candidates(
    conn: sqlite3.Connection, dataset: str
) -> list[_Candidate]:
    rows = conn.execute(
        """
        SELECT r.full_name, f.commit_sha, tf.relative_path,
               f.start_line, f.end_line, f.raw_source, f.name
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        JOIN repositories r ON f.repo_id = r.id
        WHERE tf.language = 'python' AND f.fixture_type = 'unittest_setup'
        """
    ).fetchall()
    return [
        _Candidate(
            case="unittest_detection",
            dataset=dataset,
            language="python",
            repo_full_name=repo or "",
            commit_sha=sha or "",
            relative_path=path or "",
            start_line=start or 0,
            end_line=end or 0,
            raw_source=raw_source or "",
            extra={"method_name": name},
        )
        for (repo, sha, path, start, end, raw_source, name) in rows
    ]


def _fetch_before_after_candidates(conn: sqlite3.Connection, dataset: str) -> list[_Candidate]:
    rows = conn.execute(
        """
        SELECT tf.language, r.full_name, f.commit_sha, tf.relative_path,
               f.start_line, f.end_line, f.raw_source
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        JOIN repositories r ON f.repo_id = r.id
        WHERE tf.language IN ('javascript', 'typescript')
          AND f.fixture_type IN ('mocha_before', 'mocha_after')
        """
    ).fetchall()
    return [
        _Candidate(
            case="before_after",
            dataset=dataset,
            language=language,
            repo_full_name=repo or "",
            commit_sha=sha or "",
            relative_path=path or "",
            start_line=start or 0,
            end_line=end or 0,
            raw_source=raw_source or "",
        )
        for (language, repo, sha, path, start, end, raw_source) in rows
    ]


_FETCHERS = {
    "mock_detection": (_fetch_mock_detection_candidates, ("dataset", "language")),
    "pytest_scope": (_fetch_pytest_scope_candidates, ("dataset",)),
    "unittest_detection": (_fetch_unittest_detection_candidates, ("dataset",)),
    "before_after": (_fetch_before_after_candidates, ("dataset", "language")),
}


def _build_plain_github_url(
    repo_full_name: str, commit_sha: str, file_path: str, start_line: int, end_line: int
) -> str:
    """Same shape as `corpus_utils._build_github_url()`, with `?plain=1`
    inserted before the `#L` anchor so GitHub renders the raw file as
    plain text instead of a rendered Markdown/syntax view."""
    if not repo_full_name or not commit_sha or not file_path:
        return ""
    sha = commit_sha.strip()
    if not sha:
        return ""
    path = file_path.lstrip("/")
    if start_line > 0 and end_line >= start_line:
        anchor = f"#L{start_line}-L{end_line}"
    else:
        anchor = f"#L{start_line}" if start_line > 0 else ""
    return f"https://github.com/{repo_full_name}/blob/{sha}/{path}?plain=1{anchor}"


def _slice_with_context(
    file_content: str, start_line: int, end_line: int, context: int = CONTEXT_LINES
) -> str:
    """The fixture's own lines plus `context` lines before/after,
    clamped to the file's bounds, each prefixed with its 1-indexed line
    number so the reviewer can match it against `github_url`."""
    lines = file_content.splitlines()
    if not lines or start_line <= 0:
        return file_content
    lo = max(1, start_line - context)
    hi = min(len(lines), end_line + context) if end_line >= start_line else min(len(lines), start_line + context)
    return "\n".join(f"{i}: {lines[i - 1]}" for i in range(lo, hi + 1))


def _is_python_import_line(stripped: str) -> bool:
    return stripped.startswith("import ") or stripped.startswith("from ")


def _is_js_import_line(stripped: str) -> bool:
    return stripped.startswith("import ") or "require(" in stripped


def _extract_test_related_imports(file_content: str, language: str) -> str:
    """Import/require lines whose text names a known testing-related
    package -- enough for a reviewer to identify the governing
    framework, not a full import dump. '(no test-related imports found)'
    if none match; the reviewer's own github_url is the fallback for a
    framework identified some other way (e.g. a config file)."""
    is_import_line = _is_python_import_line if language == "python" else _is_js_import_line
    keywords = (
        PYTHON_TEST_IMPORT_KEYWORDS if language == "python" else JS_TEST_IMPORT_KEYWORDS
    )
    matches = [
        stripped
        for line in file_content.splitlines()
        if is_import_line(stripped := line.strip())
        and any(keyword in stripped.lower() for keyword in keywords)
    ]
    return "; ".join(matches) if matches else "(no test-related imports found)"


def _enrich_candidate(candidate: _Candidate) -> dict[str, Any]:
    """Fetch the file once, build `source_with_context` for every case,
    and finish `detector_reported` for the two cases that need file
    content (unittest_detection, before_after) -- mock_detection and
    pytest_scope already have it from the DB-only fetch step."""
    file_content = _fetch_file_content(
        candidate.repo_full_name, candidate.commit_sha, candidate.relative_path
    )

    if file_content is not None:
        source_with_context = _slice_with_context(
            file_content, candidate.start_line, candidate.end_line
        )
    else:
        source_with_context = candidate.raw_source

    detector_reported = candidate.detector_reported
    if candidate.case == "unittest_detection":
        if file_content is not None:
            header = _find_enclosing_class_header(
                file_content, candidate.extra["method_name"], candidate.start_line
            )
            imports = _extract_test_related_imports(file_content, "python")
        else:
            header = None
            imports = "(file content unavailable)"
        class_text = header or "(module-level, no enclosing class)"
        detector_reported = f"class: {class_text} | imports: {imports}"
    elif candidate.case == "before_after":
        detector_reported = (
            _extract_test_related_imports(file_content, candidate.language)
            if file_content is not None
            else "(file content unavailable)"
        )

    return {
        "case": candidate.case,
        "dataset": candidate.dataset,
        "language": candidate.language,
        "repository": candidate.repo_full_name,
        "file_path": candidate.relative_path,
        "line_number": candidate.start_line,
        "github_url": _build_plain_github_url(
            candidate.repo_full_name,
            candidate.commit_sha,
            candidate.relative_path,
            candidate.start_line,
            candidate.end_line,
        ),
        "source_with_context": source_with_context,
        "detector_reported": detector_reported,
        "label": "",
        "notes": "",
    }


def _sample_case(
    case: str, candidates: list[_Candidate], stratify_by: tuple[str, ...], seed: int
) -> tuple[list[_Candidate], list[dict[str, Any]], bool]:
    """Stratified sample of `candidates` down to
    SAMPLE_SIZE_PER_CASE (or all of them, if fewer). Returns (sampled,
    strata_metadata, shortfall)."""
    population = len(candidates)
    shortfall = population < SAMPLE_SIZE_PER_CASE

    strata: dict[tuple[str, ...], list[_Candidate]] = {}
    for candidate in candidates:
        strata.setdefault(candidate.strata_key(stratify_by), []).append(candidate)

    strata_sizes = {key: len(items) for key, items in strata.items()}
    allocation = _allocate_stratified(strata_sizes, SAMPLE_SIZE_PER_CASE)

    sampled: list[_Candidate] = []
    strata_metadata: list[dict[str, Any]] = []
    for key in sorted(strata):
        n_k = allocation[key]
        # sample_rows() operates on dicts (content-hash sort); _Candidate
        # isn't hashable/dict-like, so sample by index over a dict view.
        as_dicts = [
            {"__index__": i, **vars(candidate)} for i, candidate in enumerate(strata[key])
        ]
        chosen = sample_rows(as_dicts, n_k, seed)
        sampled.extend(strata[key][row["__index__"]] for row in chosen)
        strata_metadata.append(
            {
                "key": dict(zip(stratify_by, key)),
                "population_size": strata_sizes[key],
                "sample_size": n_k,
            }
        )

    return sampled, strata_metadata, shortfall


def run_detector_precision_sampling(
    *,
    db_a: Path,
    db_c_sampled: Path,
    seed: int = SEED,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> list[CaseResult]:
    """Generate all four fixed-n=100 samples. Returns one CaseResult per
    case, also written to `<output_root>/sample_metadata_detector_precision_validation.json`."""
    conn_a = sqlite3.connect(db_a)
    conn_c = sqlite3.connect(db_c_sampled)
    try:
        candidates_by_case = {}
        for case, (fetcher, stratify_by) in _FETCHERS.items():
            candidates_by_case[case] = (
                fetcher(conn_a, "A") + fetcher(conn_c, "C"),
                stratify_by,
            )
    finally:
        conn_a.close()
        conn_c.close()

    results: list[CaseResult] = []
    rows_to_enrich: list[tuple[str, _Candidate]] = []
    sample_info: dict[str, tuple[list[_Candidate], list[dict[str, Any]], bool, int]] = {}

    for case, (candidates, stratify_by) in candidates_by_case.items():
        sampled, strata_metadata, shortfall = _sample_case(case, candidates, stratify_by, seed)
        sample_info[case] = (sampled, strata_metadata, shortfall, len(candidates))
        rows_to_enrich.extend((case, c) for c in sampled)
        if shortfall:
            logger.warning(
                "[Detector Precision Validation] %s: population %d < %d -- including all of it",
                case,
                len(candidates),
                SAMPLE_SIZE_PER_CASE,
            )

    with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as executor:
        enriched_rows = list(executor.map(lambda item: _enrich_candidate(item[1]), rows_to_enrich))

    rows_by_case: dict[str, list[dict[str, Any]]] = {case: [] for case in CASE_NAMES}
    for (case, _candidate), enriched in zip(rows_to_enrich, enriched_rows):
        rows_by_case[case].append(enriched)

    for case in CASE_NAMES:
        sampled, strata_metadata, shortfall, population_size = sample_info[case]
        folder, filename = CASE_OUTPUT_PATHS[case]
        step_dir = Path(output_root) / folder
        step_dir.mkdir(parents=True, exist_ok=True)
        out_path = step_dir / filename
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows_by_case[case])

        results.append(
            CaseResult(
                case=case,
                output_file=out_path,
                population_size=population_size,
                sample_size=len(sampled),
                shortfall=shortfall,
                strata=strata_metadata,
            )
        )

    metadata = {
        "seed": seed,
        "target_sample_size_per_case": SAMPLE_SIZE_PER_CASE,
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "results": [
            {
                "case": r.case,
                "output_file": str(r.output_file),
                "population_size": r.population_size,
                "sample_size": r.sample_size,
                "shortfall": r.shortfall,
                "strata": r.strata,
            }
            for r in results
        ],
    }
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "sample_metadata_detector_precision_validation.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    (output_root / "README_detector_precision_validation.md").write_text(README_TEXT, encoding="utf-8")

    for r in results:
        logger.info(
            "[Detector Precision Validation] %s: N=%d -> n=%d%s -> %s",
            r.case,
            r.population_size,
            r.sample_size,
            " (shortfall, all included)" if r.shortfall else "",
            r.output_file,
        )

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Draw fixed-n=100 manual-validation samples for mock detection, "
            "pytest scope classification, unittest detection, and bare "
            "before/after, on the final db/a.db + db/c_sampled.db datasets."
        )
    )
    parser.add_argument("--db-a", type=Path, default=paths.db_path("a"))
    parser.add_argument(
        "--db-c-sampled", type=Path, default=paths.DB_ROOT / "c_sampled.db"
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(fmt="%(message)s")
    args = build_parser().parse_args(argv)
    run_detector_precision_sampling(
        db_a=args.db_a,
        db_c_sampled=args.db_c_sampled,
        seed=args.seed,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
