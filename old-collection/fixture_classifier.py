"""
Fixture taxonomy classifier — categorizes fixtures into semantic usage patterns (RQ1 taxonomy).

This module implements a multi-level classification approach to map test fixtures into
semantic categories that represent distinct, actionable testing concerns. The taxonomy
was developed to answer RQ1: What are the primary roles/purposes of test fixtures in
real-world projects?

CLASSIFICATION APPROACH
=======================
Classification is performed in five decision-making layers, each contributing evidence
to determine fixture category membership:

    Layer 1: Keyword Pattern Matching
    --------------------------------
    Regex patterns are applied to the fixture's raw source code to detect semantic
    keywords indicative of each category. For example:
      - Keywords: 'mock', 'stub', 'spy', 'fake' → mock_setup likely
      - Keywords: 'file', 'database', 'temp', 'path' → environment likely
      - Keywords: 'create', 'build', 'construct', 'factory' → data_builder likely
    Pattern matching is case-insensitive and fast (simple regex, not AST parsing).
    See CATEGORY_KEYWORDS dict for complete keyword specifications.

    Layer 2: Mock Framework Usage Detection
    ----------------------------------------
    If the fixture uses detected mock frameworks (tracked in mock_usages table),
    mock_setup category is added to candidates.

    Layer 3: Structural Feature Heuristics
    ----------------------------------------
    Metrics extracted by the detector module provide hints:
      - num_parameters >= 2: likely service_setup (injecting dependencies)
      - num_objects_instantiated >= 3: likely data_builder (creating test data)
      - num_external_calls >= 2: likely environment (I/O, file, database operations)

    Layer 4: Scope-Based Hints
    --------------------------
    Fixture scope metadata influences classification:
      - scope ∈ {per_module, global}: add state_reset (shared state management)

    Layer 5: Complexity-Based Tiebreaker
    ------------------------------------
    High complexity (cyclomatic >= 3) without other category matches suggests
    the fixture is doing "multiple things" → hybrid.

CATEGORY DEFINITIONS (RQ1 Taxonomy)
===================================

data_builder:
    Purpose: Creates, initializes, or constructs test data structures.
    Indicators: Calls to factory methods, builder patterns, data structure construction.
    Example: "creates_user_with_profile()" — builds test user objects.

service_setup:
    Purpose: Wires dependencies, injects services, configures DI containers.
    Indicators: Multiple parameters (injected dependencies), @Provide/@Bean annotations.
    Example: "setup_service_registry()" — registers services in a container.

environment:
    Purpose: Manages external resources: files, databases, network, environment vars.
    Indicators: File I/O, database connections, temp directories, environment variables.
    Example: "temporary_database()" — creates isolated test database.

resource_management:
    Purpose: Allocates, configures, releases resources via context managers or cleanup.
    Indicators: context managers, finally blocks, open/close/acquire/release patterns.
    Example: "http_server_context()" — starts/stops a test HTTP server.

mock_setup:
    Purpose: Creates mock objects, stubs, spies for test isolation and behavior verification.
    Indicators: Direct mock framework usage (unittest.mock, pytest-mock, Jest, Mockito, etc.).
    Example: "mocked_api_client()" — creates a stub for an external API.

state_reset:
    Purpose: Resets global state, clears caches, resets databases between test runs.
    Indicators: reset(), clear(), flush(), truncate() patterns; module/global scope.
    Example: "clear_global_cache()" — empties application cache.

configuration_setup:
    Purpose: Configures application settings, environment variables, feature flags.
    Indicators: Configuration objects, environment variable assignment, feature flags.
    Example: "configured_app()" — sets up app with test configuration.

hybrid:
    Purpose: Combination of multiple categories that don't fit neatly into one.
    Triggers: Multiple categories matched at equal strength, or no category matched.
    Rationale: Complex fixtures often serve multiple purposes. Hybrid preserves visibility
              that fixture is multi-purpose but doesn't force artificial categorization.

DECISION TREE
=============
The final category is determined by:
    1. Match all keyword patterns + mock usage + structural heuristics
    2. If zero matches: return "hybrid" (unknown/underspecified)
    3. If exactly one match: return that category
    4. If multiple matches:
         - If mock_count >= 2 AND "mock_setup" is candidate: return "mock_setup"
         - If num_objects_instantiated >= 5 AND "data_builder" is candidate: return "data_builder"
         - Otherwise: return "hybrid" (genuine multi-purpose)

This tiering ensures:
    - Strong signals (e.g., heavy mocking) dominate weak signals
    - Ambiguous fixtures are marked as hybrid rather than arbitrarily assigned
    - Classification remains interpretable: humans can verify based on explicit rules

USAGE
=====
    from collection.fixture_classifier import categorize_all, _classify_fixture

    # Batch categorize all uncategorized fixtures
    counts = categorize_all()
    print(f"Categorized: {counts}")

    # Manually categorize a single fixture
    category = _classify_fixture(
        fixture_id=123,
        fixture_type="function",
        scope="function",
        loc=10,
        cyclomatic_complexity=1,
        num_objects_instantiated=2,
        num_external_calls=0,
        num_parameters=1,
        raw_source="@pytest.fixture\\ndef setup_test(): return build_obj()",
        mock_count=0
    )
    print(f"Category: {category}")
"""

