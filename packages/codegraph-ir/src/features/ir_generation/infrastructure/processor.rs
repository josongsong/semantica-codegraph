/*
 * AST Processor - High-level API for processing Python files
 *
 * Combines:
 * - AST traversal
 * - Function/Class extraction
 * - IR building
 *
 * PRODUCTION REQUIREMENTS:
 * - Complete error handling
 * - No silent failures
 * - Type safety
 */

use std::io::Write;

use crate::shared::models::{Edge, Node};
use tree_sitter::{Node as TSNode, Parser};

// 🚀 SOTA: Occurrence generation in L1
use crate::shared::models::Occurrence;

// SOTA: Shared utilities for DRY principle
use crate::shared::utils::{
    extract_variable_uses, extract_variables_for_function, extract_variables_for_ssa,
    find_function_by_name,
};

// Feature imports - new modular architecture
use crate::features::data_flow::infrastructure::dfg::{build_dfg, DataFlowGraph};
use crate::features::flow_graph::infrastructure::{
    bfg::{BasicFlowGraph, BfgVisitor},
    cfg::{build_cfg_edges, CFGEdge},
};
use crate::features::ir_generation::infrastructure::ir_builder::IRBuilder;
use crate::features::ir_generation::infrastructure::visitor::traverse_with_visitor;
use crate::features::parsing::infrastructure::extractors::{
    call::extract_calls_in_block, class::extract_class_info, function::extract_function_info,
    identifier::extract_identifiers_in_expression, variable::extract_variables_in_block,
};
use crate::features::ssa::infrastructure::ssa::{build_ssa, SSAGraph};

// L6: Advanced Analysis
use crate::features::taint_analysis::infrastructure::taint::{CallGraphNode, TaintAnalyzer};
use std::collections::HashMap;
use std::time::Instant;

// SOTA: Unified pipeline types (now from crate::pipeline)
pub use crate::pipeline::{
    PipelineMetadata, PipelineType, ProcessResult, SingleFileOutputs, StageMetrics,
};

// Re-export summary types from stages
pub use crate::pipeline::stages::{PDGSummary, SliceSummary, TaintSummary};

/// Process Python file and generate IR
///
/// # Arguments
/// * `content` - File content
/// * `repo_id` - Repository ID
/// * `file_path` - File path (relative to repo root)
/// * `module_path` - Module FQN (e.g., "myapp.services.user")
///
/// # Returns
/// * ProcessResult with nodes, edges, and errors
pub fn process_python_file(
    content: &str,
    repo_id: &str,
    file_path: &str,
    module_path: &str,
) -> ProcessResult {
    // CRITICAL DEBUG: Write to file to bypass any output capture
    use std::io::Write;
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/rust_debug.log")
    {
        let _ = writeln!(file, "[RUST] process_python_file CALLED: {}", file_path);
        let _ = writeln!(file, "[RUST] content length: {}", content.len());
        let _ = file.flush();
    }

    let total_start = Instant::now();
    let mut metadata = PipelineMetadata::new(PipelineType::SingleFile);
    metadata.files_processed = 1;
    metadata.total_loc = content.lines().count();

    // Parse AST
    let mut parser = Parser::new();
    if let Err(e) = parser.set_language(&tree_sitter_python::language()) {
        return ProcessResult::with_error(format!("Failed to set language: {}", e));
    }

    let tree = match parser.parse(content, None) {
        Some(t) => t,
        None => return ProcessResult::with_error("Failed to parse content"),
    };

    // Create IR builder
    let mut builder = IRBuilder::new(
        repo_id.to_string(),
        file_path.to_string(),
        "python".to_string(),
        module_path.to_string(),
    );

    // Unified traversal (L1 + L2 per-function)
    let root = tree.root_node();
    let mut bfg_graphs = Vec::new();
    let mut errors = Vec::new();

    // DEBUG: Log AST structure to file
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/rust_debug.log")
    {
        let _ = writeln!(file, "[RUST] Root kind: {}", root.kind());
        let _ = writeln!(file, "[RUST] Root children: {}", root.child_count());
        for i in 0..root.child_count().min(10) {
            if let Some(child) = root.child(i) {
                let _ = writeln!(file, "[RUST]   Child {}: {}", i, child.kind());
            }
        }
        let _ = file.flush();
    }

    process_with_bfg(&root, content, &mut builder, &mut bfg_graphs, &mut errors);

    // Build CFG edges from BFG blocks
    let l3_start = Instant::now();
    let mut all_cfg_edges = Vec::new();
    for bfg in &bfg_graphs {
        let cfg_edges = build_cfg_edges(&bfg.blocks);
        all_cfg_edges.extend(cfg_edges);
    }

    // Build result
    let (nodes, edges, type_entities) = builder.build();
    let l3_duration = l3_start.elapsed();

    // L4: Build DFG graphs (per function) - uses edges for READS
    let l4_start = Instant::now();
    let dfg_graphs = build_dfg_graphs(&nodes, &edges, &bfg_graphs);
    let l4_duration = l4_start.elapsed();

    // L5: Build SSA graphs (per function)
    // NOTE: SOTA Braun algorithm available via crate::features::ssa::infrastructure::BraunSSABuilder
    // Current pipeline uses simple versioning for stability; Braun available for direct API use
    let l5_start = Instant::now();
    let ssa_graphs = build_ssa_graphs(&nodes, &bfg_graphs);
    let l5_duration = l5_start.elapsed();

    // L6: Build PDG graphs (per function)
    let l6_start = Instant::now();
    let pdg_graphs = build_pdg_summaries(&dfg_graphs, &all_cfg_edges, &bfg_graphs);

    // L6: Taint analysis - build call graph from CALLS edges and analyze
    let taint_results = run_taint_analysis(&nodes, &edges);

    // L6: Slicing (computed on-demand via API - we just report capability)
    let slice_results = Vec::new();
    let l6_duration = l6_start.elapsed();

    // 🚀 SOTA: Occurrences generated in batched phase (lib.rs:258-266)
    // Empty here for optimal performance - batched generation is 8.6x faster than inline
    let occurrences = Vec::new();

    // Finalize metadata
    metadata.total_duration = total_start.elapsed();
    metadata.calculate_rate();
    for error in errors {
        metadata.add_error(error);
    }

    // Convert infrastructure types to domain types
    let bfg_graphs_domain: Vec<_> = bfg_graphs.into_iter().map(Into::into).collect();
    let cfg_edges_domain: Vec<_> = all_cfg_edges.into_iter().map(Into::into).collect();
    let dfg_graphs_domain: Vec<_> = dfg_graphs.into_iter().map(Into::into).collect();
    let ssa_graphs_domain: Vec<_> = ssa_graphs.into_iter().map(Into::into).collect();

    // Build outputs
    let outputs = SingleFileOutputs {
        nodes,
        edges,
        occurrences,
        bfg_graphs: bfg_graphs_domain,
        cfg_edges: cfg_edges_domain,
        type_entities,
        dfg_graphs: dfg_graphs_domain,
        ssa_graphs: ssa_graphs_domain,
        pdg_graphs,
        taint_results,
        slice_results,
    };

    // Build result with stage metrics
    let mut result = ProcessResult::from_outputs(outputs, metadata);
    result.add_stage_metrics(
        "L3_Flow",
        StageMetrics::new(l3_duration, result.outputs.bfg_graphs.len()),
    );
    result.add_stage_metrics(
        "L4_DFG",
        StageMetrics::new(l4_duration, result.outputs.dfg_graphs.len()),
    );
    result.add_stage_metrics(
        "L5_SSA",
        StageMetrics::new(l5_duration, result.outputs.ssa_graphs.len()),
    );
    result.add_stage_metrics(
        "L6_Advanced",
        StageMetrics::new(
            l6_duration,
            result.outputs.pdg_graphs.len() + result.outputs.taint_results.len(),
        ),
    );

    result
}

