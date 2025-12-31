/*
 * Codegraph IR - SOTA Code Analysis Engine
 *
 * Feature-First Hexagonal Architecture:
 * - shared/      : Common models (Node, Edge, Span)
 * - features/    : Vertical slices (parsing → ir → flow → dfg → ssa → pdg → taint → slicing)
 * - pipeline/    : Orchestration
 * - adapters/    : External bindings (PyO3)
 *
 * Performance:
 * - GIL release for true parallelism
 * - Rayon work-stealing
 * - 3x faster than Python implementation
 */

// Crate-level lint configuration
#![allow(dead_code)] // Many functions reserved for future use
#![allow(unused_variables)] // Parameters kept for API compatibility
#![allow(unused_imports)] // Conditional imports for feature flags
#![allow(clippy::too_many_arguments)] // Complex analysis functions need many params
#![allow(clippy::type_complexity)] // Complex types are necessary for analysis
#![allow(clippy::or_fun_call)] // or_insert_with vs or_default style preference
#![allow(clippy::map_entry)] // Style preference for entry API
#![allow(clippy::option_map_or_none)] // map_or style preference
#![allow(clippy::collapsible_if)] // Readability over brevity
#![allow(clippy::clone_on_copy)] // Explicit clone for clarity
#![allow(clippy::should_implement_trait)] // from_str naming intentional
#![allow(clippy::double_ended_iterator_last)] // Performance acceptable
#![allow(clippy::useless_format)] // Format consistency
#![allow(clippy::derivable_impls)] // Manual impl for documentation
#![allow(clippy::if_same_then_else)] // Branch clarity preferred
#![allow(clippy::only_used_in_recursion)] // Recursive params for API clarity
#![allow(clippy::empty_line_after_doc_comments)] // Doc comment style
#![allow(clippy::unwrap_or_default)] // or_insert_with style preference
#![allow(clippy::option_if_let_else)] // map_or style preference
#![allow(clippy::manual_find)] // Explicit iteration for clarity
#![allow(clippy::redundant_closure)] // Closure for consistency
#![allow(clippy::useless_conversion)] // Explicit conversion for clarity
#![allow(clippy::iter_kv_map)] // Map iteration style
#![allow(clippy::manual_map)] // map_or style preference
#![allow(clippy::needless_lifetimes)] // Explicit lifetimes for clarity
#![allow(clippy::upper_case_acronyms)] // SSA, PDG naming
#![allow(clippy::inherent_to_string)] // to_string impl intentional
#![allow(clippy::module_inception)] // Module naming intentional
#![allow(clippy::new_without_default)] // Default impl not always needed
#![allow(clippy::for_kv_map)] // Map iteration clarity
#![allow(clippy::single_match)] // Single match for readability
#![allow(clippy::manual_strip)] // Manual strip for clarity
#![allow(clippy::explicit_counter_loop)] // Explicit counter for clarity
#![allow(clippy::needless_range_loop)] // Range loop for indexing
#![allow(clippy::collapsible_else_if)] // else if clarity
#![allow(clippy::collapsible_match)] // Match clarity
#![allow(clippy::match_like_matches_macro)] // Match for readability
#![allow(clippy::ptr_arg)] // &PathBuf intentional for API compatibility
#![allow(clippy::doc_nested_refdefs)] // Doc comment style
#![allow(clippy::needless_borrowed_reference)] // Borrowed ref for clarity
#![allow(clippy::trim_split_whitespace)] // Trim then split intentional
#![allow(clippy::map_flatten)] // Map then flatten for clarity
#![allow(clippy::unnecessary_map_or)] // map_or style for compatibility
#![allow(clippy::manual_string_new)] // String construction style
#![allow(deprecated)] // GraphIndex temporarily deprecated until graph_builder completion

// Import tracing macros (conditional on feature)
#[cfg(feature = "trace")]
use tracing::{debug, error, info, trace, warn};

use crate::shared::models::Span;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyTuple};
use rayon::prelude::*;
use std::collections::HashMap;
use tree_sitter::{Node, Parser};

// ═══════════════════════════════════════════════════════════════════════════
// Module Exports - Feature-First Architecture
// ═══════════════════════════════════════════════════════════════════════════

/// Shared models and utilities
pub mod shared;

/// Feature modules (L1-L6 pipeline stages)
pub mod features;

/// Pipeline orchestration
pub mod pipeline;

/// Configuration system (RFC-001)
pub mod config;

/// External adapters (PyO3, etc.)
pub mod adapters;

/// Language-agnostic Core API (for FFI wrappers)
pub mod api;

/// Error types
pub mod errors;

/// Usecase layer (IndexingService, etc.)
pub mod usecases;

/// Benchmark system (RFC-002: SOTA Benchmark with Ground Truth)
pub mod benchmark;

// ═══════════════════════════════════════════════════════════════════════════
// Re-exports for Public API
// ═══════════════════════════════════════════════════════════════════════════

pub use pipeline::processor::{process_python_file, ProcessResult};

// RFC-RUST-ENGINE Phase 2: Projection API exports (Python-only)
#[cfg(feature = "python")]
pub use features::indexing::adapters::projection::EngineHandle;

// Clone Detection API exports
// Temporarily commented out due to compilation errors
/*
pub use features::clone_detection::{
    CloneDetector, CloneType, CodeFragment, ClonePair,
    Type1Detector, Type2Detector, Type3Detector, Type4Detector,
    MultiLevelDetector,
};
*/

// ═══════════════════════════════════════════════════════════════════════════
// Internal Types
// ═══════════════════════════════════════════════════════════════════════════

/// Temporary AST node for tree-sitter traversal (legacy API)
#[derive(Debug, Clone)]
pub struct AstNode {
    pub kind: String,
    pub name: Option<String>,
    pub span: Span,
    pub children_count: usize,
}

// ═══════════════════════════════════════════════════════════════════════════
// Rayon Thread Pool
// ═══════════════════════════════════════════════════════════════════════════

/// Initialize Rayon thread pool (75% of cores)
fn init_rayon() {
    use std::sync::Once;
    static INIT: Once = Once::new();

    INIT.call_once(|| {
        let num_cpus = num_cpus::get();
        let threads = std::cmp::max(1, (num_cpus * 3) / 4);

        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build_global()
            .expect("Failed to init Rayon");

        eprintln!(
            "[codegraph-ir] Rayon pool: {} threads (75% of {})",
            threads, num_cpus
        );
    });
}

// ═══════════════════════════════════════════════════════════════════════════
// Legacy API (for backward compatibility)
// ═══════════════════════════════════════════════════════════════════════════

/// Traverse AST and extract nodes (single file) - Legacy API
pub fn traverse_ast_single(content: &str) -> Result<Vec<AstNode>, String> {
    let mut parser = Parser::new();
    let language = tree_sitter_python::language();
    parser
        .set_language(&language)
        .map_err(|e| format!("Failed to set language: {}", e))?;

    let tree = parser
        .parse(content, None)
        .ok_or_else(|| "Failed to parse content".to_string())?;

    let root = tree.root_node();
    let mut stack = vec![root];
    let mut result = Vec::new();

    const TARGET_TYPES: &[&str] = &[
        "class_definition",
        "function_definition",
        "decorated_definition",
        "import_statement",
        "import_from_statement",
    ];

    while let Some(current) = stack.pop() {
        let node_type = current.kind();

        if TARGET_TYPES.contains(&node_type) {
            let name = extract_node_name(&current, content);
            let span = node_to_span(&current);

            result.push(AstNode {
                kind: node_type.to_string(),
                name,
                span,
                children_count: current.child_count(),
            });
        } else {
            for i in (0..current.child_count()).rev() {
                if let Some(child) = current.child(i) {
                    stack.push(child);
                }
            }
        }
    }

    Ok(result)
}

fn extract_node_name(node: &Node, source: &str) -> Option<String> {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "identifier" {
                let start = child.start_byte();
                let end = child.end_byte();
                return Some(source[start..end].to_string());
            }
        }
    }
    None
}

fn node_to_span(node: &Node) -> Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    Span::new(
        start_pos.row as u32 + 1,
        start_pos.column as u32,
        end_pos.row as u32 + 1,
        end_pos.column as u32,
    )
}

// ═══════════════════════════════════════════════════════════════════════════
// PyO3 Bindings
// ═══════════════════════════════════════════════════════════════════════════

/// Traverse multiple files in parallel - Legacy API
#[cfg(feature = "python")]
#[pyfunction]
fn traverse_ast_parallel(py: Python, files: &PyList) -> PyResult<Py<PyList>> {
    init_rayon();

    let mut file_data = Vec::with_capacity(files.len());
    for item in files.iter() {
        let tuple = item.downcast::<pyo3::types::PyTuple>()?;
        let path = tuple.get_item(0)?.extract::<String>()?;
        let content = tuple.get_item(1)?.extract::<String>()?;
        file_data.push((path, content));
    }

    let results: Vec<Result<Vec<AstNode>, String>> = py.allow_threads(|| {
        file_data
            .par_iter()
            .map(|(_path, content)| traverse_ast_single(content))
            .collect()
    });

    let py_results = PyList::empty(py);

    for (i, result) in results.into_iter().enumerate() {
        let result_dict = PyDict::new(py);
        result_dict.set_item("file_index", i)?;

        match result {
            Ok(nodes) => {
                result_dict.set_item("success", true)?;
                result_dict.set_item("node_count", nodes.len())?;

                let py_nodes = PyList::empty(py);
                for node in nodes {
                    let node_dict = PyDict::new(py);
                    node_dict.set_item("kind", node.kind)?;
                    node_dict.set_item("name", node.name)?;

                    let span_dict = PyDict::new(py);
                    span_dict.set_item("start_line", node.span.start_line)?;
                    span_dict.set_item("start_col", node.span.start_col)?;
                    span_dict.set_item("end_line", node.span.end_line)?;
                    span_dict.set_item("end_col", node.span.end_col)?;
                    node_dict.set_item("span", span_dict)?;

                    node_dict.set_item("children_count", node.children_count)?;
                    py_nodes.append(node_dict)?;
                }
                result_dict.set_item("nodes", py_nodes)?;
            }
            Err(err) => {
                result_dict.set_item("success", false)?;
                result_dict.set_item("error", err)?;
            }
        }

        py_results.append(result_dict)?;
    }

    Ok(py_results.into())
}

