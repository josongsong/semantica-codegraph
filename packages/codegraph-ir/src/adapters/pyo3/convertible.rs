//! PyO3 Conversion Traits and Utilities
//!
//! SOTA: Unified type conversion between Rust and Python.
//!
//! Eliminates 400+ lines of duplicate conversion code in lib.rs
//! by providing a consistent trait-based approach.
//!
//! # Design
//! - `ToPyDict`: Convert Rust types to Python dicts
//! - `ToPyList`: Convert collections to Python lists
//! - `FromPyDict`: Convert Python dicts to Rust types
//! - Span handling utilities (used 17+ times in original code)

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::features::data_flow::infrastructure::dfg::DataFlowGraph;
use crate::features::flow_graph::infrastructure::bfg::BasicFlowGraph;
use crate::features::flow_graph::infrastructure::cfg::CFGEdge;
use crate::features::ssa::infrastructure::ssa::SSAGraph;
use crate::features::type_resolution::domain::type_entity::TypeEntity;
use crate::pipeline::processor::{PDGSummary, SliceSummary, TaintSummary};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Occurrence, Span};

// Note: Node/Edge aliases removed - using shared::models directly (SSOT)

// ═══════════════════════════════════════════════════════════════════════════
// Conversion Traits
// ═══════════════════════════════════════════════════════════════════════════

/// Convert Rust type to Python dict
pub trait ToPyDict {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>>;
}

/// Convert Rust collection to Python list
pub trait ToPyList {
    fn to_py_list(&self, py: Python) -> PyResult<Py<PyList>>;
}

/// Convert Python dict to Rust type
pub trait FromPyDict: Sized {
    fn from_py_dict(dict: &PyDict) -> PyResult<Self>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Span Conversion (used 17+ times in original code)
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for Span {
    #[inline]
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("start_line", self.start_line)?;
        dict.set_item("start_col", self.start_col)?;
        dict.set_item("end_line", self.end_line)?;
        dict.set_item("end_col", self.end_col)?;
        Ok(dict.into())
    }
}

impl FromPyDict for Span {
    fn from_py_dict(dict: &PyDict) -> PyResult<Self> {
        let start_line: u32 = dict
            .get_item("start_line")?
            .map(|v| v.extract().unwrap_or(1))
            .unwrap_or(1);
        let start_col: u32 = dict
            .get_item("start_col")?
            .map(|v| v.extract().unwrap_or(0))
            .unwrap_or(0);
        let end_line: u32 = dict
            .get_item("end_line")?
            .map(|v| v.extract().unwrap_or(1))
            .unwrap_or(1);
        let end_col: u32 = dict
            .get_item("end_col")?
            .map(|v| v.extract().unwrap_or(0))
            .unwrap_or(0);

        Ok(Span::new(start_line, start_col, end_line, end_col))
    }
}

/// Helper to create span dict inline (for optional spans)
#[inline]
pub fn span_to_py_dict(py: Python, span: &Span) -> PyResult<Py<PyDict>> {
    span.to_py_dict(py)
}

/// Extract span from parent dict that has a "span" field
pub fn extract_span_from_dict(dict: &PyDict) -> PyResult<Span> {
    let span_dict = dict
        .get_item("span")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("span"))?
        .downcast::<PyDict>()?;
    Span::from_py_dict(span_dict)
}

// ═══════════════════════════════════════════════════════════════════════════
// Node Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for Node {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        // Required fields
        dict.set_item("id", &self.id)?;
        dict.set_item("kind", self.kind.as_str())?;
        dict.set_item("fqn", &self.fqn)?;
        dict.set_item("file_path", &self.file_path)?;
        dict.set_item("language", &self.language)?;
        dict.set_item("span", self.span.to_py_dict(py)?)?;

        // Optional fields (only set if Some)
        if let Some(ref name) = self.name {
            dict.set_item("name", name)?;
        }
        if let Some(ref module_path) = self.module_path {
            dict.set_item("module_path", module_path)?;
        }
        if let Some(ref parent_id) = self.parent_id {
            dict.set_item("parent_id", parent_id)?;
        }
        if let Some(ref docstring) = self.docstring {
            dict.set_item("docstring", docstring)?;
        }
        if let Some(ref content_hash) = self.content_hash {
            dict.set_item("content_hash", content_hash)?;
        }

        Ok(dict.into())
    }
}

