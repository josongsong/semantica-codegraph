"""Python integration tests for codegraph-ir Rust package.

This package contains Python-side tests that validate PyO3 bindings,
integration with Python components (QueryEngine), and end-to-end workflows.

Test Structure:
---------------
- integration/: Rust ↔ Python integration tests
- benchmarks/: Performance benchmarks and scaling tests
- scenarios/: Complete workflow demonstrations
- unit/: Python-side unit tests

Running Tests:
--------------
# All tests (excluding slow)
pytest tests/python/ -v

# Include slow tests
pytest tests/python/ -m "" -v

# Only benchmarks
pytest tests/python/benchmarks/ -v

# Specific test
pytest tests/python/integration/test_querydsl_integration.py -v

# With performance output
pytest tests/python/ -v -s
"""

__all__ = []
