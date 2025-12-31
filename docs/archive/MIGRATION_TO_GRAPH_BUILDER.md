# Migration Guide: query_engine.GraphIndex → graph_builder.GraphIndex

## Status: Waiting for graph_builder completion

**Current state:**
- ✅ query_engine.GraphIndex marked as DEPRECATED
- ✅ PyGraphIndex uses deprecated version (temporary)
- ⏳ Waiting for graph_builder to be completed
- ⏳ Migration will happen after graph_builder is ready

---

## Why Migrate?

### Current (Deprecated)
```rust
// features/query_engine/infrastructure/graph_index.rs
pub struct GraphIndex {
    nodes_by_id: HashMap<String, Node>,         // ❌ std HashMap (slow)
    edges_from: HashMap<String, Vec<Edge>>,     // ❌ No string interning
    edges_to: HashMap<String, Vec<Edge>>,       // ❌ Basic features only
    nodes_by_name: HashMap<String, Vec<Node>>,
}
```

**Problems:**
- ❌ std::HashMap (2-3x slower than AHashMap)
- ❌ No string interning (2x memory waste)
- ❌ No EdgeKind-specific indexes
- ❌ No framework awareness
- ❌ Limited query capabilities

---

### Target (SOTA)
```rust
// features/graph_builder/domain/mod.rs
pub struct GraphIndex {
    // ✅ Reverse indexes
    called_by: AHashMap<InternedString, Vec<InternedString>>,
    imported_by: AHashMap<InternedString, Vec<InternedString>>,
    contains_children: AHashMap<InternedString, Vec<InternedString>>,

    // ✅ EdgeKind-specific (very powerful!)
    outgoing_by_kind: AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,
    incoming_by_kind: AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,

    // ✅ Framework awareness
    routes_by_path: AHashMap<InternedString, Vec<InternedString>>,
    services_by_domain: AHashMap<InternedString, Vec<InternedString>>,
    request_flow_index: AHashMap<InternedString, RequestFlow>,
}

pub struct GraphNode {
    id: InternedString,           // ✅ String interning
    kind: NodeKind,
    fqn: InternedString,
    name: InternedString,
    attrs: AHashMap<String, serde_json::Value>,  // ✅ AHashMap
}
```

**Benefits:**
- ✅ 50% memory reduction (string interning)
- ✅ 2-3x faster (AHashMap)
- ✅ EdgeKind-specific filtering (O(1))
- ✅ Framework awareness (routes, services)
- ✅ Rich query capabilities

---

## Migration Steps (When Ready)

### Step 1: Update PyGraphIndex imports

```rust
// adapters/pyo3/api/query.rs

// Before
use crate::features::query_engine::infrastructure::GraphIndex;

// After
use crate::features::graph_builder::domain::{
    GraphIndex,
    GraphDocument,
    GraphNode,
    GraphEdge,
    InternedString,
};
```

### Step 2: Update build_graph_index_from_result

```rust
// Before (current)
fn build_graph_index_from_result(result_bytes: &[u8]) -> PyResult<GraphIndex> {
    let result: HashMap<String, serde_json::Value> = rmp_serde::from_slice(result_bytes)?;

    let nodes_json = result.get("nodes")?;
    let edges_json = result.get("edges")?;

    let nodes: Vec<Node> = serde_json::from_value(nodes_json.clone())?;
    let edges: Vec<Edge> = serde_json::from_value(edges_json.clone())?;

    let mut ir_doc = IRDocument::new("query".to_string());
    ir_doc.nodes = nodes;
    ir_doc.edges = edges;

    Ok(GraphIndex::new(&ir_doc))
}

// After (future)
fn build_graph_index_from_result(result_bytes: &[u8]) -> PyResult<GraphIndex> {
    let result: HashMap<String, serde_json::Value> = rmp_serde::from_slice(result_bytes)?;

    let nodes_json = result.get("nodes")?;
    let edges_json = result.get("edges")?;

    // Convert to GraphNode/GraphEdge (with string interning)
    let nodes: Vec<GraphNode> = serde_json::from_value(nodes_json.clone())?;
    let edges: Vec<GraphEdge> = serde_json::from_value(edges_json.clone())?;

    // Build GraphDocument (includes index!)
    let graph_doc = GraphDocument::new(nodes, edges);

    // Return the already-built index
    Ok(graph_doc.index)
}
```

