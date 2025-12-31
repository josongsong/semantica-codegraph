# Architecture Comparison: Old vs New Query API

## Problem: Old Approach Wastes 200ms Per Query

### Old Architecture (BAD ❌)

```
┌─────────────────────────────────────────────────────────────┐
│ Python Application                                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  # IR Indexing (one-time)                                   │
│  result = run_ir_indexing_pipeline(...)                     │
│  # Returns: {"nodes": [...], "edges": [...]}                │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Query 1: Find all functions                      │       │
│  │ query_nodes(result, filter1)                     │       │
│  │   │                                              │       │
│  │   ├─> [Python → Rust boundary]                  │       │
│  │   │                                              │       │
│  │   ├─> Build GraphIndex (200ms) ❌ WASTE          │       │
│  │   │    Vec<Node> → HashMap<String, Node>        │       │
│  │   │                                              │       │
│  │   ├─> Filter nodes in Rust (1ms)                │       │
│  │   │                                              │       │
│  │   └─> [Rust → Python boundary]                  │       │
│  │                                                  │       │
│  │ Total: 201ms                                     │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Query 2: Find classes starting with "Test"      │       │
│  │ query_nodes(result, filter2)                     │       │
│  │   │                                              │       │
│  │   ├─> [Python → Rust boundary]                  │       │
│  │   │                                              │       │
│  │   ├─> Build GraphIndex (200ms) ❌ WASTE AGAIN!   │       │
│  │   │    Vec<Node> → HashMap<String, Node>        │       │
│  │   │                                              │       │
│  │   ├─> Filter nodes in Rust (1ms)                │       │
│  │   │                                              │       │
│  │   └─> [Rust → Python boundary]                  │       │
│  │                                                  │       │
│  │ Total: 201ms                                     │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  Total Time: 402ms (for 2 queries)                          │
│  Wasted Time: 400ms (rebuilding GraphIndex twice)           │
└─────────────────────────────────────────────────────────────┘
```

### New Architecture (GOOD ✅)

```
┌─────────────────────────────────────────────────────────────┐
│ Python Application                                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  # IR Indexing (one-time)                                   │
│  result = run_ir_indexing_pipeline(...)                     │
│  # Returns: {"nodes": [...], "edges": [...]}                │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Build PyGraphIndex (ONCE)                        │       │
│  │ graph_index = PyGraphIndex(result)               │       │
│  │   │                                              │       │
│  │   ├─> [Python → Rust boundary]                  │       │
│  │   │                                              │       │
│  │   ├─> Build GraphIndex (200ms) ✅ ONCE           │       │
│  │   │    Vec<Node> → HashMap<String, Node>        │       │
│  │   │                                              │       │
│  │   ├─> Cache in Rust memory                      │       │
│  │   │    PyGraphIndex { index: GraphIndex }       │       │
│  │   │                                              │       │
│  │   └─> [Rust → Python: Handle to PyGraphIndex]  │       │
│  │                                                  │       │
│  │ Total: 200ms                                     │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Query 1: Find all functions                      │       │
│  │ graph_index.query_nodes(filter1)                 │       │
│  │   │                                              │       │
│  │   ├─> [Python → Rust boundary]                  │       │
│  │   │                                              │       │
│  │   ├─> Use CACHED GraphIndex (0ms) ✅             │       │
│  │   │    self.index.find_nodes_by_name()          │       │
│  │   │                                              │       │
│  │   ├─> Filter in Rust iterator (1ms)             │       │
│  │   │                                              │       │
│  │   └─> [Rust → Python: Results only]             │       │
│  │                                                  │       │
│  │ Total: 1ms                                       │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Query 2: Find classes starting with "Test"      │       │
│  │ graph_index.query_nodes(filter2)                 │       │
│  │   │                                              │       │
│  │   ├─> [Python → Rust boundary]                  │       │
│  │   │                                              │       │
│  │   ├─> Use CACHED GraphIndex (0ms) ✅             │       │
│  │   │    self.index.find_nodes_by_name()          │       │
│  │   │                                              │       │
│  │   ├─> Filter in Rust iterator (1ms)             │       │
│  │   │                                              │       │
│  │   └─> [Rust → Python: Results only]             │       │
│  │                                                  │       │
│  │ Total: 1ms                                       │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  Total Time: 202ms (for 2 queries)                          │
│  Wasted Time: 0ms ✅                                         │
│  Speedup: 2x (and scales with more queries)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Where Does Traversal Happen?

### Old Approach: Rebuilds on Every Query

```rust
// codegraph_ir.query_nodes(result, filter)  ← Python calls this

