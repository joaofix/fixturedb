"""Gold-label fixture-detection regression suite.

Closes internal-docs/REVIEWER_CRITIQUE_DETECTION_METHODOLOGY.md gap #5: the
published ">95% recall" figures in docs/reference/limitations.md had no
mechanism keeping them honest as detector code changes over time. The
existing test suites don't cover this:
- tests/collection/test_fixture_definitions_catalog_coverage.py exercises
  every YAML-defined *pattern* via synthetic, minimal, one-construct-at-a-
  time snippets (breadth over the catalog, not real-world code shape).
- tests/collection/test_extractor_unit/ tests individual rules in
  isolation.

This file is neither: each case below is REAL source text, copied verbatim
from an actual commit in this project's own collected corpus and verified
byte-for-byte against raw.githubusercontent.com/{repo}/{sha}/{path} when
added (see each case's provenance comment) -- not retyped or simplified.
A future detector change that alters output for any of these (a new false
positive, a missed detection, a changed count) fails this suite
immediately, the same way the double-detection bug below should have been
caught before it shipped.

Line numbers are NOT asserted against the original GitHub file (these
snippets omit the file's real preamble/imports, so line numbers wouldn't
match anyway) -- fixture_type/scope/framework/count/name and, where it's
the point of the case, raw_source content are what's locked in.
"""

from __future__ import annotations

from ..conftest import extract_and_find_fixtures


class TestPythonGoldRegression:
    def test_dagster_decorated_setup_method_counted_once(self):
        """dagster-io/dagster @ c584b25f17f373c62c19c4d2b88ece2828e26ed1,
        python_modules/dagster/dagster_tests/declarative_automation_tests/
        automation_condition_tests/builtins/test_freshness_result_condition.py,
        lines 15-25 (verified 2026-07-13). Found via toy Dataset B review:
        a method with both a @pytest.fixture decorator and a
        setup_method-style name was detected twice (pytest_decorator AND
        pytest_class_method) before this session's fix to
        detector_python.py. Must stay fixed."""
        code = """\
class TestFreshnessResultCondition:
    instance: DagsterInstance
    __state_cache: dict[AssetKey, FreshnessState]

    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.instance = DagsterInstance.ephemeral()
        self.__state_cache = {}
        yield
        self.instance = None  # pyright: ignore[reportAttributeAccessIssue]
        self.__state_cache = {}
"""
        fixtures = extract_and_find_fixtures(code, "python")
        assert len(fixtures) == 1, (
            f"Expected exactly 1 fixture (decorator+name-matched method "
            f"counted once), got {len(fixtures)}: "
            f"{[f.fixture_type for f in fixtures]}"
        )
        fixture = fixtures[0]
        assert fixture.name == "setup_method"
        assert fixture.fixture_type == "pytest_decorator"
        assert fixture.framework == "pytest"
        assert fixture.scope == "per_test"
        assert "DagsterInstance.ephemeral()" in fixture.raw_source
        assert "yield" in fixture.raw_source


class TestJavaGoldRegression:
    def test_glassfish_after_teardown(self):
        """javaee/glassfish @ 371c9e1beb285a30bd4203ec86fde5729dbd06f9,
        nucleus/admin/config-api/src/test/java/com/sun/enterprise/
        configapi/tests/TranslatedViewCreationTest.java, lines 152-155
        (verified 2026-07-13, sampled during toy Dataset B review)."""
        code = """\
public class TranslatedViewCreationTest {
    @After
    public void tearDown() {
        System.setProperty(propName, "");
    }
}
"""
        fixtures = extract_and_find_fixtures(code, "java")
        assert len(fixtures) == 1, f"Expected exactly 1 fixture, got {len(fixtures)}"
        fixture = fixtures[0]
        assert fixture.name == "tearDown"
        assert fixture.fixture_type == "junit4_after"
        assert fixture.framework == "junit"
        assert fixture.scope == "per_test"
        assert 'System.setProperty(propName, "")' in fixture.raw_source


class TestJavaScriptGoldRegression:
    def test_dyo_utility_comma_expression_hooks_all_detected_separately(self):
        """dyo/dyo @ 3bb4c10ac817030404982c0cb948e625bcaa7380, test/Utility.js,
        lines 7-10 (verified 2026-07-13, sampled during toy Dataset C
        review). Real, unusual source style: before(...)/after(...) pairs
        written as one comma-expression per line, so 8 distinct fixtures
        (4 mocha_before + 4 mocha_after) share only 4 physical lines --
        confirmed correct at the time (each has distinct raw_source), not
        a detector bug, but exactly the kind of unusual real-world shape a
        synthetic catalog test wouldn't surface. Guards against a future
        change collapsing or miscounting comma-expression call sites."""
        code = """\
describe('Utility', () => {
\tconst Symbol = globalThis.Symbol
\tconst Promise = globalThis.Promise
\tconst setTimeout = globalThis.setTimeout
\tconst requestAnimationFrame = globalThis.requestAnimationFrame

\tbefore(() => globalThis.Symbol = ''), after(() => globalThis.Symbol = Symbol)
\tbefore(() => globalThis.Promise = ''), after(() => globalThis.Promise = Promise)
\tbefore(() => globalThis.setTimeout = ''), after(() => globalThis.setTimeout = setTimeout)
\tbefore(() => globalThis.requestAnimationFrame = ''), after(() => globalThis.requestAnimationFrame = requestAnimationFrame)
});
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        assert len(fixtures) == 8, (
            f"Expected exactly 8 fixtures (4 before + 4 after), got "
            f"{len(fixtures)}: {[f.fixture_type for f in fixtures]}"
        )
        types = sorted(f.fixture_type for f in fixtures)
        assert types == sorted(["mocha_before", "mocha_after"] * 4)
        assert all(f.scope == "per_test" for f in fixtures)
        # Each of the 4 line-pairs' before/after must carry distinct
        # raw_source (the specific global being stubbed) -- collapsing to
        # 4 identical-looking fixtures would be the regression this case
        # exists to catch.
        raw_sources = {f.raw_source for f in fixtures}
        assert len(raw_sources) == 8


class TestTypeScriptGoldRegression:
    def test_wayne_footer_component_before_each_async(self):
        """qihoo360/wayne @ 09246ac4de905310f19a2f527b0db67b2211297e,
        src/frontend/src/app/shared/footer/footer.component.spec.ts,
        lines 9-14 (verified 2026-07-13, sampled during toy Dataset C
        review)."""
        code = """\
describe('FooterComponent', () => {
  const component: FooterComponent;
  const fixture: ComponentFixture<FooterComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [FooterComponent]
    })
      .compileComponents();
  }));
});
"""
        fixtures = extract_and_find_fixtures(code, "typescript")
        assert len(fixtures) == 1, f"Expected exactly 1 fixture, got {len(fixtures)}"
        fixture = fixtures[0]
        assert fixture.fixture_type == "before_each"
        assert fixture.scope == "per_test"
        assert "TestBed.configureTestingModule" in fixture.raw_source
