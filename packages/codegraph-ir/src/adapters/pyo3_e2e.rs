//! PyO3 bindings for End-to-End Pipeline Orchestrator
//!
//! Exposes E2EOrchestrator to Python with zero-overhead data transfer

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;
use std::path::PathBuf;

use crate::pipeline::end_to_end_config::{
    E2EPipelineConfig, IndexingMode, RepoInfo,
};
use crate::pipeline::E2EOrchestrator;

/// PyO3 wrapper for E2EPipelineConfig
#[pyclass]
#[derive(Clone)]
pub struct PyE2EPipelineConfig {
    pub inner: E2EPipelineConfig,
}

#[pymethods]
impl PyE2EPipelineConfig {
    #[new]
    #[pyo3(signature = (
        repo_path,
        repo_name,
        file_paths = None,
        parallel_workers = None,
        batch_size = 100,
        enable_cache = false,
    ))]
    fn new(
        repo_path: String,
        repo_name: String,
        file_paths: Option<Vec<String>>,
        parallel_workers: Option<usize>,
        batch_size: usize,
        enable_cache: bool,
    ) -> Self {
        let file_paths_buf = file_paths.map(|paths| paths.into_iter().map(PathBuf::from).collect());

        let mut config = E2EPipelineConfig::balanced()
            .repo_root(PathBuf::from(repo_path))
            .repo_name(repo_name)
            .indexing_mode(IndexingMode::Full)
            .with_pipeline(|builder| {
                let mut b = builder.stages(|mut s| {
                    s.chunking = true;
                    s.cross_file = true;
                    s.symbols = true;
                    s
                });

                // Configure parallel settings
                if let Some(workers) = parallel_workers {
                    b = b.parallel(|mut c| {
                        c.num_workers = workers;
                        c.batch_size = batch_size;
                        c
                    });
                }

                // Configure cache if enabled
                if enable_cache {
                    b = b.cache(|mut c| {
                        c.redis_url = "redis://localhost:6379".to_string();
                        c.cache_ttl_seconds = 7 * 24 * 60 * 60;
                        c.pool_size = 10;
                        c.connection_timeout_ms = 5000;
                        c
                    });
                }

                b
            });

        // Set file paths and language filter
        if let Some(paths) = file_paths_buf {
            config.repo_info.file_paths = Some(paths);
        }
        config.repo_info.language_filter = Some(vec!["python".to_string()]);

        Self { inner: config }
    }
}

/// Execute end-to-end pipeline for entire repository
///
/// This is the SOTA Rust-native pipeline that bypasses Python entirely
/// for IR building, cross-file resolution, chunking, occurrences, and symbols.
///
/// # Arguments
/// * `config` - Pipeline configuration
///
/// # Returns
/// Dictionary with:
/// - `nodes`: List[Node] - All IR nodes
/// - `edges`: List[Edge] - All edges
/// - `chunks`: List[Dict] - Searchable chunks
/// - `symbols`: List[Dict] - Navigation symbols
/// - `occurrences`: List[Dict] - SCIP occurrences
/// - `bfg_graphs`: List[Dict] - Basic Flow Graphs
/// - `cfg_edges`: List[Dict] - Control Flow Graph edges
/// - `type_entities`: List[Dict] - Type information
/// - `dfg_graphs`: List[Dict] - Data Flow Graphs
/// - `ssa_graphs`: List[Dict] - SSA Graphs
/// - `pdg_graphs`: List[Dict] - Program Dependence Graph summaries
/// - `taint_results`: List[Dict] - Taint analysis results
/// - `slice_results`: List[Dict] - Slice analysis results
/// - `metadata`: Dict - Performance metadata
///
/// # Example
/// ```python
/// import codegraph_ir
///
/// config = codegraph_ir.PyE2EPipelineConfig(
///     repo_path="/path/to/repo",
///     repo_name="my-repo",
///     file_paths=None,  # Auto-discover
///     parallel_workers=4,
/// )
///
/// result = codegraph_ir.execute_e2e_pipeline(config)
/// print(f"Processed {result['metadata']['files_processed']} files")
/// print(f"Found {len(result['nodes'])} nodes")
/// print(f"Duration: {result['metadata']['total_duration_ms']}ms")
/// ```
#[pyfunction]
pub fn execute_e2e_pipeline(py: Python, config: &PyE2EPipelineConfig) -> PyResult<PyObject> {
    let orchestrator = E2EOrchestrator::new(config.inner.clone());

    // Release GIL and execute pipeline (legacy sequential execution)
    let result = py.allow_threads(|| orchestrator.execute()).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Pipeline failed: {:?}", e))
    })?;

    // Reuse conversion helper
    convert_pipeline_result_to_py(py, result)
}