### Step 3: Update matches_filter (if needed)

```rust
// Check if GraphNode/GraphEdge API changed
fn matches_filter(node: &GraphNode, filter: &NodeFilter) -> bool {
    // Update field access if needed (e.g., node.name is InternedString)

    if let Some(kind_str) = &filter.kind {
        // ... same logic ...
    }

    if let Some(name) = &filter.name {
        // InternedString comparison
        if node.name.as_ref() != name {
            return false;
        }
    }

    // ... rest of filters ...

    true
}
```

### Step 4: Test migration

```bash
# Rebuild Rust module
cd packages/codegraph-rust/codegraph-ir
maturin develop

# Run performance test
cd ../../..
.venv/bin/python test_pygraphindex_performance.py
```

**Expected improvements:**
- Build time: 800ms → ~500ms (37% faster)
- Memory usage: 50% reduction
- Query time: Similar or slightly faster

### Step 5: Remove deprecated code

After migration is complete and tested:

```bash
# Remove deprecated GraphIndex
rm packages/codegraph-rust/codegraph-ir/src/features/query_engine/infrastructure/graph_index.rs

# Update mod.rs
# Remove: pub mod graph_index;
```

---

## API Compatibility

### Node access

```rust
// Before
let node = index.get_node(node_id);  // Returns Option<&Node>

// After
let node = index.get_node(node_id);  // Returns Option<&GraphNode>
// May need to update field access (e.g., node.name is InternedString)
```

### Edge queries

```rust
// Before
let outgoing = index.get_outgoing_edges(node_id);

// After
// Multiple options:
let outgoing = index.get_outgoing_edges(node_id);  // All edges
let calls = index.get_outgoing_by_kind(node_id, EdgeKind::Calls);  // Specific kind
```

### Name lookup

```rust
// Before
let nodes = index.find_nodes_by_name(name);

// After
// May need to use GraphDocument.nodes or build name index
// Check graph_builder API for name lookup
```

---

## Performance Expectations

### Build Time
```
Current:  800ms
Expected: 500ms (37% faster due to AHashMap)
```

### Memory Usage
```
Current:  ~100MB (for large codebase)
Expected: ~50MB (50% reduction via string interning)
```

### Query Time
```
Current:  3-5ms per query
Expected: 2-4ms per query (slightly faster due to AHashMap)
```

### New Capabilities
```
✅ EdgeKind filtering: O(1) instead of O(edges)
✅ Framework queries: routes, services, decorators
✅ Reverse indexes: called_by, imported_by, etc.
```

---

## Rollback Plan

If migration causes issues:

1. **Revert import changes**
   ```rust
   // Switch back to deprecated version
   use crate::features::query_engine::infrastructure::GraphIndex;
   ```

2. **Keep deprecated code**
   - Don't delete query_engine/infrastructure/graph_index.rs yet
   - Test thoroughly before removing

3. **Report issues**
   - Document any incompatibilities
   - File issues for graph_builder API adjustments

---

## Timeline

1. ⏳ **Now**: Wait for graph_builder completion
2. ⏳ **Next**: Test graph_builder in isolation
3. ⏳ **Then**: Migrate PyGraphIndex
4. ⏳ **Finally**: Remove deprecated code

---

## Notes

- **Backward compatibility**: Python API stays the same
- **Performance**: Should improve across the board
- **Features**: New capabilities (EdgeKind filtering, framework queries)
- **Risk**: Low (can rollback easily)

---

## Questions for graph_builder team

1. Is GraphDocument the main API? (yes, includes nodes + edges + index)
2. How to query nodes by name? (build custom index or iterate?)
3. How to serialize GraphNode/GraphEdge to msgpack? (for Python)
4. Any special initialization needed?
