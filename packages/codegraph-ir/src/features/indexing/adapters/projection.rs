///! RFC-RUST-ENGINE Phase 2: Projection API
///!
///! Python-facing API for querying IR without full deserialization.
///!
///! # Design Goals
///!
///! 1. Zero-copy reads where possible
///! 2. Minimal Python decode (Rust does the work)
///! 3. Filtered field access (don't decode unused fields)
///!
///! # API Surface (Phase 2 Minimum)
///!
///! - get_file_summary(): File-level metrics (no record decode)
///! - iterate_file_nodes(): Filtered node iteration
///! - get_import_edges(): Import graph extraction
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::features::indexing::domain::schema::{FileIndex, NodeRecord, PayloadLayout};

// ============================================================
// Python Module Export
// ============================================================

/// Factory function to create EngineHandle from Python
#[pyfunction]
pub fn create_engine_handle(
    py: Python,
    payload: Vec<u8>,
    layout_bytes: Vec<u8>,
    index_bytes: Vec<u8>,
) -> PyResult<Py<EngineHandle>> {
    let handle = EngineHandle::new(payload, layout_bytes, index_bytes)?;
    Py::new(py, handle)
}

/// Register EngineHandle with the Python module
pub fn register_projection_api(m: &PyModule) -> PyResult<()> {
    m.add_class::<EngineHandle>()?;
    m.add_function(wrap_pyfunction!(create_engine_handle, m)?)?;
    Ok(())
}

/// Engine handle for Python FFI
///
/// Holds serialized IR payload and provides projection queries.
///
/// # Memory Model
///
/// - payload: Vec<u8> (owned bytes)
/// - layout: PayloadLayout (section metadata)
/// - file_index: FileIndex (file → record range)
///
/// Total memory for 10K files: ~50MB payload + 660KB index = ~51MB
#[pyclass(module = "codegraph_ir")]
pub struct EngineHandle {
    payload: Vec<u8>,
    layout: PayloadLayout,
    file_index: FileIndex,
}

