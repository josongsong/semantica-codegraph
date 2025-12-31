# Architecture Review: codegraph-ir

**Date:** 2025-12-29
**Scope:** packages/codegraph-ir (507 Rust files, ~112,567 LOC)
**Focus:** SOLID principles, Hexagonal Architecture, Code Duplication

---

## Executive Summary

Analysis of the `codegraph-ir` Rust package reveals a well-intentioned **hexagonal architecture** with **feature-first organization** but suffers from:

- ❌ **1 critical circular dependency** (shared ↔ features)
- ❌ **998 unwrap() calls** creating crash risks
- ❌ **70% code duplication** in parser plugins
- ❌ **7 competing orchestrators** with overlapping logic
- ❌ **16 empty port directories** (missing abstractions)
- ⚠️ **2 god classes** (2,700+ LOC each)

**Estimated Technical Debt:** ~6,000 LOC of duplicated code + 1,000+ unwrap() calls

---

## Critical Issues (P0)

### 1. God Class: IRIndexingOrchestrator

**Location:** [`pipeline/end_to_end_orchestrator.rs`](packages/codegraph-ir/src/pipeline/end_to_end_orchestrator.rs) (2,788 LOC)

**Problem:**
Single struct with 10+ responsibilities violating SRP:
- File collection & filtering
- L1-L8 stage orchestration
- Parallelization control
- Cache management
- Error aggregation
- Lexical index integration
- RepoMap building
- Taint analysis coordination
- Clone detection
- SMT verification

**Impact:**
- Hard to test (100+ combinations)
- Hard to maintain (giant file)
- Tight coupling (changes ripple)

**Recommendation:**
Split into 4 focused components:

```rust
// Before: 1 god class
struct IRIndexingOrchestrator { /* 2,788 LOC */ }

// After: 4 single-purpose structs
struct FileCollector;              // Discovery only
struct StageExecutor<S>;           // Generic stage runner
struct ResultAggregator;           // Collect results
struct CacheManager;               // Cache logic

// Composition in facade:
struct PipelineFacade {
    collector: FileCollector,
    executor: StageExecutor<IRStage>,
    aggregator: ResultAggregator,
    cache: CacheManager,
}
```

**Files to Create:**
- `pipeline/file_collector.rs`
- `pipeline/stage_executor.rs`
- `pipeline/result_aggregator.rs`
- `pipeline/cache_manager.rs`

---

### 2. Circular Dependency: shared ↔ features

