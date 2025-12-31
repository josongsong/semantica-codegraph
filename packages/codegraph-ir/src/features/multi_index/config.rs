// Configuration constants for Multi-Layer Indexing (RFC-072)
//
// All magic numbers are centralized here for easy tuning

/// # Non-Negotiable Contract 3-3: MAX_IMPACT_DEPTH
///
/// P1-8: Dependency propagation depth limit (IMMUTABLE)
/// This value is part of the RFC-072 spec and should NOT be changed
/// without updating the RFC.
pub const MAX_IMPACT_DEPTH: u8 = 2;

/// WAL Configuration
pub mod wal {
    /// Maximum in-memory WAL entries before compaction
    /// Default: 10,000 entries
    pub const DEFAULT_MAX_ENTRIES: usize = 10_000;

    /// Compaction retention ratio (keep 50% of entries)
    /// Value is percentage * 100 (50 = 50%)
    pub const COMPACTION_RETENTION_PERCENT: i32 = 50;
}

/// Change Analysis Thresholds
pub mod analysis {
    /// Impact ratio threshold for full rebuild (50%)
    /// If more than 50% of nodes are affected, trigger full rebuild
    pub const FULL_REBUILD_THRESHOLD: f64 = 0.5;

    /// Async update threshold (10 targets)
    /// If more than 10 functions need re-embedding, use background task
    pub const ASYNC_UPDATE_THRESHOLD: usize = 10;

    /// Edge density threshold for dense graph detection
    /// If avg edges per node > 100, consider graph dense
    pub const DENSE_GRAPH_THRESHOLD: u64 = 100;

    /// Edge cost scale factor for dense graphs
    pub const DENSE_GRAPH_COST_SCALE: u64 = 10;
}

/// Escape Hatch Configuration (SOTA Enhancement)
///
/// # Use Case
/// Critical nodes (entry points, public APIs) may need deeper propagation
/// to ensure all downstream impacts are captured.
///
/// # Example
/// - Flask/FastAPI route handlers (entry points)
/// - Public library APIs (@public decorator)
/// - Main functions (program entry)
pub mod escape_hatch {
    /// Extended depth for critical nodes (escape hatch)
    /// Default: 5 (vs normal MAX_IMPACT_DEPTH = 2)
    pub const CRITICAL_NODE_MAX_DEPTH: u8 = 5;

    /// Risk threshold for triggering escape hatch
    /// If node has high fanout (many callers), extend depth
    /// Default: 10 callers
    pub const HIGH_FANOUT_THRESHOLD: usize = 10;
}

/// Cost Estimation (in milliseconds)
pub mod cost {
    /// Cost per node for graph index update
    pub const GRAPH_UPDATE_COST_PER_NODE_MS: u64 = 1;

    /// Cost per embedding operation
    pub const EMBEDDING_COST_MS: u64 = 100;

    /// Cost per file for lexical index
    pub const LEXICAL_UPDATE_COST_PER_FILE_MS: u64 = 10;
}

/// Consistency Polling
pub mod consistency {
    /// Polling interval when waiting for index consistency (10ms)
    pub const POLL_INTERVAL_MS: u64 = 10;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_constants_are_reasonable() {
        // Ensure constants are within reasonable ranges
        assert_eq!(MAX_IMPACT_DEPTH, 2); // RFC-072 contract
        assert!(wal::DEFAULT_MAX_ENTRIES >= 1000);
        assert!(analysis::FULL_REBUILD_THRESHOLD > 0.0);
        assert!(analysis::FULL_REBUILD_THRESHOLD <= 1.0);
        assert!(cost::EMBEDDING_COST_MS > 0);
    }
}
