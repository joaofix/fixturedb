"""
Central configuration for the fixture corpus collection pipeline.
Edit this file to tune search parameters before a collection run.

Reference data is not hardcoded here -- it lives as YAML in two places:
- collection/study_parameters/: settings and study-design constants
  (non-code file extensions, testing-framework registry, per-language
  search/detection settings, temporal boundaries, quality thresholds,
  sampling parameters).
- collection/heuristics/: detection-heuristic catalogs (pattern/keyword
  tables driving a classification decision) -- boilerplate-repo exclusion
  keywords, plus agent/fixture/mock detection (loaded directly by their
  own consumer modules, not here).
Edit the YAML to update a catalog; no Python change needed.
"""

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from .heuristics import load_exclusion_keywords
from .study_parameters import (
    load_framework_registry,
    load_language_configs_data,
    load_non_code_extensions,
    load_study_parameters,
)

load_dotenv()

_STUDY_PARAMS = load_study_parameters()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).parent.parent
CLONES_DIR = ROOT_DIR / "clones"  # temporary, deleted after extraction
# Secondary/bootstrap SQLite databases (per-dataset DBs live in db/{a,b,c}.db,
# see collection/paths.py -- this is only corpus.db and the older
# paired-study/between-group bootstrap DBs).
DB_DIR = ROOT_DIR / "db"
DB_PATH = DB_DIR / "corpus.db"

# ---------------------------------------------------------------------------
# Collection run label
# ---------------------------------------------------------------------------
# Tag used to version collection output subfolders (e.g. v2-pure-addition-2026-06).
# Set to empty string to write directly to root output directories (no versioning).
COLLECTION_OUTPUT_TAG = ""
LOGS_DIR = ROOT_DIR / "logs"

# ---------------------------------------------------------------------------
# Temporal boundaries, quality thresholds, and sampling parameters for the
# between-group comparison methodology -- values live in
# collection/study_parameters/study_parameters.yaml (see that file's header);
# Dataset C's min-created-date reasoning is in internal-docs/methodology-
# improvements/dataset-c-repo-selection.md.
# ---------------------------------------------------------------------------

HUMAN_CORPUS_CUTOFF_DATE = _STUDY_PARAMS["human_corpus_cutoff_date"]
AGENT_CORPUS_START_DATE = _STUDY_PARAMS["agent_corpus_start_date"]
DATASET_C_MIN_CREATED_DATE = _STUDY_PARAMS["dataset_c_min_created_date"]
SHALLOW_CLONE_BUFFER_DAYS = _STUDY_PARAMS["shallow_clone_buffer_days"]


def shallow_clone_since(since_date: str) -> str:
    """ISO date to pass as --shallow-since for a clone that only needs
    history from since_date onward: since_date minus a defensive buffer
    (see _shallow_clone_is_truncated for why any residual risk is caught
    regardless of buffer size -- this is just cheap extra slack)."""
    buffered = date.fromisoformat(since_date) - timedelta(days=SHALLOW_CLONE_BUFFER_DAYS)
    return buffered.isoformat()

MIN_STARS = _STUDY_PARAMS["min_stars"]
MIN_COMMITS = _STUDY_PARAMS["min_commits"]
# Companion threshold to LanguageConfig.test_path_patterns/test_file_suffixes
# above -- what counts as a "test file" is that catalog + is_test_file_path()
# (collection/test_commit_utils.py); this is just the "how many" floor,
# enforced post-clone by persistent_clone.py::_count_test_files().
MIN_TEST_FILES = _STUDY_PARAMS["min_test_files"]
MIN_FIXTURES_FOUND = _STUDY_PARAMS["min_fixtures_found"]
MIN_NON_BLANK_LOC = _STUDY_PARAMS["min_non_blank_loc"]  # Dataset C only

# Agent configuration files are defined in `collection/agent_patterns.py` as
# explicit pattern lists (with wildcard and directory markers) and imported by
# detection modules. Keep patterns centralized in `agent_patterns.py` to avoid
# duplication and preserve explicit, readable patterns.

TARGET_REPOS_PER_LANGUAGE_BETWEEN_GROUP = _STUDY_PARAMS[
    "target_repos_per_language_between_group"
]