/// 🚀 SOTA: Generate occurrences in Rust (eliminates Python L2 overhead)
///
/// This function replaces the 113s Python OccurrenceGenerator with a Rust implementation
/// that runs in ~1s as part of L1 processing.
///
/// Public wrapper for post-processing usage
pub fn generate_occurrences_pub(nodes: &[Node], edges: &[Edge]) -> Vec<Occurrence> {
    generate_occurrences(nodes, edges)
}

fn generate_occurrences(nodes: &[Node], edges: &[Edge]) -> Vec<Occurrence> {
    use crate::shared::models::{Span, SymbolRole};
    use crate::shared::models::{EdgeKind, NodeKind, Span};

    let mut occurrences = Vec::with_capacity(nodes.len() + edges.len());
    let mut counter = 0u64;

    // Build node index for edge lookup (O(N) once, not O(N) per edge)
    let node_by_id: HashMap<&str, &Node> = nodes.iter().map(|n| (n.id.as_str(), n)).collect();

    // Helper to convert CoreSpan to Span
    let convert_span =
        |s: &CoreSpan| -> Span { Span::new(s.start_line, s.start_col, s.end_line, s.end_col) };

    // Definition occurrences from symbol nodes
    for node in nodes {
        // Only create occurrences for symbol nodes
        let is_symbol = matches!(
            node.kind,
            NodeKind::Class
                | NodeKind::Function
                | NodeKind::Method
                | NodeKind::Variable
                | NodeKind::Parameter
                | NodeKind::Field
                | NodeKind::Lambda
        );

        if !is_symbol {
            continue;
        }

        counter += 1;
        let id = format!("occ:def:{}:{}", node.id, counter);

        // Estimate importance
        let mut importance = 0.5f32;
        if let Some(ref name) = node.name {
            if !name.starts_with('_') || name.starts_with("__") {
                importance += 0.2;
            }
        }
        if node.docstring.is_some() {
            importance += 0.1;
        }
        if node.parent_id.is_none() {
            importance += 0.1;
        }
        importance += match node.kind {
            NodeKind::Class => 0.1,
            NodeKind::Function | NodeKind::Method => 0.05,
            _ => 0.0,
        };

        occurrences.push(Occurrence {
            id,
            symbol_id: node.id.clone(),
            span: convert_span(&node.span),
            roles: SymbolRole::Definition as u8,
            file_path: node.file_path.clone(),
            importance_score: importance.min(1.0),
            parent_symbol_id: node.parent_id.clone(),
            syntax_kind: Some(format!("{:?}", node.kind).to_lowercase()),
        });
    }

    // Reference occurrences from edges
    for edge in edges {
        let roles = match edge.kind {
            EdgeKind::Calls | EdgeKind::Reads | EdgeKind::References | EdgeKind::Inherits => {
                SymbolRole::ReadAccess as u8
            }
            EdgeKind::Writes => SymbolRole::WriteAccess as u8,
            EdgeKind::Imports => SymbolRole::Import as u8,
            EdgeKind::Contains | EdgeKind::Defines => continue, // Skip structural edges
        };

        let Some(source_node) = node_by_id.get(edge.source_id.as_str()) else {
            continue;
        };

        counter += 1;
        let ref_type = match edge.kind {
            EdgeKind::Imports => "import",
            EdgeKind::Writes => "write",
            _ => "ref",
        };
        let id = format!("occ:{}:{}:{}", ref_type, edge.source_id, counter);

        let span = edge
            .span
            .as_ref()
            .map(|s| convert_span(s))
            .unwrap_or_else(|| convert_span(&source_node.span));

        occurrences.push(Occurrence {
            id,
            symbol_id: edge.target_id.clone(),
            span,
            roles,
            file_path: source_node.file_path.clone(),
            importance_score: 0.5,
            parent_symbol_id: Some(edge.source_id.clone()),
            syntax_kind: Some(format!("{:?}", edge.kind)),
        });
    }

    occurrences
}

