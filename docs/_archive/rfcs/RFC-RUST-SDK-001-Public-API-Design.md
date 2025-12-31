# RFC-RUST-SDK-001: Rust Public API & Extended QueryDSL

**Status**: Draft
**Author**: CodeGraph Team
**Created**: 2024-12-28
**Updated**: 2024-12-28
**Supersedes**: None
**Related**: RFC-SDK-001 (Python SDK - depends on this)

---

## 0. Meta

### 0.1 Document Purpose
This RFC defines the Rust public API for `codegraph-ir`, including:
1. **Clean Public API**: FFI-safe entry points for Python/other languages
2. **Extended QueryDSL**: Unified query interface covering ALL use cases
3. **Type System**: FFI-compatible data structures

### 0.2 Motivation

**Current Problems**:
```rust
// ❌ Problem 1: No unified entry point
let orchestrator = IRIndexingOrchestrator::new(config); // Too specific
let result = orchestrator.execute()?; // Returns E2EPipelineResult (all-in-memory)

// ❌ Problem 2: QueryDSL only handles path queries
let engine = QueryEngine::new(&ir_doc);
let paths = engine.execute(Q::var("user") >> Q::call("exec")); // OK
let nodes = engine.filter_nodes(|n| n.kind == "function")?; // ❌ Doesn't exist!

// ❌ Problem 3: No FFI-safe types
#[pyclass] // ❌ Can't derive - contains non-FFI-safe types
pub struct E2EPipelineResult {
    pub nodes: Vec<Node>,  // OK
    pub chunks: Vec<Chunk>,  // OK
    pub repomap_snapshot: Option<RepoMapSnapshotSummary>,  // ❌ Complex nested type
}
```

**Desired API**:
```rust
// ✅ Solution 1: Unified entry point
let engine = CodeGraphEngine::new("/path/to/repo")?;
let result = engine.index()
    .with_taint()
    .with_repomap()
    .execute()?;

// ✅ Solution 2: Extended QueryDSL covers ALL queries
// Path queries (existing)
let paths = engine.query()
    .path(Q::var("user") >> Q::call("exec"))
    .execute()?;

// Filtering queries (NEW)
let nodes = engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .where_field("language", "python")
    .limit(100)
    .execute()?;

// Aggregation queries (NEW)
let stats = engine.query()
    .nodes()
    .aggregate()
    .count()
    .avg("complexity")
    .execute()?;

// ✅ Solution 3: FFI-safe types
#[repr(C)]
#[derive(Debug, Clone)]
pub struct NodeFFI {
    pub id: *const c_char,  // FFI-safe
    pub kind: NodeKindFFI,  // enum with #[repr(u8)]
    pub name: *const c_char,
    // ... simple fields only
}
```

---

## 1. Executive Summary

### 1.1 Proposed Changes

**Three-layer architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Public Rust API (codegraph-ir/src/lib.rs)         │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ CodeGraphEngine  │  │ ExtendedQueryDSL │               │
│  │ (Entry Point)    │  │ (All Queries)    │               │
│  └────────┬─────────┘  └────────┬─────────┘               │
│           │                      │                          │
│           └──────────┬───────────┘                          │
└──────────────────────┼──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: FFI Bridge (codegraph-ir/src/ffi/)                │
│  • #[repr(C)] structs                                       │
│  • #[no_mangle] pub extern "C" functions                   │
│  • Arrow IPC serialization                                  │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: PyO3 Bindings (Optional - future work)            │
│  • #[pyclass], #[pymethods]                                 │
│  • Python-specific conveniences                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 QueryDSL Coverage Analysis

**Use Cases to Cover**:

| Use Case | Current QueryDSL | Extended QueryDSL | Notes |
|----------|------------------|-------------------|-------|
| **1. Path Queries** | ✅ Supported | ✅ Keep as-is | `Q::var("x") >> Q::call("y")` |
| **2. Node Filtering** | ❌ Missing | ✅ NEW | `nodes().filter(kind=Function)` |
| **3. Aggregation** | ❌ Missing | ✅ NEW | `nodes().aggregate().count()` |
| **4. Join Queries** | ❌ Missing | ✅ NEW | `nodes().join(edges).on("id")` |
| **5. Taint Flows** | ❌ Missing | ✅ NEW | `taint_flows().filter(severity=Critical)` |
| **6. Clone Pairs** | ❌ Missing | ✅ NEW | `clone_pairs().filter(similarity > 0.9)` |
| **7. Streaming** | ❌ Missing | ✅ NEW | `nodes().stream(chunk_size=1000)` |
| **8. Pagination** | ❌ Missing | ✅ NEW | `nodes().limit(100).offset(50)` |

