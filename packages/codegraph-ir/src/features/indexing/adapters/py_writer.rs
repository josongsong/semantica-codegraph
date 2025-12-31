///! RFC-RUST-ENGINE Phase 2.2: PyPayloadWriter
///!
///! SOTA Solution: Export PayloadWriter to Python
///!
///! This module eliminates the msgpack compatibility issue by exposing
///! the Rust PayloadWriter directly to Python via PyO3.
///!
///! # Problem (Before)
///!
///! Python msgpack → Rust rmp_serde had compatibility issues:
///! - Field ordering mismatches
///! - Type coercion failures (Python int → Rust u32/u64)
///! - Result: edge_count=0, edge iteration fails
///!
///! # Solution (After)
///!
///! Python calls Rust PayloadWriter directly:
///! ```python
///! writer = codegraph_ir.PayloadWriter()
///! writer.add_node(node_dict)
///! writer.add_edge(edge_dict)
///! payload, layout_bytes, index_bytes = writer.finalize()
///! ```
///!
///! Result: 100% compatible serialization, all counts correct.
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};

use crate::features::indexing::domain::schema::{ChunkRecord, EdgeRecord, FileIndex, NodeRecord};
use crate::features::indexing::infrastructure::writer::PayloadWriter;

// ============================================================
// PyPayloadWriter - Python-accessible PayloadWriter
// ============================================================

/// Python-accessible PayloadWriter
///
/// Creates properly framed msgpack payloads from Python dicts.
/// Eliminates cross-language serialization compatibility issues.
///
/// # Example
///
/// ```python
/// import codegraph_ir
///
/// writer = codegraph_ir.PayloadWriter()
///
/// # Add a file to the index
/// file_id = writer.add_file("src/main.py")
///
/// # Add nodes
/// writer.add_node({
///     "file_id": file_id,
///     "node_local_id": 1,
///     "kind": 1,
///     "fqn": "main.hello",
///     "start_byte": 0,
///     "end_byte": 50,
///     "local_seq": 0,
///     "name": "hello",
///     "content_hash": None
/// })
///
/// # Add edges
/// writer.add_edge({
///     "src_ref": 1,
///     "dst_ref": 2,
///     "kind": 0,
///     "local_seq": 0
/// })
///
/// # Finalize and get bytes
/// payload, layout_bytes, index_bytes = writer.finalize()
/// ```
#[pyclass(name = "PayloadWriter")]
pub struct PyPayloadWriter {
    nodes: Vec<NodeRecord>,
    edges: Vec<EdgeRecord>,
    chunks: Vec<ChunkRecord>,
    file_index: FileIndex,
}

#[pymethods]
impl PyPayloadWriter {
    /// Create a new PayloadWriter
    #[new]
    pub fn new() -> Self {
        Self {
            nodes: Vec::new(),
            edges: Vec::new(),
            chunks: Vec::new(),
            file_index: FileIndex::new(),
        }
    }

    /// Add a file to the index and return its file_id
    ///
    /// # Arguments
    /// * `file_path` - The path of the file
    ///
    /// # Returns
    /// * `file_id` - The assigned file ID (u32)
    pub fn add_file(&mut self, file_path: String) -> u32 {
        self.file_index.add_path(file_path)
    }

    /// Add a node from a Python dict
    ///
    /// # Arguments
    /// * `node_dict` - Dict with keys: file_id, node_local_id, kind, fqn,
    ///                 start_byte, end_byte, local_seq, name?, content_hash?
    ///
    /// # Raises
    /// * `ValueError` - If required fields are missing or have wrong types
    pub fn add_node(&mut self, py: Python, node_dict: &PyDict) -> PyResult<()> {
        let node = parse_node_dict(py, node_dict)?;
        self.nodes.push(node);
        Ok(())
    }

    /// Add multiple nodes from a Python list of dicts
    ///
    /// More efficient than calling add_node multiple times
    pub fn add_nodes(&mut self, py: Python, nodes_list: &PyList) -> PyResult<u32> {
        let mut count = 0u32;
        for item in nodes_list.iter() {
            let node_dict = item.downcast::<PyDict>().map_err(|_| {
                PyErr::new::<pyo3::exceptions::PyTypeError, _>("Expected list of dicts for nodes")
            })?;
            let node = parse_node_dict(py, node_dict)?;
            self.nodes.push(node);
            count += 1;
        }
        Ok(count)
    }

    /// Add an edge from a Python dict
    ///
    /// # Arguments
    /// * `edge_dict` - Dict with keys: src_ref, dst_ref, kind, local_seq
    ///
    /// # Raises
    /// * `ValueError` - If required fields are missing or have wrong types
    pub fn add_edge(&mut self, py: Python, edge_dict: &PyDict) -> PyResult<()> {
        let edge = parse_edge_dict(py, edge_dict)?;
        self.edges.push(edge);
        Ok(())
    }