/// Execute end-to-end pipeline with DAG-based orchestration
///
/// **SOTA Implementation** using Petgraph for:
/// - Automatic dependency resolution
/// - Topological sort execution order
/// - Parallel execution ready (future enhancement)
///
/// # Advantages
/// - Flexible: Enable/disable stages via config
/// - Type-safe: Compile-time exhaustiveness checks
/// - Maintainable: Add stages without modifying execution logic
/// - Debuggable: Clear execution order in logs
///
/// # Example
/// ```python
/// import codegraph_ir
///
/// config = codegraph_ir.PyE2EPipelineConfig(
///     repo_path="/path/to/repo",
///     repo_name="my-repo",
/// )
///
/// result = codegraph_ir.execute_e2e_pipeline_dag(config)
/// print("[DAG] Stage metrics:", result['stage_metrics'])
/// ```
#[pyfunction]
pub fn execute_e2e_pipeline_dag(py: Python, config: &PyE2EPipelineConfig) -> PyResult<PyObject> {
    let orchestrator = E2EOrchestrator::new(config.inner.clone());

    // Release GIL and execute pipeline with DAG orchestration
    let result = py
        .allow_threads(|| orchestrator.execute_with_dag())
        .map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Pipeline failed: {:?}", e))
        })?;

    // Reuse the same conversion logic as execute_e2e_pipeline
    convert_pipeline_result_to_py(py, result)
}

