# Performance Tests

Benchmarks and performance regression tests.

## Contents (5 tests)

### Pipeline Benchmarks
- `test_pipeline_large_benchmark.rs` - Large repository benchmark
- `test_pipeline_ultra_large_benchmark.rs` - Ultra-large repository benchmark

### Component Performance
- `occurrence_arena_performance_test.rs` - Occurrence arena performance
- `test_repomap_performance.rs` - RepoMap performance
- `integration_lexical_performance.rs` - Lexical search performance

## Running Performance Tests

```bash
# Run all performance tests
cargo test --release --test 'performance/*'

# Run specific benchmark
cargo test --release --test performance/test_pipeline_large_benchmark

# With detailed timing
cargo test --release --test 'performance/*' -- --nocapture

# Generate performance report
cargo test --release --test 'performance/*' -- --nocapture > perf_report.txt
```

## Test Organization

Performance tests should:
- Measure execution time
- Track throughput metrics
- Detect performance regressions
- Use realistic data sizes
- Always run in release mode

## Performance Targets

| Component | Target | Measurement |
|-----------|--------|-------------|
| IR Build | > 10,000 nodes/sec | Large benchmark |
| Lexical Search | < 100ms | Search latency |
| RepoMap | < 500ms | Medium repo |
| Occurrence Arena | > 1M ops/sec | Arena operations |

## Benchmarking Best Practices

1. **Always use release mode**: `cargo test --release`
2. **Run multiple times**: Average results over 3+ runs
3. **Minimize background processes**: Close other applications
4. **Consistent hardware**: Use same machine for comparisons
5. **Track trends**: Compare with previous results
