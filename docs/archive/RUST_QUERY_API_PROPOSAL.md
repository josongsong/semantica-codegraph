# Rust Query API Proposal - Leveraging Native Graph Traversal

**Date**: 2025-12-28
**Status**: Proposal
**Priority**: Medium (Query performance already excellent at 0.3ms, but Rust would unlock advanced features)

## Problem Statement

현재 아키텍처에서는 **Rust의 강력한 그래프 순회 기능을 활용하지 못하고 있습니다**.

### Current Architecture (Inefficient)

```
┌─────────────────────────────────────────────────────────────────┐
│ Rust IR Indexing (340ms)                                        │
│   - GraphIndex (O(1) lookups)                                   │
│   - ReachabilityCache (BFS/transitive closure)                  │
│   - TraversalEngine (DFS/BFS)                                   │
│   - ParallelTraversalEngine (Rayon-based)                       │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼ PyO3 (Full Conversion)
┌─────────────────────────────────────────────────────────────────┐
│ Python Conversion (93ms)                                         │
│   - Convert ALL nodes to Python objects                         │
│   - Convert ALL edges to Python objects                         │
│   - Build Python UnifiedGraphIndex                              │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼ LOSES RUST GRAPH STRUCTURES!
┌─────────────────────────────────────────────────────────────────┐
│ Python QueryEngine (0.3-0.8ms per query)                        │
│   - for-loop over Python list of nodes                          │
│   - Manual filtering in Python                                  │
│   - CAN'T use Rust's ReachabilityCache                          │
│   - CAN'T use Rust's TraversalEngine                            │
│   - CAN'T use Rust's ParallelTraversalEngine                    │
└─────────────────────────────────────────────────────────────────┘
```

**문제점**:
1. ❌ Rust의 `ReachabilityCache` (O(1) reachability check) 사용 불가
2. ❌ Rust의 `TraversalEngine` (최적화된 DFS/BFS) 사용 불가
3. ❌ Rust의 `ParallelTraversalEngine` (Rayon 병렬 순회) 사용 불가
4. ❌ 전체 그래프를 Python 객체로 변환 (93ms overhead + 메모리 복사)
5. ❌ Python for-loop으로 순회 (느리지는 않지만 최적화되지 않음)

## Existing Rust Infrastructure (UNDERUTILIZED)

Rust에 이미 구현된 강력한 기능들:

### 1. GraphIndex (`graph_index.rs`)
```rust
pub struct GraphIndex {
    nodes_by_id: HashMap<String, Node>,      // O(1) lookup
    edges_from: HashMap<String, Vec<Edge>>,  // O(1) forward edges
    edges_to: HashMap<String, Vec<Edge>>,    // O(1) backward edges
    nodes_by_name: HashMap<String, Vec<Node>>, // O(1) name search
}

impl GraphIndex {
    pub fn get_node(&self, node_id: &str) -> Option<&Node>;
    pub fn get_all_nodes(&self) -> Vec<&Node>;
    pub fn find_nodes_by_name(&self, name: &str) -> Vec<&Node>;
    pub fn get_edges_from(&self, node_id: &str) -> Vec<&Edge>;
    pub fn get_edges_to(&self, node_id: &str) -> Vec<&Edge>;
}
```

### 2. ReachabilityCache (`reachability_cache.rs`)
```rust
pub struct ReachabilityCache {
    forward_reach: HashMap<String, HashSet<String>>,   // Transitive closure
    backward_reach: HashMap<String, HashSet<String>>,  // Reverse closure
    edge_type: EdgeType,
}

impl ReachabilityCache {
    pub fn build(index: &GraphIndex, edge_type: EdgeType) -> Self; // O(V^2) build
    pub fn is_reachable(&self, source_id: &str, target_id: &str) -> bool; // O(1) query
    pub fn get_reachable_from(&self, source_id: &str) -> Option<&HashSet<String>>; // O(1)
    pub fn get_reaching_to(&self, target_id: &str) -> Option<&HashSet<String>>; // O(1)
}
```

**Use Cases**:
- Impact analysis: "이 변수를 수정하면 어떤 함수들이 영향받나?" → O(1) 응답
- Dependency queries: "X가 의존하는 모든 모듈은?" → O(1) 응답
- Security analysis: "Source에서 Sink까지 도달 가능한가?" → O(1) 응답