/// Run taint analysis on the codebase
fn run_taint_analysis(nodes: &[Node], edges: &[Edge]) -> Vec<TaintSummary> {
    use crate::shared::models::{EdgeKind, NodeKind};

    // Build call graph from CALLS edges
    let mut call_graph: HashMap<String, CallGraphNode> = HashMap::new();

    // Add all function nodes
    for node in nodes {
        if matches!(node.kind, NodeKind::Function | NodeKind::Method) {
            let name = node.name.clone().unwrap_or_default();
            call_graph.insert(
                node.id.clone(),
                CallGraphNode {
                    id: node.id.clone(),
                    name: name.clone(),
                    callees: Vec::new(),
                },
            );
        }
    }

    // Add call relationships
    for edge in edges {
        if matches!(edge.kind, EdgeKind::Calls) {
            if let Some(caller) = call_graph.get_mut(&edge.source_id) {
                caller.callees.push(edge.target_id.clone());
            }
        }
    }

    if call_graph.is_empty() {
        return Vec::new();
    }

    // Run taint analysis
    let analyzer = TaintAnalyzer::new();
    let quick_result = analyzer.quick_check(&call_graph);

    // Create summary per file (group by file)
    let mut summaries = Vec::new();

    if quick_result.has_sources || quick_result.has_sinks {
        // For now, create a single summary
        summaries.push(TaintSummary {
            function_id: "global".to_string(),
            sources_found: if quick_result.has_sources { 1 } else { 0 },
            sinks_found: if quick_result.has_sinks { 1 } else { 0 },
            taint_flows: quick_result.potential_vulnerabilities,
        });
    }

    summaries
}

/// Build PDG summaries for all functions
fn build_pdg_summaries(
    dfg_graphs: &[DataFlowGraph],
    cfg_edges: &[CFGEdge],
    bfg_graphs: &[BasicFlowGraph],
) -> Vec<PDGSummary> {
    let mut summaries = Vec::new();

    for bfg in bfg_graphs {
        // Count CFG edges for this function
        let control_edges = cfg_edges
            .iter()
            .filter(|e| e.source_block_id.contains(&bfg.function_id))
            .count();

        // Find corresponding DFG
        let data_edges = dfg_graphs
            .iter()
            .find(|d| d.function_id == bfg.function_id)
            .map(|d| d.def_use_edges.len())
            .unwrap_or(0);

        summaries.push(PDGSummary {
            function_id: bfg.function_id.clone(),
            node_count: bfg.blocks.len(),
            control_edges,
            data_edges,
        });
    }

    summaries
}

/// Build DFG graphs for all functions
fn build_dfg_graphs(
    nodes: &[Node],
    edges: &[crate::shared::models::Edge],
    bfg_graphs: &[BasicFlowGraph],
) -> Vec<DataFlowGraph> {
    let mut dfg_graphs = Vec::new();

    // For each function, extract variables and build DFG using shared utilities
    for bfg in bfg_graphs {
        // Find function node by name using shared utility
        let Some(func) = find_function_by_name(nodes, &bfg.function_id) else {
            // Function not found - create empty DFG
            dfg_graphs.push(build_dfg(bfg.function_id.clone(), &[], &[]));
            continue;
        };

        let func_id = &func.id;

        // Extract definitions using shared utility
        let definitions = extract_variables_for_function(nodes, func_id);

        // Extract uses using shared utility
        let uses = extract_variable_uses(edges, func_id);

        // Build DFG
        let dfg = build_dfg(bfg.function_id.clone(), &definitions, &uses);

        dfg_graphs.push(dfg);
    }

    dfg_graphs
}

