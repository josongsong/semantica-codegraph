# Integration Tests

Tests for component integration and inter-module interactions.

## Contents (25 tests)

### Orchestrator Integration
- `test_unified_orchestrator.rs` - Unified orchestrator
- `test_lexical_orchestrator_integration.rs` - Lexical orchestrator
- `integration_lexical_orchestrator.rs` - Lexical integration

### Language-Specific Integration
- `integration_lambda_closures.rs` - Lambda and closures
- `integration_async_decorators.rs` - Async decorators
- `integration_ssa.rs` - SSA integration
- `integration_cost_analysis.rs` - Cost analysis
- `typescript_parsing.rs` - TypeScript parsing
- `python_parsing.rs` - Python parsing

### Lexical Search Integration
- `integration_lexical_search.rs` - Lexical search
- `test_lexical_incremental_update.rs` - Incremental updates

### Clone Detection
- `test_clone_detection_integration.rs` - Clone detection integration

### Database Integration
- `test_postgres_integration.rs` - PostgreSQL integration
- `test_postgres_edge_cases.rs` - PostgreSQL edge cases

### Pipeline Integration
- `test_smart_mode_integration.rs` - Smart mode
- `test_pipeline_hybrid_integration.rs` - Hybrid pipeline
- `phase1_integration_test.rs` - Phase 1 integration

### Query & Analysis
- `test_extended_querydsl.rs` - Extended QueryDSL
- `test_fqn_e2e_integration.rs` - FQN E2E integration
- `test_l14_e2e_trcr.rs` - L14 TRCR integration

## Running Integration Tests

```bash
# Run all integration tests
cargo test --test 'integration/*'

# Run specific test
cargo test --test integration/test_unified_orchestrator

# Run with logging
RUST_LOG=debug cargo test --test 'integration/*' -- --nocapture
```

## Test Organization

Integration tests should:
- Test interactions between components
- May require external services (DB, etc.)
- Can be slower than unit tests
- Test realistic workflows