/// Helper function to convert pipeline result to Python dict
/// (Shared by execute_e2e_pipeline and execute_e2e_pipeline_dag)
fn convert_pipeline_result_to_py(
    py: Python,
    result: crate::pipeline::E2EPipelineResult,
) -> PyResult<PyObject> {
    let dict = PyDict::new(py);

    // Nodes (manual conversion to dict)
    let nodes_list = PyList::empty(py);
    for node in &result.outputs.nodes {
        let node_dict = PyDict::new(py);
        node_dict.set_item("id", &node.id)?;
        node_dict.set_item("kind", node.kind.as_str())?;
        node_dict.set_item("fqn", &node.fqn)?;
        node_dict.set_item("file_path", &node.file_path)?;
        node_dict.set_item("language", &node.language)?;
        node_dict.set_item("start_line", node.span.start_line)?;
        node_dict.set_item("end_line", node.span.end_line)?;
        node_dict.set_item("start_col", node.span.start_col)?;
        node_dict.set_item("end_col", node.span.end_col)?;
        if let Some(ref name) = node.name {
            node_dict.set_item("name", name)?;
        }
        if let Some(ref docstring) = node.docstring {
            node_dict.set_item("docstring", docstring)?;
        }
        nodes_list.append(node_dict)?;
    }
    dict.set_item("nodes", nodes_list)?;

    // Edges (manual conversion to dict)
    let edges_list = PyList::empty(py);
    for edge in &result.outputs.edges {
        let edge_dict = PyDict::new(py);
        edge_dict.set_item("source_id", &edge.source_id)?;
        edge_dict.set_item("target_id", &edge.target_id)?;
        edge_dict.set_item("kind", edge.kind.as_str())?;
        edges_list.append(edge_dict)?;
    }
    dict.set_item("edges", edges_list)?;

    // Chunks
    let chunks_list = PyList::empty(py);
    for chunk in &result.outputs.chunks {
        let chunk_dict = PyDict::new(py);
        chunk_dict.set_item("id", &chunk.id)?;
        chunk_dict.set_item("file_path", &chunk.file_path)?;
        chunk_dict.set_item("content", &chunk.content)?;
        chunk_dict.set_item("start_line", chunk.start_line)?;
        chunk_dict.set_item("end_line", chunk.end_line)?;
        chunk_dict.set_item("chunk_type", &chunk.chunk_type)?;
        chunk_dict.set_item("symbol_id", &chunk.symbol_id)?;
        chunks_list.append(chunk_dict)?;
    }
    dict.set_item("chunks", chunks_list)?;

    // Symbols
    let symbols_list = PyList::empty(py);
    for symbol in &result.outputs.symbols {
        let symbol_dict = PyDict::new(py);
        symbol_dict.set_item("id", &symbol.id)?;
        symbol_dict.set_item("name", &symbol.name)?;
        symbol_dict.set_item("kind", &symbol.kind)?;
        symbol_dict.set_item("file_path", &symbol.file_path)?;
        symbol_dict.set_item("definition", (symbol.definition.0, symbol.definition.1))?;
        symbol_dict.set_item("documentation", &symbol.documentation)?;
        symbols_list.append(symbol_dict)?;
    }
    dict.set_item("symbols", symbols_list)?;

    // Occurrences
    let occurrences_list = PyList::empty(py);
    for occurrence in &result.outputs.occurrences {
        let occ_dict = PyDict::new(py);
        occ_dict.set_item("id", &occurrence.id)?;
        occ_dict.set_item("symbol_id", &occurrence.symbol_id)?;
        occ_dict.set_item("span", occurrence.span.clone().into_py(py))?;
        occ_dict.set_item("roles", occurrence.roles)?;
        occ_dict.set_item("file_path", &occurrence.file_path)?;
        occ_dict.set_item("importance_score", occurrence.importance_score)?;
        occurrences_list.append(occ_dict)?;
    }
    dict.set_item("occurrences", occurrences_list)?;

    // SemanticIR: BFG Graphs
    let bfg_graphs_list = PyList::empty(py);
    for bfg in &result.outputs.bfg_graphs {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let bfg_dict = bfg.to_py_dict(py)?;
        bfg_graphs_list.append(bfg_dict)?;
    }
    dict.set_item("bfg_graphs", bfg_graphs_list)?;

    // SemanticIR: CFG Edges
    let cfg_edges_list = PyList::empty(py);
    for cfg_edge in &result.outputs.cfg_edges {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let cfg_dict = cfg_edge.to_py_dict(py)?;
        cfg_edges_list.append(cfg_dict)?;
    }
    dict.set_item("cfg_edges", cfg_edges_list)?;

    // SemanticIR: Type Entities
    let type_entities_list = PyList::empty(py);
    for type_entity in &result.outputs.type_entities {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let type_dict = type_entity.to_py_dict(py)?;
        type_entities_list.append(type_dict)?;
    }
    dict.set_item("type_entities", type_entities_list)?;

    // SemanticIR: DFG Graphs
    let dfg_graphs_list = PyList::empty(py);
    for dfg in &result.outputs.dfg_graphs {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let dfg_dict = dfg.to_py_dict(py)?;
        dfg_graphs_list.append(dfg_dict)?;
    }
    dict.set_item("dfg_graphs", dfg_graphs_list)?;

    // SemanticIR: SSA Graphs
    let ssa_graphs_list = PyList::empty(py);
    for ssa in &result.outputs.ssa_graphs {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let ssa_dict = ssa.to_py_dict(py)?;
        ssa_graphs_list.append(ssa_dict)?;
    }
    dict.set_item("ssa_graphs", ssa_graphs_list)?;

    // SemanticIR: PDG Summaries
    let pdg_graphs_list = PyList::empty(py);
    for pdg in &result.outputs.pdg_graphs {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let pdg_dict = pdg.to_py_dict(py)?;
        pdg_graphs_list.append(pdg_dict)?;
    }
    dict.set_item("pdg_graphs", pdg_graphs_list)?;

    // SemanticIR: Taint Results
    let taint_results_list = PyList::empty(py);
    for taint in &result.outputs.taint_results {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let taint_dict = taint.to_py_dict(py)?;
        taint_results_list.append(taint_dict)?;
    }
    dict.set_item("taint_results", taint_results_list)?;

    // SemanticIR: Slice Results
    let slice_results_list = PyList::empty(py);
    for slice in &result.outputs.slice_results {
        use crate::adapters::pyo3::convertible::ToPyDict;
        let slice_dict = slice.to_py_dict(py)?;
        slice_results_list.append(slice_dict)?;
    }
    dict.set_item("slice_results", slice_results_list)?;

    // Metadata
    let metadata_dict = PyDict::new(py);
    metadata_dict.set_item(
        "total_duration_ms",
        result.metadata.total_duration.as_millis() as u64,
    )?;
    metadata_dict.set_item("files_processed", result.metadata.files_processed)?;
    metadata_dict.set_item("files_cached", result.metadata.files_cached.unwrap_or(0))?;
    metadata_dict.set_item("files_failed", result.metadata.files_failed)?;
    metadata_dict.set_item("total_loc", result.metadata.total_loc)?;
    metadata_dict.set_item("loc_per_second", result.metadata.loc_per_second)?;
    metadata_dict.set_item(
        "cache_hit_rate",
        result.metadata.cache_hit_rate().unwrap_or(0.0),
    )?;

    // Errors
    let errors_list = PyList::new(py, &result.metadata.errors);
    metadata_dict.set_item("errors", errors_list)?;

    // Stage metrics
    let stage_metrics_dict = PyDict::new(py);
    for (stage_name, metrics) in &result.stage_metrics {
        let metrics_dict = PyDict::new(py);
        metrics_dict.set_item("duration_ms", metrics.duration.as_millis() as u64)?;
        metrics_dict.set_item("items_processed", metrics.items_processed)?;

        // Custom metrics
        let custom_dict = PyDict::new(py);
        for (key, value) in &metrics.custom {
            match value {
                crate::pipeline::core::MetricValue::Int(i) => custom_dict.set_item(key, i)?,
                crate::pipeline::core::MetricValue::Float(f) => custom_dict.set_item(key, f)?,
                crate::pipeline::core::MetricValue::String(s) => {
                    custom_dict.set_item(key, s.as_str())?
                }
                crate::pipeline::core::MetricValue::Duration(d) => {
                    custom_dict.set_item(key, d.as_millis() as u64)?
                }
                crate::pipeline::core::MetricValue::Bool(b) => custom_dict.set_item(key, b)?,
            }
        }
        metrics_dict.set_item("custom_metrics", custom_dict)?;

        stage_metrics_dict.set_item(*stage_name, metrics_dict)?;
    }
    metadata_dict.set_item("stage_metrics", stage_metrics_dict)?;

    dict.set_item("metadata", metadata_dict)?;

    Ok(dict.into())
}

