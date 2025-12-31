# RFC-RUST-SDK-001: Current State Analysis

**Status**: Draft
**Author**: CodeGraph Team
**Created**: 2024-12-28
**Purpose**: Accurate assessment of current capabilities vs. required coverage

---

## Executive Summary

**Current Reality Check**:
- ✅ **Path Queries**: Fully implemented in Rust QueryDSL (5/5 scenarios)
- ⚠️ **Filtering/Aggregation/Streaming**: NOT implemented, only proposed in RFC
- ✅ **Extensibility**: Architecture supports extensions without breaking changes

**Status**:
- Current QueryDSL = **16% coverage** (5/31 scenarios)
- Proposed Extended QueryDSL = **100% coverage** (31/31 scenarios)

---

## 1. Current Capabilities (What We HAVE)

### 1.1 Implemented Features in Rust

From `codegraph-ir/src/features/query_engine/`:

| Feature | Status | Location | Capability |
|---------|--------|----------|-----------|
| **Path Queries** | ✅ IMPLEMENTED | `query_engine/domain/expressions.rs` | Graph traversal with `Q >> Q` syntax |
| **Edge Selectors** | ✅ IMPLEMENTED | `query_engine/domain/edge_selector.rs` | `E::DFG`, `E::CALL`, `E::CFG` |
| **Node Selectors** | ✅ IMPLEMENTED | `query_engine/domain/node_selector.rs` | `Q::Func()`, `Q::Var()`, `Q::Call()` |
| **Traversal Direction** | ✅ IMPLEMENTED | `query_engine/domain/expressions.rs` | Forward, Backward, Both |
| **Depth Limiting** | ✅ IMPLEMENTED | `query_engine/domain/expressions.rs` | `.depth(max_depth)` |

**Current Public API** (Rust):
```rust
// What EXISTS today
use codegraph_ir::query_engine::{QueryEngine, Q, E};

let engine = QueryEngine::new(&ir_doc);

// ✅ Path query - WORKS
let paths = engine.execute_any_path(
    (Q::Var("user_input") >> Q::Call("execute"))
        .via(E::DFG)
        .depth(10)
);

// ❌ Filtering - DOESN'T EXIST
// let nodes = engine.query().nodes().filter(...);  // ERROR: No such method

// ❌ Aggregation - DOESN'T EXIST
// let count = engine.query().nodes().aggregate().count();  // ERROR

// ❌ Streaming - DOESN'T EXIST
// let stream = engine.query().nodes().stream(1000);  // ERROR
```

### 1.2 Coverage of Current Implementation

**Scenarios Covered by Current QueryDSL** (5/31):

| # | Scenario | Status | Evidence |
|---|----------|--------|----------|
| 1 | Dataflow (source → sink) | ✅ WORKS | `Q::var(s) >> Q::var(t)` |
| 2 | Call chain (caller → callee) | ✅ WORKS | `Q::func(a) >> Q::func(b).via(E::CALL)` |
| 3 | Taint proof (source → sink + policy) | ✅ WORKS | `Q::source(s) >> Q::sink(t)` |
| 4 | Program slicing | ✅ WORKS | `Q::var(anchor).depth(5)` |
| 5 | Data dependency | ✅ WORKS | `Q::var(a) >> Q::var(b).via(E::DFG)` |

**Current Coverage**: **5/31 = 16%**

---

## 2. Required Scenarios (What We NEED)

### 2.1 All Real-World Use Cases (31 Total)

Extracted from actual codebase usage:

#### Category 1: Path Queries (5) - ✅ COVERED
1. Dataflow (source → sink)
2. Call chain (caller → callee)
3. Taint proof (source → sink + policy)
4. Program slicing (anchor + direction)
5. Data dependency (var → var)

#### Category 2: Node Filtering (5) - ❌ NOT IMPLEMENTED
6. Filter by node kind (`kind="function"`)
7. Filter by language (`language="python"`)
8. Filter by file path (`file_path="src/main.py"`)
9. Filter by complexity threshold (`complexity >= 10`)
10. Filter by name pattern (`name contains "process"`)

#### Category 3: Edge Filtering (3) - ❌ NOT IMPLEMENTED
11. Get callers (incoming edges)
12. Get callees (outgoing edges)
13. Get references to symbol

#### Category 4: Aggregation (4) - ❌ NOT IMPLEMENTED
14. Count nodes (`len(nodes)`)
15. Average complexity (`avg(complexity)`)
16. Sum of metric (`sum(metric)`)
17. Min/Max value (`min/max`)

#### Category 5: Ordering & Pagination (4) - ❌ NOT IMPLEMENTED
18. Sort by field (`order_by("complexity")`)
19. Descending order (`reverse=True`)
20. Limit results (`[:100]`)
21. Pagination (`[offset:offset+limit]`)

