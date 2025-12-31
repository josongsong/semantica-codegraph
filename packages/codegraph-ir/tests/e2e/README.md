# End-to-End Tests

Comprehensive tests covering complete workflows from start to finish.

## Contents (11 tests)

### P0 Critical Tests
- `test_p0_comprehensive.rs` - Comprehensive P0 scenarios
- `test_p0_extreme_scenarios.rs` - Extreme edge cases
- `test_p0_modules.rs` - Module-level P0 tests

### Pipeline E2E Tests
- `test_e2e_simple.rs` - Simple end-to-end pipeline
- `test_e2e_real_world.rs` - Real-world repository tests
- `test_e2e_23_levels.rs` - Deep nesting (23 levels)
- `test_e2e_clone_pipeline_waterfall.rs` - Clone detection pipeline
- `test_e2e_querydsl_integration.rs` - QueryDSL end-to-end

### Orchestrator E2E
- `test_unified_orchestrator_e2e.rs` - Unified orchestrator E2E
- `test_postgres_pipeline_e2e.rs` - PostgreSQL pipeline E2E

### Phase Tests
- `test_phase4_comprehensive.rs` - Phase 4 comprehensive tests

## Running E2E Tests

```bash
# Run all E2E tests
cargo test --test 'e2e/*'

# Run specific test
cargo test --test e2e/test_p0_comprehensive

# Run with release mode (faster for large tests)
cargo test --release --test 'e2e/*'

# Run with timeout
cargo test --test 'e2e/*' -- --test-threads=1
```

## Test Organization

E2E tests should:
- Test complete user workflows
- Use realistic data and scenarios
- May take longer (1-30 seconds)
- Verify end-to-end correctness
- Can use external services

## Performance Notes

Some E2E tests process large codebases:
- `test_e2e_23_levels.rs` - Deep nesting scenarios
- `test_p0_comprehensive.rs` - Multiple comprehensive checks
- Run these in release mode for better performance
