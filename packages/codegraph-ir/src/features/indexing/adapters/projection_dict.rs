///! RFC-RUST-ENGINE Phase 2: Dict-based Projection API
///!
///! Workaround for PyO3 pyclass export issues - uses dict return values instead of classes
///!
///! # API Functions
///!
///! - get_file_summary_dict(): Returns dict with file stats
///! - iterate_file_nodes_dict(): Returns list of dicts
///! - get_import_edges_dict(): Returns list of tuples
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::features::indexing::domain::schema::{FileIndex, NodeRecord, PayloadLayout};

// ============================================================
// Dict-based API (workaround for pyclass export)
// ============================================================

#[pyfunction]
pub fn get_file_summary_dict(
    py: Python,
    _payload: Vec<u8>,
    layout_bytes: Vec<u8>,
    index_bytes: Vec<u8>,
    file_path: String,
) -> PyResult<PyObject> {
    // Deserialize
    let layout: PayloadLayout = rmp_serde::from_slice(&layout_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Failed to deserialize layout: {}",
            e
        ))
    })?;

    let file_index: FileIndex = rmp_serde::from_slice(&index_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Failed to deserialize index: {}",
            e
        ))
    })?;

    let summary = PyDict::new(py);

    // Get file_id
    let file_id = file_index.get_file_id(&file_path).ok_or_else(|| {
        PyErr::new::<pyo3::exceptions::PyKeyError, _>(format!("File not found: {}", file_path))
    })?;

    summary.set_item("file_id", file_id)?;
    summary.set_item("file_path", file_path)?;

    // Get node count from index
    if let Some((_offset, count)) = file_index.ranges.get(&file_id) {
        summary.set_item("node_count", count)?;
    } else {
        summary.set_item("node_count", 0)?;
    }

    // Get edge count (from layout - all edges)
    summary.set_item("edge_count", layout.edges_count)?;

    // Get chunk count (from layout - all chunks)
    summary.set_item("chunk_count", layout.chunks_count)?;

    // Phase 2.2: Blake3 hash for incremental updates
    // Blake3::hash(&payload[layout.nodes_offset..]) → hex string
    summary.set_item("hash", "not_implemented")?; // Phase 2.2

    Ok(summary.into())
}

#[pyfunction]
pub fn iterate_file_nodes_dict(
    py: Python,
    payload: Vec<u8>,
    layout_bytes: Vec<u8>,
    index_bytes: Vec<u8>,
    file_id: u32,
    fields: Option<Vec<String>>,
) -> PyResult<PyObject> {
    // Deserialize
    let layout: PayloadLayout = rmp_serde::from_slice(&layout_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Failed to deserialize layout: {}",
            e
        ))
    })?;

    let file_index: FileIndex = rmp_serde::from_slice(&index_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Failed to deserialize index: {}",
            e
        ))
    })?;

    let list = PyList::empty(py);

    // Get file range
    let (offset, count) = file_index.ranges.get(&file_id).copied().ok_or_else(|| {
        PyErr::new::<pyo3::exceptions::PyKeyError, _>(format!("File ID {} not found", file_id))
    })?;

    // Calculate absolute offset
    let abs_offset = layout.nodes_offset + offset;
    let mut current_offset = abs_offset as usize;

    // Iterate records
    for _ in 0..count {
        // Read length prefix
        if current_offset + 4 > payload.len() {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "Payload truncated",
            ));
        }

        let len = u32::from_le_bytes([
            payload[current_offset],
            payload[current_offset + 1],
            payload[current_offset + 2],
            payload[current_offset + 3],
        ]) as usize;
        current_offset += 4;

        // Read record
        if current_offset + len > payload.len() {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "Record truncated",
            ));
        }

        let record_bytes = &payload[current_offset..current_offset + len];
        let node: NodeRecord = rmp_serde::from_slice(record_bytes).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to deserialize node: {}",
                e
            ))
        })?;

        // Build filtered dict
        let node_dict = PyDict::new(py);

        if let Some(ref field_list) = fields {
            for field in field_list {
                match field.as_str() {
                    "fqn" => node_dict.set_item("fqn", &node.fqn)?,
                    "kind" => node_dict.set_item("kind", node.kind)?,
                    "file_id" => node_dict.set_item("file_id", node.file_id)?,
                    "local_seq" => node_dict.set_item("local_seq", node.local_seq)?,
                    "start_byte" => node_dict.set_item("start_byte", node.start_byte)?,
                    "end_byte" => node_dict.set_item("end_byte", node.end_byte)?,
                    _ => {}
                }
            }
        } else {
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

#[pyfunction]
pub fn get_import_edges_dict(
    py: Python,
    payload: Vec<u8>,
    layout_bytes: Vec<u8>,
    _index_bytes: Vec<u8>,
    _file_id: u32,
) -> PyResult<PyObject> {
    use crate::features::indexing::domain::schema::EdgeRecord;

    // Deserialize layout
    let layout: PayloadLayout = rmp_serde::from_slice(&layout_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Failed to deserialize layout: {}",
            e
        ))
    })?;

    let list = PyList::empty(py);

    // Get edges section
    let abs_offset = layout.edges_offset as usize;
    let mut current_offset = abs_offset;
    let edges_end = abs_offset + layout.edges_size as usize;

    // Iterate all edges and filter by source file_id
    while current_offset < edges_end {
        // Read length prefix
        if current_offset + 4 > payload.len() {
            break;
        }

        let len = u32::from_le_bytes([
            payload[current_offset],
            payload[current_offset + 1],
            payload[current_offset + 2],
            payload[current_offset + 3],
        ]) as usize;
        current_offset += 4;

        // Read edge record
        if current_offset + len > payload.len() {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "Edge record truncated",
            ));
        }

        let edge_bytes = &payload[current_offset..current_offset + len];
        let edge: EdgeRecord = rmp_serde::from_slice(edge_bytes).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to deserialize edge: {}",
                e
            ))
        })?;

        // Filter: only import edges (kind == 0)
        // File filtering: requires node_id → file_id lookup table
        if edge.kind == 0 {
            // 0 = Import edge
            // Return (src_ref, dst_ref) tuple
            let edge_dict = PyDict::new(py);
            edge_dict.set_item("src_ref", edge.src_ref)?;
            edge_dict.set_item("dst_ref", edge.dst_ref)?;
            edge_dict.set_item("kind", edge.kind)?;
            list.append(edge_dict)?;
        }

        current_offset += len;
    }

    Ok(list.into())
}

pub fn register_dict_api(m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_file_summary_dict, m)?)?;
    m.add_function(wrap_pyfunction!(iterate_file_nodes_dict, m)?)?;
    m.add_function(wrap_pyfunction!(get_import_edges_dict, m)?)?;
    Ok(())
}
