# Stress Tests

High-load and extreme scenario tests to verify system stability.

## Contents (3 tests)

### Cache Stress Tests
- `test_cache_stress.rs` - Cache under heavy load
  - Concurrent access tests
  - Memory pressure scenarios
  - Cache eviction stress

### Storage Stress Tests
- `test_sqlite_stress.rs` - SQLite under extreme load
  - Large-scale data insertion
  - Concurrent write/read operations
  - Transaction stress

### Orchestrator Stress Tests
- `test_unified_orchestrator_stress.rs` - Orchestrator stress testing
  - Large repository processing
  - Memory usage verification
  - Parallel execution stress

## Running Stress Tests

```bash
# Run all stress tests
cargo test --test 'stress/*'

# Run in release mode (recommended)
cargo test --release --test 'stress/*'

# Run with increased stack size if needed
RUST_MIN_STACK=8388608 cargo test --test 'stress/*'

# Monitor resource usage
cargo test --release --test 'stress/*' -- --nocapture
```

## Test Organization

Stress tests should:
- Push system limits
- Verify behavior under extreme conditions
- Check for memory leaks
- Test concurrent access scenarios
- May take several seconds to run

## Resource Requirements

Stress tests may require:
- 4GB+ RAM
- 2GB+ disk space
- Multi-core CPU for parallel tests
- Run in release mode for realistic performance
