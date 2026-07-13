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

MIN_STARS = _STUDY_PARAMS["min_stars"]
MIN_COMMITS = _STUDY_PARAMS["min_commits"]
MIN_TEST_FILES = _STUDY_PARAMS["min_test_files"]
MIN_FIXTURES_FOUND = _STUDY_PARAMS["min_fixtures_found"]

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


def is_known_framework(framework: str, language: str) -> bool:
    """
    Check if a detected framework is in the official registry for the language.

    This is used to validate framework detection results and catch misdetections.
    Framework names are case-insensitive for comparison.

    Args:
        framework: Detected framework name (e.g., "pytest", "junit")
        language: Programming language (e.g., "python", "java")

    Returns:
        True if framework is in FRAMEWORK_REGISTRY for the language, False otherwise
    """
    if language not in FRAMEWORK_REGISTRY:
        return False

    # Normalize to lowercase for comparison
    framework_lower = framework.lower()
    known_frameworks = [f.lower() for f in FRAMEWORK_REGISTRY[language]]
    return framework_lower in known_frameworks


def get_known_frameworks(language: str) -> list[str]:
    """
    Get the list of known frameworks for a language.

    Args:
        language: Programming language (e.g., "python", "java")

    Returns:
        List of canonical framework names for the language, or empty list if language not found
    """
    return FRAMEWORK_REGISTRY.get(language, [])


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

# ---------------------------------------------------------------------------
# Pipeline collection thresholds
# ---------------------------------------------------------------------------

# Maximum iterations in balanced collection loop (safety limit)
MAX_COLLECTION_ITERATIONS = 10

# File size warning threshold in MB (log warning if file exceeds this during extraction)
FILE_SIZE_WARN_MB = 10

# ---------------------------------------------------------------------------
# Agent Detection Configuration (Two-Tier Methodology)
# ---------------------------------------------------------------------------
# Agent config-file patterns and commit signatures live in
# collection/heuristics/agent_heuristics.yaml, loaded via
# collection/agent_patterns.py (AGENT_SIGNATURES, LIGHTWEIGHT_AGENT_CONFIG_PATTERNS,
# PAPER_AGENT_CONFIG_PATTERNS) — not duplicated here. Thresholds below live in
# collection/study_parameters/study_parameters.yaml.

# Tier 1 assessment thresholds (Phase 1C)
# If Tier 1 (corpus repos) falls below these, Phase 1D (matched repo discovery) is triggered
TIER1_MINIMUM_REPOS_WITH_AGENT = _STUDY_PARAMS["tier1_minimum_repos_with_agent"]
TIER1_MINIMUM_AGENT_COMMITS = _STUDY_PARAMS["tier1_minimum_agent_commits"]

# Tier 2 matching criteria (Phase 1D: SEART-based discovery)
# Parameters for finding supplementary repos when Tier 1 insufficient
TIER2_MATCHING_MIN_STARS = _STUDY_PARAMS["tier2_matching_min_stars"]
TIER2_MATCHING_MAX_STARS = _STUDY_PARAMS["tier2_matching_max_stars"]
TIER2_MATCHING_STAR_TOLERANCE = _STUDY_PARAMS["tier2_matching_star_tolerance"]
TIER2_MIN_COMMITS = _STUDY_PARAMS["tier2_min_commits"]
TIER2_MIN_TEST_FILES = _STUDY_PARAMS["tier2_min_test_files"]
TIER2_MUST_HAVE_AGENT_CONFIGS = _STUDY_PARAMS["tier2_must_have_agent_configs"]
