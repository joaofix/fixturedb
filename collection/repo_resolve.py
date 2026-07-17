"""Resolve Dataset B's repo list from Dataset A's already-collected repos.

`discover-repos --dataset b` has no independent discovery source of its own
-- Dataset B is the within-repo human control, so its repo population is by
definition the same agent-enabled repos Dataset A already found. This module
is the one explicit, deterministic place that resolution happens, replacing
the old multi-directory fallback-glob guessing that used to live inside
`human_corpus.select_human_corpus_repositories()` (tried `fixtures-from-agents/`
under the given dir, then a project-level fallback, then `*_human_test_commit.csv`,
then a `tests_commits/` subdirectory -- four different guesses, three
different folder-name spellings). Everything downstream of this step reads a
single, already-resolved `datasets/b/repos/{lang}_repo.csv`.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .csv_adapter import get_adapter
from .logging_utils import get_logger

logger = get_logger(__name__)

_OUTPUT_FIELDNAMES = [
    "repo_name",
    "has_agent_config",
    "language",
    "stars",
    "clone_url",
    "num_contributors",
    "qc_reason",
    "matched_config_file",
    "processed_at",
    "created_at",
    "topics",
]


def _dataset_a_repos_dir(source_dir: Path) -> Path | None:
    """Find the sibling `datasets/a/repos/` directory (real `stars`/
    `num_contributors`) from whatever `source_dir` Dataset B is actually
    resolving from.

    `default_repo_source("b")` prefers `datasets/a/fixtures/repos/`, whose
    schema doesn't carry `stars`/`num_contributors` at all (see
    `resolve_dataset_b_repos`'s docstring) -- returns None when `source_dir`
    already *is* `.../a/repos/` (nothing to enrich from) or when no `a`
    ancestor is found at all (e.g. a synthetic source_dir in a test).
    """
    for parent in (source_dir, *source_dir.parents):
        if parent.name == "a":
            candidate = parent / "repos"
            return candidate if candidate != source_dir else None
    return None


def _load_repo_metadata(repos_dir: Path) -> dict[str, tuple[str, str]]:
    """Build a `{repo_name: (stars, num_contributors)}` lookup from an
    already-collected `datasets/a/repos/*.csv` directory."""
    lookup: dict[str, tuple[str, str]] = {}
    if not repos_dir.exists():
        return lookup
    for csv_path in sorted(repos_dir.glob("*.csv"), key=lambda p: p.name):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                repo_name = (row.get("repo_name") or "").strip()
                if repo_name and repo_name not in lookup:
                    lookup[repo_name] = (
                        row.get("stars") or "0",
                        row.get("num_contributors") or "0",
                    )
    return lookup


def resolve_dataset_b_repos(
    source_dir: Path | None = None,
    output_dir: Path | None = None,
    language: str | None = None,
    stratified: bool = False,
) -> dict[str, int]:
    """Read Dataset A's repo list from `source_dir` and write a normalized
    copy per language to `output_dir`.

    `source_dir` defaults to `paths.default_repo_source("b")`, which prefers
    `datasets/a/fixtures/repos/` (repos that actually yielded agent fixtures)
    over `datasets/a/repos/` (all agent-config-positive candidates) when the
    former is populated. Both source schemas share `repo_name`/`language`/
    `clone_url`; only the fixture-repos source contributes `has_agent_config`
    implicitly (every row there yielded a fixture, so it's always positive).
    The fixture-repos schema also has no `stars`/`num_contributors` columns
    at all, so those two fields are backfilled from the sibling
    `datasets/a/repos/` directory (`_load_repo_metadata`) rather than left at
    the previous silent `0` default when resolving from that source.

    `stratified=True` caps each language's rows at `sampling.cochran_sample_size`
    of that language's own real row count (95% confidence, +/-5% margin)
    instead of writing every resolved row -- used by `toy --dataset b
    --stratified` for a representative validation sample.

    Returns a dict of {language: row_count}.
    """
    source_dir = Path(source_dir) if source_dir else paths.default_repo_source("b")
    output_dir = Path(output_dir) if output_dir else paths.stage_dir("b", "repos")

    a_repos_dir = _dataset_a_repos_dir(source_dir)
    metadata_lookup = _load_repo_metadata(a_repos_dir) if a_repos_dir else {}

    by_lang: dict[str, list[dict]] = {}
    now = datetime.now(timezone.utc).isoformat()
    seen: dict[str, set[str]] = {}

    for csv_path in sorted(source_dir.glob("*.csv"), key=lambda p: p.name):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name:
                    continue
                if language and lang != language:
                    continue
                # From datasets/a/repos/: only agent-config-positive rows.
                # From datasets/a/fixtures/repos/: every row is implicitly
                # positive (it has an accepted fixture), so accept unless
                # the column says otherwise.
                has_config = str(row.get("has_agent_config", "1") or "1").strip().lower()
                if has_config not in ("1", "true"):
                    continue

                lang_seen = seen.setdefault(lang, set())
                if repo_name in lang_seen:
                    continue
                lang_seen.add(repo_name)

                fallback_stars, fallback_contributors = metadata_lookup.get(
                    repo_name, ("0", "0")
                )
                by_lang.setdefault(lang, []).append(
                    {
                        "repo_name": repo_name,
                        "has_agent_config": 1,
                        "language": lang,
                        "stars": row.get("stars") or fallback_stars,
                        "clone_url": row.get("clone_url")
                        or f"https://github.com/{repo_name}.git",
                        "num_contributors": row.get("num_contributors")
                        or fallback_contributors,
                        "qc_reason": "",
                        "matched_config_file": row.get("matched_config_file") or "",
                        "processed_at": now,
                        "created_at": row.get("created_at") or "",
                        "topics": row.get("topics") or "[]",
                    }
                )

    if not by_lang:
        raise RuntimeError(
            f"No repos resolved for dataset b from {source_dir} -- has "
            f"discover-repos/extract-fixtures --dataset a run for this root yet? "
            f"Dataset B's repo pool is by definition Dataset A's already-collected "
            f"repos, so this step depends on Dataset A having run first (for a "
            f"toy run, both datasets must use the same --dataset a toy root)."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = get_adapter()
    counts: dict[str, int] = {}
    for lang, rows in sorted(by_lang.items()):
        if stratified:
            from .sampling import cochran_sample_size

            rows = rows[: cochran_sample_size(len(rows))]
        adapter.write_dicts(
            output_dir / f"{lang}_repo.csv", rows, _OUTPUT_FIELDNAMES
        )
        counts[lang] = len(rows)

    logger.info(
        "[discover-repos b] Resolved %d repos across %d language(s) from %s -> %s",
        sum(counts.values()),
        len(counts),
        source_dir,
        output_dir,
    )
    return counts
