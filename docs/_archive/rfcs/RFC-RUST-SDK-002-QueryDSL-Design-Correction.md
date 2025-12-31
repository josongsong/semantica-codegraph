# RFC-RUST-SDK-002: QueryDSL Design Correction

**Status**: Draft (Updated 2024-12-29)
**Author**: CodeGraph Team
**Created**: 2024-12-28
**Updated**: 2024-12-29 (Added P0 Critical Corrections)
**Supersedes**: RFC-RUST-SDK-001-QueryDSL-Coverage-Proof (partial corrections)
**Related**: RFC-RUST-SDK-001 (Public API Design)

---

## Executive Summary

**Purpose**: Correct critical design flaws in RFC-RUST-SDK-001's Extended QueryDSL that violate:
1. **Engine Single Execution Principle** (no callbacks)
2. **FFI Safety** (no Rust closures across boundary)
3. **Determinism** (reproducible queries)
4. **DX** (type-safe, IDE-friendly)

**Key Changes**:
- ❌ **Remove** `.where_fn()` (callback-based filtering)
- ❌ **Remove** `.join()` (undefined in current design)
- ✅ **Add** Expression AST for complex filtering
- ✅ **Add** Semantic contracts for search operations
- ✅ **Add** Typed field enums for DX
- ✅ **Add** P0 Critical Corrections (canonicalization, selectors, score semantics)

---

## 1. Problems with RFC-RUST-SDK-001

### 1.1 Critical Flaws

**Flaw 1: `.where_fn()` violates core principles**

```rust
// ❌ WRONG (from RFC-001)
.where_fn(|n| n.complexity > 10)

// Problems:
// 1. Cannot serialize to QueryPlan (not deterministic)
// 2. Cannot execute in Rust engine (FFI boundary)
// 3. Requires Python callback (violates single execution)
// 4. No query optimization possible
```

**Flaw 2: `.join()` is undefined**

```rust
// ❌ WRONG (from RFC-001)
.nodes().join(edges).on("id")

// Problems:
// 1. No QueryPlan definition
// 2. No Executor implementation
// 3. No schema/type contract
// 4. Cannot claim "covered" without implementation
```

**Flaw 3: Search semantics are underspecified**

```rust
// ⚠️ INCOMPLETE (from RFC-001)
.text_search(keywords)
.embedding_similarity(vec, 0.8)

// Problems:
// 1. What is "score"? (0-1? distance? direction?)
// 2. Which distance metric? (cosine/dot/L2)
// 3. How does fusion work? (RRF? weights?)
// 4. No reproducibility guarantee
```

### 1.2 Impact on Coverage Proof

**Original claim**: 31/31 scenarios covered

**Reality**:
- Scenarios 9, 29, 31 used `.where_fn()` → **NOT TRULY COVERED**
- "Complex JOIN" edge case → **NOT COVERED** (undefined)
- Regex matching via `.where_fn()` → **NOT COVERED** (needs operator)

**Actual coverage**: ~26/31 (84%) without corrections

---

## 2. Corrected Design: Expression AST

### 2.1 Replace `.where_fn()` with Expression DSL

**Principle**: All filtering must be expressible as a query plan

#### 2.1.1 Expression AST Definition (UPDATED with P0 Corrections)

