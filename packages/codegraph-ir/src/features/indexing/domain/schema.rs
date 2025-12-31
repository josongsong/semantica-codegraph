//! RFC-RUST-ENGINE Phase 2: Schema Definitions
//!
//! Wire format schema for deterministic IR serialization.
//!
//! # Contracts (Phase 1 Lock-in)
//!
//! ## 1. FFI Wire Format
//! - Outer: msgpack metadata
//! - Payload: Section-based record stream
//! - Framing: [u32_le length][record_bytes]
//!
//! ## 2. Ordering Contract
//! - Nodes: (file_path, kind, start_line, end_line, local_seq)
//! - Edges: (source_id, target_id, kind, local_seq)
//! - Total order: local_seq prevents ties
//!
//! ## 3. Memory Budget
//! - FileIndex: ~660KB for 10K files
//! - PayloadLayout: 64 bytes
//! - Record overhead: 4 bytes per record (u32 length prefix)

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ============================================================
// Payload Layout
// ============================================================

/// Payload structure metadata
///
/// Fixed layout:
/// ```text
/// [Header] [Node Section] [Edge Section] [Chunk Section]
/// ```
///
/// Each section:
/// ```text
/// [SectionHeader: 12 bytes] [Record...] [Record...]
/// ```
///
/// Record format:
/// ```text
/// [u32_le length: 4 bytes] [msgpack record_bytes]
/// ```
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct PayloadLayout {
    /// Total payload size in bytes
    pub total_size: u64,

    /// Header section
    pub header_offset: u64,
    pub header_size: u64,

    /// Node section
    pub nodes_offset: u64,
    pub nodes_count: u32,
    pub nodes_size: u64,

    /// Edge section
    pub edges_offset: u64,
    pub edges_count: u32,
    pub edges_size: u64,

    /// Chunk section
    pub chunks_offset: u64,
    pub chunks_count: u32,
    pub chunks_size: u64,
}

impl PayloadLayout {
    pub fn new() -> Self {
        Self {
            total_size: 0,
            header_offset: 0,
            header_size: 0,
            nodes_offset: 0,
            nodes_count: 0,
            nodes_size: 0,
            edges_offset: 0,
            edges_count: 0,
            edges_size: 0,
            chunks_offset: 0,
            chunks_count: 0,
            chunks_size: 0,
        }
    }
}

impl Default for PayloadLayout {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================
// File Index
// ============================================================

/// File-level range index (RFC Section 3.2.2)
///
/// Memory budget (10K files):
/// - ranges: 16 bytes × 10K = 160KB
/// - paths: ~50 bytes avg × 10K = 500KB
/// - Total: ~660KB (acceptable)
///
/// Design:
/// - file_id = index into paths vector
/// - ranges: file_id → (section_offset, record_count)
/// - O(n) get_file_id (acceptable for Phase 1)
/// - O(1) get_file_range (HashMap)
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FileIndex {
    /// file_id → (relative_offset, record_count)
    ///
    /// Offset is relative to section start (nodes_offset, edges_offset, etc.)
    /// Records are consecutive (pre-sorted by file_id)
    pub ranges: HashMap<u32, (u64, u32)>,

    /// file_id = index into this vector
    ///
    /// No separate path_to_id HashMap needed (memory optimization)
    pub paths: Vec<String>,
}

impl FileIndex {
    pub fn new() -> Self {
        Self {
            ranges: HashMap::new(),
            paths: Vec::new(),
        }
    }

    /// Get file_id by path (O(n) linear search)
    ///
    /// Acceptable for Phase 1 (10K files ~10μs)
    /// Phase 3+: Use HashMap<String, u32> for O(1)
    pub fn get_file_id(&self, file_path: &str) -> Option<u32> {
        self.paths
            .iter()
            .position(|p| p == file_path)
            .map(|idx| idx as u32)
    }

    /// Get records range for file (O(1) HashMap lookup)
    pub fn get_file_range(&self, file_path: &str) -> Option<(u64, u32)> {
        let file_id = self.get_file_id(file_path)?;
        self.ranges.get(&file_id).copied()
    }

    /// Get file path by ID (O(1) vector index)
    pub fn get_path(&self, file_id: u32) -> Option<&str> {
        self.paths.get(file_id as usize).map(|s| s.as_str())
    }