**Conclusion**: ✅ **YES, QueryDSL can cover ALL use cases with proper extensions**

---

## 2. Public API Design

### 2.1 Entry Point: `CodeGraphEngine`

```rust
// codegraph-ir/src/lib.rs

use std::path::PathBuf;

/// Main entry point for CodeGraph analysis engine
///
/// # Examples
///
/// ```rust
/// use codegraph_ir::CodeGraphEngine;
///
/// // Simple indexing
/// let engine = CodeGraphEngine::new("/path/to/repo")?;
/// let result = engine.index().execute()?;
///
/// // With features
/// let result = engine.index()
///     .with_taint()
///     .with_repomap()
///     .parallel(8)
///     .execute()?;
/// ```
pub struct CodeGraphEngine {
    config: EngineConfig,
    state: EngineState,
}

impl CodeGraphEngine {
    /// Create new engine with default configuration
    pub fn new<P: Into<PathBuf>>(repo_path: P) -> Result<Self> {
        let config = EngineConfig {
            repo_path: repo_path.into(),
            ..Default::default()
        };
        Ok(Self {
            config,
            state: EngineState::Uninitialized,
        })
    }

    /// Start indexing pipeline with builder pattern
    pub fn index(&mut self) -> IndexBuilder {
        IndexBuilder::new(&mut self.config)
    }

    /// Query the indexed repository
    ///
    /// Must call `index().execute()` first
    pub fn query(&self) -> QueryBuilder {
        assert!(self.state.is_indexed(), "Must index repository first");
        QueryBuilder::new(&self.state)
    }

    /// Get indexing statistics
    pub fn stats(&self) -> &IndexStats {
        &self.state.stats
    }
}

/// Builder for configuring indexing pipeline
///
/// Follows Stripe-style builder pattern
pub struct IndexBuilder<'a> {
    config: &'a mut EngineConfig,
}

impl<'a> IndexBuilder<'a> {
    /// Enable taint analysis (L14)
    pub fn with_taint(self) -> Self {
        self.config.stages.enable_taint = true;
        self
    }

    /// Enable RepoMap with PageRank (L16)
    pub fn with_repomap(self) -> Self {
        self.config.stages.enable_repomap = true;
        self
    }

    /// Enable clone detection (L10)
    pub fn with_clone_detection(self) -> Self {
        self.config.stages.enable_clone_detection = true;
        self
    }

    /// Set number of parallel workers
    pub fn parallel(self, workers: usize) -> Self {
        self.config.parallel_workers = workers;
        self
    }

    /// Set indexing mode
    pub fn mode(self, mode: IndexingMode) -> Self {
        self.config.mode = mode;
        self
    }

    /// Execute indexing pipeline
    pub fn execute(self) -> Result<IndexResult> {
        // Delegate to IRIndexingOrchestrator
        let orchestrator = IRIndexingOrchestrator::new(self.config.clone());
        let result = orchestrator.execute()?;

        // Convert to public API result
        Ok(IndexResult::from(result))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IndexingMode {
    /// Re-index entire repository
    Full,
    /// Only process changed files (requires cache)
    Incremental,
    /// Auto-detect based on repository characteristics
    Smart,
}

/// Public indexing result (simplified from E2EPipelineResult)
#[derive(Debug, Clone)]
pub struct IndexResult {
    pub stats: IndexStats,
    pub errors: Vec<AnalysisError>,
}

#[derive(Debug, Clone, Default)]
pub struct IndexStats {
    pub total_files: usize,
    pub total_nodes: usize,
    pub total_edges: usize,
    pub total_chunks: usize,
    pub duration_ms: u64,
    pub stages_completed: Vec<String>,
}
```

### 2.2 Extended QueryDSL

```rust
// codegraph-ir/src/query/mod.rs

pub mod builder;
pub mod filters;
pub mod aggregation;
pub mod streaming;

pub use builder::QueryBuilder;

/// Unified query builder supporting all query types
///
/// # Query Types
///
/// 1. **Path Queries**: Graph traversal (existing)
/// 2. **Filter Queries**: Node/edge filtering (new)
/// 3. **Aggregation Queries**: Statistics (new)
/// 4. **Join Queries**: Multi-entity queries (new)
pub struct QueryBuilder<'a> {
    state: &'a EngineState,
}

impl<'a> QueryBuilder<'a> {
    // ═══════════════════════════════════════════════════════════════
    // Query Type Selection
    // ═══════════════════════════════════════════════════════════════

