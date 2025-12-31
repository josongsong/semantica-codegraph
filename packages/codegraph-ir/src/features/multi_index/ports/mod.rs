// Ports: Index plugin trait and related types

use crate::features::query_engine::infrastructure::{Snapshot, TransactionDelta, TxnId};
use std::time::{Duration, SystemTime};

/// Trait that all index types must implement
pub trait IndexPlugin: Send + Sync {
    /// Unique identifier for this index type
    fn index_type(&self) -> IndexType;

    /// CRITICAL (P0-1): Returns the highest TxnId this index has applied
    /// Used for TxnWatermark-based consistency (not health checking)
    ///
    /// # Non-Negotiable Contract 3-1
    /// Consistency 판단은 applied_up_to() -> TxnId 기준
    /// health()는 관측용으로만 사용
    fn applied_up_to(&self) -> TxnId;

    /// Apply incremental delta update
    /// Returns: (success, actual_cost_ms)
    fn apply_delta(
        &mut self,
        delta: &TransactionDelta,
        analysis: &DeltaAnalysis,
    ) -> Result<(bool, u64), IndexError>;

    /// Full rebuild from scratch
    fn rebuild(&mut self, snapshot: &Snapshot) -> Result<u64, IndexError>;

    /// Query support
    fn supports_query(&self, query_type: &QueryType) -> bool;

    /// Health check (separate from consistency)
    fn health(&self) -> IndexHealth;

    /// Statistics
    fn stats(&self) -> IndexStats;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum IndexType {
    Graph,
    Vector,
    Lexical,
    IRDocStore,    // IR document persistence (PostgreSQL)
    ASTCache,      // AST caching layer
    TypeInference, // Type inference results
    MetricsStore,  // Code complexity/quality metrics
    Custom(u32),
}

#[derive(Debug, Clone)]
pub struct IndexHealth {
    pub is_healthy: bool,
    pub last_update: SystemTime,
    pub staleness: Duration,
    pub error: Option<String>,
}

#[derive(Debug, Clone)]
pub struct IndexStats {
    pub entry_count: usize,
    pub size_bytes: u64,
    pub last_rebuild_ms: u64,
    pub total_updates: u64,
}

/// P0-2: DeltaAnalysis with all required fields
///
/// # Complete Structure
/// All fields are required for correct operation:
/// - scope: Change classification
/// - impact_ratio: % of codebase affected
/// - affected_regions: Files/modules changed
/// - index_impacts: Per-index update strategies
/// - expanded_scope: Dependency propagation results (P0-2)
/// - hash_analysis: Hash-based bypass results (P0-2)
/// - from_txn/to_txn: Transaction range (P0-2)
#[derive(Debug, Clone)]
pub struct DeltaAnalysis {
    pub scope: ChangeScope,
    pub impact_ratio: f64,
    pub affected_regions: Vec<Region>,
    pub index_impacts: std::collections::HashMap<IndexType, IndexImpact>,

    // P0-2: Added missing fields
    pub expanded_scope: ExpandedScope,
    pub hash_analysis: std::collections::HashMap<String, HashComparison>,

    // P0-2: For snapshot retrieval and consistency tracking
    pub from_txn: TxnId,
    pub to_txn: TxnId,
}

#[derive(Debug, Clone)]
pub enum ChangeScope {
    /// IR structure changed (nodes/edges added/removed)
    IR {
        added_nodes: Vec<String>,
        removed_nodes: Vec<String>,
        modified_nodes: Vec<String>,
        added_edges: Vec<String>,
        removed_edges: Vec<String>,
    },

    /// Semantic meaning changed (function body, variable usage)
    Semantic {
        affected_functions: Vec<String>,
        affected_classes: Vec<String>,
        affected_files: Vec<String>,
    },

    /// Syntax changed (formatting, comments, docstrings)
    Syntax {
        affected_files: Vec<String>,
        is_pure_formatting: bool,
    },