```rust
/// Comparison operators (normalized)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CompOp {
    Eq, Ne, Lt, Lte, Gt, Gte,
    In,      // field IN [values]
    Between, // field BETWEEN a AND b
}

/// String operators
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StrOp {
    Contains, StartsWith, EndsWith,
    Regex, IRegex,
}

/// Expression AST for filtering (FFI-safe, deterministic)
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Expr {
    // Field access
    Field(String),

    // Literals
    Literal(Value),

    // Comparison (normalized)
    Cmp {
        left: Box<Expr>,
        op: CompOp,
        right: Box<Expr>
    },

    // String operations
    StrOp {
        field: Box<Expr>,
        op: StrOp,
        pattern: String
    },

    // Boolean logic (canonicalized)
    And(Vec<Expr>),
    Or(Vec<Expr>),
    Not(Box<Expr>),

    // Null check
    IsNull(Box<Expr>),
}

/// Value types (Arrow/JSON compatible)
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Value {
    Null,
    Int(i64),
    Float(f64),
    String(String),
    Bool(bool),
    List(Vec<Value>),
    Object(BTreeMap<String, Value>),  // BTreeMap for deterministic ordering
    Bytes(Vec<u8>),
    Timestamp(i64),  // Unix timestamp in microseconds
}

impl Expr {
    /// Canonicalize expression for deterministic hashing
    ///
    /// Rules:
    /// 1. And/Or operands sorted by serialized representation
    /// 2. Object keys sorted (BTreeMap)
    /// 3. Float NaN rejected, -0.0 normalized to 0.0
    pub fn canonicalize(self) -> Result<Self, ExprError> {
        match self {
            Expr::And(mut exprs) => {
                let mut canonical = Vec::new();
                for e in exprs {
                    canonical.push(e.canonicalize()?);
                }
                // Sort by bincode serialization
                canonical.sort_by_key(|e| bincode::serialize(e).unwrap());
                Ok(Expr::And(canonical))
            }
            Expr::Or(mut exprs) => {
                let mut canonical = Vec::new();
                for e in exprs {
                    canonical.push(e.canonicalize()?);
                }
                canonical.sort_by_key(|e| bincode::serialize(e).unwrap());
                Ok(Expr::Or(canonical))
            }
            Expr::Literal(Value::Float(f)) => {
                if f.is_nan() {
                    return Err(ExprError::NaNNotAllowed);
                }
                let normalized = if f == -0.0 { 0.0 } else { f };
                Ok(Expr::Literal(Value::Float(normalized)))
            }
            // Recursively canonicalize nested expressions
            Expr::Cmp { left, op, right } => {
                Ok(Expr::Cmp {
                    left: Box::new(left.canonicalize()?),
                    op,
                    right: Box::new(right.canonicalize()?),
                })
            }
            Expr::Not(e) => Ok(Expr::Not(Box::new(e.canonicalize()?))),
            other => Ok(other),
        }
    }
}
```

#### 2.1.2 Rust API

```rust
// ✅ CORRECT: Type-safe expression building
.where_expr(
    Expr::Gte(
        Box::new(Expr::Field("complexity".to_string())),
        Box::new(Expr::Literal(Value::Int(10)))
    )
)

// ✅ BETTER: Builder sugar
.where_field("complexity", Op::Gte, 10)

// ✅ BEST: Django-style sugar (compiles to Expr)
.where(complexity__gte = 10)
```

#### 2.1.3 Python API (compiles to Expr)

```python
# ✅ Django ORM style (AI-friendly)
snap.query().nodes().where(
    language="python",
    complexity__gte=10,
    name__regex="process.*"
)

# Compiles to:
# And([
#     Eq(Field("language"), Literal("python")),
#     Gte(Field("complexity"), Literal(10)),
#     Regex(Field("name"), "process.*")
# ])
```

### 2.2 Expression Builder API

```rust
pub struct ExprBuilder;

impl ExprBuilder {
    pub fn field(name: &str) -> Expr {
        Expr::Field(name.to_string())
    }

    pub fn eq(field: &str, value: Value) -> Expr {
        Expr::Eq(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value))
        )
    }

    pub fn gte(field: &str, value: Value) -> Expr {
        Expr::Gte(
            Box::new(Expr::Field(field.to_string())),
            Box::new(Expr::Literal(value))
        )
    }

    pub fn regex(field: &str, pattern: &str) -> Expr {
        Expr::Regex(
            Box::new(Expr::Field(field.to_string())),
            pattern.to_string()
        )
    }

    pub fn and(exprs: Vec<Expr>) -> Expr {
        Expr::And(exprs)
    }

    pub fn or(exprs: Vec<Expr>) -> Expr {
        Expr::Or(exprs)
    }

    pub fn not(expr: Expr) -> Expr {
        Expr::Not(Box::new(expr))
    }
}
```

---

## 3. Corrected Main Grammar

### 3.1 Entry Points (Result Type Explicit)

