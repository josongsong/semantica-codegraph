//! L4-L5: Data Flow and SSA Construction
//!
//! Extracted from processor_legacy.rs (lines 708-881)
//!
//! This stage handles:
//! - DFG (Data Flow Graph) construction from IR (L4)
//! - SSA (Static Single Assignment) graph construction (L5)
//!
//! # Functions
//! - `build_dfg_graphs()` - Build DFG for each function (69 LOC)
//! - `build_ssa_graphs()` - Build SSA from IR nodes (56 LOC)
//! - `build_ssa_graphs_with_extraction()` - Build SSA with AST extraction (56 LOC)

use crate::features::data_flow::infrastructure::dfg::{build_dfg, DataFlowGraph};
use crate::features::flow_graph::infrastructure::bfg::BasicFlowGraph;
use crate::features::parsing::ports::LanguageId;
use crate::features::ssa::infrastructure::ssa::{build_ssa, SSAGraph};
use crate::pipeline::processor::helpers::find_containing_block;
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind};
use tree_sitter::Node as TSNode;

/// Build DFG (Data Flow Graph) for all functions (L4)
///
/// For each function:
/// 1. Extract variable definitions (from Variable nodes)
/// 2. Extract variable uses (from READS edges)
/// 3. Build DFG connecting definitions to uses
///
/// # Algorithm
/// - O(N×F) where N = nodes, F = functions
/// - Uses BFG function names to group variables
///
/// # Arguments
/// * `nodes` - IR nodes (includes Variable nodes)
/// * `edges` - IR edges (includes READS edges)
/// * `bfg_graphs` - BFG graphs (one per function)
///
/// # Returns
/// Vector of DataFlowGraph, one per function
pub fn build_dfg_graphs(
    nodes: &[Node],
    edges: &[Edge],
    bfg_graphs: &[BasicFlowGraph],
) -> Vec<DataFlowGraph> {
    let mut dfg_graphs = Vec::new();

    // For each function, extract variables and build DFG
    for bfg in bfg_graphs {
        // Find function node by name to get its ID
        // bfg.function_id is the function NAME (e.g., "func")
        // We need to find the function NODE to get its ID for parent_id matching
        let func_node = nodes.iter().find(|n| {
            (n.kind == NodeKind::Function || n.kind == NodeKind::Method)
                && n.name.as_deref() == Some(bfg.function_id.as_str())
        });

        let Some(func) = func_node else {
            // Function not found
            dfg_graphs.push(build_dfg(bfg.function_id.clone(), &[], &[]));
            continue;
        };

        let func_id = &func.id;

        // Extract definitions from Variable nodes
        let mut definitions = Vec::new();

        for node in nodes {
            if node.kind == NodeKind::Variable {
                if let Some(parent_id) = &node.parent_id {
                    if parent_id == func_id {
                        definitions.push((node.name.clone().unwrap_or_default(), node.span));
                    }
                }
            }
        }

        // Extract uses from READS edges
        // CRITICAL FIX: Collect ALL reads within the function, not just function-level reads
        // Build set of all nodes within this function (including descendants)
        let mut func_nodes = std::collections::HashSet::new();
        func_nodes.insert(func_id.clone());

        // Collect all descendant nodes (BFS traversal)
        let mut to_process = vec![func_id.clone()];
        while let Some(current_id) = to_process.pop() {
            for node in nodes {
                if let Some(parent_id) = &node.parent_id {
                    if parent_id == &current_id && func_nodes.insert(node.id.clone()) {
                        to_process.push(node.id.clone());
                    }
                }
            }
        }

        // Now collect READS edges from ANY node within this function
        let mut uses = Vec::new();
        for edge in edges {
            if edge.kind == EdgeKind::Reads && func_nodes.contains(&edge.source_id) {
                if let Some(span) = edge.span {
                    uses.push((edge.target_id.clone(), span));
                }
            }
        }

        // Build DFG
        let dfg = build_dfg(bfg.function_id.clone(), &definitions, &uses);

        dfg_graphs.push(dfg);
    }

    dfg_graphs
}

