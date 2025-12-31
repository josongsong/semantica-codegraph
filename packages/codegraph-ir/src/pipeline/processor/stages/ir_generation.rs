//! L1-L2: IR Generation and Occurrence Extraction
//!
//! Extracted from processor_legacy.rs (lines 300-1233)
//!
//! This stage handles:
//! - AST traversal and IR node/edge generation (L1)
//! - Per-function BFG (Basic Flow Graph) creation
//! - Occurrence generation from IR for SCIP indexing (L2)
//!
//! # Functions
//! - `generate_occurrences()` - Convert IR to SCIP occurrences (168 LOC)
//! - `process_with_bfg()` - Process AST with BFG visitor (112 LOC)
//! - `traverse_node()` - Simple AST traversal (31 LOC)
//! - `process_function()` - Function IR generation (84 LOC)
//! - `process_class()` - Class IR generation (83 LOC)

use std::collections::HashMap;
use tree_sitter::Node as TSNode;

use crate::features::flow_graph::infrastructure::bfg::{BasicFlowGraph, BfgVisitor};
use crate::features::ir_generation::infrastructure::ir_builder::IRBuilder;
use crate::features::ir_generation::infrastructure::visitor::traverse_with_visitor;
use crate::features::parsing::infrastructure::extractors::{
    call::extract_calls_in_block, class::extract_class_info, fqn_resolver::FqnResolver,
    function::extract_function_info, identifier::extract_identifiers_in_expression,
    variable::extract_variables_in_block,
};
use crate::features::parsing::ports::LanguagePlugin;
use crate::pipeline::processor::helpers::{find_body_node, node_to_span};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Occurrence, SymbolRole};