// ═══════════════════════════════════════════════════════════════════════════
// Incremental Pipeline API (RFC-062)
// ═══════════════════════════════════════════════════════════════════════════

/// Execute incremental update pipeline
///
/// **SOTA Implementation** - All logic runs in Rust:
/// 1. L1: Re-parse only changed files (O(n_changed))
/// 2. L3: Incremental cross-file with fingerprint cutoff (P0-3)
/// 3. L2: Update chunks only for affected files using ChunkStore (P0-2)
/// 4. L4/L5: Re-aggregate occurrences/symbols for affected files
///
/// # Arguments
/// * `config` - Pipeline configuration
/// * `existing_result` - Previous pipeline result (dict from execute_e2e_pipeline)
/// * `existing_global_context` - Previous GlobalContext (dict)
/// * `existing_chunks` - Previous chunks list
/// * `changed_files` - List of (file_path, content) tuples
///
/// # Returns
/// Dictionary with:
/// - Same fields as execute_e2e_pipeline
/// - `affected_files`: List[str] - Files affected by changes
/// - `incremental_stats`: Dict - Performance statistics
///
/// # Performance
/// - Small changes (1-10 files): **10-60x** speedup
/// - Medium changes (10-100 files): **5-10x** speedup
/// - Large changes (100+ files): **2-5x** speedup
///
/// # Example
/// ```python
/// import codegraph_ir
///
/// # Initial full build
/// config = codegraph_ir.PyE2EPipelineConfig(...)
/// initial = codegraph_ir.execute_e2e_pipeline(config)
///
/// # After some files changed...
/// changed = [("src/utils.py", new_content)]
/// incremental = codegraph_ir.execute_incremental_pipeline(
///     config,
///     initial,
///     initial["global_context"],
///     initial["chunks"],
///     changed
/// )
/// print(f"Affected files: {incremental['affected_files']}")
/// print(f"Speedup: {incremental['incremental_stats']['speedup_estimate']:.1f}x")
/// ```
#[pyfunction]
pub fn execute_incremental_pipeline(
    py: Python,
    config: &PyE2EPipelineConfig,
    existing_result: &PyDict,
    existing_global_context: &PyDict,
    existing_chunks: &PyList,
    changed_files: &PyList,
) -> PyResult<PyObject> {

    // Parse changed files list
    let changed: Vec<(PathBuf, String)> = changed_files
        .iter()
        .map(|item| {
            let tuple = item.downcast::<pyo3::types::PyTuple>()?;
            let path: String = tuple.get_item(0)?.extract()?;
            let content: String = tuple.get_item(1)?.extract()?;
            Ok((PathBuf::from(path), content))
        })
        .collect::<PyResult<Vec<_>>>()?;

    // Reconstruct E2EPipelineResult from Python dict
    let existing = reconstruct_e2e_result(py, existing_result)?;

    // Reconstruct GlobalContextResult from Python dict
    let global_context = reconstruct_global_context(existing_global_context)?;

    // Reconstruct ChunkStore from Python list
    let chunk_store = reconstruct_chunk_store(existing_chunks)?;

    // Create orchestrator and execute incremental update
    let orchestrator = E2EOrchestrator::new(config.inner.clone());

    let result = py
        .allow_threads(|| {
            orchestrator.execute_incremental(&existing, changed, &global_context, &chunk_store)
        })
        .map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
                "Incremental pipeline failed: {:?}",
                e
            ))
        })?;

    // Convert result to Python
    let dict = convert_pipeline_result_to_py(py, result.result)?;
    let dict = dict.downcast::<PyDict>(py)?;

    // Add incremental-specific fields
    let affected_list = PyList::new(py, &result.affected_files);
    dict.set_item("affected_files", affected_list)?;

    // Add incremental stats
    let stats_dict = PyDict::new(py);
    stats_dict.set_item("changed_files", result.stats.changed_files)?;
    stats_dict.set_item("affected_files", result.stats.affected_files)?;
    stats_dict.set_item("cutoff_skipped", result.stats.cutoff_skipped)?;
    stats_dict.set_item("l1_reparse_ms", result.stats.l1_reparse_ms)?;
    stats_dict.set_item("l2_chunk_update_ms", result.stats.l2_chunk_update_ms)?;
    stats_dict.set_item("l3_crossfile_ms", result.stats.l3_crossfile_ms)?;
    stats_dict.set_item("total_ms", result.stats.total_ms)?;
    stats_dict.set_item("speedup_estimate", result.stats.speedup_estimate)?;
    dict.set_item("incremental_stats", stats_dict)?;

    // SOTA: Return GlobalContext for next incremental cycle
    let global_context_dict = PyDict::new(py);
    global_context_dict.set_item("total_symbols", result.global_context.total_symbols)?;
    global_context_dict.set_item("total_files", result.global_context.total_files)?;
    global_context_dict.set_item("total_imports", result.global_context.total_imports)?;
    global_context_dict.set_item("total_dependencies", result.global_context.total_dependencies)?;
    global_context_dict.set_item("build_duration_ms", result.global_context.build_duration_ms)?;

    // Convert file_dependencies to Python dict
    let file_deps_dict = PyDict::new(py);
    for (path, deps) in &result.global_context.file_dependencies {
        let deps_list = PyList::new(py, deps);
        file_deps_dict.set_item(path.as_str(), deps_list)?;
    }
    global_context_dict.set_item("file_dependencies", file_deps_dict)?;

    // Convert file_dependents to Python dict
    let file_dependents_dict = PyDict::new(py);
    for (path, deps) in &result.global_context.file_dependents {
        let deps_list = PyList::new(py, deps);
        file_dependents_dict.set_item(path.as_str(), deps_list)?;
    }
    global_context_dict.set_item("file_dependents", file_dependents_dict)?;

    // Convert topological_order to Python list
    let topo_list = PyList::new(py, &result.global_context.topological_order);
    global_context_dict.set_item("topological_order", topo_list)?;

    dict.set_item("global_context", global_context_dict)?;

    // SOTA: Return ChunkStore chunks for next incremental cycle
    let chunks_list = PyList::empty(py);
    for chunk in result.chunk_store.get_all_chunks() {
        let chunk_dict = PyDict::new(py);
        chunk_dict.set_item("id", chunk.chunk_id.as_str())?;
        chunk_dict.set_item("file_path", chunk.file_path.clone().unwrap_or_default())?;
        chunk_dict.set_item("start_line", chunk.start_line.unwrap_or(0))?;
        chunk_dict.set_item("end_line", chunk.end_line.unwrap_or(0))?;
        chunk_dict.set_item("kind", chunk.kind.to_string())?;
        chunk_dict.set_item("fqn", chunk.fqn.as_str())?;
        chunks_list.append(chunk_dict)?;
    }
    dict.set_item("chunk_store_chunks", chunks_list)?;

    Ok(dict.into())
}

