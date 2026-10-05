# Fixture detection

This page explains how a fixture is found in source code and how its metrics are
computed. Agent detection is on [its own page](agent-detection.md).

## Method

Each test file is parsed with Tree-sitter. The parser gives a syntax tree. A
fixture is a node that matches a pattern for its language:

| Language | Matches on | Examples |
|----------|-----------|----------|
| Python | Decorators and method names | `@pytest.fixture`, `setUp()` |
| Java | Annotations and method names | `@BeforeEach`, `@Rule`, `setUp()` |
| JavaScript, TypeScript | Hook calls | `beforeEach()`, `beforeAll()` |

Matching is exact. There is no scoring and no fuzzy matching. The same file
always gives the same fixtures.

The patterns are not in the code. They are in
[`fixture_definitions.yaml`](../../collection/heuristics/fixture_definitions.yaml),
one section per language. Each section also lists the cases the detector
deliberately skips, with a reason. Review the skipped cases there.

Async functions match the same way. `@pytest_asyncio.fixture` matches like
`@pytest.fixture`, and `beforeEach(async () => ...)` matches like `beforeEach`.

Java's JUnit 3 fallback matches `setUp()` and `tearDown()` only in classes that
extend `TestCase`.

## Metrics

Each fixture gets these values:

| Value | How it is computed |
|-------|--------------------|
| `loc` | Non-blank lines in the fixture body |
| `cyclomatic_complexity` | Lizard, on the fixture's own source |
| `num_parameters` | Lizard, on the fixture's own source |
| `num_comment_lines`, `comment_density` | Single-line comments, found in the syntax tree |
| `fixture_role` | `setup`, `teardown` or `other` (see below) |
| `raw_source`, `start_line`, `end_line` | Exact text and location, for audit |

The metric definitions for the paper are on the
[dataset card](../data/dataset-card.md).

**Roles.** Most fixtures are labelled by name or position. For example, `tearDown`
in unittest or `@AfterEach` in JUnit is a teardown. The rules are in
`feature_extraction_patterns.yaml`.

pytest fixtures have no fixed name, so their body is read instead:

- A call to `request.addfinalizer(...)` gives `setup_and_teardown`.
- No `yield` gives `setup`.
- A bare `yield` as the first statement gives `teardown`.
- Any other `yield` gives `setup_and_teardown`.

Cyclomatic complexity and parameter count come from Lizard. A JUnit `@Rule`
field has no function body, so Lizard reports the default values for it.

## Mocks

Mocks are found with regular expressions over each fixture's own text. The
catalog covers `unittest.mock`, `pytest-mock` and `monkeypatch` for Python,
Mockito and EasyMock for Java, and Jest, Sinon and Vitest for JavaScript and
TypeScript. The full list is in
[`feature_extraction_patterns.yaml`](../../collection/heuristics/feature_extraction_patterns.yaml).

Each mock also gets a test-double category: `dummy`, `stub`, `spy`, `mock` or
`fake`. The category comes from keywords in the fixture text. When more than one
keyword appears, the first in the priority order `dummy`, `stub`, `spy`, `fake`,
`mock` wins. If none appears, the category is `mock`.

## Code

| File | Role |
|------|------|
| `collection/detector.py` | Public entry point, `extract_fixtures()` |
| `collection/detector_shared.py` | Shared types, parser cache, mock detection |
| `collection/detector_python.py` | Python patterns |
| `collection/detector_java.py` | Java patterns |
| `collection/detector_javascript.py` | JavaScript and TypeScript patterns |

Tests are in `tests/collection/`. The catalog tests run every entry of the YAML
files through the detector, so a catalog edit is checked automatically.
