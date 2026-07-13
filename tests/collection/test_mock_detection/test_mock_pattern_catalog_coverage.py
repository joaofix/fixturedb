"""Exhaustive, catalog-driven coverage of every mock_patterns entry.

Unlike the per-language test files (which exercise real fixtures through
the full extract_fixtures() pipeline), this file is parametrized directly
over collection/heuristics/feature_extraction_patterns.yaml's
mock_patterns list. That makes two guarantees the per-language tests
can't, by construction:

1. **No pattern is silently untested.** SAMPLES is keyed by the pattern's
   own regex string. If a future edit adds a new mock_patterns entry
   without a matching sample here, this test fails immediately (KeyError)
   instead of the gap going unnoticed -- which is exactly how
   mocker.patch.object(...), Mockito.spy(...), and the Mock()/createMock()
   collision below were originally found: existing tests asserted the
   surrounding fixture was extracted, never that the specific mock pattern
   actually fired.

2. **No two patterns silently collide.** For every sample, every pattern
   in the full catalog is scanned against it (not just the one it's meant
   to test) and any unexpected extra match fails the test. This is what
   caught two real bugs during this file's own construction: the bare
   Mock()/MagicMock()/AsyncMock() pattern matched as a substring inside
   Java's EasyMock.createMock(...), and the MockK mock(X.class) pattern
   matched as a substring inside Mockito.mock(X.class) -- both fixed with
   word-boundary/negative-lookbehind additions in the YAML, verified here.
"""

from __future__ import annotations

import re

import pytest

from collection.config_data import load_feature_extraction_patterns
from collection.detector_shared import MOCK_PATTERNS

MOCK_PATTERNS_CATALOG = load_feature_extraction_patterns()["mock_patterns"]

# One minimal, realistic sample per pattern, keyed by the pattern's own
# regex string so a change to the pattern forces a matching update here.
# NOTE: keys use single-quoted, non-raw string literals (matching the YAML
# file's own single-quoted-scalar convention) rather than r"...['\"]..."
# raw strings -- a raw string's \" keeps a literal backslash before the
# quote that the YAML-parsed pattern does not have, which silently breaks
# the dict lookup below despite looking identical when printed.
SAMPLES: dict[str, str] = {
    'mock\\.patch\\s*\\(\\s*[\'"]([^\'"]+)[\'"]': "mock.patch('module.function')",
    r"mock\.patch\.object\s*\(\s*(\w+)": "mock.patch.object(Service, 'call')",
    r"create_autospec\s*\(\s*(\w+)": "create_autospec(RealApi)",
    'mocker\\.patch\\s*\\(\\s*[\'"]([^\'"]+)[\'"]': "mocker.patch('module.function')",
    r"mocker\.patch\.object\s*\(\s*(\w+)": "mocker.patch.object(service, 'get_user')",
    '(?<!mock\\.)(?<!mocker\\.)\\bpatch\\s*\\(\\s*[\'"]([^\'"]+)[\'"]': "patch('module.function')",
    r"(?<!mock\.)(?<!mocker\.)\bpatch\.object\s*\(\s*(\w+)": "patch.object(Service, 'call')",
    r"MagicMock\s*\(|\bMock\s*\(|AsyncMock\s*\(": "x = Mock(); y = MagicMock(); z = AsyncMock()",
    r"monkeypatch\.(setattr|delattr|setenv|delenv|setitem|delitem)\s*\(": "monkeypatch.setenv('ENV', 'test')",
    r"Mockito\.mock\s*\(\s*(\w+)\.class": "Mockito.mock(UserRepository.class)",
    r"@Mock\b": "@Mock",
    r"Mockito\.spy\s*\(\s*(\w+)": "Mockito.spy(real)",
    r"EasyMock\.createMock\s*\(\s*(\w+)\.class": "EasyMock.createMock(UserRepository.class)",
    "(?<!\\.)\\bmock\\s*\\(\\s*(\\w+)\\.class": "mock(UserRepository.class)",
    r"jest\.fn\s*\(": "jest.fn()",
    r"jest\.spyOn\s*\(": "jest.spyOn(console, 'log')",
    'jest\\.mock\\s*\\(\\s*[\'"]([^\'"]+)[\'"]': "jest.mock('./api')",
    r"jest\.mocked\s*\(\s*(\w+)": "jest.mocked(myModule)",
    'jest\\.createMockFromModule\\s*\\(\\s*[\'"]([^\'"]+)[\'"]': "jest.createMockFromModule('./api')",
    r"sinon\.stub\s*\(": "sinon.stub(obj, 'method')",
    r"sinon\.spy\s*\(": "sinon.spy(obj, 'method')",
    r"sinon\.mock\s*\(": "sinon.mock(obj)",
    r"sinon\.fake\s*\(": "sinon.fake()",
    r"sinon\.replace\s*\(": "sinon.replace(obj, 'method', f)",
    r"sinon\.createStubInstance\s*\(\s*(\w+)": "sinon.createStubInstance(MyClass)",
    r"vi\.fn\s*\(": "vi.fn()",
    'vi\\.mock\\s*\\(\\s*[\'"]([^\'"]+)[\'"]': "vi.mock('./service')",
    r"gomock\.NewController": "gomock.NewController(t)",
    r"testify/mock": 'import "github.com/stretchr/testify/mock"',
    '\\.On\\s*\\(\\s*[\'"](\\w+)[\'"]': '.On("MethodName")',
}