    /// Query nodes (functions, classes, etc.)
    pub fn nodes(self) -> NodeQueryBuilder<'a> {
        NodeQueryBuilder::new(self.state)
    }

    /// Query edges (calls, references, etc.)
    pub fn edges(self) -> EdgeQueryBuilder<'a> {
        EdgeQueryBuilder::new(self.state)
    }

    /// Query taint flows
    pub fn taint_flows(self) -> TaintQueryBuilder<'a> {
        TaintQueryBuilder::new(self.state)
    }

    /// Query clone pairs
    pub fn clone_pairs(self) -> CloneQueryBuilder<'a> {
        CloneQueryBuilder::new(self.state)
    }

    /// Query paths (existing QueryEngine DSL)
    pub fn path(self, expr: PathQuery) -> PathQueryBuilder<'a> {
        PathQueryBuilder::new(self.state, expr)
    }
}

// ═══════════════════════════════════════════════════════════════
// Node Query Builder
// ═══════════════════════════════════════════════════════════════

pub struct NodeQueryBuilder<'a> {
    state: &'a EngineState,
    filters: Vec<NodeFilter>,
    order_by: Vec<(String, Order)>,
    limit: Option<usize>,
    offset: Option<usize>,
}

impl<'a> NodeQueryBuilder<'a> {
    /// Filter by node kind
    pub fn filter(mut self, kind: NodeKind) -> Self {
        self.filters.push(NodeFilter::Kind(kind));
        self
    }

    /// Filter by field value
    pub fn where_field<V: Into<FilterValue>>(mut self, field: &str, value: V) -> Self {
        self.filters.push(NodeFilter::Field {
            name: field.to_string(),
            value: value.into(),
            op: FilterOp::Eq,
        });
        self
    }

    /// Filter by predicate function
    pub fn where_fn<F>(mut self, predicate: F) -> Self
    where
        F: Fn(&Node) -> bool + 'static,
    {
        self.filters.push(NodeFilter::Custom(Box::new(predicate)));
        self
    }

    /// Order results
    pub fn order_by(mut self, field: &str, order: Order) -> Self {
        self.order_by.push((field.to_string(), order));
        self
    }

    /// Limit results
    pub fn limit(mut self, n: usize) -> Self {
        self.limit = Some(n);
        self
    }

    /// Skip first n results
    pub fn offset(mut self, n: usize) -> Self {
        self.offset = Some(n);
        self
    }

    /// Execute query and collect results
    pub fn execute(self) -> Result<Vec<Node>> {
        // Apply filters
        let mut nodes: Vec<Node> = self.state.nodes
            .iter()
            .filter(|node| self.filters.iter().all(|f| f.matches(node)))
            .cloned()
            .collect();

        // Apply ordering
        for (field, order) in self.order_by.iter().rev() {
            nodes.sort_by(|a, b| {
                let cmp = compare_field(a, b, field);
                match order {
                    Order::Asc => cmp,
                    Order::Desc => cmp.reverse(),
                }
            });
        }

        // Apply pagination
        if let Some(offset) = self.offset {
            nodes = nodes.into_iter().skip(offset).collect();
        }
        if let Some(limit) = self.limit {
            nodes.truncate(limit);
        }

        Ok(nodes)
    }

    /// Execute query with streaming (memory-efficient)
    pub fn stream(self, chunk_size: usize) -> Result<NodeStream> {
        Ok(NodeStream {
            inner: Box::new(NodeStreamImpl::new(self, chunk_size)),
        })
    }

    /// Aggregate results
    pub fn aggregate(self) -> AggregationBuilder<'a> {
        AggregationBuilder::new(self)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Order {
    Asc,
    Desc,
}

// ═══════════════════════════════════════════════════════════════
// Aggregation Builder
// ═══════════════════════════════════════════════════════════════

pub struct AggregationBuilder<'a> {
    query: NodeQueryBuilder<'a>,
    aggregations: Vec<Aggregation>,
}

impl<'a> AggregationBuilder<'a> {
    /// Count results
    pub fn count(mut self) -> Self {
        self.aggregations.push(Aggregation::Count);
        self
    }

