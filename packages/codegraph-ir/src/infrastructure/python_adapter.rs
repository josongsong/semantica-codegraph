/*
 * Infrastructure: Python (PyO3) Adapter
 *
 * Exposes Rust functionality to Python
 */

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use rayon::prelude::*;

use crate::domain::models::{SourceFile, ProcessingContext};
use crate::domain::ports::IrProcessor;
use crate::application::DefaultIrProcessor;
use crate::infrastructure::TreeSitterParser;

/// Initialize Rayon thread pool (75% of cores)
pub fn init_rayon() {
    use std::sync::Once;
    static INIT: Once = Once::new();
    
    INIT.call_once(|| {
        let num_cpus = num_cpus::get();
        let threads = std::cmp::max(1, (num_cpus * 3) / 4);
        
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build_global()
            .expect("Failed to init Rayon");
        
        eprintln!("[AST] Rayon pool: {} threads (75% of {})", threads, num_cpus);
    });
}

/// Process Python files and generate IR (Python API)
#[pyfunction]
pub fn process_python_files(
    py: Python,
    files: &PyList,
    repo_id: String,
) -> PyResult<Py<PyList>> {
    init_rayon();
    
    // Extract file data (with GIL)
    let mut file_data = Vec::with_capacity(files.len());
    for item in files.iter() {
        let tuple = item.downcast::<pyo3::types::PyTuple>()?;
        let file_path = tuple.get_item(0)?.extract::<String>()?;
        let content = tuple.get_item(1)?.extract::<String>()?;
        let module_path = tuple.get_item(2)?.extract::<String>()?;
        
        file_data.push(SourceFile::new(file_path, content, module_path));
    }
    
    // Create processor (Hexagonal: Dependency Injection)
    let parser = TreeSitterParser::new();
    let processor = DefaultIrProcessor::new(parser);
    let context = ProcessingContext::new(repo_id);
    
    // GIL RELEASE - Process in parallel
    let results = py.allow_threads(|| {
        processor.process_files(file_data, &context)
    });
    
    // Convert back to Python (with GIL)
    let py_results = PyList::empty(py);
    
    for (i, result) in results.into_iter().enumerate() {
        let result_dict = PyDict::new(py);
        result_dict.set_item("file_index", i)?;
        result_dict.set_item("success", result.is_success())?;
        
        if !result.errors.is_empty() {
            result_dict.set_item("errors", result.errors)?;
        }
        
        // Convert nodes
        let py_nodes = PyList::empty(py);
        for node in result.nodes {
            let node_dict = PyDict::new(py);
            node_dict.set_item("id", node.id)?;
            node_dict.set_item("kind", node.kind.as_str())?;
            node_dict.set_item("fqn", node.fqn)?;
            node_dict.set_item("file_path", node.file_path)?;
            node_dict.set_item("language", node.language)?;
            
            // Span
            let span_dict = PyDict::new(py);
            span_dict.set_item("start_line", node.span.start_line)?;
            span_dict.set_item("start_col", node.span.start_col)?;
            span_dict.set_item("end_line", node.span.end_line)?;
            span_dict.set_item("end_col", node.span.end_col)?;
            node_dict.set_item("span", span_dict)?;
            
            // Optional fields
            if let Some(name) = node.name {
                node_dict.set_item("name", name)?;
            }
            if let Some(module_path) = node.module_path {
                node_dict.set_item("module_path", module_path)?;
            }
            if let Some(parent_id) = node.parent_id {
                node_dict.set_item("parent_id", parent_id)?;
            }
            if let Some(docstring) = node.docstring {
                node_dict.set_item("docstring", docstring)?;
            }
            if let Some(content_hash) = node.content_hash {
                node_dict.set_item("content_hash", content_hash)?;
            }
            
            py_nodes.append(node_dict)?;
        }
        result_dict.set_item("nodes", py_nodes)?;
        
        // Convert edges
        let py_edges = PyList::empty(py);
        for edge in result.edges {
            let edge_dict = PyDict::new(py);
            edge_dict.set_item("id", edge.id)?;
            edge_dict.set_item("kind", edge.kind.as_str())?;
            edge_dict.set_item("source_id", edge.source_id)?;
            edge_dict.set_item("target_id", edge.target_id)?;
            
            if let Some(span) = edge.span {
                let span_dict = PyDict::new(py);
                span_dict.set_item("start_line", span.start_line)?;
                span_dict.set_item("start_col", span.start_col)?;
                span_dict.set_item("end_line", span.end_line)?;
                span_dict.set_item("end_col", span.end_col)?;
                edge_dict.set_item("span", span_dict)?;
            }
            
            py_edges.append(edge_dict)?;
        }
        result_dict.set_item("edges", py_edges)?;
        
        py_results.append(result_dict)?;
    }
    
    Ok(py_results.into())
}