#### Category 6: Specialized Queries (5) - ❌ NOT IMPLEMENTED
22. Taint flows by vulnerability type
23. Taint flows by severity
24. Taint flows by confidence
25. Clone pairs by similarity
26. Clone pairs by type

#### Category 7: Streaming (2) - ❌ NOT IMPLEMENTED
27. Large result streaming
28. Batch processing

#### Category 8: Advanced Combinations (3) - ❌ NOT IMPLEMENTED
29. Multi-filter (language + complexity)
30. Filter + Order + Limit
31. Aggregation on filtered set

### 2.2 Gap Analysis

| Category | Required | Implemented | Gap | Gap % |
|----------|----------|-------------|-----|-------|
| Path Queries | 5 | 5 | 0 | 0% |
| Node Filtering | 5 | 0 | 5 | 100% |
| Edge Filtering | 3 | 0 | 3 | 100% |
| Aggregation | 4 | 0 | 4 | 100% |
| Ordering & Pagination | 4 | 0 | 4 | 100% |
| Specialized Queries | 5 | 0 | 5 | 100% |
| Streaming | 2 | 0 | 2 | 100% |
| Advanced Combinations | 3 | 0 | 3 | 100% |
| **TOTAL** | **31** | **5** | **26** | **84%** |

---

## 3. Current QueryDSL Specification

### 3.1 Implemented API (Rust)

From `codegraph-ir/src/features/query_engine/`:

**Public API**:
```rust
// Entry point
pub struct QueryEngine {
    // Internal: IRDocument reference
}

impl QueryEngine {
    pub fn new(ir_doc: &IRDocument) -> Self;

    // ✅ ONLY method that exists
    pub fn execute_any_path(&self, query: PathQuery) -> PathSet;
}

// Query builders
pub struct PathQuery {
    // Internal: NodeSelector + EdgeSelector + options
}

// Factory functions
pub mod Q {
    pub fn Var(name: &str) -> NodeSelector;
    pub fn Func(name: &str) -> NodeSelector;
    pub fn Call(name: &str) -> NodeSelector;
    pub fn Class(name: &str) -> NodeSelector;
    pub fn Source(name: &str) -> NodeSelector;
    pub fn Sink(name: &str) -> NodeSelector;
}

pub mod E {
    pub fn DFG() -> EdgeSelector;
    pub fn CFG() -> EdgeSelector;
    pub fn CALL() -> EdgeSelector;
    pub fn REF() -> EdgeSelector;
}

// Operators
impl Shr for NodeSelector {
    // Enables: Q::Var("a") >> Q::Var("b")
}

impl PathQuery {
    pub fn via(self, edge: EdgeSelector) -> Self;
    pub fn depth(self, max_depth: usize) -> Self;
    pub fn direction(self, dir: TraversalDirection) -> Self;
}
```

**What's MISSING**:
```rust
// ❌ These DO NOT exist in current codebase
impl QueryEngine {
    // pub fn query(&self) -> QueryBuilder;  // NO
}

pub struct QueryBuilder;  // NO
pub struct NodeQueryBuilder;  // NO
pub struct EdgeQueryBuilder;  // NO
pub struct AggregationBuilder;  // NO
pub struct TaintQueryBuilder;  // NO
pub struct CloneQueryBuilder;  // NO
```

### 3.2 Current File Structure

```
codegraph-ir/src/features/query_engine/
├── domain/
│   ├── mod.rs                    ✅ EXISTS
│   ├── edge_selector.rs          ✅ EXISTS - EdgeType, EdgeSelector
│   ├── expressions.rs            ✅ EXISTS - PathQuery, FlowExpr
│   ├── factories.rs              ✅ EXISTS - Q, E factory functions
│   ├── node_selector.rs          ✅ EXISTS - NodeSelector types
│   └── operators.rs              ✅ EXISTS - >> operator overloading
├── infrastructure/
│   ├── mod.rs                    ✅ EXISTS
│   ├── graph_index.rs            ✅ EXISTS - Graph indexing
│   ├── node_matcher.rs           ✅ EXISTS - Node matching
│   ├── parallel_traversal.rs     ✅ EXISTS - Parallel BFS/DFS
│   ├── reachability_cache.rs     ✅ EXISTS - Caching layer
│   └── traversal_engine.rs       ✅ EXISTS - Core traversal
└── query_engine.rs               ✅ EXISTS - Main QueryEngine struct

# ❌ What's MISSING (proposed in RFC but not implemented):
query_engine/
├── builder.rs                    ❌ DOES NOT EXIST
├── node_query.rs                 ❌ DOES NOT EXIST
├── edge_query.rs                 ❌ DOES NOT EXIST
├── aggregation.rs                ❌ DOES NOT EXIST
├── streaming.rs                  ❌ DOES NOT EXIST
├── taint_query.rs                ❌ DOES NOT EXIST
└── clone_query.rs                ❌ DOES NOT EXIST
```