/// Helper: Reconstruct E2EPipelineResult from Python dict
fn reconstruct_e2e_result(
    py: Python,
    dict: &PyDict,
) -> PyResult<crate::pipeline::E2EPipelineResult> {
    use crate::pipeline::{
        core::PipelineMetadata, E2EPipelineResult, PipelineType, RepositoryOutputs,
    };

    // Extract nodes
    let nodes_list: &PyList = dict
        .get_item("nodes")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("nodes"))?
        .downcast()?;

    let nodes: Vec<crate::shared::models::Node> = nodes_list
        .iter()
        .filter_map(|item| item.extract().ok())
        .collect();

    // Extract edges
    let edges_list: &PyList = dict
        .get_item("edges")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("edges"))?
        .downcast()?;

    let edges: Vec<crate::shared::models::Edge> = edges_list
        .iter()
        .filter_map(|item| item.extract().ok())
        .collect();

    // Extract occurrences - simplified, will be rebuilt from changed files
    let occurrences: Vec<crate::shared::models::Occurrence> = Vec::new();

    Ok(E2EPipelineResult {
        outputs: RepositoryOutputs {
            nodes,
            edges,
            chunks: Vec::new(),       // Will be rebuilt
            symbols: Vec::new(),      // Will be rebuilt
            occurrences,
            ir_documents: HashMap::new(),
            bfg_graphs: Vec::new(),   // Will be rebuilt from changed files
            cfg_edges: Vec::new(),
            type_entities: Vec::new(),
            dfg_graphs: Vec::new(),
            ssa_graphs: Vec::new(),
            pdg_graphs: Vec::new(),
            taint_results: Vec::new(),
            slice_results: Vec::new(),
        },
        metadata: PipelineMetadata::new(PipelineType::Repository),
        stage_metrics: HashMap::new(),
    })
}

