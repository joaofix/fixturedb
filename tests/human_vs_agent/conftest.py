"""
Re-export pytest fixtures and utilities from parent conftest.

This allows tests in tests/human_vs_agent/ to import from .conftest
if needed (though typically they won't need the collection fixtures).
"""

# Re-export everything from parent conftest
from ..conftest import *  # noqa: F401, F403
