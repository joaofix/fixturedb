"""
Comprehensive tests for num_objects_instantiated metric using Lizard-based constructor detection.

This test suite validates that object instantiations are correctly counted across all 4 supported
languages (Python, Java, JavaScript, TypeScript), including edge cases and language-specific patterns:
- Python: Capitalized function calls (MyClass())
- Java/JS/TS: new keyword with constructors (new MyClass(...))
- Generics: Type parameters in Java/TypeScript (new HashMap<String, String>())
"""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

from collection.detector import extract_fixtures


class TestObjectInstantiationsPython:
    """Test num_objects_instantiated for Python fixtures."""

    def test_single_constructor(self):
        """Fixture with single constructor should count 1."""
        code = """
@pytest.fixture
def setup_user():
    user = User()
    return user
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 1

    def test_multiple_constructors(self):
        """Fixture with multiple constructors should count each."""
        code = """
@pytest.fixture
def setup_database():
    db = Database()
    conn = Connection()
    pool = ConnectionPool()
    return db
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 3

    def test_constructor_with_arguments(self):
        """Constructors with arguments should still be counted."""
        code = """
@pytest.fixture
def setup_configured():
    config = Config(timeout=30, retries=3)
    service = Service(config=config, name="test")
    return service
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 2

    def test_no_constructors(self):
        """Fixture with no constructors should count 0."""
        code = """
@pytest.fixture
def simple_setup():
    x = 42
    y = "string"
    z = [1, 2, 3]
    return x + len(z)
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 0

    def test_factory_method_vs_constructor(self):
        """Capitalized function calls (factory methods) should be counted as constructors."""
        code = """
@pytest.fixture
def setup_factory():
    # These should all be counted (capitalized = constructor heuristic)
    obj1 = MyClass()
    obj2 = SomeFactory()
    obj3 = Dict()
    # These should NOT be counted (lowercase)
    helper = helper_function()
    data = some_data()
    return obj1
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            # Should count MyClass, SomeFactory, Dict (3 capitalized)
            assert result.fixtures[0].num_objects_instantiated == 3

    def test_unittest_setup(self):
        """unittest setUp methods should also count constructors."""
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.user = User()
        self.db = Database()
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 2


class TestObjectInstantiationsJava:
    """Test num_objects_instantiated for Java fixtures."""

    def test_single_new_keyword(self):
        """Java fixture with single 'new' should count 1."""
        code = """
@Before
public void setup() {
    user = new User();
}
"""
        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 1

    def test_multiple_new_keywords(self):
        """Java fixture with multiple 'new' should count each."""
        code = """
@Before
public void setup() {
    user = new User();
    db = new Database();
    connection = new Connection();
}
"""
        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 3

    def test_generics_in_constructor(self):
        """Java generics in constructor should be properly handled."""
        code = """
@Before
public void setup() {
    map = new HashMap<String, String>();
    list = new ArrayList<Integer>();
}
"""
        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            assert len(result.fixtures) == 1
            # Should count both HashMap and ArrayList (2 total)
            assert result.fixtures[0].num_objects_instantiated == 2

    def test_nested_generics(self):
        """Java nested generics should be handled correctly."""
        code = """
@Before
public void setup() {
    obj1 = new HashMap<String, List<Integer>>();
    obj2 = new TreeMap<String, Set<String>>();
}
"""
        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 2

    def test_no_new_keyword(self):
        """Java fixture without 'new' should count 0."""
        code = """
@Before
public void setup() {
    user = User.getInstance();
    db = mockDatabase();
}
"""
        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 0


class TestObjectInstantiationsJavaScript:
    """Test num_objects_instantiated for JavaScript fixtures."""

    def test_single_new_keyword(self):
        """JS fixture with single 'new' should count 1."""
        code = """
beforeEach(() => {
    user = new User();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 1

    def test_multiple_new_keywords(self):
        """JS fixture with multiple 'new' should count each."""
        code = """
beforeEach(() => {
    user = new User();
    db = new Database();
    connection = new Connection();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 3

    def test_no_new_keyword(self):
        """JS fixture without 'new' should count 0."""
        code = """
beforeEach(() => {
    user = User.create();
    db = getDatabase();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 0

    def test_array_constructor(self):
        """JS Array constructor should be counted."""
        code = """
beforeEach(() => {
    arr = new Array(10);
    set = new Set();
    map = new Map();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 3


class TestObjectInstantiationsTypeScript:
    """Test num_objects_instantiated for TypeScript fixtures."""

    def test_typed_constructor(self):
        """TS constructor with type annotations should be counted."""
        code = """
beforeEach(() => {
    const user: User = new User();
    const db: Database = new Database();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "typescript")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 2

    def test_generics_in_constructor(self):
        """TS generics in constructor should be properly handled."""
        code = """
beforeEach(() => {
    const map = new Map<string, any>();
    const set = new Set<string>();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "typescript")
            assert len(result.fixtures) == 1
            # Should count both Map and Set (2 total)
            assert result.fixtures[0].num_objects_instantiated == 2

    def test_complex_generics(self):
        """TS complex nested generics should be handled correctly."""
        code = """
beforeEach(() => {
    const nested = new Map<string, Array<number>>();
    const complex = new Promise<void>();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "typescript")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 2

    def test_no_new_keyword_with_types(self):
        """TS fixture without 'new' but with type annotations should count 0."""
        code = """
beforeEach(() => {
    const user: User = User.getInstance();
    const db: Database = mockDatabase();
});
"""
        with NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "typescript")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 0


class TestObjectInstantiationsEdgeCases:
    """Test edge cases across languages."""

    def test_constructor_in_return_statement(self):
        """Constructor in return statement should be counted."""
        code = """
@pytest.fixture
def setup_user():
    return User()
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            assert result.fixtures[0].num_objects_instantiated == 1

    def test_constructor_in_condition(self):
        """Constructor inside if/else should be counted."""
        code = """
@pytest.fixture
def conditional_setup():
    if True:
        obj = MyClass()
    else:
        obj = OtherClass()
    return obj
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            # Should count both MyClass and OtherClass
            assert result.fixtures[0].num_objects_instantiated == 2

    def test_constructor_in_loop(self):
        """Constructor inside loop should be counted once per match."""
        code = """
@pytest.fixture
def loop_setup():
    items = []
    for i in range(3):
        items.append(Item())
    return items
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            # Item() appears once in source, should be counted once
            assert result.fixtures[0].num_objects_instantiated == 1

    def test_mixed_constructor_types(self):
        """Fixture mixing different object creation patterns."""
        code = """
@pytest.fixture
def mixed_setup():
    # This should be counted
    user = User()
    config = {'key': 'value'}  # Not a constructor call
    helper = helper_function()  # Not a constructor
    obj = SomeClass()  # This should be counted
    return user
"""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            assert len(result.fixtures) == 1
            # Should count User and SomeClass
            assert result.fixtures[0].num_objects_instantiated == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