/// Generate SCIP occurrences from IR nodes and edges (L2)
///
/// Converts the IR graph into SCIP-compatible occurrence records for indexing.
/// Each occurrence represents a symbol definition or reference with:
/// - Symbol ID and span (location)
/// - Role (definition, read, write, import)
/// - Importance score (for ranking)
/// - Parent symbol (for hierarchy)
///
/// # Performance
/// - O(N + E) where N = nodes, E = edges
/// - Uses HashMap index for O(1) edge lookups
/// - Pre-allocates Vec capacity for efficiency
///
/// # Arguments
/// * `nodes` - IR nodes (symbols: functions, classes, variables, etc.)
/// * `edges` - IR edges (calls, reads, writes, etc.)
///
/// # Returns
/// Vector of occurrences (definitions + references)
pub fn generate_occurrences(nodes: &[Node], edges: &[Edge]) -> Vec<Occurrence> {
    let mut occurrences = Vec::with_capacity(nodes.len() + edges.len());
    let mut counter = 0u64;

    // Build node index for edge lookup (O(N) once, not O(N) per edge)
    let node_by_id: HashMap<&str, &Node> = nodes.iter().map(|n| (n.id.as_str(), n)).collect();

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
            span: node.span.clone(),
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
            _ => continue, // Skip other edge types for occurrences
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
            .clone()
            .unwrap_or_else(|| source_node.span.clone());

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

/// Process AST with per-function BFG creation (L1)
///
/// Traverses the AST and:
/// 1. Processes function/class definitions → IR nodes/edges
/// 2. Creates dedicated BFG (Basic Flow Graph) for each function
/// 3. Handles imports for cross-file resolution (RFC-062)
///
/// # BFG Structure
/// Each function gets: entry block → body blocks → exit block
///
/// # Arguments
/// * `node` - Current AST node to process
/// * `source` - Source code text
/// * `builder` - IR builder (accumulates nodes/edges)
/// * `all_bfg_graphs` - Accumulator for BFG graphs
/// * `errors` - Error accumulator
/// * `language_plugin` - Language-specific parser
pub fn process_with_bfg(
    node: &TSNode,
    source: &str,
    builder: &mut IRBuilder,
    all_bfg_graphs: &mut Vec<BasicFlowGraph>,
    errors: &mut Vec<String>,
    language_plugin: &dyn LanguagePlugin,
) {
    match node.kind() {
        // RFC-062: Process import statements for cross-file resolution
        "import_statement" => {
            if let Some(import_info) = crate::features::parsing::infrastructure::extractors::import::extract_import_statement(node, source) {
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
            if let Some(import_info) = crate::features::parsing::infrastructure::extractors::import::extract_import_from_statement(node, source) {
                builder.create_import_node(
                    import_info.module,
                    import_info.names,
                    import_info.alias,
                    import_info.span,
                    true, // from import
                );
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
                let mut func_bfg_visitor = BfgVisitor::new(language_plugin);
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
                    process_with_bfg(
                        &child,
                        source,
                        builder,
                        all_bfg_graphs,
                        errors,
                        language_plugin,
                    );
                }
            }
        }
    }
}

/// Simple AST traversal for IR generation (L1)
///
/// Recursively processes function and class definitions.
/// Used when BFG creation is not needed.
///
/// # Arguments
/// * `node` - Current AST node
/// * `source` - Source code text
/// * `builder` - IR builder
/// * `errors` - Error accumulator
#[allow(dead_code)]
pub fn traverse_node(
    node: &TSNode,
    source: &str,
    builder: &mut IRBuilder,
    errors: &mut Vec<String>,
) {
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

/// Process function definition node → IR (L1)
///
/// Creates:
/// - Function/Method node
/// - Variable nodes (from function body)
/// - WRITES edges (function → variables)
/// - CALLS edges (function → callees, with FQN resolution)
/// - READS edges (function → identifiers)
///
/// # FQN Resolution (SOTA)
/// Built-in FQN resolver converts "input" → "builtins.input"
///
/// # Arguments
/// * `node` - function_definition AST node
/// * `source` - Source code text
/// * `builder` - IR builder
/// * `is_method` - true if this is a class method
///
/// # Returns
/// Ok(()) on success, Err(msg) on failure
pub fn process_function(
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
        None, // body_span - TODO: extract from AST
        is_method,
        func_info.docstring,
        source_text,
        func_info.return_type,
    )?;

    // Process function body (variables and calls)
    if let Some(body_node) = find_body_node(node) {
        #[cfg(feature = "trace")]
        eprintln!("[TRACE] Found body node for function");

        // Extract variables
        let variables = extract_variables_in_block(&body_node, source);
        #[cfg(feature = "trace")]
        eprintln!("[TRACE] Extracted {} variables", variables.len());

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

        // Extract calls and resolve FQNs (SOTA: Built-in resolution)
        let calls = extract_calls_in_block(&body_node, source);
        let fqn_resolver = FqnResolver::new();

        for call in calls {
            // Resolve callee name to FQN (e.g., "input" → "builtins.input")
            let callee_fqn = fqn_resolver.resolve(&call.callee_name);

            // Add CALLS edge with FQN
            builder.add_calls_edge(node_id.clone(), callee_fqn.clone(), call.span);
        }

        // Extract identifier reads (READS edges)
        let identifiers = extract_identifiers_in_expression(&body_node, source);
        for identifier in identifiers {
            // Add READS edge (function reads variable)
            builder.add_reads_edge(node_id.clone(), identifier.name, identifier.span);
        }
    }

    // Finish scope
    builder.finish_scope();

    Ok(())
}

/// Process class definition node → IR (L1)
///
/// Creates:
/// - Class node with base classes and docstring
/// - Processes methods (as functions with is_method=true)
/// - Processes nested classes recursively
/// - Handles decorated definitions (@property, @staticmethod, etc.)
///
/// # Arguments
/// * `node` - class_definition AST node
/// * `source` - Source code text
/// * `builder` - IR builder
///
/// # Returns
/// Ok(()) on success, Err(msg) on failure
pub fn process_class(node: &TSNode, source: &str, builder: &mut IRBuilder) -> Result<(), String> {
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
        None, // body_span - TODO: extract from AST
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{EdgeKind, NodeKind, Span};

    #[test]
    fn test_generate_occurrences_basic() {
        let node = Node::new(
            "func:test".to_string(),
            NodeKind::Function,
            "test".to_string(),    // fqn
            "test.py".to_string(), // file_path
            Span::new(1, 0, 1, 10),
        )
        .with_docstring("Test function".to_string());

        let nodes = vec![node];
        let edges = vec![];

        let occs = generate_occurrences(&nodes, &edges);

        assert_eq!(occs.len(), 1);
        assert_eq!(occs[0].symbol_id, "func:test");
        assert_eq!(occs[0].roles, SymbolRole::Definition as u8);
        assert!(occs[0].importance_score > 0.5); // Has docstring, public name
    }

    #[test]
    fn test_generate_occurrences_with_edges() {
        let caller = Node::new(
            "func:caller".to_string(),
            NodeKind::Function,
            "caller".to_string(),  // fqn
            "test.py".to_string(), // file_path
            Span::new(1, 0, 1, 10),
        );

        let callee = Node::new(
            "func:callee".to_string(),
            NodeKind::Function,
            "callee".to_string(),  // fqn
            "test.py".to_string(), // file_path
            Span::new(2, 0, 2, 10),
        );

        let nodes = vec![caller, callee];

        let call_edge = Edge::new(
            "func:caller".to_string(),
            "func:callee".to_string(),
            EdgeKind::Calls,
        )
        .with_span(Span::new(1, 5, 1, 10));

        let edges = vec![call_edge];

        let occs = generate_occurrences(&nodes, &edges);

        // Should have 2 definitions + 1 reference
        assert_eq!(occs.len(), 3);

        // Find the reference occurrence
        let ref_occ = occs
            .iter()
            .find(|o| o.symbol_id == "func:callee" && o.roles == SymbolRole::ReadAccess as u8);
        assert!(ref_occ.is_some());
    }
}
