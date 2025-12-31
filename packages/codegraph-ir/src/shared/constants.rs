//! SOTA: Centralized Configuration Constants
//!
//! All magic numbers and tunable parameters are defined here for:
//! - Easy performance tuning
//! - Clear documentation of defaults
//! - Compile-time optimization
//! - Type safety with const generics where applicable

/// Thread pool configuration
pub mod thread_pool {
    /// Percentage of available CPU cores to use for Rayon thread pool
    /// 75% = 3/4 of cores, leaving 25% for OS and other tasks
    pub const CPU_UTILIZATION_PERCENT: f64 = 0.75;

    /// Minimum number of threads (always use at least 1)
    pub const MIN_THREADS: usize = 1;

    /// Maximum threads for parallel iterators (None = unlimited)
    pub const MAX_PARALLEL_THREADS: Option<usize> = None;
}

/// Symbol index thresholds
pub mod symbol_index {
    /// Threshold for switching from sequential to parallel iteration
    /// Based on Rayon overhead benchmarks showing break-even at ~10k items
    pub const PARALLEL_THRESHOLD: usize = 10_000;

    /// Initial capacity hint for symbol maps (reduces reallocations)
    pub const INITIAL_SYMBOL_CAPACITY: usize = 1024;

    /// Initial capacity for file -> symbols mapping
    pub const INITIAL_FILE_CAPACITY: usize = 256;
}

/// Hash generation configuration
pub mod hashing {
    /// Length of truncated hash strings (SHA256 produces 64 hex chars, we use 32)
    pub const HASH_LENGTH: usize = 32;

    /// Minimum hash length to prevent collisions
    pub const MIN_HASH_LENGTH: usize = 16;
}

/// IR builder configuration
pub mod ir_builder {
    /// Initial capacity for node vectors (typical file has 100-1000 nodes)
    pub const INITIAL_NODE_CAPACITY: usize = 512;

    /// Initial capacity for edge vectors (edges = nodes * avg_edges_per_node)
    pub const INITIAL_EDGE_CAPACITY: usize = 1024;

    /// Initial capacity for scope stack (max nesting depth in typical code)
    pub const INITIAL_SCOPE_CAPACITY: usize = 16;
}

/// Chunking configuration
pub mod chunking {
    /// Minimum lines for a chunk to be useful
    pub const MIN_CHUNK_LINES: usize = 3;

    /// Maximum lines per chunk (prevents overly large chunks)
    pub const MAX_CHUNK_LINES: usize = 500;

    /// Preferred chunk size for optimal search results
    pub const PREFERRED_CHUNK_LINES: usize = 50;
}

/// Pipeline batch processing
pub mod pipeline {
    /// Default batch size for file processing (balances memory vs parallelism)
    pub const DEFAULT_BATCH_SIZE: usize = 100;

    /// Maximum files to process in parallel (prevents memory exhaustion)
    pub const MAX_PARALLEL_FILES: usize = 1000;

    /// Timeout per stage in seconds (0 = no timeout)
    pub const STAGE_TIMEOUT_SECS: u64 = 300; // 5 minutes
}

/// Cross-file resolution
pub mod cross_file {
    /// Maximum import resolution depth (prevents infinite loops)
    pub const MAX_IMPORT_DEPTH: usize = 100;

    /// Maximum module path segments (e.g., a.b.c.d.e has 5 segments)
    pub const MAX_MODULE_PATH_SEGMENTS: usize = 50;
}

/// Type resolution configuration
pub mod type_resolution {
    /// Function signature cache capacity
    /// Typical repo: ~5,000 functions, cache hit rate: ~80%
    pub const SIGNATURE_CACHE_CAPACITY: usize = 8192;

    /// Maximum type inference depth (prevents infinite recursion)
    pub const MAX_INFERENCE_DEPTH: usize = 50;

    /// Maximum union type members (prevents type explosion)
    pub const MAX_UNION_MEMBERS: usize = 100;
}

/// Performance targets (for monitoring/metrics)
pub mod performance {
    /// Target lines of code per second (SOTA goal)
    pub const TARGET_LOC_PER_SECOND: f64 = 78_000.0;

    /// Warning threshold: emit warning if below this (70% of target)
    pub const WARNING_LOC_PER_SECOND: f64 = 54_600.0;

    /// Critical threshold: log error if below this (50% of target)
    pub const CRITICAL_LOC_PER_SECOND: f64 = 39_000.0;
}

/// Memory limits
pub mod memory {
    /// Maximum IR document size in bytes (100 MB)
    pub const MAX_DOCUMENT_SIZE: usize = 100 * 1024 * 1024;

    /// Maximum total nodes in memory (prevents OOM)
    pub const MAX_TOTAL_NODES: usize = 10_000_000;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cpu_utilization() {
        let num_cpus = num_cpus::get();
        let threads = std::cmp::max(
            thread_pool::MIN_THREADS,
            (num_cpus as f64 * thread_pool::CPU_UTILIZATION_PERCENT) as usize,
        );
        assert!(threads >= 1);
        assert!(threads <= num_cpus);
    }

    #[test]
    fn test_hash_length() {
        assert!(hashing::HASH_LENGTH >= hashing::MIN_HASH_LENGTH);
        assert!(hashing::HASH_LENGTH <= 64); // SHA256 max
    }

    #[test]
    fn test_chunk_constraints() {
        assert!(chunking::MIN_CHUNK_LINES < chunking::PREFERRED_CHUNK_LINES);
        assert!(chunking::PREFERRED_CHUNK_LINES < chunking::MAX_CHUNK_LINES);
    }
}