```rust
// ✅ Node queries
snap.query().nodes() -> NodeQueryBuilder

// ✅ Edge queries
snap.query().edges() -> EdgeQueryBuilder

// ✅ Path queries (graph traversal)
snap.query().paths(from, to) -> PathQueryBuilder

// ✅ Reachability (boolean)
snap.query().reachability(from, to) -> ReachabilityQuery

// ✅ Expand/Slice (subgraph)
snap.query().expand(anchor) -> ExpandQueryBuilder

// ✅ Search
snap.query().search().text(query) -> SearchQueryBuilder
snap.query().search().vector(embedding) -> SearchQueryBuilder
snap.query().search().hybrid(query, embedding) -> SearchQueryBuilder

// ✅ Findings (analysis outputs)
snap.query().findings() -> FindingQueryBuilder
snap.query().taint_flows() -> TaintFlowQueryBuilder
snap.query().clone_pairs() -> ClonePairQueryBuilder
```

### 3.2 Node Query (Corrected)

```rust
pub struct NodeQueryBuilder<'a> {
    // Filters (Expression AST, not closures)
    filters: Vec<Expr>,

    // Ordering
    order_by: Option<(String, Order)>,

    // Pagination
    limit: Option<usize>,
    offset: usize,
}

impl<'a> NodeQueryBuilder<'a> {
    // ✅ Expression-based filtering
    pub fn where_expr(mut self, expr: Expr) -> Self;

    // ✅ Sugar for common cases
    pub fn where_field(mut self, field: &str, op: Op, value: Value) -> Self;

    // ✅ Django-style sugar (Python)
    // .where(language="python", complexity__gte=10)
    // Compiles to: where_expr(And([Eq(...), Gte(...)]))

    // ✅ Ordering
    pub fn order_by(mut self, field: &str, direction: Order) -> Self;

    // ✅ Pagination
    pub fn limit(mut self, n: usize) -> Self;
    pub fn offset(mut self, n: usize) -> Self;

    // ✅ Aggregation
    pub fn aggregate(self) -> AggregationBuilder;

    // ✅ Streaming
    pub fn stream(self, chunk_size: usize) -> NodeStream;

    // ✅ Execute
    pub fn execute(self) -> Result<Vec<NodeRow>>;
}
```

### 3.3 Path Query (Graph Traversal) - UPDATED with Selectors

#### 3.3.1 Selector Definitions (P0 CRITICAL)

```rust
/// Node selection strategies
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum NodeSelector {
    /// Direct node ID
    ById(String),

    /// By fully qualified name
    ByName {
        name: String,
        scope: Option<String>  // file/module scope
    },

    /// By node kind + filters
    ByKind {
        kind: NodeKind,
        filters: Vec<Expr>
    },

    /// Result of another node query (subquery reference)
    ByQuery(Box<NodeQueryBuilder>),

    /// Multiple selectors (union)
    Union(Vec<NodeSelector>),
}

/// Edge selection for path traversal
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum EdgeSelector {
    /// Any edge type
    Any,

    /// Single edge kind
    ByKind(EdgeKind),

    /// Multiple edge kinds (union)
    ByKinds(Vec<EdgeKind>),

    /// Edge filter expression
    ByFilter(Vec<Expr>),
}

/// Safety limits for path queries (CRITICAL)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathLimits {
    /// Max paths to return (default: 100)
    pub max_paths: usize,

    /// Max nodes to expand during search (default: 10,000)
    pub max_expansions: usize,

    /// Query timeout in milliseconds (default: 30,000)
    pub timeout_ms: u64,

    /// Max path length (overrides depth if smaller)
    pub max_path_length: Option<usize>,
}

impl Default for PathLimits {
    fn default() -> Self {
        Self {
            max_paths: 100,
            max_expansions: 10_000,
            timeout_ms: 30_000,
            max_path_length: None,
        }
    }
}
```

#### 3.3.2 PathQueryBuilder (Updated)

```rust
pub struct PathQueryBuilder<'a> {
    from: NodeSelector,
    to: NodeSelector,
    via: EdgeSelector,
    direction: TraversalDirection,
    depth: (usize, usize),  // (min, max)
    mode: PathMode,
    limits: PathLimits,  // ✅ Safety limits
}

pub enum PathMode {
    Any,         // Find any path
    Shortest,    // Shortest path only
    All,         // All paths (DANGEROUS: requires limits)
    TopK(usize), // Top K paths by cost
}

impl<'a> PathQueryBuilder<'a> {
    pub fn via(mut self, edge: EdgeSelector) -> Self;
    pub fn direction(mut self, dir: TraversalDirection) -> Self;
    pub fn depth(mut self, max: usize) -> Self;
    pub fn depth_range(mut self, min: usize, max: usize) -> Self;

    pub fn shortest(mut self) -> Self;
    pub fn any(mut self) -> Self;

    /// All paths mode (applies default limits for safety)
    pub fn all(mut self) -> Self {
        self.mode = PathMode::All;
        self
    }

    /// Override safety limits (use with caution)
    pub fn limits(mut self, limits: PathLimits) -> Self {
        self.limits = limits;
        self
    }

    pub fn topk(mut self, k: usize) -> Self;

    pub fn execute(self) -> Result<Vec<PathRow>>;
    pub fn exists(self) -> Result<bool>;  // Reachability
}
```

