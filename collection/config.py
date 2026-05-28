"""
Central configuration for the fixture corpus collection pipeline.
Edit this file to tune search parameters before a collection run.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).parent.parent
CLONES_DIR = ROOT_DIR / "clones"  # temporary, deleted after extraction
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "corpus.db"
LOGS_DIR = ROOT_DIR / "logs"

# ---------------------------------------------------------------------------
# Temporal boundaries for between-group comparison methodology
# ---------------------------------------------------------------------------

# Between-group methodology uses different boundaries
# Human corpus: fixtures from pre-2021 repositories (before agent era)
HUMAN_CORPUS_CUTOFF_DATE = "2020-12-31"

# Agent corpus: fixtures from 2025+ repositories with agent commits
AGENT_CORPUS_START_DATE = (
    "2025-01-01"
)

# Quality thresholds for corpus filtering (same for both)
# Project minimum star floor for repository quality filtering
MIN_STARS = 500
MIN_COMMITS = 100
MIN_TEST_FILES = 5

# Agent configuration files are defined in `collection/agent_patterns.py` as
# explicit pattern lists (with wildcard and directory markers) and imported by
# detection modules. Keep patterns centralized in `agent_patterns.py` to avoid
# duplication and preserve explicit, readable patterns.

# Target repositories per language (NEW: between-group design)
TARGET_REPOS_PER_LANGUAGE_BETWEEN_GROUP = 500

for _d in (CLONES_DIR, DATA_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

# Optional: GitHub token for API rate limit relief during cloning pre-checks
# (not required for core functionality; pre-checks fail gracefully without it)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # set in .env

# ---------------------------------------------------------------------------
# File size and type filters
# ---------------------------------------------------------------------------

# Maximum file size to process (5 MB)
# Test files should never exceed this. Files larger are likely generated code,
# data files, or corrupted blobs. Prevents consuming excessive memory with
# large binary files or generated test data.
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Non-source-code file extensions to skip (resource files, data, config, etc.)
# These are checked to avoid parsing non-code files that slipped through name/path filters.
NON_CODE_EXTENSIONS = {
    # Document & markup formats
    ".txt",
    ".md",
    ".rst",
    ".pdf",
    ".docx",
    ".xhtml",
    # Data formats
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".sql",
    ".properties",
    ".dat",
    ".ttl",  # Turtle RDF files
    ".pdb",
    ".osm",  # OpenStreetMap data
    # Web assets
    ".html",
    ".css",
    ".scss",
    ".less",
    # Images
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".tga",
    ".ivf",
    ".gbk",
    # Audio & Video
    ".mp3",
    ".ogg",
    ".wav",
    ".flac",
    ".aac",
    ".m4a",
    ".wma",
    ".opus",
    ".aiff",
    ".alac",
    ".ape",
    ".mp4",
    # Fonts
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    # Build/Config artifacts
    ".map",
    ".lock",
    ".yarn",
    ".log",
    ".out",
    ".tmp",
    ".dot",  # Graph visualization
    # Geospatial files
    ".geom",
    ".shp",
    # Models & ML
    ".mlmodel",
    # Bioinformatics
    ".fasta",
    ".fax",
    ".sam",
    ".req",
    # Build dependency cache
    ".bd.fast",
    ".bd.fasta",
    ".bd",
    # Databases
    ".db",
    ".dbf",
    # C# / .NET ecosystem
    ".gucx",
    ".gusx",
    ".resx",
    ".xaml",
    ".csproj",
    ".vbproj",
    ".sln",
    ".nuspec",
    ".props",
    ".targets",
    ".ruleset",
    ".editorconfig",
    # Game engine files (Unity)
    ".unity",
    ".prefab",
    ".anim",
    ".controller",
    ".mat",
    ".asset",
    ".uxml",
    # Compressed archives
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".iso",
    ".dmg",
    # Programming/Analysis formats
    ".flf",
    ".il",
    ".snapshot",
    ".raw",
    ".tokens",
    # Test fixtures and snapshots
    ".golden",
    ".snap",
    ".input",
    ".expected",
    ".actual",
    # Windows
    ".exe",
    ".msi",
    ".dll",
    # Unix
    ".so",
    ".dylib",  # macOS dynamic libraries
    # Mobile
    ".apk",
    ".aar",  # Android archive library
    # Java archives
    ".jar",
    ".war",
    ".ear",
    # Speech recognition
    ".srx",
}

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


EXCLUSION_KEYWORDS = [
    "tutorial",
    "course",
    "homework",
    "exercise",
    "demo",
    "example",
    "sample",
    "workshop",
    "bootcamp",
    "learning",
    "practice",
    "beginner",
    "awesome-",
    "cheatsheet",
    "interview",
    "leetcode",
    "hackerrank",
]

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
    "python": LanguageConfig(
        name="Python",
        github_language="Python",
        min_stars=MIN_STARS,
        full_target=500,
        test_path_patterns=["test/", "tests/", "testing/"],
        test_file_suffixes=["test_.py", "_test.py", "_tests.py", "conftest.py"],
    ),
    "java": LanguageConfig(
        name="Java",
        github_language="Java",
        min_stars=MIN_STARS,
        full_target=500,
        test_path_patterns=["src/test/", "test/", "tests/"],
        test_file_suffixes=["Test.java", "Tests.java", "IT.java", "Spec.java"],
    ),
    "javascript": LanguageConfig(
        name="JavaScript",
        github_language="JavaScript",
        min_stars=MIN_STARS,
        full_target=250,
        test_path_patterns=["test/", "tests/", "spec/", "__tests__/"],
        test_file_suffixes=[
            ".test.js",
            ".spec.js",
            "test.js",
            ".test.jsx",
            ".spec.jsx",
            ".test.mjs",
            ".spec.mjs",
        ],
    ),
    "typescript": LanguageConfig(
        name="TypeScript",
        github_language="TypeScript",
        min_stars=MIN_STARS,
        full_target=250,
        test_path_patterns=["test/", "tests/", "spec/", "__tests__/"],
        test_file_suffixes=[
            ".test.ts",
            ".spec.ts",
            "test.ts",
            ".test.tsx",
            ".spec.tsx",
            ".test.mts",
            ".spec.mts",
        ],
    ),
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

FRAMEWORK_REGISTRY = {
    "python": [
        # Unit testing frameworks
        "pytest",  # Most popular, decorator-based
        "unittest",  # Standard library
        "nose",  # Legacy discovery-based
        "nose2",  # Modernized nose
        "doctest",  # Docstring-based
        # BDD frameworks
        "behave",  # Gherkin syntax
        "pytest-bdd",  # BDD with pytest
        # Mocking frameworks (detected in fixtures)
        "unittest_mock",  # Standard library mocking
        "pytest_mock",  # Pytest-style mocking
        # Async testing
        "pytest-asyncio",  # Async fixtures
        # Other frameworks
        "testtools",  # Extended assertions
        "trial",  # Twisted async testing
    ],
    "java": [
        # Unit testing frameworks
        "junit",  # JUnit 3/4/5 (captured as generic "junit")
        "testng",  # Annotations-based
        # BDD frameworks
        "spock",  # Groovy-based BDD
        "cucumber",  # Gherkin syntax
        # Mocking frameworks (detected in fixtures)
        "mockito",  # Primary Java mocking framework
        "easymock",  # Legacy Java mocking
        "powermock",  # Extension to Mockito
        # Specialized
        "testify",  # Custom framework
        "jtest",  # Genetic programming testing
        "arquillian",  # Container testing
    ],
    "javascript": [
        # Unit testing frameworks
        "jest",  # Snapshot and coverage built-in
        "mocha",  # Most flexible, often paired with chai
        "jasmine",  # Behavior-driven
        "ava",  # Concurrent test runner
        "vitest",  # Vite-native test runner
        # BDD frameworks
        "cucumber",  # Gherkin syntax
        # Mocking/stubbing (detected in fixtures)
        "sinon",  # Spies, stubs, mocks (often with mocha/jasmine)
        # Testing utilities
        "tap",  # Test Anything Protocol
        "uvu",  # Lightweight test runner
        "node-tap",  # TAP version for Node
    ],
    "typescript": [
        # Unit testing frameworks (TypeScript-native)
        "jest",  # With @types/jest
        "mocha",  # With typescript plugin
        "jasmine",  # TypeScript support
        "vitest",  # Vite-native with TypeScript
        "ava",  # With TypeScript support
        # BDD frameworks
        "cucumber",  # With TypeScript support
        # Mocking (detected in fixtures)
        "sinon",  # Works with TypeScript
    ],
}

# Minimum thresholds applied after cloning
MIN_TEST_FILES = 5  # repos with fewer test files are dropped
MIN_COMMITS = 100  # repos with fewer commits are dropped
MIN_FIXTURES_FOUND = 1  # repos where we detect zero fixtures are dropped
MIN_FIXTURES_FOUND = 1  # repos where we detect zero fixtures are dropped

# Per-language survival rates (discovered → analyzed with fixtures)
# These are empirically observed rates used to calculate discovery estimates.
# They are updated as we collect data for each language.
# Format: {language: survival_rate}
LANGUAGE_SURVIVAL_RATES = {
    "python": 0.076,  # 7.6% actual from completed collection
    "java": 0.15,  # estimate (Java typically has higher survival)
    "javascript": 0.08,  # estimate
    "typescript": 0.08,  # estimate
}

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

# Fixture complexity thresholds for fixture categorization
# Data builder: repos with many objects instantiated (likely factory pattern)
OBJECTS_DATA_BUILDER_THRESHOLD = 5
# Parametrized fixtures: repos with moderate reuse/complexity
OBJECTS_PARAMETRIZED_THRESHOLD = 2

# ---------------------------------------------------------------------------
# Agent Detection Configuration (Two-Tier Methodology)
# ---------------------------------------------------------------------------

# Agent configuration file patterns (used in Phase 1A/1D for agent activity detection)
AGENT_CONFIG_PATTERNS = {
    "claude": [
        "CLAUDE.md",
        ".claudeignore",
        ".claude/",
        "anthropic/",
    ],
    "cursor": [
        "CURSOR.md",
        ".cursor/",
        ".cursorrules",
    ],
    "copilot": [
        "copilot_instructions.md",
        "copilot-instructions.md",
        ".copilot-instructions.md",
        ".copilot-*.md",
        ".copilotignore",
        ".copilot/",
    ],
}

# Agent signature patterns for commit author/message detection
# Used in Phase 1B to verify Co-authored-by trailers
AGENT_SIGNATURES = {
    "claude": ["claude", "anthropic"],
    "cursor": ["cursor"],
    "copilot": ["copilot", "github.com/apps/github-copilot"],
    "github-actions": ["github-actions[bot]", "github-actions"],
    "other": [
        "aider",
        "openhands",
        "devin",
        "jules",
        "cline",
        "junie",
        "gemini",
        "coderabbit",
        "windsurf",
    ],
}

# Tier 1 assessment thresholds (Phase 1C)
# If Tier 1 (corpus repos) falls below these, Phase 1D (matched repo discovery) is triggered
TIER1_MINIMUM_REPOS_WITH_AGENT = 30  # minimum repos needed from corpus
TIER1_MINIMUM_AGENT_COMMITS = 100  # minimum agent commits needed from corpus

# Tier 2 matching criteria (Phase 1D: SEART-based discovery)
# Parameters for finding supplementary repos when Tier 1 insufficient
TIER2_MATCHING_MIN_STARS = 50  # lower bound for matched repos
TIER2_MATCHING_MAX_STARS = 50000  # upper bound for matched repos
TIER2_MATCHING_STAR_TOLERANCE = 2.0  # allow repos within 2x star count of corpus median
TIER2_MIN_COMMITS = 100  # matched repos must have >= commits
TIER2_MIN_TEST_FILES = 5  # matched repos must have >= test files
TIER2_MUST_HAVE_AGENT_CONFIGS = True  # matched repos MUST have agent config files