def test_every_catalog_pattern_has_a_sample():
    """Guardrail: a new mock_patterns entry with no SAMPLES key must fail
    loudly here, not slip through silently untested."""
    catalog_patterns = {entry["pattern"] for entry in MOCK_PATTERNS_CATALOG}
    assert catalog_patterns == set(SAMPLES), (
        "SAMPLES is out of sync with mock_patterns -- "
        f"missing: {catalog_patterns - set(SAMPLES)}, "
        f"stale: {set(SAMPLES) - catalog_patterns}"
    )


@pytest.mark.parametrize(
    "entry",
    MOCK_PATTERNS_CATALOG,
    ids=[f"{e['framework']}:{e['category']}:{e['pattern'][:30]}" for e in MOCK_PATTERNS_CATALOG],
)
def test_pattern_matches_its_own_sample(entry):
    """Each pattern must actually match the sample written for it."""
    sample = SAMPLES[entry["pattern"]]
    assert re.search(entry["pattern"], sample), (
        f"{entry['framework']}/{entry['category']} pattern {entry['pattern']!r} "
        f"did not match its own sample {sample!r}"
    )


@pytest.mark.parametrize(
    "entry",
    MOCK_PATTERNS_CATALOG,
    ids=[f"{e['framework']}:{e['category']}:{e['pattern'][:30]}" for e in MOCK_PATTERNS_CATALOG],
)
def test_sample_does_not_trigger_any_other_pattern(entry):
    """No sample should be matched by more than its own intended pattern --
    a collision would mean two frameworks/categories get recorded for one
    real mock call (double-counting num_mocks) or a wrong category is
    assigned. This is exactly the class of bug found in
    MagicMock|Mock|AsyncMock vs EasyMock.createMock(...) and static-import
    mock(X.class) vs Mockito.mock(X.class)."""
    sample = SAMPLES[entry["pattern"]]
    matches = [
        (other["pattern"], other["framework"], other["category"])
        for other in MOCK_PATTERNS_CATALOG
        if re.search(other["pattern"], sample)
    ]
    assert matches == [(entry["pattern"], entry["framework"], entry["category"])], (
        f"sample {sample!r} (intended for {entry['framework']}/{entry['category']}) "
        f"was also matched by: {[m for m in matches if m[0] != entry['pattern']]}"
    )


def test_mock_patterns_constant_matches_yaml_catalog():
    """detector_shared.MOCK_PATTERNS (what actually runs at detection time)
    must be derived from the same YAML entries this test parametrizes
    over, not a stale cached copy."""
    from_yaml = {
        (e["pattern"], e["framework"], e["category"]) for e in MOCK_PATTERNS_CATALOG
    }
    from_constant = set(MOCK_PATTERNS)
    assert from_yaml == from_constant
