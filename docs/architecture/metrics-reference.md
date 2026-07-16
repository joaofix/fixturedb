# Metrics Reference

Per-metric calculation methodology for every quantitative field FixtureDB records for a detected
fixture (`collection/detector_shared.py::FixtureResult`). For the detection pipeline itself (how a
fixture is found in the first place), see [detection.md](detection.md).

## At a Glance

| Metric | Tool / Method | Implementation | Languages |
|--------|--------------|-----------------|-----------|
| `cyclomatic_complexity` | Lizard | `complexity_provider.py::analyze_function_complexity()` | all |
| `num_parameters` | Lizard, self/cls stripped for Python | `complexity_provider.py` + `detector_shared.py::_build_result()` | all |
| `max_nesting_depth` | Custom tree-sitter traversal | `detector_shared.py::_compute_nesting_depth()` | all |
| `loc` | Non-blank line count | `detector_shared.py::_count_loc()` | all |
| `num_objects_instantiated` | Regex (constructor patterns) | `complexity_provider.py::_count_object_instantiations()` | all |
| `num_external_calls` | Regex (I/O patterns) | `detector_shared.py::_count_external_calls()` | all |
| `fixture_type`, `framework`, `scope` | AST pattern match vs. `fixture_definitions.yaml` | `detector_python.py` / `detector_java.py` / `detector_javascript.py` | all |
| `has_teardown_pair` | Post-processing, paired against sibling fixtures | `detector_shared.py::_calculate_teardown_pairs()` | all |
| `fixture_dependencies` | Post-processing, parameter-injection matching | `detector_shared.py::_detect_fixture_dependencies()` | Python/pytest only |
| `num_mocks`, `mocks` | Regex (mock-framework patterns) | `detector_shared.py::_extract_mocks()` | all |
| `raw_source`, `start_line`, `end_line` | Verbatim text/location of the fixture's own node | `detector_shared.py::_build_result()` | all |

All regex catalogs (I/O patterns, constructor patterns, mock patterns, teardown-pairing rules) live in
[feature_extraction_patterns.yaml](../../collection/heuristics/feature_extraction_patterns.yaml), not
hardcoded in Python — see [configuration.md](configuration.md#reference-data-catalogs).

---

## External Tools

### Lizard

Provides `cyclomatic_complexity` and a raw parameter/external-call count, run once per fixture against
that fixture's own isolated source text (not the whole file) via a temp-file round trip in
`analyze_function_complexity()`. On parse failure it returns safe defaults
(`cyclomatic_complexity=1`, `num_parameters=0`) rather than raising — verified against inputs Lizard
can't fully contextualize (a bare Java method with no enclosing class, a Java field declaration that
isn't a function at all) without crashing.

> McCabe, T. J. (1976). "A Complexity Measure." *IEEE Transactions on Software Engineering*, 2(4), 308–320.

### Tree-sitter

Parses every file into an AST once; fixture detection, scope classification, and `max_nesting_depth`
are all derived from that same tree. The whole pipeline reads source as bytes and only decodes
per-fixture slices at the end (UTF-8, `errors="replace"`) — verified that multi-byte UTF-8 content
elsewhere in the file does not shift line numbers or fixture boundaries; non-UTF-8 files degrade
gracefully (structural detection stays correct, non-ASCII text inside comments/strings is replaced).
Tree-sitter never raises on malformed/incomplete source (it produces error nodes instead), so a
syntax error elsewhere in a file does not prevent detection of an otherwise well-formed fixture.

---

## Custom Metrics

### max_nesting_depth

Maximum nesting level of control structures (if/for/while/try) inside the fixture's own body, via a
tree-sitter traversal that increments a counter at each control-construct node type
(`if_statement`, `while_statement`, `for_statement`, `try_statement`, `with_statement`, etc.).

The compound statement's own body-wrapper node (`"block"` in Python/Java's tree-sitter grammars) and
Java's `catch_clause`/`finally_clause` are not counted as their own extra level — only the enclosing
statement is. A flat function reports 1, one level of `if` reports 2. Regression tests with exact
(not lower-bound) assertions: `tests/collection/test_extractor_metadata/test_new_metrics.py::TestMaxNestingDepth`.

### num_objects_instantiated

Regex count of constructor-call patterns: `new ClassName(...)` (with optional generics, e.g.
`new ArrayList<Foo>()`, and dotted/namespaced constructors, e.g. `new java.util.ArrayList()` or
`new THREE.Vector3()`) for Java/JS/TS, and a capitalized-call heuristic (`ClassName(...)`) for Python.
The count is capped at Lizard's own external-call count to avoid overcounting.

Pattern catalog: `feature_extraction_patterns.yaml`'s `object_instantiation_patterns`.

**Known limitation:** the Python heuristic (capitalization) may miss lowercase-named classes or
factory functions, and doesn't distinguish library classes from user-defined ones.

### num_external_calls

Regex count of I/O/system-operation markers (file: `open(`, `Path(`; database: `query(`, `.connect()`;
HTTP: `requests.`, `.get()`; subprocess/network/environment variables). This is deliberately narrower
than Lizard's own external-call count, which counts every inter-function call regardless of whether
it's I/O.