/// Helper: Reconstruct GlobalContextResult from Python dict
fn reconstruct_global_context(
    dict: &PyDict,
) -> PyResult<crate::features::cross_file::GlobalContextResult> {
    use crate::features::cross_file::GlobalContextResult;
    use std::collections::HashMap;

    // Extract file_dependents (most important for incremental update)
    let file_dependents: HashMap<String, Vec<String>> = dict
        .get_item("file_dependents")?
        .and_then(|v| v.downcast::<PyDict>().ok())
        .map(|d| {
            d.iter()
                .filter_map(|(k, v)| {
                    let key: String = k.extract().ok()?;
                    let val: Vec<String> = v.downcast::<PyList>().ok()?.extract().ok()?;
                    Some((key, val))
                })
                .collect()
        })
        .unwrap_or_default();

    // Extract file_dependencies
    let file_dependencies: HashMap<String, Vec<String>> = dict
        .get_item("file_dependencies")?
        .and_then(|v| v.downcast::<PyDict>().ok())
        .map(|d| {
            d.iter()
                .filter_map(|(k, v)| {
                    let key: String = k.extract().ok()?;
                    let val: Vec<String> = v.downcast::<PyList>().ok()?.extract().ok()?;
                    Some((key, val))
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(GlobalContextResult {
        total_symbols: 0,
        total_files: 0,
        total_imports: 0,
        total_dependencies: 0,
        symbol_table: HashMap::new(),
        file_dependencies,
        file_dependents,
        topological_order: Vec::new(),
        build_duration_ms: 0,
        fingerprints: HashMap::new(), // Will be rebuilt
    })
}

/// Helper: Reconstruct ChunkStore from Python list
fn reconstruct_chunk_store(
    chunks_list: &PyList,
) -> PyResult<crate::features::chunking::infrastructure::ChunkStore> {
    use crate::features::chunking::{domain::Chunk, domain::ChunkKind, infrastructure::ChunkStore};

    let chunks: Vec<Chunk> = chunks_list
        .iter()
        .filter_map(|item| {
            let dict = item.downcast::<PyDict>().ok()?;
            let id: String = dict.get_item("id").ok()??.extract().ok()?;
            let file_path: String = dict.get_item("file_path").ok()??.extract().ok()?;
            let start_line: u32 = dict.get_item("start_line").ok()??.extract().ok()?;
            let end_line: u32 = dict.get_item("end_line").ok()??.extract().ok()?;

            Some(Chunk {
                chunk_id: id,
                repo_id: String::new(),
                snapshot_id: "latest".to_string(),
                project_id: None,
                module_path: None,
                file_path: Some(file_path),
                kind: ChunkKind::File,
                fqn: String::new(),
                start_line: Some(start_line),
                end_line: Some(end_line),
                original_start_line: Some(start_line),
                original_end_line: Some(end_line),
                content_hash: None,
                parent_id: None,
                children: Vec::new(),
                language: None,
                symbol_visibility: None,
                symbol_id: None,
                symbol_owner_id: None,
                summary: None,
                importance: None,
                attrs: Default::default(),
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: None,
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            })
        })
        .collect();

    Ok(ChunkStore::from_chunks(chunks))
}

/// Register E2E pipeline bindings
pub fn register_e2e_bindings(m: &PyModule) -> PyResult<()> {
    m.add_class::<PyE2EPipelineConfig>()?;
    m.add_function(wrap_pyfunction!(execute_e2e_pipeline, m)?)?;
    m.add_function(wrap_pyfunction!(execute_e2e_pipeline_dag, m)?)?;
    m.add_function(wrap_pyfunction!(execute_incremental_pipeline, m)?)?;
    Ok(())
}