/// Process Python files and generate IR (L1-L5 pipeline)
///
/// SOTA Features:
/// - L1: AST Parsing (tree-sitter)
/// - L2: IR Generation (Node + Edge)
/// - L3a: BFG/CFG Construction
/// - L3b: Type Resolution
/// - L4: DFG Generation
/// - L5: SSA Construction
#[cfg(feature = "python")]
#[pyfunction]
fn process_python_files(py: Python, files: &PyList, repo_id: String) -> PyResult<Py<PyList>> {
    init_rayon();

    let mut file_data = Vec::with_capacity(files.len());
    for item in files.iter() {
        let tuple = item.downcast::<pyo3::types::PyTuple>()?;
        let file_path = tuple.get_item(0)?.extract::<String>()?;
        let content = tuple.get_item(1)?.extract::<String>()?;
        let module_path = tuple.get_item(2)?.extract::<String>()?;
        file_data.push((file_path, content, module_path));
    }

    // GIL RELEASE - Process in parallel with Rayon
    let ir_build_start = std::time::Instant::now();
    let mut results: Vec<ProcessResult> = py.allow_threads(|| {
        file_data
            .par_iter()
            .map(|(file_path, content, module_path)| {
                process_python_file(content, &repo_id, file_path, module_path)
            })
            .collect()
    });
    let ir_build_elapsed = ir_build_start.elapsed();

    // 🚀 SOTA: Batched occurrence generation (7.6x faster than Python L2)
    // Generate occurrences for all files in parallel after IR build
    py.allow_threads(|| {
        use rayon::prelude::*;
        results.par_iter_mut().for_each(|result| {
            let occurrences =
                pipeline::processor::generate_occurrences_pub(&result.nodes, &result.edges);
            result.occurrences = occurrences;
        });
    });

    // Convert results to Python
    convert_results_to_python(py, results)
}

/// Process files in ANY supported language (Python, TypeScript, Java, Go, Kotlin, Rust)
///
/// Auto-detects language from file extension and uses appropriate parser.
///
/// SOTA Multi-Language Support:
/// - Python (.py)
/// - TypeScript/JavaScript (.ts, .tsx, .js, .jsx)
/// - Java (.java)
/// - Go (.go)
/// - Kotlin (.kt, .kts)
/// - Rust (.rs)
///
/// Input format: List of (file_path, content, module_path) tuples
/// - file_path: Path with extension (used for language detection)
/// - content: File content as string
/// - module_path: Module path (optional, use "" for non-Python languages)
///
/// Returns: Same format as process_python_files
#[cfg(feature = "python")]
#[pyfunction]
fn process_files(py: Python, files: &PyList, repo_id: String) -> PyResult<Py<PyList>> {
    init_rayon();

    let mut file_data = Vec::with_capacity(files.len());
    for item in files.iter() {
        let tuple = item.downcast::<pyo3::types::PyTuple>()?;
        let file_path = tuple.get_item(0)?.extract::<String>()?;
        let content = tuple.get_item(1)?.extract::<String>()?;
        let module_path = tuple.get_item(2)?.extract::<String>()?;
        file_data.push((file_path, content, module_path));
    }

    // GIL RELEASE - Process in parallel with Rayon
    // Uses pipeline::processor::process_file() which auto-detects language
    let mut results: Vec<ProcessResult> = py.allow_threads(|| {
        file_data
            .par_iter()
            .map(|(file_path, content, module_path)| {
                pipeline::processor::process_file(content, &repo_id, file_path, module_path)
            })
            .collect()
    });

    // 🚀 SOTA: Batched occurrence generation (7.6x faster than Python L2)
    // Generate occurrences for all files in parallel after IR build
    py.allow_threads(|| {
        use rayon::prelude::*;
        results.par_iter_mut().for_each(|result| {
            let occurrences =
                pipeline::processor::generate_occurrences_pub(&result.nodes, &result.edges);
            result.occurrences = occurrences;
        });
    });

    // Convert results to Python
    convert_results_to_python(py, results)
}

#[cfg(feature = "python")]
fn convert_results_to_python(py: Python, results: Vec<ProcessResult>) -> PyResult<Py<PyList>> {
    let py_results = PyList::empty(py);

    for (i, result) in results.into_iter().enumerate() {
        let result_dict = PyDict::new(py);
        result_dict.set_item("file_index", i)?;
        result_dict.set_item("success", result.errors.is_empty())?;

        if !result.errors.is_empty() {
            result_dict.set_item("errors", result.errors)?;
        }

        // Nodes
        let py_nodes = PyList::empty(py);
        for node in result.nodes {
            let node_dict = PyDict::new(py);
            node_dict.set_item("id", node.id)?;
            node_dict.set_item("kind", node.kind.as_str())?;
            node_dict.set_item("fqn", node.fqn)?;
            node_dict.set_item("file_path", node.file_path)?;
            node_dict.set_item("language", node.language)?;

            let span_dict = PyDict::new(py);
            span_dict.set_item("start_line", node.span.start_line)?;
            span_dict.set_item("start_col", node.span.start_col)?;
            span_dict.set_item("end_line", node.span.end_line)?;
            span_dict.set_item("end_col", node.span.end_col)?;
            node_dict.set_item("span", span_dict)?;

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

        // Edges
        let py_edges = PyList::empty(py);
        for edge in result.edges {
            let edge_dict = PyDict::new(py);
            // Generate edge ID from source and target
            let edge_id = format!("{}→{}", edge.source_id, edge.target_id);
            edge_dict.set_item("id", edge_id)?;
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

        // BFG graphs
        let py_bfg_graphs = PyList::empty(py);
        for bfg in result.bfg_graphs {
            let bfg_dict = PyDict::new(py);
            bfg_dict.set_item("id", bfg.id)?;
            bfg_dict.set_item("function_id", bfg.function_id)?;
            bfg_dict.set_item("entry_block_id", bfg.entry_block_id)?;
            bfg_dict.set_item("exit_block_id", bfg.exit_block_id)?;
            bfg_dict.set_item("total_statements", bfg.total_statements)?;

            let py_blocks = PyList::empty(py);
            for block in bfg.blocks {
                let block_dict = PyDict::new(py);
                block_dict.set_item("id", block.id)?;
                block_dict.set_item("kind", block.kind)?;
                block_dict.set_item("statement_count", block.statement_count)?;

                let span_dict = PyDict::new(py);
                span_dict.set_item("start_line", block.span_ref.span.start_line)?;
                span_dict.set_item("start_col", block.span_ref.span.start_col)?;
                span_dict.set_item("end_line", block.span_ref.span.end_line)?;
                span_dict.set_item("end_col", block.span_ref.span.end_col)?;
                block_dict.set_item("span", span_dict)?;

                py_blocks.append(block_dict)?;
            }
            bfg_dict.set_item("blocks", py_blocks)?;

            py_bfg_graphs.append(bfg_dict)?;
        }
        result_dict.set_item("bfg_graphs", py_bfg_graphs)?;

        // CFG edges
        let py_cfg_edges = PyList::empty(py);
        for cfg_edge in result.cfg_edges {
            let edge_dict = PyDict::new(py);
            edge_dict.set_item("source_block_id", cfg_edge.source_block_id)?;
            edge_dict.set_item("target_block_id", cfg_edge.target_block_id)?;
            edge_dict.set_item("edge_type", cfg_edge.edge_type.as_str())?;
            py_cfg_edges.append(edge_dict)?;
        }
        result_dict.set_item("cfg_edges", py_cfg_edges)?;

        // Type entities
        let py_type_entities = PyList::empty(py);
        for type_entity in result.type_entities {
            let type_dict = PyDict::new(py);
            type_dict.set_item("id", type_entity.id)?;
            type_dict.set_item("raw", type_entity.raw)?;
            type_dict.set_item("flavor", type_entity.flavor.as_str())?;
            type_dict.set_item("is_nullable", type_entity.is_nullable)?;
            type_dict.set_item("resolution_level", type_entity.resolution_level.as_str())?;

            if let Some(resolved_target) = type_entity.resolved_target {
                type_dict.set_item("resolved_target", resolved_target)?;
            }

            if !type_entity.generic_param_ids.is_empty() {
                let py_generic_params = PyList::empty(py);
                for param_id in type_entity.generic_param_ids {
                    py_generic_params.append(param_id)?;
                }
                type_dict.set_item("generic_param_ids", py_generic_params)?;
            }

            py_type_entities.append(type_dict)?;
        }
        result_dict.set_item("type_entities", py_type_entities)?;

        // DFG graphs
        let py_dfg_graphs = PyList::empty(py);
        for dfg in result.dfg_graphs {
            let dfg_dict = PyDict::new(py);
            dfg_dict.set_item("function_id", dfg.function_id)?;
            dfg_dict.set_item("node_count", dfg.nodes.len())?;
            dfg_dict.set_item("edge_count", dfg.def_use_edges.len())?;
            py_dfg_graphs.append(dfg_dict)?;
        }
        result_dict.set_item("dfg_graphs", py_dfg_graphs)?;

        // SSA graphs
        let py_ssa_graphs = PyList::empty(py);
        for ssa in result.ssa_graphs {
            let ssa_dict = PyDict::new(py);
            ssa_dict.set_item("function_id", ssa.function_id)?;
            ssa_dict.set_item("variable_count", ssa.variables.len())?;
            ssa_dict.set_item("phi_node_count", ssa.phi_nodes.len())?;
            py_ssa_graphs.append(ssa_dict)?;
        }
        result_dict.set_item("ssa_graphs", py_ssa_graphs)?;

        // L6: PDG graphs
        let py_pdg_graphs = PyList::empty(py);
        for pdg in result.pdg_graphs {
            let pdg_dict = PyDict::new(py);
            pdg_dict.set_item("function_id", pdg.function_id)?;
            pdg_dict.set_item("node_count", pdg.node_count)?;
            pdg_dict.set_item("control_edges", pdg.control_edges)?;
            pdg_dict.set_item("data_edges", pdg.data_edges)?;
            py_pdg_graphs.append(pdg_dict)?;
        }
        result_dict.set_item("pdg_graphs", py_pdg_graphs)?;

        // L6: Taint results
        let py_taint_results = PyList::empty(py);
        for taint in result.taint_results {
            let taint_dict = PyDict::new(py);
            taint_dict.set_item("function_id", taint.function_id)?;
            taint_dict.set_item("sources_found", taint.sources_found)?;
            taint_dict.set_item("sinks_found", taint.sinks_found)?;
            taint_dict.set_item("taint_flows", taint.taint_flows)?;
            py_taint_results.append(taint_dict)?;
        }
        result_dict.set_item("taint_results", py_taint_results)?;

        // L6: Slice results
        let py_slice_results = PyList::empty(py);
        for slice in result.slice_results {
            let slice_dict = PyDict::new(py);
            slice_dict.set_item("function_id", slice.function_id)?;
            slice_dict.set_item("criterion", slice.criterion)?;
            slice_dict.set_item("slice_size", slice.slice_size)?;
            py_slice_results.append(slice_dict)?;
        }
        result_dict.set_item("slice_results", py_slice_results)?;

        // L7: Memory Safety Issues
        let py_memory_issues = PyList::empty(py);
        for issue in result.memory_safety_issues {
            let issue_dict = PyDict::new(py);
            issue_dict.set_item("kind", format!("{:?}", issue.kind))?;
            issue_dict.set_item("variable", issue.variable)?;
            issue_dict.set_item("location", issue.location)?;
            issue_dict.set_item("message", issue.message)?;
            issue_dict.set_item("severity", issue.severity)?;
            py_memory_issues.append(issue_dict)?;
        }
        result_dict.set_item("memory_safety_issues", py_memory_issues)?;

        // L7: Security Vulnerabilities
        let py_security_vulns = PyList::empty(py);
        for vuln in result.security_vulnerabilities {
            let vuln_dict = PyDict::new(py);
            vuln_dict.set_item("category", format!("{:?}", vuln.category))?;
            vuln_dict.set_item("vuln_type", format!("{:?}", vuln.vuln_type))?;
            vuln_dict.set_item("severity", vuln.severity)?;
            vuln_dict.set_item("location", vuln.location)?;
            vuln_dict.set_item("message", vuln.message)?;
            vuln_dict.set_item("recommendation", vuln.recommendation)?;
            if let Some(cwe) = vuln.cwe_id {
                vuln_dict.set_item("cwe_id", cwe)?;
            }
            if let Some(ref path) = vuln.taint_path {
                vuln_dict.set_item("taint_path", path.clone())?;
            }
            py_security_vulns.append(vuln_dict)?;
        }
        result_dict.set_item("security_vulnerabilities", py_security_vulns)?;

        // 🚀 SOTA: Occurrences generated in Rust L1 (instead of Python L2)
        let py_occurrences = PyList::empty(py);
        for occ in result.occurrences {
            let occ_dict = PyDict::new(py);
            occ_dict.set_item("id", occ.id)?;
            occ_dict.set_item("symbol_id", occ.symbol_id)?;
            occ_dict.set_item("roles", occ.roles)?;
            occ_dict.set_item("file_path", occ.file_path)?;
            occ_dict.set_item("importance_score", occ.importance_score)?;

            let span_dict = PyDict::new(py);
            span_dict.set_item("start_line", occ.span.start_line)?;
            span_dict.set_item("start_col", occ.span.start_col)?;
            span_dict.set_item("end_line", occ.span.end_line)?;
            span_dict.set_item("end_col", occ.span.end_col)?;
            occ_dict.set_item("span", span_dict)?;

            if let Some(parent) = occ.parent_symbol_id {
                occ_dict.set_item("parent_symbol_id", parent)?;
            }
            if let Some(syntax) = occ.syntax_kind {
                occ_dict.set_item("syntax_kind", syntax)?;
            }

            py_occurrences.append(occ_dict)?;
        }
        result_dict.set_item("occurrences", py_occurrences)?;

        py_results.append(result_dict)?;
    }

    Ok(py_results.into())
}

// ═══════════════════════════════════════════════════════════════════════════
// RFC-RUST-ENGINE Phase 2: Projection API Functions
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "python")]
use features::indexing::adapters::projection_dict;
#[cfg(feature = "python")]
use features::indexing::adapters::py_writer::PyPayloadWriter;