**Known limitation:** regex-based, so it can miss uncommon I/O idioms (custom DB wrappers) or
false-positive on a string literal that happens to contain a matched substring.

### num_parameters

Lizard's parameter count, with one Python-specific correction: Lizard counts a method's implicit
`self`/`cls` as an ordinary parameter, which would inflate `num_parameters` by 1 for essentially every
unittest/pytest-class-method fixture relative to a bare pytest_decorator function or an
equivalent Java/JS fixture (neither of which has an implicit first parameter). For Python,
`num_parameters` is computed by reading each parameter's own AST node directly
(`_extract_parameter_names()`) and excluding `self`/`cls`, instead of using Lizard's raw count.

### fixture_type, framework, scope

Deterministic AST pattern matching against `fixture_definitions.yaml`'s per-language tables — same
source always produces the same classification, no heuristics involved. `scope` is one of `per_test`,
`per_class`, `per_module` (Python-only), `global`, mapped from explicit framework syntax (pytest's
`scope=` keyword, Java/JS's annotation or hook name). Full per-framework mapping and known ambiguities
(e.g. `@BeforeClass` is shared syntax between JUnit4 and TestNG — scope is correct regardless, but the
two frameworks can't always be told apart from the annotation alone): [fixture-patterns-reference.md](../usage/fixture-patterns-reference.md).

### has_teardown_pair

Binary indicator that a fixture has a paired cleanup counterpart, computed in a post-processing pass
over the whole fixture list (`_calculate_teardown_pairs()`) via three mechanisms: a `yield` in the
fixture's own body (pytest), same fixture_type distinguished by name (`setUp`/`tearDown`), or a
different fixture_type at matching scope (`@BeforeEach`/`@AfterEach`, `beforeAll`/`afterAll`, etc.).
Only the setup-side fixture is flagged; the teardown fixture itself is not. Pairing rules:
`feature_extraction_patterns.yaml`'s `teardown_detection`.

**Known limitation:** checks that cleanup logic is *present*, not that it's *correct*; implicit cleanup
(e.g. automatic connection pooling) isn't detected.

### fixture_dependencies (Python/pytest only)

A fixture's own parameter names are cross-referenced against every other fixture name detected in the
same file; a match means "this fixture depends on that one." Implemented by re-parsing each pytest
fixture's `raw_source` and reading each parameter as its own AST node
(`_extract_parameter_names()`) rather than regex-splitting the parameter list text — a naive
`[^)]*` regex truncates at the first `)`, silently losing any parameter after a default value like
`items=list()`. Regression-tested: `tests/collection/test_extractor_metadata/test_fixture_dependencies.py`.

**Known limitation:** pytest-specific (no equivalent for Java/JS fixtures); transitive/indirect
dependencies are not tracked beyond one hop.

### num_mocks (and the `mock_usages` table)

Count of distinct mock usages detected within a fixture's own AST text (never outside it — a mock set
up at module level or in a shared helper is invisible to this detector, which matters most for Jest's
conventional top-level `jest.mock(...)`). Per-mock detail (framework, test-double category, target,
interaction count, source snippet) is stored one row per mock in the `mock_usages` table — see
[Database Schema § mock_usages](database-schema.md#mock_usages).

Each match is also classified into the classic test-double taxonomy (Meszaros) — `dummy`/`stub`/`spy`/
`mock`/`fake` — by keyword-matching the construct's own name, with a small set of individually-justified
manual overrides for constructs whose name contains no category keyword (e.g. `monkeypatch` → `stub`).
`dummy` is deliberately never assigned — distinguishing it from a mock needs data-flow analysis of how
the double is used afterward, not a keyword match. Full framework list and pattern catalog:
[detection.md § Mock Detection](detection.md#mock-detection).

Mocks are scoped consistently to the fixture's own function node (`_build_result()`), including for
Python's `pytest_decorator` type — a mock construct sitting purely in a decorator's own arguments
(e.g. `@pytest.fixture(params=[MagicMock()])`) is not attributed to the fixture.

### reuse_count — removed

`reuse_count` (number of test functions using a fixture) was removed entirely, for all languages, after
an audit of the post-processing logic found the metric was fabricated for Java/JavaScript/TypeScript,
not merely approximate. Its own docstring claimed it counted test methods sharing a fixture, but the
implementation actually grouped fixtures by `scope` string across the entire file and reported the group
size for any `per_class` fixture — unrelated classes in the same file with different numbers of `@Test`
methods all received the identical value. The Python/pytest branch (parameter-injection counting) was
independently correct, but shipping one column that's reliable for one language and fabricated for three
others is worse than not having it — a reviewer has no way to tell which rows are which from the data
alone. If per-language reuse analysis is needed later, it should be a new, explicitly-scoped metric
(e.g. `reuse_count_python`), not one column silently mixing a real count with a fabricated one.

---

## Using These Metrics in Research

**Safe:** complexity/size distributions, structural patterns (scope, parameters, nesting) within a
language, framework adoption analysis.

**Use with caution:** cross-language comparisons of any custom (non-Lizard) metric — detection
approach and precision differ per language even where the metric name is shared.

**Not recommended:** benchmarking fixture complexity against non-FixtureDB corpora (metric definitions
will differ), or treating any single metric as a proxy for test quality.