/// Build SSA graphs with multi-language variable extraction (L5)
///
/// Uses language-specific AST extractors to find variable definitions,
/// then builds SSA graph with phi nodes at merge points.
///
/// # Multi-language Support
/// Supports Python, TypeScript, JavaScript, Java, Kotlin, Rust, Go
///
/// # Arguments
/// * `nodes` - IR nodes (for function lookup)
/// * `bfg_graphs` - BFG graphs (for block structure)
/// * `root_node` - AST root node
/// * `source` - Source code text
/// * `lang_id` - Language identifier
///
/// # Returns
/// Vector of SSAGraph, one per function
pub fn build_ssa_graphs_with_extraction(
    nodes: &[Node],
    bfg_graphs: &[BasicFlowGraph],
    root_node: &TSNode,
    source: &str,
    lang_id: &LanguageId,
) -> Vec<SSAGraph> {
    use crate::features::parsing::infrastructure::extractors::get_variable_extractor;

    let mut ssa_graphs = Vec::new();

    // Get language-specific variable extractor
    let language_str = match lang_id {
        LanguageId::Python => "python",
        LanguageId::TypeScript => "typescript",
        LanguageId::JavaScript => "javascript",
        LanguageId::Java => "java",
        LanguageId::Kotlin => "kotlin",
        LanguageId::Rust => "rust",
        LanguageId::Go => "go",
    };

    let extractor = get_variable_extractor(language_str);

    // For each function, extract definitions and build SSA
    for bfg in bfg_graphs {
        // Extract variables directly from AST using language-specific extractor
        let variables = extractor.extract_variables(root_node, source);

        // Map variables to blocks
        let mut definitions = Vec::new();
        for var in variables {
            let block_id = find_containing_block(&var.span, &bfg.blocks)
                .unwrap_or_else(|| bfg.entry_block_id.clone());

            definitions.push((var.name, block_id));
        }

        // Build SSA
        let ssa = build_ssa(bfg.function_id.clone(), &definitions);

        ssa_graphs.push(ssa);
    }

    ssa_graphs
}

/// Build SSA graphs from IR nodes (L5)
///
/// Simpler version that uses Variable nodes from IR instead of AST extraction.
/// Uses find_containing_block to map variables to blocks for phi placement.
///
/// # Arguments
/// * `nodes` - IR nodes (includes Variable nodes)
/// * `bfg_graphs` - BFG graphs (for block structure)
///
/// # Returns
/// Vector of SSAGraph, one per function
pub fn build_ssa_graphs(nodes: &[Node], bfg_graphs: &[BasicFlowGraph]) -> Vec<SSAGraph> {
    let mut ssa_graphs = Vec::new();

    // For each function, extract definitions and build SSA
    for bfg in bfg_graphs {
        // Find function node by name to get its ID
        let func_node = nodes.iter().find(|n| {
            (n.kind == NodeKind::Function || n.kind == NodeKind::Method)
                && n.name.as_deref() == Some(bfg.function_id.as_str())
        });

        let Some(func) = func_node else {
            // Function not found
            ssa_graphs.push(build_ssa(bfg.function_id.clone(), &[]));
            continue;
        };

        let func_id = &func.id;

        // Extract variable definitions with block info
        let mut definitions = Vec::new();

        // Find variable nodes for this function (by parent_id)
        for node in nodes {
            if node.kind == NodeKind::Variable {
                if let Some(parent_id) = &node.parent_id {
                    if parent_id == func_id {
                        // Map variable to block based on span (finds smallest containing block)
                        let block_id = find_containing_block(&node.span, &bfg.blocks)
                            .unwrap_or_else(|| bfg.entry_block_id.clone());

                        definitions.push((node.name.clone().unwrap_or_default(), block_id));
                    }
                }
            }
        }

        // Build SSA
        let ssa = build_ssa(bfg.function_id.clone(), &definitions);

        ssa_graphs.push(ssa);
    }

    ssa_graphs
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    #[test]
    fn test_build_dfg_graphs_empty() {
        let nodes = vec![];
        let edges = vec![];
        let bfg_graphs = vec![];

        let dfgs = build_dfg_graphs(&nodes, &edges, &bfg_graphs);

        assert_eq!(dfgs.len(), 0);
    }

    #[test]
    fn test_build_ssa_graphs_empty() {
        let nodes = vec![];
        let bfg_graphs = vec![];

        let ssas = build_ssa_graphs(&nodes, &bfg_graphs);

        assert_eq!(ssas.len(), 0);
    }

    #[test]
    fn test_build_dfg_with_function() {
        let func_node = Node::new(
            "func:test".to_string(),
            NodeKind::Function,
            "test".to_string(),    // fqn
            "test.py".to_string(), // file_path
            Span::new(1, 0, 5, 0),
        );

        let mut var_node = Node::new(
            "var:x".to_string(),
            NodeKind::Variable,
            "x".to_string(),       // fqn
            "test.py".to_string(), // file_path
            Span::new(2, 4, 2, 5),
        );
        var_node.parent_id = Some("func:test".to_string());

        let nodes = vec![func_node, var_node];
        let edges = vec![];

        let bfg = BasicFlowGraph {
            id: "bfg:test".to_string(),
            function_id: "test".to_string(),
            entry_block_id: "entry".to_string(),
            exit_block_id: "exit".to_string(),
            blocks: vec![],
            total_statements: 0,
        };

        let dfgs = build_dfg_graphs(&nodes, &edges, &[bfg]);

        assert_eq!(dfgs.len(), 1);
        assert_eq!(dfgs[0].function_id, "test");
    }
}
