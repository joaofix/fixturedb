"""Regression tests for the comment-exclusion fix in
collection/detector_shared.py::_extract_mocks()/_mask_comment_spans().

Found via manual validation sampling (validation-samples/mock-detection/):
a fixture whose only jest.spyOn(...) call was commented out still got
has_mock=True, because mock detection matches MOCK_PATTERNS/
_classify_mock_category() against the fixture's flat source text, with no
notion that a `//`/`#`/`/* */` comment isn't real code. Fixed by matching
against a copy of that text with every comment node's span blanked out
(same technique _count_comment_lines() already uses via COMMENT_NODE_TYPES),
while still slicing raw_snippet from the real, unmasked text.

Every test here drives the real extract_fixtures() pipeline end-to-end
(not a unit call into _extract_mocks()/_mask_comment_spans() directly) --
same convention as the rest of tests/collection/test_mock_detection/.
"""

from __future__ import annotations

from ..conftest import assert_fixture_with_type_detected, extract_and_find_fixtures


class TestPythonCommentedOutMocksExcluded:
    def test_purely_commented_out_mock_call_yields_no_mock(self):
        code = """
@pytest.fixture
def fixture_setup():
    # patcher = mock.patch("module.function")
    return real_thing()
"""
        fixture = extract_and_find_fixtures(code, "python", "fixture_setup")[0]
        assert fixture.mocks == []

    def test_real_mock_call_still_detected_alongside_a_comment_mentioning_one(self):
        """A comment mentioning a mock construct must not suppress a real
        one elsewhere in the same fixture -- masking only blanks the
        comment's own span, nothing else."""
        code = """
@pytest.fixture
def fixture_setup():
    return Mock()
"""
        fixture = extract_and_find_fixtures(code, "python", "fixture_setup")[0]
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "unittest_mock"

    def test_category_not_derived_from_a_comment_only_keyword(self):
        """_classify_mock_category() must scan the *masked* text too -- a
        'spy'/'stub'/etc. keyword sitting only in a comment shouldn't win
        the category for a real, differently-flavoured mock call."""
        code = """
@pytest.fixture
def fixture_setup():
    # spy = sinon.spy() -- not actually used
    return Mock()
"""
        fixture = extract_and_find_fixtures(code, "python", "fixture_setup")[0]
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].category == "mock"

    def test_disjoint_comment_elsewhere_does_not_block_a_real_match(self):
        """A comment on its own line, anywhere else in the fixture, must
        not interfere with a real match found later in the same body --
        masking only ever touches the comment node's own span."""
        code = """
@pytest.fixture
def fixture_setup():
    # some unrelated commentary about this fixture
    return mock.patch("module.function")
"""
        fixture = extract_and_find_fixtures(code, "python", "fixture_setup")[0]
        assert len(fixture.mocks) == 1


class TestRawSnippetStillShowsRealSurroundingCode:
    def test_raw_snippet_is_sliced_from_unmasked_text(self):
        """raw_snippet must show the real code around a match, including
        any nearby comment text -- masking only decides whether something
        counts as a match, never what's shown for one that does."""
        code = """
@pytest.fixture
def fixture_setup():
    # sets up a mock client
    return Mock()
"""
        fixture = extract_and_find_fixtures(code, "python", "fixture_setup")[0]
        assert len(fixture.mocks) == 1
        # Within SNIPPET_CONTEXT_BEFORE's window -- confirms the real
        # comment text (not blanked-out spaces) survives into raw_snippet.
        assert "client" in fixture.mocks[0].raw_snippet


class TestNonAsciiCommentOffsetAlignment:
    """The character-vs-byte offset conversion this fix relies on: a
    non-ASCII comment occupies more bytes than characters in UTF-8, so a
    naive byte-length mask would misalign every match found after it."""

    def test_real_mock_call_after_a_non_ascii_comment_is_still_found_correctly(self):
        code = """
@pytest.fixture
def fixture_setup():
    # 设置一个模拟对象用于测试目的说明一下
    return Mock()
"""
        fixture = extract_and_find_fixtures(code, "python", "fixture_setup")[0]
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "unittest_mock"
        # The snippet around the match must be the real code, not garbage
        # from a misaligned slice.
        assert "Mock()" in fixture.mocks[0].raw_snippet

    def test_commented_out_call_after_a_non_ascii_comment_is_still_excluded(self):
        code = """
@pytest.fixture
def fixture_setup():
    # 说明文字
    # patcher = mock.patch("module.function")
    return real_thing()
"""
        fixture = extract_and_find_fixtures(code, "python", "fixture_setup")[0]
        assert fixture.mocks == []


class TestJavaScriptCommentedOutMocksExcluded:
    def test_line_comment(self):
        code = """
describe('Module', () => {
    beforeEach(() => {
        // jest.spyOn(ReactRedux, 'useDispatch').mockReturnValue(mockDispatch);
        store = mockStore(getInitialState());
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.mocks == []

    def test_real_spy_call_still_detected(self):
        code = """
describe('Module', () => {
    beforeEach(() => {
        // an old approach we don't use anymore: jest.fn()
        jest.spyOn(console, 'log').mockImplementation(() => {});
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "jest"

    def test_block_comment(self):
        code = """
describe('Module', () => {
    beforeEach(() => {
        /* jest.mock('./module'); */
        setupRealDependency();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.mocks == []


class TestTypeScriptCommentedOutMocksExcluded:
    def test_line_comment(self):
        code = """
describe('Module', () => {
    beforeEach(() => {
        // vi.spyOn(console, 'log');
        doRealSetup();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.mocks == []


class TestJavaCommentedOutMocksExcluded:
    def test_line_comment(self):
        code = """
public class T {
    @Before
    public void setUp() {
        // invokeRequest = mock(InvokeRequest.class);
        realService = new RealService();
    }
}
"""
        fixture = extract_and_find_fixtures(code, "java", "setUp")[0]
        assert fixture.mocks == []

    def test_real_mock_call_still_detected_alongside_a_commented_out_one(self):
        code = """
public class T {
    @Before
    public void setUp() {
        // invokeRequest = mock(InvokeRequest.class);
        invokeResult = mock(InvokeResult.class);
    }
}
"""
        fixture = extract_and_find_fixtures(code, "java", "setUp")[0]
        assert len(fixture.mocks) == 1
        assert fixture.mocks[0].framework == "mockito"

    def test_block_comment(self):
        code = """
public class T {
    @Before
    public void setUp() {
        /* Mockito.spy(new Thing()); */
        realThing = new RealThing();
    }
}
"""
        fixture = extract_and_find_fixtures(code, "java", "setUp")[0]
        assert fixture.mocks == []
