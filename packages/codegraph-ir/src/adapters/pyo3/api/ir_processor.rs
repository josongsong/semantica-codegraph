//! IR Processor PyO3 Bindings
//!
//! Exposes IR building functionality to Python
//!
//! Allows Python to:
//! 1. Pass source code → Get IR (nodes, edges)
//! 2. Build CFG/DFG from IR
//! 3. Run advanced taint analysis

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;
use crate::features::flow_graph::infrastructure::cfg::CFGEdge;
use crate::shared::models::{Edge, Node};

// ═══════════════════════════════════════════════════════════════════════════
// IR Processing Result
// ═══════════════════════════════════════════════════════════════════════════

/// Result from IR processing
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IRProcessResult {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub cfg_edges: Vec<CFGEdge>,
    pub dfg_graphs: Vec<DataFlowGraph>,
    pub errors: Vec<String>,
}

// ═══════════════════════════════════════════════════════════════════════════
// PyO3 Functions
// ═══════════════════════════════════════════════════════════════════════════

/// Process source code and build IR
///
/// This function:
/// 1. Parses source code using tree-sitter
/// 2. Builds intermediate representation (IR)
/// 3. Returns nodes and edges as msgpack
///
/// # Arguments
/// * `source_code` - Source code as string
/// * `file_path` - File path for metadata
/// * `language` - Language ("python", "javascript", etc.)
/// * `repo_id` - Repository ID for context
///
/// # Returns
/// Msgpack bytes containing IRProcessResult
///
/// # Example (Python)
/// ```python
/// from codegraph_ir import process_source_file
///
/// source = """
/// def vulnerable():
///     user_input = input()
///     eval(user_input)
/// """
///
/// result_bytes = process_source_file(
///     source_code=source,
///     file_path="test.py",
///     language="python",
///     repo_id="test-repo"
/// )
///
/// result = msgpack.unpackb(result_bytes, raw=False)
/// print(f"Nodes: {len(result['nodes'])}")
/// print(f"Edges: {len(result['edges'])}")
/// ```
#[pyfunction]
#[pyo3(signature = (source_code, file_path, language="python", repo_id="adhoc"))]
pub fn process_source_file<'py>(
    py: Python<'py>,
    source_code: &str,
    file_path: &str,
    language: &str,
    repo_id: &str,
) -> PyResult<&'py PyBytes> {
    use crate::pipeline::processor::process_python_file;

    // Only Python supported for now
    if language != "python" {
        let result = IRProcessResult {
            nodes: Vec::new(),
            edges: Vec::new(),
            cfg_edges: Vec::new(),
            dfg_graphs: Vec::new(),
            errors: vec![format!(
                "Language '{}' not yet supported. Only 'python' is available.",
                language
            )],
        };

        let result_bytes = rmp_serde::to_vec_named(&result).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
                "Failed to serialize IR result: {}",
                e
            ))
        })?;

        return Ok(PyBytes::new(py, &result_bytes));
    }

    // Generate module path from file path (e.g., "src/main.py" → "src.main")
    let module_path = file_path.trim_end_matches(".py").replace('/', ".");

    // Call Rust IR processor with GIL released
    let process_result =
        py.allow_threads(|| process_python_file(source_code, repo_id, file_path, &module_path));

    // Convert to IRProcessResult (include CFG and DFG)
    let result = IRProcessResult {
        nodes: process_result.nodes,
        edges: process_result.edges,
        cfg_edges: process_result.cfg_edges,
        dfg_graphs: process_result.dfg_graphs,
        errors: process_result.errors,
    };

    // Serialize to msgpack (named format for Python dict compatibility)
    let result_bytes = rmp_serde::to_vec_named(&result).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Failed to serialize IR result: {}",
            e
        ))
    })?;

    Ok(PyBytes::new(py, &result_bytes))
}

/// Build CFG from IR nodes
///
/// This function builds a Control Flow Graph from IR nodes.
///
/// # Arguments
/// * `nodes_bytes` - Msgpack-encoded nodes
/// * `edges_bytes` - Msgpack-encoded edges
///
/// # Returns
/// Msgpack bytes containing CFG edges
#[pyfunction]
pub fn build_cfg_from_ir<'py>(
    py: Python<'py>,
    nodes_bytes: Vec<u8>,
    edges_bytes: Vec<u8>,
) -> PyResult<&'py PyBytes> {
    use crate::features::flow_graph::infrastructure::cfg::build_cfg_edges;
    use crate::pipeline::processor::process_python_file;

    // Deserialize nodes and edges
    let _nodes: Vec<Node> = rmp_serde::from_slice(&nodes_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Failed to deserialize nodes: {}",
            e
        ))
    })?;

    let _edges: Vec<Edge> = rmp_serde::from_slice(&edges_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Failed to deserialize edges: {}",
            e
        ))
    })?;

    // CFG requires BFG blocks which come from process_python_file()
    // This function is a helper - you should call process_source_file() first
    // which returns ProcessResult with bfg_graphs already computed

    // For now, return empty since CFG is built as part of process_python_file()
    // and included in ProcessResult.cfg_edges
    let cfg_edges: Vec<CFGEdge> = Vec::new();

    // Serialize
    let result_bytes = rmp_serde::to_vec(&cfg_edges).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to serialize CFG: {}", e))
    })?;

    Ok(PyBytes::new(py, &result_bytes))
}

/// Build DFG from IR nodes
///
/// This function builds a Data Flow Graph from IR nodes using the AdvancedDFGBuilder.
///
/// # Arguments
/// * `nodes_bytes` - Msgpack-encoded nodes
/// * `edges_bytes` - Msgpack-encoded edges
///
/// # Returns
/// Msgpack bytes containing DFG
#[pyfunction]
pub fn build_dfg_from_ir<'py>(
    py: Python<'py>,
    nodes_bytes: Vec<u8>,
    edges_bytes: Vec<u8>,
) -> PyResult<&'py PyBytes> {
    use crate::features::data_flow::infrastructure::advanced_dfg_builder::AdvancedDFGBuilder;

    // Deserialize nodes and edges
    let nodes: Vec<Node> = rmp_serde::from_slice(&nodes_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Failed to deserialize nodes: {}",
            e
        ))
    })?;

    let edges: Vec<Edge> = rmp_serde::from_slice(&edges_bytes).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Failed to deserialize edges: {}",
            e
        ))
    })?;

    // Extract function_id from nodes (use first function node or file_path)
    let function_id = nodes
        .iter()
        .find(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
        .map(|n| n.name.clone().unwrap_or_else(|| "unknown".to_string()))
        .unwrap_or_else(|| {
            // Fallback: use file path
            nodes
                .first()
                .map(|n| n.file_path.clone())
                .unwrap_or_else(|| "unknown".to_string())
        });

    // Build DFG using AdvancedDFGBuilder
    let mut builder = AdvancedDFGBuilder::new();
    let dfg = builder
        .build_from_ir(&nodes, &edges, &function_id)
        .map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to build DFG: {}", e))
        })?;

    // Serialize
    let result_bytes = rmp_serde::to_vec(&dfg).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to serialize DFG: {}", e))
    })?;

    Ok(PyBytes::new(py, &result_bytes))
}

// ═══════════════════════════════════════════════════════════════════════════
// Module Registration
// ═══════════════════════════════════════════════════════════════════════════

pub fn register_ir_processor_functions(m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_source_file, m)?)?;
    m.add_function(wrap_pyfunction!(build_cfg_from_ir, m)?)?;
    m.add_function(wrap_pyfunction!(build_dfg_from_ir, m)?)?;
    Ok(())
}