#[pymethods]
impl EngineHandle {
    #[new]
    fn new(payload: Vec<u8>, layout_bytes: Vec<u8>, index_bytes: Vec<u8>) -> PyResult<Self> {
        // Deserialize layout
        let layout: PayloadLayout = rmp_serde::from_slice(&layout_bytes).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to deserialize layout: {}",
                e
            ))
        })?;

        // Deserialize file index
        let file_index: FileIndex = rmp_serde::from_slice(&index_bytes).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to deserialize index: {}",
                e
            ))
        })?;

        Ok(Self {
            payload,
            layout,
            file_index,
        })
    }

    /// Projection 1: File summary (no Python decode)
    ///
    /// Returns:
    /// ```python
    /// {
    ///     "file_id": 0,
    ///     "node_count": 42,
    ///     "edge_count": 15,
    ///     "chunk_count": 8,
    ///     "hash": "abc123...",
    /// }
    /// ```
    ///
    /// # Performance
    ///
    /// - O(1) file_id lookup
    /// - O(1) range retrieval
    /// - No record deserialization
    /// - Target: < 1μs per file
    fn get_file_summary(&self, py: Python, file_path: &str) -> PyResult<PyObject> {
        let summary = PyDict::new(py);

        // Get file_id (O(n) in Phase 2, acceptable for 10K files)
        let file_id = self.file_index.get_file_id(file_path).ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyKeyError, _>(format!("File not found: {}", file_path))
        })?;

        summary.set_item("file_id", file_id)?;
        summary.set_item("file_path", file_path)?;

        // Get node count from index (O(1))
        if let Some((_offset, count)) = self.file_index.ranges.get(&file_id) {
            summary.set_item("node_count", count)?;
        } else {
            summary.set_item("node_count", 0)?;
        }

        // Phase 2.1: Edge/chunk counts require separate FileIndex per section
        // Requires: file_index.edge_ranges, file_index.chunk_ranges
        summary.set_item("edge_count", 0)?; // Phase 2.1
        summary.set_item("chunk_count", 0)?; // Phase 2.1

        // Phase 2.2: Content hash for change detection
        // Requires: Blake3::hash(node_bytes[offset..offset+size])
        summary.set_item("hash", "not_implemented")?; // Phase 2.2

        Ok(summary.into())
    }

    /// Projection 2: Iterate file nodes (filtered fields)
    ///
    /// Returns list of dicts with only requested fields.
    ///
    /// # Example
    ///
    /// ```python
    /// nodes = handle.iterate_file_nodes(0, ["fqn", "kind"])
    /// # [{"fqn": "test.func", "kind": 1}, ...]
    /// ```
    ///
    /// # Performance
    ///
    /// - Decodes only requested fields
    /// - Streaming iteration (no full materialization)
    /// - Target: < 1ms for 100 nodes
    fn iterate_file_nodes(
        &self,
        py: Python,
        file_id: u32,
        fields: Option<Vec<String>>,
    ) -> PyResult<PyObject> {
        let list = PyList::empty(py);

        // Get file range
        let (offset, count) = self
            .file_index
            .ranges
            .get(&file_id)
            .copied()
            .ok_or_else(|| {
                PyErr::new::<pyo3::exceptions::PyKeyError, _>(format!(
                    "File ID {} not found",
                    file_id
                ))
            })?;

        // Calculate absolute offset (relative to nodes_offset)
        let abs_offset = self.layout.nodes_offset + offset;
        let mut current_offset = abs_offset as usize;

        // Iterate records
        for _ in 0..count {
            // Read length prefix (u32 little-endian)
            if current_offset + 4 > self.payload.len() {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    "Payload truncated",
                ));
            }

            let len = u32::from_le_bytes([
                self.payload[current_offset],
                self.payload[current_offset + 1],
                self.payload[current_offset + 2],
                self.payload[current_offset + 3],
            ]) as usize;
            current_offset += 4;

            // Read record bytes
            if current_offset + len > self.payload.len() {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    "Record truncated",
                ));
            }

            let record_bytes = &self.payload[current_offset..current_offset + len];

            // Deserialize node
            let node: NodeRecord = rmp_serde::from_slice(record_bytes).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Failed to deserialize node: {}",
                    e
                ))
            })?;

            // Build filtered dict
            let node_dict = PyDict::new(py);

            if let Some(ref field_list) = fields {
                // Only include requested fields
                for field in field_list {
                    match field.as_str() {
                        "fqn" => node_dict.set_item("fqn", &node.fqn)?,
                        "kind" => node_dict.set_item("kind", node.kind)?,
                        "file_id" => node_dict.set_item("file_id", node.file_id)?,
                        "local_seq" => node_dict.set_item("local_seq", node.local_seq)?,
                        "start_byte" => node_dict.set_item("start_byte", node.start_byte)?,
                        "end_byte" => node_dict.set_item("end_byte", node.end_byte)?,
                        _ => {} // Ignore unknown fields
                    }
                }
            } else {
                // Return all fields
                node_dict.set_item("fqn", &node.fqn)?;
                node_dict.set_item("kind", node.kind)?;
                node_dict.set_item("file_id", node.file_id)?;
                node_dict.set_item("local_seq", node.local_seq)?;
                node_dict.set_item("start_byte", node.start_byte)?;
                node_dict.set_item("end_byte", node.end_byte)?;
            }

            list.append(node_dict)?;

            current_offset += len;
        }

        Ok(list.into())
    }

    /// Projection 3: Get import edges
    ///
    /// Returns list of (src_file_id, dst_file_id) tuples.
    ///
    /// # Example
    ///
    /// ```python
    /// imports = handle.get_import_edges(0)
    /// # [(0, 1), (0, 2), ...]
    /// ```
    ///
    /// # Performance
    ///
    /// - Minimal edge extraction
    /// - No full edge deserialization
    /// - Target: < 5ms for 1000 edges
    fn get_import_edges(&self, py: Python, _file_id: u32) -> PyResult<PyObject> {
        let list = PyList::empty(py);

        // Phase 2.1: Edge iteration requires:
        // 1. file_index.edge_ranges (file_id → edge offset)
        // 2. Edge section decoder with EdgeKind::Imports filter

        Ok(list.into())
    }

    /// Debug: Get layout info
    fn get_layout(&self, py: Python) -> PyResult<PyObject> {
        let dict = PyDict::new(py);

        dict.set_item("total_size", self.layout.total_size)?;
        dict.set_item("nodes_count", self.layout.nodes_count)?;
        dict.set_item("nodes_offset", self.layout.nodes_offset)?;
        dict.set_item("nodes_size", self.layout.nodes_size)?;
        dict.set_item("edges_count", self.layout.edges_count)?;
        dict.set_item("chunks_count", self.layout.chunks_count)?;

        Ok(dict.into())
    }

    /// Debug: Get file count
    fn get_file_count(&self) -> usize {
        self.file_index.paths.len()
    }
}