    /// Add multiple edges from a Python list of dicts
    pub fn add_edges(&mut self, py: Python, edges_list: &PyList) -> PyResult<u32> {
        let mut count = 0u32;
        for item in edges_list.iter() {
            let edge_dict = item.downcast::<PyDict>().map_err(|_| {
                PyErr::new::<pyo3::exceptions::PyTypeError, _>("Expected list of dicts for edges")
            })?;
            let edge = parse_edge_dict(py, edge_dict)?;
            self.edges.push(edge);
            count += 1;
        }
        Ok(count)
    }

    /// Add a chunk from a Python dict
    ///
    /// # Arguments
    /// * `chunk_dict` - Dict with keys: file_id, chunk_kind, anchor_hash,
    ///                  local_seq, fqn, start_line?, end_line?, content_hash?
    pub fn add_chunk(&mut self, py: Python, chunk_dict: &PyDict) -> PyResult<()> {
        let chunk = parse_chunk_dict(py, chunk_dict)?;
        self.chunks.push(chunk);
        Ok(())
    }

    /// Add multiple chunks from a Python list of dicts
    pub fn add_chunks(&mut self, py: Python, chunks_list: &PyList) -> PyResult<u32> {
        let mut count = 0u32;
        for item in chunks_list.iter() {
            let chunk_dict = item.downcast::<PyDict>().map_err(|_| {
                PyErr::new::<pyo3::exceptions::PyTypeError, _>("Expected list of dicts for chunks")
            })?;
            let chunk = parse_chunk_dict(py, chunk_dict)?;
            self.chunks.push(chunk);
            count += 1;
        }
        Ok(count)
    }

    /// Set the range for a file_id in the index
    ///
    /// # Arguments
    /// * `file_id` - The file ID
    /// * `offset` - Relative offset within the nodes section
    /// * `count` - Number of records for this file
    pub fn set_file_range(&mut self, file_id: u32, offset: u64, count: u32) {
        self.file_index.set_range(file_id, offset, count);
    }

    /// Sort nodes by file_id for correct range computation
    ///
    /// Call this before finalize() if nodes were added in unsorted order.
    pub fn sort_nodes_by_file(&mut self) {
        self.nodes.sort_by_key(|n| n.file_id);
    }

    /// Auto-compute file ranges from nodes
    ///
    /// IMPORTANT: Nodes must be sorted by file_id before calling this.
    /// If unsorted, call sort_nodes_by_file() first or ranges will be incorrect.
    pub fn auto_compute_file_ranges(&mut self) -> PyResult<()> {
        if self.nodes.is_empty() {
            return Ok(());
        }

        // Verify nodes are sorted by file_id
        let mut prev_file_id = self.nodes[0].file_id;
        for node in &self.nodes[1..] {
            if node.file_id < prev_file_id {
                // Auto-sort if not sorted
                self.nodes.sort_by_key(|n| n.file_id);
                break;
            }
            prev_file_id = node.file_id;
        }

        // Track current file and its range
        let mut current_file_id = self.nodes[0].file_id;
        let mut start_offset: u64 = 0;
        let mut current_offset: u64 = 0;
        let mut count: u32 = 0;

        for node in &self.nodes {
            // Calculate record size (4 bytes length prefix + msgpack bytes)
            let record_bytes = rmp_serde::to_vec(node).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Failed to serialize node: {}",
                    e
                ))
            })?;
            let record_size = 4 + record_bytes.len() as u64;

            if node.file_id != current_file_id {
                // Save previous file's range
                self.file_index
                    .set_range(current_file_id, start_offset, count);

                // Start new file
                current_file_id = node.file_id;
                start_offset = current_offset;
                count = 1;
            } else {
                count += 1;
            }

            current_offset += record_size;
        }

        // Save last file's range
        self.file_index
            .set_range(current_file_id, start_offset, count);

        Ok(())
    }

    /// Get current stats
    ///
    /// # Returns
    /// Dict with: node_count, edge_count, chunk_count, file_count
    pub fn stats(&self, py: Python) -> PyResult<PyObject> {
        let stats = PyDict::new(py);
        stats.set_item("node_count", self.nodes.len())?;
        stats.set_item("edge_count", self.edges.len())?;
        stats.set_item("chunk_count", self.chunks.len())?;
        stats.set_item("file_count", self.file_index.paths.len())?;
        Ok(stats.into())
    }

    /// Finalize and return (payload, layout_bytes, index_bytes)
    ///
    /// This method:
    /// 1. Writes all nodes, edges, chunks using Rust PayloadWriter
    /// 2. Serializes PayloadLayout and FileIndex using rmp_serde
    /// 3. Returns bytes that are 100% compatible with Rust deserialization
    ///
    /// # Returns
    /// Tuple of (payload: bytes, layout_bytes: bytes, index_bytes: bytes)
    pub fn finalize<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<(&'py PyBytes, &'py PyBytes, &'py PyBytes)> {
        // Auto-compute ranges if not set
        if self.file_index.ranges.is_empty() && !self.nodes.is_empty() {
            self.auto_compute_file_ranges()?;
        }

        // Create Rust PayloadWriter and write sections
        let mut writer = PayloadWriter::new();

        // Write nodes
        writer
            .write_nodes(std::mem::take(&mut self.nodes))
            .map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Failed to write nodes: {}",
                    e
                ))
            })?;

        // Write edges
        writer
            .write_edges(std::mem::take(&mut self.edges))
            .map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Failed to write edges: {}",
                    e
                ))
            })?;

        // Write chunks
        writer
            .write_chunks(std::mem::take(&mut self.chunks))
            .map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Failed to write chunks: {}",
                    e
                ))
            })?;

        // Finalize
        let (payload, layout, _internal_index) = writer.finalize();

        // Serialize layout using rmp_serde (guaranteed compatible)
        let layout_bytes = rmp_serde::to_vec(&layout).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to serialize layout: {}",
                e
            ))
        })?;

        // Serialize file_index using rmp_serde
        let index_bytes = rmp_serde::to_vec(&self.file_index).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to serialize index: {}",
                e
            ))
        })?;

        Ok((
            PyBytes::new(py, &payload),
            PyBytes::new(py, &layout_bytes),
            PyBytes::new(py, &index_bytes),
        ))
    }
}

