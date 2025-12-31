# Unit Tests

Focused tests for individual components and functions.

## Contents (27 tests)

### Graph Builder Tests
- `graph_builder_tests.rs` - Core graph builder functionality
- `graph_builder_standalone_test.rs` - Standalone graph builder
- `graph_builder_integration_tests.rs` - Graph builder integration

### Cache Tests
- `test_cache_integration.rs` - Cache integration tests
- `test_ir_builder_cache.rs` - IR builder caching
- `test_orchestrator_cache.rs` - Orchestrator cache tests
- `test_incremental_build.rs` - Incremental build tests

### Storage Tests
- `test_storage_integration.rs` - Storage integration
- `test_sqlite_persistence.rs` - SQLite persistence tests

### SSA Tests
- `test_ssa_edge_cases.rs` - SSA edge cases
- `test_ssa_multi_language.rs` - Multi-language SSA

### Taint Analysis Tests
- `test_fqn_taint_integration.rs` - FQN taint integration
- `test_bfg_structural.rs` - BFG structural tests

### Pattern & Registry Tests
- `pattern_registry_integration_test.rs` - Pattern registry
- `pattern_registry_language_tests.rs` - Language-specific patterns
- `javascript_patterns_test.rs` - JavaScript patterns
- `inter_variable_test.rs` - Inter-variable tests

### SMT Tests
- `smt_integration_test.rs` - SMT solver integration
- `smt_edge_cases_test.rs` - SMT edge cases
- `z3_comparison_internal.rs` - Z3 solver comparison

### Clone Detection
- `test_clone_detection_edge_cases.rs` - Clone detection edge cases

### Lexical Tests
- `test_lexical_direct_integration.rs` - Direct lexical integration

### Misc Tests
- `test_dependency_graph_cycles.rs` - Dependency graph cycles
- `test_dependency_graph_extreme.rs` - Extreme dependency graphs
- `test_trcr_bindings.rs` - TRCR bindings

## Running Unit Tests

```bash
# Run all unit tests
cargo test --test 'unit/*'

# Run specific test
cargo test --test unit/test_cache_integration

# Run with output
cargo test --test 'unit/*' -- --nocapture
```

## Test Organization

Unit tests should:
- Test a single component or function
- Be fast (< 1 second)
- Have no external dependencies
- Be independent of other tests
