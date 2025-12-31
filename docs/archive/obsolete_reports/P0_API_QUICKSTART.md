# P0 API Quickstart Guide - RFC-RUST-SDK-002

**Quick reference for using the new QueryDSL P0 features**

---

## 1. Expression AST - Type-Safe Filtering

### Basic Usage

```rust
use codegraph_ir::features::query_engine::{Expr, ExprBuilder, Value, Op};

// Simple equality check
let expr = ExprBuilder::eq("language", "python");

// Numeric comparison
let expr = ExprBuilder::gte("complexity", 10);

// String operations
let expr = ExprBuilder::contains("name", "process");
let expr = ExprBuilder::regex("name", "process.*");
let expr = ExprBuilder::starts_with("file_path", "src/");
let expr = ExprBuilder::ends_with("name", "_test");

// Boolean logic
let expr = ExprBuilder::and(vec![
    ExprBuilder::eq("language", "python"),
    ExprBuilder::gte("complexity", 10),
]);

let expr = ExprBuilder::or(vec![
    ExprBuilder::eq("language", "python"),
    ExprBuilder::eq("language", "rust"),
]);

let expr = ExprBuilder::not(
    ExprBuilder::eq("language", "javascript")
);

// Null checks
let expr = ExprBuilder::is_null("optional_field");
let expr = ExprBuilder::is_not_null("required_field");
```

### Advanced - Complex Queries

```rust
// (language == "python" AND complexity >= 10) OR name contains "test"
let expr = ExprBuilder::or(vec![
    ExprBuilder::and(vec![
        ExprBuilder::eq("language", "python"),
        ExprBuilder::gte("complexity", 10),
    ]),
    ExprBuilder::contains("name", "test"),
]);
```

### Canonicalization for Deterministic Hashing

```rust
let expr = ExprBuilder::and(vec![
    ExprBuilder::eq("language", "python"),
    ExprBuilder::gte("complexity", 10),
]);

// Canonicalize (sort And/Or operands, normalize floats)
let canonical = expr.canonicalize()?;

// Compute deterministic hash
let hash = expr.hash_canonical()?;  // [u8; 32]
```

**Benefits**:
- Same query → same hash → caching works
- Order-independent (And/Or operands sorted)
- Float edge cases handled (NaN rejected, -0.0 normalized)

---

## 2. Value Types - Arrow/JSON Compatible

### All Supported Types

```rust
use codegraph_ir::features::query_engine::Value;

// Primitives
let null = Value::Null;
let int = Value::Int(42);
let float = Value::Float(3.14);
let string = Value::String("hello".to_string());
let bool = Value::Bool(true);

// Collections
let list = Value::List(vec![
    Value::Int(1),
    Value::Int(2),
    Value::Int(3),
]);

use std::collections::BTreeMap;
let mut obj = BTreeMap::new();
obj.insert("key1".to_string(), Value::String("value1".to_string()));
obj.insert("key2".to_string(), Value::Int(42));
let object = Value::Object(obj);

// Binary data
let bytes = Value::Bytes(vec![0x01, 0x02, 0x03]);

// Timestamp (microseconds)
let timestamp = Value::Timestamp(1672531200000000);  // 2023-01-01 00:00:00 UTC
```

### From Conversions

```rust
// Auto-convert common types
let expr = ExprBuilder::eq("count", 42);           // i64
let expr = ExprBuilder::eq("ratio", 3.14);         // f64
let expr = ExprBuilder::eq("name", "test");        // &str
let expr = ExprBuilder::eq("enabled", true);       // bool
```

---

## 3. Node/Edge Selectors - Path Query Foundation

### NodeSelector - Select Start/End Nodes