### 3. TraversalEngine (Not yet implemented but planned)
```rust
pub struct TraversalEngine {
    // DFS/BFS traversal with custom predicates
    // Would enable complex graph queries
}
```

### 4. ParallelTraversalEngine (Not yet implemented but planned)
```rust
pub struct ParallelTraversalEngine {
    // Rayon-based parallel graph traversal
    // Would enable massive performance gains for complex queries
}
```

## Proposed Solution: Rust Query API via PyO3

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Rust IR Indexing (340ms)                                        │
│   - GraphIndex built                                            │
│   - ReachabilityCache built (optional)                          │
│   - Graph STAYS IN RUST MEMORY ✅                               │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼ PyO3 Query API (NEW!)
┌─────────────────────────────────────────────────────────────────┐
│ Rust Query Functions (exposed to Python)                        │
│                                                                  │
│   query_nodes(filter: NodeFilter) -> Vec<Node>                  │
│   query_edges(filter: EdgeFilter) -> Vec<Edge>                  │
│   is_reachable(source: str, target: str) -> bool                │
│   get_reachable_nodes(node_id: str) -> Vec<Node>                │
│   find_path(source: str, target: str) -> Option<Vec<Node>>      │
│   traverse_dfs(start: str, predicate: Fn) -> Vec<Node>          │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼ Minimal Conversion (only results)
┌─────────────────────────────────────────────────────────────────┐
│ Python QueryDSL (Thin Wrapper)                                  │
│                                                                  │
│   Q.Func().match(engine)  →  rust.query_nodes(...)              │
│   Q.Class().match(engine) →  rust.query_nodes(...)              │
│   engine.is_reachable(a, b) → rust.is_reachable(a, b)           │
└─────────────────────────────────────────────────────────────────┘
```

### API Design (PyO3 Functions)

```rust
// File: packages/codegraph-rust/codegraph-ir/src/adapters/pyo3/api/query.rs

use pyo3::prelude::*;
use crate::features::query_engine::infrastructure::{GraphIndex, ReachabilityCache};

/// Node filter for queries
#[pyclass]
pub struct NodeFilter {
    #[pyo3(get, set)]
    pub kind: Option<String>,  // "FUNCTION", "CLASS", etc.

    #[pyo3(get, set)]
    pub name: Option<String>,  // Exact name match

    #[pyo3(get, set)]
    pub name_prefix: Option<String>,  // Prefix match

    #[pyo3(get, set)]
    pub file_path: Option<String>,  // File filter
}

/// Query nodes with filter (returns only matching nodes)
#[pyfunction]
pub fn query_nodes(
    ir_result: &IRIndexingResult,  // Contains GraphIndex
    filter: NodeFilter
) -> PyResult<Vec<PyNode>> {
    let index = &ir_result.graph_index;

    // Execute query in Rust (fast)
    let nodes = if let Some(name) = filter.name {
        index.find_nodes_by_name(&name)
    } else {
        index.get_all_nodes()
    };

    // Apply filters in Rust (fast)
    let filtered: Vec<&Node> = nodes.into_iter()
        .filter(|n| {
            if let Some(kind) = &filter.kind {
                n.kind.to_string() == *kind
            } else {
                true
            }
        })
        .filter(|n| {
            if let Some(prefix) = &filter.name_prefix {
                n.name.as_ref().map(|s| s.starts_with(prefix)).unwrap_or(false)
            } else {
                true
            }
        })
        .collect();

    // Convert ONLY results to Python (minimal overhead)
    Ok(filtered.into_iter().map(|n| convert_node(n)).collect())
}

/// Check if target is reachable from source (O(1) with cache)
#[pyfunction]
pub fn is_reachable(
    ir_result: &IRIndexingResult,
    source_id: String,
    target_id: String,
    edge_type: Option<String>,  // "DFG", "CFG", "CALL"
) -> PyResult<bool> {
    let cache = ir_result.reachability_cache
        .as_ref()
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            "ReachabilityCache not built"
        ))?;

    Ok(cache.is_reachable(&source_id, &target_id))
}

/// Get all nodes reachable from source (O(1) with cache)
#[pyfunction]
pub fn get_reachable_nodes(
    ir_result: &IRIndexingResult,
    source_id: String,
) -> PyResult<Vec<PyNode>> {
    let cache = &ir_result.reachability_cache.as_ref().unwrap();
    let index = &ir_result.graph_index;

    let reachable_ids = cache.get_reachable_from(&source_id)
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>(
            format!("Node not found: {}", source_id)
        ))?;

    // Convert only reachable nodes to Python
    let nodes: Vec<PyNode> = reachable_ids.iter()
        .filter_map(|id| index.get_node(id))
        .map(|n| convert_node(n))
        .collect();

    Ok(nodes)
}

