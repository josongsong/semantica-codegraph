# Python Integration Tests for Rust IR Pipeline

This directory contains Python integration tests that validate the PyO3 bindings and end-to-end workflows.

## Directory Structure

```
tests/python/
├── README.md                      # This file
├── conftest.py                    # Pytest fixtures and common utilities
├── integration/                   # Integration tests (Rust ↔ Python)
│   ├── test_e2e_pipeline.py      # E2E pipeline PyO3 bindings
│   ├── test_querydsl_integration.py # QueryDSL integration (Rust IR → Python QueryEngine)
│   └── test_ir_handler_integration.py # IR handler integration tests
├── benchmarks/                    # Performance benchmarks
│   ├── test_querydsl_scaling.py  # QueryDSL scaling tests on real repos
│   ├── test_rfc062_sota.py       # RFC-062 SOTA PyO3 API benchmarks
│   └── test_real_codebase.py     # Real codebase performance tests
├── scenarios/                     # Complete workflow scenarios
│   └── complete_indexing_workflow.py # Full data distribution workflow
└── unit/                          # Python-side unit tests
    └── test_api_compatibility.py # API compatibility tests
```

## Running Tests

```bash
# Run all Python integration tests
pytest tests/python/integration/ -v

# Run benchmarks
pytest tests/python/benchmarks/ -v --benchmark-only

# Run specific test
pytest tests/python/integration/test_querydsl_integration.py -v

# Run with performance metrics
pytest tests/python/benchmarks/test_querydsl_scaling.py -v -s
```

## Test Categories

### Integration Tests (`integration/`)
Tests that validate Rust ↔ Python boundaries:
- **E2E Pipeline**: Validates `run_ir_indexing_pipeline()` PyO3 API
- **QueryDSL Integration**: Tests Rust IR → Python IRDocument → QueryEngine workflow
- **IR Handler**: Tests IR handler integration with Python runtime

### Benchmarks (`benchmarks/`)
Performance-focused tests measuring throughput and latency:
- **QueryDSL Scaling**: Tests conversion overhead and query performance on real repos
- **RFC-062 SOTA**: Validates zero-overhead PyO3 API performance (1M+ symbols/sec)
- **Real Codebase**: Tests on production-scale codebases (238K LOC+)

### Scenarios (`scenarios/`)
Complete end-to-end workflow demonstrations:
- **Complete Indexing Workflow**: Shows data distribution to all backends (QueryEngine, Qdrant, PostgreSQL, SCIP)

### Unit Tests (`unit/`)
Python-specific unit tests:
- **API Compatibility**: Tests backward compatibility of Python APIs

## Performance Targets

| Test | Target | Current |
|------|--------|---------|
| Indexing (codegraph-engine) | < 3000ms | 1,653ms ✅ |
| Conversion (36K nodes) | < 100ms | 81ms ✅ |
| QueryEngine Init | < 500ms | 187ms ✅ |
| Avg Query Time | < 5ms | 0.002ms ✅ |
| RFC-062 Symbol Throughput | > 1M/sec | 1.1M/sec ✅ |

## Writing New Tests

### Integration Test Template

```python
#!/usr/bin/env python3
"""Test {Feature} PyO3 Integration

This test validates {what it validates}.
"""

import codegraph_ir
import pytest
import tempfile
import os


def test_{feature}_basic():
    """Test basic {feature} functionality"""
    # Setup
    repo_path = create_test_repo()

    try:
        # Execute
        result = codegraph_ir.run_ir_indexing_pipeline(
            repo_root=repo_path,
            repo_name="test-repo",
            file_paths=None,
            enable_chunking=True,
            enable_cross_file=True,
            enable_symbols=True,
            enable_points_to=True,
            parallel_workers=4,
        )

        # Assert
        assert result['nodes'], "Should have nodes"
        assert result['metadata']['files_failed'] == 0

    finally:
        # Cleanup
        import shutil
        shutil.rmtree(repo_path, ignore_errors=True)
```

### Benchmark Test Template

```python
#!/usr/bin/env python3
"""Benchmark {Feature} Performance

Measures {what it measures}.
"""

import codegraph_ir
import time
import pytest


@pytest.mark.benchmark
def test_{feature}_performance():
    """Benchmark {feature} performance"""
    # Setup
    repo_path = get_large_repo()

    # Measure
    start = time.perf_counter()
    result = run_pipeline(repo_path)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Assert
    assert elapsed_ms < TARGET_MS, f"Should complete in < {TARGET_MS}ms, got {elapsed_ms:.2f}ms"

    print(f"✅ Performance: {elapsed_ms:.2f}ms")
```

## CI/CD Integration

These tests are run in CI/CD:

```bash
# Quick smoke tests (< 10s)
pytest tests/python/integration/ -m "not slow" -v

# Full test suite (includes benchmarks)
pytest tests/python/ -v

# Performance regression tests
pytest tests/python/benchmarks/ --benchmark-compare
```

## Dependencies

Required packages (see `pyproject.toml`):
- `codegraph_ir` (Rust extension)
- `codegraph_engine` (QueryEngine)
- `pytest` (test runner)
- `pytest-benchmark` (for benchmarks)
- `pytest-asyncio` (for async tests)

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError: No module named 'codegraph_ir'`:
```bash
# Rebuild Rust extension
cd packages/codegraph-rust/codegraph-ir
maturin develop --release
```

### Performance Regression
If benchmarks fail:
1. Check system resources (CPU load, memory)
2. Run benchmarks multiple times to confirm
3. Compare against baseline in `benchmark_results/`

### Path Issues
All test paths should be absolute. Use:
```python
import os
repo_path = os.path.abspath("path/to/repo")
```

## Related Documentation

- [Rust Tests README](../README.md) - Rust-side test organization
- [TESTING.md](../../TESTING.md) - Complete testing guide
- [QueryDSL Integration Results](../../../../../QUERYDSL_INTEGRATION_RESULTS.md) - Latest benchmark results