```rust
use codegraph_ir::features::query_engine::{NodeSelectorBuilder, NodeSelector};

// By direct ID
let selector = NodeSelectorBuilder::by_id("node_abc123");

// By fully qualified name
let selector = NodeSelectorBuilder::by_name("process_data");

// By name with scope (file/module)
let selector = NodeSelectorBuilder::by_name_scoped(
    "process_data",
    "src/data/processor.py"
);

// By node kind
let selector = NodeSelectorBuilder::by_kind("function");

// By kind with filters
let selector = NodeSelectorBuilder::by_kind_filtered(
    "function",
    vec![
        ExprBuilder::gte("complexity", 10),
        ExprBuilder::contains("name", "process"),
    ]
);

// Union of multiple selectors
let selector = NodeSelectorBuilder::union(vec![
    NodeSelectorBuilder::by_name("main"),
    NodeSelectorBuilder::by_name("run"),
]);
```

### EdgeSelector - Filter Edges During Traversal

```rust
use codegraph_ir::features::query_engine::{EdgeSelectorBuilder, EdgeSelector};

// Any edge type
let selector = EdgeSelectorBuilder::any();

// Specific edge kind
let selector = EdgeSelectorBuilder::by_kind("calls");

// Multiple edge kinds
let selector = EdgeSelectorBuilder::by_kinds(vec![
    "calls".to_string(),
    "imports".to_string(),
]);

// Edge filter expression
let selector = EdgeSelectorBuilder::by_filter(vec![
    ExprBuilder::eq("weight", 1),
]);
```

### PathLimits - Safety Guardrails

```rust
use codegraph_ir::features::query_engine::PathLimits;

// Use safe defaults (recommended)
let limits = PathLimits::default();
// max_paths: 100
// max_expansions: 10,000
// timeout_ms: 30,000

// Custom limits with validation
let limits = PathLimits::new(
    1000,    // max_paths
    50_000,  // max_expansions
    60_000,  // timeout_ms
)?;

// Add max path length
let limits = PathLimits::default()
    .with_max_length(50);

// Unlimited (DANGEROUS - only for trusted queries)
let limits = PathLimits::unlimited();
```

**Safety Contract**:
- Default limits prevent graph explosion (DoS protection)
- Conservative for production use
- Can be overridden when needed

---

## 4. Search Score Semantics - Reproducible Search

### ScoreSemantics - Explicit Score Interpretation

```rust
use codegraph_ir::features::query_engine::ScoreSemantics;

// BM25 with explicit parameters
let semantics = ScoreSemantics::BM25 { k1: 1.2, b: 0.75 };

// Cosine similarity [-1, 1]
let semantics = ScoreSemantics::CosineSimilarity;

// Dot product (unbounded)
let semantics = ScoreSemantics::DotProduct;

// L2 distance [0, ∞) - lower is better
let semantics = ScoreSemantics::L2Distance;

// Fused (hybrid search)
let semantics = ScoreSemantics::Fused {
    strategy: FusionStrategy::RRF { k: 60 }
};
```

### SearchHitRow - Complete Score Information

```rust
use codegraph_ir::features::query_engine::{SearchHitRow, SearchSource};

let hit = SearchHitRow::new(
    "node123".to_string(),
    15.5,                                      // score_raw (BM25 unbounded)
    0.85,                                      // score_norm [0, 1]
    0.85,                                      // sort_key (higher = better)
    ScoreSemantics::BM25 { k1: 1.2, b: 0.75 },
    SearchSource::Lexical,
    1,                                         // rank (1-based)
);

// Add metadata
let hit = hit.with_metadata(
    "file_path".to_string(),
    Value::String("main.rs".to_string())
);

// Access fields
println!("Node: {}", hit.node_id);
println!("Raw score: {}", hit.score_raw);
println!("Normalized: {}", hit.score_norm);
println!("Rank: {}", hit.rank);
```

**Benefits**:
- `score_raw`: Original engine output (for debugging)
- `score_norm`: Normalized [0, 1] (for comparison)
- `sort_key`: Always "higher = better" (for deterministic sorting)
- `score_semantics`: Documents score interpretation

---

## 5. Fusion Config - Hybrid Search Specification

### FusionStrategy

```rust
use codegraph_ir::features::query_engine::{FusionStrategy, FusionConfig};
use std::collections::HashMap;

// Reciprocal Rank Fusion (default k=60)
let strategy = FusionStrategy::RRF { k: 60 };

// Linear combination with weights
let mut weights = HashMap::new();
weights.insert("lexical".to_string(), 0.3);
weights.insert("semantic".to_string(), 0.7);

let strategy = FusionStrategy::LinearCombination {
    weights,
    normalize_weights: true,  // Auto-normalize to sum=1
};

// Max score across channels
let strategy = FusionStrategy::Max;
```

