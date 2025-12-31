# Python Tests Quick Start

Get started with Python integration tests in 5 minutes.

## TL;DR

```bash
# From codegraph-ir root
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph/packages/codegraph-rust/codegraph-ir

# Build Rust extension
make build-python

# Run all tests
make test-python

# Run specific category
make test-python-integration    # Integration tests
make test-python-benchmark      # Benchmarks
```

## Prerequisites

```bash
# Python 3.10+
python --version

# Install dependencies
pip install pytest pytest-benchmark pytest-asyncio

# Build Rust extension
cd packages/codegraph-rust/codegraph-ir
maturin develop --release
```

## Directory Structure

```
tests/python/
├── integration/     # Rust ↔ Python integration tests
├── benchmarks/      # Performance benchmarks
├── scenarios/       # Complete workflow demos
└── unit/           # Python unit tests
```

## Running Tests

### All Tests (Fast)
Excludes slow tests by default:
```bash
cd tests/python
pytest -v
```

### Include Slow Tests
```bash
cd tests/python
pytest -m "" -v
```

### Specific Category
```bash
cd tests/python
pytest integration/ -v              # Integration only
pytest benchmarks/ -v -s            # Benchmarks with output
pytest scenarios/ -v                # Scenarios
pytest unit/ -v                     # Unit tests
```

### Single Test
```bash
cd tests/python
pytest integration/test_querydsl_integration.py -v
pytest integration/test_querydsl_integration.py::test_querydsl_basic_queries -v
```

### With Performance Output
```bash
cd tests/python
pytest benchmarks/test_querydsl_scaling.py -v -s
```

## Writing a New Test

### 1. Choose Category

- **integration/**: Tests Rust ↔ Python boundaries
- **benchmarks/**: Measures performance
- **scenarios/**: Demonstrates workflows
- **unit/**: Python-only unit tests

### 2. Use Template

```python
#!/usr/bin/env python3
"""Test {Feature} Integration

This test validates {what it validates}.
"""

import codegraph_ir
import pytest


def test_feature_basic(simple_python_repo):
    """Test basic feature functionality"""
    repo_path, filenames = simple_python_repo

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


@pytest.mark.benchmark
def test_feature_performance(codegraph_engine_path, perf):
    """Benchmark feature performance"""
    import time

    # Measure
    start = time.perf_counter()
    result = run_pipeline(str(codegraph_engine_path))
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Assert
    perf.assert_indexing_time(elapsed_ms, max_ms=3000, loc=238000)
```

### 3. Available Fixtures

From `conftest.py`:

```python
# Repository fixtures
simple_python_repo       # 3 files: module_a, module_b, utils
security_test_repo       # Auth module with SQL injection pattern
temp_repo               # Factory for custom repos

# Path fixtures
codegraph_engine_path   # Path to codegraph-engine
codegraph_ir_path       # Path to codegraph-ir

# Assertion helpers
perf.assert_indexing_time()
perf.assert_query_time()
perf.assert_conversion_rate()
```

### 4. Add Markers

```python
@pytest.mark.integration      # Integration test
@pytest.mark.benchmark        # Performance benchmark
@pytest.mark.slow            # Slow test (> 5s)
@pytest.mark.unit            # Unit test
```

## Common Tasks

### Test a New Feature

1. **Write integration test** in `integration/test_my_feature.py`
2. **Add fixtures** to `conftest.py` if needed
3. **Run test**: `pytest integration/test_my_feature.py -v`
4. **Commit both test and feature code**

### Add Performance Benchmark

1. **Create benchmark** in `benchmarks/test_my_feature_perf.py`
2. **Use @pytest.mark.benchmark** decorator
3. **Add performance assertions** using `perf` fixture
4. **Run**: `pytest benchmarks/test_my_feature_perf.py -v -s`

### Debug a Failing Test

```bash
# Run with full output
pytest tests/python/integration/test_failing.py -v -s

# Run with pdb
pytest tests/python/integration/test_failing.py --pdb

# Run with verbose logging
pytest tests/python/integration/test_failing.py -v --log-cli-level=DEBUG
```

### Update After Rust API Change

1. **Rebuild extension**: `make build-python`
2. **Run affected tests**: `pytest integration/ -v`
3. **Update test if needed**
4. **Verify all pass**: `make test-python`

## Performance Targets

Current targets (as of 2025-12-27):

| Metric | Target | Current |
|--------|--------|---------|
| Indexing (238K LOC) | < 3000ms | 1,653ms ✅ |
| Conversion (36K nodes) | < 100ms | 81ms ✅ |
| QueryEngine Init | < 500ms | 187ms ✅ |
| Avg Query Time | < 5ms | 0.002ms ✅ |

## Troubleshooting

### "ModuleNotFoundError: No module named 'codegraph_ir'"

```bash
cd packages/codegraph-rust/codegraph-ir
maturin develop --release
```

### "Import Error: codegraph_engine"

```bash
pip install -e packages/codegraph-shared
pip install -e packages/codegraph-engine
```

### "Tests not found"

```bash
# Run from correct directory
cd packages/codegraph-rust/codegraph-ir/tests/python
pytest -v
```

### "Permission denied" when creating temp files

```bash
# Check temp directory permissions
ls -la /tmp
# Or set TMPDIR
export TMPDIR=/path/to/writable/dir
```

## CI/CD

### Pull Request (Fast)
```bash
make test-python  # Excludes slow tests
```

### Nightly (Full)
```bash
make test-python-all  # Includes slow tests
```

### Benchmarks
```bash
make test-python-benchmark  # Performance tests
```

## Next Steps

- Read [README.md](README.md) for detailed guide
- See [TEST_ORGANIZATION.md](../../TEST_ORGANIZATION.md) for complete test structure
- Check [MIGRATION.md](MIGRATION.md) for migration details
- Review [conftest.py](conftest.py) for available fixtures

## Examples

### Run QueryDSL Integration Test
```bash
cd tests/python
pytest integration/test_querydsl_integration.py -v
```

Expected output:
```
test_querydsl_integration.py::test_querydsl_basic_queries PASSED
✓ Indexing: 3.46ms
✓ Conversion: 0.059ms
✓ QueryEngine Init: 117ms
✓ Avg Query: 0.002ms
```

### Run Scaling Benchmark
```bash
cd tests/python
pytest benchmarks/test_querydsl_scaling.py -v -s
```

Expected output:
```
codegraph-engine (238K LOC):
  Indexing:     1,653ms (86.0%)
  Conversion:      81ms ( 4.2%)
  Init:           187ms ( 9.7%)
  Total:        1,922ms
```

### Run Complete Workflow Demo
```bash
cd tests/python
python scenarios/complete_indexing_workflow.py
```

Shows data distribution to all backends (QueryEngine, Qdrant, PostgreSQL, SCIP).

## Tips

1. **Use fixtures**: Don't create repos manually, use `simple_python_repo` or `temp_repo`
2. **Mark slow tests**: Add `@pytest.mark.slow` for tests > 5s
3. **Use -s for debug**: `pytest -s` shows print statements
4. **Rebuild after changes**: Always `make build-python` after Rust changes
5. **Check conftest.py**: Many utilities already exist in conftest

## Help

Run `pytest --help` for full options or see:
- [Pytest documentation](https://docs.pytest.org/)
- [conftest.py](conftest.py) - Available fixtures
- [README.md](README.md) - Detailed test guide