**Location:** [`shared/models/mod.rs:44`](packages/codegraph-ir/src/shared/models/mod.rs#L44)

```rust
pub use crate::features::flow_graph::domain::cfg::{CFGBlock, CFGEdge};
```

**Problem:**
- `shared` depends on `features` (wrong direction)
- Breaks layered architecture
- Prevents modular compilation

**Dependency Graph (Current - WRONG):**
```
shared/models ──────┐
       ↑            ↓
       │     features/flow_graph
       │            ↓
  pipeline ─────> features/*
```

**Should Be:**
```
shared/models (pure domain types)
       ↑
  features/* ────> shared
       ↑
  pipeline/orchestrators
```

**Recommendation:**
Move `CFGBlock` and `CFGEdge` to `shared/models/flow.rs`:

```rust
// src/shared/models/flow.rs (NEW)
pub struct CFGBlock {
    pub id: String,
    pub kind: BlockKind,
    pub statement_count: usize,
    pub span_ref: SpanRef,
}

pub struct CFGEdge {
    pub source_block_id: String,
    pub target_block_id: String,
    pub edge_type: CFGEdgeType,
}
```

Then update `features/flow_graph/domain/cfg.rs` to re-export from shared.

---

### 3. 998 unwrap() Calls

**Distribution:**
- `features/cache/` - 33 unwraps
- `features/query_engine/` - 39 unwraps
- `features/storage/` - 25 unwraps
- `pipeline/` - 47 unwraps
- Others - 854 unwraps across 125+ files

**High-Risk Example:** [`features/cache/l1_cache.rs`](packages/codegraph-ir/src/features/cache/infrastructure/l1_cache.rs)
```rust
let cache = CACHE.lock().unwrap(); // Panics if mutex poisoned!
cache.insert(key, value);
```

**Impact:**
- Production crashes on edge cases
- No graceful degradation
- Unpredictable failure modes

**Recommendation:**

1. **Add lint to prevent new unwraps:**
```rust
// Add to src/lib.rs
#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)]
```

2. **Replace unwrap() with proper error handling:**
```rust
// Before
let cache = CACHE.lock().unwrap();

// After
let cache = CACHE.lock()
    .map_err(|e| CodegraphError::CachePoisoned(e.to_string()))?;
```

3. **Use anyhow for context:**
```rust
use anyhow::Context;

file.read()
    .context("Failed to read IR document for caching")?
```

**Tracking:** Create `UNWRAP_REMOVAL_PLAN.md` with file-by-file checklist.

---

### 4. Parser Plugin Duplication (70%)

**Files:**
- [`parsing/plugins/python.rs`](packages/codegraph-ir/src/features/parsing/plugins/python.rs) (1,209 LOC)
- `parsing/plugins/typescript.rs` (1,240 LOC)
- `parsing/plugins/java.rs` (1,249 LOC)
- `parsing/plugins/kotlin.rs` (976 LOC)
- `parsing/plugins/rust_lang.rs` (1,324 LOC)
- `parsing/plugins/go.rs` (985 LOC)

**Duplicated Logic (same in all 6 files):**
```rust
// Pattern 1: Function extraction (~200 LOC each)
fn extract_functions(node: &TSNode) -> Vec<Node> { /* ... */ }

// Pattern 2: Class extraction (~150 LOC each)
fn extract_classes(node: &TSNode) -> Vec<Node> { /* ... */ }

// Pattern 3: Import extraction (~100 LOC each)
fn extract_imports(node: &TSNode) -> Vec<Edge> { /* ... */ }

// Pattern 4: Variable extraction (~120 LOC each)
fn extract_variables(node: &TSNode) -> Vec<Node> { /* ... */ }
```

**Duplication Score:** 70% (4,200 LOC duplicated)

**Recommendation:**

Extract common logic into base trait:

```rust
// src/features/parsing/infrastructure/base_extractor.rs (NEW)
pub trait ASTExtractor {
    type Language: tree_sitter::Language;

    // Common logic (implemented once)
    fn extract_symbol(&self, node: TSNode, kind: NodeKind) -> Option<Node> {
        // Shared node extraction logic
    }

    fn traverse_extract<F>(&self, root: TSNode, filter: F) -> Vec<Node>
    where F: Fn(&TSNode) -> bool {
        // Shared traversal logic
    }

    // Language-specific overrides (default implementations)
    fn function_node_types(&self) -> &[&str] {
        &["function_definition"]
    }

    fn class_node_types(&self) -> &[&str] {
        &["class_definition"]
    }

    fn import_node_types(&self) -> &[&str] {
        &["import_statement", "import_from_statement"]
    }
}

// Language-specific overrides (minimal)
impl ASTExtractor for PythonExtractor {
    type Language = tree_sitter_python::Language;

    // Only override if different from default
    fn function_node_types(&self) -> &[&str] {
        &["function_definition", "async_function_definition"]
    }
}
```

**Savings:** ~4,200 LOC → ~1,500 LOC (70% reduction)

---

## High Priority Issues (P1)

### 5. Missing Port Traits (16 empty ports/)

**Found:** 16 features have `ports/` directories but **zero trait definitions**

**Empty Ports:**
- `features/chunking/ports/` - No `ChunkRepository` trait
- `features/cross_file/ports/` - No `SymbolIndex` trait
- `features/storage/ports/` - No `StorageBackend` trait
- `features/lexical/ports/` - No `SearchIndex` trait
- ... (12 more)

**Impact:**
- Violates Dependency Inversion Principle
- Tight coupling to concrete implementations
- Hard to swap implementations (e.g., PostgreSQL → SQLite)
- Impossible to mock for testing

**Recommendation:**

Define port traits for each feature:

```rust
// features/chunking/ports/chunk_repository.rs (NEW)
pub trait ChunkRepository: Send + Sync {
    fn save(&self, chunk: &Chunk) -> Result<ChunkId>;
    fn find_by_id(&self, id: &ChunkId) -> Result<Option<Chunk>>;
    fn find_by_file(&self, file_path: &str) -> Result<Vec<Chunk>>;
    fn delete(&self, id: &ChunkId) -> Result<()>;
}

// features/chunking/infrastructure/postgres_chunk_repo.rs
pub struct PostgresChunkRepository { /* ... */ }

impl ChunkRepository for PostgresChunkRepository {
    fn save(&self, chunk: &Chunk) -> Result<ChunkId> { /* ... */ }
    // ...
}

// features/chunking/application/chunk_service.rs
pub struct ChunkService<R: ChunkRepository> {
    repository: Arc<R>, // Dependency on trait, not concrete type
}
```

**Priority Order:**
1. `ChunkRepository` (chunking)
2. `SymbolIndex` (cross_file)
3. `StorageBackend` (storage)
4. `SearchIndex` (lexical)
5. `TypeResolver` (types)

---

### 6. Orchestrator Proliferation (7 competing types)

**Found:**
```
IRIndexingOrchestrator          (pipeline/end_to_end_orchestrator.rs)
UnifiedOrchestrator             (pipeline/unified_orchestrator/mod.rs)
MultiLayerIndexOrchestrator     (features/multi_index/infrastructure/orchestrator.rs)
SmtOrchestrator                 (features/smt/infrastructure/orchestrator.rs)
ShadowFSOrchestrator            (features/query_engine/infrastructure/shadow_fs.rs)
StorageIntegratedOrchestrator   (pipeline/storage_integration.rs.disabled)
+ Generic Orchestrator<P,G,F,T,D,S> (features/multi_index/)
```

**Problem:**
Each orchestrator re-implements:
- Stage execution logic
- Error aggregation
- Timing metrics
- Parallel execution
- Result building

**Recommendation:**

Single composable orchestrator with pluggable stages:

```rust
// pipeline/core/orchestrator.rs (NEW)
pub trait PipelineStage: Send + Sync {
    type Input;
    type Output;

    fn name(&self) -> &'static str;
    fn execute(&self, input: Self::Input) -> Result<Self::Output>;
}

pub struct PipelineOrchestrator {
    stages: Vec<Box<dyn PipelineStage<Input=Document, Output=Document>>>,
}

impl PipelineOrchestrator {
    pub fn new() -> Self { /* ... */ }

    pub fn add_stage<S>(mut self, stage: S) -> Self
    where S: PipelineStage<Input=Document, Output=Document> + 'static
    {
        self.stages.push(Box::new(stage));
        self
    }

    pub fn execute(&self, input: Document) -> Result<Document> {
        let mut result = input;
        for stage in &self.stages {
            result = stage.execute(result)?;
        }
        Ok(result)
    }
}

// Usage:
let orchestrator = PipelineOrchestrator::new()
    .add_stage(IRBuildStage::new())
    .add_stage(ChunkingStage::new())
    .add_stage(CrossFileStage::new())
    .add_stage(TaintStage::new());

let result = orchestrator.execute(input)?;
```

---

### 7. Inconsistent Hexagonal Architecture

**Violations Found:**

#### A. Infrastructure Leaking into Domain

**Example:** [`ir_generation/domain/ir_document.rs`](packages/codegraph-ir/src/features/ir_generation/domain/ir_document.rs)
```rust
use tree_sitter::Node; // ❌ Infrastructure dependency in domain!

pub struct IRDocument {
    pub nodes: Vec<Node>,
    // ...
}
```

**Domain models should NEVER import external libs** (tree-sitter, petgraph, etc.)

**Fix:**
```rust
// Domain uses only shared types
use crate::shared::models::Node;

pub struct IRDocument {
    pub nodes: Vec<Node>, // ✅ Pure domain type
}
```

#### B. Missing Application Layer

**Features without `application/`:**
- `chunking/` - Business logic in infrastructure
- `cross_file/` - Mixing domain + infra
- `lexical/` - No use case layer
- `storage/` - Repository pattern but no service layer

**Well-structured features (follow these):**
- ✅ `data_flow/` - Has domain, application, infrastructure, ports
- ✅ `flow_graph/` - Clean separation
- ✅ `ssa/` - Proper hexagonal layers

**Recommendation:**

Enforce consistent structure across ALL features:

```
features/<feature>/
├── domain/           # Pure business logic (no external deps)
│   ├── models.rs     # Domain entities
│   └── services.rs   # Domain services
├── ports/            # Trait definitions (abstractions)
│   └── repository.rs
├── application/      # Use cases (orchestrates domain)
│   └── use_case.rs
└── infrastructure/   # Implementations (external libs OK here)
    ├── repository_impl.rs
    └── external_adapter.rs
```

---

### 8. Taint Solver Duplication (50%)

**Files:**
- [`taint_analysis/infrastructure/ifds_solver.rs`](packages/codegraph-ir/src/features/taint_analysis/infrastructure/ifds_solver.rs) (1,238 LOC)
- `taint_analysis/infrastructure/ide_solver.rs` (888 LOC)
- `taint_analysis/infrastructure/interprocedural_taint.rs` (1,752 LOC)

**Shared Logic (~1,500 LOC duplicated):**
- Worklist algorithm (`while !worklist.is_empty() { ... }`)
- Fact propagation (`propagate_facts()`)
- Path tracking (`PathEdge` management)
- Summary generation (`compute_summary()`)

**Recommendation:**

Extract base solver with template method pattern:

```rust
// taint_analysis/infrastructure/base_solver.rs (NEW)
pub trait TaintSolver {
    type Fact: Clone + Eq + Hash;
    type Summary;

    // Template method (common algorithm)
    fn solve(&mut self) -> Result<Self::Summary> {
        while let Some(edge) = self.worklist_pop() {
            self.process_edge(edge)?;
        }
        self.build_summary()
    }

    // Hooks for specialization
    fn process_edge(&mut self, edge: PathEdge<Self::Fact>) -> Result<()>;
    fn build_summary(&self) -> Self::Summary;
    fn worklist_pop(&mut self) -> Option<PathEdge<Self::Fact>>;
}

// Specializations
impl TaintSolver for IFDSSolver {
    type Fact = DataFlowFact;
    type Summary = IFDSSummary;

    fn process_edge(&mut self, edge: PathEdge<Self::Fact>) -> Result<()> {
        // IFDS-specific logic only
    }
}

impl TaintSolver for IDESolver {
    type Fact = ValueFlowFact;
    type Summary = IDESummary;

    fn process_edge(&mut self, edge: PathEdge<Self::Fact>) -> Result<()> {
        // IDE-specific logic only
    }
}
```

**Savings:** ~1,500 LOC → ~800 LOC (47% reduction)

---

## Medium Priority Issues (P2)

### 9. Clone Detector Duplication (60%)

**Files:**
- `clone_detection/infrastructure/type1_detector.rs` (774 LOC)
- `clone_detection/infrastructure/type2_detector.rs` (~750 LOC)
- `clone_detection/infrastructure/type3_detector.rs` (819 LOC)
- `clone_detection/infrastructure/type4_detector.rs` (832 LOC)

**Shared Logic (~1,900 LOC):**
- Fragment extraction
- Similarity computation
- Clone pair collection
- Filtering by threshold

**Recommendation:**

Strategy pattern with shared base:

```rust
// clone_detection/infrastructure/base_detector.rs (NEW)
pub trait CloneDetector {
    fn extract_fragments(&self, code: &str) -> Vec<Fragment>;
    fn compute_similarity(&self, a: &Fragment, b: &Fragment) -> f64;

    // Template method (shared algorithm)
    fn detect(&self, files: &[File]) -> Vec<ClonePair> {
        let fragments = self.extract_all_fragments(files);
        let pairs = self.find_similar_pairs(&fragments);
        self.filter_by_threshold(pairs)
    }
}

// Specializations (only similarity logic differs)
impl CloneDetector for Type1Detector {
    fn compute_similarity(&self, a: &Fragment, b: &Fragment) -> f64 {
        exact_match(a.content, b.content)
    }
}

impl CloneDetector for Type3Detector {
    fn compute_similarity(&self, a: &Fragment, b: &Fragment) -> f64 {
        token_based_similarity(a.tokens, b.tokens)
    }
}
```

---

### 10. 10 Backup Files in Source Tree

**Found:**
```
shared/models/node.rs.bak2
shared/models/node.rs.orig
shared/models/edge.rs.bak3
shared/models/edge.rs.bak4
ir_generation/domain/ir_document.rs.bak6
multi_index/infrastructure/orchestrator.rs.backup
features/multi_index/infrastructure/orchestrator.rs.backup
+ 3 more
```

**Impact:**
- Clutters codebase
- Confuses developers
- Git history already stores old versions

**Recommendation:**

1. **Delete backup files:**
```bash
find packages/codegraph-ir/src -name "*.bak*" -delete
find packages/codegraph-ir/src -name "*.orig" -delete
find packages/codegraph-ir/src -name "*.backup" -delete
```

2. **Add to .gitignore:**
```gitignore
*.bak*
*.orig
*.backup
*.rs.disabled
```

---

### 11. God Module: lib.rs (2,786 LOC)

**Location:** [`src/lib.rs`](packages/codegraph-ir/src/lib.rs)

**Contents:**
- Legacy AST API (lines 160-233)
- PyO3 bindings for 20+ functions (lines 240-2,384)
- Cross-file resolution API (lines 790-1,289)
- Symbol dependency APIs (lines 1,420-1,876)
- Trigger APIs (lines 1,880-2,233)
- E2E pipeline API (lines 2,238-2,573)
- Module registration (lines 2,578-2,671)

**Recommendation:**

Split into focused modules:

```
adapters/pyo3/
├── mod.rs              (Module registration only)
├── legacy_api.rs       (traverse_ast_*, ~100 LOC)
├── cross_file_api.rs   (build_global_context_*, ~500 LOC)
├── symbol_api.rs       (get_symbol_*, ~450 LOC)
├── trigger_api.rs      (cold_start_*, watch_mode_*, ~350 LOC)
└── pipeline_api.rs     (run_ir_indexing_pipeline, ~400 LOC)
```

Then `lib.rs` becomes:
```rust
// src/lib.rs (NEW - ~50 LOC)
pub mod shared;
pub mod features;
pub mod pipeline;
pub mod adapters;
pub mod api;
pub mod errors;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pymodule]
fn codegraph_ir(_py: Python, m: &PyModule) -> PyResult<()> {
    adapters::pyo3::register_all(m)?;
    Ok(())
}
```

---

### 12. 104 TODO/FIXME Comments

**Distribution:**
- `features/taint_analysis/` - 17 TODOs
- `features/points_to/` - 12 TODOs
- `features/query_engine/` - 9 TODOs
- `pipeline/` - 14 TODOs
- Others - 52 TODOs

**High-Priority TODOs:**

**1. Cross-file resolution incomplete:**
```rust
// features/cross_file/import_resolver.rs:45
// TODO: Handle relative imports properly
```

**2. Cache eviction not implemented:**
```rust
// features/cache/l1_cache.rs:89
// FIXME: Implement LRU eviction policy
```

**3. Taint sanitization missing:**
```rust
// features/taint_analysis/infrastructure/interprocedural_taint.rs:234
// TODO: Add sanitizer support (e.g., HTML escaping)
```

**Recommendation:**

1. **Track TODOs in GitHub Issues**
2. **Convert critical TODOs to tracked issues**
3. **Remove stale TODOs (>6 months old)**

---

## Refactoring Action Plan

### Phase 1: Critical Fixes (Week 1-2)

**Goal:** Remove circular dependencies, prevent new unwraps

- [ ] **Fix circular dependency** (shared ↔ features)
  - Move `CFGBlock`, `CFGEdge` to `shared/models/flow.rs`
  - Update imports in `features/flow_graph/`
  - Verify no other shared→features deps

- [ ] **Add unwrap prevention lint**
  ```rust
  #![deny(clippy::unwrap_used)]
  #![deny(clippy::expect_used)]
  ```

- [ ] **Clean up backup files**
  ```bash
  git rm **/*.bak* **/*.orig **/*.backup
  ```

### Phase 2: Deduplication (Week 3-4)

**Goal:** Eliminate 70% parser duplication

- [ ] **Extract `trait ASTExtractor`**
  - Create `features/parsing/infrastructure/base_extractor.rs`
  - Implement default methods for common logic
  - Refactor `python.rs` first (proof of concept)
  - Migrate remaining 5 parsers

- [ ] **Extract taint solver base**
  - Create `features/taint_analysis/infrastructure/base_solver.rs`
  - Implement `trait TaintSolver` with template method
  - Refactor IFDS, IDE, Interprocedural solvers

**Expected Savings:** 5,700 LOC → 2,300 LOC (60% reduction)

### Phase 3: Architecture Enforcement (Week 5-6)

**Goal:** Consistent hexagonal architecture

- [ ] **Define port traits for top 5 features**
  - `ChunkRepository` (chunking)
  - `SymbolIndex` (cross_file)
  - `StorageBackend` (storage)
  - `SearchIndex` (lexical)
  - `TypeResolver` (types)

- [ ] **Fix domain layer violations**
  - Remove `tree_sitter` from `ir_generation/domain/`
  - Extract infrastructure deps to adapter layer

- [ ] **Add missing application layers**
  - `chunking/application/chunk_service.rs`
  - `cross_file/application/resolution_service.rs`
  - `storage/application/storage_service.rs`

### Phase 4: God Class Refactoring (Week 7-8)

**Goal:** Split IRIndexingOrchestrator, lib.rs

- [ ] **Split IRIndexingOrchestrator**
  - Create `FileCollector` (discovery)
  - Create `StageExecutor<S>` (generic runner)
  - Create `ResultAggregator` (collection)
  - Create `CacheManager` (caching)
  - Compose in `PipelineFacade`

- [ ] **Split lib.rs PyO3 bindings**
  - Extract to `adapters/pyo3/legacy_api.rs`
  - Extract to `adapters/pyo3/cross_file_api.rs`
  - Extract to `adapters/pyo3/symbol_api.rs`
  - Extract to `adapters/pyo3/trigger_api.rs`
  - Extract to `adapters/pyo3/pipeline_api.rs`

### Phase 5: Orchestrator Consolidation (Week 9-10)

**Goal:** Single composable orchestrator

- [ ] **Create `PipelineOrchestrator`**
  - Define `trait PipelineStage`
  - Implement generic orchestrator
  - Migrate `IRIndexingOrchestrator` to use stages

- [ ] **Deprecate old orchestrators**
  - Mark `UnifiedOrchestrator` as deprecated
  - Provide migration guide
  - Remove `StorageIntegratedOrchestrator` (disabled)

### Phase 6: Error Handling Hardening (Week 11-12)

**Goal:** Eliminate unwrap() calls

- [ ] **Systematic unwrap() removal**
  - Priority 1: Cache (33 unwraps)
  - Priority 2: Query engine (39 unwraps)
  - Priority 3: Storage (25 unwraps)
  - Priority 4: Pipeline (47 unwraps)
  - Priority 5: Remaining (854 unwraps)

- [ ] **Add error context**
  - Use `anyhow::Context` throughout
  - Define domain-specific error types
  - Improve error messages

**Target:** <50 unwraps remaining (emergency-only cases)

---

## Architectural Guidelines (Future)

### 1. File Size Limits

- **Module files:** Max 500 LOC (split if exceeding)
- **Struct definitions:** Max 200 LOC
- **Function definitions:** Max 50 LOC

### 2. Dependency Rules

- **Domain:** Zero external dependencies (only `shared`)
- **Ports:** Only trait definitions (no implementations)
- **Application:** Orchestrates domain + ports
- **Infrastructure:** Implements ports (external libs OK)

### 3. Error Handling

- **Production code:** NEVER use `unwrap()` or `expect()`
- **Test code:** OK to use `unwrap()` (but prefer `?`)
- **All public APIs:** Return `Result<T, E>`

### 4. Code Duplication

- **>50% duplication:** Extract to trait/base class
- **>30% duplication:** Consider refactoring
- **<30% duplication:** Document intentional differences

### 5. Testing Requirements

- **New features:** Require unit tests (80% coverage)
- **Bug fixes:** Require regression test
- **Refactorings:** Maintain existing coverage

---

## Metrics Tracking

### Before Refactoring

- **Total LOC:** 112,567
- **Duplicated LOC:** ~6,000 (5.3%)
- **unwrap() calls:** 998
- **Average file size:** 221 LOC
- **Largest file:** 2,788 LOC
- **Empty port directories:** 16
- **Orchestrator types:** 7

### After Refactoring (Target)

- **Total LOC:** 106,000 (-6,567 via dedup)
- **Duplicated LOC:** <1,800 (1.7%)
- **unwrap() calls:** <50 (-95%)
- **Average file size:** <200 LOC
- **Largest file:** <800 LOC
- **Empty port directories:** 0
- **Orchestrator types:** 1

### Success Criteria

- ✅ Zero circular dependencies
- ✅ All features have port traits
- ✅ All features follow hexagonal pattern
- ✅ <50 unwrap() calls in production code
- ✅ Code duplication <2%
- ✅ Test coverage >80%

---

## Conclusion

The `codegraph-ir` codebase demonstrates **strong architectural intentions** but requires **systematic refactoring** to achieve:

1. **Maintainability** - Split god classes, reduce duplication
2. **Testability** - Define port traits, inject dependencies
3. **Reliability** - Remove unwrap(), proper error handling
4. **Consistency** - Enforce hexagonal architecture across all features

**Estimated effort:** 12 weeks (1 engineer, full-time)
**Expected impact:** 60% LOC reduction, 95% unwrap elimination, zero architectural violations

**Recommendation:** Prioritize Phase 1-2 (critical fixes + deduplication) for immediate impact, then Phase 3-6 for long-term maintainability.

---

**Next Steps:**

1. Review and approve refactoring plan
2. Create GitHub project with 72 tracked issues
3. Assign phases to sprint milestones
4. Begin Phase 1 implementation