### FusionConfig - Complete Specification

```rust
use codegraph_ir::features::query_engine::{
    FusionConfig, ScoreNormalization, TieBreakRule
};

// Default config (RRF with rank-based normalization)
let config = FusionConfig::default();

// RRF with custom k
let config = FusionConfig::rrf(100);

// Linear combination
let mut weights = HashMap::new();
weights.insert("lexical".to_string(), 0.3);
weights.insert("semantic".to_string(), 0.7);
let config = FusionConfig::linear(weights);

// Max fusion
let config = FusionConfig::max();

// Builder pattern
let config = FusionConfig::rrf(60)
    .with_normalization(ScoreNormalization::MinMax)
    .with_tie_break(TieBreakRule::NodeIdAsc)
    .with_pool_size(500);
```

### Score Normalization

```rust
use codegraph_ir::features::query_engine::ScoreNormalization;

let norm = ScoreNormalization::None;       // Use raw scores
let norm = ScoreNormalization::MinMax;     // (x - min) / (max - min)
let norm = ScoreNormalization::ZScore;     // (x - mean) / stddev
let norm = ScoreNormalization::RankBased;  // Percentile rank (default)
```

### Tie-Breaking Rules

```rust
use codegraph_ir::features::query_engine::TieBreakRule;

// Stable sort by node_id (default)
let rule = TieBreakRule::NodeIdAsc;

// Channel priority order
let rule = TieBreakRule::ChannelPriority(vec![
    "lexical".to_string(),
    "semantic".to_string(),
]);

// Custom field
let rule = TieBreakRule::Field {
    name: "timestamp".to_string(),
    ascending: false,
};
```

---

## 6. Complete Example - Hybrid Search Query

```rust
use codegraph_ir::features::query_engine::{
    ExprBuilder, NodeSelectorBuilder, EdgeSelectorBuilder,
    PathLimits, FusionConfig, ScoreSemantics, SearchSource,
    SearchHitRow, Value,
};
use std::collections::HashMap;

// 1. Build filter expression
let filter = ExprBuilder::and(vec![
    ExprBuilder::eq("language", "python"),
    ExprBuilder::gte("complexity", 10),
    ExprBuilder::contains("name", "process"),
]);

// Canonicalize for deterministic hashing
let canonical_filter = filter.clone().canonicalize()?;
let filter_hash = filter.hash_canonical()?;

// 2. Build node selector for path query
let from = NodeSelectorBuilder::by_name_scoped(
    "main",
    "src/main.py"
);

let to = NodeSelectorBuilder::by_kind_filtered(
    "function",
    vec![ExprBuilder::contains("name", "handler")]
);

// 3. Configure path limits
let limits = PathLimits::new(100, 10_000, 30_000)?
    .with_max_length(50);

// 4. Configure hybrid search fusion
let mut weights = HashMap::new();
weights.insert("lexical".to_string(), 0.3);
weights.insert("semantic".to_string(), 0.7);

let fusion_config = FusionConfig::linear(weights)
    .with_normalization(ScoreNormalization::MinMax)
    .with_tie_break(TieBreakRule::NodeIdAsc)
    .with_pool_size(1000);

// 5. Create search hit with complete semantics
let hit = SearchHitRow::new(
    "node_xyz".to_string(),
    42.5,                                    // BM25 raw score
    0.92,                                    // Normalized [0, 1]
    0.92,                                    // Sort key
    ScoreSemantics::Fused {
        strategy: fusion_config.strategy.clone()
    },
    SearchSource::Hybrid,
    1,
);

// Add metadata
let hit = hit.with_metadata(
    "file_path".to_string(),
    Value::String("src/processor.py".to_string())
);

println!("Found: {} (score: {}, rank: {})",
    hit.node_id, hit.score_norm, hit.rank);
```

---

## 7. Python API (Future)

**Planned Python bindings** (for reference):