// ============================================================
// Helper Functions: Parse Python dicts to Rust structs
// ============================================================

/// Helper to get a required field from PyDict
fn get_required<'a, T>(dict: &'a PyDict, field: &str) -> PyResult<T>
where
    T: pyo3::FromPyObject<'a>,
{
    dict.get_item(field)?
        .ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Missing field: {}", field))
        })?
        .extract()
}

/// Helper to get an optional field from PyDict
fn get_optional<'a, T>(dict: &'a PyDict, field: &str) -> PyResult<Option<T>>
where
    T: pyo3::FromPyObject<'a>,
{
    match dict.get_item(field)? {
        Some(value) => {
            if value.is_none() {
                Ok(None)
            } else {
                Ok(Some(value.extract()?))
            }
        }
        None => Ok(None),
    }
}

fn parse_node_dict(_py: Python, dict: &PyDict) -> PyResult<NodeRecord> {
    let file_id: u32 = get_required(dict, "file_id")?;
    let node_local_id: u32 = get_required(dict, "node_local_id")?;
    let kind: u8 = get_required(dict, "kind")?;
    let fqn: String = get_required(dict, "fqn")?;
    let start_byte: u32 = get_required(dict, "start_byte")?;
    let end_byte: u32 = get_required(dict, "end_byte")?;
    let local_seq: u32 = get_required(dict, "local_seq")?;

    // Optional fields
    let name: Option<String> = get_optional(dict, "name")?;
    let content_hash: Option<String> = get_optional(dict, "content_hash")?;

    Ok(NodeRecord {
        file_id,
        node_local_id,
        kind,
        fqn,
        start_byte,
        end_byte,
        local_seq,
        name,
        content_hash,
    })
}

fn parse_edge_dict(_py: Python, dict: &PyDict) -> PyResult<EdgeRecord> {
    let src_ref: u64 = get_required(dict, "src_ref")?;
    let dst_ref: u64 = get_required(dict, "dst_ref")?;
    let kind: u8 = get_required(dict, "kind")?;
    let local_seq: u32 = get_required(dict, "local_seq")?;

    Ok(EdgeRecord {
        src_ref,
        dst_ref,
        kind,
        local_seq,
    })
}

fn parse_chunk_dict(_py: Python, dict: &PyDict) -> PyResult<ChunkRecord> {
    let file_id: u32 = get_required(dict, "file_id")?;
    let chunk_kind: u8 = get_required(dict, "chunk_kind")?;
    let anchor_hash: String = get_required(dict, "anchor_hash")?;
    let local_seq: u32 = get_required(dict, "local_seq")?;
    let fqn: String = get_required(dict, "fqn")?;

    // Optional fields
    let start_line: Option<u32> = get_optional(dict, "start_line")?;
    let end_line: Option<u32> = get_optional(dict, "end_line")?;
    let content_hash: Option<String> = get_optional(dict, "content_hash")?;

    Ok(ChunkRecord {
        file_id,
        chunk_kind,
        anchor_hash,
        local_seq,
        fqn,
        start_line,
        end_line,
        content_hash,
    })
}

// ============================================================
// Module Registration
// ============================================================

pub fn register_py_writer(m: &PyModule) -> PyResult<()> {
    m.add_class::<PyPayloadWriter>()?;
    Ok(())
}

// ============================================================
// Tests
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_py_payload_writer_new() {
        let writer = PyPayloadWriter::new();
        assert_eq!(writer.nodes.len(), 0);
        assert_eq!(writer.edges.len(), 0);
        assert_eq!(writer.file_index.paths.len(), 0);
    }
}
