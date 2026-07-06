"""
Tests for cross-fixture post-processing: fixture_dependencies detection
(collection/detector_shared.py::_detect_fixture_dependencies) and scope
propagation (collection/detector_shared.py::_propagate_fixture_scopes).

Both passes only run for pytest fixtures (the only language/framework where
fixture-as-parameter dependency injection is detected).
"""

from ..conftest import extract_and_find_fixtures


class TestFixtureDependencyDetection:
    """Test _detect_fixture_dependencies populates fixture_dependencies."""

    def test_fixture_with_no_dependencies(self):
        code = """
@pytest.fixture
def simple():
    return 1
"""
        fixtures = extract_and_find_fixtures(code, "python")
        simple = next(f for f in fixtures if f.name == "simple")
        assert simple.fixture_dependencies == []

    def test_fixture_depending_on_multiple_fixtures(self):
        code = """
@pytest.fixture
def db():
    return connect()

@pytest.fixture
def cache():
    return Cache()

@pytest.fixture
def service(db, cache):
    return Service(db, cache)
"""
        fixtures = extract_and_find_fixtures(code, "python")
        service = next(f for f in fixtures if f.name == "service")
        assert sorted(service.fixture_dependencies) == ["cache", "db"]

    def test_parameter_not_matching_a_known_fixture_is_not_a_dependency(self):
        """A plain (non-fixture) parameter, e.g. injected by pytest itself
        (tmp_path) or a parametrize indirect value, should not show up in
        fixture_dependencies just because it's a parameter name."""
        code = """
@pytest.fixture
def report(tmp_path):
    return tmp_path / "report.txt"
"""
        fixtures = extract_and_find_fixtures(code, "python")
        report = next(f for f in fixtures if f.name == "report")
        assert report.fixture_dependencies == []

    def test_non_pytest_fixture_types_are_not_analyzed(self):
        """Only fixture_type == 'pytest_decorator' fixtures are eligible;
        unittest setUp (which also takes an implicit 'self' but is not
        parameter-injected the same way) must not populate dependencies."""
        code = """
@pytest.fixture
def helper():
    return Helper()

class TestExample(unittest.TestCase):
    def setUp(self):
        self.data = []
"""
        fixtures = extract_and_find_fixtures(code, "python")
        setup = next(f for f in fixtures if f.name == "setUp")
        assert setup.fixture_dependencies == []

    def test_default_value_containing_close_paren_does_not_break_detection(self):
        """Regression test: the old regex-based parameter extraction used
        `[^)]*` to grab the parameter list text, which truncated at the
        first `)` -- including one inside a default value like `list()` --
        silently losing any parameter declared after it. The AST-based
        _extract_parameter_names fix reads each parameter as its own node,
        so this can no longer happen."""
        code = """
@pytest.fixture
def db_connection():
    return connect()

@pytest.fixture
def repo(items=list(), db_connection=None):
    return Repo(items, db_connection)
"""
        fixtures = extract_and_find_fixtures(code, "python")
        repo = next(f for f in fixtures if f.name == "repo")
        assert repo.fixture_dependencies == ["db_connection"]

    def test_default_value_containing_comma_does_not_break_detection(self):
        """Regression test: a dict/collection default value containing a
        comma (e.g. `{"a": 1, "b": 2}`) must not be mis-split into extra,
        bogus "parameters" by a naive comma-split of the parameter text."""
        code = """
@pytest.fixture
def db_connection():
    return connect()

@pytest.fixture
def repo(data={"a": 1, "b": 2}, db_connection=None):
    return Repo(data, db_connection)
"""
        fixtures = extract_and_find_fixtures(code, "python")
        repo = next(f for f in fixtures if f.name == "repo")
        assert repo.fixture_dependencies == ["db_connection"]
        assert repo.num_parameters == 2


class TestFixtureScopePropagation:
    """Test _propagate_fixture_scopes downgrades scope based on dependencies."""

    def test_module_scoped_fixture_depending_on_test_scoped_is_downgraded(self):
        """A per_module fixture that depends on a per_test fixture is an
        impossible configuration (the narrower-scoped dependency would be
        torn down before the wider-scoped fixture's next use) -- the wider
        fixture's scope must be downgraded to match."""
        code = """
@pytest.fixture
def request_id():
    return uuid4()

@pytest.fixture(scope="module")
def report(request_id):
    return Report(request_id)
"""
        fixtures = extract_and_find_fixtures(code, "python")
        request_id = next(f for f in fixtures if f.name == "request_id")
        report = next(f for f in fixtures if f.name == "report")
        assert request_id.scope == "per_test"
        assert report.scope == "per_test"

    def test_matching_scopes_are_not_changed(self):
        code = """
@pytest.fixture(scope="module")
def db():
    return connect()

@pytest.fixture(scope="module")
def repo(db):
    return Repo(db)
"""
        fixtures = extract_and_find_fixtures(code, "python")
        repo = next(f for f in fixtures if f.name == "repo")
        assert repo.scope == "per_module"

    def test_wider_scoped_dependency_does_not_widen_dependent(self):
        """A per_test fixture depending on a global fixture should stay
        per_test -- scope propagation only ever narrows, never widens."""
        code = """
@pytest.fixture(scope="session")
def db():
    return connect()

@pytest.fixture
def txn(db):
    return db.begin()
"""
        fixtures = extract_and_find_fixtures(code, "python")
        txn = next(f for f in fixtures if f.name == "txn")
        assert txn.scope == "per_test"

    def test_propagation_through_a_chain_of_dependencies(self):
        """Scope constraints must propagate transitively: if C depends on B
        which depends on A (per_test), C must also be downgraded to
        per_test even though C doesn't directly depend on A."""
        code = """
@pytest.fixture
def request_id():
    return uuid4()

@pytest.fixture(scope="module")
def mid(request_id):
    return Mid(request_id)

@pytest.fixture(scope="session")
def top(mid):
    return Top(mid)
"""
        fixtures = extract_and_find_fixtures(code, "python")
        mid = next(f for f in fixtures if f.name == "mid")
        top = next(f for f in fixtures if f.name == "top")
        assert mid.scope == "per_test"
        assert top.scope == "per_test"