```python
from codegraph_ir import (
    ExprBuilder, NodeSelectorBuilder, PathLimits,
    FusionConfig, ScoreSemantics
)

# Django-style filtering (compiles to Expr AST)
query = snap.query().nodes().where(
    language="python",
    complexity__gte=10,
    name__regex="process.*"
)

# Path query with selectors
paths = snap.query().paths(
    from_=NodeSelectorBuilder.by_name("main"),
    to=NodeSelectorBuilder.by_kind("function")
).via("calls").depth(5).limits(
    PathLimits.default()
).execute()

# Hybrid search with fusion
results = snap.query().search().hybrid(
    query="authentication logic",
    embedding=[0.1, 0.2, ...],
).fusion_config(
    FusionConfig.linear({"lexical": 0.3, "semantic": 0.7})
).execute()

# Each result has complete score information
for hit in results:
    print(f"{hit.node_id}: {hit.score_norm} ({hit.score_semantics})")
```

---

## 8. Key Principles

### Determinism
- All queries produce identical results given same input
- Canonicalization ensures order-independence
- Score semantics document interpretation

### FFI Safety
- No Rust closures in public API
- All types fully serializable
- Safe to call from Python/other languages

### Production Safety
- PathLimits prevent DoS attacks
- Conservative defaults
- Validation on inputs

### Reproducibility
- Complete semantic contracts
- Explicit score interpretation
- Deterministic tie-breaking

---

## 9. Testing Your Queries

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_expression_determinism() {
        // Same expression, different order
        let expr1 = ExprBuilder::and(vec![
            ExprBuilder::eq("a", "1"),
            ExprBuilder::eq("b", "2"),
        ]);

        let expr2 = ExprBuilder::and(vec![
            ExprBuilder::eq("b", "2"),
            ExprBuilder::eq("a", "1"),
        ]);

        // Should produce same hash after canonicalization
        let hash1 = expr1.hash_canonical().unwrap();
        let hash2 = expr2.hash_canonical().unwrap();

        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_fusion_config_defaults() {
        let config = FusionConfig::default();

        // Verify RRF with k=60
        match config.strategy {
            FusionStrategy::RRF { k } => assert_eq!(k, 60),
            _ => panic!("Expected RRF"),
        }

        // Verify safe defaults
        assert_eq!(config.candidate_pool_size, 1000);
    }

    #[test]
    fn test_path_limits_safety() {
        let limits = PathLimits::default();

        // Verify conservative defaults
        assert_eq!(limits.max_paths, 100);
        assert_eq!(limits.max_expansions, 10_000);
        assert_eq!(limits.timeout_ms, 30_000);
    }
}
```

---

## 10. Common Patterns

### Pattern 1: Complex Filter with Canonicalization
```rust
let filter = ExprBuilder::and(vec![
    ExprBuilder::eq("language", "python"),
    ExprBuilder::or(vec![
        ExprBuilder::contains("name", "test"),
        ExprBuilder::contains("name", "spec"),
    ]),
    ExprBuilder::gte("coverage", 80),
]);

let canonical = filter.canonicalize()?;
let hash = canonical.clone().hash_canonical()?;
```

### Pattern 2: Path Query with Safety
```rust
let from = NodeSelectorBuilder::by_name("entrypoint");
let to = NodeSelectorBuilder::by_kind("database_query");
let limits = PathLimits::default();

// Query is safe: max 100 paths, 10k expansions, 30s timeout
```

### Pattern 3: Hybrid Search with RRF
```rust
let fusion = FusionConfig::rrf(60)
    .with_normalization(ScoreNormalization::RankBased)
    .with_tie_break(TieBreakRule::NodeIdAsc);

// Deterministic: RRF k=60, rank-based norm, node_id tie-break
```

---

**End of Quickstart Guide**

For complete API reference, see:
- Expression AST: `src/features/query_engine/expression.rs`
- Selectors: `src/features/query_engine/selectors.rs`
- Search Types: `src/features/query_engine/search_types.rs`
- RFC Document: `docs/rfcs/RFC-RUST-SDK-002-QueryDSL-Design-Correction.md`
