//! RFC-RUST-ENGINE Phase 2: PayloadWriter
//!
//! Implements framing protocol: [u32_le length][record_bytes]
//!
//! # Test-Driven Development
//!
//! This module is developed using TDD:
//! 1. Write failing tests
//! 2. Implement minimum code to pass
//! 3. Refactor
//!
//! # Performance Targets

//! - 10K records < 100ms
//! - Memory: Single-pass, streaming write
//! - Determinism: Sorted input → deterministic output

use byteorder::{LittleEndian, WriteBytesExt};
use std::io::Write;

use crate::features::indexing::domain::schema::{
    ChunkRecord, EdgeRecord, FileIndex, NodeRecord, PayloadLayout,
};

/// PayloadWriter with framing protocol
///
/// Writes IR records to a byte buffer with length-prefixed framing.
///
/// # Framing Protocol
///
/// Each record is written as:
/// ```text
/// [u32_le length: 4 bytes][msgpack record_bytes: length bytes]
/// ```
///
/// # Usage
///
/// ```rust,ignore
/// let mut writer = PayloadWriter::new();
/// writer.write_nodes(nodes)?;
/// writer.write_edges(edges)?;
/// let (payload, layout) = writer.finalize();
/// ```
pub struct PayloadWriter {
    buffer: Vec<u8>,
    layout: PayloadLayout,
    file_index: FileIndex,
}

impl PayloadWriter {
    /// Create new writer
    pub fn new() -> Self {
        Self {
            buffer: Vec::new(),
            layout: PayloadLayout::new(),
            file_index: FileIndex::new(),
        }
    }

    /// Write header section (metadata)
    ///
    /// Header contains:
    /// - Schema version
    /// - Timestamp
    /// - Record counts
    pub fn write_header(&mut self, metadata: &[u8]) -> Result<(), WriteError> {
        self.layout.header_offset = self.buffer.len() as u64;

        // Write length-prefixed metadata
        let len = metadata.len() as u32;
        self.buffer
            .write_u32::<LittleEndian>(len)
            .map_err(|e| WriteError::Io(e.to_string()))?;

        self.buffer
            .write_all(metadata)
            .map_err(|e| WriteError::Io(e.to_string()))?;

        self.layout.header_size = (self.buffer.len() as u64) - self.layout.header_offset;

        Ok(())
    }

    /// Write node section with framing
    ///
    /// Nodes MUST be pre-sorted by ordering key:
    /// (file_path, kind, start_byte, end_byte, local_seq)
    ///
    /// # Framing
    ///
    /// For each node:
    /// 1. Serialize to msgpack
    /// 2. Write u32 length prefix
    /// 3. Write msgpack bytes
    pub fn write_nodes(&mut self, nodes: Vec<NodeRecord>) -> Result<(), WriteError> {
        self.layout.nodes_offset = self.buffer.len() as u64;
        self.layout.nodes_count = nodes.len() as u32;

        for node in nodes.iter() {
            self.write_framed_record(node)?;
        }

        self.layout.nodes_size = (self.buffer.len() as u64) - self.layout.nodes_offset;

        Ok(())
    }

    /// Write edge section with framing
    ///
    /// Edges MUST be pre-sorted by ordering key:
    /// (src_ref, dst_ref, kind, local_seq)
    pub fn write_edges(&mut self, edges: Vec<EdgeRecord>) -> Result<(), WriteError> {
        self.layout.edges_offset = self.buffer.len() as u64;
        self.layout.edges_count = edges.len() as u32;

        for edge in edges.iter() {
            self.write_framed_record(edge)?;
        }

        self.layout.edges_size = (self.buffer.len() as u64) - self.layout.edges_offset;

        Ok(())
    }

    /// Write chunk section with framing
    ///
    /// Chunks MUST be pre-sorted by ordering key:
    /// (file_id, chunk_kind, anchor_hash, local_seq)
    pub fn write_chunks(&mut self, chunks: Vec<ChunkRecord>) -> Result<(), WriteError> {
        self.layout.chunks_offset = self.buffer.len() as u64;
        self.layout.chunks_count = chunks.len() as u32;

        for chunk in chunks.iter() {
            self.write_framed_record(chunk)?;
        }

        self.layout.chunks_size = (self.buffer.len() as u64) - self.layout.chunks_offset;

        Ok(())
    }

    /// Write a single record with length prefix
    ///
    /// # Framing Format
    ///
    /// ```text
    /// [u32_le length][msgpack bytes]
    /// ```
    fn write_framed_record<T: serde::Serialize>(&mut self, record: &T) -> Result<(), WriteError> {
        // Serialize to msgpack
        let record_bytes =
            rmp_serde::to_vec(record).map_err(|e| WriteError::Serialization(e.to_string()))?;

        let len = record_bytes.len() as u32;

        // Write length prefix (u32 little-endian)
        self.buffer
            .write_u32::<LittleEndian>(len)
            .map_err(|e| WriteError::Io(e.to_string()))?;

        // Write record bytes
        self.buffer
            .write_all(&record_bytes)
            .map_err(|e| WriteError::Io(e.to_string()))?;

        Ok(())
    }

    /// Finalize and return (payload, layout, file_index)
    pub fn finalize(mut self) -> (Vec<u8>, PayloadLayout, FileIndex) {
        self.layout.total_size = self.buffer.len() as u64;
        (self.buffer, self.layout, self.file_index)
    }
}

impl Default for PayloadWriter {
    fn default() -> Self {
        Self::new()
    }
}

/// Write errors
#[derive(Debug)]
pub enum WriteError {
    Io(String),
    Serialization(String),
}