#[cfg(feature = "python")]
#[pyfunction]
fn rfc_get_file_summary(
    py: Python,
    payload: Vec<u8>,
    layout_bytes: Vec<u8>,
    index_bytes: Vec<u8>,
    file_path: String,
) -> PyResult<PyObject> {
    projection_dict::get_file_summary_dict(py, payload, layout_bytes, index_bytes, file_path)
}

#[cfg(feature = "python")]
#[pyfunction]
fn rfc_iterate_nodes(
    py: Python,
    payload: Vec<u8>,
    layout_bytes: Vec<u8>,
    index_bytes: Vec<u8>,
    file_id: u32,
    fields: Option<Vec<String>>,
) -> PyResult<PyObject> {
    projection_dict::iterate_file_nodes_dict(
        py,
        payload,
        layout_bytes,
        index_bytes,
        file_id,
        fields,
    )
}

#[cfg(feature = "python")]
#[pyfunction]
fn rfc_get_import_edges(
    py: Python,
    payload: Vec<u8>,
    layout_bytes: Vec<u8>,
    index_bytes: Vec<u8>,
    file_id: u32,
) -> PyResult<PyObject> {
    projection_dict::get_import_edges_dict(py, payload, layout_bytes, index_bytes, file_id)
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase 3: Msgpack API (Zero-Copy Performance)
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "python")]
use pyo3::types::PyBytes;

/// IR-only result for msgpack serialization
#[derive(serde::Serialize)]
struct IRResult {
    file_index: usize,
    success: bool,
    errors: Vec<String>,
    nodes: Vec<crate::shared::models::Node>,
    edges: Vec<crate::shared::models::Edge>,
    /// 🚀 SOTA: Occurrences included in msgpack (no PyDict overhead)
    occurrences: Vec<shared::models::Occurrence>,
}

/// Process Python files and return msgpack bytes (FAST)
///
/// Returns msgpack-serialized results instead of PyDict.
/// ~10x faster than process_python_files for large batches.
///
/// Python usage:
/// ```python
/// import msgpack
/// raw = codegraph_ir.process_python_files_msgpack(files, repo_id)
/// results = msgpack.unpackb(raw)
/// ```
#[cfg(feature = "python")]
#[pyfunction]
fn process_python_files_msgpack<'py>(
    py: Python<'py>,
    files: &PyList,
    repo_id: String,
) -> PyResult<&'py PyBytes> {
    init_rayon();

    // Extract file data from Python (GIL held)
    let mut file_data = Vec::with_capacity(files.len());
    for item in files.iter() {
        let tuple = item.downcast::<pyo3::types::PyTuple>()?;
        let file_path = tuple.get_item(0)?.extract::<String>()?;
        let content = tuple.get_item(1)?.extract::<String>()?;
        let module_path = tuple.get_item(2)?.extract::<String>()?;
        file_data.push((file_path, content, module_path));
    }

    // GIL RELEASE - Process in parallel with Rayon
    let results: Vec<ProcessResult> = py.allow_threads(|| {
        file_data
            .par_iter()
            .map(|(file_path, content, module_path)| {
                process_python_file(content, &repo_id, file_path, module_path)
            })
            .collect()
    });

    // Convert to IR-only results and serialize with msgpack (GIL released)
    // 🚀 SOTA: Include occurrences in msgpack (no PyDict overhead)
    let ir_results: Vec<IRResult> = results
        .into_iter()
        .enumerate()
        .map(|(i, r)| IRResult {
            file_index: i,
            success: r.errors.is_empty(),
            errors: r.errors,
            nodes: r.nodes,
            edges: r.edges,
            occurrences: r.occurrences,
        })
        .collect();

    // Serialize to msgpack (named fields for Python dict compatibility)
    let bytes = rmp_serde::to_vec_named(&ir_results).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "msgpack serialization failed: {}",
            e
        ))
    })?;

    Ok(PyBytes::new(py, &bytes))
}

// ═══════════════════════════════════════════════════════════════════════════
// RFC-062: Cross-File Resolution API (12x faster)
// ═══════════════════════════════════════════════════════════════════════════

use features::cross_file::{
    build_global_context, update_global_context, GlobalContextResult,
    IRDocument as CrossFileIRDocument,
};