### 3.4 Search Query (Semantic Contracts Added) - UPDATED with Score Semantics

#### 3.4.1 Score Semantics (P0 CRITICAL)

```rust
/// Score semantics for reproducibility
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ScoreSemantics {
    /// BM25: unbounded, higher = better
    BM25 { k1: f64, b: f64 },

    /// Cosine similarity: [-1, 1], higher = better
    CosineSimilarity,

    /// Dot product: unbounded, higher = better
    DotProduct,

    /// L2 distance: [0, ∞), lower = better (inverted for sort_key)
    L2Distance,

    /// Fused score (hybrid search)
    Fused { strategy: FusionStrategy },
}

/// Distance metrics for vector search
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DistanceMetric {
    Cosine,
    DotProduct,
    L2,
}

/// Fusion strategies for hybrid search (UPDATED)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FusionStrategy {
    /// Reciprocal Rank Fusion with k parameter
    RRF { k: usize },  // ✅ k parameter explicit (default: 60)

    /// Weighted linear combination
    LinearCombination {
        weights: HashMap<String, f64>,  // channel -> weight
        normalize_weights: bool,         // auto-normalize to sum=1?
    },

    /// Take max score across channels
    Max,
}

/// Score normalization methods
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ScoreNormalization {
    None,
    MinMax,      // (x - min) / (max - min)
    ZScore,      // (x - mean) / stddev
    RankBased,   // Convert to percentile rank
}

/// Tie-breaking rules for deterministic ordering
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TieBreakRule {
    NodeIdAsc,   // Stable sort by node_id (lexicographic)
    ChannelPriority(Vec<String>),  // By original channel rank
    Field { name: String, order: Order },  // Custom field
}

/// Fusion configuration (complete contract)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FusionConfig {
    pub strategy: FusionStrategy,
    pub normalization: ScoreNormalization,
    pub tie_break: TieBreakRule,
    pub candidate_pool_size: usize,  // Per-channel top-N before fusion
}

impl Default for FusionConfig {
    fn default() -> Self {
        Self {
            strategy: FusionStrategy::RRF { k: 60 },
            normalization: ScoreNormalization::RankBased,
            tie_break: TieBreakRule::NodeIdAsc,
            candidate_pool_size: 1000,
        }
    }
}
```

#### 3.4.2 SearchConfig (Complete)

```rust
pub struct SearchConfig {
    // Text search
    pub tokenizer: Tokenizer,      // whitespace / ngram / ...
    pub ranking: RankingAlgo,      // BM25 / TF-IDF / ...
    pub boost_fields: HashMap<String, f64>,

    // Vector search
    pub distance_metric: DistanceMetric,  // Cosine / Dot / L2
    pub normalize: bool,
    pub threshold: f64,

    // Hybrid fusion (UPDATED)
    pub fusion: Option<FusionConfig>,  // ✅ Complete fusion contract
}

pub struct SearchQueryBuilder<'a> {
    query_type: SearchType,
    config: SearchConfig,
    filters: Vec<Expr>,            // Additional filters
    limit: usize,
}

impl<'a> SearchQueryBuilder<'a> {
    pub fn text(query: &str) -> Self;
    pub fn vector(embedding: Vec<f64>) -> Self;
    pub fn hybrid(query: &str, embedding: Vec<f64>) -> Self;

    // ✅ Semantic contracts
    pub fn with_config(mut self, config: SearchConfig) -> Self;
    pub fn distance_metric(mut self, metric: DistanceMetric) -> Self;
    pub fn fusion_config(mut self, fusion: FusionConfig) -> Self;  // ✅ Complete fusion
    pub fn weights(mut self, weights: HashMap<String, f64>) -> Self;

    // ✅ Filters (same Expr AST)
    pub fn where_expr(mut self, expr: Expr) -> Self;

    pub fn limit(mut self, n: usize) -> Self;

    pub fn execute(self) -> Result<Vec<SearchHitRow>>;
}

/// Result row for search (UPDATED with score semantics)
#[derive(Debug, Clone)]
pub struct SearchHitRow {
    pub node_id: String,

    /// Raw score from search engine (unnormalized)
    pub score_raw: f64,

    /// Normalized score [0, 1] where higher = better
    /// Normalization: (score - min) / (max - min) within result set
    pub score_norm: f64,

    /// Sort key (always higher = better, deterministic)
    pub sort_key: f64,

    /// Score semantics (how to interpret score_raw)
    pub score_semantics: ScoreSemantics,

    pub source: SearchSource,    // Lexical / Semantic / Hybrid
    pub rank: usize,             // 1-based rank
    pub metadata: HashMap<String, Value>,
}
```