#[pyfunction]
pub fn query_nodes(ir_result_bytes: &[u8], filter: &NodeFilter) -> PyResult<PyBytes> {
    // ❌ Build GraphIndex EVERY TIME (200ms waste)
    let index = build_graph_index_from_result(ir_result_bytes)?;

    // ✅ Traversal happens in Rust (this is good)
    let base_nodes = index.find_nodes_by_name(name);

    // ✅ Filtering happens in Rust (this is good)
    let filtered: Vec<Node> = base_nodes.into_iter()
        .filter(|node| matches_filter(node, filter))
        .collect();

    Ok(PyBytes::new(py, &result_bytes))
}

// Problem: GraphIndex is discarded after each query!
// Next query rebuilds it from scratch!
```

### New Approach: Caches GraphIndex in Rust

```rust
// graph_index = PyGraphIndex(result)  ← Python builds ONCE
// graph_index.query_nodes(filter)     ← Python reuses many times

#[pyclass]
pub struct PyGraphIndex {
    index: GraphIndex,  // ✅ Cached in RUST memory (persists across calls)
}

#[pymethods]
impl PyGraphIndex {
    #[new]
    fn new(ir_result_bytes: &[u8]) -> PyResult<Self> {
        // ✅ Build GraphIndex ONCE (200ms, but only once)
        let index = build_graph_index_from_result(ir_result_bytes)?;

        // ✅ Store in Rust struct (Python gets a handle)
        Ok(Self { index })
    }

    fn query_nodes(&self, filter: &NodeFilter) -> PyResult<PyBytes> {
        // ✅ Reuse CACHED GraphIndex (0ms)
        let base_nodes = self.index.find_nodes_by_name(name);

        // ✅ Traversal happens in Rust
        let filtered: Vec<Node> = base_nodes.into_iter()
            .filter(|node| matches_filter(node, filter))
            .collect();

        Ok(PyBytes::new(py, &result_bytes))
    }
}

// Solution: GraphIndex persists in PyGraphIndex.index!
// Queries reuse it without rebuilding!
```

---

## Memory Layout

### Old Approach

```
Python Heap:
  result = {"nodes": [...], "edges": [...]}

Rust Stack (per query):
  query_nodes() {
      index = build_graph_index(...)  ← Builds HashMap
      // ... use index ...
  }  ← index destroyed after function returns!

  query_nodes() {
      index = build_graph_index(...)  ← Builds HashMap AGAIN!
      // ... use index ...
  }  ← index destroyed after function returns!
```

### New Approach

```
Python Heap:
  result = {"nodes": [...], "edges": [...]}
  graph_index = PyGraphIndex(...)  ← Python handle to Rust object

Rust Heap (persistent):
  PyGraphIndex {
      index: GraphIndex {
          nodes_by_id: HashMap {...},      ← Persists across queries
          edges_from: HashMap {...},       ← Persists across queries
          edges_to: HashMap {...},         ← Persists across queries
          nodes_by_name: HashMap {...},    ← Persists across queries
      }
  }

Rust Stack (per query):
  query_nodes(&self) {
      base_nodes = self.index.find_nodes_by_name(...)  ← Uses cached HashMap
      // ... filter ...
  }
```

---

## Speedup Analysis

### For 10 Queries

**Old Approach:**
```
Query 1: 200ms (build) + 1ms (filter) = 201ms
Query 2: 200ms (build) + 1ms (filter) = 201ms
Query 3: 200ms (build) + 1ms (filter) = 201ms
...
Query 10: 200ms (build) + 1ms (filter) = 201ms

Total: 2010ms
Wasted: 2000ms (rebuilding GraphIndex 10 times)
```

**New Approach:**
```
Build: 200ms (ONCE)
Query 1: 0ms (cached) + 1ms (filter) = 1ms
Query 2: 0ms (cached) + 1ms (filter) = 1ms
Query 3: 0ms (cached) + 1ms (filter) = 1ms
...
Query 10: 0ms (cached) + 1ms (filter) = 1ms

Total: 210ms
Wasted: 0ms

Speedup: 9.6x (2010ms / 210ms)
```

### For 100 Queries

**Old Approach:** 20,100ms (20 seconds!)
**New Approach:** 300ms
**Speedup:** 67x

### For 1000 Queries

**Old Approach:** 201,000ms (3.35 minutes!)
**New Approach:** 1,200ms (1.2 seconds)
**Speedup:** 167x

---

## Key Insight

**The more queries you run, the bigger the speedup!**

This is exactly the use case for:
- IDE autocomplete (hundreds of queries per minute)
- Interactive graph exploration (clicking around the graph)
- Batch analysis (analyzing patterns across the codebase)

PyGraphIndex makes all of these use cases fast by caching the GraphIndex in Rust memory.