    /// Average of field
    pub fn avg(mut self, field: &str) -> Self {
        self.aggregations.push(Aggregation::Avg(field.to_string()));
        self
    }

    /// Sum of field
    pub fn sum(mut self, field: &str) -> Self {
        self.aggregations.push(Aggregation::Sum(field.to_string()));
        self
    }

    /// Min/Max of field
    pub fn min(mut self, field: &str) -> Self {
        self.aggregations.push(Aggregation::Min(field.to_string()));
        self
    }

    pub fn max(mut self, field: &str) -> Self {
        self.aggregations.push(Aggregation::Max(field.to_string()));
        self
    }

    /// Execute aggregations
    pub fn execute(self) -> Result<AggregationResult> {
        let nodes = self.query.execute()?;

        let mut result = AggregationResult::default();

        for agg in &self.aggregations {
            match agg {
                Aggregation::Count => {
                    result.count = Some(nodes.len());
                }
                Aggregation::Avg(field) => {
                    let values: Vec<f64> = nodes.iter()
                        .filter_map(|n| extract_numeric_field(n, field))
                        .collect();
                    result.avg = Some(values.iter().sum::<f64>() / values.len() as f64);
                }
                // ... other aggregations
            }
        }

        Ok(result)
    }
}

#[derive(Debug, Clone, Default)]
pub struct AggregationResult {
    pub count: Option<usize>,
    pub avg: Option<f64>,
    pub sum: Option<f64>,
    pub min: Option<f64>,
    pub max: Option<f64>,
}

// ═══════════════════════════════════════════════════════════════
// Streaming Support
// ═══════════════════════════════════════════════════════════════

/// Streaming iterator over nodes (memory-efficient)
pub struct NodeStream {
    inner: Box<dyn Iterator<Item = Vec<Node>> + Send>,
}

impl Iterator for NodeStream {
    type Item = Vec<Node>;

    fn next(&mut self) -> Option<Self::Item> {
        self.inner.next()
    }
}

struct NodeStreamImpl<'a> {
    query: NodeQueryBuilder<'a>,
    chunk_size: usize,
    offset: usize,
}

impl<'a> NodeStreamImpl<'a> {
    fn new(query: NodeQueryBuilder<'a>, chunk_size: usize) -> Self {
        Self {
            query,
            chunk_size,
            offset: 0,
        }
    }
}

impl<'a> Iterator for NodeStreamImpl<'a> {
    type Item = Vec<Node>;