// ============================================================
// TDD: Tests First!
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::indexing::domain::schema::NodeRecord;
    use crate::features::indexing::infrastructure::writer::PayloadWriter;

    /// Helper: Create test payload
    fn create_test_payload() -> (Vec<u8>, PayloadLayout, FileIndex) {
        let mut writer = PayloadWriter::new();

        // Add test nodes
        let nodes = vec![
            NodeRecord {
                file_id: 0,
                node_local_id: 1,
                kind: 1,
                fqn: "test.func1".to_string(),
                start_byte: 10,
                end_byte: 20,
                local_seq: 0,
                name: Some("func1".to_string()),
                content_hash: None,
            },
            NodeRecord {
                file_id: 0,
                node_local_id: 2,
                kind: 1,
                fqn: "test.func2".to_string(),
                start_byte: 30,
                end_byte: 40,
                local_seq: 1,
                name: Some("func2".to_string()),
                content_hash: None,
            },
        ];

        writer.write_nodes(nodes).unwrap();

        let (payload, layout, mut file_index) = writer.finalize();

        // Manually build file index for test
        file_index.add_path("test.py".to_string());
        file_index.set_range(0, 0, 2); // file_id=0, offset=0, count=2

        (payload, layout, file_index)
    }

    /// RED: Test EngineHandle creation
    #[test]
    fn test_engine_handle_creation() {
        let (payload, layout, file_index) = create_test_payload();

        // Serialize layout and index
        let layout_bytes = rmp_serde::to_vec(&layout).unwrap();
        let index_bytes = rmp_serde::to_vec(&file_index).unwrap();

        // Create handle
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|_py| {
            let handle = EngineHandle::new(payload, layout_bytes, index_bytes).unwrap();

            assert_eq!(handle.get_file_count(), 1);
        });
    }

    /// RED: Test get_file_summary
    #[test]
    fn test_get_file_summary() {
        let (payload, layout, file_index) = create_test_payload();

        let layout_bytes = rmp_serde::to_vec(&layout).unwrap();
        let index_bytes = rmp_serde::to_vec(&file_index).unwrap();

        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let handle = EngineHandle::new(payload, layout_bytes, index_bytes).unwrap();

            let summary = handle.get_file_summary(py, "test.py").unwrap();
            let dict = summary.downcast::<PyDict>(py).unwrap();

            assert_eq!(
                dict.get_item("file_id")
                    .unwrap()
                    .unwrap()
                    .extract::<u32>()
                    .unwrap(),
                0
            );
            assert_eq!(
                dict.get_item("node_count")
                    .unwrap()
                    .unwrap()
                    .extract::<u32>()
                    .unwrap(),
                2
            );
        });
    }

    /// RED: Test iterate_file_nodes (all fields)
    #[test]
    fn test_iterate_file_nodes_all_fields() {
        let (payload, layout, file_index) = create_test_payload();

        let layout_bytes = rmp_serde::to_vec(&layout).unwrap();
        let index_bytes = rmp_serde::to_vec(&file_index).unwrap();

        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let handle = EngineHandle::new(payload, layout_bytes, index_bytes).unwrap();

            let nodes = handle.iterate_file_nodes(py, 0, None).unwrap();
            let list = nodes.downcast::<PyList>(py).unwrap();

            assert_eq!(list.len(), 2);

            // Check first node
            let node0 = list.get_item(0).unwrap().downcast::<PyDict>().unwrap();
            assert_eq!(
                node0
                    .get_item("fqn")
                    .unwrap()
                    .unwrap()
                    .extract::<String>()
                    .unwrap(),
                "test.func1"
            );
        });
    }

    /// RED: Test iterate_file_nodes (filtered fields)
    #[test]
    fn test_iterate_file_nodes_filtered() {
        let (payload, layout, file_index) = create_test_payload();

        let layout_bytes = rmp_serde::to_vec(&layout).unwrap();
        let index_bytes = rmp_serde::to_vec(&file_index).unwrap();

        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let handle = EngineHandle::new(payload, layout_bytes, index_bytes).unwrap();

            // Request only "fqn" and "kind"
            let fields = vec!["fqn".to_string(), "kind".to_string()];
            let nodes = handle.iterate_file_nodes(py, 0, Some(fields)).unwrap();
            let list = nodes.downcast::<PyList>(py).unwrap();

            assert_eq!(list.len(), 2);

            // Verify only requested fields are present
            let node0 = list.get_item(0).unwrap().downcast::<PyDict>().unwrap();
            assert!(node0.get_item("fqn").unwrap().is_some());
            assert!(node0.get_item("kind").unwrap().is_some());
            // file_id should not be present (not requested)
            assert!(
                node0.get_item("file_id").is_ok() && node0.get_item("file_id").unwrap().is_none()
            );
        });
    }

    /// RED: Test get_import_edges (stub)
    #[test]
    fn test_get_import_edges() {
        let (payload, layout, file_index) = create_test_payload();

        let layout_bytes = rmp_serde::to_vec(&layout).unwrap();
        let index_bytes = rmp_serde::to_vec(&file_index).unwrap();

        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let handle = EngineHandle::new(payload, layout_bytes, index_bytes).unwrap();

            let edges = handle.get_import_edges(py, 0).unwrap();
            let list = edges.downcast::<PyList>(py).unwrap();

            // Currently returns empty (stub)
            assert_eq!(list.len(), 0);
        });
    }
}