/// Find shortest path between source and target (Dijkstra/BFS)
#[pyfunction]
pub fn find_path(
    ir_result: &IRIndexingResult,
    source_id: String,
    target_id: String,
) -> PyResult<Option<Vec<PyNode>>> {
    // TODO: Implement BFS pathfinding
    // Returns path as Vec<Node> or None if no path exists
    unimplemented!("Coming soon")
}
```

### Python QueryDSL Integration

```python
# File: packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/query/query_engine.py

import codegraph_ir  # Rust module

class QueryEngine:
    """
    Query Engine - Hybrid Rust/Python approach

    Fast path: Delegate to Rust for common queries
    Fallback: Python for complex/custom queries
    """

    def __init__(self, ir_doc_or_rust_result):
        if isinstance(ir_doc_or_rust_result, dict) and "nodes" in ir_doc_or_rust_result:
            # Rust result - KEEP RUST REFERENCE!
            self._rust_result = ir_doc_or_rust_result
            self._use_rust = True

            # Build minimal Python index for fallback
            self._py_index = self._build_minimal_index(ir_doc_or_rust_result)
        else:
            # Python IRDocument - use existing path
            self._rust_result = None
            self._use_rust = False
            self._py_index = UnifiedGraphIndex(ir_doc_or_rust_result)

    def match_nodes(self, query: NodeQuery) -> list[Node]:
        """Execute node query (Rust fast path if available)"""
        if self._use_rust and self._can_use_rust_fast_path(query):
            # FAST PATH: Query in Rust, get only results
            filter = self._build_rust_filter(query)
            rust_nodes = codegraph_ir.query_nodes(self._rust_result, filter)
            return rust_nodes
        else:
            # FALLBACK: Python query
            return list(self._py_index.match_nodes(query))

    def is_reachable(self, source_id: str, target_id: str) -> bool:
        """Check reachability (O(1) with Rust cache)"""
        if self._use_rust:
            return codegraph_ir.is_reachable(
                self._rust_result,
                source_id,
                target_id
            )
        else:
            # Python fallback (slower)
            return self._py_index.is_reachable(source_id, target_id)

    def get_reachable_nodes(self, source_id: str) -> list[Node]:
        """Get all reachable nodes (O(1) with Rust cache)"""
        if self._use_rust:
            return codegraph_ir.get_reachable_nodes(
                self._rust_result,
                source_id
            )
        else:
            # Python fallback
            return self._py_index.get_reachable_nodes(source_id)
```

## Performance Comparison

### Current Approach (Python Query)
```python
# 100 files, 6,710 nodes, 17,578 edges

# Query: Find all functions starting with 'build'
all_funcs = list(engine.node_matcher.match(Q.Func()))  # 0.579ms
filtered = [f for f in all_funcs if f.name.startswith('build')]  # 0.162ms
# Total: 0.741ms
```

### Proposed Approach (Rust Query)
```python
# Same data