import logging
import re
from collection.db import db_session
from collection.config import (
    OBJECTS_DATA_BUILDER_THRESHOLD,
    OBJECTS_PARAMETRIZED_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword patterns for each category
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "mock_setup": [
        r"\bmock\b",
        r"\bstub\b",
        r"\bspy\b",
        r"\bfake\b",
        r"mockito",
        r"easymock",
        r"unittest_mock",
        r"pytest_mock",
        r"jest\.mock",
        r"jest\.spyOn",
        r"sinon\.stub",
        r"testify",
        r"gomock",
        r"moq",
        r"nsubstitute",
        r"create(Mock|Stub|Spy)",
        r"\.when\(",
        r"\.thenReturn",
        r"\.thenThrow",
        r"\.verify\(",
        r"setupMock",
        r"prepareMock",
    ],
    "data_builder": [
        r"\bcreate\b",
        r"\bbuild\b",
        r"\bconstruct\b",
        r"\bnew \w+\(",
        r"factory",
        r"builder",
        r"fixture",
        r"\.add\(",
        r"\.append\(",
        r"\.put\(",
        r"\.set\(",
        r"testdata",
        r"test_data",
        r"sample",
        r"prepare_data",
        r"create_.*objects?",
        r"build_.*objects?",
    ],
    "service_setup": [
        r"\binject\b",
        r"\bwire\b",
        r"\bbind\b",
        r"\bprovide\b",
        r"dependenc",
        r"container",
        r"registry",
        r"factory\.create",
        r"\.register\(",
        r"\.bind\(",
        r"setUp.*service",
        r"setupModule",
        r"initializeService",
    ],
    "environment": [
        r"\bfile\b",
        r"\bfolder\b",
        r"\bdirectory\b",
        r"\bdatabase\b",
        r"\bdb\b",
        r"\btemp\b",
        r"\btmp\b",
        r"\bpath\b",
        r"tempfile",
        r"tempdir",
        r"tmpdir",
        r"sqlite",
        r"connection",
        r"\.create\(\)",
        r"\.mkdir\(",
        r"\.chdir\(",
        r"os\.",
        r"tempfile\.",
        r"pathlib\.",
        r"filesystem",
    ],
    "resource_management": [
        r"\bopen\(",
        r"\bclose\(",
        r"\bconnect\(",
        r"\bdisconnect\(",
        r"\bacquire\(",
        r"\brelease\(",
        r"\byield\b",
        r"\bwith\b",
        r"context_?manager",
        r"transaction",
        r"cleanup",
        r"teardown",
        r"shutdown",
        r"\.close\(\)",
        r"finally:",
    ],
    "state_reset": [
        r"\breset\b",
        r"\bclear\b",
        r"\bclean\b",
        r"\brestore\b",
        r"\bflush\b",
        r"\btruncate\b",
        r"reset.*state",
        r"clear.*cache",
        r"clear.*data",
        r"cleanup",
        r"\.reset\(",
        r"\.clear\(",
        r"\.flush\(",
        r"deleteAll",
        r"drop_all",
    ],
    "configuration_setup": [
        r"\bconfig\b",
        r"\bsetting\b",
        r"\benv\b",
        r"\bfeature\b",
        r"\bflag\b",
        r"\bproperty\b",
        r"\bconfigur",
        r"environment_?variable",
        r"os\.environ",
        r"dotenv",
        r"config\.set",
        r"setProperty",
        r"setEnvironment",
        r"setup.*configuration",
        r"initialize.*config",
        r"set.*flag",
        r"enable.*feature",
    ],
}