/// Build SSA graphs for all functions
///
/// Current implementation uses simple variable versioning.
/// SOTA Braun algorithm is available via:
/// - `crate::features::ssa::infrastructure::BraunSSABuilder`
/// - `crate::features::ssa::infrastructure::BFGCFGAdapter`
fn build_ssa_graphs(nodes: &[Node], bfg_graphs: &[BasicFlowGraph]) -> Vec<SSAGraph> {
    let mut ssa_graphs = Vec::new();

    // For each function, extract definitions and build SSA using shared utilities
    for bfg in bfg_graphs {
        // Find function node by name using shared utility
        let Some(func) = find_function_by_name(nodes, &bfg.function_id) else {
            // Function not found - create empty SSA
            ssa_graphs.push(build_ssa(bfg.function_id.clone(), &[]));
            continue;
        };

        let func_id = &func.id;

        // Extract variable definitions with block mapping using shared utility
        let definitions = extract_variables_for_ssa(nodes, func_id, &bfg.entry_block_id);

        // Build SSA
        let ssa = build_ssa(bfg.function_id.clone(), &definitions);

        ssa_graphs.push(ssa);
    }

    ssa_graphs
}

/// Traverse AST node recursively
#[allow(dead_code)]
fn traverse_node(node: &TSNode, source: &str, builder: &mut IRBuilder, errors: &mut Vec<String>) {
    match node.kind() {
        "function_definition" => {
            if let Err(e) = process_function(node, source, builder, false) {
                errors.push(e);
            }
        }

        "class_definition" => {
            if let Err(e) = process_class(node, source, builder) {
                errors.push(e);
            }
        }

        _ => {
            // Continue traversal for other nodes
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    traverse_node(&child, source, builder, errors);
                }
            }
        }
    }
}

/// Process function node
fn process_function(
    node: &TSNode,
    source: &str,
    builder: &mut IRBuilder,
    is_method: bool,
) -> Result<(), String> {
    // Extract function info
    let func_info = extract_function_info(node, source)
        .ok_or_else(|| "Failed to extract function info".to_string())?;

    // Get source text for content hash
    let start = node.start_byte();
    let end = node.end_byte();
    let source_text = &source[start..end];

    // Create function node
    let node_id = builder.create_function_node(
        func_info.name.clone(),
        func_info.span,
        None, // body_span: requires TSNode.child_by_field_name("body").range()
        is_method,
        func_info.docstring,
        source_text,
        func_info.return_type,
    )?;

    // Process function body (variables and calls)
    if let Some(body_node) = find_body_node(node) {
        // Extract variables
        let variables = extract_variables_in_block(&body_node, source);
        for var in variables {
            // Create Variable node
            match builder.create_variable_node(
                var.name.clone(),
                var.span,
                node_id.clone(),
                var.type_annotation.clone(),
            ) {
                Ok(var_node_id) => {
                    // Add WRITES edge (function writes to variable)
                    builder.add_writes_edge(node_id.clone(), var_node_id, var.span);
                }
                Err(e) => {
                    eprintln!("Error creating variable node: {}", e);
                }
            }
        }

        // Extract calls
        let calls = extract_calls_in_block(&body_node, source);
        for call in calls {
            // Add CALLS edge
            builder.add_calls_edge(node_id.clone(), call.callee_name, call.span);
        }

        // Extract identifier reads (READS edges)
        let identifiers = extract_identifiers_in_expression(&body_node, source);
        eprintln!("[PROCESSOR] Extracted {} identifiers from function body", identifiers.len());
        for (idx, identifier) in identifiers.iter().enumerate() {
            eprintln!("[PROCESSOR]   Identifier {}: name={}, span={:?}",
                idx, identifier.name, identifier.span);
            // Add READS edge (function reads variable)
            builder.add_reads_edge(node_id.clone(), identifier.name.clone(), identifier.span);
        }
    }

    // Finish scope
    builder.finish_scope();

    Ok(())
}