---

## 4. Extensibility Assessment

### 4.1 Can We Extend Without Breaking Changes?

**Analysis**: ✅ **YES - Clean extension path**

**Evidence**:

1. **Current API is minimal**:
   ```rust
   // Current public API (won't change)
   QueryEngine::new(ir_doc)
   engine.execute_any_path(query)
   ```

2. **Can add new methods without breaking existing code**:
   ```rust
   // Existing code continues to work
   let paths = engine.execute_any_path(Q::var("x") >> Q::call("y"));

   // NEW: Add parallel method (backward compatible)
   impl QueryEngine {
       pub fn query(&self) -> QueryBuilder {  // NEW method
           QueryBuilder::new(self.ir_doc)
       }
   }

   // New code uses new API
   let nodes = engine.query().nodes().filter(...);
   ```

3. **No breaking changes to existing types**:
   - `PathQuery`, `NodeSelector`, `EdgeSelector` remain unchanged
   - New builders are separate types
   - Existing `Q::` and `E::` factories keep working

### 4.2 Architecture Supports Extension

**Current Clean Architecture**:
```
domain/          ✅ Pure domain logic (no dependencies)
├── expressions  ✅ PathQuery, FlowExpr
├── selectors    ✅ NodeSelector, EdgeSelector
└── factories    ✅ Q, E

infrastructure/  ✅ Implementation details
├── traversal    ✅ Graph algorithms
├── indexing     ✅ Performance optimization
└── caching      ✅ Result caching

query_engine.rs  ✅ Thin facade
```

**Extension Points**:
1. ✅ Add new domain types (NodeQueryBuilder, AggregationBuilder)
2. ✅ Add new infrastructure (streaming, filtering)
3. ✅ Add new methods to QueryEngine (non-breaking)

---

## 5. Scenarios NOT Covered (But Extensible)

### 5.1 Currently Unsupported (26 scenarios)

**Category: Node Filtering (5)**
```rust
// ❌ NOT IMPLEMENTED - But architecture supports it
engine.query()
    .nodes()
    .filter(NodeKind::Function)
    .where_field("language", "python")
    .execute()
```

**Implementation Path**:
1. Add `NodeQueryBuilder` struct
2. Implement filtering methods
3. Add `query()` method to `QueryEngine`

**Feasibility**: ✅ **Straightforward** (no breaking changes)

**Category: Aggregation (4)**
```rust
// ❌ NOT IMPLEMENTED
engine.query()
    .nodes()
    .aggregate()
    .count()
    .avg("complexity")
    .execute()
```

**Implementation Path**:
1. Add `AggregationBuilder` struct
2. Implement statistical functions
3. Wire up to existing node iteration

**Feasibility**: ✅ **Straightforward** (pure computation over existing nodes)

**Category: Streaming (2)**
```rust
// ❌ NOT IMPLEMENTED
let stream = engine.query()
    .nodes()
    .stream(1000)?;
```

**Implementation Path**:
1. Add `NodeStream` struct implementing `Iterator`
2. Use chunking with `ir_doc.nodes` iteration
3. O(chunk_size) memory guarantee

**Feasibility**: ✅ **Straightforward** (Rust iterators are natural fit)

### 5.2 Why Not Implemented Yet?

**Hypothesis**: Initial focus was on graph traversal (core competency)

**Evidence**:
- QueryEngine focuses on path finding (BFS/DFS)
- Python layer handles filtering/aggregation ad-hoc
- No unified query interface existed

**Consequence**: Python code has manual filtering everywhere
```python
# Current workaround in Python
all_nodes = get_all_nodes()
python_nodes = [n for n in all_nodes if n.language == "python"]
complex_nodes = [n for n in python_nodes if n.complexity > 10]
sorted_nodes = sorted(complex_nodes, key=lambda n: n.complexity, reverse=True)
top_10 = sorted_nodes[:10]
```

**Better approach** (with extended QueryDSL):
```rust
// In Rust SDK
let top_10 = engine.query()
    .nodes()
    .where_field("language", "python")
    .where_fn(|n| n.complexity > 10)
    .order_by("complexity", Order::Desc)
    .limit(10)
    .execute()?;
```

---

## 6. Extension Strategy

### 6.1 Phased Implementation (RFC-RUST-SDK-001)

**Phase 1: Public API Skeleton** (Week 1)
- Add `CodeGraphEngine` entry point
- Add `IndexBuilder` for pipeline configuration
- ✅ No breaking changes to existing QueryEngine