for _d in (CLONES_DIR, DB_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

# Optional: GitHub token for API rate limit relief during cloning pre-checks
# (not required for core functionality; pre-checks fail gracefully without it)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # set in .env

# Dataset C sampling seed (default lives in study_parameters.yaml, overridable via env)
DATASET_C_SAMPLING_SEED = int(
    os.getenv("DATASET_C_SAMPLING_SEED", str(_STUDY_PARAMS["dataset_c_sampling_seed"]))
)

# ---------------------------------------------------------------------------
# File size and type filters
# ---------------------------------------------------------------------------

# Maximum file size to process (5 MB)
# Test files should never exceed this. Files larger are likely generated code,
# data files, or corrupted blobs. Prevents consuming excessive memory with
# large binary files or generated test data.
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Non-source-code file extensions to skip (resource files, data, config, etc.)
# See collection/study_parameters/non_code_extensions.yaml for the full catalog.
NON_CODE_EXTENSIONS = set(load_non_code_extensions())

# ---------------------------------------------------------------------------
# Repository search filters
# ---------------------------------------------------------------------------

# Minimum repository star floor used by language configs and discovery filters.
# (Defined in the between-group section above)


@dataclass
class LanguageConfig:
    """Per-language search and detection configuration."""

    name: str  # human-readable
    github_language: str  # label used by GitHub search API
    min_stars: int = MIN_STARS
    full_target: int = 500  # target count for full production dataset

    # test_path_patterns/test_file_suffixes below are the catalog -- data
    # only, no matching logic here, same split as AGENT_SIGNATURES/
    # agent_heuristics.yaml further down this file. The plain-string (not
    # regex) boundary-aware matching that interprets these entries lives in
    # is_test_file_path() (collection/test_commit_utils.py) -- the single
    # canonical "is this a test file" definition, reused for fixture-
    # extraction candidacy, commit purity gating, and Dataset C's own
    # file-language detection. MIN_TEST_FILES below is the companion
    # threshold ("how many test files must a repo have").

    # Paths that signal "this is a test file"
    test_path_patterns: list[str] = field(default_factory=list)

    # File name suffixes that signal a test file
    test_file_suffixes: list[str] = field(default_factory=list)

    # Keywords whose presence in repo name/description signals a non-research repo
    exclusion_keywords: list[str] = field(default_factory=lambda: EXCLUSION_KEYWORDS)


# ---------------------------------------------------------------------------
# Star tier thresholds
#
# Repos are tagged at collection time as 'core' (≥500 stars, comparable to
# Hamster's selection criterion) or 'extended' (100–499 stars, adds diversity).
# Both tiers are collected; analyses can be stratified or filtered by tier.
#
# Literature reference:
#   Hamster (arXiv:2509.26204) uses ≥500 stars + organisational ownership.
#   Studies using ≥1000 stars claim "influential project" comparability.
#   This project uses a 500-star floor as the quality minimum for discovery.
# ---------------------------------------------------------------------------


# See collection/heuristics/exclusion_keywords.yaml for the full catalog.
EXCLUSION_KEYWORDS: list[str] = load_exclusion_keywords()


# ---------------------------------------------------------------------------
# Per-language targets
#
# target_repos is the gold-standard final count: repositories with status='analysed'
# AND at least one extracted fixture. The `collect` command loops until this target
# is reached for each language.
#
# JavaScript and TypeScript targets are lower because many such repos are
# frontend-only and yield few or no fixture definitions.
# ---------------------------------------------------------------------------

LANGUAGE_CONFIGS = {
    lang: LanguageConfig(**fields)
    for lang, fields in load_language_configs_data().items()
}

# ---------------------------------------------------------------------------
# Testing Framework Registry
#
# Authoritative mapping of testing frameworks per language.
# Used to validate detected frameworks and ensure consistency.
# Categories: unit, integration, bdd, mocking
#
# This registry supports:
# 1. Validation of detected frameworks (catch typos/misspellings)
# 2. Documentation of known frameworks for each language
# 3. Consistency across analyses (canonical names)
# 4. Future enhancement: generating detection patterns from registry
# ---------------------------------------------------------------------------

# See collection/study_parameters/framework_registry.yaml for the full catalog.
FRAMEWORK_REGISTRY = load_framework_registry()

# Clone batch size (used by `clone` command for incremental cloning)
CLONE_BATCH_SIZE = 50

# Number of parallel clone workers
CLONE_WORKERS = 12

# Number of parallel extraction workers (balanced for SQLite single-writer limit)
# SQLite has a single-writer limitation; only one transaction can write at a time.
# With 20-retry aggressive backoff policy (exponential: 0.5s, 1s, 2s, 4s...),
# 8 workers is safe and provides excellent parallelism on multi-core machines.
# The retry mechanism handles lock contention automatically.
EXTRACT_WORKERS = 8

# Maximum time to spend extracting fixtures from a single test file (seconds)
# Files that exceed this timeout are skipped to prevent pathological cases
# (e.g., minified code, massive auto-generated test files, etc.)
FILE_EXTRACTION_TIMEOUT = 180  # 3 minutes

# Maximum time to spend on a single ephemeral `git clone` (seconds) --
# temp_clone_commit_history()'s default, used by test_commit_filter.py and
# human_test_commit_filter.py. Raised from 300s -> 600s 2026-08-12: with
# clone concurrency now throttled (see ephemeral_clone.py's
# _CLONE_SEMAPHORE), the remaining timeout failures are genuine large-repo
# outliers (e.g. skforecast/skforecast, ~1GB) rather than bandwidth
# contention, and 300s wasn't enough runway even alone.
CLONE_TIMEOUT_SECONDS = 600  # 10 minutes

# ---------------------------------------------------------------------------
# Pipeline collection thresholds
# ---------------------------------------------------------------------------

# Maximum iterations in balanced collection loop (safety limit)
MAX_COLLECTION_ITERATIONS = 10

# File size warning threshold in MB (log warning if file exceeds this during extraction)
FILE_SIZE_WARN_MB = 10

# ---------------------------------------------------------------------------
# Agent Detection Configuration
# ---------------------------------------------------------------------------
# Agent config-file patterns and commit signatures live in
# collection/heuristics/agent_heuristics.yaml, loaded via
# collection/agent_patterns.py (AGENT_SIGNATURES, LIGHTWEIGHT_AGENT_CONFIG_PATTERNS,
# PAPER_AGENT_CONFIG_PATTERNS) — not duplicated here.