impl std::fmt::Display for WriteError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            WriteError::Io(msg) => write!(f, "IO error: {}", msg),
            WriteError::Serialization(msg) => write!(f, "Serialization error: {}", msg),
        }
    }
}

impl std::error::Error for WriteError {}

// ============================================================
// TDD: Tests First!
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// RED: Test framing format
    ///
    /// Verify that records are written with correct length prefix
    #[test]
    fn test_framed_record_format() {
        let mut writer = PayloadWriter::new();

        let node = NodeRecord {
            file_id: 0,
            node_local_id: 42,
            kind: 1,
            fqn: "test".to_string(),
            start_byte: 100,
            end_byte: 200,
            local_seq: 0,
            name: None,
            content_hash: None,
        };

        writer.write_nodes(vec![node]).unwrap();

        let (payload, _layout, _index) = writer.finalize();

        // Verify framing: [u32_le length][bytes]
        assert!(payload.len() >= 4, "Payload too short");

        // Read length prefix
        let len = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);

        // Verify payload size matches: 4 (length) + len (record)
        assert_eq!(
            payload.len(),
            4 + len as usize,
            "Payload size mismatch: expected {} + {}, got {}",
            4,
            len,
            payload.len()
        );

        // Verify we can deserialize back
        let record_bytes = &payload[4..];
        let decoded: NodeRecord = rmp_serde::from_slice(record_bytes).unwrap();
        assert_eq!(decoded.fqn, "test");
    }

    /// RED: Test multiple records
    #[test]
    fn test_multiple_nodes() {
        let mut writer = PayloadWriter::new();

        let nodes = vec![
            NodeRecord {
                file_id: 0,
                node_local_id: 1,
                kind: 1,
                fqn: "func1".to_string(),
                start_byte: 10,
                end_byte: 20,
                local_seq: 0,
                name: None,
                content_hash: None,
            },
            NodeRecord {
                file_id: 0,
                node_local_id: 2,
                kind: 1,
                fqn: "func2".to_string(),
                start_byte: 30,
                end_byte: 40,
                local_seq: 1,
                name: None,
                content_hash: None,
            },
        ];

        writer.write_nodes(nodes).unwrap();

        let (payload, layout, _index) = writer.finalize();

        // Verify layout
        assert_eq!(layout.nodes_count, 2);
        assert_eq!(layout.nodes_offset, 0);
        assert_eq!(layout.nodes_size as usize, payload.len());

        // Verify we can read both records
        let mut offset = 0;
        for i in 0..2 {
            // Read length
            let len = u32::from_le_bytes([
                payload[offset],
                payload[offset + 1],
                payload[offset + 2],
                payload[offset + 3],
            ]);
            offset += 4;

            // Read record
            let record_bytes = &payload[offset..offset + len as usize];
            let node: NodeRecord = rmp_serde::from_slice(record_bytes).unwrap();
            assert_eq!(node.node_local_id, (i + 1) as u32);

            offset += len as usize;
        }
    }

    /// RED: Test edge section
    #[test]
    fn test_write_edges() {
        let mut writer = PayloadWriter::new();

        let edges = vec![EdgeRecord {
            src_ref: 1,
            dst_ref: 2,
            kind: 0,
            local_seq: 0,
        }];

        writer.write_edges(edges).unwrap();

        let (_payload, layout, _index) = writer.finalize();

        assert_eq!(layout.edges_count, 1);
        assert!(layout.edges_size > 0);
    }

    /// RED: Test section separation
    #[test]
    fn test_section_separation() {
        let mut writer = PayloadWriter::new();

        // Write header
        let header = b"metadata";
        writer.write_header(header).unwrap();

        // Write nodes
        let nodes = vec![NodeRecord {
            file_id: 0,
            node_local_id: 1,
            kind: 1,
            fqn: "test".to_string(),
            start_byte: 10,
            end_byte: 20,
            local_seq: 0,
            name: None,
            content_hash: None,
        }];
        writer.write_nodes(nodes).unwrap();

        // Write edges
        let edges = vec![EdgeRecord {
            src_ref: 1,
            dst_ref: 2,
            kind: 0,
            local_seq: 0,
        }];
        writer.write_edges(edges).unwrap();

        let (payload, layout, _index) = writer.finalize();

        // Verify sections don't overlap
        assert!(layout.header_offset == 0);
        assert!(layout.nodes_offset == layout.header_offset + layout.header_size);
        assert!(layout.edges_offset == layout.nodes_offset + layout.nodes_size);
        assert_eq!(layout.total_size as usize, payload.len());
    }

    /// RED: Test determinism
    ///
    /// Same input → same output
    #[test]
    fn test_determinism() {
        let nodes = vec![NodeRecord {
            file_id: 0,
            node_local_id: 1,
            kind: 1,
            fqn: "test".to_string(),
            start_byte: 10,
            end_byte: 20,
            local_seq: 0,
            name: None,
            content_hash: None,
        }];

        // Write twice
        let mut writer1 = PayloadWriter::new();
        writer1.write_nodes(nodes.clone()).unwrap();
        let (payload1, _, _) = writer1.finalize();

        let mut writer2 = PayloadWriter::new();
        writer2.write_nodes(nodes).unwrap();
        let (payload2, _, _) = writer2.finalize();

        // Verify determinism
        assert_eq!(payload1, payload2, "Output not deterministic");
    }

    /// RED: Test empty sections
    #[test]
    fn test_empty_sections() {
        let mut writer = PayloadWriter::new();

        writer.write_nodes(vec![]).unwrap();
        writer.write_edges(vec![]).unwrap();

        let (_payload, layout, _index) = writer.finalize();

        assert_eq!(layout.nodes_count, 0);
        assert_eq!(layout.edges_count, 0);
    }
}