impl FromPyDict for Node {
    fn from_py_dict(dict: &PyDict) -> PyResult<Self> {
        let id: String = dict
            .get_item("id")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("id"))?
            .extract()?;

        let kind_str: String = dict
            .get_item("kind")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("kind"))?
            .extract()?;

        // Parse NodeKind from string
        let kind = match kind_str.to_lowercase().as_str() {
            "file" => NodeKind::File,
            "module" => NodeKind::Module,
            "class" => NodeKind::Class,
            "function" => NodeKind::Function,
            "method" => NodeKind::Method,
            "variable" => NodeKind::Variable,
            "parameter" => NodeKind::Parameter,
            "field" => NodeKind::Field,
            "lambda" => NodeKind::Lambda,
            "import" => NodeKind::Import,
            _ => NodeKind::Variable, // default fallback
        };

        let fqn: String = dict
            .get_item("fqn")?
            .map(|v| v.extract().unwrap_or_default())
            .unwrap_or_default();

        let file_path: String = dict
            .get_item("file_path")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("file_path"))?
            .extract()?;

        let span = extract_span_from_dict(dict)?;

        let name: Option<String> = dict.get_item("name")?.and_then(|v| v.extract().ok());

        let mut node = Node::new(id, kind, fqn, file_path, span);
        if let Some(n) = name {
            node = node.with_name(n);
        }

        Ok(node)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Edge Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for Edge {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        // Generate ID from source + target
        let id = format!("{}→{}", self.source_id, self.target_id);
        dict.set_item("id", &id)?;
        dict.set_item("kind", self.kind.as_str())?;
        dict.set_item("source_id", &self.source_id)?;
        dict.set_item("target_id", &self.target_id)?;

        if let Some(ref span) = self.span {
            dict.set_item("span", span.to_py_dict(py)?)?;
        }

        Ok(dict.into())
    }
}

impl FromPyDict for Edge {
    fn from_py_dict(dict: &PyDict) -> PyResult<Self> {
        let source_id: String = dict
            .get_item("source_id")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("source_id"))?
            .extract()?;

        let target_id: String = dict
            .get_item("target_id")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("target_id"))?
            .extract()?;

        let kind_str: String = dict
            .get_item("kind")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("kind"))?
            .extract()?;

        // Parse EdgeKind from string
        let kind = match kind_str.to_uppercase().as_str() {
            "CONTAINS" => EdgeKind::Contains,
            "CALLS" => EdgeKind::Calls,
            "READS" => EdgeKind::Reads,
            "WRITES" => EdgeKind::Writes,
            "INHERITS" => EdgeKind::Inherits,
            "IMPORTS" => EdgeKind::Imports,
            "REFERENCES" => EdgeKind::References,
            "DEFINES" => EdgeKind::Defines,
            _ => EdgeKind::References, // default fallback
        };

        Ok(Edge::new(source_id, target_id, kind))
    }
}

// NOTE: Node and Edge ToPyDict implementations defined above (using shared::models)