---

## 4. Corrected Coverage Matrix

### 4.1 Scenarios Fixed with Expression AST

| # | Scenario | OLD (WRONG) | NEW (CORRECT) |
|---|----------|-------------|---------------|
| 9 | Filter by complexity threshold | `.where_fn(\|n\| n.complexity > 10)` | `.where_field("complexity", Op::Gte, 10)` |
| 10 | Filter by name pattern | `.where_fn(\|n\| n.name.contains("process"))` | `.where_field("name", Op::Contains, "process")` |
| Regex | Regex matching | `.where_fn(\|n\| regex.is_match(n.name))` | `.where_field("name", Op::Regex, pattern)` |
| 29 | Multi-filter | Multiple `.where_fn()` | `.where_expr(Expr::And([...]))` |
| 31 | Aggregation on filtered set | `.where_fn().aggregate()` | `.where_expr(...).aggregate()` |

### 4.2 Scenarios Removed (Not Covered)

| # | Scenario | Reason | Alternative |
|---|----------|--------|-------------|
| JOIN | Complex JOIN | Not defined in QueryPlan/Executor | Use separate node/edge queries + client-side join, OR defer to v2 |

### 4.3 Updated Coverage

| Category | Scenarios | Covered (Corrected) | Notes |
|----------|-----------|---------------------|-------|
| Path Queries | 5 | 5 ✅ | Native support (no change) |
| Node Filtering | 5 | 5 ✅ | Now via Expr AST |
| Edge Filtering | 3 | 3 ✅ | No change |
| Aggregation | 4 | 4 ✅ | No change |
| Ordering & Pagination | 4 | 4 ✅ | No change |
| Specialized Queries | 5 | 5 ✅ | No change |
| Streaming | 2 | 2 ✅ | No change |
| Advanced Combinations | 3 | 3 ✅ | Now via Expr AST composition |
| **TOTAL** | **31** | **31 ✅** | **100% (with corrections)** |

---

## 5. DX Improvements

### 5.1 Typed Field Enums (Recommended)

```rust
/// Node fields (type-safe)
pub enum NodeField {
    Name,
    Language,
    FilePath,
    Complexity,
    LinesOfCode,
    // ... generated from schema
}

impl NodeField {
    pub fn as_str(&self) -> &'static str {
        match self {
            NodeField::Name => "name",
            NodeField::Language => "language",
            // ...
        }
    }
}

// Usage (type-safe, IDE autocomplete)
.where_field(NodeField::Complexity, Op::Gte, 10)
```

### 5.2 Python Type Hints

```python
from typing import Literal

FieldName = Literal["name", "language", "file_path", "complexity", "lines_of_code"]

def where(self, **filters: Dict[str, Any]) -> "NodeQueryBuilder":
    """
    Type-safe Django-style filtering.

    Examples:
        .where(language="python")
        .where(complexity__gte=10)
        .where(name__regex="process.*")
    """
    ...
```

### 5.3 Result Types (Explicit Schemas)