/// Build global context from msgpack-serialized IR documents (RFC-062 Zero-Copy)
///
/// High-performance cross-file resolution with zero-copy msgpack interface:
/// - Input: Vec<u8> msgpack-serialized IR documents
/// - Output: Vec<u8> msgpack-serialized GlobalContextResult
///
/// This eliminates 96% Python ↔ Rust conversion overhead.
///
/// Performance: ~3.8M symbols/sec on M1 MacBook Pro (vs 150K with PyDict)
#[cfg(feature = "python")]
#[pyfunction]
fn build_global_context_msgpack(py: Python, msgpack_data: Vec<u8>) -> PyResult<Vec<u8>> {
    use std::time::Instant;
    init_rayon();

    let total_start = Instant::now();

    // Deserialize IR documents from msgpack
    let deserialize_start = Instant::now();
    let rust_irs: Vec<CrossFileIRDocument> = py
        .allow_threads(|| {
            rmp_serde::from_slice(&msgpack_data)
                .map_err(|e| format!("Failed to deserialize msgpack: {}", e))
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;
    let deserialize_time = deserialize_start.elapsed();

    // GIL RELEASE - Process in parallel with Rayon
    let process_start = Instant::now();
    let result: GlobalContextResult = py.allow_threads(|| build_global_context(rust_irs));
    let process_time = process_start.elapsed();

    // Serialize result to msgpack
    let serialize_start = Instant::now();
    let msgpack_result = py
        .allow_threads(|| {
            rmp_serde::to_vec(&result).map_err(|e| format!("Failed to serialize result: {}", e))
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;
    let serialize_time = serialize_start.elapsed();

    let total_time = total_start.elapsed();

    // PROFILING
    eprintln!(
        "[MSGPACK PROFILE] Total: {:.2}ms",
        total_time.as_secs_f64() * 1000.0
    );
    eprintln!(
        "  ├─ Deserialize msgpack: {:.2}ms ({:.1}%)",
        deserialize_time.as_secs_f64() * 1000.0,
        deserialize_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );
    eprintln!(
        "  ├─ Process (Rust): {:.2}ms ({:.1}%)",
        process_time.as_secs_f64() * 1000.0,
        process_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );
    eprintln!(
        "  └─ Serialize msgpack: {:.2}ms ({:.1}%)",
        serialize_time.as_secs_f64() * 1000.0,
        serialize_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );

    Ok(msgpack_result)
}

/// Build global context from Apache Arrow IPC (RFC-062 Zero-Copy)
///
/// SOTA zero-copy cross-file resolution using Apache Arrow columnar format:
/// - Input: Arrow IPC stream bytes + file_paths dictionary
/// - Output: Arrow IPC stream bytes
///
/// Performance: ~10x faster than PyDict, ~3x faster than msgpack
/// - Zero-copy columnar data access
/// - File path deduplication
/// - Compact binary format (38% of msgpack size)
#[cfg(feature = "python")]
#[pyfunction]
fn build_global_context_arrow(
    py: Python,
    arrow_bytes: Vec<u8>,
    file_paths: Vec<String>,
) -> PyResult<Vec<u8>> {
    use arrow::array::*;
    use arrow::ipc::reader::StreamReader;
    use std::io::Cursor;
    use std::time::Instant;

    init_rayon();

    let total_start = Instant::now();

    // Deserialize Arrow IPC (zero-copy!)
    let deserialize_start = Instant::now();
    let rust_irs: Vec<CrossFileIRDocument> = py
        .allow_threads(|| {
            let cursor = Cursor::new(&arrow_bytes);
            let reader = StreamReader::try_new(cursor, None)
                .map_err(|e| format!("Failed to read Arrow IPC: {}", e))?;

            let mut ir_docs_map: std::collections::HashMap<u16, CrossFileIRDocument> =
                std::collections::HashMap::new();

            // Read all batches
            for batch_result in reader {
                let batch = batch_result.map_err(|e| format!("Failed to read batch: {}", e))?;

                // Zero-copy column access
                let ids = batch
                    .column(0)
                    .as_any()
                    .downcast_ref::<StringArray>()
                    .ok_or("Invalid id column")?;
                let fqns = batch
                    .column(1)
                    .as_any()
                    .downcast_ref::<StringArray>()
                    .ok_or("Invalid fqn column")?;
                let _names = batch
                    .column(2)
                    .as_any()
                    .downcast_ref::<StringArray>()
                    .ok_or("Invalid name column")?;
                let kinds = batch
                    .column(3)
                    .as_any()
                    .downcast_ref::<UInt8Array>()
                    .ok_or("Invalid kind column")?;
                let file_ids = batch
                    .column(4)
                    .as_any()
                    .downcast_ref::<UInt16Array>()
                    .ok_or("Invalid file_id column")?;
                let _languages = batch
                    .column(5)
                    .as_any()
                    .downcast_ref::<UInt8Array>()
                    .ok_or("Invalid language column")?;
                let start_lines = batch
                    .column(6)
                    .as_any()
                    .downcast_ref::<UInt32Array>()
                    .ok_or("Invalid start_line column")?;
                let start_cols = batch
                    .column(7)
                    .as_any()
                    .downcast_ref::<UInt16Array>()
                    .ok_or("Invalid start_col column")?;
                let end_lines = batch
                    .column(8)
                    .as_any()
                    .downcast_ref::<UInt32Array>()
                    .ok_or("Invalid end_line column")?;
                let end_cols = batch
                    .column(9)
                    .as_any()
                    .downcast_ref::<UInt16Array>()
                    .ok_or("Invalid end_col column")?;

                // Process each row
                for i in 0..batch.num_rows() {
                    let file_id = file_ids.value(i);
                    let file_path = file_paths
                        .get(file_id as usize)
                        .ok_or("Invalid file_id")?
                        .clone();

                    // Create node
                    let kind = match kinds.value(i) {
                        0 => shared::models::NodeKind::File,
                        1 => shared::models::NodeKind::Module,
                        2 => shared::models::NodeKind::Class,
                        3 => shared::models::NodeKind::Function,
                        4 => shared::models::NodeKind::Method,
                        5 => shared::models::NodeKind::Variable,
                        6 => shared::models::NodeKind::Parameter,
                        7 => shared::models::NodeKind::Field,
                        8 => shared::models::NodeKind::Lambda,
                        9 => shared::models::NodeKind::Import,
                        _ => shared::models::NodeKind::Variable,
                    };

                    let node = shared::models::Node::new(
                        ids.value(i).to_string(),
                        kind,
                        fqns.value(i).to_string(),
                        file_path.clone(),
                        shared::models::Span::new(
                            start_lines.value(i),
                            start_cols.value(i) as u32,
                            end_lines.value(i),
                            end_cols.value(i) as u32,
                        ),
                    );

                    // Add to IR document
                    ir_docs_map
                        .entry(file_id)
                        .or_insert_with(|| {
                            CrossFileIRDocument::new(file_path.clone(), vec![], vec![])
                        })
                        .nodes
                        .push(node);
                }
            }

            // Convert to Vec
            let mut rust_irs: Vec<_> = ir_docs_map.into_iter().map(|(_, doc)| doc).collect();
            rust_irs.sort_by(|a, b| a.file_path.cmp(&b.file_path));

            Ok::<_, String>(rust_irs)
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;

    let deserialize_time = deserialize_start.elapsed();

    // GIL RELEASE - Process in parallel with Rayon
    let process_start = Instant::now();
    let result: GlobalContextResult = py.allow_threads(|| build_global_context(rust_irs));
    let process_time = process_start.elapsed();

    // Serialize result to msgpack (for now - can be Arrow later)
    let serialize_start = Instant::now();
    let result_bytes = py
        .allow_threads(|| {
            rmp_serde::to_vec(&result).map_err(|e| format!("Failed to serialize result: {}", e))
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;
    let serialize_time = serialize_start.elapsed();

    let total_time = total_start.elapsed();

    // PROFILING
    eprintln!(
        "[ARROW PROFILE] Total: {:.2}ms",
        total_time.as_secs_f64() * 1000.0
    );
    eprintln!(
        "  ├─ Deserialize Arrow IPC: {:.2}ms ({:.1}%)",
        deserialize_time.as_secs_f64() * 1000.0,
        deserialize_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );
    eprintln!(
        "  ├─ Process (Rust): {:.2}ms ({:.1}%)",
        process_time.as_secs_f64() * 1000.0,
        process_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );
    eprintln!(
        "  └─ Serialize result: {:.2}ms ({:.1}%)",
        serialize_time.as_secs_f64() * 1000.0,
        serialize_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );

    Ok(result_bytes)
}

/// Build global context from IR documents (RFC-062)
///
/// High-performance cross-file resolution using:
/// - DashMap for lock-free symbol index
/// - Rayon for parallel processing
/// - petgraph for dependency graph
///
/// Returns GlobalContextResult with:
/// - symbol_table: FQN → Symbol
/// - file_dependencies: file → dependencies
/// - file_dependents: file → dependents
/// - topological_order: files in topological order
/// - build_duration_ms: processing time
///
/// SOTA: Zero-overhead Python→Rust transfer using PyO3 #[pyclass]
///
/// Performance: Python creates Rust objects directly (no dict conversion)
/// Expected throughput: ~1.1M symbols/sec (vs 145K with old PyDict API)
#[cfg(feature = "python")]
#[pyfunction]
fn build_global_context_py(py: Python, ir_docs: Vec<CrossFileIRDocument>) -> PyResult<Py<PyDict>> {
    init_rayon();

    // PROFILING: Start timing
    let total_start = std::time::Instant::now();

    // GIL RELEASE - Process in parallel with Rayon
    let process_start = std::time::Instant::now();
    let result: GlobalContextResult = py.allow_threads(|| build_global_context(ir_docs));
    let process_time = process_start.elapsed();

    // Convert result to Python dict
    let convert_start = std::time::Instant::now();
    let py_result = convert_global_context_to_python(py, result)?;
    let convert_time = convert_start.elapsed();
    let total_time = total_start.elapsed();

    // PROFILING: Print timing breakdown (SOTA: no extract overhead!)
    eprintln!(
        "[RFC-062 SOTA] Total: {:.2}ms",
        total_time.as_secs_f64() * 1000.0
    );
    eprintln!(
        "  ├─ Process (Rust): {:.2}ms ({:.1}%)",
        process_time.as_secs_f64() * 1000.0,
        process_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );
    eprintln!(
        "  └─ Convert Rust→Python: {:.2}ms ({:.1}%)",
        convert_time.as_secs_f64() * 1000.0,
        convert_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );

    Ok(py_result)
}

/// Extract Node from Python dict
#[cfg(feature = "python")]
fn extract_node_from_dict(dict: &PyDict) -> PyResult<shared::models::Node> {
    let id: String = dict
        .get_item("id")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("id"))?
        .extract()?;

    let kind_str: String = dict
        .get_item("kind")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("kind"))?
        .extract()?;

    let kind = match kind_str.as_str() {
        "file" => shared::models::NodeKind::File,
        "module" => shared::models::NodeKind::Module,
        "class" => shared::models::NodeKind::Class,
        "function" => shared::models::NodeKind::Function,
        "method" => shared::models::NodeKind::Method,
        "variable" => shared::models::NodeKind::Variable,
        "parameter" => shared::models::NodeKind::Parameter,
        "field" => shared::models::NodeKind::Field,
        "lambda" => shared::models::NodeKind::Lambda,
        "import" => shared::models::NodeKind::Import,
        _ => shared::models::NodeKind::Variable,
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

    let mut node = shared::models::Node::new(id, kind, fqn, file_path, span);
    if let Some(n) = name {
        node = node.with_name(n);
    }

    Ok(node)
}

/// Extract Span from Python dict
#[cfg(feature = "python")]
fn extract_span_from_dict(dict: &PyDict) -> PyResult<shared::models::Span> {
    let span_dict = dict
        .get_item("span")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("span"))?
        .downcast::<PyDict>()?;

    let start_line: u32 = span_dict
        .get_item("start_line")?
        .map(|v| v.extract().unwrap_or(1))
        .unwrap_or(1);
    let start_col: u32 = span_dict
        .get_item("start_col")?
        .map(|v| v.extract().unwrap_or(0))
        .unwrap_or(0);
    let end_line: u32 = span_dict
        .get_item("end_line")?
        .map(|v| v.extract().unwrap_or(1))
        .unwrap_or(1);
    let end_col: u32 = span_dict
        .get_item("end_col")?
        .map(|v| v.extract().unwrap_or(0))
        .unwrap_or(0);

    Ok(shared::models::Span::new(
        start_line, start_col, end_line, end_col,
    ))
}

/// Extract Edge from Python dict
#[cfg(feature = "python")]
fn extract_edge_from_dict(dict: &PyDict) -> PyResult<shared::models::Edge> {
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

    let kind = match kind_str.as_str() {
        "CONTAINS" => shared::models::EdgeKind::Contains,
        "CALLS" => shared::models::EdgeKind::Calls,
        "READS" => shared::models::EdgeKind::Reads,
        "WRITES" => shared::models::EdgeKind::Writes,
        "INHERITS" => shared::models::EdgeKind::Inherits,
        "IMPORTS" => shared::models::EdgeKind::Imports,
        "REFERENCES" => shared::models::EdgeKind::References,
        "DEFINES" => shared::models::EdgeKind::Defines,
        _ => shared::models::EdgeKind::References,
    };

    Ok(shared::models::Edge::new(source_id, target_id, kind))
}

/// Convert GlobalContextResult to Python dict
///
/// SOTA Optimizations:
/// - Pre-allocated PyList with PyList::new() instead of append loop
/// - Reduced dictionary key lookups
#[cfg(feature = "python")]
fn convert_global_context_to_python(
    py: Python,
    result: GlobalContextResult,
) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);

    // Basic stats
    dict.set_item("total_symbols", result.total_symbols)?;
    dict.set_item("total_files", result.total_files)?;
    dict.set_item("total_imports", result.total_imports)?;
    dict.set_item("total_dependencies", result.total_dependencies)?;
    dict.set_item("build_duration_ms", result.build_duration_ms)?;

    // Symbol table (FQN → Symbol dict)
    let symbol_table_start = std::time::Instant::now();
    let py_symbol_table = PyDict::new(py);
    for (fqn, symbol) in result.symbol_table {
        let symbol_dict = PyDict::new(py);
        symbol_dict.set_item("fqn", &symbol.fqn)?;
        symbol_dict.set_item("name", &symbol.name)?;
        symbol_dict.set_item("kind", symbol.kind.as_str())?;
        symbol_dict.set_item("file_path", &symbol.file_path)?;
        symbol_dict.set_item("node_id", &symbol.node_id)?;

        let span_dict = PyDict::new(py);
        span_dict.set_item("start_line", symbol.span.start_line)?;
        span_dict.set_item("start_col", symbol.span.start_col)?;
        span_dict.set_item("end_line", symbol.span.end_line)?;
        span_dict.set_item("end_col", symbol.span.end_col)?;
        symbol_dict.set_item("span", span_dict)?;

        py_symbol_table.set_item(fqn, symbol_dict)?;
    }
    dict.set_item("symbol_table", py_symbol_table)?;
    let symbol_table_time = symbol_table_start.elapsed();

    // SOTA: File dependencies - use PyList::new with pre-collected Vec
    let deps_start = std::time::Instant::now();
    let py_deps = PyDict::new(py);
    for (file, deps) in result.file_dependencies {
        // Pre-allocate list with known size
        let py_dep_list = PyList::new(py, deps.iter().map(|s| s.as_str()));
        py_deps.set_item(file, py_dep_list)?;
    }
    dict.set_item("file_dependencies", py_deps)?;

    // SOTA: File dependents - use PyList::new with pre-collected Vec
    let py_dependents = PyDict::new(py);
    for (file, deps) in result.file_dependents {
        let py_dep_list = PyList::new(py, deps.iter().map(|s| s.as_str()));
        py_dependents.set_item(file, py_dep_list)?;
    }
    dict.set_item("file_dependents", py_dependents)?;

    // SOTA: Topological order - use PyList::new
    let py_topo = PyList::new(py, result.topological_order.iter().map(|s| s.as_str()));
    dict.set_item("topological_order", py_topo)?;
    let deps_time = deps_start.elapsed();

    // SOTA Priority 3: Symbol-level dependency graph stats
    if let Some(stats) = result.symbol_graph_stats {
        let stats_dict = PyDict::new(py);
        stats_dict.set_item("total_symbols", stats.total_symbols)?;
        stats_dict.set_item("total_edges", stats.total_edges)?;

        // edges_by_kind: HashMap<SymbolEdgeKind, usize>
        let edges_by_kind_dict = PyDict::new(py);
        for (edge_kind, count) in stats.edges_by_kind {
            let kind_str = match edge_kind {
                features::cross_file::SymbolEdgeKind::Calls => "Calls",
                features::cross_file::SymbolEdgeKind::CalledBy => "CalledBy",
                features::cross_file::SymbolEdgeKind::Overrides => "Overrides",
                features::cross_file::SymbolEdgeKind::Inherits => "Inherits",
                features::cross_file::SymbolEdgeKind::Implements => "Implements",
                features::cross_file::SymbolEdgeKind::Reads => "Reads",
                features::cross_file::SymbolEdgeKind::Writes => "Writes",
                features::cross_file::SymbolEdgeKind::Imports => "Imports",
                features::cross_file::SymbolEdgeKind::Exports => "Exports",
                features::cross_file::SymbolEdgeKind::InstanceOf => "InstanceOf",
                features::cross_file::SymbolEdgeKind::Returns => "Returns",
            };
            edges_by_kind_dict.set_item(kind_str, count)?;
        }
        stats_dict.set_item("edges_by_kind", edges_by_kind_dict)?;

        dict.set_item("symbol_graph_stats", stats_dict)?;
    }

    // PROFILING: Detailed conversion breakdown
    eprintln!("    [Convert Detail]");
    eprintln!(
        "      ├─ Symbol table: {:.2}ms",
        symbol_table_time.as_secs_f64() * 1000.0
    );
    eprintln!(
        "      └─ Dependencies: {:.2}ms",
        deps_time.as_secs_f64() * 1000.0
    );

    Ok(dict.into())
}

/// Incremental update of global context (RFC-062)
///
/// Re-processes only changed files and their transitive dependents.
/// Much faster than full rebuild when only a few files changed.
///
/// Arguments:
/// - existing_context: Previous GlobalContextResult (as Python dict)
/// - changed_ir_docs: List of changed IR documents
/// - all_ir_docs: All IR documents (including unchanged)
///
/// Returns: (new_context, affected_files)
#[cfg(feature = "python")]
#[pyfunction]
fn update_global_context_py(
    py: Python,
    existing_context: &PyDict,
    changed_ir_docs: &PyList,
    all_ir_docs: &PyList,
) -> PyResult<Py<PyTuple>> {
    init_rayon();

    // Extract existing context
    let existing_deps: HashMap<String, Vec<String>> = existing_context
        .get_item("file_dependents")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("file_dependents"))?
        .downcast::<PyDict>()?
        .iter()
        .map(|(k, v)| {
            let key: String = k.extract().unwrap();
            let val: Vec<String> = v.downcast::<PyList>().unwrap().extract().unwrap();
            (key, val)
        })
        .collect();

    // Create minimal GlobalContextResult for existing context
    let existing_result = GlobalContextResult {
        total_symbols: 0,
        total_files: 0,
        total_imports: 0,
        total_dependencies: 0,
        symbol_table: HashMap::new(),
        file_dependencies: HashMap::new(),
        file_dependents: existing_deps,
        topological_order: vec![],
        build_duration_ms: 0,
        symbol_graph_stats: None,
    };

    // Extract changed IR documents
    let mut rust_changed_irs = Vec::with_capacity(changed_ir_docs.len());
    for item in changed_ir_docs.iter() {
        let dict = item.downcast::<PyDict>()?;
        let file_path: String = dict
            .get_item("file_path")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("file_path"))?
            .extract()?;

        let nodes_list: &PyList = dict
            .get_item("nodes")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("nodes"))?
            .downcast()?;
        let mut nodes = Vec::with_capacity(nodes_list.len());
        for node_obj in nodes_list.iter() {
            let node_dict = node_obj.downcast::<PyDict>()?;
            let node = extract_node_from_dict(node_dict)?;
            nodes.push(node);
        }

        let edges_list: &PyList = dict
            .get_item("edges")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("edges"))?
            .downcast()?;
        let mut edges = Vec::with_capacity(edges_list.len());
        for edge_obj in edges_list.iter() {
            let edge_dict = edge_obj.downcast::<PyDict>()?;
            let edge = extract_edge_from_dict(edge_dict)?;
            edges.push(edge);
        }

        rust_changed_irs.push(CrossFileIRDocument::new(file_path, nodes, edges));
    }

    // Extract all IR documents
    let mut rust_all_irs = Vec::with_capacity(all_ir_docs.len());
    for item in all_ir_docs.iter() {
        let dict = item.downcast::<PyDict>()?;
        let file_path: String = dict
            .get_item("file_path")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("file_path"))?
            .extract()?;

        let nodes_list: &PyList = dict
            .get_item("nodes")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("nodes"))?
            .downcast()?;
        let mut nodes = Vec::with_capacity(nodes_list.len());
        for node_obj in nodes_list.iter() {
            let node_dict = node_obj.downcast::<PyDict>()?;
            let node = extract_node_from_dict(node_dict)?;
            nodes.push(node);
        }

        let edges_list: &PyList = dict
            .get_item("edges")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("edges"))?
            .downcast()?;
        let mut edges = Vec::with_capacity(edges_list.len());
        for edge_obj in edges_list.iter() {
            let edge_dict = edge_obj.downcast::<PyDict>()?;
            let edge = extract_edge_from_dict(edge_dict)?;
            edges.push(edge);
        }

        rust_all_irs.push(CrossFileIRDocument::new(file_path, nodes, edges));
    }

    // GIL RELEASE - Process incrementally
    let (new_result, affected_files) = py
        .allow_threads(|| update_global_context(&existing_result, rust_changed_irs, rust_all_irs));

    // Convert to Python
    let py_context = convert_global_context_to_python(py, new_result)?;
    let py_affected = PyList::new(py, affected_files.iter().map(|s| s.as_str()));

    // Return tuple (new_context, affected_files)
    // Cast both to &PyAny for homogeneous tuple
    let tuple_items: Vec<&PyAny> = vec![py_context.as_ref(py), py_affected];
    let tuple = PyTuple::new(py, &tuple_items);
    Ok(tuple.into())
}