// ═══════════════════════════════════════════════════════════════════════════
// BFG (Basic Flow Graph) Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for BasicFlowGraph {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("id", &self.id)?;
        dict.set_item("function_id", &self.function_id)?;
        dict.set_item("entry_block_id", &self.entry_block_id)?;
        dict.set_item("exit_block_id", &self.exit_block_id)?;
        dict.set_item("total_statements", self.total_statements)?;

        // Convert blocks to list
        let py_blocks = PyList::empty(py);
        for block in &self.blocks {
            let block_dict = PyDict::new(py);
            block_dict.set_item("id", &block.id)?;
            block_dict.set_item("kind", &block.kind)?;
            block_dict.set_item("statement_count", block.statement_count)?;
            // Manually convert span
            let span_dict = PyDict::new(py);
            span_dict.set_item("start_line", block.span_ref.span.start_line)?;
            span_dict.set_item("start_col", block.span_ref.span.start_col)?;
            span_dict.set_item("end_line", block.span_ref.span.end_line)?;
            span_dict.set_item("end_col", block.span_ref.span.end_col)?;
            block_dict.set_item("span", span_dict)?;
            py_blocks.append(block_dict)?;
        }
        dict.set_item("blocks", py_blocks)?;

        Ok(dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// CFG Edge Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for CFGEdge {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("source_block_id", &self.source_block_id)?;
        dict.set_item("target_block_id", &self.target_block_id)?;
        dict.set_item("edge_type", self.edge_type.as_str())?;

        Ok(dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Type Entity Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for TypeEntity {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("id", &self.id)?;
        dict.set_item("raw", &self.raw)?;
        dict.set_item("flavor", self.flavor.as_str())?;
        dict.set_item("is_nullable", self.is_nullable)?;
        dict.set_item("resolution_level", self.resolution_level.as_str())?;

        if let Some(ref resolved_target) = self.resolved_target {
            dict.set_item("resolved_target", resolved_target)?;
        }

        if !self.generic_param_ids.is_empty() {
            let py_params = PyList::empty(py);
            for param_id in &self.generic_param_ids {
                py_params.append(param_id)?;
            }
            dict.set_item("generic_param_ids", py_params)?;
        }

        Ok(dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// DFG Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for DataFlowGraph {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("function_id", &self.function_id)?;
        dict.set_item("node_count", self.nodes.len())?;
        dict.set_item("edge_count", self.def_use_edges.len())?;

        Ok(dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// SSA Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for SSAGraph {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("function_id", &self.function_id)?;
        dict.set_item("variable_count", self.variables.len())?;
        dict.set_item("phi_node_count", self.phi_nodes.len())?;

        Ok(dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// PDG/Taint/Slice Conversion
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for PDGSummary {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("function_id", &self.function_id)?;
        dict.set_item("node_count", self.node_count)?;
        dict.set_item("control_edges", self.control_edges)?;
        dict.set_item("data_edges", self.data_edges)?;

        Ok(dict.into())
    }
}

impl ToPyDict for TaintSummary {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("function_id", &self.function_id)?;
        dict.set_item("sources_found", self.sources_found)?;
        dict.set_item("sinks_found", self.sinks_found)?;
        dict.set_item("taint_flows", self.taint_flows)?;

        Ok(dict.into())
    }
}

impl ToPyDict for SliceSummary {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("function_id", &self.function_id)?;
        dict.set_item("criterion", &self.criterion)?;
        dict.set_item("slice_size", self.slice_size)?;

        Ok(dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Occurrence Conversion (SCIP-compatible)
// ═══════════════════════════════════════════════════════════════════════════

impl ToPyDict for Occurrence {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("id", &self.id)?;
        dict.set_item("symbol_id", &self.symbol_id)?;
        dict.set_item("roles", self.roles)?;
        dict.set_item("file_path", &self.file_path)?;
        dict.set_item("importance_score", self.importance_score)?;
        dict.set_item("span", self.span.to_py_dict(py)?)?;

        if let Some(ref parent) = self.parent_symbol_id {
            dict.set_item("parent_symbol_id", parent)?;
        }
        if let Some(ref syntax) = self.syntax_kind {
            dict.set_item("syntax_kind", syntax)?;
        }

        Ok(dict.into())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Collection Conversion Utilities
// ═══════════════════════════════════════════════════════════════════════════

/// Convert a Vec of ToPyDict types to Python list
pub fn vec_to_py_list<T: ToPyDict>(py: Python, items: &[T]) -> PyResult<Py<PyList>> {
    let list = PyList::empty(py);
    for item in items {
        list.append(item.to_py_dict(py)?)?;
    }
    Ok(list.into())
}

/// Convert Vec<String> to Python list
pub fn strings_to_py_list(py: Python, items: &[String]) -> PyResult<Py<PyList>> {
    let list = PyList::empty(py);
    for item in items {
        list.append(item)?;
    }
    Ok(list.into())
}

// ═══════════════════════════════════════════════════════════════════════════
// ProcessResult Conversion (main entry point)
// ═══════════════════════════════════════════════════════════════════════════

use crate::pipeline::processor::ProcessResult;

impl ToPyDict for ProcessResult {
    fn to_py_dict(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);

        dict.set_item("success", self.errors.is_empty())?;

        if !self.errors.is_empty() {
            dict.set_item("errors", &self.errors)?;
        }

        // Convert all collections using trait
        dict.set_item("nodes", vec_to_py_list(py, &self.nodes)?)?;
        dict.set_item("edges", vec_to_py_list(py, &self.edges)?)?;
        dict.set_item("bfg_graphs", vec_to_py_list(py, &self.bfg_graphs)?)?;
        dict.set_item("cfg_edges", vec_to_py_list(py, &self.cfg_edges)?)?;
        dict.set_item("type_entities", vec_to_py_list(py, &self.type_entities)?)?;
        dict.set_item("dfg_graphs", vec_to_py_list(py, &self.dfg_graphs)?)?;
        dict.set_item("ssa_graphs", vec_to_py_list(py, &self.ssa_graphs)?)?;
        dict.set_item("pdg_graphs", vec_to_py_list(py, &self.pdg_graphs)?)?;
        dict.set_item("taint_results", vec_to_py_list(py, &self.taint_results)?)?;
        dict.set_item("slice_results", vec_to_py_list(py, &self.slice_results)?)?;
        dict.set_item("occurrences", vec_to_py_list(py, &self.occurrences)?)?;

        Ok(dict.into())
    }
}

/// Convert Vec<ProcessResult> to Python list with file indices
pub fn results_to_py_list(py: Python, results: Vec<ProcessResult>) -> PyResult<Py<PyList>> {
    let list = PyList::empty(py);

    for (i, result) in results.into_iter().enumerate() {
        let result_dict = PyDict::new(py);
        result_dict.set_item("file_index", i)?;

        // Merge with ToPyDict result
        let inner_dict = result.to_py_dict(py)?;
        let inner_ref = inner_dict.as_ref(py);
        for (key, value) in inner_ref.iter() {
            result_dict.set_item(key, value)?;
        }

        list.append(result_dict)?;
    }

    Ok(list.into())
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_span_roundtrip() {
        pyo3::prepare_freethreaded_python();

        Python::with_gil(|py| {
            let span = Span::new(1, 0, 10, 5);
            let py_dict = span.to_py_dict(py).unwrap();
            let py_dict_ref = py_dict.as_ref(py);

            let span2 = Span::from_py_dict(py_dict_ref).unwrap();

            assert_eq!(span.start_line, span2.start_line);
            assert_eq!(span.start_col, span2.start_col);
            assert_eq!(span.end_line, span2.end_line);
            assert_eq!(span.end_col, span2.end_col);
        });
    }

    #[test]
    fn test_node_to_py_dict() {
        pyo3::prepare_freethreaded_python();

        Python::with_gil(|py| {
            let node = Node::new(
                "test-id".to_string(),
                NodeKind::Function,
                "module.func".to_string(),
                "test.py".to_string(),
                Span::new(1, 0, 10, 0),
            )
            .with_name("func".to_string());

            let py_dict = node.to_py_dict(py).unwrap();
            let py_dict_ref = py_dict.as_ref(py);

            let id: String = py_dict_ref
                .get_item("id")
                .unwrap()
                .unwrap()
                .extract()
                .unwrap();
            assert_eq!(id, "test-id");

            let name: String = py_dict_ref
                .get_item("name")
                .unwrap()
                .unwrap()
                .extract()
                .unwrap();
            assert_eq!(name, "func");
        });
    }

    #[test]
    fn test_edge_roundtrip() {
        pyo3::prepare_freethreaded_python();

        Python::with_gil(|py| {
            let edge = Edge::new("source".to_string(), "target".to_string(), EdgeKind::Calls);

            let py_dict = edge.to_py_dict(py).unwrap();
            let py_dict_ref = py_dict.as_ref(py);

            let edge2 = Edge::from_py_dict(py_dict_ref).unwrap();

            assert_eq!(edge.source_id, edge2.source_id);
            assert_eq!(edge.target_id, edge2.target_id);
        });
    }
}