    /// Add file path and return assigned file_id
    pub fn add_path(&mut self, file_path: String) -> u32 {
        let file_id = self.paths.len() as u32;
        self.paths.push(file_path);
        file_id
    }

    /// Set range for file_id
    pub fn set_range(&mut self, file_id: u32, offset: u64, count: u32) {
        self.ranges.insert(file_id, (offset, count));
    }
}

impl Default for FileIndex {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================
// Node Record (Compact)
// ============================================================

/// Node record (compact wire format)
///
/// Ordering key: (file_id, kind, start_byte, end_byte, local_seq)
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct NodeRecord {
    /// File ID (u32 instead of String for compactness)
    pub file_id: u32,

    /// Node local ID within file
    pub node_local_id: u32,

    /// Node kind (enum ordinal)
    pub kind: u8,

    /// Fully qualified name
    pub fqn: String,

    /// Span (start_byte, end_byte for ordering)
    pub start_byte: u32,
    pub end_byte: u32,

    /// Ordering tie-breaker (RFC Phase 1)
    pub local_seq: u32,

    /// Optional fields (compact representation)
    pub name: Option<String>,
    pub content_hash: Option<String>,
}

// ============================================================
// Edge Record (Compact)
// ============================================================

/// Edge record (compact wire format)
///
/// Ordering key: (src_ref, dst_ref, kind, local_seq)
///
/// CRITICAL: src_ref/dst_ref are u64 (not String!)
/// - Faster comparison (O(1) vs O(n))
/// - Deterministic ordering guaranteed
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct EdgeRecord {
    /// Source reference (u64 integer, not String ID!)
    pub src_ref: u64,

    /// Destination reference (u64 integer)
    pub dst_ref: u64,

    /// Edge kind (enum ordinal)
    pub kind: u8,

    /// Ordering tie-breaker (RFC Phase 1)
    pub local_seq: u32,
}

// ============================================================
// Chunk Record (Compact)
// ============================================================

/// Chunk record (compact wire format)
///
/// Ordering key: (file_id, chunk_kind, anchor_hash, local_seq)
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ChunkRecord {
    /// File ID
    pub file_id: u32,

    /// Chunk kind (enum ordinal)
    pub chunk_kind: u8,

    /// Anchor hash (for ordering)
    pub anchor_hash: String,

    /// Ordering tie-breaker (RFC Phase 1)
    pub local_seq: u32,

    /// Content fields
    pub fqn: String,
    pub start_line: Option<u32>,
    pub end_line: Option<u32>,
    pub content_hash: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_file_index_operations() {
        let mut index = FileIndex::new();

        // Add paths
        let id0 = index.add_path("file_a.py".to_string());
        let id1 = index.add_path("file_b.py".to_string());

        assert_eq!(id0, 0);
        assert_eq!(id1, 1);

        // Set ranges
        index.set_range(id0, 0, 10);
        index.set_range(id1, 100, 20);

        // Get by path
        assert_eq!(index.get_file_id("file_a.py"), Some(0));
        assert_eq!(index.get_file_id("file_b.py"), Some(1));
        assert_eq!(index.get_file_id("missing.py"), None);

        // Get range
        assert_eq!(index.get_file_range("file_a.py"), Some((0, 10)));
        assert_eq!(index.get_file_range("file_b.py"), Some((100, 20)));

        // Get path
        assert_eq!(index.get_path(0), Some("file_a.py"));
        assert_eq!(index.get_path(1), Some("file_b.py"));
        assert_eq!(index.get_path(999), None);
    }

    #[test]
    fn test_payload_layout_default() {
        let layout = PayloadLayout::default();
        assert_eq!(layout.total_size, 0);
        assert_eq!(layout.nodes_count, 0);
    }

    #[test]
    fn test_node_record_size() {
        // Verify NodeRecord is reasonably compact
        let node = NodeRecord {
            file_id: 0,
            node_local_id: 42,
            kind: 1,
            fqn: "test.func".to_string(),
            start_byte: 100,
            end_byte: 200,
            local_seq: 5,
            name: Some("func".to_string()),
            content_hash: None,
        };

        let serialized = rmp_serde::to_vec(&node).unwrap();
        // Should be < 100 bytes for typical case
        assert!(
            serialized.len() < 100,
            "NodeRecord too large: {} bytes",
            serialized.len()
        );
    }
}