// ═══════════════════════════════════════════════════════════════════════════
// SOTA Priority 3: Symbol-level Dependency Graph API
// ═══════════════════════════════════════════════════════════════════════════

/// Get symbols that this symbol depends on (RFC-062 Priority 3)
///
/// Returns list of FQNs this symbol depends on, optionally filtered by edge kind.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the symbol to analyze
/// - edge_kind: Optional edge kind filter (e.g., "Calls", "Inherits", "Reads")
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (ir_docs, fqn, edge_kind = None))]
fn get_symbol_dependencies(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
    edge_kind: Option<String>,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Parse edge kind
    let edge_kind_enum = edge_kind.and_then(|s| parse_symbol_edge_kind(&s));

    // Get dependencies
    let deps = graph.get_dependencies(&fqn, edge_kind_enum);

    Ok(PyList::new(py, deps.iter().map(|s| s.as_str())).into())
}

/// Get symbols that depend on this symbol (reverse lookup) (RFC-062 Priority 3)
///
/// Returns list of FQNs that depend on this symbol, optionally filtered by edge kind.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the symbol to analyze
/// - edge_kind: Optional edge kind filter (e.g., "Calls", "Inherits", "Writes")
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (ir_docs, fqn, edge_kind = None))]
fn get_symbol_dependents(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
    edge_kind: Option<String>,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Parse edge kind
    let edge_kind_enum = edge_kind.and_then(|s| parse_symbol_edge_kind(&s));

    // Get dependents
    let dependents = graph.get_dependents(&fqn, edge_kind_enum);

    Ok(PyList::new(py, dependents.iter().map(|s| s.as_str())).into())
}

/// Get all transitive dependencies (closure) (RFC-062 Priority 3)
///
/// Returns all symbols transitively reachable from this symbol.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the symbol to analyze
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
fn get_transitive_dependencies(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Get transitive dependencies
    let deps = graph.get_transitive_dependencies(&fqn);

    Ok(PyList::new(py, deps.iter().map(|s| s.as_str())).into())
}

/// Get all transitive dependents (reverse closure) (RFC-062 Priority 3)
///
/// Returns all symbols that transitively depend on this symbol.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the symbol to analyze
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
fn get_transitive_dependents(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Get transitive dependents
    let dependents = graph.get_transitive_dependents(&fqn);

    Ok(PyList::new(py, dependents.iter().map(|s| s.as_str())).into())
}

/// Get functions called by this function (RFC-062 Priority 3)
///
/// Returns list of function FQNs called by this function.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the function to analyze
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
fn get_symbol_callees(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Get call graph
    let call_graph = graph.call_graph().ok_or_else(|| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Call graph not available")
    })?;

    // Get callees
    let callees = call_graph.get_callees(&fqn);

    Ok(PyList::new(py, callees.iter().map(|s| s.as_str())).into())
}