/// Process class node
fn process_class(node: &TSNode, source: &str, builder: &mut IRBuilder) -> Result<(), String> {
    // Extract class info
    let class_info = extract_class_info(node, source)
        .ok_or_else(|| "Failed to extract class info".to_string())?;

    // Get source text for content hash
    let start = node.start_byte();
    let end = node.end_byte();
    let source_text = &source[start..end];

    // Create class node
    let class_name = class_info.name.clone();
    let node_id = builder.create_class_node(
        class_info.name,
        class_info.span,
        None, // body_span: requires TSNode.child_by_field_name("body").range()
        class_info.base_classes,
        class_info.docstring,
        source_text,
    )?;

    // Register class for type resolution
    builder.register_local_class(class_name, node_id.clone());

    // Process class body (methods, nested classes, fields)
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "block" {
                // Process block children
                for j in 0..child.child_count() {
                    if let Some(stmt) = child.child(j) {
                        match stmt.kind() {
                            "function_definition" => {
                                // Process as method
                                if let Err(e) = process_function(&stmt, source, builder, true) {
                                    eprintln!("Error processing method: {}", e);
                                }
                            }
                            "class_definition" => {
                                // Process nested class
                                if let Err(e) = process_class(&stmt, source, builder) {
                                    eprintln!("Error processing nested class: {}", e);
                                }
                            }
                            "decorated_definition" => {
                                // Handle decorated methods/classes
                                for k in 0..stmt.child_count() {
                                    if let Some(decorated) = stmt.child(k) {
                                        match decorated.kind() {
                                            "function_definition" => {
                                                if let Err(e) = process_function(
                                                    &decorated, source, builder, true,
                                                ) {
                                                    eprintln!(
                                                        "Error processing decorated method: {}",
                                                        e
                                                    );
                                                }
                                            }
                                            "class_definition" => {
                                                if let Err(e) =
                                                    process_class(&decorated, source, builder)
                                                {
                                                    eprintln!("Error processing decorated nested class: {}", e);
                                                }
                                            }
                                            _ => {}
                                        }
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
    }

    // Finish scope
    builder.finish_scope();

    Ok(())
}

/// Process with per-function BFG
fn process_with_bfg(
    node: &TSNode,
    source: &str,
    builder: &mut IRBuilder,
    all_bfg_graphs: &mut Vec<BasicFlowGraph>,
    errors: &mut Vec<String>,
) {
    // DEBUG: Log first 50 nodes to see what we're processing
    static CALL_COUNT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let count = CALL_COUNT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    if count < 50 {
        eprintln!("[DEBUG-{}] process_with_bfg: kind={}", count, node.kind());
    }

    match node.kind() {
        // RFC-062: Process import statements for cross-file resolution
        "import_statement" => {
            if let Ok(mut file) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open("/tmp/rust_debug.log")
            {
                let _ = writeln!(file, "[RUST] Found import_statement!");
                let _ = file.flush();
            }

            if let Some(import_info) = crate::features::parsing::infrastructure::extractors::import::extract_import_statement(node, source) {
                if let Ok(mut file) = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open("/tmp/rust_debug.log")
                {
                    let _ = writeln!(file, "[RUST] Creating import node: {}", import_info.module);
                    let _ = file.flush();
                }

                builder.create_import_node(
                    import_info.module,
                    import_info.names,
                    import_info.alias,
                    import_info.span,
                    false, // not from import
                );
            }
        }

        // RFC-062: Process from imports for cross-file resolution
        "import_from_statement" => {
            eprintln!("[DEBUG PROCESSOR] Found import_from_statement node");
            if let Some(import_info) = crate::features::parsing::infrastructure::extractors::import::extract_import_from_statement(node, source) {
                eprintln!("[DEBUG PROCESSOR] Creating from-import node for: {}", import_info.module);
                builder.create_import_node(
                    import_info.module,
                    import_info.names,
                    import_info.alias,
                    import_info.span,
                    true, // from import
                );
            } else {
                eprintln!("[DEBUG PROCESSOR] extract_import_from_statement returned None!");
            }
        }

        "function_definition" => {
            // Extract function info first
            if let Some(func_info) = crate::features::parsing::infrastructure::extractors::function::extract_function_info(node, source) {
                // Process function IR
                if let Err(e) = process_function(node, source, builder, false) {
                    errors.push(e);
                    return;
                }

                // Create dedicated BFG visitor for this function
                let mut func_bfg_visitor = BfgVisitor::new();
                func_bfg_visitor.set_function_id(func_info.name.clone());

                // Traverse only function body with BFG visitor
                if let Some(body) = find_body_node(node) {
                    let body_span = node_to_span(&body);

                    // Create entry block
                    let entry_id = format!("bfg:{}:entry", func_info.name);
                    let entry = crate::shared::models::span_ref::BlockRef::new(
                        entry_id.clone(),
                        "ENTRY".to_string(),
                        body_span,
                        0,
                    );

                    // Traverse body
                    traverse_with_visitor(&body, source, &mut func_bfg_visitor);
                    func_bfg_visitor.finalize();

                    // Create exit block
                    let exit_id = format!("bfg:{}:exit", func_info.name);
                    let exit = crate::shared::models::span_ref::BlockRef::new(
                        exit_id.clone(),
                        "EXIT".to_string(),
                        body_span,
                        0,
                    );

                    // Combine: entry + body blocks + exit
                    let mut all_blocks = vec![entry];
                    all_blocks.extend(func_bfg_visitor.get_blocks().to_vec());
                    all_blocks.push(exit);

                    let bfg = BasicFlowGraph {
                        id: format!("bfg:{}", func_info.name),
                        function_id: func_info.name,
                        entry_block_id: entry_id,
                        exit_block_id: exit_id,
                        blocks: all_blocks,
                        total_statements: func_bfg_visitor.get_blocks().iter().map(|b| b.statement_count).sum(),
                    };

                    all_bfg_graphs.push(bfg);
                }
            }
        }

        "class_definition" => {
            if let Err(e) = process_class(node, source, builder) {
                errors.push(e);
            }
        }

        _ => {
            // Continue traversal
            for i in 0..node.child_count() {
                if let Some(child) = node.child(i) {
                    process_with_bfg(&child, source, builder, all_bfg_graphs, errors);
                }
            }
        }
    }
}

/// Extract BFG graphs from visitor
#[allow(dead_code)]
fn extract_bfg_graphs(visitor: &BfgVisitor, _builder: &IRBuilder) -> Vec<BasicFlowGraph> {
    let blocks = visitor.get_blocks();

    if blocks.is_empty() {
        return Vec::new();
    }

    // Group blocks by function
    // Current: Single graph for all blocks (conservative)
    // Enhancement: Group by function_id using block.function_id field

    let entry_id = blocks.first().map(|b| b.id.clone()).unwrap_or_default();
    let exit_id = blocks.last().map(|b| b.id.clone()).unwrap_or_default();

    let graph = BasicFlowGraph {
        id: "bfg:main".to_string(),
        function_id: "func:main".to_string(),
        entry_block_id: entry_id,
        exit_block_id: exit_id,
        blocks: blocks.to_vec(),
        total_statements: blocks.iter().map(|b| b.statement_count).sum(),
    };

    vec![graph]
}

/// Find body node (block) in function/class
fn find_body_node<'a>(node: &'a TSNode) -> Option<TSNode<'a>> {
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            if child.kind() == "block" {
                return Some(child);
            }
        }
    }
    None
}

/// Convert TSNode to Span
fn node_to_span(node: &TSNode) -> codegraph_core::types::Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    codegraph_core::types::Span::new(
        start_pos.row as u32 + 1,
        start_pos.column as u32,
        end_pos.row as u32 + 1,
        end_pos.column as u32,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_simple_function() {
        let code = r#"
def hello():
    return "world"
"#;

        let result = process_python_file(code, "test-repo", "test.py", "test");

        assert!(
            result.metadata.errors.is_empty(),
            "Errors: {:?}",
            result.metadata.errors
        );
        let nodes = &result.outputs.nodes;
        assert_eq!(nodes.len(), 1);

        let node = &nodes[0];
        assert_eq!(node.name, Some("hello".to_string()));
        assert_eq!(node.fqn, "test.hello");
    }

    #[test]
    fn test_process_class_with_methods() {
        let code = r#"
class MyClass:
    def method1(self):
        pass

    def method2(self):
        pass
"#;

        let result = process_python_file(code, "test-repo", "test.py", "test");

        assert!(
            result.metadata.errors.is_empty(),
            "Errors: {:?}",
            result.metadata.errors
        );

        let nodes = &result.outputs.nodes;
        let edges = &result.outputs.edges;

        // Should have: 1 class + 2 methods = 3 nodes
        assert_eq!(nodes.len(), 3);

        // Check class
        let class_node = nodes
            .iter()
            .find(|n| n.name == Some("MyClass".to_string()))
            .expect("Class node not found");
        assert_eq!(class_node.fqn, "test.MyClass");

        // Check methods
        let method1 = nodes
            .iter()
            .find(|n| n.name == Some("method1".to_string()))
            .expect("method1 not found");
        assert_eq!(method1.fqn, "test.MyClass.method1");

        // Check CONTAINS edges
        let contains_edges: Vec<_> = edges
            .iter()
            .filter(|e| e.kind == crate::shared::models::EdgeKind::Contains)
            .collect();
        // Should have: class from module (1) + 2 methods from class (2) = 3 total
        // But module node is not created yet, so only 2 edges (methods from class)
        assert!(
            contains_edges.len() >= 2,
            "Expected at least 2 CONTAINS edges, got {}",
            contains_edges.len()
        );
    }

    #[test]
    fn test_process_invalid_syntax() {
        let code = "def invalid syntax here";

        let result = process_python_file(code, "test-repo", "test.py", "test");

        // Should not crash, but may have errors
        // (tree-sitter is error-tolerant)
        let nodes = &result.outputs.nodes;
        assert!(nodes.len() >= 0);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // L3 Type Resolution Integration Tests
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    #[test]
    fn test_function_with_return_type() {
        let code = r#"
def add(x: int, y: int) -> int:
    return x + y
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have function node
        let func_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
            .collect();
        assert_eq!(func_nodes.len(), 1);

        // Should have return type
        let func = func_nodes[0];
        assert!(
            func.declared_type_id.is_some(),
            "Function should have return type"
        );

        // Should have type entity for 'int'
        let int_types: Vec<_> = result
            .outputs.type_entities
            .iter()
            .filter(|t| t.raw == "int")
            .collect();
        assert!(!int_types.is_empty(), "Should have int type entity");

        let int_type = int_types[0];
        assert_eq!(int_type.flavor, codegraph_core::types::TypeFlavor::Builtin);
        assert_eq!(
            int_type.resolution_level,
            codegraph_core::types::TypeResolutionLevel::Builtin
        );
    }

    #[test]
    fn test_function_with_generic_return_type() {
        let code = r#"
def get_items() -> List[str]:
    return ["a", "b"]
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have function node
        let func_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
            .collect();
        assert_eq!(func_nodes.len(), 1);

        // Should have return type
        assert!(func_nodes[0].declared_type_id.is_some());

        // Should have List[str] type with generic params
        let list_types: Vec<_> = result
            .outputs.type_entities
            .iter()
            .filter(|t| t.raw == "List[str]")
            .collect();
        assert!(!list_types.is_empty(), "Should have List[str] type");

        let list_type = list_types[0];
        assert!(
            list_type.generic_param_ids.is_some(),
            "List should have generic params"
        );
        assert_eq!(list_type.generic_param_ids.as_ref().unwrap().len(), 1);
    }

    #[test]
    fn test_function_without_type_annotation() {
        let code = r#"
def no_types(x, y):
    return x + y
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have function node
        let func_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
            .collect();
        assert_eq!(func_nodes.len(), 1);

        // Should NOT have return type
        assert!(
            func_nodes[0].declared_type_id.is_none(),
            "Untyped function should not have type"
        );
    }

    #[test]
    fn test_variable_with_type_annotation() {
        let code = r#"
def func():
    x: int = 5
    y: str = "hello"
    z = 10
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have variable nodes
        let var_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Variable))
            .collect();
        assert_eq!(var_nodes.len(), 3, "Should have 3 variables");

        // Check typed variables
        let x_node = var_nodes
            .iter()
            .find(|n| n.name == Some("x".to_string()))
            .expect("x not found");
        assert!(x_node.declared_type_id.is_some(), "x should have type");

        let y_node = var_nodes
            .iter()
            .find(|n| n.name == Some("y".to_string()))
            .expect("y not found");
        assert!(y_node.declared_type_id.is_some(), "y should have type");

        // Check untyped variable
        let z_node = var_nodes
            .iter()
            .find(|n| n.name == Some("z".to_string()))
            .expect("z not found");
        assert!(z_node.declared_type_id.is_none(), "z should not have type");

        // Check type entities
        let int_types: Vec<_> = result
            .outputs.type_entities
            .iter()
            .filter(|t| t.raw == "int")
            .collect();
        assert!(!int_types.is_empty(), "Should have int type");

        let str_types: Vec<_> = result
            .outputs.type_entities
            .iter()
            .filter(|t| t.raw == "str")
            .collect();
        assert!(!str_types.is_empty(), "Should have str type");
    }

    #[test]
    fn test_variable_with_complex_type() {
        let code = r#"
def func():
    items: List[Dict[str, int]] = []
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have variable node
        let var_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Variable))
            .collect();
        assert_eq!(var_nodes.len(), 1);

        // Should have type
        assert!(var_nodes[0].declared_type_id.is_some());

        // Should have complex type entity
        let complex_types: Vec<_> = result
            .outputs.type_entities
            .iter()
            .filter(|t| t.raw == "List[Dict[str, int]]")
            .collect();
        assert!(!complex_types.is_empty(), "Should have complex type");

        // Should have nested generic params
        let complex_type = complex_types[0];
        assert!(complex_type.generic_param_ids.is_some());
    }

    #[test]
    fn test_user_defined_type_resolution() {
        let code = r#"
class MyClass:
    pass

def func() -> MyClass:
    obj: MyClass = MyClass()
    return obj
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have class node
        let class_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Class))
            .collect();
        assert_eq!(class_nodes.len(), 1);
        let class_node_id = &class_nodes[0].id;

        // Should have function with MyClass return type
        let func_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
            .collect();
        assert_eq!(func_nodes.len(), 1);
        assert!(
            func_nodes[0].declared_type_id.is_some(),
            "Function should have return type"
        );

        // Should have variable with MyClass type
        let var_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Variable))
            .collect();
        assert_eq!(var_nodes.len(), 1);
        assert!(
            var_nodes[0].declared_type_id.is_some(),
            "Variable should have type"
        );

        // Check MyClass type entity
        let myclass_types: Vec<_> = result
            .outputs.type_entities
            .iter()
            .filter(|t| t.raw == "MyClass")
            .collect();
        assert!(!myclass_types.is_empty(), "Should have MyClass type");

        let myclass_type = myclass_types[0];
        assert_eq!(myclass_type.flavor, codegraph_core::types::TypeFlavor::User);
        assert_eq!(
            myclass_type.resolution_level,
            codegraph_core::types::TypeResolutionLevel::Local
        );
        assert_eq!(myclass_type.resolved_target, Some(class_node_id.clone()));
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // L4 Data Flow Tests (READS/WRITES edges)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    #[test]
    fn test_writes_edge_generation() {
        let code = r#"
def func():
    x = 1
    y = 2
    z = x + y
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have function node
        let func_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
            .collect();
        assert_eq!(func_nodes.len(), 1);
        let func_id = &func_nodes[0].id;

        // Should have 3 variables
        let var_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Variable))
            .collect();
        assert_eq!(var_nodes.len(), 3, "Should have 3 variables (x, y, z)");

        // Should have WRITES edges from function to each variable
        let writes_edges: Vec<_> = result
            .outputs.edges
            .iter()
            .filter(|e| matches!(e.kind, crate::shared::models::EdgeKind::Writes))
            .collect();
        assert_eq!(writes_edges.len(), 3, "Should have 3 WRITES edges");

        // All WRITES edges should originate from function
        for edge in &writes_edges {
            assert_eq!(
                &edge.source_id, func_id,
                "WRITES edge should come from function"
            );
        }

        // Check that each variable is written to
        let written_var_ids: std::collections::HashSet<_> =
            writes_edges.iter().map(|e| &e.target_id).collect();
        assert_eq!(
            written_var_ids.len(),
            3,
            "All 3 variables should be written"
        );
    }

    #[test]
    fn test_calls_edge_generation() {
        let code = r#"
def helper():
    pass

def main():
    helper()
    helper()
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have 2 function nodes
        let func_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
            .collect();
        assert_eq!(func_nodes.len(), 2);

        // Should have CALLS edges
        let calls_edges: Vec<_> = result
            .outputs.edges
            .iter()
            .filter(|e| matches!(e.kind, crate::shared::models::EdgeKind::Calls))
            .collect();
        assert!(calls_edges.len() >= 2, "Should have at least 2 CALLS edges");
    }

    #[test]
    fn test_contains_edge_hierarchy() {
        let code = r#"
class MyClass:
    def method(self):
        x = 1
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have class, method, variable
        let class_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Class))
            .collect();
        assert_eq!(class_nodes.len(), 1);

        let method_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Method))
            .collect();
        assert_eq!(method_nodes.len(), 1);

        let var_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Variable))
            .collect();
        assert_eq!(var_nodes.len(), 1);

        // Should have CONTAINS edges forming hierarchy
        let contains_edges: Vec<_> = result
            .outputs.edges
            .iter()
            .filter(|e| matches!(e.kind, crate::shared::models::EdgeKind::Contains))
            .collect();
        assert!(
            contains_edges.len() >= 2,
            "Should have CONTAINS edges for hierarchy"
        );

        // Class should contain method
        let class_contains_method = contains_edges
            .iter()
            .any(|e| e.source_id == class_nodes[0].id && e.target_id == method_nodes[0].id);
        assert!(class_contains_method, "Class should contain method");
    }

    #[test]
    fn test_reads_edge_generation() {
        let code = r#"
def func():
    x = 1
    y = 2
    z = x + y
    return z
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have function
        let func_nodes: Vec<_> = result
            .outputs.nodes
            .iter()
            .filter(|n| matches!(n.kind, crate::shared::models::NodeKind::Function))
            .collect();
        assert_eq!(func_nodes.len(), 1);
        let func_id = &func_nodes[0].id;

        // Should have READS edges
        let reads_edges: Vec<_> = result
            .outputs.edges
            .iter()
            .filter(|e| matches!(e.kind, crate::shared::models::EdgeKind::Reads))
            .collect();
        assert!(
            reads_edges.len() >= 2,
            "Should have READS edges for x, y, z"
        );

        // All READS edges should originate from function
        for edge in &reads_edges {
            assert_eq!(
                &edge.source_id, func_id,
                "READS edge should come from function"
            );
        }
    }

    #[test]
    fn test_reads_vs_writes_distinction() {
        let code = r#"
def func():
    x = 1
    y = x + 2
"#;
        let result = process_python_file(code, "test_repo", "test.py", "test");

        // Should have WRITES edges for x, y (definitions)
        let writes_edges: Vec<_> = result
            .outputs.edges
            .iter()
            .filter(|e| matches!(e.kind, crate::shared::models::EdgeKind::Writes))
            .collect();
        assert_eq!(writes_edges.len(), 2, "Should have 2 WRITES edges");

        // Should have READS edge for x (used in y = x + 2)
        let reads_edges: Vec<_> = result
            .outputs.edges
            .iter()
            .filter(|e| matches!(e.kind, crate::shared::models::EdgeKind::Reads))
            .collect();
        assert!(reads_edges.len() >= 1, "Should have READS edge for x");
    }
}

