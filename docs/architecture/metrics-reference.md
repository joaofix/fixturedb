# Metrics Reference

Per-metric calculation methodology for every quantitative field FixtureDB records for a detected
fixture (`collection/detector_shared.py::FixtureResult`). For the detection pipeline itself (how a
fixture is found in the first place), see [detection.md](detection.md).

## At a Glance

| Metric | Tool / Method | Implementation | Languages |
|--------|--------------|-----------------|-----------|
| `cyclomatic_complexity` | Lizard | `complexity_provider.py::analyze_function_complexity()` | all |
| `num_parameters` | Lizard, self/cls stripped for Python | `complexity_provider.py` + `detector_shared.py::_build_result()` | all |
| `loc` | Non-blank line count | `detector_shared.py::_count_loc()` | all |
| `num_comment_lines`, `comment_density` | Tree-sitter comment-node walk | `detector_shared.py::_count_comment_lines()` | all |
| `fixture_type` | AST pattern match vs. `fixture_definitions.yaml` | `detector_python.py` / `detector_java.py` / `detector_javascript.py` | all |
| `fixture_role` | Post-processing, paired against sibling fixtures | `detector_shared.py::_classify_fixture_kinds()` | all |
| `num_mocks`, `mocks` | Regex (mock-framework patterns) | `detector_shared.py::_extract_mocks()` | all |
| `raw_source`, `start_line`, `end_line` | Verbatim text/location of the fixture's own node | `detector_shared.py::_build_result()` | all |

`scope`, `framework`, `max_nesting_depth`, `num_objects_instantiated`,
`num_external_calls`, `has_teardown_pair`, and `fixture_dependencies` were
removed from the extracted metric set entirely (not just stopped from
being read): `scope`/`framework` were fully redundant with `fixture_type`
(verified 1:1 mapping across every fixture_type value in the collected
data), and the other four simply aren't part of the paper's reported
metrics. `fixture_dependencies` and `container_id` were purely internal
signals (dependency propagation for `scope`, and teardown pairing for
`has_teardown_pair`) that had nothing left to serve once those two were
gone, so they were removed along with the code that only ever fed them.

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

Parses every file into an AST once; fixture detection and every custom (non-Lizard) metric are
derived from that same tree. The whole pipeline reads source as bytes and only decodes
per-fixture slices at the end (UTF-8, `errors="replace"`) — verified that multi-byte UTF-8 content
elsewhere in the file does not shift line numbers or fixture boundaries; non-UTF-8 files degrade
gracefully (structural detection stays correct, non-ASCII text inside comments/strings is replaced).
Tree-sitter never raises on malformed/incomplete source (it produces error nodes instead), so a
syntax error elsewhere in a file does not prevent detection of an otherwise well-formed fixture.

---

## Custom Metrics

### num_comment_lines, comment_density

Comment lines are counted from the AST, not from regex/text scanning: `_count_comment_lines()` walks every descendant of the fixture's own tree-sitter node (the same node `_build_result()` derives `raw_source`/`loc`/every other metric from — no re-parsing) and sums the line span of each node whose type is that language's comment node type — `comment` for Python (line-only; the grammar has no block-comment construct) and JS/TS (one type covers both `//` and `/* */`), or `line_comment`/`block_comment` for Java (two distinct types). A `//`/`#` line comment always spans exactly one line; a `/* */` block comment can span several, clipped to the fixture's own `start_line`/`end_line` if it were ever to extend past them (in practice it can't — every counted node is a genuine descendant, so it's already contained within the fixture's own span by construction).

`comment_density` is `num_comment_lines / loc`, computed after `loc` since it depends on it; `0.0` (not a `ZeroDivisionError`) if `loc` is `0`, though a real fixture's `loc` is never actually 0 (even a bare one-line signature counts as 1 non-blank line).

Because detection is AST-node-based, a `#`/`//`/`/* */` marker sitting inside a string literal is never mistaken for a real comment — the parser already knows it's string content, not a comment token.

**Note on existing DB files:** `num_comment_lines`/`comment_density` were added after `db/a.db`/`db/b.db`/`db/c.db` were already collected — see [Database Schema](database-schema.md#fixtures) for the migration/backfill caveat (self-healed schema, not backfilled values; a full re-extraction is required for real numbers on previously-collected data).

### num_parameters

Lizard's parameter count, with one Python-specific correction: Lizard counts a method's implicit
`self`/`cls` as an ordinary parameter, which would inflate `num_parameters` by 1 for essentially every
unittest/pytest-class-method fixture relative to a bare pytest_decorator function or an
equivalent Java/JS fixture (neither of which has an implicit first parameter). For Python,
`num_parameters` is computed by reading each parameter's own AST node directly
(`_extract_parameter_names()`) and excluding `self`/`cls`, instead of using Lizard's raw count.

### fixture_type

Deterministic AST pattern matching against `fixture_definitions.yaml`'s per-language tables — same
source always produces the same classification, no heuristics involved. Full per-framework mapping
and known ambiguities (e.g. `@BeforeClass` is shared syntax between JUnit4 and TestNG and the two
frameworks can't always be told apart from the annotation alone): [fixture-patterns-reference.md](../usage/fixture-patterns-reference.md).

### fixture_role

setup/teardown/setup_and_teardown/other, computed in a post-processing pass over the whole fixture
list (`_classify_fixture_kinds()`) by cross-referencing each fixture_type against
`feature_extraction_patterns.yaml`'s `teardown_detection` tables: same fixture_type distinguished by
name (`setUp`/`tearDown`), or a different fixture_type at the matching position (`@BeforeEach`/
`@AfterEach`, `beforeAll`/`afterAll`, etc.). `pytest_decorator` is the one exception, classified
directly from body analysis (presence/position of `yield`) at detection time instead, since every
pytest fixture is just named whatever the developer called it.

### num_mocks (and the `mock_usages` table)

Count of distinct mock usages detected within a fixture's own AST text (never outside it — a mock set
up at module level or in a shared helper is invisible to this detector, which matters most for Jest's
conventional top-level `jest.mock(...)`). Per-mock detail (framework, test-double category, target,
interaction count, source snippet) is stored one row per mock in the `mock_usages` table — see
[Database Schema § mock_usages](database-schema.md#mock_usages).

Each fixture is also classified into the classic test-double taxonomy (Meszaros) — `dummy`/`stub`/`spy`/
`mock`/`fake` — by scanning the fixture's own full body text, case-insensitively, for one of the five
category terms in priority order (dummy > stub > spy > fake > mock; falls back to `mock`, the
least-specific term, when none is found). One category is computed per fixture and applied to every mock
recorded in it. This is the same identifier-keyword method used in related work: `dummy` is a real,
reachable category (e.g. a `dummy_request = Mock()` fixture), not a value that can never appear. Full
framework list and pattern catalog: [detection.md § Mock Detection](detection.md#mock-detection).

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

**Safe:** complexity/size distributions, structural patterns (fixture_type, parameters) within a
language, framework adoption analysis.

**Use with caution:** cross-language comparisons of any custom (non-Lizard) metric — detection
approach and precision differ per language even where the metric name is shared.

**Not recommended:** benchmarking fixture complexity against non-FixtureDB corpora (metric definitions
will differ), or treating any single metric as a proxy for test quality.