/// Get functions that call this function (RFC-062 Priority 3)
///
/// Returns list of function FQNs that call this function.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the function to analyze
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
fn get_symbol_callers(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Get call graph
    let call_graph = graph.call_graph().ok_or_else(|| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Call graph not available")
    })?;

    // Get callers
    let callers = call_graph.get_callers(&fqn);

    Ok(PyList::new(py, callers.iter().map(|s| s.as_str())).into())
}

/// Get all functions transitively called by this function (RFC-062 Priority 3)
///
/// Returns all functions reachable from this function through call chains.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the function to analyze
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
fn get_transitive_callees(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Get call graph
    let call_graph = graph.call_graph().ok_or_else(|| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Call graph not available")
    })?;

    // Get transitive callees
    let callees = call_graph.get_transitive_callees(&fqn);

    Ok(PyList::new(py, callees.iter().map(|s| s.as_str())).into())
}

/// Get all functions that can transitively reach this function (RFC-062 Priority 3)
///
/// Returns all functions that can reach this function through call chains.
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the function to analyze
///
/// Returns: List of FQNs (strings)
#[cfg(feature = "python")]
#[pyfunction]
fn get_transitive_callers(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
) -> PyResult<Py<PyList>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Get call graph
    let call_graph = graph.call_graph().ok_or_else(|| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Call graph not available")
    })?;

    // Get transitive callers
    let callers = call_graph.get_transitive_callers(&fqn);

    Ok(PyList::new(py, callers.iter().map(|s| s.as_str())).into())
}

/// Analyze impact of changing a symbol (RFC-062 Priority 3)
///
/// Computes what breaks if a symbol is changed/removed.
///
/// Returns dict with:
/// - target_fqn: Symbol being analyzed
/// - direct_dependents: List of symbols that directly depend on target
/// - transitive_dependents: List of symbols that transitively depend on target
/// - affected_files: List of file paths affected by the change
/// - risk_score: 0.0-1.0 (higher = more impact)
/// - risk_level: "Low" (0.0-0.3), "Medium" (0.3-0.7), "High" (0.7-1.0)
/// - max_call_depth: Maximum depth of call chains from this symbol
/// - impact_by_kind: Dict of edge kind → count
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqn: Fully qualified name of the symbol to analyze
///
/// Returns: Impact analysis result (dict)
#[cfg(feature = "python")]
#[pyfunction]
fn analyze_symbol_impact(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqn: String,
) -> PyResult<Py<PyDict>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    let total_symbols = graph.stats().total_symbols;

    // Compute impact
    let impact = features::cross_file::ImpactAnalysis::compute(&graph, &fqn, total_symbols)
        .ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Symbol not found: {}", fqn))
        })?;

    // Convert to Python dict
    let result = PyDict::new(py);
    result.set_item("target_fqn", &impact.target_fqn)?;

    let py_direct_deps = PyList::new(py, impact.direct_dependents.iter().map(|s| s.as_str()));
    result.set_item("direct_dependents", py_direct_deps)?;

    let py_trans_deps = PyList::new(py, impact.transitive_dependents.iter().map(|s| s.as_str()));
    result.set_item("transitive_dependents", py_trans_deps)?;

    let py_files = PyList::new(py, impact.affected_files.iter().map(|s| s.as_str()));
    result.set_item("affected_files", py_files)?;

    result.set_item("risk_score", impact.risk_score)?;

    let risk_level_str = match impact.risk_level() {
        features::cross_file::RiskLevel::Low => "Low",
        features::cross_file::RiskLevel::Medium => "Medium",
        features::cross_file::RiskLevel::High => "High",
    };
    result.set_item("risk_level", risk_level_str)?;

    result.set_item("max_call_depth", impact.max_call_depth)?;

    // impact_by_kind
    let impact_by_kind_dict = PyDict::new(py);
    for (edge_kind, count) in impact.impact_by_kind {
        let kind_str = symbol_edge_kind_to_str(edge_kind);
        impact_by_kind_dict.set_item(kind_str, count)?;
    }
    result.set_item("impact_by_kind", impact_by_kind_dict)?;

    Ok(result.into())
}

/// Batch impact analysis for multiple symbols (RFC-062 Priority 3)
///
/// Analyzes impact of changing multiple symbols at once.
///
/// Returns dict with:
/// - impacts: List of individual impact analyses
/// - total_affected_files: Combined list of affected files
/// - max_risk_score: Maximum risk score across all symbols
/// - summary: Dict with total_symbols_changed, total_dependents, total_affected_files,
///            high_risk_count, medium_risk_count, low_risk_count
///
/// Arguments:
/// - ir_docs: List of IR documents
/// - fqns: List of FQNs to analyze
///
/// Returns: Batch impact analysis result (dict)
#[cfg(feature = "python")]
#[pyfunction]
fn batch_analyze_impact(
    py: Python,
    ir_docs: Vec<CrossFileIRDocument>,
    fqns: Vec<String>,
) -> PyResult<Py<PyDict>> {
    init_rayon();

    // Build symbol graph
    let graph =
        py.allow_threads(|| features::cross_file::SymbolDependencyGraph::build_from_irs(&ir_docs));

    // Compute batch impact
    let batch = features::cross_file::BatchImpactAnalysis::compute(&graph, &fqns);

    // Convert to Python dict
    let result = PyDict::new(py);

    // impacts
    let py_impacts = PyList::empty(py);
    for impact in batch.impacts {
        let impact_dict = PyDict::new(py);
        impact_dict.set_item("target_fqn", &impact.target_fqn)?;

        let py_direct_deps = PyList::new(py, impact.direct_dependents.iter().map(|s| s.as_str()));
        impact_dict.set_item("direct_dependents", py_direct_deps)?;

        let py_trans_deps =
            PyList::new(py, impact.transitive_dependents.iter().map(|s| s.as_str()));
        impact_dict.set_item("transitive_dependents", py_trans_deps)?;

        let py_files = PyList::new(py, impact.affected_files.iter().map(|s| s.as_str()));
        impact_dict.set_item("affected_files", py_files)?;

        impact_dict.set_item("risk_score", impact.risk_score)?;

        let risk_level_str = match impact.risk_level() {
            features::cross_file::RiskLevel::Low => "Low",
            features::cross_file::RiskLevel::Medium => "Medium",
            features::cross_file::RiskLevel::High => "High",
        };
        impact_dict.set_item("risk_level", risk_level_str)?;

        impact_dict.set_item("max_call_depth", impact.max_call_depth)?;

        py_impacts.append(impact_dict)?;
    }
    result.set_item("impacts", py_impacts)?;

    // total_affected_files
    let py_total_files = PyList::new(py, batch.total_affected_files.iter().map(|s| s.as_str()));
    result.set_item("total_affected_files", py_total_files)?;

    // max_risk_score
    result.set_item("max_risk_score", batch.max_risk_score)?;

    // summary
    let summary_dict = PyDict::new(py);
    summary_dict.set_item("total_symbols_changed", batch.summary.total_symbols_changed)?;
    summary_dict.set_item("total_dependents", batch.summary.total_dependents)?;
    summary_dict.set_item("total_affected_files", batch.summary.total_affected_files)?;
    summary_dict.set_item("high_risk_count", batch.summary.high_risk_count)?;
    summary_dict.set_item("medium_risk_count", batch.summary.medium_risk_count)?;
    summary_dict.set_item("low_risk_count", batch.summary.low_risk_count)?;
    result.set_item("summary", summary_dict)?;

    Ok(result.into())
}

/// Helper: Parse edge kind string to enum
fn parse_symbol_edge_kind(s: &str) -> Option<features::cross_file::SymbolEdgeKind> {
    match s {
        "Calls" => Some(features::cross_file::SymbolEdgeKind::Calls),
        "CalledBy" => Some(features::cross_file::SymbolEdgeKind::CalledBy),
        "Overrides" => Some(features::cross_file::SymbolEdgeKind::Overrides),
        "Inherits" => Some(features::cross_file::SymbolEdgeKind::Inherits),
        "Implements" => Some(features::cross_file::SymbolEdgeKind::Implements),
        "Reads" => Some(features::cross_file::SymbolEdgeKind::Reads),
        "Writes" => Some(features::cross_file::SymbolEdgeKind::Writes),
        "Imports" => Some(features::cross_file::SymbolEdgeKind::Imports),
        "Exports" => Some(features::cross_file::SymbolEdgeKind::Exports),
        "InstanceOf" => Some(features::cross_file::SymbolEdgeKind::InstanceOf),
        "Returns" => Some(features::cross_file::SymbolEdgeKind::Returns),
        _ => None,
    }
}