**Phase 2: Extended QueryDSL** (Week 2)
- Add `QueryBuilder`, `NodeQueryBuilder`, `EdgeQueryBuilder`
- Add `AggregationBuilder`
- Add `NodeStream` for streaming
- ✅ Builds on top of existing QueryEngine

**Phase 3: Specialized Builders** (Week 3)
- Add `TaintQueryBuilder`
- Add `CloneQueryBuilder`
- ✅ Reuses existing taint/clone analysis infrastructure

**Phase 4: FFI & PyO3** (Week 4)
- Add `#[repr(C)]` FFI types
- Add PyO3 bindings
- ✅ Exposes extended QueryDSL to Python

### 6.2 Backward Compatibility Guarantee

**Existing Rust code continues to work**:
```rust
// ✅ This will NEVER break
use codegraph_ir::query_engine::{QueryEngine, Q, E};

let engine = QueryEngine::new(&ir_doc);
let paths = engine.execute_any_path(
    Q::Var("user") >> Q::Call("exec")
);
```

**New code uses new API**:
```rust
// ✅ NEW - Coexists with old API
use codegraph_ir::CodeGraphEngine;

let engine = CodeGraphEngine::new("/repo")?;
let nodes = engine.query().nodes().filter(...).execute()?;
```

---

## 7. Summary

### 7.1 Current State Matrix

| Aspect | Status | Details |
|--------|--------|---------|
| **Implemented Features** | 16% (5/31) | Path queries only |
| **Required Features** | 100% (31/31) | All use cases identified |
| **Architecture Quality** | ✅ Excellent | Clean separation, extensible |
| **Breaking Changes** | ✅ None required | Can extend without breaking |
| **Implementation Effort** | ⏳ 4 weeks | Phased rollout |

### 7.2 Current Capabilities

✅ **HAVE**:
- Path queries (graph traversal)
- Edge type selection (DFG, CFG, CALL)
- Node selectors (Var, Func, Call, Class)
- Depth limiting
- Direction control
- Operator overloading (`>>`)

❌ **DON'T HAVE** (but can add):
- Node filtering by attributes
- Aggregation (count, avg, sum, min, max)
- Ordering & pagination
- Streaming (O(chunk_size) memory)
- Specialized query builders (Taint, Clone)
- Edge filtering (callers, callees, references)

### 7.3 Required Coverage

**Must Support** (31 scenarios):
- ✅ 5 Path Queries (implemented)
- ⏳ 5 Node Filtering (proposed)
- ⏳ 3 Edge Filtering (proposed)
- ⏳ 4 Aggregation (proposed)
- ⏳ 4 Ordering & Pagination (proposed)
- ⏳ 5 Specialized Queries (proposed)
- ⏳ 2 Streaming (proposed)
- ⏳ 3 Advanced Combinations (proposed)

### 7.4 Extensibility

✅ **Clean Extension Path**:
- No breaking changes required
- Architecture supports new features
- Existing code continues to work
- New API coexists with old API

**Implementation Confidence**: **HIGH**
- Clear separation of concerns
- Well-defined interfaces
- Proven patterns (builder, fluent API)
- Rust type system ensures correctness

---

## 8. Recommendation

### 8.1 Go/No-Go Decision

✅ **GO - Proceed with RFC-RUST-SDK-001 implementation**

**Reasoning**:
1. ✅ Current architecture supports extension
2. ✅ No breaking changes required
3. ✅ Gap is well-defined (26 missing scenarios)
4. ✅ Implementation path is clear (4 phases)
5. ✅ Backward compatibility guaranteed

### 8.2 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking changes | LOW | HIGH | Phased rollout, parallel APIs |
| Performance regression | LOW | MEDIUM | Benchmark each phase |
| API complexity | MEDIUM | LOW | Progressive disclosure (L1→L4) |
| Implementation effort | LOW | MEDIUM | 4-week schedule with buffer |

### 8.3 Success Criteria

**Phase 1 Success**:
- [ ] `CodeGraphEngine::new()` works
- [ ] `engine.index().execute()` completes
- [ ] Zero breaking changes to existing code

**Phase 2 Success**:
- [ ] All 31 scenarios have QueryDSL syntax
- [ ] Filtering/aggregation tests pass
- [ ] Streaming memory test passes (O(chunk_size))

**Phase 3 Success**:
- [ ] TaintQueryBuilder covers all TRCR use cases
- [ ] CloneQueryBuilder covers clone detection
- [ ] Integration tests pass

**Phase 4 Success**:
- [ ] FFI types are #[repr(C)] safe
- [ ] PyO3 bindings expose all QueryDSL features
- [ ] Python SDK can use extended QueryDSL

---

**End of Current State Analysis**