    /// Metadata changed (imports, annotations, types)
    Metadata { affected_symbols: Vec<String> },
}

#[derive(Debug, Clone)]
pub struct Region {
    pub file_path: String,
    pub module_path: Option<String>,
    pub node_ids: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct IndexImpact {
    pub requires_update: bool,
    pub estimated_cost_ms: u64,
    pub strategy: UpdateStrategy,
}

/// P0-3: UpdateStrategy with Sync/Async separation
///
/// # Non-Negotiable Contract 3-6
/// - SyncIncremental = commit latency에 포함 (blocks)
/// - AsyncIncremental / FullRebuild = background (non-blocking)
/// - Lazy = query-time gate
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UpdateStrategy {
    Skip,             // No update needed
    SyncIncremental,  // O(D) incremental update (blocks commit)
    AsyncIncremental, // O(D) incremental update (background task)
    FullRebuild,      // O(N) full rebuild (always async)
    Lazy,             // Defer until query
}

/// P0-2: Expanded scope from dependency propagation
///
/// # Non-Negotiable Contract 3-3
/// Signature 변경만 BFS 전파
/// MAX_IMPACT_DEPTH = 2 고정
#[derive(Debug, Clone)]
pub struct ExpandedScope {
    /// Directly modified nodes
    pub primary_targets: Vec<String>,

    /// Propagated via dependencies (signature changes only)
    pub secondary_targets: Vec<String>,
}

/// P0-2: Hash comparison results for bypass logic (CORRECTED: 4-Level Hash)
///
/// # Non-Negotiable Contract 3-2 (REVISED)
/// Embed unit = Function signature + body semantics + docstring
/// 4-level hierarchy: signature → body → doc → format
/// Flags are MUTUALLY EXCLUSIVE (only one can be true)
#[derive(Debug, Clone)]
pub struct HashComparison {
    /// Level 1: API surface changed (name, params, return type)
    /// RENAMED from logic_changed for clarity
    pub signature_changed: bool,

    /// Level 2: Body semantics changed (AST/control-flow/data-flow)
    /// NEW: Body changes DO trigger re-embedding (B안 채택)
    pub body_changed: bool,

    /// Level 3: Documentation changed (but NOT signature/body)
    /// Exclusive: true only if !signature_changed && !body_changed
    pub doc_changed: bool,

    /// Level 4: Formatting only (whitespace, comments)
    /// Exclusive: true only if !signature && !body && !doc
    pub format_changed: bool,
}

impl HashComparison {
    /// INVARIANT: Exactly ONE flag must be true (mutual exclusivity)
    pub fn validate(&self) -> Result<(), String> {
        let flags = [
            self.signature_changed,
            self.body_changed,
            self.doc_changed,
            self.format_changed,
        ];
        let count = flags.iter().filter(|&&f| f).count();

        if count != 1 {
            Err(format!(
                "HashComparison invariant violated: {} flags are true, expected exactly 1",
                count
            ))
        } else {
            Ok(())
        }
    }

    /// Check if re-embedding is required
    /// TRUE if signature OR body changed
    pub fn requires_reembedding(&self) -> bool {
        self.signature_changed || self.body_changed
    }
}

#[derive(Debug, Clone)]
pub enum QueryType {
    SemanticSearch,
    SimilarCode,
    TextSearch,
    IdentifierLookup,
    Reachability,
    IRDocLookup,
    FQNSearch,
    ASTLookup,
    MetricsLookup,
    ComplexityAnalysis,
    HybridSearch,
}

#[derive(Debug, Clone)]
pub enum IndexError {
    NotFound(String),
    AlreadyExists(String),
    InvalidInput(String),
    InternalError(String),
    TimeoutError(String),
    ResourceError(String),
}

impl std::fmt::Display for IndexError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            IndexError::NotFound(msg) => write!(f, "Not found: {}", msg),
            IndexError::AlreadyExists(msg) => write!(f, "Already exists: {}", msg),
            IndexError::InvalidInput(msg) => write!(f, "Invalid input: {}", msg),
            IndexError::InternalError(msg) => write!(f, "Internal error: {}", msg),
            IndexError::TimeoutError(msg) => write!(f, "Timeout: {}", msg),
            IndexError::ResourceError(msg) => write!(f, "Resource error: {}", msg),
        }
    }
}

impl std::error::Error for IndexError {}