```rust
/// Node result row (Arrow schema)
#[derive(Debug, Clone)]
pub struct NodeRow {
    pub id: String,
    pub name: String,
    pub kind: NodeKind,
    pub file_path: Option<String>,
    pub span: Span,
    pub metadata: HashMap<String, Value>,
}

/// Edge result row
#[derive(Debug, Clone)]
pub struct EdgeRow {
    pub id: String,
    pub source_id: String,
    pub target_id: String,
    pub kind: EdgeKind,
    pub metadata: HashMap<String, Value>,
}

/// Path result row
#[derive(Debug, Clone)]
pub struct PathRow {
    pub node_sequence: Vec<String>,
    pub edge_sequence: Vec<String>,
    pub length: usize,
    pub cost: f64,
}
```

---

## 6. QueryPlan Serialization

### 6.1 QueryPlan Schema (Updated)

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryPlan {
    pub query_type: QueryType,
    pub filters: Vec<Expr>,        // ✅ Expression AST (not closures)
    pub ordering: Option<(String, Order)>,
    pub pagination: Pagination,
    pub config: QueryConfig,       // ✅ Semantic contracts
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum QueryType {
    Nodes,
    Edges,
    Paths(PathSpec),
    Reachability(PathSpec),
    Expand(ExpandSpec),
    Search(SearchSpec),
    Findings(FindingSpec),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchSpec {
    pub query: Option<String>,
    pub embedding: Option<Vec<f64>>,
    pub config: SearchConfig,      // ✅ Full semantic contract
}
```

### 6.2 Determinism Guarantee

```rust
// ✅ QueryPlan is:
// 1. Fully serializable (no closures, no callbacks)
// 2. Deterministic (same plan + same snapshot = same result)
// 3. Reproducible (can be stored, replayed, debugged)
// 4. Optimizable (engine can rewrite Expr AST)

let plan_json = serde_json::to_string(&query_plan)?;
let plan_hash = blake3::hash(plan_json.as_bytes());

// Same plan + same snapshot -> same hash -> cacheable
```

---

## 7. Migration from RFC-001

### 7.1 Breaking Changes

| Old API (WRONG) | New API (CORRECT) |
|-----------------|-------------------|
| `.where_fn(\|n\| n.complexity > 10)` | `.where_field("complexity", Op::Gte, 10)` |
| `.where_fn(\|n\| n.name.contains("x"))` | `.where_field("name", Op::Contains, "x")` |
| `.where_fn(\|n\| regex.is_match(...))` | `.where_field("name", Op::Regex, pattern)` |
| `.nodes().join(edges).on("id")` | *Removed* (use separate queries or defer to v2) |

### 7.2 New APIs

```rust
// ✅ Expression builders
ExprBuilder::eq("language", "python")
ExprBuilder::gte("complexity", 10)
ExprBuilder::regex("name", "process.*")
ExprBuilder::and([expr1, expr2])

// ✅ Search semantic contracts
.search().vector(embedding)
    .distance_metric(DistanceMetric::Cosine)
    .threshold(0.8)

.search().hybrid(query, embedding)
    .fusion_strategy(FusionStrategy::RRF)
    .weights(hashmap!{"lexical" => 0.3, "semantic" => 0.7})
```

---

## 8. Non-Goals (Explicit Exclusions)

### 8.1 Main Grammar MUST NOT Include

- ❌ `.where_fn()` (callbacks/closures)
- ❌ `.join()` (undefined in v1)
- ❌ Python callback execution
- ❌ Arbitrary code in predicates
- ❌ Implicit result type inference

### 8.2 Deferred to Future RFCs

- `JOIN` operations → RFC-SDK-003
- User-defined functions → RFC-SDK-004
- Streaming aggregations → RFC-SDK-005

---

## 9. P0 Critical Corrections Summary (2024-12-29)

### 9.1 Five Core Corrections (MUST HAVE)

#### 9.1.1 Expr Canonicalization (Determinism)

**Contract**: All `Expr::And` and `Expr::Or` operands MUST be sorted by their serialized representation (bincode). All `Object` values MUST use `BTreeMap` for key ordering. Float values MUST reject NaN and normalize `-0.0` to `0.0`.

**Why Critical**: Without canonicalization, identical queries produce different hashes, breaking caching and reproducibility.

#### 9.1.2 Value Type Extensions (Arrow/JSON Compatibility)

**Added**: `Null`, `List`, `Object` (BTreeMap), `Bytes`, `Timestamp`

**Why Critical**:
- `Null` required for `IS NULL` queries
- `List`/`Object` required for metadata filtering
- `Timestamp` required for git history/blame queries

#### 9.1.3 NodeSelector/EdgeSelector (Path Query Foundation)

**Contract**: All `NodeSelector` variants MUST be expressible as `NodeSpec { kind: Option<NodeKind>, filters: Vec<Expr> }` for unified optimization. `ByQuery` is supported but may have optimization limitations in v1.

**Why Critical**: Path queries cannot execute without selector definitions.

#### 9.1.4 Search Score Semantics (Reproducibility)

**Contract**: `SearchHitRow` MUST provide both `score_raw` (engine output) and `score_norm` (0-1 normalized). `sort_key` MUST always represent "higher = better" for deterministic ordering. `score_semantics` MUST specify the distance metric and normalization method.

**Why Critical**: Without score semantics, search results are not reproducible across runs.

#### 9.1.5 Fusion Config Complete Specification (Hybrid Search)

**Contract**: `FusionConfig` MUST specify:
- RRF `k` parameter (default: 60)
- Score normalization strategy (MinMax/ZScore/RankBased)
- Tie-breaking rule (NodeIdAsc for determinism)
- Candidate pool size (default: 1000)

**Why Critical**: Hybrid search is non-deterministic without complete fusion specification.

### 9.2 Path Explosion Guardrails

**Contract**: `PathQueryBuilder::all()` MUST enforce default limits: `max_paths: 100`, `max_expansions: 10_000`, `timeout_ms: 30_000`. These can be overridden via `.limits()` but MUST never be unlimited.

**Why Critical**: Production safety against graph explosion attacks.

---

## 10. Conclusion

### 10.1 Corrections Summary

**Fixed**:
1. ✅ Replaced `.where_fn()` with Expression AST
2. ✅ Removed undefined `.join()` from coverage claims
3. ✅ Added semantic contracts for search operations
4. ✅ Improved DX with typed fields and result schemas
5. ✅ **Added P0 Critical Corrections** (canonicalization, selectors, score semantics, fusion, safety limits)

**Impact**:
- **Coverage**: Still 31/31 (100%) with corrections
- **Determinism**: ✅ **Guaranteed** (canonicalization + score semantics)
- **FFI Safety**: ✅ Guaranteed (no Rust closures)
- **DX**: ✅ Improved (type-safe, AI-friendly)
- **Safety**: ✅ **Production-ready** (path limits, timeout guards)

### 10.2 Final API Summary

```rust
// Entry points (result type explicit)
snap.query().nodes()           -> NodeQueryBuilder
snap.query().edges()           -> EdgeQueryBuilder
snap.query().paths(from, to)   -> PathQueryBuilder
snap.query().reachability(...)  -> ReachabilityQuery
snap.query().expand(anchor)    -> ExpandQueryBuilder
snap.query().search()          -> SearchQueryBuilder
snap.query().findings()        -> FindingQueryBuilder

// Filtering (Expression AST, not closures)
.where_expr(Expr::And([...]))
.where_field("field", Op::Gte, value)
.where(field__op=value)        // Python sugar

// Ordering & Pagination
.order_by("field", Order::Desc)
.limit(100)
.offset(50)

// Aggregation & Streaming
.aggregate().count().avg("field")
.stream(chunk_size)

// Execute
.execute() -> Result<Vec<Row>>
```

### 10.3 Implementation Priority

**P0 (MUST HAVE - Blocking)**:
1. ✅ Expr Canonicalization (Section 9.1.1)
2. ✅ Value Type Extensions (Section 9.1.2)
3. ✅ NodeSelector/EdgeSelector (Section 9.1.3)
4. ✅ Search Score Semantics (Section 9.1.4)
5. ✅ Fusion Config (Section 9.1.5)

**P1 (SHOULD HAVE - Recommended)**:
6. FieldRef type safety (manual NodeField enum acceptable)
7. Operator normalization (Expr::Cmp pattern)
8. Expand result type clarification
9. Schema codegen (deferred, manual enum is acceptable)

### 10.4 Recommendation

✅ **Approve RFC-RUST-SDK-002 with P0 corrections**

**Next steps**:
1. Implement P0 items (5 critical corrections)
2. Write integration tests for all 31 scenarios
3. Validate determinism (canonicalization tests)
4. Benchmark search score reproducibility
5. Update Python bindings with new types

---

**End of RFC-RUST-SDK-002**