/// Helper: Convert edge kind enum to string
fn symbol_edge_kind_to_str(kind: features::cross_file::SymbolEdgeKind) -> &'static str {
    match kind {
        features::cross_file::SymbolEdgeKind::Calls => "Calls",
        features::cross_file::SymbolEdgeKind::CalledBy => "CalledBy",
        features::cross_file::SymbolEdgeKind::Overrides => "Overrides",
        features::cross_file::SymbolEdgeKind::Inherits => "Inherits",
        features::cross_file::SymbolEdgeKind::Implements => "Implements",
        features::cross_file::SymbolEdgeKind::Reads => "Reads",
        features::cross_file::SymbolEdgeKind::Writes => "Writes",
        features::cross_file::SymbolEdgeKind::Imports => "Imports",
        features::cross_file::SymbolEdgeKind::Exports => "Exports",
        features::cross_file::SymbolEdgeKind::InstanceOf => "InstanceOf",
        features::cross_file::SymbolEdgeKind::Returns => "Returns",
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// SOTA Repository Pipeline API
// ═══════════════════════════════════════════════════════════════════════════

/// Run the SOTA IR Indexing pipeline in pure Rust
///
/// This is the main entry point for Python to trigger full repository IR indexing.
/// ALL processing happens in Rust; Python only receives the final results.
///
/// # Pipeline Stages (L1-L6)
/// - **L1**: IR Build - Parse files and generate IR (nodes, edges)
/// - **L2**: Chunking - Create searchable chunks from IR
/// - **L3**: CrossFile - Resolve imports and cross-file references
/// - **L4**: Occurrences - Generate SCIP occurrences
/// - **L5**: Symbols - Extract symbols for navigation
/// - **L6**: PointsTo - Compute alias analysis (Andersen/Steensgaard)
///
/// # Arguments
/// * `repo_root` - Root directory of the repository
/// * `repo_name` - Name of the repository
/// * `file_paths` - Optional list of file paths (for incremental mode)
/// * `enable_chunking` - Enable L2 chunking stage
/// * `enable_cross_file` - Enable L3 cross-file resolution
/// * `enable_symbols` - Enable L5 symbol extraction
/// * `enable_points_to` - Enable L6 points-to analysis
/// * `enable_repomap` - Enable L16 RepoMap repository structure visualization
/// * `parallel_workers` - Number of parallel workers (0 = auto)
///
/// # Returns
/// * Python dict with nodes, edges, chunks, symbols, occurrences, points_to_summary, and stats
///
/// # Performance
/// - GIL released during Rust processing
/// - Rayon parallel processing
/// - Achieved: 661,000+ LOC/s (8.5x improvement over target 78,000 LOC/s)
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    repo_root,
    repo_name,
    file_paths = None,
    enable_chunking = true,
    enable_cross_file = true,
    enable_symbols = true,
    enable_points_to = true,
    enable_repomap = false,
    enable_taint = false,
    use_trcr = false,
    parallel_workers = 0
))]
fn run_ir_indexing_pipeline(
    py: Python,
    repo_root: String,
    repo_name: String,
    file_paths: Option<Vec<String>>,
    enable_chunking: bool,
    enable_cross_file: bool,
    enable_symbols: bool,
    enable_points_to: bool,
    enable_repomap: bool,
    enable_taint: bool,
    use_trcr: bool,
    parallel_workers: usize,
) -> PyResult<Py<PyDict>> {
    use crate::config::{PipelineConfig, Preset, ParallelConfig as Cfg001ParallelConfig};
    use pipeline::{E2EPipelineConfig, IRIndexingOrchestrator, IndexingMode};
    use std::path::PathBuf;
    use std::time::Instant;

    init_rayon();

    let total_start = Instant::now();

    // Build RFC-001 PipelineConfig from individual flags
    let pipeline_config = PipelineConfig::preset(Preset::Balanced)
        .stages(|mut s| {
            s.parsing = true; // Always enabled
            s.chunking = enable_chunking;
            s.lexical = false;
            s.cross_file = enable_cross_file;
            s.clone = false;
            s.pta = enable_points_to;
            s.flow_graphs = false;
            s.type_inference = false;
            s.symbols = enable_symbols;
            s.effects = false;
            s.taint = enable_taint;
            s.repomap = enable_repomap;
            s.heap = enable_points_to; // Enable heap analysis when points-to is enabled
            s.pdg = false;
            s.concurrency = false;
            s.slicing = false;
            s
        })
        .parallel(|mut p| {
            p.num_workers = if parallel_workers == 0 {
                0 // Auto
            } else {
                parallel_workers
            };
            p.batch_size = 100;
            p
        })
        .build()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Configuration build failed: {}", e
        )))?;

    // Build E2E pipeline config using RFC-001 ValidatedConfig
    let config = E2EPipelineConfig::with_config(pipeline_config)
        .repo_root(PathBuf::from(&repo_root))
        .repo_name(repo_name.clone())
        .indexing_mode(IndexingMode::Full)
        .mmap_threshold(1024 * 1024);

    // Set file paths if provided
    let config = if let Some(fps) = file_paths {
        config.file_paths(fps.into_iter().map(PathBuf::from).collect())
    } else {
        config
    };

    // Execute pipeline with GIL released
    let result = py
        .allow_threads(|| {
            let orchestrator = IRIndexingOrchestrator::new(config);
            orchestrator.execute()
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.message))?;

    let process_time = total_start.elapsed();

    // Convert result to Python dict
    let convert_start = Instant::now();
    let py_result = convert_e2e_result_to_python(py, result)?;
    let convert_time = convert_start.elapsed();

    let total_time = total_start.elapsed();

    // PROFILING
    eprintln!(
        "[SOTA IR Indexing Pipeline] Total: {:.2}ms",
        total_time.as_secs_f64() * 1000.0
    );
    eprintln!(
        "  ├─ Rust Processing: {:.2}ms ({:.1}%)",
        process_time.as_secs_f64() * 1000.0,
        process_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );
    eprintln!(
        "  └─ Convert Rust→Python: {:.2}ms ({:.1}%)",
        convert_time.as_secs_f64() * 1000.0,
        convert_time.as_secs_f64() / total_time.as_secs_f64() * 100.0
    );

    Ok(py_result)
}

/// Convert E2EPipelineResult to Python dict with Rust QueryEngine
#[cfg(feature = "python")]
fn convert_e2e_result_to_python(
    py: Python,
    result: pipeline::E2EPipelineResult,
) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);

    // Create IRDocument from nodes and edges for QueryEngine
    let ir_doc = {
        let mut doc = features::ir_generation::domain::ir_document::IRDocument::new("".to_string());
        // Convert nodes from E2E result to IRDocument nodes
        for node in &result.nodes {
            doc.nodes.push(node.clone());
        }
        for edge in &result.edges {
            doc.edges.push(edge.clone());
        }
        doc
    };

    // Create Rust QueryEngine and add to result
    let query_engine = adapters::pyo3::api::rust_query_engine::PyRustQueryEngine::new(ir_doc);
    dict.set_item("query_engine", Py::new(py, query_engine)?)?;

    // Convert nodes to Python list of dicts
    let py_nodes = PyList::new(
        py,
        result.nodes.iter().map(|n| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &n.id);
            let _ = d.set_item("kind", format!("{:?}", n.kind));
            let _ = d.set_item("fqn", &n.fqn);
            let _ = d.set_item("file_path", &n.file_path);
            let _ = d.set_item("name", &n.name);

            let span_dict = PyDict::new(py);
            let _ = span_dict.set_item("start_line", n.span.start_line);
            let _ = span_dict.set_item("start_col", n.span.start_col);
            let _ = span_dict.set_item("end_line", n.span.end_line);
            let _ = span_dict.set_item("end_col", n.span.end_col);
            let _ = d.set_item("span", span_dict);
            d
        }),
    );
    dict.set_item("nodes", py_nodes)?;

    // Convert edges
    let py_edges = PyList::new(
        py,
        result.edges.iter().map(|e| {
            let d = PyDict::new(py);
            let _ = d.set_item("source_id", &e.source_id);
            let _ = d.set_item("target_id", &e.target_id);
            let _ = d.set_item("kind", format!("{:?}", e.kind));
            d
        }),
    );
    dict.set_item("edges", py_edges)?;

    // Convert chunks
    let py_chunks = PyList::new(
        py,
        result.chunks.iter().map(|c| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &c.id);
            let _ = d.set_item("file_path", &c.file_path);
            let _ = d.set_item("content", &c.content);
            let _ = d.set_item("start_line", c.start_line);
            let _ = d.set_item("end_line", c.end_line);
            let _ = d.set_item("chunk_type", &c.chunk_type);
            let _ = d.set_item("symbol_id", &c.symbol_id);
            d
        }),
    );
    dict.set_item("chunks", py_chunks)?;

    // Convert symbols
    let py_symbols = PyList::new(
        py,
        result.symbols.iter().map(|s| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &s.id);
            let _ = d.set_item("name", &s.name);
            let _ = d.set_item("kind", &s.kind);
            let _ = d.set_item("file_path", &s.file_path);
            let _ = d.set_item("definition", (s.definition.0, s.definition.1));
            let _ = d.set_item("documentation", &s.documentation);
            d
        }),
    );
    dict.set_item("symbols", py_symbols)?;

    // Convert occurrences
    let py_occurrences = PyList::new(
        py,
        result.occurrences.iter().map(|o| {
            let d = PyDict::new(py);
            let _ = d.set_item("id", &o.id);
            let _ = d.set_item("symbol_id", &o.symbol_id);
            let _ = d.set_item("file_path", &o.file_path);
            let _ = d.set_item("roles", o.roles); // Bitflags as u8
            let _ = d.set_item("importance_score", o.importance_score);

            let span_dict = PyDict::new(py);
            let _ = span_dict.set_item("start_line", o.span.start_line);
            let _ = span_dict.set_item("start_col", o.span.start_col);
            let _ = span_dict.set_item("end_line", o.span.end_line);
            let _ = span_dict.set_item("end_col", o.span.end_col);
            let _ = d.set_item("span", span_dict);
            d
        }),
    );
    dict.set_item("occurrences", py_occurrences)?;

    // Convert stats
    let py_stats = PyDict::new(py);
    py_stats.set_item("total_duration_ms", result.stats.total_duration.as_millis())?;
    py_stats.set_item("files_processed", result.stats.files_processed)?;
    py_stats.set_item("files_cached", result.stats.files_cached)?;
    py_stats.set_item("files_failed", result.stats.files_failed)?;
    py_stats.set_item("total_loc", result.stats.total_loc)?;
    py_stats.set_item("loc_per_second", result.stats.loc_per_second)?;
    py_stats.set_item("cache_hit_rate", result.stats.cache_hit_rate)?;

    // Stage durations
    let py_stage_durations = PyDict::new(py);
    for (stage, duration) in &result.stats.stage_durations {
        py_stage_durations.set_item(stage, duration.as_millis())?;
    }
    py_stats.set_item("stage_durations", py_stage_durations)?;

    // Errors
    let py_errors = PyList::new(py, result.stats.errors.iter().map(|e| e.as_str()));
    py_stats.set_item("errors", py_errors)?;

    dict.set_item("stats", py_stats)?;

    // Convert points-to analysis summary (if present)
    if let Some(ref pts) = result.points_to_summary {
        let py_pts = PyDict::new(py);
        py_pts.set_item("variables_count", pts.variables_count)?;
        py_pts.set_item("allocations_count", pts.allocations_count)?;
        py_pts.set_item("constraints_count", pts.constraints_count)?;
        py_pts.set_item("alias_pairs", pts.alias_pairs)?;
        py_pts.set_item("mode_used", &pts.mode_used)?;
        py_pts.set_item("duration_ms", pts.duration_ms)?;
        dict.set_item("points_to_summary", py_pts)?;
    } else {
        dict.set_item("points_to_summary", py.None())?;
    }

    // Convert taint analysis results
    let py_taint_results = PyList::new(
        py,
        result.taint_results.iter().map(|t| {
            let d = PyDict::new(py);
            let _ = d.set_item("function_id", &t.function_id);
            let _ = d.set_item("sources_found", t.sources_found);
            let _ = d.set_item("sinks_found", t.sinks_found);
            let _ = d.set_item("taint_flows", t.taint_flows);
            d
        }),
    );
    dict.set_item("taint_results", py_taint_results)?;

    // Convert RepoMap snapshot (if present)
    if let Some(ref snapshot) = result.repomap_snapshot {
        let py_snapshot = PyDict::new(py);
        py_snapshot.set_item("repo_id", &snapshot.repo_id)?;
        py_snapshot.set_item("snapshot_id", &snapshot.snapshot_id)?;
        py_snapshot.set_item("total_nodes", snapshot.total_nodes)?;
        py_snapshot.set_item("root_id", &snapshot.root_id)?;
        py_snapshot.set_item("total_loc", snapshot.total_loc)?;
        py_snapshot.set_item("total_symbols", snapshot.total_symbols)?;
        py_snapshot.set_item("total_files", snapshot.total_files)?;
        py_snapshot.set_item("created_at", snapshot.created_at)?;

        // Convert nodes
        let py_nodes = PyList::new(
            py,
            snapshot.nodes.iter().map(|node| {
                let d = PyDict::new(py);
                let _ = d.set_item("id", &node.id);
                let _ = d.set_item("kind", &node.kind);
                let _ = d.set_item("name", &node.name);
                let _ = d.set_item("path", &node.path);
                let _ = d.set_item("parent_id", &node.parent_id);
                let _ = d.set_item("children_count", node.children_count);
                let _ = d.set_item("depth", node.depth);
                let _ = d.set_item("pagerank", node.pagerank);
                let _ = d.set_item("authority", node.authority);
                let _ = d.set_item("hub", node.hub);
                let _ = d.set_item("combined_importance", node.combined_importance);
                let _ = d.set_item("loc", node.loc);
                let _ = d.set_item("symbol_count", node.symbol_count);
                d
            }),
        );
        py_snapshot.set_item("nodes", py_nodes)?;

        dict.set_item("repomap_snapshot", py_snapshot)?;
    } else {
        dict.set_item("repomap_snapshot", py.None())?;
    }

    Ok(dict.into())
}

