# Test Organization Migration

## What Changed

Tests have been reorganized into two main subdirectories to match the source code structure:

```
tests/
├── conftest.py                  # Shared pytest configuration and utilities
├── TEST_ORGANIZATION.md         # Test organization documentation
├── TEST_PLAN.md                 # Test strategy and planning
├── fixtures/                    # Shared test data
│
├── collection/                  # Tests for collection module
│   ├── conftest.py              # Re-exports parent conftest
│   ├── __init__.py
│   ├── test_detector_edge_cases.py
│   ├── test_extractor_coverage.py
│   ├── test_framework_detection.py
│   ├── test_framework_gaps.md
│   ├── test_github_search_loader.py
│   ├── test_test_file_discovery.py
│   ├── test_extractor_edge_cases/
│   ├── test_extractor_metadata/
│   ├── test_extractor_unit/
│   ├── test_mock_detection/
│   ├── test_integration/
│   └── test_export/
│
└── human_vs_agent/              # Tests for human_vs_agent phases
    ├── conftest.py              # Re-exports parent conftest
    ├── __init__.py
    ├── test_agent_detection_end_to_end.py
    ├── test_split_agent_detector.py
    ├── test_split_dataset_exporter.py
    ├── test_split_dataset_sampler.py
    ├── test_split_fixture_extractor.py
    └── test_split_integration.py
```

## Why

The tests are now organized to match the source code structure:
- `tests/collection/` mirrors `collection/` module
- `tests/human_vs_agent/` mirrors `human_vs_agent/` folder
- Shared configuration remains at `tests/` root level

This makes it clear which tests validate which components.

## Technical Details

### Conftest Hierarchy

```
tests/conftest.py               # Root fixtures and utilities
├── tests/collection/conftest.py       # Re-exports parent
└── tests/human_vs_agent/conftest.py   # Re-exports parent
```

The conftest files in subdirectories re-export everything from the parent, allowing imports like:
- `from .conftest import create_test_file` in `tests/collection/test_framework_detection.py`
- `from ..conftest import create_test_file` in `tests/collection/test_extractor_edge_cases/test_edge_cases.py`

### Import Compatibility

All test files use absolute imports from packages:
```python
from collection.detector import extract_fixtures
from collection.agent_detector import AgentFileScanner
```

Pytest automatically discovers conftest.py files in the directory hierarchy, so fixtures and utilities are available to all tests regardless of location.

## Running Tests

```bash
# Run all tests
pytest tests/

# Run only collection tests
pytest tests/collection/

# Run only human_vs_agent tests
pytest tests/human_vs_agent/

# Run specific test file
pytest tests/collection/test_detector_edge_cases.py

# Run with coverage
pytest tests/ --cov=collection --cov=human_vs_agent --cov-report=html
```

## Test Coverage

### Collection Tests
- **Fixture Detection**: Detector accuracy, edge cases, error handling
- **Fixture Extraction**: Language-specific extraction for Python, Java, JavaScript, TypeScript, Go
- **Framework Detection**: Pytest, unittest, JUnit, xUnit, etc.
- **Mock Detection**: Mock framework recognition (pytest-mock, unittest.mock, etc.)
- **Export**: CSV and ZIP export functionality
- **Integration**: Realistic fixture extraction from real repositories

### Human vs Agent Tests
- **Agent Detection**: Co-authored-by trailer verification
- **Dataset Splitting**: Human (pre-2021) vs LLM (2022+) fixture separation
- **Export**: Fixture export with tier labels (Tier 1 corpus, Tier 2 matched repos)
- **Sampling**: Stratified sampling to balance human vs LLM counts
- **Integration**: End-to-end pipeline validation

## Verification

All tests have been verified:
- ✓ Pytest discovers all tests
- ✓ All imports resolve correctly
- ✓ No syntax errors in moved files
- ✓ Conftest hierarchy works correctly