# Query: Find all functions starting with 'build'
filter = NodeFilter(kind="FUNCTION", name_prefix="build")
results = codegraph_ir.query_nodes(rust_result, filter)
# Expected: 0.050ms (15x faster)
# Why: No Python for-loop, Rust iterator, fewer conversions
```

### Advanced Queries (NEW CAPABILITIES)

**Impact Analysis (O(1) with ReachabilityCache)**:
```python
# Current: Not possible without custom BFS
# Proposed:
affected_nodes = engine.get_reachable_nodes("function_id")
# Expected: 0.001ms (O(1) hash lookup)
```

**Security Analysis (Taint Tracking)**:
```python
# Current: Need full Python traversal
# Proposed:
is_vulnerable = engine.is_reachable(
    source_id="user_input_var",
    target_id="sql_execute_func"
)
# Expected: 0.001ms (O(1) hash lookup)
```

## Implementation Plan

### Phase 1: Core Query API (1-2 days)
- [ ] Implement `query_nodes()` with NodeFilter
- [ ] Implement `query_edges()` with EdgeFilter
- [ ] Expose GraphIndex via PyO3
- [ ] Update QueryEngine to use Rust fast path

**Deliverables**:
- `packages/codegraph-rust/codegraph-ir/src/adapters/pyo3/api/query.rs`
- Updated `QueryEngine` with Rust delegation
- Benchmark showing 10-15x speedup for filtering queries

### Phase 2: Reachability API (1 day)
- [ ] Expose `ReachabilityCache::is_reachable()`
- [ ] Expose `ReachabilityCache::get_reachable_from()`
- [ ] Expose `ReachabilityCache::get_reaching_to()`
- [ ] Add option to build cache during IR indexing

**Deliverables**:
- Reachability query functions in PyO3
- O(1) reachability checks from Python
- Impact analysis demo

### Phase 3: Advanced Traversal (2-3 days)
- [ ] Implement `find_path()` (BFS shortest path)
- [ ] Implement `traverse_dfs()` with custom predicates
- [ ] Implement `traverse_bfs()` with custom predicates
- [ ] Add parallel traversal for large graphs

**Deliverables**:
- Full graph traversal API
- Path finding algorithms
- Complex query examples

### Phase 4: Benchmark & Optimize (1 day)
- [ ] Comprehensive benchmark: Rust vs Python queries
- [ ] Profile conversion overhead
- [ ] Optimize msgpack serialization for results
- [ ] Document performance characteristics

**Deliverables**:
- Updated `BENCHMARK_RESULTS.md` with query comparison
- Performance guide for when to use Rust vs Python

## Benefits

### Performance
- **10-15x faster queries** for filtering operations (no Python for-loops)
- **O(1) reachability checks** (vs O(V+E) Python BFS)
- **Parallel traversal** for complex queries (Rayon)
- **Lower memory usage** (no full graph conversion, only results)

### New Capabilities
- **Impact analysis**: "What's affected by this change?" (O(1))
- **Dependency graphs**: "Show all dependencies" (O(1))
- **Security analysis**: "Is taint path possible?" (O(1))
- **Path finding**: "Shortest call path from A to B" (BFS in Rust)

### Developer Experience
- **Same QueryDSL API** (backward compatible)
- **Automatic optimization** (Rust fast path when available)
- **Python fallback** (complex queries still work)
- **Clear performance model** (documented when Rust is used)

## Risks & Mitigation

### Risk 1: PyO3 Overhead for Small Queries
**Issue**: Converting results to Python might be slower than pure Python for tiny result sets (< 10 nodes)

**Mitigation**:
- Benchmark threshold: Use Rust only if expected results > 10 nodes
- Profile conversion overhead
- Add `use_rust=False` option for debugging

### Risk 2: API Complexity
**Issue**: Maintaining two code paths (Rust + Python)

**Mitigation**:
- Clear separation: Rust for hot path, Python for edge cases
- Comprehensive tests for both paths
- Document which queries use Rust vs Python

### Risk 3: Reachability Cache Memory
**Issue**: ReachabilityCache is O(V^2) memory for dense graphs

**Mitigation**:
- Make cache optional (build only when needed)
- Add cache eviction for large graphs
- Document memory characteristics

## Alternatives Considered

### Alternative 1: Keep Current Architecture
**Pros**: Already works, 0.3ms query time is excellent
**Cons**: Can't leverage Rust's advanced features (reachability, parallel traversal)
**Decision**: Rejected - We're leaving performance on the table

### Alternative 2: Pure Rust QueryDSL
**Pros**: Maximum performance
**Cons**: Breaking change, lose Python flexibility
**Decision**: Rejected - Too disruptive

### Alternative 3: Hybrid (CHOSEN)
**Pros**: Backward compatible, leverages both languages' strengths
**Cons**: Slight complexity in maintaining two paths
**Decision**: Accepted - Best of both worlds

## Conclusion

현재 Python 쿼리 성능이 이미 훌륭하지만 (0.3ms avg), Rust의 그래프 순회 기능을 PyO3로 노출하면:

1. ✅ **기존 성능을 10-15x 개선** (0.3ms → 0.02ms)
2. ✅ **새로운 기능 추가** (O(1) reachability, impact analysis)
3. ✅ **하위 호환성 유지** (QueryDSL API 동일)
4. ✅ **메모리 효율 향상** (전체 그래프 변환 → 결과만 변환)

**추천**: Phase 1-2 구현 (3-4일 투자로 큰 ROI)