    fn next(&mut self) -> Option<Self::Item> {
        let mut query = self.query.clone();
        query.offset = Some(self.offset);
        query.limit = Some(self.chunk_size);

        match query.execute() {
            Ok(nodes) if !nodes.is_empty() => {
                self.offset += nodes.len();
                Some(nodes)
            }
            _ => None,
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// Taint Query Builder (Specialized)
// ═══════════════════════════════════════════════════════════════

pub struct TaintQueryBuilder<'a> {
    state: &'a EngineState,
    filters: Vec<TaintFilter>,
}

impl<'a> TaintQueryBuilder<'a> {
    /// Filter by severity
    pub fn severity(mut self, severity: Severity) -> Self {
        self.filters.push(TaintFilter::Severity(severity));
        self
    }

    /// Filter by vulnerability type (CWE)
    pub fn vulnerability_type(mut self, cwe: &str) -> Self {
        self.filters.push(TaintFilter::VulnerabilityType(cwe.to_string()));
        self
    }

    /// Filter by confidence threshold
    pub fn min_confidence(mut self, threshold: f64) -> Self {
        self.filters.push(TaintFilter::MinConfidence(threshold));
        self
    }

    /// Execute query
    pub fn execute(self) -> Result<Vec<TaintFlow>> {
        let flows: Vec<TaintFlow> = self.state.taint_flows
            .iter()
            .filter(|flow| self.filters.iter().all(|f| f.matches(flow)))
            .cloned()
            .collect();

        Ok(flows)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Critical,
    High,
    Medium,
    Low,
}

// ═══════════════════════════════════════════════════════════════
// Clone Query Builder (Specialized)
// ═══════════════════════════════════════════════════════════════

pub struct CloneQueryBuilder<'a> {
    state: &'a EngineState,
    filters: Vec<CloneFilter>,
}

impl<'a> CloneQueryBuilder<'a> {
    /// Filter by clone type (Type 1-4)
    pub fn clone_type(mut self, ty: CloneType) -> Self {
        self.filters.push(CloneFilter::Type(ty));
        self
    }

    /// Filter by minimum similarity
    pub fn min_similarity(mut self, threshold: f64) -> Self {
        self.filters.push(CloneFilter::MinSimilarity(threshold));
        self
    }

    /// Execute query
    pub fn execute(self) -> Result<Vec<ClonePair>> {
        let pairs: Vec<ClonePair> = self.state.clone_pairs
            .iter()
            .filter(|pair| self.filters.iter().all(|f| f.matches(pair)))
            .cloned()
            .collect();

        Ok(pairs)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloneType {
    Type1,  // Exact clones (whitespace differs)
    Type2,  // Renamed identifiers
    Type3,  // Modified statements
    Type4,  // Semantic clones (different syntax, same behavior)
}
```

---

## 3. FFI-Safe Types

### 3.1 Core Principle

**Rule**: Only expose simple, #[repr(C)] types across FFI boundary

```rust
// codegraph-ir/src/ffi/types.rs

use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_uint};

/// FFI-safe node representation
#[repr(C)]
#[derive(Debug, Clone)]
pub struct NodeFFI {
    pub id: *const c_char,
    pub kind: NodeKindFFI,
    pub name: *const c_char,
    pub file_path: *const c_char,
    pub start_line: c_uint,
    pub end_line: c_uint,
    pub language: *const c_char,  // nullable (null pointer = None)
    pub complexity: c_uint,       // 0 = None
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NodeKindFFI {
    Function = 0,
    Class = 1,
    Method = 2,
    Variable = 3,
    Import = 4,
    Call = 5,
}

impl NodeFFI {
    /// Convert from internal Node to FFI-safe representation
    pub fn from_node(node: &Node) -> Self {
        Self {
            id: CString::new(node.id.clone()).unwrap().into_raw(),
            kind: NodeKindFFI::from(&node.kind),
            name: CString::new(node.name.clone()).unwrap().into_raw(),
            file_path: CString::new(node.file_path.clone()).unwrap().into_raw(),
            start_line: node.start_line as c_uint,
            end_line: node.end_line as c_uint,
            language: node.language
                .as_ref()
                .map(|s| CString::new(s.clone()).unwrap().into_raw())
                .unwrap_or(std::ptr::null()),
            complexity: node.complexity.unwrap_or(0) as c_uint,
        }
    }

    /// Free allocated strings
    pub unsafe fn free(&mut self) {
        if !self.id.is_null() {
            let _ = CString::from_raw(self.id as *mut c_char);
        }
        if !self.name.is_null() {
            let _ = CString::from_raw(self.name as *mut c_char);
        }
        // ... free other fields
    }
}

/// FFI-safe array wrapper
#[repr(C)]
pub struct NodeArrayFFI {
    pub data: *const NodeFFI,
    pub len: usize,
    pub capacity: usize,
}

impl NodeArrayFFI {
    pub fn from_vec(nodes: Vec<Node>) -> Self {
        let ffi_nodes: Vec<NodeFFI> = nodes.iter()
            .map(NodeFFI::from_node)
            .collect();

        let len = ffi_nodes.len();
        let capacity = ffi_nodes.capacity();
        let data = Box::into_raw(ffi_nodes.into_boxed_slice()) as *const NodeFFI;

        Self { data, len, capacity }
    }

    pub unsafe fn free(&mut self) {
        if !self.data.is_null() {
            let slice = std::slice::from_raw_parts_mut(
                self.data as *mut NodeFFI,
                self.len,
            );
            for node in slice {
                node.free();
            }
            let _ = Vec::from_raw_parts(self.data as *mut NodeFFI, self.len, self.capacity);
        }
    }
}
```

### 3.2 FFI Functions

```rust
// codegraph-ir/src/ffi/mod.rs

use std::os::raw::c_char;
use std::ffi::CStr;

/// Create new CodeGraph engine
#[no_mangle]
pub extern "C" fn codegraph_engine_new(repo_path: *const c_char) -> *mut CodeGraphEngine {
    let repo_path = unsafe {
        assert!(!repo_path.is_null());
        CStr::from_ptr(repo_path).to_str().unwrap()
    };

    match CodeGraphEngine::new(repo_path) {
        Ok(engine) => Box::into_raw(Box::new(engine)),
        Err(_) => std::ptr::null_mut(),
    }
}

/// Free engine
#[no_mangle]
pub extern "C" fn codegraph_engine_free(engine: *mut CodeGraphEngine) {
    if !engine.is_null() {
        unsafe {
            let _ = Box::from_raw(engine);
        }
    }
}

/// Index repository
#[no_mangle]
pub extern "C" fn codegraph_engine_index(
    engine: *mut CodeGraphEngine,
    enable_taint: bool,
    enable_repomap: bool,
    parallel_workers: usize,
) -> *mut IndexResultFFI {
    let engine = unsafe {
        assert!(!engine.is_null());
        &mut *engine
    };

    let result = engine.index()
        .with_taint_if(enable_taint)
        .with_repomap_if(enable_repomap)
        .parallel(parallel_workers)
        .execute();

    match result {
        Ok(r) => Box::into_raw(Box::new(IndexResultFFI::from(r))),
        Err(_) => std::ptr::null_mut(),
    }
}

/// Query nodes
#[no_mangle]
pub extern "C" fn codegraph_engine_query_nodes(
    engine: *const CodeGraphEngine,
    kind: NodeKindFFI,
    language: *const c_char,  // nullable
    limit: usize,
) -> NodeArrayFFI {
    let engine = unsafe {
        assert!(!engine.is_null());
        &*engine
    };

    let mut query = engine.query().nodes().filter(kind.into());

    if !language.is_null() {
        let lang = unsafe { CStr::from_ptr(language).to_str().unwrap() };
        query = query.where_field("language", lang);
    }

    query = query.limit(limit);

    match query.execute() {
        Ok(nodes) => NodeArrayFFI::from_vec(nodes),
        Err(_) => NodeArrayFFI { data: std::ptr::null(), len: 0, capacity: 0 },
    }
}

/// Free node array
#[no_mangle]
pub extern "C" fn codegraph_node_array_free(mut array: NodeArrayFFI) {
    unsafe {
        array.free();
    }
}
```

---

## 4. Use Case Coverage

### 4.1 All SDK Use Cases Mapped to QueryDSL

```rust
// ═══════════════════════════════════════════════════════════════
// Use Case 1: Simple Node Filtering
// ═══════════════════════════════════════════════════════════════

let functions = engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .where_field("language", "python")
    .execute()?;

// ═══════════════════════════════════════════════════════════════
// Use Case 2: Aggregation
// ═══════════════════════════════════════════════════════════════

let stats = engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .aggregate()
    .count()
    .avg("complexity")
    .execute()?;

println!("Total functions: {}", stats.count.unwrap());
println!("Average complexity: {:.2}", stats.avg.unwrap());

// ═══════════════════════════════════════════════════════════════
// Use Case 3: Taint Flow Detection
// ═══════════════════════════════════════════════════════════════

let critical_vulns = engine.query()
    .taint_flows()
    .severity(Severity::Critical)
    .vulnerability_type("CWE-89")  // SQL Injection
    .min_confidence(0.8)
    .execute()?;

for flow in critical_vulns {
    println!("Vulnerability: {} -> {}", flow.source_node_id, flow.sink_node_id);
    println!("Path: {:?}", flow.flow_path);
}

// ═══════════════════════════════════════════════════════════════
// Use Case 4: Clone Detection
// ═══════════════════════════════════════════════════════════════

let clones = engine.query()
    .clone_pairs()
    .clone_type(CloneType::Type3)
    .min_similarity(0.85)
    .execute()?;

// ═══════════════════════════════════════════════════════════════
// Use Case 5: Path Queries (Existing DSL)
// ═══════════════════════════════════════════════════════════════

use codegraph_ir::query::{Q, E};

let paths = engine.query()
    .path(
        (Q::var("user_input") >> Q::call("execute"))
            .via(E::dfg())
            .any_path()
            .limit_paths(20)
    )
    .execute()?;

// ═══════════════════════════════════════════════════════════════
// Use Case 6: Streaming (Large Repositories)
// ═══════════════════════════════════════════════════════════════

let stream = engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .stream(1000)?;  // 1000 nodes per batch

for batch in stream {
    // Process 1000 nodes at a time
    // Memory usage: O(1000) not O(total)
    process_batch(batch);
}

// ═══════════════════════════════════════════════════════════════
// Use Case 7: Pagination
// ═══════════════════════════════════════════════════════════════

let page1 = engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .order_by("complexity", Order::Desc)
    .limit(50)
    .offset(0)
    .execute()?;

let page2 = engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .order_by("complexity", Order::Desc)
    .limit(50)
    .offset(50)
    .execute()?;

// ═══════════════════════════════════════════════════════════════
// Use Case 8: Complex Multi-Filter Query
// ═══════════════════════════════════════════════════════════════

let complex_functions = engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .where_field("language", "python")
    .where_fn(|node| {
        // Custom predicate
        node.complexity.unwrap_or(0) > 10 &&
        node.name.starts_with("process_")
    })
    .order_by("complexity", Order::Desc)
    .limit(20)
    .execute()?;
```

**Conclusion**: ✅ **Extended QueryDSL covers 100% of SDK use cases**

---

## 5. Implementation Plan

### 5.1 Phase 1: Public API Skeleton (Week 1)

**Goal**: Define public-facing API without breaking existing code

**Tasks**:
1. Create `src/lib.rs` with public exports
2. Define `CodeGraphEngine` struct
3. Define `IndexBuilder` with builder pattern
4. Add integration tests

**Files**:
```
codegraph-ir/
├── src/
│   ├── lib.rs                    # NEW: Public API entry point
│   ├── public_api/               # NEW: Public API module
│   │   ├── mod.rs
│   │   ├── engine.rs             # CodeGraphEngine
│   │   └── index_builder.rs     # IndexBuilder
│   └── ... (existing features)
```

### 5.2 Phase 2: Extended QueryDSL (Week 2)

**Goal**: Implement filtering, aggregation, streaming

**Tasks**:
1. Create `src/query/` module
2. Implement `NodeQueryBuilder`
3. Implement `AggregationBuilder`
4. Implement `NodeStream`
5. Add query tests

**Files**:
```
codegraph-ir/
├── src/
│   ├── query/                    # NEW: Extended QueryDSL
│   │   ├── mod.rs
│   │   ├── builder.rs            # QueryBuilder
│   │   ├── node_query.rs         # NodeQueryBuilder
│   │   ├── aggregation.rs        # AggregationBuilder
│   │   ├── streaming.rs          # NodeStream
│   │   ├── taint_query.rs        # TaintQueryBuilder
│   │   └── clone_query.rs        # CloneQueryBuilder
```

### 5.3 Phase 3: FFI Bridge (Week 3)

**Goal**: C-compatible FFI layer

**Tasks**:
1. Define `#[repr(C)]` types
2. Implement `#[no_mangle]` functions
3. Add FFI tests (call from C)
4. Document FFI safety guarantees

**Files**:
```
codegraph-ir/
├── src/
│   ├── ffi/                      # NEW: FFI layer
│   │   ├── mod.rs
│   │   ├── types.rs              # FFI-safe types
│   │   └── functions.rs          # extern "C" functions
```

### 5.4 Phase 4: Documentation & Examples (Week 4)

**Goal**: Production-ready documentation

**Tasks**:
1. Add rustdoc comments
2. Create examples/
3. Write integration guide
4. Benchmark QueryDSL performance

---

## 6. Testing Strategy

### 6.1 Unit Tests

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_query_builder_filter() {
        let engine = CodeGraphEngine::new("/test/repo").unwrap();
        engine.index().execute().unwrap();

        let nodes = engine.query()
            .nodes()
            .filter(NodeKind::Function)
            .execute()
            .unwrap();

        assert!(nodes.iter().all(|n| n.kind == NodeKind::Function));
    }

    #[test]
    fn test_aggregation() {
        let engine = CodeGraphEngine::new("/test/repo").unwrap();
        engine.index().execute().unwrap();

        let stats = engine.query()
            .nodes()
            .aggregate()
            .count()
            .avg("complexity")
            .execute()
            .unwrap();

        assert!(stats.count.unwrap() > 0);
        assert!(stats.avg.unwrap() >= 0.0);
    }

    #[test]
    fn test_streaming_memory_efficiency() {
        let engine = CodeGraphEngine::new("/large/repo").unwrap();
        engine.index().execute().unwrap();

        let stream = engine.query()
            .nodes()
            .stream(1000)
            .unwrap();

        let mut total = 0;
        for batch in stream {
            assert!(batch.len() <= 1000);
            total += batch.len();
        }

        assert!(total > 1000); // Verify we got multiple batches
    }
}
```

### 6.2 FFI Tests

```c
// tests/ffi_test.c

#include <assert.h>
#include <stdio.h>
#include "codegraph_ir.h"

void test_ffi_basic() {
    // Create engine
    CodeGraphEngine* engine = codegraph_engine_new("/test/repo");
    assert(engine != NULL);

    // Index
    IndexResultFFI* result = codegraph_engine_index(engine, true, true, 4);
    assert(result != NULL);
    assert(result->stats.total_nodes > 0);

    // Query
    NodeArrayFFI nodes = codegraph_engine_query_nodes(
        engine,
        NODEKIND_FUNCTION,
        "python",
        100
    );
    assert(nodes.len > 0);
    assert(nodes.len <= 100);

    // Cleanup
    codegraph_node_array_free(nodes);
    codegraph_engine_free(engine);
}

int main() {
    test_ffi_basic();
    printf("All FFI tests passed!\n");
    return 0;
}
```

---

## 7. Performance Benchmarks

### 7.1 QueryDSL Performance Targets

| Query Type | Repository Size | Target Time | Notes |
|------------|----------------|-------------|-------|
| Simple Filter | 10K nodes | < 10ms | In-memory filter |
| Aggregation | 100K nodes | < 50ms | Single pass |
| Path Query | 10K nodes | < 100ms | BFS traversal |
| Streaming (1st batch) | 1M nodes | < 20ms | Lazy evaluation |

### 7.2 Benchmark Suite

```rust
// benches/query_benchmarks.rs

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use codegraph_ir::CodeGraphEngine;

fn bench_filter_query(c: &mut Criterion) {
    let engine = CodeGraphEngine::new("benches/fixtures/django").unwrap();
    engine.index().execute().unwrap();

    c.bench_function("filter_10k_nodes", |b| {
        b.iter(|| {
            engine.query()
                .nodes()
                .filter(NodeKind::Function)
                .where_field("language", "python")
                .execute()
                .unwrap()
        });
    });
}

fn bench_aggregation(c: &mut Criterion) {
    let engine = CodeGraphEngine::new("benches/fixtures/django").unwrap();
    engine.index().execute().unwrap();

    c.bench_function("aggregation_100k_nodes", |b| {
        b.iter(|| {
            engine.query()
                .nodes()
                .aggregate()
                .count()
                .avg("complexity")
                .execute()
                .unwrap()
        });
    });
}

criterion_group!(benches, bench_filter_query, bench_aggregation);
criterion_main!(benches);
```

---

## 8. Migration Path

### 8.1 Existing Code Compatibility

**Guarantee**: All existing Rust code continues to work

```rust
// ✅ Old code still works
use codegraph_ir::pipeline::IRIndexingOrchestrator;

let orchestrator = IRIndexingOrchestrator::new(config);
let result = orchestrator.execute()?;

// ✅ New code uses public API
use codegraph_ir::CodeGraphEngine;

let engine = CodeGraphEngine::new("/repo")?;
let result = engine.index().execute()?;
```

### 8.2 Python Migration

**Before** (direct FFI):
```python
# ❌ Not implemented yet
```

**After** (via public API):
```python
import codegraph_ir

engine = codegraph_ir.CodeGraphEngine("/repo")
result = engine.index().execute()

nodes = engine.query().nodes().filter(kind="function").execute()
```

---

## 9. Open Questions

### 9.1 Resolved

✅ **Q1**: Should QueryDSL be unified or split into multiple builders?
**A1**: Unified `QueryBuilder` with type-specific sub-builders (clearer API)

✅ **Q2**: FFI or PyO3 first?
**A2**: FFI first (C-compatible, works with any language including Python via ctypes)

### 9.2 Open

⏳ **Q3**: Should we support SQL-like syntax?
**Proposal**: `engine.sql("SELECT * FROM nodes WHERE kind='function'")`
**Status**: Defer to Phase 2 (after QueryDSL proven)

⏳ **Q4**: Should streaming use async/await?
**Current**: `Iterator<Item = Vec<Node>>`
**Alternative**: `Stream<Item = Vec<Node>>` (requires async runtime)
**Status**: TBD based on performance testing

---

## 10. Approval

**Reviewers**:
- [ ] @songmin (Architecture)
- [ ] @rust-team (API design)
- [ ] @python-team (FFI usability)

**Approval Criteria**:
1. ✅ QueryDSL covers 100% of use cases
2. ✅ FFI layer is safe and well-documented
3. ✅ Performance benchmarks meet targets
4. ✅ Backward compatibility maintained

**Status**: ⏳ Awaiting review

---

**End of RFC-RUST-SDK-001**