# ---------------------------------------------------------------------------
# Categorization logic
# ---------------------------------------------------------------------------


def _classify_fixture(
    fixture_id: int,
    fixture_type: str,
    scope: str,
    loc: int,
    cyclomatic_complexity: int,
    num_objects_instantiated: int,
    num_external_calls: int,
    num_parameters: int,
    raw_source: str,
    mock_count: int,
) -> str:
    """
    Categorize a single fixture using heuristics based on structure and content.
    Returns one of the category labels.
    """
    if not raw_source:
        return "hybrid"  # default if no source available

    source_lower = raw_source.lower()
    matched_categories = set()

    # 1. Check keyword patterns in raw_source
    for category, keywords in CATEGORY_KEYWORDS.items():
        for pattern in keywords:
            if re.search(pattern, source_lower, re.IGNORECASE):
                matched_categories.add(category)
                break

    # 2. Check for mocks in mock_usages table
    if mock_count > 0:
        matched_categories.add("mock_setup")

    # 3. Structural heuristics
    if num_parameters >= 2:
        matched_categories.add("service_setup")
    if num_objects_instantiated >= 3:
        matched_categories.add("data_builder")
    if num_external_calls >= 2:
        matched_categories.add("environment")

    # 4. Scope-based hints
    if scope in ("per_module", "global"):
        matched_categories.add("state_reset")

    # 5. Complexity heuristics
    if cyclomatic_complexity >= 3:
        # More complex fixtures often do multiple things
        if len(matched_categories) == 0:
            matched_categories.add("hybrid")

    # Decision logic: pick single best category or "hybrid"
    if len(matched_categories) == 0:
        return "hybrid"
    elif len(matched_categories) == 1:
        return list(matched_categories)[0]
    else:
        # Multiple categories matched -> check for dominance
        # If mock_setup is strong (lots of mock calls), it wins
        if mock_count >= 2 and "mock_setup" in matched_categories:
            return "mock_setup"
        # If it looks like a builder (lots of object instantiation), it wins
        if (
            num_objects_instantiated >= OBJECTS_DATA_BUILDER_THRESHOLD
            and "data_builder" in matched_categories
        ):
            return "data_builder"
        # Otherwise, it's genuinely hybrid
        return "hybrid"


def categorize_all(overwrite: bool = False) -> dict[str, int]:
    """
    Categorize all fixtures that have no category label yet.
    If overwrite=True, re-categorize all fixtures including already-categorized ones.
    Returns a count dict {category: n}.
    """
    counts: dict[str, int] = {}

    with db_session() as conn:
        if overwrite:
            query = """
                SELECT f.id, f.fixture_type, f.scope, f.loc, f.cyclomatic_complexity,
                       f.num_objects_instantiated, f.num_external_calls, f.num_parameters,
                       f.raw_source, COALESCE(COUNT(m.id), 0) as mock_count
                FROM fixtures f
                LEFT JOIN mock_usages m ON f.id = m.fixture_id
                GROUP BY f.id
            """
        else:
            query = """
                SELECT f.id, f.fixture_type, f.scope, f.loc, f.cyclomatic_complexity,
                       f.num_objects_instantiated, f.num_external_calls, f.num_parameters,
                       f.raw_source, COALESCE(COUNT(m.id), 0) as mock_count
                FROM fixtures f
                LEFT JOIN mock_usages m ON f.id = m.fixture_id
                WHERE f.category IS NULL
                GROUP BY f.id
            """

        rows = conn.execute(query).fetchall()
        logger.info(f"Categorizing {len(rows)} fixtures …")

        for row in rows:
            category = _classify_fixture(
                fixture_id=row["id"],
                fixture_type=row["fixture_type"],
                scope=row["scope"],
                loc=row["loc"],
                cyclomatic_complexity=row["cyclomatic_complexity"],
                num_objects_instantiated=row["num_objects_instantiated"],
                num_external_calls=row["num_external_calls"],
                num_parameters=row["num_parameters"],
                raw_source=row["raw_source"],
                mock_count=row["mock_count"],
            )
            conn.execute(
                "UPDATE fixtures SET category = ? WHERE id = ?",
                (category, row["id"]),
            )
            counts[category] = counts.get(category, 0) + 1

    logger.info(f"Fixture categorization done: {counts}")
    return counts