// ═══════════════════════════════════════════════════════════════════════════
// Python Module Registration
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(feature = "python")]
#[pymodule]
fn codegraph_ir(_py: Python, m: &PyModule) -> PyResult<()> {
    // ═══════════════════════════════════════════════════════════════════════════
    // MINIMAL PYTHON API - E2E Pipeline + Graph Query Only
    // ═══════════════════════════════════════════════════════════════════════════

    // Core types (required for IR results)
    m.add_class::<shared::models::Span>()?;
    m.add_class::<shared::models::NodeKind>()?;
    m.add_class::<shared::models::EdgeKind>()?;
    m.add_class::<shared::models::Node>()?;
    m.add_class::<shared::models::Edge>()?;
    m.add_class::<features::cross_file::IRDocument>()?;

    // Rust QueryEngine (zero-copy, no Python indexing overhead)
    m.add_class::<adapters::pyo3::api::rust_query_engine::PyRustQueryEngine>()?;

    // ═══════════════════════════════════════════════════════════════════════════
    // 1. E2E Pipeline - Single Entry Point for All Analysis
    // ═══════════════════════════════════════════════════════════════════════════
    // Usage: result = codegraph_ir.run_ir_indexing_pipeline(repo_root, ...)
    // Returns: Complete IR with all analysis results (IR, chunks, symbols, etc.)
    m.add_function(wrap_pyfunction!(run_ir_indexing_pipeline, m)?)?;

    // ═══════════════════════════════════════════════════════════════════════════
    // Lexical Search API (RFC-072 L3 Layer)
    // TEMPORARILY DISABLED: SqliteChunkStore compilation error
    // ═══════════════════════════════════════════════════════════════════════════
    // Usage: index = codegraph_ir.LexicalIndex.new(...)
    //        index.index_files([...])
    //        hits = index.search("query")
    // adapters::pyo3::api::lexical::register_lexical_api(m)?;

    // ═══════════════════════════════════════════════════════════════════════════
    // Clone Detection API (RFC-076)
    // TEMPORARILY DISABLED: compilation errors preventing testing
    // ═══════════════════════════════════════════════════════════════════════════
    // m.add_function(wrap_pyfunction!(adapters::pyo3::api::clone_detection::detect_clones_all_py, m)?)?;
    // m.add_function(wrap_pyfunction!(adapters::pyo3::api::clone_detection::detect_clones_type1_py, m)?)?;
    // m.add_function(wrap_pyfunction!(adapters::pyo3::api::clone_detection::detect_clones_type2_py, m)?)?;
    // m.add_function(wrap_pyfunction!(adapters::pyo3::api::clone_detection::detect_clones_type3_py, m)?)?;
    // m.add_function(wrap_pyfunction!(adapters::pyo3::api::clone_detection::detect_clones_type4_py, m)?)?;
    // m.add_function(wrap_pyfunction!(adapters::pyo3::api::clone_detection::detect_clones_in_file_py, m)?)?;

    // ═══════════════════════════════════════════════════════════════════════════
    // 2. Query Results - Use Python List Comprehensions
    // ═══════════════════════════════════════════════════════════════════════════
    // The E2E pipeline returns native Python dicts, so you can query using:
    //
    //   # Find all functions
    //   functions = [n for n in result['nodes'] if n['kind'] == 'Function']
    //
    //   # Find auth-related functions
    //   auth_funcs = [n for n in result['nodes']
    //                 if n['kind'] == 'Function' and 'auth' in n['name']]
    //
    //   # Get function at specific line
    //   func = [n for n in result['nodes']
    //           if n['span']['start_line'] == 42][0]
    //
    // No need for complex Rust graph query API when Python works perfectly!
    // ═══════════════════════════════════════════════════════════════════════════

    // ═══════════════════════════════════════════════════════════════════════════
    // Taint Analysis API (Integrated into E2E Pipeline)
    // ═══════════════════════════════════════════════════════════════════════════
    // Use: run_ir_indexing_pipeline(..., enable_taint=True)
    // Result contains taint_paths in the response dict

    // ═══════════════════════════════════════════════════════════════════════════
    // Program Slicing API (SOTA: Thin Slicing, Chopping)
    // ═══════════════════════════════════════════════════════════════════════════
    // Usage:
    //   - backward_slice(pdg_data, target_node, max_depth, config)
    //   - forward_slice(pdg_data, source_node, max_depth, config)
    //   - hybrid_slice(pdg_data, focus_node, max_depth, config)
    //   - thin_slice(pdg_data, target_node, max_depth) - SOTA: Sridharan et al., PLDI 2007
    //   - chop(pdg_data, source_node, target_node, max_depth, config) - SOTA: Jackson & Rollins, FSE 1994
    // ═══════════════════════════════════════════════════════════════════════════
    adapters::pyo3::api::slice::register_slice_api(m)?;

    // ═══════════════════════════════════════════════════════════════════════════
    // RFC-001 Configuration System (Full Python Control)
    // ═══════════════════════════════════════════════════════════════════════════
    // Usage:
    //   config = PipelineConfig.preset("balanced")
    //       .with_stages(taint=True, pta=True, slicing=True)
    //       .with_taint(max_depth=100, use_points_to=True)
    //       .with_pta(mode="precise", field_sensitive=True)
    //   result = run_pipeline_with_config("/path/to/repo", "my-repo", config)
    //
    // Classes:
    //   - PipelineConfig: Main configuration (preset + stage overrides)
    //   - StageControl: Stage on/off switches
    //
    // Functions:
    //   - run_pipeline_with_config(): Config-based pipeline execution
    // ═══════════════════════════════════════════════════════════════════════════
    adapters::pyo3::api::config::register_config_api(m)?;

    // ═══════════════════════════════════════════════════════════════════════════
    // DEPRECATED APIs - Disabled (use E2E pipeline instead)
    // ═══════════════════════════════════════════════════════════════════════════
    // - process_python_files, process_files (use run_ir_indexing_pipeline)
    // - build_global_context_* (integrated into E2E pipeline)
    // - get_symbol_dependencies, analyze_symbol_impact (query result nodes/edges)
    // - quick_taint_check (use analyze_taint)
    // - IR processor, streaming, advanced taint (use E2E pipeline)
    // - PyGraphIndex, NodeFilter (use Python list comprehensions)
    // ═══════════════════════════════════════════════════════════════════════════

    Ok(())
}

// ═══════════════════════════════════════════════════════════════════════════
// E2E Pipeline API (Advanced Analysis)
// ═══════════════════════════════════════════════════════════════════════════

// ⚠️  DISABLED - Config struct fields changed
/*
/// Execute full E2E pipeline with all advanced analyses (msgpack interface)
///
/// This function executes the complete IR indexing pipeline (L1-L8) including:
/// - L1: IR Build (parse files, generate nodes/edges)
/// - L2: Chunking (create searchable chunks)
/// - L3: CrossFile (resolve imports, cross-file references)
/// - L4: Occurrences (SCIP occurrences)
/// - L5: Symbols (symbol extraction)
/// - L6: PointsTo (alias analysis)
/// - L7: CFG/DFG/SSA (control/data flow)
/// - L8: Advanced Analyses (Effect Analysis, SMT, PDG, Taint, Heap, Security)
///
/// # Arguments
/// * `files` - List of (file_path, content, module_path) tuples
/// * `repo_id` - Repository identifier
/// * `repo_root` - Repository root path (optional)
///
/// # Returns
/// msgpack-serialized E2EPipelineResult with all analysis results
#[cfg(feature = "python")]
#[pyfunction]
fn execute_e2e_pipeline_msgpack<'py>(
    py: Python<'py>,
    files: &PyList,
    repo_id: String,
    repo_root: Option<String>,
) -> PyResult<&'py PyBytes> {
    init_rayon();

    // Extract file data from Python (GIL held)
    let mut file_paths = Vec::with_capacity(files.len());
    for item in files.iter() {
        let tuple = item.downcast::<pyo3::types::PyTuple>()?;
        let file_path = tuple.get_item(0)?.extract::<String>()?;
        file_paths.push(file_path);
    }

    // Build E2E pipeline config
    let repo_info = pipeline::RepoInfo {
        repo_name: repo_id.clone(),
        repo_root: repo_root.unwrap_or_else(|| ".".to_string()).into(),
        language: "python".to_string(),
    };

    let config = pipeline::E2EPipelineConfig {
        repo_info,
        file_paths,
        parallel_config: pipeline::ParallelConfig::default(),
        stage_control: pipeline::StageControl::default(),
        cache_config: pipeline::CacheConfig::default(),
        indexing_mode: pipeline::IndexingMode::Full,
    };

    // Execute pipeline (GIL released)
    let result = py.allow_threads(|| {
        let orchestrator = pipeline::IRIndexingOrchestrator::new(config);
        orchestrator.execute()
    }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
        format!("E2E pipeline execution failed: {}", e)
    ))?;

    // Serialize to msgpack
    let bytes = rmp_serde::to_vec_named(&result)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("msgpack serialization failed: {}", e)
        ))?;

    Ok(PyBytes::new(py, &bytes))
}
*/

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_traverse_empty_content() {
        let result = traverse_ast_single("");
        assert!(result.is_ok());
    }

    #[test]
    fn test_traverse_simple_function() {
        let result = traverse_ast_single("def foo(): pass");
        assert!(result.is_ok());
        let nodes = result.unwrap();
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].kind, "function_definition");
        assert_eq!(nodes[0].name, Some("foo".to_string()));
    }

    #[test]
    fn test_process_simple_file() {
        let result = process_python_file("def hello(): pass", "test-repo", "test.py", "test");
        assert!(result.errors.is_empty());
        assert!(!result.nodes.is_empty());
    }
}