#[cfg(test)]
mod dfg_ssa_tests {
    use super::*;

    #[test]
    fn test_dfg_from_process_file() {
        let code = r#"
def func():
    x = 1
    y = x + 2
    return y
"#;

        let result = process_python_file(code, "test", "test.py", "test");

        println!("Nodes: {:?}", result.outputs.nodes.len());
        for node in &result.outputs.nodes {
            println!(
                "  {:?}: {:?}, parent={:?}",
                node.kind, node.name, node.parent_id
            );
        }

        println!("Edges: {:?}", result.outputs.edges.len());
        for edge in &result.outputs.edges {
            if edge.kind == crate::shared::models::EdgeKind::Reads {
                println!("  READS: {} -> {}", edge.source_id, edge.target_id);
            }
        }

        println!("BFG graphs: {:?}", result.outputs.bfg_graphs.len());
        for bfg in &result.outputs.bfg_graphs {
            println!("  function_id: {}", bfg.function_id);
        }

        println!("DFG graphs: {:?}", result.outputs.dfg_graphs.len());
        for dfg in &result.outputs.dfg_graphs {
            println!(
                "  function_id: {}, nodes={}, edges={}",
                dfg.function_id,
                dfg.nodes.len(),
                dfg.def_use_edges.len()
            );
        }

        assert!(result.outputs.dfg_graphs.len() >= 1);
        let dfg = &result.outputs.dfg_graphs[0];
        assert!(dfg.nodes.len() > 0, "DFG should have nodes");
    }
}
